from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any


class ModularLogger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = RLock()

    def write(self, event: str, **payload: Any) -> None:
        record = {"timestamp": datetime.now().isoformat(timespec="seconds"), "event": str(event), **payload}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def write_legacy(self, file_name: str, text: Any, logs_dir: Path) -> None:
        try:
            path = Path(logs_dir) / str(file_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._lock, path.open("a", encoding="utf-8") as stream:
                stream.write(f"[{stamp}] {text}\n")
        except Exception:
            pass
