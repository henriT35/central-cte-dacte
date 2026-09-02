from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InvoiceShadowItem:
    invoice_number: str
    invoice_key: str
    partner: str
    cte_number: str
    cte_key: str
    nf_number: str
    nf_key: str
    billed_value: float
    blocked_value: float
    status: str
    is_problem: bool
    proof_status: str = ""
    base_link: str = ""
    source_file: str = ""
    sequence: str = ""
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InvoiceShadowSummary:
    invoice_number: str
    invoice_key: str
    partner: str
    item_count: int
    ok_count: int
    problem_count: int
    total_value: float
    blocked_value: float
    payable_value: float
    status: str
    empty_nf_count: int = 0
    clone_count: int = 0
    item_fingerprints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["item_fingerprints"] = list(self.item_fingerprints)
        return data


@dataclass(frozen=True)
class InvoiceShadowSnapshot:
    source: str
    document_count: int
    invoice_count: int
    item_count: int
    clone_count: int
    empty_nf_count: int
    total_value: float
    blocked_value: float
    payable_value: float
    invoices: tuple[InvoiceShadowSummary, ...] = ()
    items: tuple[InvoiceShadowItem, ...] = ()
    document_invoice_numbers: tuple[str, ...] = ()
    input_fingerprint: str = ""
    warnings: tuple[str, ...] = ()

    def to_dict(self, *, include_items: bool = True) -> dict[str, Any]:
        data = {
            "source": self.source,
            "document_count": self.document_count,
            "invoice_count": self.invoice_count,
            "item_count": self.item_count,
            "clone_count": self.clone_count,
            "empty_nf_count": self.empty_nf_count,
            "total_value": self.total_value,
            "blocked_value": self.blocked_value,
            "payable_value": self.payable_value,
            "invoices": [invoice.to_dict() for invoice in self.invoices],
            "document_invoice_numbers": list(self.document_invoice_numbers),
            "input_fingerprint": self.input_fingerprint,
            "warnings": list(self.warnings),
        }
        if include_items:
            data["items"] = [item.to_dict() for item in self.items]
        return data


@dataclass(frozen=True)
class InvoiceShadowDifference:
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
class InvoiceShadowResult:
    classification: str
    modular: InvoiceShadowSnapshot
    legacy: InvoiceShadowSnapshot
    differences: tuple[InvoiceShadowDifference, ...] = ()
    golden_batch: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0
    error: str = ""

    def to_dict(self, *, include_items: bool = True) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "modular": self.modular.to_dict(include_items=include_items),
            "legacy": self.legacy.to_dict(include_items=include_items),
            "differences": [item.to_dict() for item in self.differences],
            "golden_batch": dict(self.golden_batch),
            "elapsed_ms": round(float(self.elapsed_ms or 0.0), 3),
            "error": self.error,
        }
