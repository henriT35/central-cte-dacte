from __future__ import annotations

import hashlib
from pathlib import Path


class FileIntegrityService:
    @staticmethod
    def digest(path: Path, algorithm: str = "sha256") -> str:
        hasher = hashlib.new(algorithm)
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def sha256(self, path: Path) -> str:
        return self.digest(path, "sha256")

    def sha1(self, path: Path) -> str:
        return self.digest(path, "sha1")

    def identical(self, first: Path, second: Path) -> bool:
        a, b = Path(first), Path(second)
        return a.exists() and b.exists() and a.stat().st_size == b.stat().st_size and self.sha256(a) == self.sha256(b)
