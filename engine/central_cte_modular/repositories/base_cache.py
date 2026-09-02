from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Mapping

from .rodovitor_base_repository import RodovitorBaseRepository, row_fingerprint


class RodovitorBaseCache:
    """Cache compacto e validado da base Rodovitor.

    O cache guarda somente a lista canônica de registros. O índice por NF é
    reconstruído em memória apontando para os mesmos objetos, evitando a
    duplicação gigantesca do cache legado que serializava rows e index.
    """

    FORMAT = "central-cte-rodovitor-base-cache"
    SCHEMA_VERSION = 3
    LOADER_ID = "rodovitor-modular-cache-v3-sswweb"

    def __init__(self, repository: RodovitorBaseRepository, cache_dir: str | Path) -> None:
        self.repository = repository
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def source_signature(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path).resolve()
        files = self.repository.source_files(path)
        entries: list[dict[str, Any]] = []
        combined = hashlib.sha256()
        for source in files:
            stat = source.stat()
            sha256 = self._sha256_file(source)
            entry = {
                "name": source.name,
                "size": int(stat.st_size),
                "mtime_ns": int(
                    getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
                ),
                "sha256": sha256,
            }
            entries.append(entry)
            encoded = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
            combined.update(len(encoded).to_bytes(8, "big"))
            combined.update(encoded)
        source_format = "sswweb" if self.repository.is_ssw_source(path) else "xlsx"
        return {
            "name": path.name,
            "kind": "collection" if len(files) > 1 or path.is_dir() else "file",
            "source_format": source_format,
            "file_count": len(files),
            "files": entries,
            "sha256": combined.hexdigest(),
            "loader": self.LOADER_ID,
        }

    def cache_path(self, file_path: str | Path) -> Path:
        path = Path(file_path).resolve()
        base_name = path.name if path.is_dir() else path.stem
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", base_name).strip("_") or "base_rodovitor"
        location_hash = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
        return self.cache_dir / f"{safe}_{location_hash}_modular_v3.json.gz"

    def load(self, file_path: str | Path, *, force: bool = False) -> dict[str, Any]:
        path = Path(file_path)
        started = time.perf_counter()
        signature = self.source_signature(path)
        cache_path = self.cache_path(path)
        cache_error = ""

        if not force and cache_path.exists():
            try:
                data = self._read_valid_cache(path, cache_path, signature)
                elapsed = time.perf_counter() - started
                data["_cache"] = {
                    "status": "HIT",
                    "provider": "modular",
                    "format": self.FORMAT,
                    "schema_version": self.SCHEMA_VERSION,
                    "cache_path": str(cache_path),
                    "arquivo": path.name,
                    "source_format": signature.get("source_format", ""),
                    "source_files": [item.get("name", "") for item in signature.get("files", [])],
                    "file_count": int(signature.get("file_count") or 0),
                    "seconds": round(elapsed, 3),
                    "source_sha256": signature["sha256"],
                    "row_count": len(data.get("rows") or []),
                    "nf_count": len(data.get("index") or {}),
                }
                return data
            except Exception as exc:
                cache_error = f"{type(exc).__name__}: {exc}"
                self._quarantine(cache_path)

        data = self.repository.load(path)
        validation = self.repository.validate_data(data)
        self._write_cache(path, cache_path, signature, data, validation)
        elapsed = time.perf_counter() - started
        data["_cache"] = {
            "status": "MISS",
            "provider": "modular",
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "cache_path": str(cache_path),
            "arquivo": path.name,
            "source_format": signature.get("source_format", ""),
            "source_files": [item.get("name", "") for item in signature.get("files", [])],
            "file_count": int(signature.get("file_count") or 0),
            "seconds": round(elapsed, 3),
            "source_sha256": signature["sha256"],
            "row_count": validation["row_count"],
            "nf_count": validation["nf_count"],
            "fingerprint": validation["fingerprint"],
            "cache_rebuilt_after_error": cache_error,
        }
        return data

    def _read_valid_cache(
        self,
        source_path: Path,
        cache_path: Path,
        expected_signature: Mapping[str, Any],
    ) -> dict[str, Any]:
        with gzip.open(cache_path, "rt", encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict):
            raise ValueError("Cache não é um objeto JSON.")
        if payload.get("format") != self.FORMAT:
            raise ValueError("Formato de cache desconhecido.")
        if int(payload.get("schema_version") or 0) != self.SCHEMA_VERSION:
            raise ValueError("Versão de cache incompatível.")
        if payload.get("source") != dict(expected_signature):
            raise ValueError("A planilha foi alterada desde a criação do cache.")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Cache sem lista de registros.")
        expected_count = int(payload.get("row_count") or 0)
        if expected_count != len(rows):
            raise ValueError(f"Quantidade inválida no cache: {len(rows)} != {expected_count}.")
        expected_fingerprint = str(payload.get("rows_sha256") or "")
        actual_fingerprint = row_fingerprint(rows)
        if not expected_fingerprint or actual_fingerprint != expected_fingerprint:
            raise ValueError("Hash dos registros do cache não confere.")
        data = self.repository.rebuild_from_cached_rows(
            source_path,
            rows,
            fingerprint=actual_fingerprint,
            skipped_without_nf=int(payload.get("skipped_without_nf") or 0),
        )
        data["source_format"] = str(expected_signature.get("source_format") or "")
        data["source_files"] = [
            str(item.get("name") or "") for item in expected_signature.get("files", [])
        ]
        validation = self.repository.validate_data(data)
        expected_nf_count = int(payload.get("nf_count") or 0)
        if expected_nf_count != validation["nf_count"]:
            raise ValueError(
                f"Quantidade de NFs inválida no cache: {validation['nf_count']} != {expected_nf_count}."
            )
        return data

    def _write_cache(
        self,
        source_path: Path,
        cache_path: Path,
        signature: Mapping[str, Any],
        data: Mapping[str, Any],
        validation: Mapping[str, Any],
    ) -> None:
        payload = {
            "format": self.FORMAT,
            "schema_version": self.SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_path": str(source_path.resolve()),
            "source_format": str(signature.get("source_format") or ""),
            "source_files": [item.get("name", "") for item in signature.get("files", [])],
            "source": dict(signature),
            "row_count": int(validation["row_count"]),
            "nf_count": int(validation["nf_count"]),
            "skipped_without_nf": 0,
            "rows_sha256": str(validation["fingerprint"]),
            "rows": data.get("rows") or [],
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=cache_path.name + ".", suffix=".tmp", dir=str(cache_path.parent)
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as stream:
                json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"), default=str)
            os.replace(temporary, cache_path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except Exception:
                pass

    def invalidate(self, file_path: str | Path) -> bool:
        path = self.cache_path(file_path)
        if not path.exists():
            return False
        path.unlink()
        return True

    @staticmethod
    def _quarantine(cache_path: Path) -> None:
        if not cache_path.exists():
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = cache_path.with_name(cache_path.name + f".corrompido_{stamp}")
        try:
            os.replace(cache_path, target)
        except Exception:
            try:
                cache_path.unlink(missing_ok=True)
            except Exception:
                pass
