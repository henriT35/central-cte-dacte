from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any, MutableMapping

from ..invoices import (
    InvoiceAuditReport,
    InvoiceDecisionAuditEngine,
    InvoiceDecisionAuditReport,
    InvoiceInputAuditEngine,
    InvoiceInputAuditReport,
    InvoicePromotionEngine,
    InvoicePromotionReport,
    InvoiceShadowEngine,
    InvoiceShadowService,
)
from ..invoices.normalization import stable_hash

BRIDGE_VERSION = "2.6.67.3"


def install_invoice_shadow_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    paths = services.resolve("paths")
    logger = services.resolve("logger")
    settings = services.resolve("settings")
    report_dir = Path(paths.reports) / "motor_faturas_sombra"
    input_report_dir = Path(paths.reports) / "motor_faturas_entrada_sombra"
    decision_report_dir = Path(paths.reports) / "motor_faturas_decisao_sombra"
    promotion_report_dir = Path(paths.reports) / "motor_faturas_promocao"
    for directory in (report_dir, input_report_dir, decision_report_dir, promotion_report_dir):
        directory.mkdir(parents=True, exist_ok=True)

    emergency_flag = Path(paths.sessions) / "DESATIVAR_MOTOR_FATURAS_SOMBRA.flag"
    input_emergency_flag = Path(paths.sessions) / "DESATIVAR_ENTRADA_FATURAS_SOMBRA.flag"
    decision_emergency_flag = Path(paths.sessions) / "DESATIVAR_DECISAO_FATURAS_SOMBRA.flag"
    force_legacy_flag = Path(paths.sessions) / "FORCAR_DECISAO_FATURAS_LEGADO.flag"
    contract_path = Path(paths.config) / "golden_batch_contract.json"
    bases_directory = Path(getattr(paths, "bases", Path(paths.reports).parent / "bases"))
    default_base_path = bases_directory

    shadow_engine = InvoiceShadowEngine()
    shadow_reporter = InvoiceAuditReport(report_dir)
    shadow_service = InvoiceShadowService(shadow_engine, shadow_reporter, contract_path=contract_path)
    input_engine = InvoiceInputAuditEngine()
    input_reporter = InvoiceInputAuditReport(input_report_dir)
    decision_engine = InvoiceDecisionAuditEngine(contract_path=contract_path)
    decision_reporter = InvoiceDecisionAuditReport(decision_report_dir)
    promotion_engine = InvoicePromotionEngine()
    promotion_reporter = InvoicePromotionReport(promotion_report_dir)

    for name, instance in (
        ("invoice_shadow", shadow_service),
        ("invoice_input_shadow", input_engine),
        ("invoice_decision_shadow", decision_engine),
        ("invoice_promotion", promotion_engine),
    ):
        try:
            services.register_instance(name, instance)
        except Exception:
            pass

    patched_classes: set[int] = set()
    patch_lock = threading.RLock()
    input_jobs_lock = threading.RLock()
    input_jobs: set[str] = set()
    input_completed: set[str] = set()

    def log(message: str, **extra: Any) -> None:
        try:
            logger.write("motor_faturas_sombra", message=str(message), **extra)
        except Exception:
            pass

    def _true(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "sim", "yes", "on"}

    def disabled() -> bool:
        return _true(os.environ.get("CENTRAL_CTE_DISABLE_INVOICE_SHADOW")) or emergency_flag.exists()

    def input_disabled() -> bool:
        return disabled() or _true(os.environ.get("CENTRAL_CTE_DISABLE_INVOICE_INPUT_SHADOW")) or input_emergency_flag.exists()

    def decision_disabled() -> bool:
        return input_disabled() or _true(os.environ.get("CENTRAL_CTE_DISABLE_INVOICE_DECISION_SHADOW")) or decision_emergency_flag.exists()

    def decision_mode() -> str:
        if force_legacy_flag.exists() or _true(os.environ.get("CENTRAL_CTE_FORCE_LEGACY_INVOICE_DECISION")):
            return "legacy"
        env = str(os.environ.get("CENTRAL_CTE_INVOICE_DECISION_MODE", "") or "").strip().lower()
        try:
            configured = str((settings.load() or {}).get("invoice_decision_mode") or "").strip().lower()
        except Exception:
            configured = ""
        raw = env or configured or "modular_guarded"
        aliases = {
            "modular": "modular_guarded",
            "guarded": "modular_guarded",
            "modular_guarded": "modular_guarded",
            "promocao_controlada": "modular_guarded",
            "shadow": "shadow",
            "sombra": "shadow",
            "legacy": "legacy",
            "legado": "legacy",
        }
        return aliases.get(raw, "modular_guarded")

    def run_audit(page: Any, *, consumer: str = "manual", input_state: dict[str, Any] | None = None) -> dict[str, Any]:
        if disabled():
            return {"version": BRIDGE_VERSION, "classification": "DESATIVADO", "consumer": consumer}
        result = shadow_service.audit(page, input_state=input_state, consumer=consumer)
        try:
            page._modular_invoice_shadow_last = result.to_dict(include_items=False)
        except Exception:
            pass
        return result.to_dict(include_items=False)

    def run_input_audit(page: Any, *, capture: dict[str, Any] | None = None, consumer: str = "manual") -> dict[str, Any]:
        if input_disabled():
            return {"version": BRIDGE_VERSION, "classification": "DESATIVADO", "consumer": consumer}
        captured = capture or input_engine.capture(page)
        result = input_engine.audit(page, captured, default_base=default_base_path)
        input_reporter.write(result, consumer=consumer)
        payload = result.to_dict(include_documents=False)
        try:
            page._modular_invoice_input_last = payload
        except Exception:
            pass
        return payload

    def run_decision_audit(page: Any, *, capture: dict[str, Any] | None = None, consumer: str = "manual") -> dict[str, Any]:
        if decision_disabled():
            return {"version": BRIDGE_VERSION, "classification": "DESATIVADO", "consumer": consumer}
        captured = capture or input_engine.capture(page)
        input_result = input_engine.audit(page, captured, default_base=default_base_path)
        input_reporter.write(input_result, consumer=consumer)
        legacy_records = [deepcopy(record) for record in list(getattr(page, "invoice_detail_records", []) or []) if isinstance(record, dict)]
        result = decision_engine.audit(input_result.snapshot, legacy_records)
        decision_reporter.write(result, consumer=consumer)
        payload = result.to_dict(include_decisions=False)
        try:
            page._modular_invoice_decision_last = payload
        except Exception:
            pass
        return payload

    def _refresh_page(page: Any) -> None:
        try:
            table = getattr(page, "invoice_table", None)
            add = getattr(page, "add_invoice_row", None)
            if table is not None:
                try:
                    table.setRowCount(0)
                except Exception:
                    pass
                if callable(add):
                    for row in list(getattr(page, "invoice_rows", []) or []):
                        try:
                            add(row)
                        except Exception:
                            pass
        except Exception:
            pass
        for name in ("update_cards", "load_details_for_selected"):
            try:
                callback = getattr(page, name, None)
                if callable(callback):
                    callback()
            except Exception:
                pass

    def run_promotion(
        page: Any,
        *,
        capture: dict[str, Any] | None = None,
        consumer: str = "manual",
        apply_result: bool = True,
    ) -> dict[str, Any]:
        if decision_disabled():
            return {"version": BRIDGE_VERSION, "classification": "DESATIVADO", "consumer": consumer}
        captured = capture or input_engine.capture(page)
        input_result = input_engine.audit(page, captured, default_base=default_base_path)
        input_reporter.write(input_result, consumer=consumer)
        legacy_records = [deepcopy(record) for record in list(getattr(page, "invoice_detail_records", []) or []) if isinstance(record, dict)]
        decision_result = decision_engine.audit(input_result.snapshot, legacy_records)
        decision_reporter.write(decision_result, consumer=consumer)
        mode = decision_mode()
        force_legacy = mode != "modular_guarded"
        reason = ""
        if mode == "legacy":
            reason = "Modo legado forçado por configuração, variável de ambiente ou arquivo de emergência."
        elif mode == "shadow":
            reason = "Modo sombra ativo; a auditoria é executada sem promover o resultado."
        promotion = promotion_engine.promote(
            page,
            input_result,
            decision_result,
            force_legacy=force_legacy,
            force_reason=reason,
        )
        promotion_reporter.write(promotion, consumer=consumer)
        if apply_result and mode == "modular_guarded":
            promotion_engine.apply(page, promotion)
            try:
                page._modular_invoice_promotion_result_2673 = promotion
            except Exception:
                pass
            _refresh_page(page)
        try:
            page._modular_invoice_input_last = input_result.to_dict(include_documents=False)
            page._modular_invoice_decision_last = decision_result.to_dict(include_decisions=False)
            page._modular_invoice_promotion_last = promotion.to_dict(include_records=False)
        except Exception:
            pass
        log(
            "Promoção controlada da decisão de faturas concluída",
            mode=mode,
            classification=promotion.classification,
            official_result=promotion.official_result,
            modular_invoices=promotion.modular_invoice_count,
            legacy_invoices=promotion.legacy_invoice_count,
            blocked_value=promotion.blocked_value,
        )
        return promotion.to_dict(include_records=False)

    def _job_key(capture: dict[str, Any], legacy_records: list[dict[str, Any]]) -> str:
        document_parts = []
        for document in capture.get("documents") or []:
            document_parts.append((
                document.get("fatura") or "",
                document.get("path") or document.get("arquivo") or "",
                len(str(document.get("texto") or "")),
                len(document.get("items") or []),
            ))
        legacy_parts = []
        for record in legacy_records:
            legacy_parts.append((
                record.get("Fatura") or "",
                record.get("CT-e fatura") or record.get("CT-e") or "",
                record.get("NF fatura") or record.get("NF") or "",
                record.get("Valor fatura") or record.get("Valor CT-e") or 0,
                record.get("Status final CT-e") or record.get("Status CT-e") or "",
            ))
        return stable_hash((sorted(document_parts, key=str), sorted(legacy_parts, key=str)))

    def submit_input_audit(page: Any, *, capture: dict[str, Any], consumer: str) -> dict[str, Any]:
        if input_disabled():
            return {"version": BRIDGE_VERSION, "classification": "DESATIVADO", "consumer": consumer}
        legacy_records = [deepcopy(record) for record in list(getattr(page, "invoice_detail_records", []) or []) if isinstance(record, dict)]
        job_key = _job_key(capture, legacy_records)
        with input_jobs_lock:
            if job_key in input_jobs:
                return {"version": BRIDGE_VERSION, "classification": "EM_EXECUCAO", "job_key": job_key}
            if job_key in input_completed:
                return {"version": BRIDGE_VERSION, "classification": "JA_AUDITADO", "job_key": job_key}
            input_jobs.add(job_key)

        proxy = SimpleNamespace(invoice_detail_records=legacy_records)

        def worker() -> None:
            try:
                input_result = input_engine.audit(proxy, capture, default_base=default_base_path)
                input_reporter.write(input_result, consumer=consumer)
                try:
                    page._modular_invoice_input_last = input_result.to_dict(include_documents=False)
                except Exception:
                    pass
                log(
                    "Auditoria modular da entrada de faturas concluída",
                    classification=input_result.classification,
                    documents=input_result.snapshot.document_count,
                    items=input_result.snapshot.item_count,
                    differences=len(input_result.differences),
                )
                if not decision_disabled():
                    decision_result = decision_engine.audit(input_result.snapshot, legacy_records)
                    decision_reporter.write(decision_result, consumer=consumer)
                    try:
                        page._modular_invoice_decision_last = decision_result.to_dict(include_decisions=False)
                    except Exception:
                        pass
                    # Em modo sombra/legado, grava também o parecer de promoção,
                    # mas nunca altera a tela nem os registros oficiais.
                    promotion = promotion_engine.promote(
                        proxy,
                        input_result,
                        decision_result,
                        force_legacy=True,
                        force_reason="Auditoria assíncrona sem promoção oficial.",
                    )
                    promotion_reporter.write(promotion, consumer=consumer)
                    log(
                        "Auditoria modular da decisão de faturas concluída",
                        classification=decision_result.classification,
                        invoices=decision_result.snapshot.invoice_count,
                        items=decision_result.snapshot.counted_item_count,
                        blocked_value=decision_result.snapshot.blocked_value,
                        differences=len(decision_result.differences),
                    )
            except Exception as exc:
                log("Falha na auditoria modular da entrada de faturas", error=f"{type(exc).__name__}: {exc}")
            finally:
                with input_jobs_lock:
                    input_jobs.discard(job_key)
                    input_completed.add(job_key)

        try:
            threading.Thread(target=worker, name="decisao-faturas-sombra-2673", daemon=True).start()
            return {"version": BRIDGE_VERSION, "classification": "AGENDADO", "job_key": job_key}
        except Exception:
            with input_jobs_lock:
                input_jobs.discard(job_key)
            return run_input_audit(proxy, capture=capture, consumer=consumer)

    def patch_class(cls: type) -> bool:
        with patch_lock:
            if id(cls) in patched_classes or getattr(cls, "_motor_faturas_promocao_2673", False):
                return True
            original_process = getattr(cls, "process_invoices", None)
            if not callable(original_process) or not getattr(cls, "_hotfix_faturas_2664", False):
                return False
            original_build = getattr(cls, "build_invoice_report_sheets", None)
            original_parse = getattr(cls, "parse_invoice_text", None)
            original_parse_ssw = getattr(cls, "parse_ssw_len_invoice_text", None)
            setattr(cls, "LEGACY_PROCESS_INVOICES_2673", original_process)
            if callable(original_build):
                setattr(cls, "LEGACY_BUILD_INVOICE_REPORT_2673", original_build)

            def process_invoices(self: Any, *args: Any, **kwargs: Any) -> Any:
                phase1_input = shadow_service.capture_input(self) if not disabled() else None
                phase2_capture = input_engine.capture(self) if not input_disabled() else None
                result = original_process(self, *args, **kwargs)
                if not disabled():
                    try:
                        run_audit(self, consumer="process_invoices", input_state=phase1_input)
                    except Exception as exc:
                        log("Falha na auditoria após process_invoices", error=str(exc))
                if phase2_capture is not None and not input_disabled():
                    try:
                        if decision_mode() == "modular_guarded" and not decision_disabled():
                            run_promotion(self, capture=phase2_capture, consumer="process_invoices", apply_result=True)
                        else:
                            submit_input_audit(self, capture=phase2_capture, consumer="process_invoices")
                    except Exception as exc:
                        log("Falha na promoção/auditoria da decisão de faturas", error=f"{type(exc).__name__}: {exc}")
                return result

            setattr(cls, "process_invoices", process_invoices)

            def _cache_full_pdf_text(self: Any, text: Any, path: Any) -> None:
                try:
                    cache = getattr(self, "_modular_invoice_full_text_2673", None)
                    if not isinstance(cache, dict):
                        cache = {}
                        setattr(self, "_modular_invoice_full_text_2673", cache)
                    key = str(path or "")
                    cache[key] = str(text or "")
                    try:
                        cache[Path(key).name] = str(text or "")
                    except Exception:
                        pass
                    # Compatibilidade com a captura criada na fase anterior.
                    setattr(self, "_modular_invoice_full_text_2672", cache)
                except Exception:
                    pass

            if callable(original_parse):
                def parse_invoice_text(self: Any, text: Any, path: Any, *args: Any, **kwargs: Any) -> Any:
                    _cache_full_pdf_text(self, text, path)
                    return original_parse(self, text, path, *args, **kwargs)
                setattr(cls, "parse_invoice_text", parse_invoice_text)

            if callable(original_parse_ssw) and original_parse_ssw is not original_parse:
                def parse_ssw_len_invoice_text(self: Any, text: Any, path: Any, *args: Any, **kwargs: Any) -> Any:
                    _cache_full_pdf_text(self, text, path)
                    return original_parse_ssw(self, text, path, *args, **kwargs)
                setattr(cls, "parse_ssw_len_invoice_text", parse_ssw_len_invoice_text)

            if callable(original_build):
                def build_invoice_report_sheets(self: Any, *args: Any, **kwargs: Any) -> Any:
                    promotion = getattr(self, "_modular_invoice_promotion_result_2673", None)
                    sheets = original_build(self, *args, **kwargs)
                    # O gerador legado reconstrói seus caches antes de montar a
                    # planilha. Reaplica atomicamente a decisão modular já
                    # homologada para que a interface continue coerente depois
                    # da exportação. Os valores da planilha permanecem idênticos
                    # porque só faturas sem divergência crítica são promovidas.
                    if promotion is not None and decision_mode() == "modular_guarded":
                        try:
                            promotion_engine.apply(self, promotion)
                            _refresh_page(self)
                        except Exception as exc:
                            log("Falha ao reaplicar promoção após relatório", error=str(exc))
                    return sheets
                setattr(cls, "build_invoice_report_sheets", build_invoice_report_sheets)

            setattr(cls, "auditar_motor_faturas_modular_2673", lambda self: run_audit(self, consumer="manual"))
            setattr(cls, "auditar_entrada_faturas_modular_2673", lambda self: run_input_audit(self, consumer="manual"))
            setattr(cls, "auditar_decisao_faturas_modular_2673", lambda self: run_decision_audit(self, consumer="manual"))
            setattr(cls, "promover_decisao_faturas_modular_2673", lambda self: run_promotion(self, consumer="manual", apply_result=True))
            # Aliases da fase anterior para scripts e atalhos existentes.
            setattr(cls, "auditar_motor_faturas_modular_2672", lambda self: run_audit(self, consumer="manual"))
            setattr(cls, "auditar_entrada_faturas_modular_2672", lambda self: run_input_audit(self, consumer="manual"))
            setattr(cls, "auditar_decisao_faturas_modular_2672", lambda self: run_decision_audit(self, consumer="manual"))
            setattr(cls, "_motor_faturas_sombra_2672", True)
            setattr(cls, "_motor_faturas_promocao_2673", True)
            patched_classes.add(id(cls))
            log("FaturasPage instrumentada", class_module=getattr(cls, "__module__", ""), phase=BRIDGE_VERSION, mode=decision_mode())
            return True

    def scan_and_patch() -> int:
        found: list[type] = []
        direct = module_globals.get("FaturasPage")
        if isinstance(direct, type):
            found.append(direct)
        for exact in (True, False):
            for module in list(sys.modules.values()):
                try:
                    cls = getattr(module, "FaturasPage", None)
                    if not isinstance(cls, type) or cls in found:
                        continue
                    defining = getattr(cls, "__module__", "") == getattr(module, "__name__", "")
                    if defining == exact:
                        found.append(cls)
                except Exception:
                    continue
        return sum(1 for cls in found if patch_class(cls))

    patched_now = scan_and_patch()

    module_globals.update({
        "MODULAR_INVOICE_SHADOW_ENGINE": shadow_engine,
        "MODULAR_INVOICE_SHADOW_REPORTER": shadow_reporter,
        "MODULAR_INVOICE_SHADOW_SERVICE": shadow_service,
        "MODULAR_INVOICE_INPUT_ENGINE": input_engine,
        "MODULAR_INVOICE_INPUT_REPORTER": input_reporter,
        "MODULAR_INVOICE_DECISION_ENGINE": decision_engine,
        "MODULAR_INVOICE_DECISION_REPORTER": decision_reporter,
        "MODULAR_INVOICE_PROMOTION_ENGINE": promotion_engine,
        "MODULAR_INVOICE_PROMOTION_REPORTER": promotion_reporter,
        "MODULAR_INVOICE_SHADOW_REPORT_DIR": report_dir,
        "MODULAR_INVOICE_INPUT_REPORT_DIR": input_report_dir,
        "MODULAR_INVOICE_DECISION_REPORT_DIR": decision_report_dir,
        "MODULAR_INVOICE_PROMOTION_REPORT_DIR": promotion_report_dir,
        "MODULAR_INVOICE_SHADOW_EMERGENCY_FLAG": emergency_flag,
        "MODULAR_INVOICE_INPUT_EMERGENCY_FLAG": input_emergency_flag,
        "MODULAR_INVOICE_DECISION_EMERGENCY_FLAG": decision_emergency_flag,
        "MODULAR_INVOICE_FORCE_LEGACY_FLAG": force_legacy_flag,
        "MODULAR_INVOICE_SHADOW_VERSION": BRIDGE_VERSION,
        "run_invoice_shadow_audit": run_audit,
        "run_invoice_input_shadow_audit": run_input_audit,
        "run_invoice_decision_shadow_audit": run_decision_audit,
        "run_invoice_decision_promotion": run_promotion,
        "get_invoice_decision_mode": decision_mode,
        "get_invoice_shadow_summary": shadow_service.snapshot,
        "rescan_invoice_shadow_bridge": scan_and_patch,
    })

    mode = decision_mode()
    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": mode,
        "phase": 4,
        "patched_classes": patched_now,
        "report_dir": str(report_dir),
        "input_report_dir": str(input_report_dir),
        "decision_report_dir": str(decision_report_dir),
        "promotion_report_dir": str(promotion_report_dir),
        "emergency_flag": str(emergency_flag),
        "input_emergency_flag": str(input_emergency_flag),
        "decision_emergency_flag": str(decision_emergency_flag),
        "force_legacy_flag": str(force_legacy_flag),
        "official_result": "modular_guarded_with_invoice_fallback" if mode == "modular_guarded" else "legacy",
        "activation": "event_driven_by_view_and_page_coordinator",
        "polling_thread": False,
    }
