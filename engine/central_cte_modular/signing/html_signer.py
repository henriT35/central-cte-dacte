from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .common import (SIGNATURE_CSS_MARKER, SIGNATURE_HTML_MARKER, _compose_document, _extract_body_pages, _extract_style,
                     STAMP_STANDARD_WIDTH_MM, STAMP_STANDARD_HEIGHT_MM, STAMP_STANDARD_ASPECT,
                     STAMP_MIN_WIDTH_MM, STAMP_MAX_WIDTH_MM, STAMP_OFFICIAL_X_MM, STAMP_OFFICIAL_Y_MM,
                     STAMP_OFFICIAL_ROTATION_DEG, DACTE_PRINT_PAGE_MARGIN_MM, SIGNATURE_SCALE_MIN_PERCENT,
                     SIGNATURE_SCALE_MAX_PERCENT, SIGNATURE_OFFSET_LIMIT_MM)
from .image_processing import _signature_data_uri, _signature_stamp_data_uri
from .models import SignatureProfile

STAMP_SIZE_LABELS = {
    "small": "Compacto - 68 x 25,6 mm",
    "medium": "Amplo - 76 x 28,6 mm",
    "large": "Oficial - 85 x 32 mm",
    "official": "Oficial - 85 x 32 mm",
    "custom": "Personalizado pelo editor",
}


def normalize_stamp_size(value: Optional[str]) -> str:
    key = str(value or "official").strip().lower()
    aliases = {
        "p": "small", "pequeno": "small", "small": "small",
        "m": "medium", "medio": "medium", "médio": "medium", "medium": "medium",
        "g": "official", "grande": "official", "large": "official",
        "official": "official", "oficial": "official", "padrao": "official", "padrão": "official",
        "custom": "custom", "personalizado": "custom",
    }
    return aliases.get(key, "official")


def _layout_value(profile: SignatureProfile, name: str, fallback: float) -> float:
    try:
        value = float(getattr(profile, name, fallback))
        return fallback if value != value else value
    except Exception:
        return fallback


def _stamp_dimensions(size: str) -> tuple[float, float]:
    normalized = normalize_stamp_size(size)
    widths = {"small": 68.0, "medium": 76.0, "large": 85.0, "official": 85.0}
    width = widths.get(normalized, STAMP_STANDARD_WIDTH_MM)
    return width, width / STAMP_STANDARD_ASPECT


def _css_mm(value: str, fallback: float) -> float:
    match = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*mm\s*", str(value or ""), flags=re.I)
    if not match:
        return float(fallback)
    try:
        return float(match.group(1).replace(",", "."))
    except Exception:
        return float(fallback)


def _extract_print_page_margins_mm(document_html: str, fallback: float = DACTE_PRINT_PAGE_MARGIN_MM) -> tuple[float, float]:
    blocks = re.findall(r"@page\s*\{([^{}]*)\}", str(document_html or ""), flags=re.I | re.S)
    for block in reversed(blocks):
        match = re.search(r"(?:^|;)\s*margin\s*:\s*([^;{}]+)", block, flags=re.I)
        if not match:
            continue
        parts = [part for part in re.split(r"\s+", match.group(1).strip()) if part]
        if not 1 <= len(parts) <= 4 or any(not re.fullmatch(r"-?\d+(?:[.,]\d+)?mm", part, flags=re.I) for part in parts):
            continue
        values = [_css_mm(part, fallback) for part in parts]
        if len(values) == 1:
            top = left = values[0]
        elif len(values) == 2:
            top, left = values[0], values[1]
        elif len(values) == 3:
            top, left = values[0], values[1]
        else:
            top, left = values[0], values[3]
        return max(0.0, left), max(0.0, top)
    return float(fallback), float(fallback)


