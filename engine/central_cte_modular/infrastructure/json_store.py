from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class AtomicJsonStore:
    """Thread-safe JSON persistence with atomic replacement."""

    def __init__(self, path: Path, default: Any = None) -> None:
        self.path = Path(path)
        self.default = {} if default is None else default
        self._lock = RLock()

    def load(self) -> Any:
        with self._lock:
            if not self.path.exists():
                return self._copy_default()
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return self._copy_default()

    def save(self, value: Any) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            os.replace(temporary, self.path)

    def _copy_default(self) -> Any:
        try:
            return json.loads(json.dumps(self.default))
        except Exception:
            return self.default
