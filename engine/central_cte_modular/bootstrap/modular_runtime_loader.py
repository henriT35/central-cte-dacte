from __future__ import annotations

import csv
import hashlib
import json
import sys
import types
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, MutableMapping

from .application_factory import ModularApplicationFactory
from ..ui.views import ModularViewFactory
from .runtime_registry import RuntimeRegistry

BOOTSTRAP_VERSION = "2.7.0"
from central_cte_modular.version import APP_VERSION as APP_VERSION_LABEL
COMPAT_SOURCE_NAMES = (
    "central_cte_core_2_6_68_1.py",
    "central_cte_compat_audit_2_7_0.py",
)
COMPAT_SOURCE_NAME = COMPAT_SOURCE_NAMES[0]


@dataclass
class EngineBootstrapState:
    version: str
    installed_at: str
    engine_file: Path
    compatibility_source: Path
    compatibility_sources: tuple[Path, ...]
    compatibility_module: types.ModuleType
    runtime: RuntimeRegistry
    view_factory: ModularViewFactory
    application_factory: ModularApplicationFactory
    legacy_inventory: dict[str, Any]
    active_engine_lines: int
    compatibility_source_lines: int
    compatibility_part_lines: dict[str, int]
    compatibility_sha256: str
    eager_exports: tuple[str, ...]

    @property
    def services(self) -> Any:
        return self.runtime.services

    def summary(self) -> dict[str, Any]:
        namespace = vars(self.compatibility_module)
        inventory = dict(self.legacy_inventory)
        environment_state = namespace.get("CENTRAL_CTE_RUNTIME_ENVIRONMENT_COMPAT_STATE", {})
        composition_state = namespace.get("CENTRAL_CTE_LEGACY_CORE_COMPOSITION_STATE", {})
        support_extraction = namespace.get("CENTRAL_CTE_RUNTIME_SUPPORT_COMPAT_STATE", {})
        parser_extraction = namespace.get("CENTRAL_CTE_XML_PARSER_COMPAT_STATE", {})
        rendering_extraction = namespace.get("CENTRAL_CTE_RENDERING_PRINT_COMPAT_STATE", {})
        base_extraction = namespace.get("CENTRAL_CTE_BASE_REPOSITORY_COMPAT_STATE", {})
        report_extraction = namespace.get("CENTRAL_CTE_REPORT_EXCEL_COMPAT_STATE", {})
        commercial_validation_extraction = namespace.get("CENTRAL_CTE_COMMERCIAL_VALIDATION_COMPAT_STATE", {})
        lazy_registry = namespace.get("CENTRAL_CTE_LEGACY_LAZY_REGISTRY")
        try:
            lazy_summary = lazy_registry.snapshot() if lazy_registry is not None else {}
        except Exception:
            lazy_summary = {}
        try:
            view_summary = self.view_factory.summary()
        except Exception:
            view_summary = {}
        try:
            factory_summary = self.application_factory.summary()
        except Exception:
            factory_summary = {}
        return {
            "version": self.version,
            "installed_at": self.installed_at,
            "engine_file": str(self.engine_file),
            "compatibility_source": str(self.compatibility_source),
            "compatibility_sources": [str(p) for p in self.compatibility_sources],
            "compatibility_parts": len(self.compatibility_sources),
            "compatibility_part_lines": dict(self.compatibility_part_lines),
            "compatibility_module": self.compatibility_module.__name__,
            "active_engine_lines": self.active_engine_lines,
            "compatibility_source_lines": self.compatibility_source_lines,
            "compatibility_sha256": self.compatibility_sha256,
            "eager_exports": len(self.eager_exports),
            "legacy_namespace_symbols": len(namespace),
            "runtime_bridges": len(self.runtime.states),
            "runtime_bridges_active": self.runtime.summary().get("bridges_active", 0),
            "runtime_hidden_artifacts": len(self.runtime.artifacts),
            "runtime_public_exports": len(self.runtime.public_exports),
            "runtime_removed_startup_symbols": len(self.runtime.removed_startup_symbols),
            "legacy_inventory_entries": int(inventory.get("entries", 0) or 0),
            "legacy_inventory_active": int(inventory.get("active", 0) or 0),
            "legacy_inventory_dormant": int(inventory.get("dormant", 0) or 0),
            "legacy_inventory_mode": inventory.get("mode", ""),
            "legacy_patch_coordinator_present": False,
            "legacy_adapter_discovery_enabled": False,
            "legacy_worker_threads": 0,
            "legacy_core_facade_lines": self.compatibility_part_lines.get(self.compatibility_source.name, 0),
            "legacy_core_facade_mode": composition_state.get("facade_mode", "") if isinstance(composition_state, dict) else "",
            "legacy_core_facade_heavy_imports": environment_state.get("facade_heavy_imports", -1) if isinstance(environment_state, dict) else -1,
            "legacy_core_facade_constants": environment_state.get("facade_constants", -1) if isinstance(environment_state, dict) else -1,
            "legacy_core_environment_symbols": environment_state.get("symbol_count", 0) if isinstance(environment_state, dict) else 0,
            "legacy_core_tk_backend": environment_state.get("tk_backend", "") if isinstance(environment_state, dict) else "",
            "legacy_core_composition_components": composition_state.get("component_count", 0) if isinstance(composition_state, dict) else 0,
            "legacy_core_composition_functions": composition_state.get("functions", 0) if isinstance(composition_state, dict) else 0,
            "legacy_runtime_loaded": bool(composition_state.get("legacy_runtime_loaded", True)) if isinstance(composition_state, dict) else True,
            "legacy_runtime_reason": composition_state.get("legacy_runtime_reason", "") if isinstance(composition_state, dict) else "",
            "legacy_fallbacks_on_demand": bool(composition_state.get("legacy_fallbacks_on_demand", False)) if isinstance(composition_state, dict) else False,
            "legacy_fallback_components_loaded": lazy_summary.get("loaded_count", 0),
            "legacy_fallback_components_pending": lazy_summary.get("pending_count", 0),
            "legacy_fallback_functions_loaded": lazy_summary.get("functions_eager", 0),
            "legacy_fallback_functions_deferred": lazy_summary.get("functions_deferred", 0),
            "legacy_fallback_loaded_names": lazy_summary.get("loaded_components", []),
            "legacy_fallback_pending_names": lazy_summary.get("pending_components", []),
            "view_factory_mode": view_summary.get("mode", ""),
            "view_backend": view_summary.get("selected_backend", "deferred"),
            "view_loaded": bool(view_summary.get("loaded", False)),
            "modular_page_class_count": int(view_summary.get("page_class_count", 0) or 0),
            "modular_page_classes": list(view_summary.get("page_classes_loaded", []) or []),
            "modular_view_loaded": bool(view_summary.get("modular_loaded", False)),
            "legacy_view_loaded": bool(view_summary.get("legacy_loaded", False)),
            "legacy_ui_loaded_at_bootstrap": bool(view_summary.get("legacy_source_loaded_at_bootstrap", False)),
            "modular_view_source_lines": view_summary.get("modular_source_lines", 0),
            "legacy_view_source_lines": view_summary.get("legacy_source_lines", 0),
            "application_factory_mode": factory_summary.get("mode", ""),
            "application_factory_create_count": factory_summary.get("create_count", 0),
            "application_factory_run_count": factory_summary.get("run_count", 0),
            "legacy_core_support_functions_extracted": len(support_extraction.get("functions", ())) if isinstance(support_extraction, dict) else 0,
            "legacy_core_parser_functions_extracted": len(parser_extraction.get("functions", ())) if isinstance(parser_extraction, dict) else 0,
            "legacy_core_rendering_functions_extracted": len(rendering_extraction.get("functions", ())) if isinstance(rendering_extraction, dict) else 0,
            "legacy_core_base_functions_extracted": len(base_extraction.get("functions", ())) if isinstance(base_extraction, dict) else 0,
            "legacy_core_report_functions_extracted": len(report_extraction.get("functions", ())) if isinstance(report_extraction, dict) else 0,
            "legacy_core_commercial_validation_functions_extracted": len(commercial_validation_extraction.get("functions", ())) if isinstance(commercial_validation_extraction, dict) else 0,
        }

    def create_application(self) -> Any:
        return self.application_factory.create()

    def run_application(self) -> None:
        self.application_factory.run()


