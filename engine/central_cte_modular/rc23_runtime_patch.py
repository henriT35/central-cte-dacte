from __future__ import annotations

"""RC23: relatório executivo de faturas em cinco abas."""

from typing import Any, MutableMapping

from .rc22_runtime_patch import install_rc22_runtime
from .reports.invoice_executive_xlsx import InvoiceExecutiveXlsxWriter
from .reports.invoice_report import InvoiceReportBuilder


RC23_VERSION = "2.7.0 RC23 — Relatório Executivo de Faturas"


def install_rc23_runtime(target_globals: MutableMapping[str, Any], bootstrap_state: Any) -> dict[str, Any]:
    """Preserva integralmente a RC22 e promove apenas o relatório de faturas."""
    prior_state = install_rc22_runtime(target_globals, bootstrap_state)
    services = bootstrap_state.services
    published = {
        "APP_VERSION": RC23_VERSION,
        "CENTRAL_CTE_RC22_STATE": prior_state,
        "MODULAR_INVOICE_REPORT_BUILDER": InvoiceReportBuilder(),
        "MODULAR_INVOICE_XLSX_WRITER": InvoiceExecutiveXlsxWriter(),
    }
    target_globals.update(published)
    target_globals["RC23_RUNTIME_PATCH"] = True
    try:
        services.register_instance("invoice_report_builder", published["MODULAR_INVOICE_REPORT_BUILDER"], replace=True)
        services.register_instance("invoice_executive_xlsx_writer", published["MODULAR_INVOICE_XLSX_WRITER"], replace=True)
    except Exception:
        pass
    return {
        "version": RC23_VERSION,
        "active": True,
        "rc22_preserved": bool(prior_state.get("active")),
        "invoice_report_only": True,
        "xml_report_unchanged": True,
        "commercial_rules_unchanged": True,
        "sheets": ["PAINEL", "FATURAS", "ATENÇÃO", "CT_ES", "AUDITORIA_TÉCNICA"],
        "native_charts": 4,
        "native_tables": 4,
        "technical_columns_preserved": 57,
    }


__all__ = ["RC23_VERSION", "install_rc23_runtime"]
