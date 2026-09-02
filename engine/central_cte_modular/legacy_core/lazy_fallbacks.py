from __future__ import annotations

"""Registro de fallbacks históricos carregados somente quando necessários.

A interface e as pontes modulares precisam conhecer a assinatura das funções
históricas para manter rollback e modo sombra, mas não precisam instalar todos
os seus corpos durante a inicialização. Este módulo publica proxies leves e
carrega o componente correspondente na primeira chamada real.
"""

import csv
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, MutableMapping

LAZY_FALLBACK_VERSION = "2.7.0"


@dataclass(frozen=True, slots=True)
class LazyFallbackComponentSpec:
    name: str
    module_name: str
    installer_name: str
    state_name: str
    functions: tuple[str, ...]
    constants: tuple[str, ...] = ()
    eager: bool = False


_COMPONENTS: tuple[LazyFallbackComponentSpec, ...] = (
    LazyFallbackComponentSpec(
        "environment",
        "central_cte_modular.legacy_core.runtime_environment_compat",
        "install_runtime_environment_compat",
        "CENTRAL_CTE_RUNTIME_ENVIRONMENT_COMPAT_STATE",
        (),
        (),
        True,
    ),
    LazyFallbackComponentSpec(
        "support",
        "central_cte_modular.legacy_core.runtime_support_compat",
        "install_runtime_support_compat",
        "CENTRAL_CTE_RUNTIME_SUPPORT_COMPAT_STATE",
        (
            "resource_path", "app_runtime_dir", "safe_open_folder", "safe_open_file",
            "ensure_work_folders", "_central_cte_is_cte_info",
            "_central_cte_clean_complementary_information",
            "_central_cte_complementary_store_path", "_central_cte_info_identity",
            "_central_cte_load_complementary_store", "_central_cte_save_complementary_store",
            "get_complementary_print_information", "apply_complementary_print_information",
            "_central_cte_apply_complementary_information_html", "write_app_log",
            "photo_asset", "show_startup_error",
        ),
        (
            "CENTRAL_CTE_COMPLEMENTARY_INFO_KEY",
            "CENTRAL_CTE_COMPLEMENTARY_INFO_META_KEY",
            "CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS",
            "_CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE",
            "_CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME",
            "ASSET_B64",
        ),
        True,
    ),
    LazyFallbackComponentSpec(
        "xml_parser",
        "central_cte_modular.legacy_core.xml_parser_compat",
        "install_xml_parser_compat",
        "CENTRAL_CTE_XML_PARSER_COMPAT_STATE",
        (
            "local_name", "first", "all_of", "child", "text", "only_digits",
            "extract_cnpjs", "format_cnpj_cpf", "format_cep", "money", "money_float",
            "qty", "date_br", "format_chave", "map_tp_cte", "map_tp_serv",
            "map_tomador", "map_modal", "map_cst", "addr_lines", "pessoa_info",
            "pessoa_emit_info", "get_inf_id", "extract_nfe_number_from_key",
            "extract_cnpj_from_nfe_key", "extract_series_from_key", "find_medidas",
            "get_protocol", "get_seguro", "get_imposto", "_cte_obs_line",
            "get_obs_parts", "get_obs", "parse_cte", "parse_xml",
        ),
    ),
    LazyFallbackComponentSpec(
        "rendering_print",
        "central_cte_modular.legacy_core.rendering_print_compat",
        "install_rendering_print_compat",
        "CENTRAL_CTE_RENDERING_PRINT_COMPAT_STATE",
        (
            "code128c_svg", "cell", "fmt_field", "person_box", "tomador_box",
            "render_dacte_page", "summary_page", "render_page", "render_document",
            "print_file_windows", "open_html_for_print",
        ),
        ("CODE128_PATTERNS", "CSS"),
    ),
    LazyFallbackComponentSpec(
        "base_repository",
        "central_cte_modular.legacy_core.base_repository_compat",
        "install_base_repository_compat",
        "CENTRAL_CTE_BASE_REPOSITORY_COMPAT_STATE",
        (
            "norm_text", "normalize_header", "normalize_nf", "parse_number_br",
            "parse_percent", "parse_optional_single_money", "fmt_percent", "safe_get",
            "xlsx_col_to_index", "xlsx_load_shared_strings", "xlsx_sheet_paths",
            "read_xlsx_sheet", "try_read_xlsx_sheet", "resolve_xlsx_sheet_path",
            "append_rows_to_xlsx_sheet", "append_dicts_to_xlsx_sheet",
            "make_partner_id_from_name", "next_region_id", "normalize_percent_text",
            "cadastro_tabela_salvar_xlsx", "rows_to_dicts", "pick_col",
            "classify_base_cte", "xml_validation_partner_policy", "doc_identity_for_nf",
            "split_city_uf", "cnpj_match_score", "city_match_score", "base_cache_key",
            "base_cache_file", "load_rodovitor_base_cached", "load_rodovitor_base",
            "score_base_candidate", "_select_best_base_candidate", "find_base_by_nf",
            "load_partner_tables",
        ),
        ("XML_VALIDATION_PARTNER_POLICIES",),
    ),
    LazyFallbackComponentSpec(
        "commercial_validation",
        "central_cte_modular.legacy_core.commercial_validation_compat",
        "install_commercial_validation_compat",
        "CENTRAL_CTE_COMMERCIAL_VALIDATION_COMPAT_STATE",
        (
            "identify_partner", "detect_partner_charge_type", "extra_matches_charge_type",
            "choose_extra_rule", "calculate_extra_expected", "get_nfs_from_info",
            "get_nf_from_info", "is_generic_destination", "rule_matches_location",
            "choose_partner_rule", "candidate_summary", "special_weight_city_match",
            "choose_weight_special_rule", "normalize_base_calculo", "base_value_for_rule",
            "sum_base_for_rule", "component_value", "total_components_value",
            "non_frete_peso_components_value", "peso_base_kg_from_info",
            "peso_xml_debug_from_info", "format_peso_xml_debug", "should_use_frete_peso",
            "component_values_by_keywords", "comparison_value_from_xml",
            "format_component_list", "validation_report_text",
            "status_nf_fora_base_periodo", "diagnostico_nf_fora_base_periodo",
            "summarize_base_statuses", "base_rows_have_same_route", "validate_cte_value",
        ),
    ),
    LazyFallbackComponentSpec(
        "report_excel",
        "central_cte_modular.legacy_core.report_excel_compat",
        "install_report_excel_compat",
        "CENTRAL_CTE_REPORT_EXCEL_COMPAT_STATE",
        (
            "xml_escape", "excel_column_name", "safe_sheet_name", "xlsx_cell_xml",
            "xlsx_sheet_xml", "write_simple_xlsx", "audit_issue",
            "partner_name_for_audit", "audit_partner_tables", "build_partner_audit_sheets",
            "write_partner_audit_xlsx", "partner_audit_text", "base_audit_issue",
            "audit_rodovitor_base", "build_base_audit_sheets", "write_base_audit_xlsx",
            "base_audit_text", "validation_export_row", "report_bucket", "report_float",
            "add_group_totals", "build_group_rows", "build_validation_report_sheets",
            "weight_audit_row", "build_weight_audit_sheets", "write_weight_audit_xlsx",
            "write_validation_report_xlsx",
        ),
    ),
)


