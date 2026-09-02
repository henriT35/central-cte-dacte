from __future__ import annotations

import os
from pathlib import Path
from typing import Any, MutableMapping

from ..rendering.component_control_renderer import (
    COMPONENT_CONTROL_RENDERER_VERSION,
    ComponentControlRenderer,
)
from ..rendering.dacte_renderer import ModularDacteRenderer
from ..rendering.document_renderer import HtmlDocumentRenderer
from ..rendering.guarded_renderer import (
    GuardedHtmlRenderer,
    MODE_LEGACY_SHADOW,
    MODE_MODULAR_GUARDED,
    RendererPromotionReport,
    VALID_MODES,
)
from ..rendering.overlays.complementary_information import ComplementaryInformationOverlay
from ..rendering.styles import DACTE_CSS

BRIDGE_VERSION = "2.6.69.6"


def install_rendering_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    legacy_dacte = module_globals.get("LEGACY_RENDER_DACTE_PAGE") or module_globals.get("render_dacte_page")
    legacy_summary = module_globals.get("LEGACY_RENDER_SUMMARY_PAGE") or module_globals.get("summary_page")
    if not callable(legacy_dacte) or not callable(legacy_summary):
        return {
            "version": BRIDGE_VERSION,
            "active": False,
            "reason": "renderizadores legados não encontrados",
        }

    get_information = module_globals.get("get_complementary_print_information")
    is_cte = module_globals.get("_central_cte_is_cte_info")
    if not callable(get_information):
        get_information = lambda _info: ""
    if not callable(is_cte):
        is_cte = lambda info: str((info or {}).get("tipo", "")).replace("-", "").replace(" ", "").upper() in {"CTE", "CT"}

    paths = services.resolve("paths")
    logger = services.resolve("logger")
    try:
        settings = services.resolve("settings")
    except Exception:
        settings = None
    memory_settings: dict[str, Any] = {}
    report_dir = Path(paths.reports) / "renderizador_sombra"
    reporter = RendererPromotionReport(report_dir)
    sessions_dir = Path(getattr(paths, "sessions", Path(paths.reports).parent / "sessoes"))
    emergency_flag = sessions_dir / "FORCAR_RENDERIZADOR_LEGADO.flag"

    def log(message: str) -> None:
        try:
            logger.write("renderizador_dacte", message=str(message))
        except Exception:
            pass

    def get_mode() -> str:
        environment_mode = str(os.environ.get("CENTRAL_CTE_DACTE_RENDERER_MODE", "") or "").strip().lower()
        if environment_mode in VALID_MODES:
            return environment_mode
        if emergency_flag.exists():
            return MODE_LEGACY_SHADOW
        try:
            source = settings.load() if settings is not None else memory_settings
            configured = str(source.get("dacte_renderer_mode", "") or "").strip().lower()
            if configured in VALID_MODES:
                return configured
        except Exception:
            pass
        return MODE_MODULAR_GUARDED

    def set_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_MODES)}")
        if settings is None:
            memory_settings["dacte_renderer_mode"] = normalized
        else:
            values = settings.load()
            values["dacte_renderer_mode"] = normalized
            settings.save(values)
        return normalized

    component_control_renderer = ComponentControlRenderer()
    modular_renderer = ModularDacteRenderer(compact_overlay=component_control_renderer)

    def legacy_dacte_with_component_control(info: dict[str, Any]) -> str:
        return component_control_renderer.apply(info, legacy_dacte(info))

    guarded = GuardedHtmlRenderer(
        legacy_dacte_with_component_control,
        legacy_summary,
        modular_renderer.render_dacte,
        modular_renderer.render_summary,
        reporter,
        get_mode,
        log,
    )

    def render_page(info: dict[str, Any]) -> str:
        return guarded.render_dacte(info) if info.get("tipo") == "CT-e" else guarded.render_summary(info)

    complementary_overlay = ComplementaryInformationOverlay(get_information, is_cte)
    document_renderer = HtmlDocumentRenderer(render_page, complementary_overlay, DACTE_CSS)

    module_globals["LEGACY_RENDER_DACTE_PAGE"] = legacy_dacte
    module_globals["LEGACY_RENDER_SUMMARY_PAGE"] = legacy_summary
    module_globals["MODULAR_DACTE_RENDERER"] = modular_renderer
    module_globals["MODULAR_COMPONENT_CONTROL_RENDERER"] = component_control_renderer
    module_globals["MODULAR_RENDERING_CONTROLLER"] = guarded
    module_globals["MODULAR_RENDERING_REPORTER"] = reporter
    module_globals["MODULAR_RENDERING_REPORT_DIR"] = report_dir
    module_globals["MODULAR_RENDERING_EMERGENCY_FLAG"] = emergency_flag
    module_globals["render_dacte_page_modular"] = modular_renderer.render_dacte
    module_globals["summary_page_modular"] = modular_renderer.render_summary
    module_globals["render_dacte_page"] = guarded.render_dacte
    module_globals["summary_page"] = guarded.render_summary
    module_globals["render_page"] = render_page
    module_globals["render_document"] = document_renderer.render
    module_globals["get_dacte_renderer_mode"] = get_mode
    module_globals["set_dacte_renderer_mode"] = set_mode
    module_globals["get_dacte_renderer_summary"] = reporter.snapshot
    module_globals["MODULAR_RENDERING_VERSION"] = BRIDGE_VERSION

    try:
        services.register_instance(
            "component_control_renderer",
            component_control_renderer,
            replace=True,
        )
        services.register_instance("dacte_renderer", modular_renderer, replace=True)
        services.register_instance("rendering_controller", guarded, replace=True)
    except Exception as exc:
        log(f"Falha ao registrar serviços do renderizador: {exc}")

    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": get_mode(),
        "official": "modular_when_html_exact",
        "component_control": "direct_modular_renderer",
        "component_control_version": COMPONENT_CONTROL_RENDERER_VERSION,
        "fallback": "legacy_on_any_html_difference_or_modular_error",
        "legacy_calls_per_page": 1,
        "modular_calls_per_page": 1,
        "report_directory": str(report_dir),
        "session_id": reporter.session_id,
        "emergency_rollback_flag": str(emergency_flag),
        "latest_reports": [
            str(report_dir / "ultima_renderizacao.json"),
            str(report_dir / "ultima_renderizacao.txt"),
            str(report_dir / "ultima_renderizacao.csv"),
            str(reporter.jsonl_path),
        ],
    }
