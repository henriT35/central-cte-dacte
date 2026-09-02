from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import Any


class ServiceNotFoundError(KeyError):
    """Raised when a requested service was not registered."""


class ServiceContainer:
    """Small lazy dependency container used during the strangler migration.

    Services are resolved once by default and cached. This keeps construction
    explicit while avoiding imports from the monolithic engine.
    """

    def __init__(self) -> None:
        self._factories: dict[str, Callable[["ServiceContainer"], Any]] = {}
        self._instances: dict[str, Any] = {}
        self._lock = RLock()

    def register_instance(self, name: str, value: Any, *, replace: bool = False) -> None:
        key = self._normalize(name)
        with self._lock:
            if not replace and (key in self._instances or key in self._factories):
                raise ValueError(f"Serviço já registrado: {key}")
            self._instances[key] = value
            self._factories.pop(key, None)

    def register_factory(
        self,
        name: str,
        factory: Callable[["ServiceContainer"], Any],
        *,
        replace: bool = False,
    ) -> None:
        if not callable(factory):
            raise TypeError("A fábrica do serviço precisa ser chamável.")
        key = self._normalize(name)
        with self._lock:
            if not replace and (key in self._instances or key in self._factories):
                raise ValueError(f"Serviço já registrado: {key}")
            self._factories[key] = factory
            self._instances.pop(key, None)

    def resolve(self, name: str) -> Any:
        key = self._normalize(name)
        with self._lock:
            if key in self._instances:
                return self._instances[key]
            factory = self._factories.get(key)
            if factory is None:
                raise ServiceNotFoundError(key)
            instance = factory(self)
            self._instances[key] = instance
            return instance

    def contains(self, name: str) -> bool:
        key = self._normalize(name)
        with self._lock:
            return key in self._instances or key in self._factories

    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(set(self._instances) | set(self._factories)))

    @staticmethod
    def _normalize(name: str) -> str:
        key = str(name or "").strip().lower()
        if not key:
            raise ValueError("O nome do serviço não pode ficar vazio.")
        return key
