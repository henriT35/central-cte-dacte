from __future__ import annotations

"""RC21: compactação final obrigatória antes de HTML, assinatura e PDF."""

from typing import Any, Iterable, Mapping, MutableMapping

from .commercial.compact_render_guard import (
    COMPACT_RENDER_GUARD_VERSION,
    FinalCompactRenderGuard,
)
from .rc20_runtime_patch import install_rc20_runtime

RC21_VERSION = "2.7.0 RC21 — Guarda Final do Cálculo Compacto"


def install_rc21_runtime(target_globals: MutableMapping[str, Any], bootstrap_state: Any) -> dict[str, Any]:
    prior_state = install_rc20_runtime(target_globals, bootstrap_state)
    namespace = bootstrap_state.compatibility_module
    services = bootstrap_state.services
    engine_namespace = services.resolve("engine_namespace")

    guard = FinalCompactRenderGuard()
    prior_validate = engine_namespace.get("validate_cte_value")
    prior_render_document = engine_namespace.get("render_document")
    prior_render_dacte = engine_namespace.get("render_dacte_page")
    prior_render_dacte_modular = engine_namespace.get("render_dacte_page_modular")
    prior_render_page = engine_namespace.get("render_page")

    if not callable(prior_validate):
        raise RuntimeError("validate_cte_value RC20 não está disponível")
    if not callable(prior_render_document):
        raise RuntimeError("render_document modular não está disponível")
    if not callable(prior_render_dacte):
        raise RuntimeError("render_dacte_page modular não está disponível")

    def validate_cte_value(info: dict[str, Any], base_data: Any, tables: Any):
        result = prior_validate(info, base_data, tables)
        if isinstance(result, MutableMapping):
            guard.repair_validation(info, result)
        return result

    def render_document(
        infos: Iterable[Mapping[str, Any]],
        with_button: bool = True,
        auto_print: bool = False,
    ) -> str:
        # ``list`` é intencional para evitar que um gerador seja consumido duas
        # vezes e para garantir que assinatura individual e lote recebam a
        # mesma fotografia reparada.
        prepared = guard.prepare_infos(list(infos), strict=True)
        return prior_render_document(
            prepared,
            with_button=with_button,
            auto_print=auto_print,
        )

    def render_dacte_page(info: Mapping[str, Any]) -> str:
        prepared = guard.prepare_infos([info], strict=True)[0]
        return prior_render_dacte(prepared)

    def render_dacte_page_modular(info: Mapping[str, Any]) -> str:
        prepared = guard.prepare_infos([info], strict=True)[0]
        renderer = prior_render_dacte_modular or prior_render_dacte
        return renderer(prepared)

    def render_page(info: Mapping[str, Any]) -> str:
        if str(info.get("tipo") or "") == "CT-e":
            return render_dacte_page(info)
        if callable(prior_render_page):
            return prior_render_page(info)
        return prior_render_dacte(info)

    published = {
        "validate_cte_value": validate_cte_value,
        "render_document": render_document,
        "render_dacte_page": render_dacte_page,
        "render_dacte_page_modular": render_dacte_page_modular,
        "render_page": render_page,
        "MODULAR_COMPACT_RENDER_GUARD": guard,
        "MODULAR_COMPACT_RENDER_GUARD_VERSION": COMPACT_RENDER_GUARD_VERSION,
        "APP_VERSION": RC21_VERSION,
    }
    for name, value in published.items():
        engine_namespace[name] = value
        try:
            setattr(namespace, name, value)
        except Exception:
            pass
    target_globals.update(published)
    target_globals.update({
        "CENTRAL_CTE_RC20_STATE": prior_state,
        "RC21_RUNTIME_PATCH": True,
    })

    try:
        services.register_instance("compact_render_guard", guard, replace=True)
    except Exception:
        pass

    return {
        "version": RC21_VERSION,
        "active": True,
        "rc20_preserved": bool(prior_state.get("active")),
        "guard_version": COMPACT_RENDER_GUARD_VERSION,
        "validation_repaired_after_final_result": True,
        "html_guard_active": True,
        "signature_guard_active": True,
        "pdf_guard_active": True,
        "fail_closed_on_ok_with_visual_divergence": True,
        "render_document_wrapped": True,
        "render_dacte_page_wrapped": True,
    }


__all__ = ["RC21_VERSION", "install_rc21_runtime"]
