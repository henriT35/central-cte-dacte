from __future__ import annotations

import os
from pathlib import Path
from typing import Any, MutableMapping

from ..commercial.commercial_engine import CommercialDependencies, ModularCommercialEngine
from ..commercial.guarded_commercial import (
    CommercialAuditReport,
    CommercialFunctionGuard,
    MODE_LEGACY_SHADOW,
    MODE_MODULAR_GUARDED,
    VALID_MODES,
)

BRIDGE_VERSION = "2.7.0-rc17"


def _info_context(info: Any) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {}
    emit = info.get("emit", {}) or {}
    return {
        "cte": str(info.get("numero") or ""),
        "serie": str(info.get("serie") or ""),
        "emitente": str(info.get("emitente") or emit.get("nome") or ""),
        "cnpj": str(emit.get("cnpjcpf") or emit.get("cnpj") or ""),
    }


def install_commercial_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    required_dependencies = {
        "norm_text": module_globals.get("norm_text"),
        "only_digits": module_globals.get("only_digits"),
        "parse_number_br": module_globals.get("parse_number_br"),
        "normalize_nf": module_globals.get("normalize_nf"),
        "partner_policy": module_globals.get("xml_validation_partner_policy"),
    }
    missing_dependencies = [name for name, value in required_dependencies.items() if not callable(value)]
    if missing_dependencies:
        return {
            "version": BRIDGE_VERSION,
            "active": False,
            "reason": f"dependências ausentes: {', '.join(missing_dependencies)}",
        }

    function_names = [
        "identify_partner",
        "detect_partner_charge_type",
        "extra_matches_charge_type",
        "choose_extra_rule",
        "calculate_extra_expected",
        "get_nfs_from_info",
        "get_nf_from_info",
        "is_generic_destination",
        "rule_matches_location",
        "choose_partner_rule",
        "special_weight_city_match",
        "choose_weight_special_rule",
        "normalize_base_calculo",
        "base_value_for_rule",
        "sum_base_for_rule",
        "component_value",
        "total_components_value",
        "non_frete_peso_components_value",
        "peso_base_kg_from_info",
        "should_use_frete_peso",
        "component_values_by_keywords",
        "comparison_value_from_xml",
    ]
    legacy_functions = {name: module_globals.get(name) for name in function_names}
    missing_functions = [name for name, value in legacy_functions.items() if not callable(value)]
    if missing_functions:
        return {
            "version": BRIDGE_VERSION,
            "active": False,
            "reason": f"funções comerciais legadas ausentes: {', '.join(missing_functions)}",
        }

    paths = services.resolve("paths")
    logger = services.resolve("logger")
    try:
        settings = services.resolve("settings")
    except Exception:
        settings = None
    memory_settings: dict[str, Any] = {}
    report_dir = Path(paths.reports) / "motor_comercial_sombra"
    report = CommercialAuditReport(report_dir)
    sessions_dir = Path(getattr(paths, "sessions", Path(paths.reports).parent / "sessoes"))
    emergency_flag = sessions_dir / "FORCAR_MOTOR_COMERCIAL_LEGADO.flag"

    def log(message: str) -> None:
        try:
            logger.write("motor_comercial", message=str(message))
        except Exception:
            pass

    def get_mode() -> str:
        environment_mode = str(os.environ.get("CENTRAL_CTE_COMMERCIAL_MODE", "") or "").strip().lower()
        if environment_mode in VALID_MODES:
            return environment_mode
        if emergency_flag.exists():
            return MODE_LEGACY_SHADOW
        try:
            source = settings.load() if settings is not None else memory_settings
            configured = str(source.get("commercial_mode", "") or "").strip().lower()
            if configured in VALID_MODES:
                return configured
        except Exception:
            pass
        return MODE_MODULAR_GUARDED

    def set_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_MODES)}")
        if settings is None:
            memory_settings["commercial_mode"] = normalized
        else:
            values = settings.load()
            values["commercial_mode"] = normalized
            settings.save(values)
        return normalized

    dependencies = CommercialDependencies(
        norm_text=required_dependencies["norm_text"],
        only_digits=required_dependencies["only_digits"],
        parse_number_br=required_dependencies["parse_number_br"],
        normalize_nf=required_dependencies["normalize_nf"],
        partner_policy=required_dependencies["partner_policy"],
    )
    engine = ModularCommercialEngine(dependencies)
    guard = CommercialFunctionGuard(report, get_mode)

    context_builders = {
        "identify_partner": lambda info, tables: _info_context(info),
        "detect_partner_charge_type": lambda info: _info_context(info),
        "extra_matches_charge_type": lambda extra, charge: {"tipo_extra": extra.get("tipo_extra", ""), "cobranca": charge},
        "choose_extra_rule": lambda partner_id, charge, tables, row=None: {"parceiro": partner_id, "cobranca": charge, "destino": f"{(row or {}).get('destino_cidade', '')}/{(row or {}).get('destino_uf', '')}"},
        "calculate_extra_expected": lambda base_freight, rule: {"base": base_freight, "regra": rule.get("tipo_extra", "")},
        "get_nfs_from_info": lambda info: _info_context(info),
        "get_nf_from_info": lambda info: _info_context(info),
        "is_generic_destination": lambda name: {"destino": str(name or "")},
        "rule_matches_location": lambda rule, row: {
            "parceiro": rule.get("partner_id", ""),
            "origem": f"{(row or {}).get('origem_cidade', '')}/{(row or {}).get('origem_uf', '')}",
            "destino": f"{(row or {}).get('destino_cidade', '')}/{(row or {}).get('destino_uf', '')}",
            "regiao": rule.get("regiao", ""),
        },
        "choose_partner_rule": lambda partner_id, row, tables: {
            "parceiro": partner_id,
            "origem": f"{(row or {}).get('origem_cidade', '')}/{(row or {}).get('origem_uf', '')}",
            "destino": f"{(row or {}).get('destino_cidade', '')}/{(row or {}).get('destino_uf', '')}",
        },
        "special_weight_city_match": lambda rule_city, destination_city: {"regra": rule_city, "destino": destination_city},
        "choose_weight_special_rule": lambda partner_id, row, tables, weight: {
            "parceiro": partner_id,
            "destino": f"{(row or {}).get('destino_cidade', '')}/{(row or {}).get('destino_uf', '')}",
            "peso_kg": weight,
        },
        "normalize_base_calculo": lambda value: {"base": str(value or "")},
        "base_value_for_rule": lambda row, calculation: {"nf": row.get("nf", ""), "base": calculation},
        "sum_base_for_rule": lambda rows, calculation: {"linhas": len(rows or []), "base": calculation},
        "component_value": lambda info, *parts: {**_info_context(info), "componentes": list(parts)},
        "total_components_value": lambda info: _info_context(info),
        "non_frete_peso_components_value": lambda info: _info_context(info),
        "peso_base_kg_from_info": lambda info: _info_context(info),
        "should_use_frete_peso": lambda rule, info: {**_info_context(info), "modo": rule.get("modo_calculo", ""), "ton": rule.get("ton_rate", 0)},
        "component_values_by_keywords": lambda info, keywords: {**_info_context(info), "palavras": list(keywords or [])},
        "comparison_value_from_xml": lambda info, mode="FRETE_VALOR": {**_info_context(info), "modo": mode},
    }

    for name in function_names:
        legacy = legacy_functions[name]
        modular = getattr(engine, name)
        module_globals[f"LEGACY_COMMERCIAL_{name.upper()}"] = legacy
        module_globals[f"MODULAR_COMMERCIAL_{name.upper()}"] = modular
        module_globals[name] = guard.wrap(name, legacy, modular, context_builders.get(name))

    module_globals["MODULAR_COMMERCIAL_ENGINE"] = engine
    module_globals["MODULAR_COMMERCIAL_GUARD"] = guard
    module_globals["MODULAR_COMMERCIAL_REPORTER"] = report
    module_globals["MODULAR_COMMERCIAL_REPORT_DIR"] = report_dir
    module_globals["MODULAR_COMMERCIAL_EMERGENCY_FLAG"] = emergency_flag
    module_globals["get_commercial_mode"] = get_mode
    module_globals["set_commercial_mode"] = set_mode
    module_globals["get_commercial_summary"] = report.snapshot
    module_globals["MODULAR_COMMERCIAL_VERSION"] = BRIDGE_VERSION

    try:
        services.register_instance("commercial_engine", engine, replace=True)
        services.register_instance("commercial_guard", guard, replace=True)
        services.register_instance("commercial_report", report, replace=True)
    except Exception as exc:
        log(f"Não foi possível registrar serviços comerciais: {exc}")

    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": get_mode(),
        "official_strategy": "modular_per_function_when_exact",
        "fallback": "legacy_per_function_on_difference_or_error",
        "validation_orchestrator": "legacy_unchanged",
        "functions_guarded": list(function_names),
        "function_count": len(function_names),
        "report_directory": str(report_dir),
        "session_id": report.session_id,
        "emergency_rollback_flag": str(emergency_flag),
        "latest_reports": [
            str(report_dir / "ultima_auditoria_comercial.json"),
            str(report_dir / "ultima_auditoria_comercial.txt"),
            str(report_dir / "ultima_auditoria_comercial.csv"),
            str(report.jsonl_path),
        ],
    }
