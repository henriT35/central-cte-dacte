from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_store import AtomicJsonStore


class JsonSettings(AtomicJsonStore):
    def __init__(self, path: Path) -> None:
        super().__init__(path, default={})

    def load(self) -> dict[str, Any]:
        value = super().load()
        return value if isinstance(value, dict) else {}

    def save(self, values: dict[str, Any]) -> None:
        super().save(dict(values or {}))
