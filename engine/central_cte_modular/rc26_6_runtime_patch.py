from __future__ import annotations

"""RC26.6: preserva a RC26.5 e publica a correção comercial do repasse JSP."""

from typing import Any, MutableMapping

from .rc26_5_runtime_patch import install_rc26_5_runtime
from .reports.invoice_executive_xlsx import InvoiceExecutiveXlsxWriter
from .reports.invoice_report import InvoiceReportBuilder
from .reports.xml_validation_report import XmlValidationReportGenerator
from .reports.xml_validation_xlsx import XmlValidationXlsxWriter


RC26_6_VERSION = "2.7.0 RC26.6 — Diferença JSP sem gross-up presumido"


def install_rc26_6_runtime(
    target_globals: MutableMapping[str, Any],
    bootstrap_state: Any,
) -> dict[str, Any]:
    """Ativa a RC26.6 sobre a RC26.5 sem alterar parser, faturas ou PDF."""

    prior_state = install_rc26_5_runtime(target_globals, bootstrap_state)
    services = bootstrap_state.services
    namespace = bootstrap_state.compatibility_module
    engine_namespace = services.resolve("engine_namespace")

    published = {
        "APP_VERSION": RC26_6_VERSION,
        "CENTRAL_CTE_RC26_5_STATE": prior_state,
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

    target_globals["RC26_6_RUNTIME_PATCH"] = True
    return {
        "version": RC26_6_VERSION,
        "active": True,
        "rc26_5_preserved": bool(prior_state.get("active")),
        "commercial_correction": "JSP: gross-up de IMPOSTO/GRIS somente com percentual explícito na tabela",
        "cte_579882_expected": 147.45,
        "cte_579882_difference": 2.24,
        "parser_unchanged": True,
        "invoice_logic_unchanged": True,
        "signature_pdf_unchanged": True,
        "windows_excel_homologation": "pending_user_platform_validation",
    }


__all__ = ["RC26_6_VERSION", "install_rc26_6_runtime"]
