from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InvoiceInputItem:
    invoice_number: str
    invoice_key: str
    partner: str
    cte_number: str
    cte_key: str
    nf_number: str
    nf_key: str
    billed_value: float
    layout: str
    source_file: str
    source_document_hash: str
    sequence: int
    base_cte: str = ""
    weight: float = 0.0
    merchandise_value: float = 0.0
    commission_value: float = 0.0
    freight_origin_value: float = 0.0
    invoice_issue_date: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvoiceInputDocument:
    invoice_number: str
    invoice_key: str
    partner: str
    source_file: str
    document_hash: str
    text_hash: str
    parser_source: str
    layout: str
    items: tuple[InvoiceInputItem, ...] = ()
    invoice_issue_date: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["items"] = [item.to_dict() for item in self.items]
        data["warnings"] = list(self.warnings)
        return data


@dataclass(frozen=True)
class InvoiceBaseLink:
    invoice_number: str
    cte_number: str
    nf_number: str
    billed_value: float
    status: str
    mode: str
    confidence: str
    base_nf: str = ""
    base_cte: str = ""
    base_value: float = 0.0
    base_invoice: str = ""
    proof_status: str = ""
    document_type: str = ""
    candidate_count: int = 0
    cte_issue_date: str = ""
    scan_date: str = ""
    scan_time: str = ""
    message: str = ""
    base_freight_value: float = 0.0
    base_freight_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvoiceInputSnapshot:
    document_count: int
    unique_document_count: int
    duplicate_document_count: int
    invoice_count: int
    item_count: int
    empty_nf_count: int
    parser_error_count: int
    documents: tuple[InvoiceInputDocument, ...] = ()
    links: tuple[InvoiceBaseLink, ...] = ()
    input_fingerprint: str = ""
    elapsed_ms: float = 0.0
    warnings: tuple[str, ...] = ()

    def to_dict(self, *, include_documents: bool = True) -> dict[str, Any]:
        data = {
            "document_count": self.document_count,
            "unique_document_count": self.unique_document_count,
            "duplicate_document_count": self.duplicate_document_count,
            "invoice_count": self.invoice_count,
            "item_count": self.item_count,
            "empty_nf_count": self.empty_nf_count,
            "parser_error_count": self.parser_error_count,
            "links": [item.to_dict() for item in self.links],
            "input_fingerprint": self.input_fingerprint,
            "elapsed_ms": round(float(self.elapsed_ms or 0.0), 3),
            "warnings": list(self.warnings),
        }
        if include_documents:
            data["documents"] = [item.to_dict() for item in self.documents]
        return data


@dataclass(frozen=True)
class InvoiceInputDifference:
    severity: str
    scope: str
    key: str
    field: str
    modular: Any
    legacy: Any
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvoiceInputAuditResult:
    classification: str
    snapshot: InvoiceInputSnapshot
    differences: tuple[InvoiceInputDifference, ...] = ()
    error: str = ""

    def to_dict(self, *, include_documents: bool = True) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "snapshot": self.snapshot.to_dict(include_documents=include_documents),
            "differences": [item.to_dict() for item in self.differences],
            "error": self.error,
        }
