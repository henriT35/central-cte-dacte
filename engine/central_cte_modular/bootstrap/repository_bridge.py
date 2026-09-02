from __future__ import annotations

import os
from pathlib import Path
from typing import Any, MutableMapping

from ..repositories.component_configuration import (
    COMPONENT_CONFIGURATION_VERSION,
    ComponentConfigurationService,
)
from ..repositories.base_cache import RodovitorBaseCache
from ..repositories.base_guard import (
    GuardedRodovitorBaseLoader,
    MODE_LEGACY as BASE_MODE_LEGACY,
    MODE_MODULAR_GUARDED as BASE_MODE_MODULAR_GUARDED,
    MODE_SHADOW as BASE_MODE_SHADOW,
    VALID_BASE_MODES,
)
from ..repositories.partner_table_repository import PartnerTableRepository
from ..repositories.repository_audit import (
    BaseSampleAuditor,
    MODE_LEGACY_SHADOW,
    MODE_MODULAR_GUARDED,
    PartnerTableGuard,
    RepositoryAuditReport,
    VALID_MODES,
)
from ..repositories.rodovitor_base_repository import RodovitorBaseRepository

BRIDGE_VERSION = "2.7.0 RC17 SSWWEB"
BASE_SAMPLE_SIZE = 500


def install_repository_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    legacy_base_cached = module_globals.get("LEGACY_LOAD_RODOVITOR_BASE_CACHED") or module_globals.get("load_rodovitor_base_cached")
    legacy_base_raw = module_globals.get("LEGACY_LOAD_RODOVITOR_BASE") or module_globals.get("load_rodovitor_base")
    legacy_partner_loader = module_globals.get("LEGACY_LOAD_PARTNER_TABLES") or module_globals.get("load_partner_tables")
    if not callable(legacy_base_cached) or not callable(legacy_base_raw) or not callable(legacy_partner_loader):
        return {"version": BRIDGE_VERSION, "active": False, "reason": "carregadores legados não encontrados"}

    paths = services.resolve("paths")
    logger = services.resolve("logger")
    try:
        settings = services.resolve("settings")
    except Exception:
        settings = None
    memory_settings: dict[str, Any] = {}
    report_dir = Path(paths.reports) / "repositorios_sombra"
    report = RepositoryAuditReport(report_dir)
    sessions_dir = Path(getattr(paths, "sessions", Path(paths.reports).parent / "sessoes"))
    cache_dir = Path(getattr(paths, "cache", Path(paths.reports).parent / "cache"))
    emergency_all_flag = sessions_dir / "FORCAR_REPOSITORIOS_LEGADOS.flag"
    emergency_base_flag = sessions_dir / "FORCAR_BASE_RODOVITOR_LEGADA.flag"

    def log(message: str) -> None:
        try:
            logger.write("repositorios", message=str(message))
        except Exception:
            pass

    def load_settings() -> dict[str, Any]:
        try:
            return settings.load() if settings is not None else dict(memory_settings)
        except Exception:
            return dict(memory_settings)

    def save_setting(name: str, value: Any) -> None:
        if settings is None:
            memory_settings[name] = value
            return
        values = settings.load()
        values[name] = value
        settings.save(values)

    def get_partner_mode() -> str:
        environment_mode = str(os.environ.get("CENTRAL_CTE_REPOSITORY_MODE", "") or "").strip().lower()
        if environment_mode in VALID_MODES:
            return environment_mode
        if emergency_all_flag.exists():
            return MODE_LEGACY_SHADOW
        configured = str(load_settings().get("repository_mode", "") or "").strip().lower()
        return configured if configured in VALID_MODES else MODE_MODULAR_GUARDED

    def set_partner_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_MODES)}")
        save_setting("repository_mode", normalized)
        return normalized

    def get_base_mode() -> str:
        environment_mode = str(os.environ.get("CENTRAL_CTE_BASE_REPOSITORY_MODE", "") or "").strip().lower()
        aliases = {
            "modular": BASE_MODE_MODULAR_GUARDED,
            "modular_guarded": BASE_MODE_MODULAR_GUARDED,
            "legacy": BASE_MODE_LEGACY,
            "legacy_shadow": BASE_MODE_LEGACY,
            "shadow": BASE_MODE_SHADOW,
        }
        if environment_mode in aliases:
            return aliases[environment_mode]
        if emergency_all_flag.exists() or emergency_base_flag.exists():
            return BASE_MODE_LEGACY
        configured = str(load_settings().get("base_repository_mode", "") or "").strip().lower()
        configured = aliases.get(configured, configured)
        return configured if configured in VALID_BASE_MODES else BASE_MODE_MODULAR_GUARDED

    def set_base_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        aliases = {
            "modular": BASE_MODE_MODULAR_GUARDED,
            "legacy_shadow": BASE_MODE_LEGACY,
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in VALID_BASE_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_BASE_MODES)}")
        save_setting("base_repository_mode", normalized)
        return normalized

    base_repository = RodovitorBaseRepository()
    base_cache = RodovitorBaseCache(base_repository, cache_dir)
    component_configuration = ComponentConfigurationService()
    partner_repository = PartnerTableRepository(component_configuration=component_configuration)

    def legacy_partner_loader_with_components(file_path: str | Path) -> dict[str, Any]:
        tables = legacy_partner_loader(file_path)
        tables = partner_repository.enrich_weight_bands(tables)
        return dict(component_configuration.enrich_tables(tables))

    partner_guard = PartnerTableGuard(
        legacy_partner_loader_with_components,
        partner_repository.load,
        report,
        get_partner_mode,
    )

    def load_partner_tables_guarded(file_path: str | Path) -> dict[str, Any]:
        tables = partner_guard.load(file_path)
        tables = partner_repository.enrich_weight_bands(tables)
        return dict(component_configuration.enrich_tables(tables))

    base_guard = GuardedRodovitorBaseLoader(base_cache, legacy_base_cached, report, get_base_mode)
    base_auditor = BaseSampleAuditor(base_repository, report, sample_size=BASE_SAMPLE_SIZE)

    def audit_base_sample_now(file_path: str | Path, data: Any | None = None) -> dict[str, Any]:
        base_data = data if isinstance(data, dict) else base_guard.load(file_path)
        return base_auditor.audit(file_path, base_data)

    def load_base_modular_cached(file_path: str | Path, force: bool = False) -> dict[str, Any]:
        return base_cache.load(file_path, force=force)

    def invalidate_base_cache(file_path: str | Path) -> bool:
        return base_cache.invalidate(file_path)

    module_globals["LEGACY_LOAD_RODOVITOR_BASE"] = legacy_base_raw
    module_globals["LEGACY_LOAD_RODOVITOR_BASE_CACHED"] = legacy_base_cached
    module_globals["LEGACY_LOAD_PARTNER_TABLES"] = legacy_partner_loader
    module_globals["MODULAR_RODOVITOR_BASE_REPOSITORY"] = base_repository
    module_globals["MODULAR_RODOVITOR_BASE_CACHE"] = base_cache
    module_globals["MODULAR_RODOVITOR_BASE_GUARD"] = base_guard
    module_globals["MODULAR_PARTNER_TABLE_REPOSITORY"] = partner_repository
    module_globals["MODULAR_COMPONENT_CONFIGURATION"] = component_configuration
    module_globals["MODULAR_PARTNER_TABLE_GUARD"] = partner_guard
    module_globals["MODULAR_BASE_SAMPLE_AUDITOR"] = base_auditor
    module_globals["MODULAR_REPOSITORY_REPORTER"] = report
    module_globals["MODULAR_REPOSITORY_REPORT_DIR"] = report_dir
    module_globals["MODULAR_REPOSITORY_EMERGENCY_FLAG"] = emergency_all_flag
    module_globals["MODULAR_BASE_REPOSITORY_EMERGENCY_FLAG"] = emergency_base_flag

    # Contrato oficial da base: exclusivamente modular SSW Web.
    # O carregador legado permanece registrado apenas para auditoria histórica,
    # mas não é mais chamado por nenhuma exportação pública.
    module_globals["load_rodovitor_base_modular"] = base_repository.load
    module_globals["load_rodovitor_base_modular_sample"] = base_repository.load_sample
    module_globals["load_rodovitor_base_modular_cached"] = load_base_modular_cached
    module_globals["load_rodovitor_base"] = base_repository.load
    module_globals["load_rodovitor_base_cached"] = load_base_modular_cached
    module_globals["invalidate_rodovitor_base_modular_cache"] = invalidate_base_cache
    module_globals["audit_rodovitor_base_sample_now"] = audit_base_sample_now

    module_globals["load_partner_tables_modular"] = partner_repository.load
    module_globals["load_partner_tables"] = load_partner_tables_guarded
    module_globals["get_repository_mode"] = get_partner_mode
    module_globals["set_repository_mode"] = set_partner_mode
    module_globals["get_base_repository_mode"] = get_base_mode
    module_globals["set_base_repository_mode"] = set_base_mode
    module_globals["get_repository_summary"] = report.snapshot
    module_globals["MODULAR_REPOSITORY_VERSION"] = BRIDGE_VERSION

    try:
        services.register_instance("rodovitor_base_repository", base_repository, replace=True)
        services.register_instance("rodovitor_base_cache", base_cache, replace=True)
        services.register_instance("rodovitor_base_guard", base_guard, replace=True)
        services.register_instance("partner_table_repository", partner_repository, replace=True)
        services.register_instance("component_configuration", component_configuration, replace=True)
        services.register_instance("base_sample_auditor", base_auditor, replace=True)
    except Exception as exc:
        log(f"Falha ao registrar serviços de repositório: {exc}")

    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "partner_mode": get_partner_mode(),
        "base_mode": get_base_mode(),
        "partner_tables_official": "modular_when_data_exact",
        "component_configuration": "direct_modular_service",
        "component_configuration_version": COMPONENT_CONFIGURATION_VERSION,
        "partner_tables_fallback": "legacy_on_difference_or_modular_error",
        "base_official": "modular",
        "base_fallback": "disabled_sswweb_only",
        "base_cache": "gzip_rows_only_multi_source_sha256_validated_v3",
        "base_streaming_xlsx": True,
        "base_streaming_sswweb": True,
        "base_sswweb_multi_file": True,
        "base_full_double_load": False,
        "base_index_rebuilt_from_same_row_objects": True,
        "write_operations": "legacy_unchanged",
        "report_directory": str(report_dir),
        "cache_directory": str(cache_dir),
        "session_id": report.session_id,
        "emergency_rollback_flag": str(emergency_all_flag),
        "base_emergency_rollback_flag": str(emergency_base_flag),
        "latest_reports": [
            str(report_dir / "ultima_auditoria_repositorios.json"),
            str(report_dir / "ultima_auditoria_repositorios.txt"),
            str(report_dir / "ultima_auditoria_repositorios.csv"),
            str(report.jsonl_path),
        ],
    }