class LazyFallbackRegistry:
    def __init__(
        self,
        target_globals: MutableMapping[str, Any],
        components: tuple[LazyFallbackComponentSpec, ...] = _COMPONENTS,
    ) -> None:
        self.target_globals = target_globals
        self.components = {component.name: component for component in components}
        self.export_map: dict[str, str] = {}
        self.loaded: dict[str, dict[str, Any]] = {}
        self.loading: set[str] = set()
        self.load_events: list[dict[str, Any]] = []
        self.created_at = datetime.now().isoformat(timespec="seconds")
        self._lock = threading.RLock()
        self._composition_state: dict[str, Any] | None = None
        for component in components:
            for export in (*component.functions, *component.constants):
                current = self.export_map.get(export)
                if current and current != component.name:
                    raise ValueError(f"Exportação histórica duplicada: {export}: {current}/{component.name}")
                self.export_map[export] = component.name

    def install(self) -> dict[str, Any]:
        for component in self.components.values():
            if component.eager:
                self.ensure(component.name, trigger="startup_eager")
            else:
                self._register_deferred_component(component)
        state = self._build_composition_state()
        self._composition_state = state
        self.target_globals["CENTRAL_CTE_LEGACY_CORE_COMPOSITION_STATE"] = state
        self.target_globals["CENTRAL_CTE_LEGACY_LAZY_REGISTRY"] = self
        self.target_globals["get_legacy_fallback_summary"] = self.snapshot
        self.target_globals["load_legacy_fallback_component"] = self.ensure
        self.target_globals["resolve_legacy_fallback_export"] = self.resolve
        return state

    def _register_deferred_component(self, component: LazyFallbackComponentSpec) -> None:
        placeholder = {
            "version": LAZY_FALLBACK_VERSION,
            "module": component.module_name,
            "active": False,
            "deferred": True,
            "loaded": False,
            "component": component.name,
            "functions": list(component.functions),
            "constants": list(component.constants),
        }
        self.target_globals[component.state_name] = placeholder
        for function_name in component.functions:
            if function_name not in self.target_globals:
                self.target_globals[function_name] = self._build_proxy(component.name, function_name)

    def _build_proxy(self, component_name: str, function_name: str) -> Callable[..., Any]:
        def lazy_proxy(*args: Any, **kwargs: Any) -> Any:
            self.ensure(component_name, trigger=f"function:{function_name}")
            function = self.target_globals.get(function_name)
            if function is lazy_proxy or not callable(function):
                raise RuntimeError(
                    f"O componente legado {component_name!r} não publicou {function_name!r}."
                )
            return function(*args, **kwargs)

        lazy_proxy.__name__ = function_name
        lazy_proxy.__qualname__ = function_name
        lazy_proxy.__module__ = self.components[component_name].module_name
        lazy_proxy.__doc__ = (
            f"Proxy preguiçoso do fallback histórico {component_name}.{function_name}."
        )
        setattr(lazy_proxy, "_central_cte_lazy_fallback", True)
        setattr(lazy_proxy, "_central_cte_lazy_component", component_name)
        setattr(lazy_proxy, "_central_cte_lazy_export", function_name)
        return lazy_proxy

    def has_export(self, name: str) -> bool:
        return str(name or "") in self.export_map

    def resolve(self, name: str) -> Any:
        export = str(name or "")
        component_name = self.export_map.get(export)
        if not component_name:
            raise AttributeError(export)
        self.ensure(component_name, trigger=f"resolve:{export}")
        if export not in self.target_globals:
            raise AttributeError(export)
        return self.target_globals[export]

    def ensure(self, component_name: str, trigger: str = "manual") -> dict[str, Any]:
        name = str(component_name or "")
        component = self.components.get(name)
        if component is None:
            raise KeyError(f"Componente legado desconhecido: {name}")
        with self._lock:
            existing = self.loaded.get(name)
            if existing is not None:
                return existing
            if name in self.loading:
                raise RuntimeError(f"Carregamento recursivo detectado no componente {name!r}")
            self.loading.add(name)
        started = time.perf_counter()
        error = ""
        try:
            module = import_module(component.module_name)
            installer = getattr(module, component.installer_name)
            state = installer(self.target_globals)
            if not isinstance(state, dict):
                raise TypeError(f"Instalador {component.installer_name} não retornou estado válido")
            state = dict(state)
            state.update(
                {
                    "component": component.name,
                    "deferred": False,
                    "loaded": True,
                    "lazy_trigger": trigger,
                    "lazy_loaded_at": datetime.now().isoformat(timespec="seconds"),
                }
            )
            self.target_globals[component.state_name] = state
            with self._lock:
                self.loaded[name] = state
            return state
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            failed_state = {
                "version": LAZY_FALLBACK_VERSION,
                "module": component.module_name,
                "active": False,
                "deferred": True,
                "loaded": False,
                "component": component.name,
                "functions": list(component.functions),
                "constants": list(component.constants),
                "last_error": error,
                "lazy_trigger": trigger,
            }
            self.target_globals[component.state_name] = failed_state
            raise
        finally:
            elapsed = time.perf_counter() - started
            with self._lock:
                self.loading.discard(name)
                self.load_events.append(
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "component": name,
                        "trigger": trigger,
                        "seconds": round(elapsed, 6),
                        "success": not bool(error),
                        "error": error,
                    }
                )
                self._refresh_composition_state()

    def _build_composition_state(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "version": LAZY_FALLBACK_VERSION,
            "module": __name__,
            "active": True,
            "components": snapshot["components"],
            "component_count": snapshot["component_count"],
            "functions": snapshot["function_count"],
            "constants": snapshot["constant_count"],
            "functions_eager": snapshot["functions_eager"],
            "functions_deferred": snapshot["functions_deferred"],
            "loaded_components": snapshot["loaded_components"],
            "pending_components": snapshot["pending_components"],
            "facade_mode": "lazy_declarative_installer",
            "legacy_runtime_loaded": False,
            "legacy_runtime_shell_loaded": True,
            "legacy_fallbacks_on_demand": True,
            "legacy_runtime_reason": (
                "interface histórica carregada; corpos de fallback permanecem preguiçosos"
            ),
        }

    def _refresh_composition_state(self) -> None:
        if self._composition_state is None:
            return
        snapshot = self.snapshot()
        self._composition_state.update(
            {
                "components": snapshot["components"],
                "loaded_components": snapshot["loaded_components"],
                "pending_components": snapshot["pending_components"],
                "functions_eager": snapshot["functions_eager"],
                "functions_deferred": snapshot["functions_deferred"],
                "load_event_count": len(self.load_events),
                "legacy_runtime_loaded": not bool(snapshot["pending_components"]),
            }
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            loaded_names = set(self.loaded)
            events = list(self.load_events)
        components: list[dict[str, Any]] = []
        functions_eager = 0
        functions_deferred = 0
        constants_eager = 0
        constants_deferred = 0
        for component in self.components.values():
            loaded = component.name in loaded_names
            functions = len(component.functions)
            constants = len(component.constants)
            if loaded:
                functions_eager += functions
                constants_eager += constants
            else:
                functions_deferred += functions
                constants_deferred += constants
            components.append(
                {
                    "name": component.name,
                    "module": component.module_name,
                    "installer": component.installer_name,
                    "state_name": component.state_name,
                    "eager": component.eager,
                    "loaded": loaded,
                    "functions": functions,
                    "constants": constants,
                }
            )
        loaded_components = [item["name"] for item in components if item["loaded"]]
        pending_components = [item["name"] for item in components if not item["loaded"]]
        return {
            "version": LAZY_FALLBACK_VERSION,
            "created_at": self.created_at,
            "component_count": len(components),
            "function_count": sum(item["functions"] for item in components),
            "constant_count": sum(item["constants"] for item in components),
            "functions_eager": functions_eager,
            "functions_deferred": functions_deferred,
            "constants_eager": constants_eager,
            "constants_deferred": constants_deferred,
            "loaded_components": loaded_components,
            "pending_components": pending_components,
            "loaded_count": len(loaded_components),
            "pending_count": len(pending_components),
            "components": components,
            "load_events": events,
            "load_event_count": len(events),
        }

    def write_audit(self, report_dir: str | Path) -> dict[str, Any]:
        directory = Path(report_dir)
        directory.mkdir(parents=True, exist_ok=True)
        payload = self.snapshot()
        json_path = directory / "ultima_auditoria_fallbacks.json"
        txt_path = directory / "ultima_auditoria_fallbacks.txt"
        csv_path = directory / "ultima_auditoria_fallbacks.csv"
        jsonl_path = directory / "fallbacks_sob_demanda.jsonl"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        lines = [
            f"Central CT-e Fallbacks Sob Demanda {LAZY_FALLBACK_VERSION}",
            f"Criado em: {payload['created_at']}",
            f"Componentes: {payload['component_count']}",
            f"Carregados: {payload['loaded_count']}",
            f"Pendentes: {payload['pending_count']}",
            f"Funções carregadas: {payload['functions_eager']}",
            f"Funções adiadas: {payload['functions_deferred']}",
            "",
            "Componentes:",
        ]
        for item in payload["components"]:
            status = "CARREGADO" if item["loaded"] else "ADIADO"
            lines.append(
                f"- {item['name']}: {status}; funções={item['functions']}; constantes={item['constants']}"
            )
        if payload["load_events"]:
            lines.extend(["", "Eventos de carregamento:"])
            for event in payload["load_events"]:
                lines.append(
                    f"- {event['timestamp']} | {event['component']} | {event['trigger']} | "
                    f"{event['seconds']}s | {'OK' if event['success'] else event['error']}"
                )
        txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["COMPONENTE", "STATUS", "EAGER", "FUNCOES", "CONSTANTES", "MODULO"])
            for item in payload["components"]:
                writer.writerow(
                    [
                        item["name"],
                        "CARREGADO" if item["loaded"] else "ADIADO",
                        "SIM" if item["eager"] else "NAO",
                        item["functions"],
                        item["constants"],
                        item["module"],
                    ]
                )
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        return payload


def install_lazy_fallbacks(target_globals: MutableMapping[str, Any]) -> LazyFallbackRegistry:
    existing = target_globals.get("CENTRAL_CTE_LEGACY_LAZY_REGISTRY")
    if isinstance(existing, LazyFallbackRegistry):
        return existing
    registry = LazyFallbackRegistry(target_globals)
    registry.install()
    return registry


__all__ = [
    "LAZY_FALLBACK_VERSION",
    "LazyFallbackComponentSpec",
    "LazyFallbackRegistry",
    "install_lazy_fallbacks",
]
