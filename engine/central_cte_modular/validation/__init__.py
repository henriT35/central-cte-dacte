"""Serviços modulares de validação de CT-e."""

from .cte_value_orchestrator import ORCHESTRATOR_VERSION, ModularCteValueOrchestrator, ValidationDependencies
from .guarded import (
    MODE_LEGACY, MODE_MODULAR_GUARDED, MODE_SHADOW, VALID_MODES,
    GuardedValidationOrchestrator, ValidationAuditReport,
)

__all__ = [
    "ORCHESTRATOR_VERSION", "ModularCteValueOrchestrator", "ValidationDependencies",
    "MODE_LEGACY", "MODE_MODULAR_GUARDED", "MODE_SHADOW", "VALID_MODES",
    "GuardedValidationOrchestrator", "ValidationAuditReport",
]
