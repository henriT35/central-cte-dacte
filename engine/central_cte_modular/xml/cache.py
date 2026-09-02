from __future__ import annotations

"""Cache persistente dos resultados do parser XML.

O backend preferencial é SQLite. Distribuições antigas que não incluam a
extensão ``_sqlite3`` continuam funcionando por meio de um fallback JSON.GZ
atômico. Em ambos os casos a validade usa caminho, tamanho, ``mtime_ns`` e a
versão do parser. Para manter a leitura única, o SHA-256 completo é opcional
e só é calculado quando ``CENTRAL_CTE_XML_CACHE_SHA256=1``.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping
import gzip
import hashlib
import json
import os

try:  # No executável antigo o módulo nativo pode não ter sido empacotado.
    import sqlite3  # type: ignore
except Exception:  # pragma: no cover - exercitado no executável sem _sqlite3
    sqlite3 = None  # type: ignore

CACHE_VERSION = "2.7.0-rc17-xml-cache-3"


@dataclass(frozen=True)
class XmlCacheStats:
    requested: int = 0
    hits: int = 0
    misses: int = 0
    backend: str = "disabled"

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "hits": self.hits,
            "misses": self.misses,
            "backend": self.backend,
            "cache_version": CACHE_VERSION,
        }


class XmlParseCache:
    def __init__(
        self,
        path: Path | str,
        *,
        parser_version: str,
        enabled: bool = True,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.parser_version = str(parser_version or "unknown")
        self.enabled = bool(enabled)
        self._lock = RLock()
        self._json_path = self.path.with_suffix(".json.gz")
        self._json_loaded = False
        self._json_records: dict[str, dict[str, Any]] = {}
        self.backend = "disabled"
        if self.enabled:
            self.backend = "sqlite" if sqlite3 is not None else "json.gz"
            if self.backend == "sqlite":
                try:
                    self._ensure_sqlite()
                except Exception:
                    self.backend = "json.gz"

    @staticmethod
    def canonical(path: Path | str) -> str:
        candidate = Path(path)
        try:
            return os.path.normcase(str(candidate.expanduser().resolve()))
        except Exception:
            return os.path.normcase(os.path.abspath(str(candidate)))

    @staticmethod
    def sha256(path: Path | str) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _stat(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return int(stat.st_size), int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))

    def lookup_many(
        self,
        paths: Iterable[Path | str],
    ) -> tuple[dict[str, dict[str, Any]], XmlCacheStats]:
        requested = [Path(path) for path in paths]
        if not self.enabled or not requested:
            return {}, XmlCacheStats(
                requested=len(requested),
                hits=0,
                misses=len(requested),
                backend=self.backend,
            )
        with self._lock:
            if self.backend == "sqlite":
                hits = self._lookup_sqlite(requested)
            else:
                hits = self._lookup_json(requested)
        return hits, XmlCacheStats(
            requested=len(requested),
            hits=len(hits),
            misses=max(0, len(requested) - len(hits)),
            backend=self.backend,
        )

    def store_many(self, records: Mapping[Path | str, Mapping[str, Any]]) -> int:
        if not self.enabled or not records:
            return 0
        prepared: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for raw_path, raw_result in records.items():
            path = Path(raw_path)
            try:
                size, mtime_ns = self._stat(path)
                audit_hash = str(os.environ.get("CENTRAL_CTE_XML_CACHE_SHA256", "0") or "0").strip().lower()
                digest = self.sha256(path) if audit_hash in {"1", "true", "sim", "yes", "on"} else ""
            except Exception:
                continue
            result = dict(raw_result or {})
            result["path"] = str(path)
            result.setdefault("arquivo", path.name)
            prepared.append({
                "path": self.canonical(path),
                "size": size,
                "mtime_ns": mtime_ns,
                "sha256": digest,
                "parser_version": self.parser_version,
                "result": result,
                "updated_at": now,
            })
        if not prepared:
            return 0
        with self._lock:
            if self.backend == "sqlite":
                try:
                    self._store_sqlite(prepared)
                except Exception:
                    # Não perde a importação se o SQLite ficar indisponível.
                    self.backend = "json.gz"
                    self._store_json(prepared)
            else:
                self._store_json(prepared)
        return len(prepared)

    def clear(self) -> None:
        with self._lock:
            for target in (self.path, self._json_path):
                try:
                    target.unlink(missing_ok=True)
                except Exception:
                    pass
            self._json_loaded = True
            self._json_records = {}
            if self.enabled and self.backend == "sqlite":
                self._ensure_sqlite()

    # ------------------------------------------------------------------
    # SQLite
    # ------------------------------------------------------------------
    def _connect(self):
        if sqlite3 is None:
            raise RuntimeError("sqlite3 indisponível")
        connection = sqlite3.connect(str(self.path), timeout=20.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA temp_store=MEMORY")
        return connection

    def _ensure_sqlite(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS xml_parse_cache (
                    path TEXT PRIMARY KEY,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_xml_cache_signature "
                "ON xml_parse_cache(size, mtime_ns, parser_version)"
            )

    def _lookup_sqlite(self, paths: list[Path]) -> dict[str, dict[str, Any]]:
        signatures: dict[str, tuple[Path, int, int]] = {}
        for path in paths:
            try:
                size, mtime_ns = self._stat(path)
            except Exception:
                continue
            signatures[self.canonical(path)] = (path, size, mtime_ns)
        if not signatures:
            return {}
        found: dict[str, dict[str, Any]] = {}
        keys = list(signatures)
        with self._connect() as connection:
            for start in range(0, len(keys), 800):
                chunk = keys[start:start + 800]
                placeholders = ",".join("?" for _ in chunk)
                query = (
                    "SELECT path, size, mtime_ns, parser_version, result_json "
                    f"FROM xml_parse_cache WHERE path IN ({placeholders})"
                )
                for key, size, mtime_ns, parser_version, payload in connection.execute(query, chunk):
                    signature = signatures.get(str(key))
                    if signature is None:
                        continue
                    path, current_size, current_mtime = signature
                    if (
                        int(size) != current_size
                        or int(mtime_ns) != current_mtime
                        or str(parser_version) != self.parser_version
                    ):
                        continue
                    try:
                        result = json.loads(payload)
                    except Exception:
                        continue
                    if isinstance(result, dict):
                        result["path"] = str(path)
                        result.setdefault("arquivo", path.name)
                        found[str(key)] = result
        return found

    def _store_sqlite(self, prepared: list[dict[str, Any]]) -> None:
        rows = [
            (
                item["path"],
                item["size"],
                item["mtime_ns"],
                item["sha256"],
                item["parser_version"],
                json.dumps(item["result"], ensure_ascii=False, separators=(",", ":"), default=str),
                item["updated_at"],
            )
            for item in prepared
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO xml_parse_cache
                    (path, size, mtime_ns, sha256, parser_version, result_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size=excluded.size,
                    mtime_ns=excluded.mtime_ns,
                    sha256=excluded.sha256,
                    parser_version=excluded.parser_version,
                    result_json=excluded.result_json,
                    updated_at=excluded.updated_at
                """,
                rows,
            )

    # ------------------------------------------------------------------
    # JSON.GZ fallback
    # ------------------------------------------------------------------
    def _load_json(self) -> None:
        if self._json_loaded:
            return
        self._json_loaded = True
        self._json_records = {}
        if not self._json_path.is_file():
            return
        try:
            with gzip.open(self._json_path, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            if isinstance(payload, dict) and isinstance(payload.get("records"), dict):
                self._json_records = dict(payload["records"])
        except Exception:
            self._json_records = {}

    def _lookup_json(self, paths: list[Path]) -> dict[str, dict[str, Any]]:
        self._load_json()
        found: dict[str, dict[str, Any]] = {}
        for path in paths:
            try:
                size, mtime_ns = self._stat(path)
            except Exception:
                continue
            key = self.canonical(path)
            record = self._json_records.get(key)
            if not isinstance(record, dict):
                continue
            if (
                int(record.get("size", -1)) != size
                or int(record.get("mtime_ns", -1)) != mtime_ns
                or str(record.get("parser_version", "")) != self.parser_version
            ):
                continue
            result = record.get("result")
            if isinstance(result, dict):
                copied = dict(result)
                copied["path"] = str(path)
                copied.setdefault("arquivo", path.name)
                found[key] = copied
        return found

    def _store_json(self, prepared: list[dict[str, Any]]) -> None:
        self._load_json()
        for item in prepared:
            self._json_records[item["path"]] = {
                "size": item["size"],
                "mtime_ns": item["mtime_ns"],
                "sha256": item["sha256"],
                "parser_version": item["parser_version"],
                "result": item["result"],
                "updated_at": item["updated_at"],
            }
        payload = {
            "cache_version": CACHE_VERSION,
            "parser_version": self.parser_version,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "records": self._json_records,
        }
        temp = self._json_path.with_suffix(self._json_path.suffix + ".tmp")
        with gzip.open(temp, "wt", encoding="utf-8", compresslevel=5) as stream:
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), default=str)
        temp.replace(self._json_path)


__all__ = ["CACHE_VERSION", "XmlCacheStats", "XmlParseCache"]
