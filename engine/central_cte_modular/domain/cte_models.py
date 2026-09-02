from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Party:
    name: str = ""
    tax_id: str = ""
    state_registration: str = ""
    city: str = ""
    state: str = ""
    address: str = ""
    postal_code: str = ""
    phone: str = ""


@dataclass(frozen=True)
class InvoiceReference:
    number: str = ""
    access_key: str = ""
    series: str = ""


@dataclass(frozen=True)
class CargoData:
    gross_weight_kg: Decimal = Decimal("0")
    calculation_weight_kg: Decimal = Decimal("0")
    volume_m3: Decimal = Decimal("0")
    goods_value: Decimal = Decimal("0")
    description: str = ""


@dataclass(frozen=True)
class CteDocument:
    number: str
    series: str = ""
    access_key: str = ""
    issuer: Party = field(default_factory=Party)
    sender: Party = field(default_factory=Party)
    recipient: Party = field(default_factory=Party)
    dispatcher: Party = field(default_factory=Party)
    receiver: Party = field(default_factory=Party)
    payer: Party = field(default_factory=Party)
    invoices: tuple[InvoiceReference, ...] = ()
    cargo: CargoData = field(default_factory=CargoData)
    service_value: Decimal = Decimal("0")
    source_path: Path | None = None
    raw_metadata: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
