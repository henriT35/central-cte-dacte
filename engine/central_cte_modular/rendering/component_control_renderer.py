from __future__ import annotations

"""Renderização explícita do bloco de controle interno no DACTE."""

from .overlays.compact_control import CompactControlOverlay

COMPONENT_CONTROL_RENDERER_VERSION = "2.6.69.6"


class ComponentControlRenderer(CompactControlOverlay):
    """Nome de serviço estável para o overlay antes instalado por monkeypatch."""


__all__ = ["COMPONENT_CONTROL_RENDERER_VERSION", "ComponentControlRenderer"]
