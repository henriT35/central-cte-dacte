"""Repositórios modulares para base Rodovitor e tabelas de parceiros."""

from .base_cache import RodovitorBaseCache
from .component_configuration import (
    COMPONENT_CONFIGURATION_VERSION,
    ComponentConfigurationService,
)
from .base_guard import GuardedRodovitorBaseLoader
from .rodovitor_base_repository import RodovitorBaseRepository
from .sswweb_reader import SswWebBaseReader
from .partner_table_repository import PartnerTableRepository
from .repository_audit import RepositoryAuditReport, PartnerTableGuard, BaseSampleAuditor

__all__ = [
    "COMPONENT_CONFIGURATION_VERSION",
    "ComponentConfigurationService",
    "RodovitorBaseRepository",
    "SswWebBaseReader",
    "RodovitorBaseCache",
    "GuardedRodovitorBaseLoader",
    "PartnerTableRepository",
    "RepositoryAuditReport",
    "PartnerTableGuard",
    "BaseSampleAuditor",
]
