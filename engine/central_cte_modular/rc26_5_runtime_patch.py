from __future__ import annotations

"""RC26.5: segundo pente-fino visual e dos relatórios OpenXML."""

from typing import Any, MutableMapping

from .rc25_runtime_patch import install_rc25_runtime
from .reports.invoice_executive_xlsx import InvoiceExecutiveXlsxWriter
from .reports.invoice_report import InvoiceReportBuilder
from .reports.xml_validation_report import XmlValidationReportGenerator
from .reports.xml_validation_xlsx import XmlValidationXlsxWriter


RC26_5_VERSION = "2.7.0 RC26.5 — Pente-fino visual e relatórios compactos"


def install_rc26_5_runtime(
    target_globals: MutableMapping[str, Any],
    bootstrap_state: Any,
) -> dict[str, Any]:
    """Preserva o motor RC25/RC26.4 e substitui somente UI e relatórios."""

    prior_state = install_rc25_runtime(target_globals, bootstrap_state)
    services = bootstrap_state.services
    namespace = bootstrap_state.compatibility_module
    engine_namespace = services.resolve("engine_namespace")
    published = {
        "APP_VERSION": RC26_5_VERSION,
        "CENTRAL_CTE_RC25_STATE": prior_state,
        "MODULAR_INVOICE_REPORT_BUILDER": InvoiceReportBuilder(),
        "MODULAR_INVOICE_XLSX_WRITER": InvoiceExecutiveXlsxWriter(),
        "MODULAR_XML_REPORT_GENERATOR": XmlValidationReportGenerator(),
        "MODULAR_XML_XLSX_WRITER": XmlValidationXlsxWriter(),
    }
    for name, value in published.items():
        target_globals[name] = value
        engine_namespace[name] = value
        try:
            setattr(namespace, name, value)
        except Exception:
            pass
    target_globals["RC26_5_RUNTIME_PATCH"] = True
    for name, instance in (
        ("invoice_report_builder", published["MODULAR_INVOICE_REPORT_BUILDER"]),
        ("invoice_executive_xlsx_writer", published["MODULAR_INVOICE_XLSX_WRITER"]),
        ("xml_validation_report_generator", published["MODULAR_XML_REPORT_GENERATOR"]),
        ("xml_validation_xlsx_writer", published["MODULAR_XML_XLSX_WRITER"]),
    ):
        try:
            services.register_instance(name, instance, replace=True)
        except Exception:
            pass
    return {
        "version": RC26_5_VERSION,
        "active": True,
        "rc25_preserved": bool(prior_state.get("active")),
        "report_and_ui_layer_only": True,
        "commercial_rules_unchanged": True,
        "parser_unchanged": True,
        "invoice_sheets": ["PAINEL", "FATURAS", "ATENÇÃO", "CT_ES", "AUDITORIA_TÉCNICA"],
        "xml_sheets": ["PAINEL", "ATENÇÃO", "DETALHAMENTO", "AUDITORIA_TÉCNICA"],
        "invoice_native_charts": 5,
        "xml_native_charts": 5,
        "calculation_mode": "automatic",
    }


__all__ = ["RC26_5_VERSION", "install_rc26_5_runtime"]
