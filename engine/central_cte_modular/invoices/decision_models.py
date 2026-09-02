from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InvoiceItemDecision:
    invoice_number: str
    invoice_key: str
    partner: str
    cte_number: str
    cte_key: str
    nf_number: str
    nf_key: str
    billed_value: float
    base_status: str
    link_mode: str
    link_confidence: str
    base_nf: str
    base_cte: str
    base_value: float
    base_invoice: str
    proof_status: str
    document_type: str
    is_complementary: bool
    is_courtesy: bool
    proof_required: bool
    proof_ok: bool
    value_status: str
    value_difference: float
    sla_status: str
    sla_days: int | None
    decision_code: str
    status: str
    blocked_value: float
    payable_value: float
    financial_counted: bool
    reason: str
    recommended_action: str
    decision_path: str
    ignored_nf_numbers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source_file: str = ""
    sequence: int = 0
    fingerprint: str = ""
    base_freight_value: float = 0.0
    base_freight_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ignored_nf_numbers"] = list(self.ignored_nf_numbers)
        data["warnings"] = list(self.warnings)
        return data


@dataclass(frozen=True)
class InvoiceDecisionSummary:
    invoice_number: str
    invoice_key: str
    partner: str
    item_count: int
    counted_item_count: int
    ok_count: int
    complementary_count: int
    missing_proof_count: int
    outside_base_count: int
    review_count: int
    ignored_nf_count: int
    total_value: float
    blocked_value: float
    payable_value: float
    status: str
    item_fingerprints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["item_fingerprints"] = list(self.item_fingerprints)
        return data


@dataclass(frozen=True)
class InvoiceDecisionSnapshot:
    invoice_count: int
    item_count: int
    counted_item_count: int
    ok_count: int
    complementary_count: int
    missing_proof_count: int
    outside_base_count: int
    review_count: int
    ignored_nf_count: int
    total_value: float
    blocked_value: float
    payable_value: float
    invoices: tuple[InvoiceDecisionSummary, ...] = ()
    decisions: tuple[InvoiceItemDecision, ...] = ()
    input_fingerprint: str = ""
    elapsed_ms: float = 0.0
    warnings: tuple[str, ...] = ()

    def to_dict(self, *, include_decisions: bool = True) -> dict[str, Any]:
        data = {
            "invoice_count": self.invoice_count,
            "item_count": self.item_count,
            "counted_item_count": self.counted_item_count,
            "ok_count": self.ok_count,
            "complementary_count": self.complementary_count,
            "missing_proof_count": self.missing_proof_count,
            "outside_base_count": self.outside_base_count,
            "review_count": self.review_count,
            "ignored_nf_count": self.ignored_nf_count,
            "total_value": self.total_value,
            "blocked_value": self.blocked_value,
            "payable_value": self.payable_value,
            "invoices": [item.to_dict() for item in self.invoices],
            "input_fingerprint": self.input_fingerprint,
            "elapsed_ms": round(float(self.elapsed_ms or 0.0), 3),
            "warnings": list(self.warnings),
        }
        if include_decisions:
            data["decisions"] = [item.to_dict() for item in self.decisions]
        return data


@dataclass(frozen=True)
class InvoiceDecisionDifference:
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
class InvoiceDecisionAuditResult:
    classification: str
    snapshot: InvoiceDecisionSnapshot
    differences: tuple[InvoiceDecisionDifference, ...] = ()
    legacy_totals: dict[str, Any] = field(default_factory=dict)
    golden_batch: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self, *, include_decisions: bool = True) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "snapshot": self.snapshot.to_dict(include_decisions=include_decisions),
            "differences": [item.to_dict() for item in self.differences],
            "legacy_totals": dict(self.legacy_totals),
            "golden_batch": dict(self.golden_batch),
            "error": self.error,
        }
