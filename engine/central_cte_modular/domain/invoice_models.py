from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class InvoiceItem:
    cte_number: str
    nf_number: str = ""
    value: Decimal = Decimal("0")
    document_type: str = "NORMAL"


@dataclass(frozen=True)
class InvoiceDocument:
    number: str
    partner_name: str
    items: tuple[InvoiceItem, ...] = ()
    source_path: Path | None = None
