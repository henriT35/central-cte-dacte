from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InvoicePromotionResult:
    version: str
    mode: str
    classification: str
    official_result: str
    input_classification: str
    decision_classification: str
    invoice_count: int
    item_count: int
    modular_invoice_count: int
    legacy_invoice_count: int
    modular_item_count: int
    legacy_item_count: int
    total_value: float
    blocked_value: float
    payable_value: float
    modular_invoices: tuple[str, ...] = ()
    legacy_invoices: tuple[str, ...] = ()
    critical_invoices: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    elapsed_ms: float = 0.0
    records: tuple[dict[str, Any], ...] = field(default_factory=tuple, repr=False)
    invoice_rows: tuple[tuple[Any, ...], ...] = field(default_factory=tuple, repr=False)
    detail_rows_by_invoice: dict[str, tuple[tuple[Any, ...], ...]] = field(default_factory=dict, repr=False)
    stats: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self, *, include_records: bool = False) -> dict[str, Any]:
        data = {
            "version": self.version,
            "mode": self.mode,
            "classification": self.classification,
            "official_result": self.official_result,
            "input_classification": self.input_classification,
            "decision_classification": self.decision_classification,
            "invoice_count": self.invoice_count,
            "item_count": self.item_count,
            "modular_invoice_count": self.modular_invoice_count,
            "legacy_invoice_count": self.legacy_invoice_count,
            "modular_item_count": self.modular_item_count,
            "legacy_item_count": self.legacy_item_count,
            "total_value": self.total_value,
            "blocked_value": self.blocked_value,
            "payable_value": self.payable_value,
            "modular_invoices": list(self.modular_invoices),
            "legacy_invoices": list(self.legacy_invoices),
            "critical_invoices": list(self.critical_invoices),
            "reasons": list(self.reasons),
            "elapsed_ms": round(float(self.elapsed_ms or 0.0), 3),
            "stats": dict(self.stats),
        }
        if include_records:
            data["records"] = [dict(item) for item in self.records]
            data["invoice_rows"] = [list(item) for item in self.invoice_rows]
            data["detail_rows_by_invoice"] = {
                key: [list(row) for row in rows]
                for key, rows in self.detail_rows_by_invoice.items()
            }
        return data
