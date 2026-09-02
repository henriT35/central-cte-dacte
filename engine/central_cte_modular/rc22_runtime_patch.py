from __future__ import annotations

"""RC22: relatório executivo de validação dos XMLs em quatro abas."""

from typing import Any, MutableMapping

from .rc21_runtime_patch import install_rc21_runtime
from .reports.xml_validation_report import (
    REPORT_VERSION,
    XmlValidationReportGenerator,
)


RC22_VERSION = "2.7.0 RC22 — Relatório XML Executivo"


def install_rc22_runtime(target_globals: MutableMapping[str, Any], bootstrap_state: Any) -> dict[str, Any]:
    """Preserva integralmente a RC21 e substitui só a exportação XLSX dos XMLs."""

    prior_state = install_rc21_runtime(target_globals, bootstrap_state)
    namespace = bootstrap_state.compatibility_module
    services = bootstrap_state.services
    engine_namespace = services.resolve("engine_namespace")

    legacy_export_row = getattr(namespace, "validation_export_row", None)
    if not callable(legacy_export_row):
        legacy_export_row = engine_namespace.get("validation_export_row")
    if not callable(legacy_export_row):
        raise RuntimeError("validation_export_row histórico não está disponível para preservar a auditoria técnica")

    generator = XmlValidationReportGenerator(legacy_export_row=legacy_export_row)

    def write_validation_report_xlsx(file_path: Any, files: Any):
        generator.write(file_path, list(files or []))
        return None

    published = {
        "write_validation_report_xlsx": write_validation_report_xlsx,
        "MODULAR_XML_VALIDATION_REPORT_GENERATOR": generator,
        "MODULAR_XML_VALIDATION_REPORT_VERSION": REPORT_VERSION,
        "APP_VERSION": RC22_VERSION,
        "CENTRAL_CTE_RC21_STATE": prior_state,
    }
    for name, value in published.items():
        engine_namespace[name] = value
        try:
            setattr(namespace, name, value)
        except Exception:
            pass
    target_globals.update(published)
    target_globals["RC22_RUNTIME_PATCH"] = True

    try:
        services.register_instance("xml_validation_report_generator", generator, replace=True)
    except Exception:
        pass

    return {
        "version": RC22_VERSION,
        "report_version": REPORT_VERSION,
        "active": True,
        "rc21_preserved": bool(prior_state.get("active")),
        "xml_report_only": True,
        "invoice_report_unchanged": True,
        "sheets": ["PAINEL", "ATENÇÃO", "DETALHAMENTO", "AUDITORIA_TÉCNICA"],
        "native_charts": 4,
        "technical_columns_preserved": 60,
        "toll_audit_uses_applied_rule": True,
    }


__all__ = ["RC22_VERSION", "install_rc22_runtime"]
