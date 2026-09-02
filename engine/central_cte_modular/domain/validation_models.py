from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .partner_models import PartnerRule, RouteMatch
from .statuses import StatusFamily


@dataclass(frozen=True)
class ValidationResult:
    status: str
    family: StatusFamily
    xml_value: Decimal = Decimal("0")
    expected_value: Decimal | None = None
    difference: Decimal | None = None
    selected_route: RouteMatch | None = None
    selected_rule: PartnerRule | None = None
    ignored_invoices: tuple[str, ...] = ()
    decision_log: tuple[str, ...] = ()
