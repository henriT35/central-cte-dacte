from __future__ import annotations

"""Composição preguiçosa do runtime histórico residual.

Somente o ambiente mínimo e os helpers necessários para construir a interface
são instalados na inicialização. Parser, renderização, Base/XLSX, validação e
relatórios históricos recebem proxies e são carregados na primeira chamada.
"""

from typing import Any, MutableMapping

from .lazy_fallbacks import LAZY_FALLBACK_VERSION, install_lazy_fallbacks

COMPOSITION_VERSION = LAZY_FALLBACK_VERSION


def install_legacy_core_composition(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
    registry = install_lazy_fallbacks(target_globals)
    state = target_globals.get("CENTRAL_CTE_LEGACY_CORE_COMPOSITION_STATE")
    if not isinstance(state, dict):
        raise RuntimeError("A composição preguiçosa não publicou seu estado.")
    state["version"] = COMPOSITION_VERSION
    state["module"] = __name__
    state["registry"] = registry.__class__.__name__
    return state


__all__ = [
    "COMPOSITION_VERSION",
    "install_legacy_core_composition",
]
