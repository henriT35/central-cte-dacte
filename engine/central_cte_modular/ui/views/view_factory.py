from __future__ import annotations

"""Fábrica preguiçosa das vistas do Central CT-e.

A interface Tk deixa de participar da composição inicial do runtime. A vista
modular é montada apenas quando a aplicação, ``App`` ou os widgets são
solicitados. A fonte Tk histórica permanece disponível como fallback explícito
ou automático, sem ser executada durante o bootstrap normal.
"""

import csv
import hashlib
import json
import os
import sys
import threading
import time
import types
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, MutableMapping

VIEW_FACTORY_VERSION = "2.7.0"
MODE_MODULAR_GUARDED = "modular_guarded"
MODE_LEGACY = "legacy"
VALID_MODES = {MODE_MODULAR_GUARDED, MODE_LEGACY}
CORE_VIEW_CLASS_NAMES = ("ImageButton", "StatCard", "App")
PAGE_VIEW_CLASS_NAMES = ("CTePage", "FaturasPage")
VIEW_CLASS_NAMES = CORE_VIEW_CLASS_NAMES + PAGE_VIEW_CLASS_NAMES
MODULAR_SOURCE_NAMES = (
    "tk_widgets_2700.py",
    "cte_page_2700.py",
    "faturas_page_2700.py",
    "tk_app_2700.py",
)
LEGACY_SOURCE_RELATIVE = Path("legacy") / "ui" / "central_cte_tk_app_2_6_68_1.py"


@dataclass
class ViewFactoryState:
    version: str = VIEW_FACTORY_VERSION
    installed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    mode: str = MODE_MODULAR_GUARDED
    selected_backend: str = "deferred"
    load_count: int = 0
    resolve_count: int = 0
    fallback_count: int = 0
    modular_loaded: bool = False
    legacy_loaded: bool = False
    loaded_at: str = ""
    load_seconds: float = 0.0
    last_error: str = ""
    app_methods: int = 0
    class_names: list[str] = field(default_factory=list)
    callbacks_executed: int = 0
    callback_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "installed_at": self.installed_at,
            "mode": self.mode,
            "selected_backend": self.selected_backend,
            "load_count": self.load_count,
            "resolve_count": self.resolve_count,
            "fallback_count": self.fallback_count,
            "modular_loaded": self.modular_loaded,
            "legacy_loaded": self.legacy_loaded,
            "loaded_at": self.loaded_at,
            "load_seconds": self.load_seconds,
            "last_error": self.last_error,
            "app_methods": self.app_methods,
            "class_names": list(self.class_names),
            "callbacks_executed": self.callbacks_executed,
            "callback_errors": list(self.callback_errors),
        }


