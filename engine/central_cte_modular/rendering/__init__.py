"""Renderização modular e controlada do DACTE/HTML."""
from .component_control_renderer import (
    COMPONENT_CONTROL_RENDERER_VERSION,
    ComponentControlRenderer,
)
from .dacte_renderer import ModularDacteRenderer
from .document_renderer import HtmlDocumentRenderer
from .guarded_renderer import GuardedHtmlRenderer, RendererPromotionReport

__all__ = [
    "COMPONENT_CONTROL_RENDERER_VERSION",
    "ComponentControlRenderer",
    "ModularDacteRenderer",
    "HtmlDocumentRenderer",
    "GuardedHtmlRenderer",
    "RendererPromotionReport",
]
