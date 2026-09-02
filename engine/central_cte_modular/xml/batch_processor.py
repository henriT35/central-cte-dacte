from __future__ import annotations

"""Processador rápido de lotes XML com cache e paralelismo controlado."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping
import multiprocessing
import os
import sys
import time

from .cache import XmlParseCache
from .cte_parser import PARSER_VERSION, parse_xml_modular
from .promotion import MODE_MODULAR_FAST

BATCH_PROCESSOR_VERSION = "2.7.0-rc17-batch-4"
ProgressCallback = Callable[[int, int, str], Any]


def _parse_modular_worker(path_text: str) -> tuple[str, dict[str, Any]]:
    """Worker de módulo, necessário para ser serializável no Windows/PyInstaller."""
    path = Path(path_text)
    return path_text, parse_xml_modular(path)


@dataclass
class XmlBatchParseResult:
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    requested: int = 0
    cache_hits: int = 0
    parsed: int = 0
    workers: int = 1
    parallel: bool = False
    elapsed_ms: float = 0.0
    cache_backend: str = "disabled"
    mode: str = MODE_MODULAR_FAST
    parallel_fallback: str = ""

    def to_metrics(self) -> dict[str, Any]:
        return {
            "processor_version": BATCH_PROCESSOR_VERSION,
            "parser_version": PARSER_VERSION,
            "requested_xml": self.requested,
            "cache_hits": self.cache_hits,
            "parsed_xml": self.parsed,
            "parser_errors": len(self.errors),
            "workers": self.workers,
            "parallel": self.parallel,
            "parallel_fallback": self.parallel_fallback,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "cache_backend": self.cache_backend,
            "mode": self.mode,
        }


class FastXmlBatchProcessor:
    def __init__(
        self,
        cache: XmlParseCache | None = None,
        *,
        mode_resolver: Callable[[], str] | None = None,
        max_workers: int | None = None,
        parallel_threshold: int = 100,
        parallel_min_bytes: int = 32 * 1024 * 1024,
        parallel_min_files: int = 2000,
    ) -> None:
        self.cache = cache
        self.mode_resolver = mode_resolver or (lambda: MODE_MODULAR_FAST)
        self.max_workers = self._resolve_worker_count(max_workers)
        self.parallel_threshold = max(2, int(parallel_threshold))
        self.parallel_min_bytes = max(0, int(parallel_min_bytes))
        self.parallel_min_files = max(self.parallel_threshold, int(parallel_min_files))

    @staticmethod
    def _resolve_worker_count(value: int | None) -> int:
        env_value = str(os.environ.get("CENTRAL_CTE_XML_WORKERS", "") or "").strip()
        if env_value:
            try:
                value = int(env_value)
            except ValueError:
                pass
        cpu = max(1, int(os.cpu_count() or 1))
        selected = int(value) if value is not None else min(4, cpu)
        return max(1, min(4, selected, cpu))

    def _mode(self) -> str:
        try:
            return str(self.mode_resolver() or MODE_MODULAR_FAST).strip().lower()
        except Exception:
            return MODE_MODULAR_FAST

    @staticmethod
    def _notify(callback: ProgressCallback | None, done: int, total: int, stage: str) -> None:
        if not callable(callback):
            return
        try:
            callback(int(done), int(total), str(stage))
        except Exception:
            pass

    def parse_many(
        self,
        paths: Iterable[Path | str],
        *,
        parser: Callable[[Path], Mapping[str, Any]] | None = None,
        progress: ProgressCallback | None = None,
    ) -> XmlBatchParseResult:
        started = time.perf_counter()
        ordered = [Path(path) for path in paths]
        mode = self._mode()
        result = XmlBatchParseResult(requested=len(ordered), mode=mode)
        total = len(ordered)
        if not ordered:
            return result

        # Homologação e emergência preservam o parser conectado exatamente como
        # antes. Cache e processos ficam restritos ao modo modular rápido.
        if mode != MODE_MODULAR_FAST:
            parse = parser or parse_xml_modular
            for index, path in enumerate(ordered, start=1):
                try:
                    parsed = dict(parse(path) or {})
                    parsed["path"] = str(path)
                    parsed.setdefault("arquivo", path.name)
                    result.results[XmlParseCache.canonical(path)] = parsed
                    result.parsed += 1
                except Exception as exc:
                    result.errors[XmlParseCache.canonical(path)] = f"{type(exc).__name__}: {exc}"
                self._notify(progress, index, total, "homologacao")
            result.elapsed_ms = (time.perf_counter() - started) * 1000.0
            return result

        cache_hits: dict[str, dict[str, Any]] = {}
        if self.cache is not None:
            cache_hits, stats = self.cache.lookup_many(ordered)
            result.cache_backend = stats.backend
        result.results.update(cache_hits)
        result.cache_hits = len(cache_hits)
        self._notify(progress, result.cache_hits, total, "cache")

        misses = [path for path in ordered if XmlParseCache.canonical(path) not in cache_hits]
        freshly_parsed: dict[Path, dict[str, Any]] = {}
        if misses:
            use_parallel = self._can_parallelize(misses)
            if use_parallel:
                try:
                    parsed_records = self._parse_parallel(misses, progress, total, result.cache_hits)
                    result.parallel = True
                    result.workers = self.max_workers
                except Exception as exc:
                    result.parallel_fallback = f"{type(exc).__name__}: {exc}"
                    parsed_records = self._parse_sequential(misses, progress, total, result.cache_hits)
                    result.parallel = False
                    result.workers = 1
            else:
                parsed_records = self._parse_sequential(misses, progress, total, result.cache_hits)
                result.workers = 1

            for path, parsed, error in parsed_records:
                key = XmlParseCache.canonical(path)
                if error:
                    result.errors[key] = error
                    continue
                info = dict(parsed or {})
                info["path"] = str(path)
                info.setdefault("arquivo", path.name)
                result.results[key] = info
                freshly_parsed[path] = info
                result.parsed += 1

        if freshly_parsed and self.cache is not None:
            try:
                self.cache.store_many(freshly_parsed)
                result.cache_backend = self.cache.backend
            except Exception as exc:
                if not result.parallel_fallback:
                    result.parallel_fallback = f"cache: {type(exc).__name__}: {exc}"

        result.elapsed_ms = (time.perf_counter() - started) * 1000.0
        self._notify(progress, total, total, "concluido")
        return result

    def _can_parallelize(self, paths: list[Path]) -> bool:
        disabled = str(os.environ.get("CENTRAL_CTE_XML_PARALLEL", "1") or "1").strip().lower()
        if disabled in {"0", "false", "nao", "não", "off"}:
            return False
        if self.max_workers <= 1 or len(paths) < self.parallel_threshold:
            return False
        # No Windows, iniciar processos custa mais que ler centenas de XMLs
        # pequenos. O paralelismo só entra quando o volume total compensa esse
        # pedágio; pode ser forçado com CENTRAL_CTE_XML_PARALLEL=force.
        if disabled in {"force", "forcar", "forçar"}:
            return True
        # O Windows/PyInstaller usa ``spawn`` e paga um custo alto para abrir
        # processos. Por isso, centenas de XMLs pequenos continuam sequenciais;
        # processos entram apenas em lotes realmente grandes ou pesados.
        if len(paths) >= self.parallel_min_files:
            return True

        total_bytes = 0
        for path in paths:
            try:
                total_bytes += int(path.stat().st_size)
            except Exception:
                pass
        return total_bytes >= self.parallel_min_bytes

    def _parse_sequential(
        self,
        paths: list[Path],
        progress: ProgressCallback | None,
        total: int,
        completed_before: int,
    ) -> list[tuple[Path, dict[str, Any], str]]:
        output: list[tuple[Path, dict[str, Any], str]] = []
        for offset, path in enumerate(paths, start=1):
            try:
                output.append((path, parse_xml_modular(path), ""))
            except Exception as exc:
                output.append((path, {}, f"{type(exc).__name__}: {exc}"))
            self._notify(progress, completed_before + offset, total, "parser")
        return output

    def _parse_parallel(
        self,
        paths: list[Path],
        progress: ProgressCallback | None,
        total: int,
        completed_before: int,
    ) -> list[tuple[Path, dict[str, Any], str]]:
        # ``spawn`` corresponde ao comportamento do Windows e evita herdar a UI.
        context = multiprocessing.get_context("spawn")
        output: list[tuple[Path, dict[str, Any], str]] = []
        path_texts = [str(path) for path in paths]
        chunk_size = max(1, len(path_texts) // max(1, self.max_workers * 8))
        with ProcessPoolExecutor(
            max_workers=self.max_workers,
            mp_context=context,
        ) as executor:
            iterator = executor.map(_parse_modular_worker, path_texts, chunksize=chunk_size)
            for offset, (path_text, parsed) in enumerate(iterator, start=1):
                output.append((Path(path_text), dict(parsed or {}), ""))
                self._notify(progress, completed_before + offset, total, "parser_paralelo")
        return output


__all__ = [
    "BATCH_PROCESSOR_VERSION",
    "FastXmlBatchProcessor",
    "ProgressCallback",
    "XmlBatchParseResult",
]
