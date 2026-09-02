#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(os.environ.get("BACKUP_SOURCE_ROOT", "/data")).resolve()
OUTPUT_ROOT = Path(os.environ.get("BACKUP_OUTPUT_ROOT", "/backups")).resolve()
INTERVAL_SECONDS = max(300, int(os.environ.get("BACKUP_INTERVAL_SECONDS", "86400")))
RETENTION_COUNT = max(1, int(os.environ.get("BACKUP_RETENTION_COUNT", "14")))
RUN_ON_START = os.environ.get("BACKUP_RUN_ON_START", "1").strip() == "1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_sqlite_consistently(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30.0)
    try:
        target_connection = sqlite3.connect(target)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
    finally:
        source_connection.close()


def make_snapshot(snapshot_root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for source in sorted(SOURCE_ROOT.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(SOURCE_ROOT)
        if source.name.endswith(("-wal", "-shm")):
            continue
        target = snapshot_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
            try:
                copy_sqlite_consistently(source, target)
            except sqlite3.DatabaseError:
                shutil.copy2(source, target)
        else:
            shutil.copy2(source, target)
        entries.append({
            "path": relative.as_posix(),
            "size_bytes": target.stat().st_size,
            "sha256": sha256_file(target),
        })
    return entries


def upload_s3(path: Path) -> dict[str, Any] | None:
    bucket = os.environ.get("S3_BUCKET", "").strip()
    if not bucket:
        return None
    import boto3

    prefix = os.environ.get("S3_PREFIX", "central-cte").strip().strip("/")
    endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip() or None
    region = os.environ.get("S3_REGION", "us-east-1").strip() or "us-east-1"
    key = f"{prefix}/{path.name}" if prefix else path.name
    client = boto3.client("s3", endpoint_url=endpoint, region_name=region)
    extra_args: dict[str, str] = {"ContentType": "application/zip"}
    encryption = os.environ.get("S3_SERVER_SIDE_ENCRYPTION", "").strip()
    kms_key_id = os.environ.get("S3_KMS_KEY_ID", "").strip()
    if encryption:
        if encryption not in {"AES256", "aws:kms"}:
            raise ValueError("S3_SERVER_SIDE_ENCRYPTION deve ser AES256 ou aws:kms.")
        extra_args["ServerSideEncryption"] = encryption
    if kms_key_id:
        if encryption != "aws:kms":
            raise ValueError("S3_KMS_KEY_ID exige S3_SERVER_SIDE_ENCRYPTION=aws:kms.")
        extra_args["SSEKMSKeyId"] = kms_key_id
    client.upload_file(str(path), bucket, key, ExtraArgs=extra_args)
    return {"bucket": bucket, "key": key, "endpoint": endpoint or "AWS"}


def prune_local_backups() -> None:
    backups = sorted(OUTPUT_ROOT.glob("central_cte_full_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in backups[RETENTION_COUNT:]:
        stale.unlink(missing_ok=True)
        stale.with_suffix(stale.suffix + ".sha256").unlink(missing_ok=True)


def create_backup() -> dict[str, Any]:
    if not SOURCE_ROOT.is_dir():
        raise FileNotFoundError(f"A origem do backup não existe: {SOURCE_ROOT}")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    final_path = OUTPUT_ROOT / f"central_cte_full_{timestamp}.zip"
    temporary_path = final_path.with_suffix(".zip.tmp")

    with tempfile.TemporaryDirectory(prefix="central_cte_backup_") as temp:
        snapshot_root = Path(temp) / "data"
        snapshot_root.mkdir(parents=True, exist_ok=True)
        entries = make_snapshot(snapshot_root)
        manifest = {
            "format": "central-cte-backup-v1",
            "created_at_utc": now_iso(),
            "source": str(SOURCE_ROOT),
            "files": entries,
            "file_count": len(entries),
            "total_bytes": sum(item["size_bytes"] for item in entries),
        }
        manifest_path = Path(temp) / "backup_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            archive.write(manifest_path, "backup_manifest.json")
            for source in sorted(snapshot_root.rglob("*")):
                if source.is_file():
                    archive.write(source, f"data/{source.relative_to(snapshot_root).as_posix()}")

    with zipfile.ZipFile(temporary_path, "r") as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise RuntimeError(f"Backup corrompido na entrada: {corrupt}")
    temporary_path.replace(final_path)
    digest = sha256_file(final_path)
    final_path.with_suffix(final_path.suffix + ".sha256").write_text(f"{digest}  {final_path.name}\n", encoding="utf-8")
    remote = None
    remote_error = ""
    try:
        remote = upload_s3(final_path)
    except Exception as exc:
        remote_error = str(exc)
        print(json.dumps({"event": "backup.remote_failure", "error": remote_error, "path": str(final_path)}, ensure_ascii=False), flush=True)
    prune_local_backups()
    result = {
        "path": str(final_path),
        "sha256": digest,
        "size_bytes": final_path.stat().st_size,
        "remote": remote,
        "remote_error": remote_error,
    }
    print(json.dumps({"event": "backup.complete", **result}, ensure_ascii=False), flush=True)
    return result


def main() -> int:
    print(json.dumps({
        "event": "backup.scheduler.start",
        "source": str(SOURCE_ROOT),
        "output": str(OUTPUT_ROOT),
        "interval_seconds": INTERVAL_SECONDS,
        "retention_count": RETENTION_COUNT,
        "run_on_start": RUN_ON_START,
    }, ensure_ascii=False), flush=True)
    first = True
    while True:
        if RUN_ON_START or not first:
            try:
                create_backup()
            except Exception as exc:
                print(json.dumps({"event": "backup.failure", "error": str(exc), "time": now_iso()}, ensure_ascii=False), flush=True)
        first = False
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
