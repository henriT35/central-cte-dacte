from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterator, MutableMapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

RUNTIME_VERSION = "2.7.0"

# Funções realmente consumidas pelo motor legado e pela interface. Objetos de
# infraestrutura, guards, reporters e cópias LEGACY_/MODULAR_ ficam no registro
# central, em vez de poluir o namespace global do motor.
_OPERATIONAL_EXPORTS = {
    # infraestrutura
    "resource_path", "app_runtime_dir", "safe_open_folder", "safe_open_file",
    "ensure_work_folders", "write_app_log", "only_digits", "extract_cnpjs",
    "format_cnpj_cpf", "format_cep", "money", "money_float", "qty", "date_br",
    "format_chave", "norm_text", "normalize_header", "normalize_nf",
    # parser
    "parse_xml", "parse_xml_modular", "compare_xml_parsers",
    "compare_xml_parsers_with_legacy", "compare_xml_parser_results",
    "audit_xml_paths", "audit_xml_folder", "get_parser_shadow_summary",
    "get_parser_audit_consolidated_summary", "rebuild_parser_audit_reports",
    "get_xml_parser_mode", "set_xml_parser_mode", "get_parser_promotion_summary",
    # renderização
    "render_dacte_page", "summary_page", "render_page", "render_document",
    "render_dacte_page_modular", "summary_page_modular",
    "get_dacte_renderer_mode", "set_dacte_renderer_mode",
    "get_dacte_renderer_summary",
    # repositórios
    "load_rodovitor_base", "load_rodovitor_base_cached",
    "load_rodovitor_base_modular", "load_rodovitor_base_modular_cached",
    "load_rodovitor_base_modular_sample", "invalidate_rodovitor_base_modular_cache",
    "audit_rodovitor_base_sample_now", "load_partner_tables",
    "load_partner_tables_modular", "get_repository_mode", "set_repository_mode",
    "get_base_repository_mode", "set_base_repository_mode", "get_repository_summary",
    # motor comercial
    "identify_partner", "detect_partner_charge_type", "extra_matches_charge_type",
    "choose_extra_rule", "calculate_extra_expected", "get_nfs_from_info",
    "get_nf_from_info", "is_generic_destination", "rule_matches_location",
    "choose_partner_rule", "special_weight_city_match", "choose_weight_special_rule",
    "normalize_base_calculo", "base_value_for_rule", "sum_base_for_rule",
    "component_value", "total_components_value", "non_frete_peso_components_value",
    "peso_base_kg_from_info", "should_use_frete_peso",
    "component_values_by_keywords", "comparison_value_from_xml",
    "get_commercial_mode", "set_commercial_mode", "get_commercial_summary",
    # validação e status
    "validate_cte_value", "validate_cte_value_modular_core",
    "validate_cte_value_modular", "get_validation_orchestrator_mode",
    "set_validation_orchestrator_mode", "get_validation_orchestrator_summary",
    "report_bucket", "classify_validation_status", "status_matches_filter",
    "get_status_decision_mode", "set_status_decision_mode",
    "rescan_status_ui_bridge",
    "get_status_decision_summary",
    # faturas, relatórios, UI e assinatura: APIs de diagnóstico/rollback
    "run_invoice_shadow_audit", "run_invoice_input_shadow_audit",
    "run_invoice_decision_shadow_audit", "run_invoice_decision_promotion",
    "get_invoice_decision_mode", "get_invoice_shadow_summary",
    "rescan_invoice_shadow_bridge", "get_invoice_report_mode",
    "rescan_reporting_bridge", "get_ui_controller_mode",
    "rescan_ui_controller_bridge", "get_signature_pdf_mode",
    "set_signature_pdf_mode", "get_signature_pdf_audit_summary",
    "validate_generated_pdf",
    # fábrica modular e fallbacks sob demanda
    "get_view_factory_summary", "resolve_view_class",
    "get_view_backend_mode", "set_view_backend_mode",
    "create_central_cte_application", "run_central_cte_application",
    "get_application_factory_summary", "get_legacy_fallback_summary",
    "load_legacy_fallback_component", "resolve_legacy_fallback_export",
}

