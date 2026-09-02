from __future__ import annotations

from pathlib import Path
from typing import Any

from .settings import JsonSettings


class JsonSessionStore(JsonSettings):
    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self.load()
        data[str(key)] = value
        self.save(data)

    def remove(self, key: str) -> bool:
        data = self.load()
        existed = str(key) in data
        data.pop(str(key), None)
        self.save(data)
        return existed
