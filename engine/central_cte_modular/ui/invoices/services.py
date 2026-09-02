from __future__ import annotations

"""Serviços diretos da página de faturas.

Esta camada não conhece Tk, widgets ou o runtime histórico. Ela recebe dados
simples, chama os motores modulares e devolve read models prontos para a vista.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from ...invoices import (
    InvoiceBaseLinker,
    InvoiceDecisionEngine,
    InvoiceDocumentParser,
    InvoiceInputCatalog,
)
from ...invoices.pdf_reader import InvoicePdfTextReader
from ...reports import InvoiceExecutiveXlsxWriter, InvoiceReportBuilder

SERVICES_VERSION = "2.7.0-RC26.5-comprovante-simples"


@dataclass(frozen=True, slots=True)
class InvoiceProcessingResult:
    input_snapshot: Any
    decision_snapshot: Any
    documents: int
    items: int
    invoices: int
    total_value: float
    blocked_value: float
    payable_value: float
    base_info: dict[str, Any]


class InvoicePageServices:
    """Fachada sem estado sobre parser, vínculo, decisão e relatório."""

    version = SERVICES_VERSION

    def __init__(
        self,
        *,
        pdf_reader: InvoicePdfTextReader | None = None,
        document_parser: InvoiceDocumentParser | None = None,
        input_catalog: InvoiceInputCatalog | None = None,
        base_linker: InvoiceBaseLinker | None = None,
        decision_engine: InvoiceDecisionEngine | None = None,
        report_builder: InvoiceReportBuilder | None = None,
        xlsx_writer: InvoiceExecutiveXlsxWriter | None = None,
    ) -> None:
        self.pdf_reader = pdf_reader or InvoicePdfTextReader()
        self.document_parser = document_parser or InvoiceDocumentParser()
        self.input_catalog = input_catalog or InvoiceInputCatalog()
        self.base_linker = base_linker or InvoiceBaseLinker()
        self.decision_engine = decision_engine or InvoiceDecisionEngine()
        self.report_builder = report_builder or InvoiceReportBuilder()
        self.xlsx_writer = xlsx_writer or InvoiceExecutiveXlsxWriter()

    def read_pdf(
        self,
        path: str | Path,
        *,
        fallback: Callable[[Path], Any] | None = None,
    ) -> tuple[str, str]:
        return self.pdf_reader.read(Path(path), fallback=fallback)

    def parse_text(self, text: Any, path: Any = "") -> dict[str, Any]:
        parsed = self.document_parser.parse(
            {"texto": str(text or ""), "path": str(path or "")}
        )
        return parsed.to_dict()

    def process(
        self,
        documents: Iterable[Mapping[str, Any]],
        *,
        base_path: str | Path | None,
    ) -> InvoiceProcessingResult:
        input_snapshot = self.input_catalog.build(list(documents))
        items = [
            item
            for document in input_snapshot.documents
            for item in document.items
        ]
        links = self.base_linker.link(base_path, items) if items else ()
        linked_snapshot = replace(input_snapshot, links=tuple(links))
        decision_snapshot = self.decision_engine.decide(linked_snapshot)
        return InvoiceProcessingResult(
            input_snapshot=linked_snapshot,
            decision_snapshot=decision_snapshot,
            documents=int(getattr(linked_snapshot, "document_count", 0) or 0),
            items=int(getattr(decision_snapshot, "item_count", 0) or 0),
            invoices=int(getattr(decision_snapshot, "invoice_count", 0) or 0),
            total_value=float(getattr(decision_snapshot, "total_value", 0.0) or 0.0),
            blocked_value=float(getattr(decision_snapshot, "blocked_value", 0.0) or 0.0),
            payable_value=float(getattr(decision_snapshot, "payable_value", 0.0) or 0.0),
            base_info=dict(getattr(self.base_linker, "last_base_info", {}) or {}),
        )

    def build_report(self, page: Any, only_problem_invoices: bool = False) -> list[Any]:
        return self.report_builder.build(page, bool(only_problem_invoices)).sheets

    def write_report(self, path: str | Path, sheets: Sequence[Any]) -> Path:
        return self.xlsx_writer.write(Path(path), list(sheets))


__all__ = [
    "SERVICES_VERSION",
    "InvoiceProcessingResult",
    "InvoicePageServices",
]