# Estados mantidos por compatibilidade com testes e diagnóstico, sem republicar
# cada objeto interno criado pelas pontes.
_STATE_EXPORTS = {
    "MODULAR_INFRASTRUCTURE_STATE",
    "MODULAR_XML_PARSER_STATE",
    "MODULAR_RENDERING_STATE",
    "MODULAR_REPOSITORY_STATE",
    "MODULAR_COMMERCIAL_STATE",
    "MODULAR_VALIDATION_STATE",
    "MODULAR_CTE_HELPERS_STATE",
    "MODULAR_STATUS_STATE",
    "MODULAR_INVOICE_SHADOW_STATE",
    "MODULAR_REPORTING_STATE",
    "MODULAR_UI_STATE",
    "MODULAR_SIGNATURE_PDF_STATE",
    "MODULAR_LEGACY_INVENTORY_STATE",
    "MODULAR_BOOTSTRAP_STATE",
    "MODULAR_VIEW_FACTORY_STATE",
    "MODULAR_APPLICATION_FACTORY_STATE",
    "MODULAR_LAZY_FALLBACK_STATE",
}

_PUBLIC_EXACT = _OPERATIONAL_EXPORTS | _STATE_EXPORTS | {
    "APP_VERSION",
    "MODULAR_FOUNDATION_VERSION",
    "MODULAR_FOUNDATION_STATE",
    "MODULAR_SERVICES",
    "CENTRAL_CTE_RUNTIME",
    "get_modular_service",
    "get_modular_runtime",
    "get_modular_artifact",
    "get_modular_state",
    "adapt_legacy_cte_info",
    "__getattr__", "__dir__",
}


def is_public_export(name: str) -> bool:
    return str(name or "") in _PUBLIC_EXACT


@dataclass
class RuntimeRegistry:
    version: str
    installed_at: str
    engine_file: Path
    services: Any
    legacy_engine_path: Path
    states: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    public_exports: set[str] = field(default_factory=set)
    removed_startup_symbols: list[str] = field(default_factory=list)
    bridge_order: list[str] = field(default_factory=list)
    global_count_before: int = 0
    global_count_after: int = 0
    _lock: RLock = field(default_factory=RLock, repr=False)

    def resolve(self, name: str) -> Any:
        return self.services.resolve(name)

    def artifact(self, name: str, default: Any = None) -> Any:
        with self._lock:
            return self.artifacts.get(str(name), default)

    def state(self, name: str, default: Any = None) -> Any:
        with self._lock:
            return self.states.get(str(name), default)

    def register_state(self, name: str, value: Any) -> None:
        with self._lock:
            self.states[str(name)] = value
            if str(name) not in self.bridge_order:
                self.bridge_order.append(str(name))

    def summary(self) -> dict[str, Any]:
        with self._lock:
            active = 0
            inactive = 0
            for value in self.states.values():
                if isinstance(value, dict) and value.get("active") is False:
                    inactive += 1
                else:
                    active += 1
            return {
                "version": self.version,
                "installed_at": self.installed_at,
                "engine_file": str(self.engine_file),
                "legacy_engine_path": str(self.legacy_engine_path),
                "bridges": len(self.states),
                "bridges_active": active,
                "bridges_inactive": inactive,
                "hidden_artifacts": len(self.artifacts),
                "public_exports": len(self.public_exports),
                "removed_startup_symbols": len(self.removed_startup_symbols),
                "global_count_before": self.global_count_before,
                "global_count_after": self.global_count_after,
                "global_delta": self.global_count_after - self.global_count_before,
                "bridge_order": list(self.bridge_order),
            }

    def write_audit(self, report_dir: Path) -> None:
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        payload = self.summary()
        payload["states"] = {
            key: _json_safe(value) for key, value in sorted(self.states.items())
        }
        payload["public_export_names"] = sorted(self.public_exports)
        payload["hidden_artifact_names"] = sorted(self.artifacts)
        payload["removed_startup_symbol_names"] = list(self.removed_startup_symbols)

        json_path = report_dir / "ultima_auditoria_runtime.json"
        txt_path = report_dir / "ultima_auditoria_runtime.txt"
        csv_path = report_dir / "ultima_auditoria_runtime.csv"
        jsonl_path = report_dir / "runtime_modular.jsonl"

        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"Central CT-e Runtime Modular {self.version}",
            f"Instalado em: {self.installed_at}",
            f"Pontes registradas: {payload['bridges']}",
            f"Pontes ativas: {payload['bridges_active']}",
            f"Pontes inativas: {payload['bridges_inactive']}",
            f"Artefatos internos fora dos globais: {payload['hidden_artifacts']}",
            f"Exportações públicas controladas: {payload['public_exports']}",
            f"Entradas de hotfix removidas após a instalação: {payload['removed_startup_symbols']}",
            f"Globais antes: {payload['global_count_before']}",
            f"Globais depois: {payload['global_count_after']}",
            "",
            "Ordem das pontes:",
        ]
        lines.extend(f"- {name}" for name in self.bridge_order)
        if self.removed_startup_symbols:
            lines.extend(["", "Entradas de hotfix neutralizadas:"])
            lines.extend(f"- {name}" for name in self.removed_startup_symbols)
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["TIPO", "NOME", "STATUS", "VERSAO"])
            for name, state in sorted(self.states.items()):
                status = "ATIVO"
                version = ""
                if isinstance(state, dict):
                    status = "INATIVO" if state.get("active") is False else "ATIVO"
                    version = str(state.get("version") or "")
                writer.writerow(["PONTE", name, status, version])
            for name in sorted(self.artifacts):
                writer.writerow(["ARTEFATO_INTERNO", name, "REGISTRADO", ""])
            for name in sorted(self.public_exports):
                writer.writerow(["EXPORTACAO_PUBLICA", name, "PUBLICADA", ""])
            for name in self.removed_startup_symbols:
                writer.writerow(["HOTFIX_START", name, "REMOVIDO_APOS_INSTALACAO", ""])

        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


