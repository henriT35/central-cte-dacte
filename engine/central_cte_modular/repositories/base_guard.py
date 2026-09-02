from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time
from typing import Any, Callable, Mapping

from .base_cache import RodovitorBaseCache
from .repository_audit import RepositoryAuditReport

MODE_MODULAR_GUARDED = "modular_guarded"
MODE_LEGACY = "legacy"
MODE_SHADOW = "shadow"
VALID_BASE_MODES = {MODE_MODULAR_GUARDED, MODE_LEGACY, MODE_SHADOW}


class GuardedRodovitorBaseLoader:
    """Promove a base modular sem executar uma segunda carga completa.

    No modo padrão o legado só é chamado se a leitura/cache modular falhar.
    ``shadow`` mantém o legado oficial e tenta o modular apenas para diagnóstico;
    existe somente para homologação pontual, não é o modo padrão.
    """

    def __init__(
        self,
        modular_cache: RodovitorBaseCache,
        legacy_cached_loader: Callable[..., dict[str, Any]],
        report: RepositoryAuditReport,
        get_mode: Callable[[], str],
    ) -> None:
        self.modular_cache = modular_cache
        self.legacy_cached_loader = legacy_cached_loader
        self.report = report
        self.get_mode = get_mode

    def load(self, file_path: str | Path, force: bool = False) -> dict[str, Any]:
        path = Path(file_path)
        mode = str(self.get_mode() or MODE_MODULAR_GUARDED).strip().lower()
        if mode not in VALID_BASE_MODES:
            mode = MODE_MODULAR_GUARDED
        modular_only = path.is_dir() or path.suffix.lower() == ".sswweb"

        if mode == MODE_LEGACY and modular_only:
            started = time.perf_counter()
            modular = self.modular_cache.load(path, force=force)
            elapsed = time.perf_counter() - started
            self._record(
                path,
                selected="modular",
                reason="sswweb_requires_modular",
                mode=mode,
                elapsed=elapsed,
                data=modular,
                modular_error="",
                exact_equal=True,
            )
            return modular

        if mode == MODE_LEGACY:
            started = time.perf_counter()
            legacy = self.legacy_cached_loader(path, force=force)
            elapsed = time.perf_counter() - started
            self._record(
                path,
                selected="legacy",
                reason="legacy_forced",
                mode=mode,
                elapsed=elapsed,
                data=legacy,
                modular_error="",
            )
            return legacy

        if mode == MODE_SHADOW and modular_only:
            started = time.perf_counter()
            modular = self.modular_cache.load(path, force=force)
            elapsed = time.perf_counter() - started
            self._record(
                path,
                selected="modular",
                reason="sswweb_shadow_without_legacy",
                mode=mode,
                elapsed=elapsed,
                data=modular,
                modular_error="",
                exact_equal=True,
            )
            return modular

        if mode == MODE_SHADOW:
            started = time.perf_counter()
            legacy = self.legacy_cached_loader(path, force=force)
            legacy_seconds = time.perf_counter() - started
            modular_error = ""
            modular: dict[str, Any] | None = None
            started = time.perf_counter()
            try:
                modular = self.modular_cache.load(path, force=force)
            except Exception as exc:
                modular_error = f"{type(exc).__name__}: {exc}"
            modular_seconds = time.perf_counter() - started
            exact = self._contract_equal(legacy, modular) if modular is not None else False
            self._record(
                path,
                selected="legacy",
                reason="shadow_equal" if exact else ("modular_error" if modular_error else "shadow_different"),
                mode=mode,
                elapsed=legacy_seconds,
                data=legacy,
                modular_error=modular_error,
                modular_seconds=modular_seconds,
                exact_equal=exact,
            )
            return legacy

        started = time.perf_counter()
        try:
            modular = self.modular_cache.load(path, force=force)
            elapsed = time.perf_counter() - started
            cache = dict(modular.get("_cache") or {})
            if cache.get("status") == "HIT":
                reason = "modular_cache_hit"
            elif cache.get("source_format") == "sswweb":
                reason = "modular_sswweb_loaded"
            else:
                reason = "modular_xlsx_loaded"
            self._record(
                path,
                selected="modular",
                reason=reason,
                mode=mode,
                elapsed=elapsed,
                data=modular,
                modular_error="",
                exact_equal=True,
            )
            return modular
        except Exception as exc:
            modular_error = f"{type(exc).__name__}: {exc}"
            modular_seconds = time.perf_counter() - started
            if modular_only:
                self.report.record({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "kind": "base_rodovitor_completa",
                    "file_path": str(path),
                    "selected": "modular",
                    "reason": "modular_sswweb_error",
                    "mode": mode,
                    "exact_equal": False,
                    "legacy_seconds": 0.0,
                    "modular_seconds": round(modular_seconds, 4),
                    "total_rows": 0,
                    "total_nfs": 0,
                    "cache_status": "",
                    "cache_path": "",
                    "source_sha256": "",
                    "modular_sha256": "",
                    "legacy_sha256": "",
                    "modular_error": modular_error,
                    "first_difference": None,
                    "note": "Fontes .sswweb não possuem fallback no leitor XLSX legado.",
                })
                raise
            started = time.perf_counter()
            legacy = self.legacy_cached_loader(path, force=force)
            legacy_seconds = time.perf_counter() - started
            self._record(
                path,
                selected="legacy",
                reason="modular_error_fallback_legacy",
                mode=mode,
                elapsed=legacy_seconds,
                data=legacy,
                modular_error=modular_error,
                modular_seconds=modular_seconds,
                exact_equal=False,
            )
            return legacy

    @staticmethod
    def _contract_equal(left: Mapping[str, Any], right: Mapping[str, Any] | None) -> bool:
        if right is None:
            return False
        return left.get("rows") == right.get("rows") and left.get("index") == right.get("index")

    def _record(
        self,
        path: Path,
        *,
        selected: str,
        reason: str,
        mode: str,
        elapsed: float,
        data: Mapping[str, Any],
        modular_error: str,
        modular_seconds: float | None = None,
        exact_equal: bool | None = None,
    ) -> None:
        cache = dict(data.get("_cache") or {})
        rows = data.get("rows") or []
        index = data.get("index") or {}
        self.report.record({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "kind": "base_rodovitor_completa",
            "file_path": str(path),
            "selected": selected,
            "reason": reason,
            "mode": mode,
            "exact_equal": exact_equal,
            "legacy_seconds": round(elapsed, 4) if selected == "legacy" else 0.0,
            "modular_seconds": round(
                modular_seconds if modular_seconds is not None else (elapsed if selected == "modular" else 0.0), 4
            ),
            "sample_rows": "",
            "matched_rows": "",
            "mismatched_rows": "",
            "total_rows": len(rows),
            "total_nfs": len(index),
            "cache_status": cache.get("status", ""),
            "cache_path": cache.get("cache_path", ""),
            "source_sha256": cache.get("source_sha256", ""),
            "modular_sha256": cache.get("fingerprint", ""),
            "legacy_sha256": "",
            "modular_error": modular_error,
            "first_difference": None,
            "note": (
                "Carga modular oficial sem dupla leitura completa."
                if selected == "modular"
                else "Fallback/forçamento explícito para o carregador legado."
            ),
        })
