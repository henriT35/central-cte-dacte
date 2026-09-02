from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, MutableMapping

from .compatibility import LegacyInfoAdapter
from .service_container import ServiceContainer
from .infrastructure_bridge import install_infrastructure_bridge
from .xml_parser_bridge import install_xml_parser_shadow
from .rendering_bridge import install_rendering_bridge
from .repository_bridge import install_repository_bridge
from .commercial_bridge import install_commercial_bridge
from .validation_bridge import install_validation_bridge
from .cte_helpers_bridge import install_cte_helpers_bridge
from .status_bridge import install_status_bridge
from .invoice_bridge import install_invoice_shadow_bridge
from .reporting_bridge import install_reporting_bridge
from .ui_bridge import install_ui_bridge
from .signature_pdf_bridge import install_signature_pdf_bridge
from .runtime_registry import (
    EngineNamespace,
    RUNTIME_VERSION,
    RuntimeRegistry,
    cleanup_startup_symbols,
)
from ..infrastructure.file_integrity import FileIntegrityService
from ..infrastructure.logging import ModularLogger
from ..infrastructure.paths import ApplicationPaths
from ..infrastructure.session_store import JsonSessionStore
from ..infrastructure.settings import JsonSettings
from ..infrastructure.runtime import RuntimeEnvironment

FOUNDATION_VERSION = RUNTIME_VERSION


@dataclass(frozen=True)
class FoundationState:
    version: str
    installed_at: str
    paths: ApplicationPaths
    services: ServiceContainer
    legacy_engine_path: Path


def build_container(engine_file: Path) -> ServiceContainer:
    paths = ApplicationPaths.from_engine_file(engine_file)
    container = ServiceContainer()
    container.register_instance("paths", paths)
    container.register_instance("legacy_info_adapter", LegacyInfoAdapter())
    container.register_factory("logger", lambda c: ModularLogger(c.resolve("paths").logs / "modular_foundation.jsonl"))
    container.register_factory("settings", lambda c: JsonSettings(c.resolve("paths").sessions / "modular_settings.json"))
    container.register_factory("session_store", lambda c: JsonSessionStore(c.resolve("paths").sessions / "modular_session.json"))
    container.register_instance("file_integrity", FileIntegrityService())
    container.register_instance("runtime", RuntimeEnvironment.from_engine_file(engine_file))
    return container


