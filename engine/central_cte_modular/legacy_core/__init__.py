"""Compatibilidade histórica desacoplada e carregada sob demanda.

O pacote não importa os módulos de fallback durante sua própria inicialização.
Os instaladores antigos continuam acessíveis por ``__getattr__`` para manter
compatibilidade com scripts de diagnóstico e testes históricos.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "install_runtime_environment_compat": (
        "central_cte_modular.legacy_core.runtime_environment_compat",
        "install_runtime_environment_compat",
    ),
    "install_legacy_core_composition": (
        "central_cte_modular.legacy_core.runtime_composition_compat",
        "install_legacy_core_composition",
    ),
    "install_lazy_fallbacks": (
        "central_cte_modular.legacy_core.lazy_fallbacks",
        "install_lazy_fallbacks",
    ),
    "LazyFallbackRegistry": (
        "central_cte_modular.legacy_core.lazy_fallbacks",
        "LazyFallbackRegistry",
    ),
    "install_runtime_support_compat": (
        "central_cte_modular.legacy_core.runtime_support_compat",
        "install_runtime_support_compat",
    ),
    "install_xml_parser_compat": (
        "central_cte_modular.legacy_core.xml_parser_compat",
        "install_xml_parser_compat",
    ),
    "install_rendering_print_compat": (
        "central_cte_modular.legacy_core.rendering_print_compat",
        "install_rendering_print_compat",
    ),
    "install_base_repository_compat": (
        "central_cte_modular.legacy_core.base_repository_compat",
        "install_base_repository_compat",
    ),
    "install_report_excel_compat": (
        "central_cte_modular.legacy_core.report_excel_compat",
        "install_report_excel_compat",
    ),
    "install_commercial_validation_compat": (
        "central_cte_modular.legacy_core.commercial_validation_compat",
        "install_commercial_validation_compat",
    ),
}


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = sorted(_EXPORTS)