def _combined_sha256(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.as_posix().encode("utf-8")); digest.update(b"\0")
        digest.update(path.read_bytes()); digest.update(b"\0")
    return digest.hexdigest()


def _line_count(path: Path) -> int:
    try:
        return len(Path(path).read_text(encoding="utf-8-sig").splitlines())
    except Exception:
        return 0


def _compat_module_name(sources: tuple[Path, ...], logical_engine_file: Path) -> str:
    seed = "|".join(str(source.resolve()) for source in sources) + f"|{logical_engine_file.resolve()}"
    token = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    return f"central_cte_modular_runtime_2700_{token}"


def _compatibility_sources(logical_file: Path) -> tuple[Path, ...]:
    legacy_dir = logical_file.parent / "legacy"
    sources = tuple(legacy_dir / name for name in COMPAT_SOURCE_NAMES)
    missing = [str(source) for source in sources if not source.exists()]
    if missing:
        raise FileNotFoundError("Fontes mínimas de compatibilidade não encontradas: " + ", ".join(missing))
    return sources


def _load_legacy_inventory(logical_file: Path) -> dict[str, Any]:
    inventory_path = logical_file.parent.parent / "docs" / "LEGACY_PATCH_INVENTORY_2_7_0.json"
    try:
        payload = json.loads(inventory_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("inventário inválido")
        payload["path"] = str(inventory_path)
        return payload
    except Exception as exc:
        return {
            "version": BOOTSTRAP_VERSION,
            "mode": "static_audit_inventory_unavailable",
            "entries": 27, "active": 0, "dormant": 27,
            "runtime_imported": False, "coordinator_present": False,
            "worker_threads": 0, "error": f"{type(exc).__name__}: {exc}",
            "path": str(inventory_path),
        }


def load_compatibility_runtime(engine_file: Path) -> tuple[types.ModuleType, tuple[Path, ...]]:
    logical_file = Path(engine_file).resolve()
    sources = _compatibility_sources(logical_file)
    module_name = _compat_module_name(sources, logical_file)
    existing = sys.modules.get(module_name)
    if isinstance(existing, types.ModuleType):
        return existing, sources
    module = types.ModuleType(module_name)
    module.__dict__.update({
        "__file__": str(logical_file), "__package__": "", "__loader__": None, "__spec__": None,
        "__legacy_source_file__": str(sources[0]),
        "__legacy_source_files__": tuple(str(source) for source in sources),
        "__central_cte_compat__": True, "__central_cte_compat_split__": True,
    })
    sys.modules[module_name] = module
    try:
        for source in sources:
            code = compile(source.read_text(encoding="utf-8-sig"), str(source), "exec")
            exec(code, module.__dict__, module.__dict__)
        state = {
            "version": BOOTSTRAP_VERSION,
            "mode": "zero_runtime_patches",
            "applied": [], "errors": [], "complete": True,
            "runtime_residual_count": 0,
            "xml_import": "direct_modular_service",
            "cte_helpers": "direct_modular_service",
        }
        module.CENTRAL_CTE_RUNTIME_COMPAT_VERSION = BOOTSTRAP_VERSION
        module.CENTRAL_CTE_RUNTIME_COMPAT_STATE = dict(state)
        module.__dict__["__runtime_residual_state__"] = dict(state)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module, sources


def _write_bootstrap_audit(state: EngineBootstrapState) -> None:
    try:
        paths = state.services.resolve("paths")
        report_dir = Path(paths.reports) / "bootstrap_modular"
        report_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return
    payload = state.summary()
    payload["eager_export_names"] = list(state.eager_exports)
    payload["runtime_summary"] = state.runtime.summary()
    (report_dir / "ultima_auditoria_bootstrap.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"Central CT-e Bootstrap Modular {state.version}",
        f"Instalado em: {state.installed_at}",
        f"Motor ativo: {state.engine_file}",
        f"Linhas do motor ativo: {state.active_engine_lines}",
        f"Partes mínimas de compatibilidade: {len(state.compatibility_sources)}",
        f"Linhas isoladas: {state.compatibility_source_lines}",
        f"SHA-256 combinado: {state.compatibility_sha256}",
        f"Exportações carregadas diretamente: {len(state.eager_exports)}",
        f"Inventário histórico: {payload['legacy_inventory_entries']} entradas / {payload['legacy_inventory_active']} ativas / {payload['legacy_inventory_dormant']} dormentes",
        "Coordenador de patches: REMOVIDO",
        "Descoberta de páginas: REMOVIDA",
        "Workers de patches: 0",
        f"Vista modular carregada: {'SIM' if payload['modular_view_loaded'] else 'NÃO'}",
        f"Fallback visual carregado: {'SIM' if payload['legacy_view_loaded'] else 'NÃO'}",
        f"Fallbacks funcionais sob demanda: {'SIM' if payload['legacy_fallbacks_on_demand'] else 'NÃO'}",
        "",
        "O inventário histórico é um arquivo JSON estático e não participa do runtime.",
        "CTePage e FaturasPage são resolvidas diretamente pela fábrica modular.",
        "A fonte Tk histórica permanece apenas como fallback de recuperação até a homologação no Windows.",
    ]
    (report_dir / "ultima_auditoria_bootstrap.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")
    with (report_dir / "ultima_auditoria_bootstrap.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["METRICA", "VALOR"])
        for key, value in sorted(payload.items()):
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            writer.writerow([key, value])
    with (report_dir / "bootstrap_modular.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))+"\n")


def bootstrap_engine_facade(target_globals: MutableMapping[str, Any], engine_file: Path) -> EngineBootstrapState:
    existing = target_globals.get("CENTRAL_CTE_BOOTSTRAP")
    if isinstance(existing, EngineBootstrapState):
        return existing
    logical_file = Path(engine_file).resolve()
    compatibility_module, sources = load_compatibility_runtime(logical_file)
    from central_cte_modular import install_runtime
    runtime = install_runtime(vars(compatibility_module), logical_file)
    installed_at = datetime.now().isoformat(timespec="seconds")
    inventory = _load_legacy_inventory(logical_file)
    view_factory = ModularViewFactory(
        compatibility_module, runtime, logical_file, facade_globals=target_globals
    )
    application_factory = ModularApplicationFactory(
        compatibility_module, runtime, view_factory
    )
    eager_names = set(runtime.public_exports)
    eager_names.update({
        "APP_TITLE", "APP_VERSION", "APP_VERSION_BASE", "show_startup_error", "resource_path",
        "app_runtime_dir", "ensure_work_folders", "CENTRAL_CTE_RUNTIME",
        "MODULAR_FOUNDATION_VERSION", "MODULAR_FOUNDATION_STATE", "MODULAR_SERVICES",
    })
    copied=[]
    for name in sorted(eager_names):
        if name.startswith("__"): continue
        try:
            target_globals[name] = getattr(compatibility_module, name); copied.append(name)
        except Exception:
            continue
    part_lines = {source.name:_line_count(source) for source in sources}
    state = EngineBootstrapState(
        version=BOOTSTRAP_VERSION, installed_at=installed_at, engine_file=logical_file,
        compatibility_source=sources[0], compatibility_sources=sources,
        compatibility_module=compatibility_module, runtime=runtime,
        view_factory=view_factory, application_factory=application_factory,
        legacy_inventory=inventory, active_engine_lines=_line_count(logical_file),
        compatibility_source_lines=sum(part_lines.values()), compatibility_part_lines=part_lines,
        compatibility_sha256=_combined_sha256(sources), eager_exports=tuple(copied),
    )
    def _view_summary(): return view_factory.summary()
    def _resolve_view(name: str="App"): return view_factory.resolve(name)
    def _get_view_mode(): return view_factory.mode()
    def _set_view_mode(mode: str): return view_factory.set_mode(mode)
    def _factory_summary(): return application_factory.summary()
    def _create_application(): return application_factory.create()
    def _run_application(): application_factory.run()
    def _legacy_inventory_summary(): return dict(inventory)
    def _facade_getattr(name: str) -> Any:
        if name == "CENTRAL_CTE_BOOTSTRAP": return state
        if name in {"App", "ImageButton", "StatCard", "CTePage", "FaturasPage"}:
            value=view_factory.resolve(name); target_globals[name]=value; return value
        try: return getattr(compatibility_module, name)
        except AttributeError: pass
        value=runtime.artifact(name, _MISSING)
        if value is not _MISSING: return value
        value=runtime.state(name, _MISSING)
        if value is not _MISSING: return value
        raise AttributeError(f"módulo do Central CT-e não possui o atributo {name!r}")
    def _facade_dir():
        return sorted(set(target_globals)|set(dir(compatibility_module))|set(runtime.artifacts)|set(runtime.states))
    target_globals.update({
        "CENTRAL_CTE_BOOTSTRAP": state,
        "CENTRAL_CTE_RUNTIME": runtime,
        "CENTRAL_CTE_COMPAT_RUNTIME": compatibility_module,
        "CENTRAL_CTE_VIEW_FACTORY": view_factory,
        "CENTRAL_CTE_APPLICATION_FACTORY": application_factory,
        "get_view_factory_summary": _view_summary,
        "resolve_view_class": _resolve_view,
        "get_view_backend_mode": _get_view_mode,
        "set_view_backend_mode": _set_view_mode,
        "create_central_cte_application": _create_application,
        "run_central_cte_application": _run_application,
        "get_application_factory_summary": _factory_summary,
        "get_legacy_inventory_summary": _legacy_inventory_summary,
        "MODULAR_FOUNDATION_VERSION": BOOTSTRAP_VERSION,
        "APP_VERSION": APP_VERSION_LABEL,
        "__getattr__": _facade_getattr,
        "__dir__": _facade_dir,
    })
    foundation_state=target_globals.get("MODULAR_FOUNDATION_STATE")
    try: object.__setattr__(foundation_state, "version", BOOTSTRAP_VERSION)
    except Exception: pass
    try: compatibility_module.APP_VERSION=APP_VERSION_LABEL
    except Exception: pass
    lazy_registry=getattr(compatibility_module,"CENTRAL_CTE_LEGACY_LAZY_REGISTRY",None)
    if lazy_registry is not None:
        target_globals["get_legacy_fallback_summary"]=lazy_registry.snapshot
        target_globals["load_legacy_fallback_component"]=lazy_registry.ensure
        target_globals["resolve_legacy_fallback_export"]=lazy_registry.resolve
    public={
        "CENTRAL_CTE_BOOTSTRAP", "CENTRAL_CTE_RUNTIME", "CENTRAL_CTE_VIEW_FACTORY",
        "CENTRAL_CTE_APPLICATION_FACTORY", "MODULAR_FOUNDATION_VERSION", "MODULAR_FOUNDATION_STATE",
        "get_view_factory_summary", "resolve_view_class", "get_view_backend_mode", "set_view_backend_mode",
        "create_central_cte_application", "run_central_cte_application", "get_application_factory_summary",
        "get_legacy_inventory_summary", "get_legacy_fallback_summary", "load_legacy_fallback_component",
        "resolve_legacy_fallback_export", "App", "CTePage", "FaturasPage", "APP_TITLE", "APP_VERSION",
    }
    target_globals["__all__"]=sorted(set(copied)|public)
    try:
        runtime.artifacts["CENTRAL_CTE_BOOTSTRAP_STATE"]=state
        runtime.artifacts["CENTRAL_CTE_COMPAT_RUNTIME"]=compatibility_module
        runtime.artifacts["CENTRAL_CTE_VIEW_FACTORY"]=view_factory
        runtime.artifacts["CENTRAL_CTE_APPLICATION_FACTORY"]=application_factory
        runtime.artifacts["CENTRAL_CTE_LEGACY_INVENTORY"]=inventory
        if lazy_registry is not None: runtime.artifacts["CENTRAL_CTE_LEGACY_LAZY_REGISTRY"]=lazy_registry
        runtime.public_exports.update({
            "get_view_factory_summary", "resolve_view_class", "get_view_backend_mode", "set_view_backend_mode",
            "create_central_cte_application", "run_central_cte_application", "get_application_factory_summary",
            "get_legacy_inventory_summary", "get_legacy_fallback_summary", "load_legacy_fallback_component",
            "resolve_legacy_fallback_export",
        })
        runtime.states["MODULAR_LEGACY_INVENTORY_STATE"]={
            "version":BOOTSTRAP_VERSION, "active":True, "mode":"static_audit_only",
            "entries":inventory.get("entries",27), "active_entries":inventory.get("active",0),
            "dormant_entries":inventory.get("dormant",27), "coordinator_present":False,
            "page_discovery":False, "worker_threads":0,
        }
        runtime.states["MODULAR_BOOTSTRAP_STATE"]={
            "version":BOOTSTRAP_VERSION, "active":True, "mode":"modular_direct_no_patch_coordinator",
            "active_engine_lines":state.active_engine_lines, "compatibility_parts":len(sources),
            "compatibility_source_lines":state.compatibility_source_lines,
            "compatibility_sha256":state.compatibility_sha256,
            "legacy_patch_coordinator":False, "legacy_page_adapter_discovery":False,
            "legacy_worker_threads":0, "automatic_patch_start_calls":0,
            "legacy_runtime_loaded_for":"minimal support and on-demand emergency fallback",
            "legacy_fallbacks_on_demand":True, "application_factory":"modular_direct",
            "view_factory":"modular_guarded", "legacy_ui_loaded_at_bootstrap":False,
            "ui_activation":"event_driven",
        }
        runtime.states["MODULAR_VIEW_FACTORY_STATE"]=view_factory.summary()
        runtime.states["MODULAR_APPLICATION_FACTORY_STATE"]=application_factory.summary()
        runtime.states["MODULAR_LAZY_FALLBACK_STATE"]=lazy_registry.snapshot() if lazy_registry else {"active":False}
        for name in ("MODULAR_LEGACY_INVENTORY_STATE","MODULAR_BOOTSTRAP_STATE","MODULAR_VIEW_FACTORY_STATE","MODULAR_APPLICATION_FACTORY_STATE","MODULAR_LAZY_FALLBACK_STATE"):
            if name not in runtime.bridge_order: runtime.bridge_order.append(name)
    except Exception:
        pass
    try:
        paths=state.services.resolve("paths"); runtime.write_audit(Path(paths.reports)/"runtime_modular")
    except Exception: pass
    if lazy_registry is not None:
        try: lazy_registry.write_audit(Path(state.services.resolve("paths").reports)/"fallbacks_sob_demanda")
        except Exception: pass
    view_factory.write_audit(); application_factory.write_audit(); _write_bootstrap_audit(state)
    return state


_MISSING=object()

__all__=[
    "BOOTSTRAP_VERSION", "APP_VERSION_LABEL", "COMPAT_SOURCE_NAME", "COMPAT_SOURCE_NAMES",
    "EngineBootstrapState", "load_compatibility_runtime", "bootstrap_engine_facade",
]