class ModularViewFactory:
    def __init__(
        self,
        compatibility_module: types.ModuleType,
        runtime: Any,
        engine_file: Path,
        *,
        facade_globals: MutableMapping[str, Any] | None = None,
    ) -> None:
        self.compatibility_module = compatibility_module
        self.runtime = runtime
        self.engine_file = Path(engine_file).resolve()
        self.facade_globals = facade_globals
        self.state = ViewFactoryState()
        self._lock = threading.RLock()
        self._view_module: types.ModuleType | None = None
        self._classes: dict[str, type] = {}
        self._module_dir = Path(__file__).resolve().parent
        self._modular_sources = tuple(self._module_dir / name for name in MODULAR_SOURCE_NAMES)
        self._legacy_source = self.engine_file.parent / LEGACY_SOURCE_RELATIVE
        self._settings = self._resolve_service("settings")
        self._paths = self._resolve_service("paths")
        self._force_legacy_flag = self._resolve_force_legacy_flag()
        self.report_dir = self._resolve_report_dir()
        self.write_audit()

    def _resolve_service(self, name: str) -> Any | None:
        try:
            return self.runtime.services.resolve(name)
        except Exception:
            return None

    def _resolve_force_legacy_flag(self) -> Path:
        try:
            sessions = Path(self._paths.sessions)
        except Exception:
            sessions = self.engine_file.parent / "sessoes"
        return sessions / "FORCAR_INTERFACE_TK_LEGADA.flag"

    def _resolve_report_dir(self) -> Path | None:
        try:
            return Path(self._paths.reports) / "fabrica_vistas_modulares"
        except Exception:
            return None

    @staticmethod
    def _true(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "sim", "yes", "on"}

    def mode(self) -> str:
        if self._force_legacy_flag.exists() or self._true(
            os.environ.get("CENTRAL_CTE_FORCE_LEGACY_VIEW")
        ):
            self.state.mode = MODE_LEGACY
            return MODE_LEGACY
        env = str(os.environ.get("CENTRAL_CTE_VIEW_MODE", "") or "").strip().lower()
        configured = ""
        try:
            configured = str(
                (self._settings.load() or {}).get("view_backend_mode") or ""
            ).strip().lower()
        except Exception:
            pass
        aliases = {
            "modular": MODE_MODULAR_GUARDED,
            "guarded": MODE_MODULAR_GUARDED,
            "modular_guarded": MODE_MODULAR_GUARDED,
            "controlado": MODE_MODULAR_GUARDED,
            "legacy": MODE_LEGACY,
            "legado": MODE_LEGACY,
        }
        self.state.mode = aliases.get(env or configured, MODE_MODULAR_GUARDED)
        return self.state.mode

    def set_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        aliases = {
            "modular": MODE_MODULAR_GUARDED,
            "guarded": MODE_MODULAR_GUARDED,
            "modular_guarded": MODE_MODULAR_GUARDED,
            "controlado": MODE_MODULAR_GUARDED,
            "legacy": MODE_LEGACY,
            "legado": MODE_LEGACY,
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo de vista inválido: {mode!r}")
        if self._settings is not None:
            values = self._settings.load() or {}
            values["view_backend_mode"] = normalized
            self._settings.save(values)
        self.state.mode = normalized
        self.write_audit()
        return normalized

    def resolve(self, class_name: str = "App") -> type:
        requested = str(class_name or "App")
        if requested not in VIEW_CLASS_NAMES:
            raise AttributeError(f"Classe de vista desconhecida: {requested}")
        with self._lock:
            self.state.resolve_count += 1
            cached = self._classes.get(requested)
            if isinstance(cached, type):
                return cached
            if self.mode() == MODE_LEGACY:
                self._load_legacy(reason="modo_legado")
            else:
                try:
                    self._load_modular()
                except Exception as exc:
                    self.state.last_error = f"{type(exc).__name__}: {exc}"
                    self.state.fallback_count += 1
                    self._load_legacy(reason="falha_vista_modular")
            resolved = self._classes.get(requested)
            if not isinstance(resolved, type):
                raise RuntimeError(f"A classe {requested} não foi publicada pela vista selecionada.")
            return resolved

    def _new_module(self, backend: str, sources: tuple[Path, ...]) -> types.ModuleType:
        token_seed = "|".join(str(path.resolve()) for path in sources)
        token = hashlib.sha1(token_seed.encode("utf-8")).hexdigest()[:12]
        name = f"central_cte_runtime_view_{backend}_{token}"
        old = sys.modules.get(name)
        if isinstance(old, types.ModuleType):
            return old
        module = types.ModuleType(name)
        namespace = module.__dict__
        namespace.update(vars(self.compatibility_module))
        namespace.update(
            {
                "__name__": name,
                "__package__": "central_cte_modular.ui.views",
                "__loader__": None,
                "__spec__": None,
                "__file__": str(sources[-1]),
                "__central_cte_view_backend__": backend,
                "__central_cte_view_sources__": tuple(str(path) for path in sources),
            }
        )
        sys.modules[name] = module
        return module

    def _exec_sources(self, backend: str, sources: tuple[Path, ...]) -> types.ModuleType:
        missing = [str(path) for path in sources if not path.exists()]
        if missing:
            raise FileNotFoundError("Fontes da vista ausentes: " + ", ".join(missing))
        module = self._new_module(backend, sources)
        required = VIEW_CLASS_NAMES if backend == "modular_tk" else CORE_VIEW_CLASS_NAMES
        if all(isinstance(getattr(module, name, None), type) for name in required):
            return module
        try:
            for source in sources:
                text = source.read_text(encoding="utf-8-sig")
                code = compile(text, str(source), "exec")
                exec(code, module.__dict__, module.__dict__)
        except Exception:
            sys.modules.pop(module.__name__, None)
            raise
        self._validate_contract(module, backend=backend)
        return module

    @staticmethod
    def _validate_contract(module: types.ModuleType, *, backend: str) -> None:
        required = VIEW_CLASS_NAMES if backend == "modular_tk" else CORE_VIEW_CLASS_NAMES
        missing = [name for name in required if not isinstance(getattr(module, name, None), type)]
        if missing:
            raise RuntimeError("Contrato visual incompleto: " + ", ".join(missing))
        app = getattr(module, "App")
        required = ("create_widgets", "add_files", "refresh_table", "update_stats", "mainloop")
        absent = [name for name in required if not callable(getattr(app, name, None))]
        if absent:
            raise RuntimeError("Contrato da App incompleto: " + ", ".join(absent))

    def _load_modular(self) -> None:
        if self.state.modular_loaded:
            return
        started = time.perf_counter()
        module = self._exec_sources("modular_tk", self._modular_sources)
        self._activate(module, backend="modular_tk_view")
        self.state.modular_loaded = True
        self.state.load_seconds = round(time.perf_counter() - started, 6)
        self.state.last_error = ""

    def _load_legacy(self, *, reason: str) -> None:
        if self.state.legacy_loaded:
            return
        started = time.perf_counter()
        module = self._exec_sources("legacy_tk", (self._legacy_source,))
        self._activate(module, backend="legacy_tk_fallback")
        self.state.legacy_loaded = True
        self.state.load_seconds = round(time.perf_counter() - started, 6)
        if reason:
            self.state.last_error = self.state.last_error or reason

    def _activate(self, module: types.ModuleType, *, backend: str) -> None:
        classes = {
            name: getattr(module, name)
            for name in VIEW_CLASS_NAMES
            if isinstance(getattr(module, name, None), type)
        }
        self._view_module = module
        self._classes = classes
        for name, value in classes.items():
            setattr(self.compatibility_module, name, value)
            if self.facade_globals is not None:
                self.facade_globals[name] = value
            try:
                self.runtime.artifacts[f"MODULAR_VIEW_CLASS_{name.upper()}"] = value
            except Exception:
                pass
        self.state.selected_backend = backend
        self.state.load_count += 1
        self.state.loaded_at = datetime.now().isoformat(timespec="seconds")
        self.state.class_names = list(classes)
        app = classes["App"]
        self.state.app_methods = sum(
            1 for name, value in vars(app).items() if callable(value) and not name.startswith("__")
        )
        self._notify_class_consumers()
        self.write_audit()

    def _notify_class_consumers(self) -> None:
        callbacks: list[tuple[str, Any]] = []
        for name in (
            "rescan_status_ui_bridge",
            "rescan_ui_controller_bridge",
            "rescan_invoice_shadow_bridge",
            "rescan_reporting_bridge",
        ):
            callback = getattr(self.compatibility_module, name, None)
            if callable(callback):
                callbacks.append((name, callback))
        for name, callback in callbacks:
            try:
                callback()
                self.state.callbacks_executed += 1
            except Exception as exc:
                self.state.callback_errors.append(f"{name}:{type(exc).__name__}:{exc}")

    def class_contract(self) -> dict[str, Any]:
        return {
            "required_classes": list(CORE_VIEW_CLASS_NAMES),
            "modular_page_classes": list(PAGE_VIEW_CLASS_NAMES),
            "modular_sources": [str(path) for path in self._modular_sources],
            "legacy_source": str(self._legacy_source),
            "modular_source_lines": sum(_line_count(path) for path in self._modular_sources),
            "legacy_source_lines": _line_count(self._legacy_source),
            "modular_source_sha256": _combined_sha256(self._modular_sources),
            "legacy_source_sha256": _sha256(self._legacy_source),
        }

    def summary(self) -> dict[str, Any]:
        payload = self.state.to_dict()
        payload.update(self.class_contract())
        payload["force_legacy_flag"] = str(self._force_legacy_flag)
        payload["view_module"] = self._view_module.__name__ if self._view_module else ""
        payload["loaded"] = bool(self._classes)
        payload["page_classes_loaded"] = [name for name in PAGE_VIEW_CLASS_NAMES if name in self._classes]
        payload["page_class_count"] = len(payload["page_classes_loaded"])
        payload["legacy_source_loaded_at_bootstrap"] = False
        return payload

    def write_audit(self) -> dict[str, Any]:
        payload = self.summary()
        if self.report_dir is None:
            return payload
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            (self.report_dir / "ultima_auditoria_vistas.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            lines = [
                f"Central CT-e Fábrica de Vistas {VIEW_FACTORY_VERSION}",
                f"Instalada em: {payload['installed_at']}",
                f"Modo: {payload['mode']}",
                f"Backend selecionado: {payload['selected_backend']}",
                f"Vista carregada: {'SIM' if payload['loaded'] else 'NÃO'}",
                f"Vista modular carregada: {'SIM' if payload['modular_loaded'] else 'NÃO'}",
                f"Fallback legado carregado: {'SIM' if payload['legacy_loaded'] else 'NÃO'}",
                f"Carregamentos: {payload['load_count']}",
                f"Resoluções: {payload['resolve_count']}",
                f"Fallbacks automáticos: {payload['fallback_count']}",
                f"Métodos próprios da App: {payload['app_methods']}",
                f"Páginas modulares carregadas: {', '.join(payload.get('page_classes_loaded') or []) or '-'}",
                f"Linhas das fontes modulares: {payload['modular_source_lines']}",
                f"Linhas da fonte legada: {payload['legacy_source_lines']}",
                f"Tempo de carga: {payload['load_seconds']}s",
                f"Callbacks executados: {payload['callbacks_executed']}",
                f"Flag de retorno legado: {payload['force_legacy_flag']}",
                f"Último erro: {payload['last_error'] or '-'}",
            ]
            if payload["callback_errors"]:
                lines.extend(["", "Erros de callbacks:"])
                lines.extend(f"- {value}" for value in payload["callback_errors"])
            (self.report_dir / "ultima_auditoria_vistas.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
            with (self.report_dir / "ultima_auditoria_vistas.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["METRICA", "VALOR"])
                for key in (
                    "version", "installed_at", "mode", "selected_backend", "loaded",
                    "modular_loaded", "legacy_loaded", "load_count", "resolve_count",
                    "fallback_count", "app_methods", "page_class_count", "page_classes_loaded", "modular_source_lines",
                    "legacy_source_lines", "load_seconds", "callbacks_executed",
                    "last_error", "force_legacy_flag",
                ):
                    writer.writerow([key, payload.get(key, "")])
            with (self.report_dir / "vistas_modulares.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception:
            pass
        return payload


def _line_count(path: Path) -> int:
    try:
        return len(Path(path).read_text(encoding="utf-8-sig").splitlines())
    except Exception:
        return 0


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except Exception:
        return ""


def _combined_sha256(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        try:
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        except Exception:
            return ""
    return digest.hexdigest()


__all__ = [
    "VIEW_FACTORY_VERSION",
    "MODE_MODULAR_GUARDED",
    "MODE_LEGACY",
    "CORE_VIEW_CLASS_NAMES",
    "PAGE_VIEW_CLASS_NAMES",
    "VIEW_CLASS_NAMES",
    "ViewFactoryState",
    "ModularViewFactory",
]