def _signature_solid_svg_data_uri(
    image_uri: str,
    title: str,
    date_text: str,
    signature_scale_percent: float = 100.0,
    signature_offset_x_mm: float = 0.0,
    signature_offset_y_mm: float = 0.0,
) -> str:
    """Bloco vetorial único com escala e posição independentes da assinatura."""
    safe_title = html.escape(str(title or "REDESPACHO").upper()[:40])
    safe_date = html.escape(str(date_text or "")[:20])
    safe_image = str(image_uri or "")
    scale_percent = max(
        SIGNATURE_SCALE_MIN_PERCENT,
        min(SIGNATURE_SCALE_MAX_PERCENT, float(signature_scale_percent or 100.0)),
    )
    scale = scale_percent / 100.0
    offset_x_mm = max(-SIGNATURE_OFFSET_LIMIT_MM, min(SIGNATURE_OFFSET_LIMIT_MM, float(signature_offset_x_mm or 0.0)))
    offset_y_mm = max(-SIGNATURE_OFFSET_LIMIT_MM, min(SIGNATURE_OFFSET_LIMIT_MM, float(signature_offset_y_mm or 0.0)))
    offset_x_svg = offset_x_mm * (1000.0 / STAMP_STANDARD_WIDTH_MM)
    offset_y_svg = offset_y_mm * (376.0 / STAMP_STANDARD_HEIGHT_MM)
    center_x, center_y = 560.0, 230.0
    signature_transform = (
        f"translate({offset_x_svg:.2f} {offset_y_svg:.2f}) "
        f"translate({center_x:.2f} {center_y:.2f}) "
        f"scale({scale:.4f}) "
        f"translate({-center_x:.2f} {-center_y:.2f})"
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="376" viewBox="0 0 1000 376">
<rect x="7" y="7" width="986" height="362" fill="none" stroke="#111" stroke-width="5"/>
<text x="500" y="101" text-anchor="middle" font-family="Arial, sans-serif" font-size="88" font-weight="800" fill="#111">{safe_title}</text>
<text x="500" y="151" text-anchor="middle" font-family="Arial, sans-serif" font-size="48" font-weight="700" fill="#111">{safe_date}</text>
<text x="35" y="323" font-family="Arial, sans-serif" font-size="52" font-weight="800" fill="#111">Ass:</text>
<line x1="160" y1="313" x2="955" y2="313" stroke="#111" stroke-width="4"/>
<g data-signature-scale-percent="{scale_percent:.2f}" data-signature-offset-x-mm="{offset_x_mm:.2f}" data-signature-offset-y-mm="{offset_y_mm:.2f}" transform="{signature_transform}">
<image href="{safe_image}" x="165" y="128" width="790" height="204" preserveAspectRatio="xMidYMid meet"/>
</g>
</svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def signature_block_html(
    profile: SignatureProfile,
    date_text: str,
    image_uri: str,
    position: Optional[str] = None,
    stamp_size: str = "official",
    print_page_margins_mm: Optional[tuple[float, float]] = None,
) -> str:
    pos = position or profile.position or "official-stamp"
    size = normalize_stamp_size(stamp_size)
    style = ""
    if pos in {"custom", "reference-docs", "official-stamp"}:
        if pos == "official-stamp":
            x_mm = STAMP_OFFICIAL_X_MM
            y_mm = STAMP_OFFICIAL_Y_MM
            width_mm = STAMP_STANDARD_WIDTH_MM
            height_mm = STAMP_STANDARD_HEIGHT_MM
            rotation = STAMP_OFFICIAL_ROTATION_DEG
        elif pos == "reference-docs":
            x_mm, y_mm = STAMP_OFFICIAL_X_MM, STAMP_OFFICIAL_Y_MM
            width_mm, height_mm = STAMP_STANDARD_WIDTH_MM, STAMP_STANDARD_HEIGHT_MM
            rotation = -6.0
        else:
            x_mm = _layout_value(profile, "custom_x_mm", STAMP_OFFICIAL_X_MM)
            y_mm = _layout_value(profile, "custom_y_mm", STAMP_OFFICIAL_Y_MM)
            width_mm = _layout_value(profile, "custom_width_mm", STAMP_STANDARD_WIDTH_MM)
            height_mm = _layout_value(profile, "custom_height_mm", STAMP_STANDARD_HEIGHT_MM)
            rotation = _layout_value(profile, "custom_rotation_deg", STAMP_OFFICIAL_ROTATION_DEG)
            width_mm = max(STAMP_MIN_WIDTH_MM, min(STAMP_MAX_WIDTH_MM, width_mm))
            # O editor trabalha como bloco sólido. A altura é sempre derivada da largura
            # para manter exatamente a proporção 85:32, inclusive abaixo de 68 mm.
            height_mm = width_mm / STAMP_STANDARD_ASPECT

        x_mm = max(5.0, min(210.0 - width_mm - 5.0, x_mm))
        y_mm = max(5.0, min(297.0 - height_mm - 5.0, y_mm))
        margin_left_mm, margin_top_mm = print_page_margins_mm or (DACTE_PRINT_PAGE_MARGIN_MM, DACTE_PRINT_PAGE_MARGIN_MM)
        print_x_mm = x_mm - max(0.0, float(margin_left_mm))
        print_y_mm = y_mm - max(0.0, float(margin_top_mm))
        style = (
            f"--central-cte-page-x:{x_mm:.2f}mm;"
            f"--central-cte-page-y:{y_mm:.2f}mm;"
            f"--central-cte-print-x:{print_x_mm:.2f}mm;"
            f"--central-cte-print-y:{print_y_mm:.2f}mm;"
            f"left:var(--central-cte-page-x);"
            f"top:var(--central-cte-page-y);"
            f"width:{width_mm:.2f}mm;"
            f"height:{height_mm:.2f}mm;"
            f"transform:rotate({max(-15.0,min(15.0,rotation)):.2f}deg);"
        )
    else:
        width_mm, height_mm = _stamp_dimensions(size)
        style = f"width:{width_mm:.2f}mm;height:{height_mm:.2f}mm;"
    solid_uri = _signature_solid_svg_data_uri(
        image_uri,
        profile.title or "REDESPACHO",
        date_text,
        _layout_value(profile, "signature_scale_percent", 100.0),
        _layout_value(profile, "signature_offset_x_mm", 0.0),
        _layout_value(profile, "signature_offset_y_mm", 0.0),
    )
    return f"""<div class="central-cte-signature central-cte-signature-{html.escape(pos)} central-cte-signature-size-{size}" style="{style}" data-central-signature="1">
<img class="central-cte-signature-solid" src="{solid_uri}" alt="Carimbo oficial de assinatura">
</div>"""


def signature_css() -> str:
    return f"""
/* {SIGNATURE_CSS_MARKER} */
.page {{ position:relative; }}
.central-cte-signature {{ position:absolute; z-index:8; text-align:center; font-family:Arial,sans-serif; color:#111; line-height:1.05; pointer-events:none; break-inside:avoid; transform-origin:center center; box-sizing:border-box; overflow:visible; }}
.central-cte-signature-custom, .central-cte-signature-reference-docs, .central-cte-signature-official-stamp {{ display:block; overflow:visible; opacity:1; }}
.central-cte-signature-solid {{ display:block; width:100%; height:100%; object-fit:fill; overflow:visible; }}
.central-cte-signature-size-small {{ width:68mm; height:25.6mm; }}
.central-cte-signature-size-medium {{ width:76mm; height:28.6mm; }}
.central-cte-signature-size-large, .central-cte-signature-size-official {{ width:85mm; height:32mm; }}
.central-cte-signature-top-left {{ top:8.5mm; left:11mm; }}
.central-cte-signature-top-right {{ top:8.5mm; right:11mm; }}
.central-cte-signature-bottom-left {{ bottom:7mm; left:11mm; }}
.central-cte-signature-bottom-right {{ bottom:7mm; right:8mm; }}
.decl-grid > .central-cte-signature-host {{ position:relative; overflow:visible; padding:0; display:flex; align-items:center; justify-content:center; box-sizing:border-box; min-height:25.6mm; }}
.central-cte-signature-stampbox {{ padding:0; border:0; box-sizing:border-box; background:transparent; margin:0 auto; display:flex; align-items:center; justify-content:center; overflow:visible; }}
.central-cte-signature-stampbox-small {{ width:68mm; height:25.6mm; }}
.central-cte-signature-stampbox-medium {{ width:76mm; height:28.6mm; }}
.central-cte-signature-stampbox-large, .central-cte-signature-stampbox-official {{ width:85mm; height:32mm; }}
.central-cte-signature-stamp {{ display:block; width:100%; height:100%; object-fit:fill; margin:0 auto; overflow:visible; }}
@media print {{
  .central-cte-signature-custom, .central-cte-signature-reference-docs, .central-cte-signature-official-stamp {{
    left:var(--central-cte-print-x, var(--central-cte-page-x)) !important;
    top:var(--central-cte-print-y, var(--central-cte-page-y)) !important;
  }}
}}
"""

def inject_signature_html(document_html: str, profile: SignatureProfile, date_text: str, processed_path: Path, position: Optional[str] = None, stamp_size: str = "official") -> str:
    if SIGNATURE_HTML_MARKER in document_html:
        return document_html
    chosen_position = position or profile.position or "official-stamp"
    if chosen_position == "signature-field":
        chosen_position = "signature-field-legacy"
    chosen_size = normalize_stamp_size(stamp_size or profile.stamp_size)
    result = document_html
    css = signature_css()
    if SIGNATURE_CSS_MARKER not in result:
        if re.search(r"</style>", result, flags=re.I):
            result = re.sub(r"</style>", css + "\n</style>", result, count=1, flags=re.I)
        else:
            result = result.replace("</head>", f"<style>{css}</style></head>", 1)
    if chosen_position == "signature-field-legacy":
        stamp_uri = _signature_stamp_data_uri(processed_path, profile.title, date_text, profile.person_name)
        stamp = (
            f'<div class="center central-cte-signature-host" data-central-signature="1">'
            f'<div class="central-cte-signature-stampbox central-cte-signature-stampbox-{chosen_size}"><img class="central-cte-signature-stamp" src="{stamp_uri}" alt="Carimbo de assinatura"></div></div>'
        )
        host_pattern = (r'<div\s+class=["\']center["\']>\s*'
                        r'<div\s+style=["\']height:30px;?["\']>\s*</div>\s*'
                        r'<div>ASSINATURA\s*/\s*CARIMBO</div>\s*</div>')
        result, count = re.subn(host_pattern, stamp, result, count=1, flags=re.I | re.S)
    else:
        image_uri = _signature_data_uri(processed_path, compact=False)
        print_margins = _extract_print_page_margins_mm(result)
        block = signature_block_html(profile, date_text, image_uri, chosen_position, chosen_size, print_margins)
        result, count = re.subn(r"(<div\s+class=[\"']page[\"'][^>]*>)", r"\1\n" + block, result, count=1, flags=re.I)
    if count == 0:
        image_uri = _signature_data_uri(processed_path, compact=False)
        print_margins = _extract_print_page_margins_mm(result)
        block = signature_block_html(profile, date_text, image_uri, chosen_position, chosen_size, print_margins)
        result, count = re.subn(r"(<div\s+class=[\"']page[\"'][^>]*>)", r"\1\n" + block, result, count=1, flags=re.I)
    if count == 0:
        result = result.replace("<body>", "<body>" + block, 1)
    return result

def _resolve_render_document(engine: Any) -> Callable[..., str]:
    """Aceita módulo, objeto-ponte ou a própria função render_document."""
    if callable(engine):
        return engine
    renderer = getattr(engine, "render_document", None) if engine is not None else None
    if callable(renderer):
        return renderer
    raise RuntimeError(
        "O renderizador do DACTE não foi conectado ao motor de assinatura. "
        "Aplique a versão 2.6.65.19.2 para usar a prévia DACTE organizada e a linha encostada na assinatura."
    )

def render_signed_html(engine: Any, info: dict[str, Any], profile: SignatureProfile, date_text: str, position: Optional[str] = None, stamp_size: str = "official") -> str:
    processed = Path(profile.processed_file)
    if not processed.exists():
        raise RuntimeError("A imagem tratada da assinatura não foi encontrada. Importe novamente a folha assinada.")
    renderer = _resolve_render_document(engine)
    base = renderer([info], with_button=False)
    return inject_signature_html(base, profile, date_text, processed, position, stamp_size)

def render_signed_batch_html(engine: Any, infos: Iterable[dict[str, Any]], profile: SignatureProfile, date_text: str, position: Optional[str] = None, stamp_size: str = "official") -> str:
    documents = [render_signed_html(engine, info, profile, date_text, position, stamp_size) for info in infos]
    if not documents:
        raise RuntimeError("Nenhum CT-e foi informado para o lote.")
    style = _extract_style(documents[0])
    bodies = [_extract_body_pages(document) for document in documents]
    return _compose_document(style, bodies, title="Lote de DACTEs assinados")
