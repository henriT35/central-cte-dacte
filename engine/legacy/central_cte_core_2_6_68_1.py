# -*- coding: utf-8 -*-
"""Fachada preguiçosa de compatibilidade do Central CT-e 2.7.0."""

from central_cte_modular.legacy_core.runtime_composition_compat import (
    install_legacy_core_composition as _install_legacy_core_composition_2690,
)

CENTRAL_CTE_LEGACY_CORE_COMPOSITION_STATE = _install_legacy_core_composition_2690(globals())
del _install_legacy_core_composition_2690
