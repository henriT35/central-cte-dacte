from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, MutableMapping

from ..decisions import StatusAuditReport, StatusDecisionEngine

BRIDGE_VERSION = "2.6.66.9"
MODE_MODULAR_UNIFIED = "modular_unified"
MODE_LEGACY_SHADOW = "legacy_shadow"
VALID_MODES = {MODE_MODULAR_UNIFIED, MODE_LEGACY_SHADOW}


def _legacy_filter_match(status: Any, selected_filter: Any, normalize: Any) -> bool:
    current = str(selected_filter or "TODOS")
    n = normalize(status)
    if current == "TODOS":
        return True
    if current == "NÃO VALIDADO":
        return n == "NAO VALIDADO"
    if current == "OK":
        return n.startswith("OK")
    if current == "DIVERGENTES":
        return "DIVERGENTE" in n
    if current == "REVISÃO":
        return any(x in n for x in ["REVISAR", "REVISAO", "AMBIG", "MULTIPLAS", "REGRA SEM VALOR", "PENDENTE"])
    if current == "SEM BASE":
        return "NF NAO ENCONTRADA" in n or "ORIGINAL NAO ENCONTRADO" in n or "BASE" in n
    if current == "SEM PARCEIRO/REGRA":
        return "PARCEIRO" in n or "REGRA" in n
    if current == "ERROS":
        return "ERRO" in n or "NAO E CT-E" in n or "NF NAO LIDA" in n
    if current.startswith("STATUS: "):
        return str(status or "") == current.split(":", 1)[1].strip()
    return True