class EngineNamespace(MutableMapping[str, Any]):
    """Namespace filtrado usado pelas pontes durante a migração.

    Leituras enxergam o motor e os artefatos já registrados. Escritas de
    símbolos operacionais são publicadas no motor; objetos de implementação
    ficam somente no RuntimeRegistry.
    """

    def __init__(self, engine_globals: MutableMapping[str, Any], registry: RuntimeRegistry):
        self._engine = engine_globals
        self._registry = registry

    def __getitem__(self, key: str) -> Any:
        if key in self._engine:
            return self._engine[key]
        if key in self._registry.artifacts:
            return self._registry.artifacts[key]
        if key in self._registry.states:
            return self._registry.states[key]
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        name = str(key)
        if is_public_export(name):
            self._engine[name] = value
            self._registry.public_exports.add(name)
            return
        self._registry.artifacts[name] = value

    def __delitem__(self, key: str) -> None:
        if key in self._engine:
            del self._engine[key]
            return
        if key in self._registry.artifacts:
            del self._registry.artifacts[key]
            return
        if key in self._registry.states:
            del self._registry.states[key]
            return
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        seen = set()
        for key in self._engine:
            seen.add(key)
            yield key
        for source in (self._registry.artifacts, self._registry.states):
            for key in source:
                if key not in seen:
                    seen.add(key)
                    yield key

    def __len__(self) -> int:
        return len(set(self._engine) | set(self._registry.artifacts) | set(self._registry.states))

    @property
    def engine_globals(self) -> MutableMapping[str, Any]:
        return self._engine

    def publish(self, name: str, value: Any) -> None:
        self._engine[str(name)] = value
        self._registry.public_exports.add(str(name))

    def register_state(self, name: str, value: Any, *, publish: bool = True) -> None:
        self._registry.register_state(name, value)
        if publish:
            self.publish(name, value)


def cleanup_startup_symbols(engine_globals: MutableMapping[str, Any]) -> list[str]:
    """Remove somente funções de entrada já executadas.

    As funções ``*_apply`` permanecem porque threads legadas ainda podem usá-las.
    Isso impede reinstalação acidental sem interferir nas rotinas em andamento.
    """

    pattern = re.compile(r"^_central_cte_(?:hotfix|modular_foundation)_.+_start$")
    removed: list[str] = []
    for name in sorted(list(engine_globals)):
        if not pattern.match(name):
            continue
        value = engine_globals.get(name)
        if not callable(value):
            continue
        try:
            del engine_globals[name]
            removed.append(name)
        except Exception:
            continue
    return removed


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return repr(value)


__all__ = [
    "RUNTIME_VERSION",
    "RuntimeRegistry",
    "EngineNamespace",
    "cleanup_startup_symbols",
    "is_public_export",
]
