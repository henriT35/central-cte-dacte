#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if target != root and root not in target.parents:
            raise RuntimeError(f"Entrada insegura no backup: {member.filename}")
    archive.extractall(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura um backup completo da Central CT-e")
    parser.add_argument("backup")
    parser.add_argument("--target", default="/data")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    backup = Path(args.backup).resolve()
    target = Path(args.target).resolve()
    if not args.confirm:
        raise SystemExit("Use --confirm para autorizar a substituição dos dados.")
    if not backup.is_file():
        raise FileNotFoundError(backup)
    digest = sha256_file(backup)
    if args.expected_sha256 and digest.lower() != args.expected_sha256.strip().lower():
        raise RuntimeError("O SHA-256 do backup não confere.")

    with tempfile.TemporaryDirectory(prefix="central_cte_restore_") as temp:
        extracted = Path(temp)
        with zipfile.ZipFile(backup, "r") as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise RuntimeError(f"Backup corrompido na entrada: {corrupt}")
            safe_extract(archive, extracted)
        manifest = json.loads((extracted / "backup_manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format") != "central-cte-backup-v1":
            raise RuntimeError("Formato de backup desconhecido.")
        data = extracted / "data"
        for entry in manifest.get("files") or []:
            path = data / str(entry["path"])
            if not path.is_file() or sha256_file(path) != entry["sha256"]:
                raise RuntimeError(f"Integridade inválida em {entry['path']}")
        target.mkdir(parents=True, exist_ok=True)
        for current in list(target.iterdir()):
            if current.is_dir() and not current.is_symlink():
                shutil.rmtree(current)
            else:
                current.unlink(missing_ok=True)
        shutil.copytree(data, target, dirs_exist_ok=True)
    print(json.dumps({"restored": True, "target": str(target), "sha256": digest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
