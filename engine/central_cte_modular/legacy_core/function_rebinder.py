from __future__ import annotations

from types import FunctionType
from typing import Any, Iterable, MutableMapping


def clone_function_for_namespace(function: FunctionType, target_globals: MutableMapping[str, Any]) -> FunctionType:
    """Clona uma função mantendo o código no módulo extraído e os globais no host legado.

    Isso preserva o contrato histórico: chamadas globais continuam resolvidas no
    runtime composto, mas os corpos deixam de ocupar o arquivo central.
    """

    clone = FunctionType(
        function.__code__,
        target_globals,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    clone.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    clone.__annotations__ = dict(getattr(function, "__annotations__", {}) or {})
    clone.__dict__.update(getattr(function, "__dict__", {}) or {})
    clone.__doc__ = function.__doc__
    clone.__module__ = function.__module__
    clone.__qualname__ = function.__qualname__
    return clone


def install_rebound_functions(
    source_globals: MutableMapping[str, Any],
    target_globals: MutableMapping[str, Any],
    names: Iterable[str],
) -> tuple[str, ...]:
    installed: list[str] = []
    for name in names:
        function = source_globals.get(name)
        if not isinstance(function, FunctionType):
            raise TypeError(f"{name!r} não é uma função extraível")
        target_globals[name] = clone_function_for_namespace(function, target_globals)
        installed.append(name)
    return tuple(installed)


__all__ = ["clone_function_for_namespace", "install_rebound_functions"]