def install_runtime(module_globals: MutableMapping[str, Any], engine_file: Path) -> RuntimeRegistry:
    existing = module_globals.get("CENTRAL_CTE_RUNTIME")
    if isinstance(existing, RuntimeRegistry):
        return existing

    path = Path(engine_file).resolve()
    services = build_container(path)
    legacy_engine_path = path.parent / "legacy" / "central_cte_engine_2_6_65_20_2_frozen.py"
    installed_at = datetime.now().isoformat(timespec="seconds")
    registry = RuntimeRegistry(
        version=FOUNDATION_VERSION,
        installed_at=installed_at,
        engine_file=path,
        services=services,
        legacy_engine_path=legacy_engine_path,
        global_count_before=len(module_globals),
    )
    namespace = EngineNamespace(module_globals, registry)

    foundation = FoundationState(
        version=FOUNDATION_VERSION,
        installed_at=installed_at,
        paths=services.resolve("paths"),
        services=services,
        legacy_engine_path=legacy_engine_path,
    )

    # Um único registro público substitui a antiga coleção de objetos MODULAR_*
    # espalhados pelo motor. Os aliases de estado ficam por compatibilidade.
    namespace.publish("CENTRAL_CTE_RUNTIME", registry)
    namespace.publish("MODULAR_FOUNDATION_VERSION", FOUNDATION_VERSION)
    namespace.publish("MODULAR_FOUNDATION_STATE", foundation)
    namespace.publish("MODULAR_SERVICES", services)
    namespace.publish("get_modular_service", services.resolve)
    namespace.publish("get_modular_runtime", lambda: registry)
    namespace.publish("get_modular_artifact", registry.artifact)
    namespace.publish("get_modular_state", registry.state)
    namespace.publish("adapt_legacy_cte_info", services.resolve("legacy_info_adapter").to_document)

    _missing = object()
    previous_module_getattr = module_globals.get("__getattr__")

    def _module_getattr(name: str) -> Any:
        lazy_fallbacks = module_globals.get("CENTRAL_CTE_LEGACY_LAZY_REGISTRY")
        try:
            if lazy_fallbacks is not None and lazy_fallbacks.has_export(name):
                return lazy_fallbacks.resolve(name)
        except Exception:
            raise
        value = registry.artifact(name, _missing)
        if value is not _missing:
            return value
        value = registry.state(name, _missing)
        if value is not _missing:
            return value
        if callable(previous_module_getattr):
            return previous_module_getattr(name)
        raise AttributeError(f"módulo do Central CT-e não possui o atributo {name!r}")

    def _module_dir() -> list[str]:
        return sorted(set(module_globals) | set(registry.artifacts) | set(registry.states))

    namespace.publish("__getattr__", _module_getattr)
    namespace.publish("__dir__", _module_dir)

    try:
        services.register_instance("runtime_registry", registry)
        services.register_instance("engine_namespace", namespace)
    except Exception:
        pass

    installers = (
        ("MODULAR_INFRASTRUCTURE_STATE", lambda: install_infrastructure_bridge(namespace, path, services)),
        ("MODULAR_XML_PARSER_STATE", lambda: install_xml_parser_shadow(namespace, services)),
        ("MODULAR_RENDERING_STATE", lambda: install_rendering_bridge(namespace, services)),
        ("MODULAR_REPOSITORY_STATE", lambda: install_repository_bridge(namespace, services)),
        ("MODULAR_COMMERCIAL_STATE", lambda: install_commercial_bridge(namespace, services)),
        ("MODULAR_VALIDATION_STATE", lambda: install_validation_bridge(namespace, services)),
        ("MODULAR_CTE_HELPERS_STATE", lambda: install_cte_helpers_bridge(namespace, services)),
        ("MODULAR_STATUS_STATE", lambda: install_status_bridge(namespace, services)),
        ("MODULAR_INVOICE_SHADOW_STATE", lambda: install_invoice_shadow_bridge(namespace, services)),
        ("MODULAR_REPORTING_STATE", lambda: install_reporting_bridge(namespace, services)),
        ("MODULAR_UI_STATE", lambda: install_ui_bridge(namespace, services)),
        ("MODULAR_SIGNATURE_PDF_STATE", lambda: install_signature_pdf_bridge(namespace, services)),
    )

    logger = services.resolve("logger")
    for state_name, installer in installers:
        try:
            state = installer()
        except Exception as exc:
            state = {
                "version": FOUNDATION_VERSION,
                "active": False,
                "reason": f"falha de instalação: {exc}",
            }
            try:
                logger.write("runtime_bridge_error", bridge=state_name, error=str(exc))
            except Exception:
                pass
        namespace.register_state(state_name, state, publish=True)

    # O inventário estático 2.7.0 registra zero integrações ativas. Remover símbolos
    # *_start impede reinstalações acidentais e mantém o namespace enxuto; os
    # corpos históricos permanecem apenas nos fallbacks de auditoria.
    registry.removed_startup_symbols = cleanup_startup_symbols(module_globals)
    registry.global_count_after = len(module_globals)

    try:
        report_dir = foundation.paths.reports / "runtime_modular"
        registry.write_audit(report_dir)
    except Exception as exc:
        try:
            logger.write("runtime_audit_error", error=str(exc))
        except Exception:
            pass

    return registry


def install_foundation(module_globals: MutableMapping[str, Any], engine_file: Path) -> FoundationState:
    """Compatibilidade com as versões 2.6.66.x/2.6.67.x anteriores."""

    runtime = install_runtime(module_globals, engine_file)
    state = module_globals.get("MODULAR_FOUNDATION_STATE")
    if isinstance(state, FoundationState):
        return state
    return FoundationState(
        version=runtime.version,
        installed_at=runtime.installed_at,
        paths=runtime.services.resolve("paths"),
        services=runtime.services,
        legacy_engine_path=runtime.legacy_engine_path,
    )
