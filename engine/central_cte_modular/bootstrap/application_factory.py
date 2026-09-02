from __future__ import annotations

"""Fábrica modular da aplicação.

A construção da janela principal deixa de ficar embutida no carregador do
runtime. A fábrica concentra criação, revarredura dos adaptadores, auditoria e
tratamento de erro de inicialização, preparando a retirada final da interface
histórica na série 2.7.x.
"""

import csv
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

APPLICATION_FACTORY_VERSION = "2.7.0"


@dataclass
class ApplicationFactoryState:
    version: str = APPLICATION_FACTORY_VERSION
    installed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    mode: str = "modular_factory_direct_2700"
    create_count: int = 0
    run_count: int = 0
    last_created_at: str = ""
    last_create_seconds: float = 0.0
    last_error: str = ""
    app_class_name: str = "App"
    ui_backend: str = "deferred_modular_view"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "installed_at": self.installed_at,
            "mode": self.mode,
            "create_count": self.create_count,
            "run_count": self.run_count,
            "last_created_at": self.last_created_at,
            "last_create_seconds": self.last_create_seconds,
            "last_error": self.last_error,
            "app_class_name": self.app_class_name,
            "ui_backend": self.ui_backend,
        }


class ModularApplicationFactory:
    def __init__(
        self,
        compatibility_module: ModuleType,
        runtime: Any,
        view_factory: Any,
    ) -> None:
        self.compatibility_module = compatibility_module
        self.runtime = runtime
        self.view_factory = view_factory
        self.state = ApplicationFactoryState()
        self._lock = threading.RLock()
        self._active_application: Any | None = None
        self.report_dir = self._resolve_report_dir()
        self.write_audit()

    def _resolve_report_dir(self) -> Path | None:
        try:
            paths = self.runtime.services.resolve("paths")
            return Path(paths.reports) / "fabrica_aplicacao_modular"
        except Exception:
            return None

    def _resolve_app_class(self) -> type:
        app_class = self.view_factory.resolve("App")
        if not isinstance(app_class, type):
            raise RuntimeError("A fábrica de vistas não publicou uma classe App válida.")
        try:
            view_summary = self.view_factory.summary()
            self.state.ui_backend = str(view_summary.get("selected_backend") or "unknown")
        except Exception:
            self.state.ui_backend = "unknown"
        return app_class

    def create(self, *, app_class: type | None = None) -> Any:
        with self._lock:
            if self._active_application is not None:
                return self._active_application
            started = time.perf_counter()
            try:
                resolved_class = app_class or self._resolve_app_class()
                application = resolved_class()
                self._active_application = application
                self.state.create_count += 1
                self.state.last_created_at = datetime.now().isoformat(timespec="seconds")
                self.state.last_create_seconds = round(time.perf_counter() - started, 6)
                self.state.last_error = ""
                self._write_lazy_fallback_audit()
                self.write_audit()
                return application
            except Exception as exc:
                self.state.last_create_seconds = round(time.perf_counter() - started, 6)
                self.state.last_error = f"{type(exc).__name__}: {exc}"
                self.write_audit()
                raise

    def release(self, application: Any | None = None) -> None:
        with self._lock:
            if application is None or application is self._active_application:
                self._active_application = None

    def run(self) -> None:
        application = None
        try:
            application = self.create()
            self.state.run_count += 1
            self.write_audit()
            application.mainloop()
        except Exception as exc:
            self.state.last_error = f"{type(exc).__name__}: {exc}"
            self.write_audit()
            handler = getattr(self.compatibility_module, "show_startup_error", None)
            if callable(handler):
                handler(exc)
                return
            raise
        finally:
            if application is not None:
                self.release(application)

    def _write_lazy_fallback_audit(self) -> None:
        registry = getattr(
            self.compatibility_module, "CENTRAL_CTE_LEGACY_LAZY_REGISTRY", None
        )
        if registry is None or self.report_dir is None:
            return
        writer = getattr(registry, "write_audit", None)
        if callable(writer):
            try:
                writer(self.report_dir.parent / "fallbacks_sob_demanda")
            except Exception:
                pass

    def summary(self) -> dict[str, Any]:
        payload = self.state.to_dict()
        payload["active_application"] = self._active_application is not None
        lazy_registry = getattr(
            self.compatibility_module, "CENTRAL_CTE_LEGACY_LAZY_REGISTRY", None
        )
        try:
            payload["lazy_fallbacks"] = lazy_registry.snapshot() if lazy_registry else {}
        except Exception:
            payload["lazy_fallbacks"] = {}
        try:
            payload["view_factory"] = self.view_factory.summary()
            if payload["view_factory"].get("loaded"):
                payload["ui_backend"] = str(
                    payload["view_factory"].get("selected_backend") or payload["ui_backend"]
                )
        except Exception:
            payload["view_factory"] = {}
        return payload

    def write_audit(self) -> dict[str, Any]:
        payload = self.summary()
        if self.report_dir is None:
            return payload
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            (self.report_dir / "ultima_auditoria_fabrica.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            lines = [
                f"Central CT-e Fábrica Modular {APPLICATION_FACTORY_VERSION}",
                f"Instalada em: {payload['installed_at']}",
                f"Modo: {payload['mode']}",
                f"Classe da aplicação: {payload['app_class_name']}",
                f"Backend visual: {payload['ui_backend']}",
                f"Vista carregada: {'SIM' if (payload.get('view_factory') or {}).get('loaded') else 'NÃO'}",
                f"Fallback visual: {'SIM' if (payload.get('view_factory') or {}).get('legacy_loaded') else 'NÃO'}",
                f"Criações: {payload['create_count']}",
                f"Execuções: {payload['run_count']}",
                f"Última criação: {payload['last_created_at'] or '-'}",
                f"Tempo da última criação: {payload['last_create_seconds']}s",
                f"Aplicação ativa: {'SIM' if payload['active_application'] else 'NÃO'}",
                f"Último erro: {payload['last_error'] or '-'}",
            ]
            lazy = payload.get("lazy_fallbacks") or {}
            if lazy:
                lines.extend(
                    [
                        "",
                        f"Fallbacks carregados: {lazy.get('loaded_count', 0)}",
                        f"Fallbacks pendentes: {lazy.get('pending_count', 0)}",
                        "Pendentes: " + ", ".join(lazy.get("pending_components", []) or []),
                    ]
                )
            (self.report_dir / "ultima_auditoria_fabrica.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
            with (self.report_dir / "ultima_auditoria_fabrica.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["METRICA", "VALOR"])
                for key in (
                    "version", "installed_at", "mode", "app_class_name", "ui_backend",
                    "create_count", "run_count", "last_created_at",
                    "last_create_seconds", "active_application",
                    "last_error",
                ):
                    writer.writerow([key, payload.get(key, "")])
                if lazy:
                    writer.writerow(["fallbacks_loaded", lazy.get("loaded_count", 0)])
                    writer.writerow(["fallbacks_pending", lazy.get("pending_count", 0)])
            with (self.report_dir / "fabrica_aplicacao.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
                )
        except Exception:
            pass
        return payload


__all__ = [
    "APPLICATION_FACTORY_VERSION",
    "ApplicationFactoryState",
    "ModularApplicationFactory",
]
