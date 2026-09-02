from __future__ import annotations

"""RC24: auditoria genérica de pedágio e compacto explicativo da Rodotec."""

from typing import Any, MutableMapping

from .commercial.compact_control_service import COMPACT_CONTROL_SERVICE_VERSION
from .commercial.compact_render_guard import COMPACT_RENDER_GUARD_VERSION
from .commercial.optional_components import calcular_pedagio_regra
from .rc23_runtime_patch import install_rc23_runtime

RC24_VERSION = "2.7.0 RC24 — Rodotec: GRIS e Pedágio Auditáveis"


def install_rc24_runtime(target_globals: MutableMapping[str, Any], bootstrap_state: Any) -> dict[str, Any]:
    prior_state = install_rc23_runtime(target_globals, bootstrap_state)
    namespace = bootstrap_state.compatibility_module
    services = bootstrap_state.services
    engine_namespace = services.resolve("engine_namespace")
    published = {
        "APP_VERSION": RC24_VERSION,
        "CENTRAL_CTE_RC23_STATE": prior_state,
        "calcular_pedagio_regra": calcular_pedagio_regra,
    }
    for name, value in published.items():
        target_globals[name] = value
        engine_namespace[name] = value
        try:
            setattr(namespace, name, value)
        except Exception:
            pass
    target_globals["RC24_RUNTIME_PATCH"] = True
    return {
        "version": RC24_VERSION,
        "active": True,
        "rc23_preserved": bool(prior_state.get("active")),
        "toll_audit_generic": True,
        "rodotec_toll_formula": "ceil(peso_kg / fracao_kg) * valor_fracao",
        "rodotec_gris_formula": "valor_mercadoria * percentual_gris",
        "compact_formula_explicit": True,
        "compact_control_version": COMPACT_CONTROL_SERVICE_VERSION,
        "compact_guard_version": COMPACT_RENDER_GUARD_VERSION,
        "reports_preserved": True,
    }


__all__ = ["RC24_VERSION", "install_rc24_runtime"]
