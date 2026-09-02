from __future__ import annotations

"""Correções RC20 para o cálculo compacto orientado pelo resultado validado.

A RC19 reativou o bloco compacto, porém o serviço visual ainda escolhia o modo
pela simples presença de tarifa por tonelada na tabela. Regras híbridas da
Rodotec possuem percentual e tarifa por tonelada ao mesmo tempo; por isso 78
CT-es cobrados em FRETE VALOR eram exibidos como FRETE PESO. A RC20 reaplica o
compacto depois de todos os enriquecimentos comerciais e usa a decisão final do
validador como fonte de verdade.
"""

from typing import Any, MutableMapping

from .commercial.compact_control_service import COMPACT_CONTROL_SERVICE_VERSION
from .rc19_runtime_patch import install_rc19_runtime

RC20_VERSION = "2.7.0 RC20 — Compacto Fiel ao Cálculo Validado"


def install_rc20_runtime(target_globals: MutableMapping[str, Any], bootstrap_state: Any) -> dict[str, Any]:
    prior_state = install_rc19_runtime(target_globals, bootstrap_state)
    namespace = bootstrap_state.compatibility_module
    services = bootstrap_state.services
    engine_namespace = services.resolve("engine_namespace")

    enriched_validate = engine_namespace.get("validate_cte_value")
    compact_control = engine_namespace.get("MODULAR_COMPACT_CONTROL")
    if not callable(enriched_validate):
        raise RuntimeError("validate_cte_value enriquecido da RC19 não está disponível")
    if compact_control is None or not hasattr(compact_control, "apply"):
        raise RuntimeError("serviço de cálculo compacto não está disponível")

    def validate_cte_value(info: dict[str, Any], base_data: Any, tables: Any):
        result = enriched_validate(info, base_data, tables)
        # A reaplicação é intencional. CompactControlService.clear() remove o
        # bloco anterior antes de reconstruí-lo com o status, componente,
        # esperado e repasses já consolidados pelo motor comercial.
        return compact_control.apply(result, info, base_data, tables)

    engine_namespace["validate_cte_value"] = validate_cte_value
    namespace.validate_cte_value = validate_cte_value
    namespace.APP_VERSION = RC20_VERSION

    target_globals.update({
        "APP_VERSION": RC20_VERSION,
        "validate_cte_value": validate_cte_value,
        "CENTRAL_CTE_RC19_STATE": prior_state,
        "RC20_RUNTIME_PATCH": True,
    })

    return {
        "version": RC20_VERSION,
        "active": True,
        "rc19_bridge_preserved": bool(prior_state.get("active")),
        "compact_reapplied_after_enrichment": True,
        "compact_mode_source": "componente_comparado + modo_calculo do resultado final",
        "frete_valor_priority": True,
        "frete_peso_preserved": True,
        "validation_bridge_reinstalled": bool(prior_state.get("validation_bridge_reinstalled")),
        "compact_control_active": True,
        "component_control_active": bool(prior_state.get("component_control_active")),
        "compact_control_version": COMPACT_CONTROL_SERVICE_VERSION,
    }


__all__ = ["RC20_VERSION", "install_rc20_runtime"]
