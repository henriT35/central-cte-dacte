from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, MutableMapping

from ..commercial.compact_control_service import (
    COMPACT_CONTROL_SERVICE_VERSION,
    CompactControlDependencies,
    CompactControlService,
)
from ..commercial.component_calculator import (
    COMPONENT_CALCULATOR_VERSION,
    ComponentCalculationDependencies,
    ComponentCalculationService,
)
from ..repositories.component_configuration import ComponentConfigurationService
from ..validation import (
    MODE_LEGACY,
    MODE_MODULAR_GUARDED,
    MODE_SHADOW,
    VALID_MODES,
    GuardedValidationOrchestrator,
    ModularCteValueOrchestrator,
    ValidationAuditReport,
    ValidationDependencies,
)

BRIDGE_VERSION = "2.7.0-rc17"


_COMMERCIAL_DEPENDENCIES = {
    "calculate_extra_expected": "MODULAR_COMMERCIAL_CALCULATE_EXTRA_EXPECTED",
    "choose_extra_rule": "MODULAR_COMMERCIAL_CHOOSE_EXTRA_RULE",
    "choose_partner_rule": "MODULAR_COMMERCIAL_CHOOSE_PARTNER_RULE",
    "choose_weight_special_rule": "MODULAR_COMMERCIAL_CHOOSE_WEIGHT_SPECIAL_RULE",
    "comparison_value_from_xml": "MODULAR_COMMERCIAL_COMPARISON_VALUE_FROM_XML",
    "component_value": "MODULAR_COMMERCIAL_COMPONENT_VALUE",
    "detect_partner_charge_type": "MODULAR_COMMERCIAL_DETECT_PARTNER_CHARGE_TYPE",
    "get_nfs_from_info": "MODULAR_COMMERCIAL_GET_NFS_FROM_INFO",
    "identify_partner": "MODULAR_COMMERCIAL_IDENTIFY_PARTNER",
    "non_frete_peso_components_value": "MODULAR_COMMERCIAL_NON_FRETE_PESO_COMPONENTS_VALUE",
    "normalize_base_calculo": "MODULAR_COMMERCIAL_NORMALIZE_BASE_CALCULO",
    "peso_base_kg_from_info": "MODULAR_COMMERCIAL_PESO_BASE_KG_FROM_INFO",
    "rule_matches_location": "MODULAR_COMMERCIAL_RULE_MATCHES_LOCATION",
    "should_use_frete_peso": "MODULAR_COMMERCIAL_SHOULD_USE_FRETE_PESO",
    "sum_base_for_rule": "MODULAR_COMMERCIAL_SUM_BASE_FOR_RULE",
}

_COMPATIBILITY_DEPENDENCIES = {
    "base_rows_have_same_route": "base_rows_have_same_route",
    "candidate_summary": "candidate_summary",
    "detect_partner_manual_extra": "detect_partner_manual_extra",
    "diagnostico_nf_fora_base_periodo": "diagnostico_nf_fora_base_periodo",
    "find_base_by_nf": "find_base_by_nf",
    "fmt_percent": "fmt_percent",
    "format_component_list": "format_component_list",
    "format_peso_xml_debug": "format_peso_xml_debug",
    "money": "money",
    "norm_text": "norm_text",
    "parse_number_br": "parse_number_br",
    "rule_pedagio_expected": "rule_pedagio_expected",
    "status_nf_fora_base_periodo": "status_nf_fora_base_periodo",
    "summarize_base_statuses": "summarize_base_statuses",
    "validate_rodotec_components_fallback": "validate_rodotec_components_fallback",
    "xml_validation_partner_policy": "xml_validation_partner_policy",
}