def install_status_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    normalize = module_globals.get("norm_text")
    legacy_report_bucket = module_globals.get("report_bucket")
    legacy_validate = module_globals.get("validate_cte_value")
    app_class = module_globals.get("App")
    if not callable(normalize) or not callable(legacy_report_bucket) or not callable(legacy_validate):
        return {
            "version": BRIDGE_VERSION,
            "active": False,
            "reason": "dependências legadas de status ausentes",
        }

    paths = services.resolve("paths")
    logger = services.resolve("logger")
    try:
        settings = services.resolve("settings")
    except Exception:
        settings = None
    memory_settings: dict[str, Any] = {}
    report_dir = Path(paths.reports) / "classificador_status_sombra"
    audit = StatusAuditReport(report_dir)
    engine = StatusDecisionEngine()
    sessions_dir = Path(getattr(paths, "sessions", Path(paths.reports).parent / "sessoes"))
    emergency_flag = sessions_dir / "FORCAR_CLASSIFICADOR_STATUS_LEGADO.flag"

    def log(message: str) -> None:
        try:
            logger.write("classificador_status", message=str(message))
        except Exception:
            pass

    def get_mode() -> str:
        environment_mode = str(os.environ.get("CENTRAL_CTE_STATUS_MODE", "") or "").strip().lower()
        if environment_mode in VALID_MODES:
            return environment_mode
        if emergency_flag.exists():
            return MODE_LEGACY_SHADOW
        try:
            source = settings.load() if settings is not None else memory_settings
            configured = str(source.get("status_decision_mode", "") or "").strip().lower()
            if configured in VALID_MODES:
                return configured
        except Exception:
            pass
        return MODE_MODULAR_UNIFIED

    def set_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_MODES)}")
        if settings is None:
            memory_settings["status_decision_mode"] = normalized
        else:
            values = settings.load()
            values["status_decision_mode"] = normalized
            settings.save(values)
        return normalized

    def classify_validation_status(status: Any) -> dict[str, Any]:
        decision = engine.classify(status)
        audit.record(status=decision.raw_status, consumer="classify", modular=decision.to_dict())
        return decision.to_dict()

    def centralized_report_bucket(status: Any) -> str:
        decision = engine.classify(status)
        modular = decision.report_bucket
        try:
            legacy = legacy_report_bucket(status)
        except Exception as exc:
            legacy = f"ERRO:{exc}"
        audit.record(status=decision.raw_status, consumer="report_bucket", modular=modular, legacy=legacy)
        return legacy if get_mode() == MODE_LEGACY_SHADOW and not str(legacy).startswith("ERRO:") else modular

    def centralized_status_matches_filter(status: Any, selected_filter: Any) -> bool:
        modular = engine.matches_filter(status, selected_filter)
        try:
            legacy = _legacy_filter_match(status, selected_filter, normalize)
        except Exception as exc:
            legacy = f"ERRO:{exc}"
        audit.record(
            status=str(status or ""),
            consumer="filter_match",
            modular=modular,
            legacy=legacy,
            context={"filter": str(selected_filter or "TODOS")},
        )
        return bool(legacy) if get_mode() == MODE_LEGACY_SHADOW and not isinstance(legacy, str) else modular

    def decorated_validate_cte_value(info: Any, base_data: Any, tables: Any) -> Any:
        result = legacy_validate(info, base_data, tables)
        if not isinstance(result, dict):
            return result
        decorated = engine.decorate_result(result)
        decision = engine.classify(result.get("status"))
        audit.record(
            status=decision.raw_status,
            consumer="validation_result",
            modular={
                "family": decision.family.value,
                "disposition": decision.disposition.value,
                "bucket": decision.report_bucket,
                "tags": list(decision.tags),
            },
            context={
                "cte": str((info or {}).get("numero", "")) if isinstance(info, dict) else "",
                "serie": str((info or {}).get("serie", "")) if isinstance(info, dict) else "",
            },
        )
        return result if get_mode() == MODE_LEGACY_SHADOW else decorated

    module_globals["LEGACY_STATUS_REPORT_BUCKET"] = legacy_report_bucket
    module_globals["LEGACY_STATUS_VALIDATE_CTE_VALUE"] = legacy_validate
    module_globals["report_bucket"] = centralized_report_bucket
    module_globals["validate_cte_value"] = decorated_validate_cte_value
    module_globals["classify_validation_status"] = classify_validation_status
    module_globals["status_matches_filter"] = centralized_status_matches_filter
    module_globals["get_status_decision_mode"] = get_mode
    module_globals["set_status_decision_mode"] = set_mode
    module_globals["get_status_decision_summary"] = audit.snapshot
    module_globals["MODULAR_STATUS_ENGINE"] = engine
    module_globals["MODULAR_STATUS_REPORTER"] = audit
    module_globals["MODULAR_STATUS_REPORT_DIR"] = report_dir
    module_globals["MODULAR_STATUS_EMERGENCY_FLAG"] = emergency_flag
    module_globals["MODULAR_STATUS_VERSION"] = BRIDGE_VERSION

    patched_methods: list[str] = []
    patched_app_classes: set[int] = set()

    def patch_app_class(candidate: Any | None = None) -> list[str]:
        app_class = candidate if isinstance(candidate, type) else module_globals.get("App")
        if not isinstance(app_class, type):
            return []
        if id(app_class) in patched_app_classes or getattr(app_class, "_central_cte_status_ui_2669", False):
            return list(patched_methods)
        legacy_filter_method = getattr(app_class, "status_matches_current_filter", None)
        legacy_update_stats = getattr(app_class, "update_stats", None)
        legacy_summary_text = getattr(app_class, "validation_summary_text", None)

        if callable(legacy_filter_method):
            setattr(app_class, "LEGACY_STATUS_MATCHES_CURRENT_FILTER", legacy_filter_method)

            def status_matches_current_filter(self: Any, status: Any) -> bool:
                try:
                    selected = self.filter_status_var.get() if hasattr(self, "filter_status_var") else "TODOS"
                except Exception:
                    selected = "TODOS"
                return centralized_status_matches_filter(status, selected)

            setattr(app_class, "status_matches_current_filter", status_matches_current_filter)
            patched_methods.append("App.status_matches_current_filter")

        if callable(legacy_update_stats):
            setattr(app_class, "LEGACY_STATUS_UPDATE_STATS", legacy_update_stats)

            def update_stats(self: Any) -> Any:
                output = legacy_update_stats(self)
                rows = list(getattr(self, "files", []) or [])
                modular_count, modular_value = engine.count_divergences(rows)
                legacy_count = 0
                legacy_value = 0.0
                for row in rows:
                    result = row.get("validacao") or {}
                    if "DIVERGENTE" in normalize(result.get("status", "")):
                        legacy_count += 1
                        try:
                            legacy_value += abs(float(result.get("diferenca") or 0.0))
                        except Exception:
                            try:
                                legacy_value += abs(float(module_globals.get("parse_number_br")(result.get("diferenca", 0.0))))
                            except Exception:
                                pass
                audit.record(
                    status="LOTE",
                    consumer="card_divergencias",
                    modular={"quantidade": modular_count, "valor": round(modular_value, 6)},
                    legacy={"quantidade": legacy_count, "valor": round(legacy_value, 6)},
                )
                if get_mode() == MODE_MODULAR_UNIFIED and hasattr(self, "card_diff"):
                    try:
                        money = module_globals.get("money")
                        formatted = money(modular_value) if callable(money) else f"{modular_value:.2f}"
                        self.card_diff.set_values(str(modular_count), f"R$ {formatted}")
                    except Exception:
                        pass
                return output

            setattr(app_class, "update_stats", update_stats)
            patched_methods.append("App.update_stats")

        if callable(legacy_summary_text):
            setattr(app_class, "LEGACY_STATUS_VALIDATION_SUMMARY_TEXT", legacy_summary_text)

            def validation_summary_text(self: Any, counts: Any = None) -> str:
                legacy_text = legacy_summary_text(self, counts)
                effective_counts = dict(counts or {})
                if not effective_counts:
                    for info in list(getattr(self, "files", []) or []):
                        try:
                            status = self.validation_status_of(info)
                        except Exception:
                            status = str(((info or {}).get("validacao") or {}).get("status") or "NÃO VALIDADO")
                        effective_counts[status] = effective_counts.get(status, 0) + 1
                modular_summary = engine.summarize_counts(effective_counts)
                legacy_div = None
                legacy_review = None
                match = re.search(r"^Divergentes:\s*(\d+)", legacy_text, flags=re.MULTILINE)
                if match:
                    legacy_div = int(match.group(1))
                match = re.search(r"^Para revisão/erro/sem cadastro:\s*(\d+)", legacy_text, flags=re.MULTILINE)
                if match:
                    legacy_review = int(match.group(1))
                audit.record(
                    status="LOTE",
                    consumer="resumo_validacao",
                    modular={"divergentes": modular_summary["divergent"], "revisao": modular_summary["review_total"]},
                    legacy={"divergentes": legacy_div, "revisao": legacy_review},
                )
                if get_mode() == MODE_LEGACY_SHADOW:
                    return legacy_text
                text = re.sub(
                    r"^Divergentes:\s*\d+",
                    f"Divergentes: {modular_summary['divergent']}",
                    legacy_text,
                    flags=re.MULTILINE,
                )
                text = re.sub(
                    r"^Para revisão/erro/sem cadastro:\s*\d+",
                    f"Para revisão/erro/sem cadastro: {modular_summary['review_total']}",
                    text,
                    flags=re.MULTILINE,
                )
                return text

            setattr(app_class, "validation_summary_text", validation_summary_text)
            patched_methods.append("App.validation_summary_text")

        setattr(app_class, "_central_cte_status_ui_2669", True)
        patched_app_classes.add(id(app_class))
        return list(patched_methods)

    patch_app_class(app_class)
    module_globals["rescan_status_ui_bridge"] = patch_app_class

    try:
        services.register_instance("status_decision_engine", engine, replace=True)
        services.register_instance("status_decision_report", audit, replace=True)
    except Exception as exc:
        log(f"Não foi possível registrar serviços de status: {exc}")

    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": get_mode(),
        "official_strategy": "single_modular_status_classifier",
        "raw_status_preserved": True,
        "validation_result_decorated": True,
        "patched_global_functions": ["report_bucket", "validate_cte_value"],
        "patched_methods": patched_methods,
        "ui_activation": "event_driven_rescan",
        "report_directory": str(report_dir),
        "session_id": audit.session_id,
        "emergency_rollback_flag": str(emergency_flag),
        "latest_reports": [
            str(report_dir / "ultima_auditoria_status.json"),
            str(report_dir / "ultima_auditoria_status.txt"),
            str(report_dir / "ultima_auditoria_status.csv"),
            str(audit.jsonl_path),
        ],
    }
