from __future__ import annotations

"""Contratos puros usados pela proteção visual Qt da RC26.5.

O módulo não importa PySide6. Assim, identidade de CT-e, escala tipográfica e
conversão de roda/touchpad podem ser testadas também fora do Windows.
"""

from typing import Any, Mapping


def stable_cte_key(info: Mapping[str, Any] | None) -> tuple[str, ...]:
    info = info or {}
    access_key = str(info.get("chave") or info.get("access_key") or "").strip()
    if access_key:
        return ("CHAVE", access_key)
    emit = info.get("emit") or {}
    emitter = str(
        emit.get("cnpj")
        or emit.get("cnpjcpf")
        or emit.get("cpf")
        or info.get("emit_cnpj")
        or info.get("parceiro")
        or ""
    ).strip()
    return (
        "CTE",
        str(info.get("numero") or info.get("number") or "").strip(),
        str(info.get("serie") or info.get("series") or "").strip(),
        emitter,
        str(info.get("arquivo") or info.get("file") or info.get("path") or "").strip(),
    )


def card_value_point_size(value: Any) -> int:
    """Escala valores longos sem quebrar a linha nem dominar o card."""

    text = " ".join(str(value or "").split())
    length = len(text)
    if length <= 6:
        return 24
    if length <= 11:
        return 21
    if length <= 17:
        return 18
    return 16


def horizontal_scroll_delta(
    *,
    angle_x: int = 0,
    angle_y: int = 0,
    pixel_x: int = 0,
    pixel_y: int = 0,
    shift_pressed: bool = False,
) -> int:
    """Normaliza roda horizontal, touchpad e Shift+roda em um único delta."""

    direct = pixel_x or angle_x
    if direct:
        return int(direct)
    if shift_pressed:
        return int(pixel_y or angle_y)
    return 0


__all__ = ["card_value_point_size", "horizontal_scroll_delta", "stable_cte_key"]