def install_validation_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    legacy_validate = module_globals.get("validate_cte_value")
    if not callable(legacy_validate):
        return {"version": BRIDGE_VERSION, "active": False, "reason": "validate_cte_value legado ausente"}

    dependencies: dict[str, Callable[..., Any]] = {}
    missing: list[str] = []
    for field_name, global_name in {**_COMMERCIAL_DEPENDENCIES, **_COMPATIBILITY_DEPENDENCIES}.items():
        value = module_globals.get(global_name)
        if callable(value):
            dependencies[field_name] = value
        else:
            missing.append(f"{field_name} ({global_name})")
    if missing:
        return {
            "version": BRIDGE_VERSION,
            "active": False,
            "reason": "dependências ausentes: " + ", ".join(missing),
        }

    paths = services.resolve("paths")
    logger = services.resolve("logger")
    try:
        settings = services.resolve("settings")
    except Exception:
        settings = None
    memory_settings: dict[str, Any] = {}
    report_dir = Path(paths.reports) / "orquestrador_validacao_modular"
    report = ValidationAuditReport(report_dir)
    sessions_dir = Path(getattr(paths, "sessions", Path(paths.reports).parent / "sessoes"))
    emergency_flag = sessions_dir / "FORCAR_ORQUESTRADOR_VALIDACAO_LEGADO.flag"

    def log(message: str) -> None:
        try:
            logger.write("orquestrador_validacao", message=str(message))
        except Exception:
            pass

    def load_settings() -> dict[str, Any]:
        try:
            return settings.load() if settings is not None else dict(memory_settings)
        except Exception:
            return dict(memory_settings)

    def save_setting(name: str, value: Any) -> None:
        if settings is None:
            memory_settings[name] = value
            return
        values = settings.load()
        values[name] = value
        settings.save(values)

    def get_mode() -> str:
        environment_mode = str(os.environ.get("CENTRAL_CTE_VALIDATION_ORCHESTRATOR_MODE", "") or "").strip().lower()
        aliases = {
            "modular": MODE_MODULAR_GUARDED,
            "modular_guarded": MODE_MODULAR_GUARDED,
            "shadow": MODE_SHADOW,
            "legacy_shadow": MODE_SHADOW,
            "legacy": MODE_LEGACY,
        }
        environment_mode = aliases.get(environment_mode, environment_mode)
        if environment_mode in VALID_MODES:
            return environment_mode
        if emergency_flag.exists():
            return MODE_LEGACY
        configured = str(load_settings().get("validation_orchestrator_mode", "") or "").strip().lower()
        configured = aliases.get(configured, configured)
        return configured if configured in VALID_MODES else MODE_MODULAR_GUARDED

    def set_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        aliases = {"modular": MODE_MODULAR_GUARDED, "legacy_shadow": MODE_SHADOW}
        normalized = aliases.get(normalized, normalized)
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_MODES)}")
        save_setting("validation_orchestrator_mode", normalized)
        return normalized

    dependency_object = ValidationDependencies(**{
        key: value for key, value in dependencies.items()
        if key in ValidationDependencies.__dataclass_fields__
    })
    orchestrator = ModularCteValueOrchestrator(dependency_object)
    try:
        component_configuration = services.resolve("component_configuration")
    except Exception:
        component_configuration = ComponentConfigurationService()
    component_dependencies = ComponentCalculationDependencies(
        norm_text=dependencies["norm_text"],
        parse_number_br=dependencies["parse_number_br"],
        get_nfs_from_info=dependencies["get_nfs_from_info"],
        find_base_by_nf=dependencies["find_base_by_nf"],
        identify_partner=dependencies["identify_partner"],
        base_rows_have_same_route=dependencies["base_rows_have_same_route"],
        choose_partner_rule=dependencies["choose_partner_rule"],
        should_use_frete_peso=dependencies["should_use_frete_peso"],
        peso_base_kg_from_info=dependencies["peso_base_kg_from_info"],
        format_peso_xml_debug=dependencies["format_peso_xml_debug"],
        money=dependencies["money"],
    )
    component_control = ComponentCalculationService(
        component_dependencies,
        component_configuration,
    )
    compact_dependencies = CompactControlDependencies(
        norm_text=dependencies["norm_text"],
        parse_number_br=dependencies["parse_number_br"],
        get_nfs_from_info=dependencies["get_nfs_from_info"],
        find_base_by_nf=dependencies["find_base_by_nf"],
        identify_partner=dependencies["identify_partner"],
        base_rows_have_same_route=dependencies["base_rows_have_same_route"],
        choose_partner_rule=dependencies["choose_partner_rule"],
        rule_matches_location=dependencies["rule_matches_location"],
        sum_base_for_rule=dependencies["sum_base_for_rule"],
        peso_base_kg_from_info=dependencies["peso_base_kg_from_info"],
        money=dependencies["money"],
    )
    compact_control = CompactControlService(
        compact_dependencies,
        component_configuration,
    )

    def modular_core(info: Any, base_data: Any, tables: Any) -> dict[str, Any]:
        return orchestrator.validate_contract(orchestrator.validate(info, base_data, tables))

    def apply_component_control(result: Any, info: Any, base_data: Any, tables: Any) -> dict[str, Any]:
        try:
            result = component_control.apply(result, info, base_data, tables)
        except Exception as exc:
            try:
                result.setdefault("trace", []).append(
                    f"Controle interno modular 2.6.69.6 não foi aplicado: {exc}"
                )
            except Exception:
                pass
        return orchestrator.validate_contract(result)

    def apply_validation_overlays(result: Any, info: Any, base_data: Any, tables: Any) -> dict[str, Any]:
        try:
            result = compact_control.apply(result, info, base_data, tables)
        except Exception as exc:
            try:
                result.setdefault("trace", []).append(
                    f"Controle compacto modular 2.6.69.6 não foi aplicado: {exc}"
                )
            except Exception:
                pass
        return apply_component_control(result, info, base_data, tables)

    def modular_with_overlays(info: Any, base_data: Any, tables: Any) -> dict[str, Any]:
        return apply_validation_overlays(modular_core(info, base_data, tables), info, base_data, tables)

    def legacy_with_modular_overlays(info: Any, base_data: Any, tables: Any) -> dict[str, Any]:
        return apply_validation_overlays(legacy_validate(info, base_data, tables), info, base_data, tables)

    guard = GuardedValidationOrchestrator(
        modular_core,
        legacy_with_modular_overlays,
        report,
        get_mode,
        postprocess=apply_validation_overlays,
        contract_validator=orchestrator.validate_contract,
    )

    module_globals["LEGACY_VALIDATION_ORCHESTRATOR"] = legacy_validate
    module_globals["MODULAR_CTE_VALUE_ORCHESTRATOR"] = orchestrator
    module_globals["MODULAR_COMPACT_CONTROL"] = compact_control
    module_globals["MODULAR_COMPONENT_CALCULATION"] = component_control
    module_globals["MODULAR_VALIDATION_GUARD"] = guard
    module_globals["MODULAR_VALIDATION_REPORTER"] = report
    module_globals["MODULAR_VALIDATION_REPORT_DIR"] = report_dir
    module_globals["MODULAR_VALIDATION_EMERGENCY_FLAG"] = emergency_flag
    module_globals["validate_cte_value_modular_core"] = modular_core
    module_globals["validate_cte_value_modular"] = modular_with_overlays
    module_globals["validate_cte_value"] = guard.validate
    module_globals["get_validation_orchestrator_mode"] = get_mode
    module_globals["set_validation_orchestrator_mode"] = set_mode
    module_globals["get_validation_orchestrator_summary"] = report.snapshot
    module_globals["MODULAR_VALIDATION_VERSION"] = BRIDGE_VERSION

    try:
        services.register_instance("cte_value_orchestrator", orchestrator, replace=True)
        services.register_instance("compact_control", compact_control, replace=True)
        services.register_instance("component_calculation", component_control, replace=True)
        services.register_instance("cte_validation_guard", guard, replace=True)
        services.register_instance("cte_validation_report", report, replace=True)
    except Exception as exc:
        log(f"Falha ao registrar serviços do orquestrador: {exc}")

    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": get_mode(),
        "official_orchestrator": "modular",
        "normal_flow_legacy_validation_calls": 0,
        "fallback": "legacy_only_on_modular_error_or_emergency_flag",
        "shadow_mode": "legacy_official_with_exact_comparison",
        "commercial_dependencies": "direct_modular_services",
        "base_matcher": "compatibility_adapter_pending_extraction",
        "compact_control": "direct_modular_service",
        "compact_control_version": COMPACT_CONTROL_SERVICE_VERSION,
        "component_control": "direct_modular_service",
        "component_control_version": COMPONENT_CALCULATOR_VERSION,
        "status_decoration": "installed_after_validation_bridge",
        "report_directory": str(report_dir),
        "session_id": report.session_id,
        "emergency_rollback_flag": str(emergency_flag),
        "latest_reports": [
            str(report_dir / "ultima_auditoria_orquestrador.json"),
            str(report_dir / "ultima_auditoria_orquestrador.txt"),
            str(report_dir / "ultima_auditoria_orquestrador.csv"),
            str(report.jsonl_path),
        ],
    }
