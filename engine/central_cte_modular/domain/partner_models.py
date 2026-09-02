from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Any


@dataclass(frozen=True)
class RouteMatch:
    partner_id: str
    origin_city: str = ""
    destination_city: str = ""
    receiver_city: str = ""
    route_code: str = ""
    confidence: Decimal = Decimal("0")
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PartnerRule:
    partner_id: str
    rule_id: str
    calculation_method: str
    rate: Decimal | None = None
    minimum_value: Decimal | None = None
    metadata: Mapping[str, Any] | None = None
