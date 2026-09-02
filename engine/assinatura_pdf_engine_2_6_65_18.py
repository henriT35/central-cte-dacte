# -*- coding: utf-8 -*-
"""Motor modular de assinatura visual e PDF para o Central CT-e / DACTE.

Versão 2.6.65.25.0.

Este módulo atua somente sobre a representação HTML/PDF. O XML fiscal
original nunca é alterado. A integração com a tela XMLs é instalada por uma
ponte mínima no motor principal.
"""
from __future__ import annotations

import base64
import hashlib
import html
import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
except Exception:  # pragma: no cover - tratado pela interface
    Image = None
    ImageDraw = None
    ImageEnhance = None
    ImageFilter = None
    ImageFont = None
    ImageOps = None

VERSION = "2.6.65.25.0"
MODULE_TITLE = "Assinaturas e PDF"
PROFILE_FILE = "perfis_assinatura.json"
MAX_PROFILE_NAME = 80
MAX_PERSON_NAME = 120
MAX_TITLE = 60
SIGNATURE_CSS_MARKER = "central-cte-signature-css-266518"
SIGNATURE_HTML_MARKER = "data-central-signature=\"1\""

# Padrão RC6 - prévia fiel do CT-e real e redimensionamento livre do carimbo.
STAMP_STANDARD_WIDTH_MM = 85.0
STAMP_STANDARD_HEIGHT_MM = 32.0
STAMP_STANDARD_ASPECT = STAMP_STANDARD_WIDTH_MM / STAMP_STANDARD_HEIGHT_MM
STAMP_MIN_WIDTH_MM = 42.0
STAMP_MAX_WIDTH_MM = 96.0
STAMP_OFFICIAL_X_MM = 117.0
STAMP_OFFICIAL_Y_MM = 257.0
STAMP_OFFICIAL_ROTATION_DEG = 0.0
DACTE_PRINT_PAGE_MARGIN_MM = 4.0
SIGNATURE_SCALE_MIN_PERCENT = 40.0
SIGNATURE_SCALE_MAX_PERCENT = 250.0
SIGNATURE_OFFSET_LIMIT_MM = 15.0


# ---------------------------------------------------------------------------
# Utilidades puras
# ---------------------------------------------------------------------------
def _norm(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).upper().strip()


def _only_digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def _safe_filename(value: Any, fallback: str = "ARQUIVO", max_length: int = 95) -> str:
    raw = unicodedata.normalize("NFKD", str(value or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.replace("º", "").replace("ª", "")
    raw = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " ", raw)
    raw = re.sub(r"[^A-Za-z0-9._ -]+", " ", raw)
    raw = re.sub(r"[\s._-]+", "_", raw).strip("._ ")
    if not raw:
        raw = fallback
    return raw[:max_length].rstrip("._ ") or fallback


def _safe_output_component(value: Any, fallback: str = "ARQUIVO", max_length: int = 95) -> str:
    """Componente seguro para nomes exibidos ao usuário, usando espaços em vez de sublinhados."""
    raw = _safe_filename(value, fallback, max_length).replace("_", " ")
    raw = re.sub(r"\s+", " ", raw).strip(" .")
    return raw[:max_length].rstrip(" .") or fallback.replace("_", " ")


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def partner_name_from_info(info: dict[str, Any]) -> str:
    result = info.get("validacao") or info.get("validation") or {}
    emit = info.get("emit") or {}
    candidates = (
        result.get("partner_name"),
        result.get("nome_parceiro"),
        result.get("partner_id"),
        info.get("parceiro"),
        info.get("partner_name"),
        info.get("emitente"),
        emit.get("nome"),
        emit.get("fant"),
    )
    partner = _first_nonempty(*candidates)
    if not partner:
        return "PARCEIRO_NAO_IDENTIFICADO"
    if _norm(partner) in {"SEM PARCEIRO", "NAO IDENTIFICADO", "NÃO IDENTIFICADO", "-"}:
        return "PARCEIRO_NAO_IDENTIFICADO"
    return partner


def _unique_path(path: Path) -> Path:
    path = Path(path)
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def cte_output_basename(info: dict[str, Any], used: Optional[set[str]] = None) -> str:
    number = _safe_output_component(info.get("numero"), "SEM NUMERO", 28)
    partner = _safe_output_component(partner_name_from_info(info), "PARCEIRO NAO IDENTIFICADO", 72)
    base = f"CT-e {number} {partner}"
    used = used if used is not None else set()
    candidate = base
    if candidate.casefold() in used:
        series = _safe_output_component(info.get("serie"), "", 10)
        key = _only_digits(info.get("chave"))
        suffix = f" S{series}" if series else ""
        if key:
            suffix += f" {key[-8:]}"
        candidate = base + suffix
    serial = 2
    original = candidate
    while candidate.casefold() in used:
        candidate = f"{original} ({serial})"
        serial += 1
    used.add(candidate.casefold())
    return candidate


def _data_uri(path: Path) -> str:
    mime = "image/png"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _qt_core_gui():
    """Carrega o backend gráfico já empacotado com o Central CT-e."""
    core = importlib.import_module("PySide6.QtCore")
    gui = importlib.import_module("PySide6.QtGui")
    return core, gui


def _qt_enum(owner, container_name: str, value_name: str):
    container = getattr(owner, container_name, None)
    if container is not None and hasattr(container, value_name):
        return getattr(container, value_name)
    if hasattr(owner, value_name):
        return getattr(owner, value_name)
    raise AttributeError(f"Enum Qt não encontrado: {container_name}.{value_name}")


def image_backend_status() -> tuple[str, str]:
    """Retorna o backend disponível sem exigir instalação manual de pacotes."""
    if Image is not None:
        return "Pillow", "Tratamento avançado disponível"
    try:
        _qt_core_gui()
        return "Qt", "Modo compatível interno disponível (Pillow não é necessária)"
    except Exception:
        return "Indisponível", "Os componentes gráficos do programa não foram localizados"


def _qimage_memory(image):
    pointer = image.bits()
    try:
        pointer.setsize(image.sizeInBytes())
    except Exception:
        pass
    return memoryview(pointer).cast("B")


def _qt_image_png_bytes(image) -> bytes:
    core, _ = _qt_core_gui()
    array = core.QByteArray()
    buffer = core.QBuffer(array)
    mode = getattr(getattr(core.QIODevice, "OpenModeFlag", core.QIODevice), "WriteOnly")
    if not buffer.open(mode):
        raise RuntimeError("Não foi possível criar a imagem temporária da assinatura.")
    if not image.save(buffer, "PNG"):
        raise RuntimeError("O backend Qt não conseguiu salvar a assinatura em PNG.")
    buffer.close()
    return bytes(array)


def _qt_load_qimage(path: Path, max_side: int = 2600):
    """Lê imagem ou a primeira página de PDF usando os plugins do Qt do EXE."""
    core, gui = _qt_core_gui()
    reader = gui.QImageReader(str(path))
    try:
        reader.setAutoTransform(True)
    except Exception:
        pass
    if not reader.canRead():
        message = reader.errorString() or "formato não reconhecido pelo Qt"
        raise RuntimeError(f"Não foi possível ler o arquivo pelo modo compatível: {message}")
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > 0:
        scale = min(1.0, max_side / max(size.width(), size.height()))
        # PDF costuma informar o tamanho em pontos. Amplia a primeira página para
        # manter os traços da caneta nítidos durante o recorte.
        if path.suffix.lower() == ".pdf" and max(size.width(), size.height()) < 1800:
            scale = min(max_side / max(size.width(), size.height()), 2.8)
        if abs(scale - 1.0) > 0.01:
            reader.setScaledSize(core.QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale))))
    image = reader.read()
    if image.isNull():
        raise RuntimeError(reader.errorString() or "O Qt retornou uma imagem vazia.")
    rgba_format = _qt_enum(gui.QImage, "Format", "Format_RGBA8888")
    return image.convertToFormat(rgba_format)


def _signature_data_uri(path: Path, compact: bool = False) -> str:
    """Normaliza a proporção da assinatura para evitar cortes entre renderizadores."""
    target = (680, 100) if compact else (680, 220)
    if Image is not None:
        with Image.open(path) as source:
            image = source.convert("RGBA")
            image.thumbnail(target, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", target, (255, 255, 255, 0))
            x = (target[0] - image.width) // 2
            y = (target[1] - image.height) // 2
            canvas.alpha_composite(image, (x, y))
            stream = io.BytesIO()
            canvas.save(stream, "PNG", optimize=True)
        return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")
    try:
        core, gui = _qt_core_gui()
        source = _qt_load_qimage(path, max_side=max(target))
        aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
        smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
        scaled = source.scaled(target[0], target[1], aspect, smooth)
        canvas_format = _qt_enum(gui.QImage, "Format", "Format_ARGB32_Premultiplied")
        canvas = gui.QImage(target[0], target[1], canvas_format)
        canvas.fill(getattr(getattr(core.Qt, "GlobalColor", core.Qt), "transparent"))
        painter = gui.QPainter(canvas)
        painter.setRenderHint(gui.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage((target[0] - scaled.width()) // 2, (target[1] - scaled.height()) // 2, scaled)
        painter.end()
        return "data:image/png;base64," + base64.b64encode(_qt_image_png_bytes(canvas)).decode("ascii")
    except Exception:
        return _data_uri(path)


def _signature_stamp_data_uri(path: Path, title: str, date_text: str, person_name: str = "") -> str:
    """Monta o carimbo oficial 85 x 32 mm com assinatura grande sobre a linha.

    O bloco é produzido como uma imagem única para impedir que Edge/Chrome,
    Qt ou a impressora alterem separadamente título, data, linha e assinatura.
    """
    safe_title = str(title or "REDESPACHO").upper()[:34]
    safe_date = str(date_text or "")[:20]
    width, height = 1000, 376

    if Image is None or ImageDraw is None:
        try:
            core, gui = _qt_core_gui()
            canvas_format = _qt_enum(gui.QImage, "Format", "Format_ARGB32_Premultiplied")
            canvas = gui.QImage(width, height, canvas_format)
            canvas.fill(getattr(getattr(core.Qt, "GlobalColor", core.Qt), "transparent"))
            painter = gui.QPainter(canvas)
            painter.setRenderHint(gui.QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(gui.QPainter.RenderHint.SmoothPixmapTransform, True)
            black = gui.QColor(18, 18, 18)

            border_pen = gui.QPen(black)
            border_pen.setWidth(5)
            painter.setPen(border_pen)
            painter.drawRect(7, 7, width - 14, height - 14)

            align = (
                getattr(getattr(core.Qt, "AlignmentFlag", core.Qt), "AlignHCenter")
                | getattr(getattr(core.Qt, "AlignmentFlag", core.Qt), "AlignVCenter")
            )
            title_font = gui.QFont("Arial", 66)
            title_font.setBold(True)
            painter.setFont(title_font)
            painter.drawText(core.QRect(30, 24, width - 60, 82), align, safe_title)

            if safe_date:
                date_font = gui.QFont("Arial", 38)
                date_font.setBold(True)
                painter.setFont(date_font)
                painter.drawText(core.QRect(30, 96, width - 60, 58), align, safe_date)

            label_font = gui.QFont("Arial", 42)
            label_font.setBold(True)
            painter.setFont(label_font)
            painter.drawText(core.QRect(34, 267, 150, 70), align, "Ass:")

            line_pen = gui.QPen(black)
            line_pen.setWidth(4)
            painter.setPen(line_pen)
            painter.drawLine(160, 313, 955, 313)

            signature = _qt_load_qimage(path, max_side=1800)
            aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
            smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
            signature = signature.scaled(790, 220, aspect, smooth)
            x = 165 + max(0, (790 - signature.width()) // 2)
            # A assinatura toca/sobrepõe a linha, como num carimbo real.
            y = 128 + max(0, (204 - signature.height()) // 2)
            painter.drawImage(x, y, signature)
            painter.end()
            return "data:image/png;base64," + base64.b64encode(_qt_image_png_bytes(canvas)).decode("ascii")
        except Exception:
            return _signature_data_uri(path, compact=False)

    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)

    def load_font(size: int, bold: bool = False):
        candidates = []
        if os.name == "nt":
            windir = Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts"
            candidates.extend([
                windir / ("arialbd.ttf" if bold else "arial.ttf"),
                windir / "calibrib.ttf",
                windir / "calibri.ttf",
            ])
        candidates.extend([
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ])
        if ImageFont is not None:
            for candidate in candidates:
                try:
                    if candidate.exists():
                        return ImageFont.truetype(str(candidate), size=size)
                except Exception:
                    pass
            try:
                return ImageFont.load_default(size=size)
            except TypeError:
                return ImageFont.load_default()
        return None

    title_font = load_font(88, bold=True)
    date_font = load_font(48, bold=True)
    label_font = load_font(52, bold=True)

    draw.rectangle((7, 7, width - 8, height - 8), outline=(18, 18, 18, 255), width=5)
    title_bbox = draw.textbbox((0, 0), safe_title, font=title_font) if hasattr(draw, "textbbox") else (0, 0, len(safe_title) * 44, 88)
    draw.text(((width - (title_bbox[2] - title_bbox[0])) // 2, 18), safe_title, fill=(18, 18, 18, 255), font=title_font)

    if safe_date:
        date_bbox = draw.textbbox((0, 0), safe_date, font=date_font) if hasattr(draw, "textbbox") else (0, 0, len(safe_date) * 24, 48)
        draw.text(((width - (date_bbox[2] - date_bbox[0])) // 2, 100), safe_date, fill=(18, 18, 18, 255), font=date_font)

    draw.text((34, 267), "Ass:", fill=(18, 18, 18, 255), font=label_font)
    draw.line((160, 313, 955, 313), fill=(18, 18, 18, 255), width=4)

    with Image.open(path) as source:
        signature = source.convert("RGBA")
        signature.thumbnail((790, 220), Image.Resampling.LANCZOS)
        x = 165 + max(0, (790 - signature.width) // 2)
        y = 128 + max(0, (204 - signature.height) // 2)
        canvas.alpha_composite(signature, (x, y))

    stream = io.BytesIO()
    canvas.save(stream, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")

def _extract_body_pages(document_html: str) -> str:
    match = re.search(r"<body[^>]*>(.*?)</body>", document_html, flags=re.I | re.S)
    body = match.group(1) if match else document_html
    body = re.sub(r"<div\s+class=[\"']printbar[\"'][^>]*>.*?</div>", "", body, flags=re.I | re.S)
    return body.strip()


def _extract_style(document_html: str) -> str:
    match = re.search(r"<style[^>]*>(.*?)</style>", document_html, flags=re.I | re.S)
    return match.group(1) if match else ""


def _compose_document(style: str, bodies: Iterable[str], title: str = "DACTE em PDF") -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>{style}</style>
</head>
<body>
{''.join(bodies)}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Perfis de assinatura
# ---------------------------------------------------------------------------
@dataclass
class SignatureProfile:
    id: str
    name: str
    person_name: str
    role: str = ""
    title: str = "REDESPACHO"
    position: str = "official-stamp"
    active: bool = True
    created_at: str = ""
    updated_at: str = ""
    original_file: str = ""
    processed_file: str = ""
    original_sha256: str = ""
    threshold: int = 242
    stamp_size: str = "official"
    custom_x_mm: float = STAMP_OFFICIAL_X_MM
    custom_y_mm: float = STAMP_OFFICIAL_Y_MM
    custom_width_mm: float = STAMP_STANDARD_WIDTH_MM
    custom_height_mm: float = STAMP_STANDARD_HEIGHT_MM
    custom_rotation_deg: float = STAMP_OFFICIAL_ROTATION_DEG
    signature_scale_percent: float = 100.0
    signature_offset_x_mm: float = 0.0
    signature_offset_y_mm: float = 0.0
    last_used_at: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.processed_file)


class SignatureProfileStore:
    def __init__(self, runtime_dir: Path):
        self.runtime_dir = Path(runtime_dir)
        self.root = self.runtime_dir / "sessoes" / "assinaturas"
        self.originals = self.root / "originais"
        self.processed = self.root / "tratadas"
        self.sheets = self.root / "folhas_cadastro"
        self.logs = self.runtime_dir / "logs"
        for folder in (self.root, self.originals, self.processed, self.sheets, self.logs):
            folder.mkdir(parents=True, exist_ok=True)
        self.path = self.root / PROFILE_FILE

    def load(self) -> list[SignatureProfile]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            items = raw.get("profiles", raw if isinstance(raw, list) else [])
            result = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                allowed = {field for field in SignatureProfile.__dataclass_fields__}
                data = {key: value for key, value in item.items() if key in allowed}
                profile = SignatureProfile(**data)
                # Migração transparente dos perfis antigos, que usavam 40 x 20 mm
                # e deixavam a assinatura quase invisível na impressão.
                if float(getattr(profile, "custom_width_mm", 0.0) or 0.0) < STAMP_MIN_WIDTH_MM:
                    profile.custom_width_mm = STAMP_STANDARD_WIDTH_MM
                    profile.custom_height_mm = STAMP_STANDARD_HEIGHT_MM
                    if float(getattr(profile, "custom_x_mm", 0.0) or 0.0) > 125.0:
                        profile.custom_x_mm = STAMP_OFFICIAL_X_MM
                    if abs(float(getattr(profile, "custom_y_mm", 0.0) or 0.0) - 199.0) < 0.01:
                        profile.custom_y_mm = STAMP_OFFICIAL_Y_MM
                    if abs(float(getattr(profile, "custom_rotation_deg", 0.0) or 0.0) + 15.0) < 0.01:
                        profile.custom_rotation_deg = STAMP_OFFICIAL_ROTATION_DEG
                if str(getattr(profile, "stamp_size", "") or "").lower() in {"small", "medium", "large", ""}:
                    profile.stamp_size = "official"
                profile.signature_scale_percent = max(
                    SIGNATURE_SCALE_MIN_PERCENT,
                    min(SIGNATURE_SCALE_MAX_PERCENT, float(getattr(profile, "signature_scale_percent", 100.0) or 100.0)),
                )
                profile.signature_offset_x_mm = max(
                    -SIGNATURE_OFFSET_LIMIT_MM,
                    min(SIGNATURE_OFFSET_LIMIT_MM, float(getattr(profile, "signature_offset_x_mm", 0.0) or 0.0)),
                )
                profile.signature_offset_y_mm = max(
                    -SIGNATURE_OFFSET_LIMIT_MM,
                    min(SIGNATURE_OFFSET_LIMIT_MM, float(getattr(profile, "signature_offset_y_mm", 0.0) or 0.0)),
                )
                result.append(profile)
            return result
        except Exception:
            self._log_error("Falha ao ler perfis de assinatura", traceback.format_exc())
            return []

    def save(self, profiles: Iterable[SignatureProfile]) -> None:
        payload = {
            "version": VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "profiles": [asdict(profile) for profile in profiles],
        }
        _atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    def get(self, profile_id: str) -> Optional[SignatureProfile]:
        for profile in self.load():
            if profile.id == profile_id:
                return profile
        return None

    def upsert(self, profile: SignatureProfile) -> SignatureProfile:
        profiles = self.load()
        now = datetime.now().isoformat(timespec="seconds")
        if not profile.created_at:
            profile.created_at = now
        profile.updated_at = now
        replaced = False
        for index, current in enumerate(profiles):
            if current.id == profile.id:
                profiles[index] = profile
                replaced = True
                break
        if not replaced:
            profiles.append(profile)
        self.save(profiles)
        return profile

    def delete(self, profile_id: str) -> bool:
        profiles = self.load()
        target = next((profile for profile in profiles if profile.id == profile_id), None)
        if target is None:
            return False
        remaining = [profile for profile in profiles if profile.id != profile_id]
        self.save(remaining)
        for value in (target.original_file, target.processed_file):
            if not value:
                continue
            try:
                path = Path(value)
                if path.exists() and self.root in path.resolve().parents:
                    path.unlink()
            except Exception:
                pass
        return True

    def create_profile(self, name: str, person_name: str, role: str, title: str, position: str) -> SignatureProfile:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        token = hashlib.sha1(f"{name}|{person_name}|{time.time_ns()}".encode("utf-8")).hexdigest()[:7].upper()
        profile_id = f"ASS-{stamp[-8:]}-{token}"
        return self.upsert(SignatureProfile(
            id=profile_id,
            name=str(name or "Assinatura").strip()[:MAX_PROFILE_NAME],
            person_name=str(person_name or "").strip()[:MAX_PERSON_NAME],
            role=str(role or "").strip()[:MAX_PERSON_NAME],
            title=str(title or "REDESPACHO").strip()[:MAX_TITLE],
            position=position or "official-stamp",
        ))

    def _log_error(self, context: str, details: str) -> None:
        try:
            path = self.logs / f"assinatura_pdf_erros_{datetime.now():%Y%m%d}.txt"
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"\n[{datetime.now():%d/%m/%Y %H:%M:%S}] {context}\n{details}\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Folha de cadastro e tratamento de imagem
# ---------------------------------------------------------------------------
def registration_sheet_html(profile: SignatureProfile) -> str:
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Cadastro de assinatura {html.escape(profile.id)}</title>
<style>
@page {{ size:A4 portrait; margin:12mm; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font-family:Arial,sans-serif; color:#111; }}
.sheet {{ width:186mm; min-height:273mm; padding:8mm; border:1px solid #bbb; }}
h1 {{ font-size:20px; margin:0 0 8mm; text-align:center; }}
.meta {{ display:grid; grid-template-columns:34mm 1fr; gap:3mm 4mm; font-size:12px; margin-bottom:9mm; }}
.meta b {{ text-transform:uppercase; font-size:10px; }}
.instructions {{ font-size:13px; line-height:1.45; padding:5mm; background:#f5f7fa; border-left:4px solid #0b4f9f; margin-bottom:10mm; }}
.signature-frame {{ position:relative; width:150mm; height:58mm; margin:0 auto; border:2px solid #111; background:#fff; }}
.corner {{ position:absolute; width:12mm; height:12mm; }}
.c1 {{ left:-2px; top:-2px; border-left:6px solid #111; border-top:6px solid #111; }}
.c2 {{ right:-2px; top:-2px; border-right:6px solid #111; border-top:6px solid #111; }}
.c3 {{ left:-2px; bottom:-2px; border-left:6px solid #111; border-bottom:6px solid #111; }}
.c4 {{ right:-2px; bottom:-2px; border-right:6px solid #111; border-bottom:6px solid #111; }}
.frame-label {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#d6d6d6; font-size:21px; letter-spacing:2px; font-weight:bold; }}
.code {{ margin-top:7mm; text-align:center; font:700 13px monospace; letter-spacing:1px; }}
.warning {{ margin-top:12mm; font-size:11px; line-height:1.4; }}
</style></head><body><div class="sheet">
<h1>CADASTRO DE ASSINATURA - CENTRAL CT-e</h1>
<div class="meta">
<b>Perfil</b><span>{html.escape(profile.name)}</span>
<b>Responsável</b><span>{html.escape(profile.person_name)}</span>
<b>Cargo / setor</b><span>{html.escape(profile.role or '-')}</span>
<b>Título no documento</b><span>{html.escape(profile.title or '-')}</span>
</div>
<div class="instructions"><b>Como preencher:</b> imprima esta folha em tamanho A4, assine dentro do quadro usando caneta azul ou preta e depois digitalize a página inteira em PDF, JPG ou PNG. Não encoste a assinatura nas bordas.</div>
<div class="signature-frame" data-registration-box="1">
<div class="corner c1"></div><div class="corner c2"></div><div class="corner c3"></div><div class="corner c4"></div>
</div>
<div class="code">CÓDIGO DO CADASTRO: {html.escape(profile.id)}</div>
<div class="warning">A imagem tratada será utilizada somente na representação HTML/PDF do DACTE. O XML fiscal autorizado não será modificado.</div>
</div></body></html>"""


def _load_image(path: Path):
    suffix = path.suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp", ".pdf"}:
        raise RuntimeError("Formato não suportado. Use PDF, JPG, JPEG ou PNG.")
    if Image is not None:
        if suffix != ".pdf":
            with Image.open(path) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
        return render_pdf_first_page(path)
    # O EXE já possui PySide6 e o plugin qpdf. Este caminho elimina a
    # necessidade de instalar Pillow na máquina do usuário.
    return _qt_load_qimage(path)


def render_pdf_first_page(path: Path):
    errors: list[str] = []
    if Image is not None:
        try:
            pdfium = importlib.import_module("pypdfium2")
            document = pdfium.PdfDocument(str(path))
            page = document[0]
            bitmap = page.render(scale=2.4)
            image = bitmap.to_pil().convert("RGB")
            page.close()
            document.close()
            return image
        except Exception as exc:
            errors.append(f"PDFium: {exc}")

        try:
            fitz = importlib.import_module("fitz")
            document = fitz.open(str(path))
            page = document.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2.4, 2.4), alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            document.close()
            return image
        except Exception as exc:
            errors.append(f"PyMuPDF: {exc}")

    try:
        qimage = _qt_load_qimage(path)
        if Image is None:
            return qimage
        return Image.open(io.BytesIO(_qt_image_png_bytes(qimage))).convert("RGB")
    except Exception as exc:
        errors.append(f"Qt/qpdf: {exc}")

    if Image is not None:
        try:
            browser = find_browser()
            if browser:
                with tempfile.TemporaryDirectory(prefix="cte_pdf_page_") as tmp:
                    output = Path(tmp) / "pagina.png"
                    user_data = Path(tmp) / "perfil"
                    command = [
                        str(browser), "--headless=new", "--disable-gpu", "--disable-extensions",
                        "--hide-scrollbars", f"--user-data-dir={user_data}",
                        "--window-size=1654,2339", f"--screenshot={output}", path.resolve().as_uri(),
                    ]
                    if os.name != "nt":
                        command.insert(1, "--no-sandbox")
                    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, creationflags=_no_window_flags())
                    if process.returncode == 0 and output.exists():
                        with Image.open(output) as image:
                            return image.convert("RGB")
                    errors.append("Edge/Chrome não gerou a imagem da primeira página")
        except Exception as exc:
            errors.append(f"Edge/Chrome: {exc}")

    raise RuntimeError("Não foi possível ler a primeira página do PDF. " + " | ".join(errors[-3:]))


def _clusters(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    groups: list[tuple[int, int]] = []
    start = previous = values[0]
    for value in values[1:]:
        if value <= previous + 3:
            previous = value
            continue
        groups.append((start, previous))
        start = previous = value
    groups.append((start, previous))
    return groups


def _dark_mask_counts(image, threshold: int = 105):
    if Image is not None and hasattr(image, "convert"):
        gray = ImageOps.grayscale(image)
        width, height = gray.size
        pixels = gray.load()
        row_counts = [0] * height
        col_counts = [0] * width
        for y in range(height):
            count = 0
            for x in range(width):
                if pixels[x, y] < threshold:
                    count += 1
                    col_counts[x] += 1
            row_counts[y] = count
        return row_counts, col_counts
    _, gui = _qt_core_gui()
    gray_format = _qt_enum(gui.QImage, "Format", "Format_Grayscale8")
    gray = image.convertToFormat(gray_format)
    width, height = gray.width(), gray.height()
    data = _qimage_memory(gray)
    stride = gray.bytesPerLine()
    row_counts = [0] * height
    col_counts = [0] * width
    for y in range(height):
        base = y * stride
        count = 0
        for x in range(width):
            if data[base + x] < threshold:
                count += 1
                col_counts[x] += 1
        row_counts[y] = count
    return row_counts, col_counts


def _image_dimensions(image) -> tuple[int, int]:
    """Retorna largura e altura para Pillow ou QImage sem depender do backend."""
    if Image is not None and hasattr(image, "size") and not hasattr(image, "isNull"):
        return int(image.size[0]), int(image.size[1])
    return int(image.width()), int(image.height())


def _template_registration_box(image) -> Optional[tuple[int, int, int, int]]:
    """Fallback geométrico para a folha A4 gerada pelo próprio programa.

    A folha possui posição fixa do quadro. Este caminho é usado quando uma
    digitalização suaviza/clareia as linhas a ponto de o detector não enxergá-las.
    O recorte corresponde à área interna do quadro, sem cabeçalho, código ou rodapé.
    """
    width, height = _image_dimensions(image)
    if width < 500 or height < 700:
        return None
    ratio = width / max(1, height)
    # A4 retrato, incluindo pequenas variações de scanner e margens.
    if not (0.62 <= ratio <= 0.80):
        return None
    left = int(round(width * 0.165))
    right = int(round(width * 0.835))
    top = int(round(height * 0.335))
    bottom = int(round(height * 0.515))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _detect_registration_box_details(image) -> tuple[Optional[tuple[int, int, int, int]], str]:
    """Localiza o quadro por linhas e retorna também o método utilizado."""
    use_pillow = Image is not None and hasattr(image, "copy") and not hasattr(image, "isNull")
    max_side = 1800
    scale = 1.0
    if use_pillow:
        work = image.copy().convert("RGB")
        if max(work.size) > max_side:
            scale = max_side / max(work.size)
            work.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        width, height = work.size
    else:
        core, _ = _qt_core_gui()
        work = image.copy()
        width, height = work.width(), work.height()
        if max(width, height) > max_side:
            scale = max_side / max(width, height)
            aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
            smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
            work = work.scaled(max_side, max_side, aspect, smooth)
            width, height = work.width(), work.height()

    # Digitalizações e o plugin PDF do Qt podem suavizar linhas pretas. Testa
    # limiares progressivos, em vez de depender apenas de preto quase puro.
    all_candidates: list[tuple[float, int, int, int, int]] = []
    for threshold in (105, 135, 165, 195, 220):
        row_counts, col_counts = _dark_mask_counts(work, threshold=threshold)
        row_min = int(width * 0.34)
        col_min = int(height * 0.055)
        strong_rows = [index for index, value in enumerate(row_counts) if value >= row_min]
        strong_cols = [index for index, value in enumerate(col_counts) if value >= col_min]
        if len(strong_rows) < 2 or len(strong_cols) < 2:
            continue
        row_groups = _clusters(strong_rows)
        col_groups = _clusters(strong_cols)
        for top_group in row_groups:
            for bottom_group in row_groups:
                top = int(sum(top_group) / 2)
                bottom = int(sum(bottom_group) / 2)
                box_h = bottom - top
                if box_h < height * 0.10 or box_h > height * 0.34:
                    continue
                for left_group in col_groups:
                    for right_group in col_groups:
                        left = int(sum(left_group) / 2)
                        right = int(sum(right_group) / 2)
                        box_w = right - left
                        if box_w < width * 0.48 or box_w > width * 0.92:
                            continue
                        ratio = box_w / max(1, box_h)
                        if ratio < 1.8 or ratio > 5.4:
                            continue
                        width_ratio = box_w / max(1, width)
                        height_ratio = box_h / max(1, height)
                        center_y = ((top + bottom) / 2) / max(1, height)
                        center_x = ((left + right) / 2) / max(1, width)
                        # Geometria esperada do quadro: ~72% da largura, ~20%
                        # da altura e centralizado horizontalmente na metade superior.
                        penalty = (
                            abs(width_ratio - 0.72) * 5200
                            + abs(height_ratio - 0.20) * 6800
                            + abs(center_y - 0.425) * 4200
                            + abs(center_x - 0.50) * 1800
                            + threshold * 0.08
                        )
                        # O tamanho absoluto não pode dominar a escolha, pois
                        # blocos de instrução acima do quadro podem formar um
                        # retângulo maior. Prioriza a geometria conhecida da folha.
                        score = -penalty
                        all_candidates.append((score, left, top, right, bottom))
        if all_candidates and threshold <= 165:
            # Em geral o primeiro conjunto confiável já representa as linhas reais.
            break

    if all_candidates:
        _, left, top, right, bottom = max(all_candidates)
        pad_x = max(8, int((right - left) * 0.055))
        pad_y = max(8, int((bottom - top) * 0.13))
        left, right = left + pad_x, right - pad_x
        top, bottom = top + pad_y, bottom - pad_y
        if right > left and bottom > top:
            inverse = 1.0 / scale
            box = tuple(int(round(value * inverse)) for value in (left, top, right, bottom))
            return box, "quadro da folha localizado automaticamente"

    template = _template_registration_box(image)
    if template:
        return template, "quadro localizado pela posição padrão da folha de cadastro"
    return None, ""


def detect_registration_box(image) -> Optional[tuple[int, int, int, int]]:
    """API pública: retorna somente o retângulo localizado."""
    return _detect_registration_box_details(image)[0]


def _crop_to_nonwhite(image, threshold: int = 248, padding: int = 18):
    if Image is not None and not hasattr(image, "isNull"):
        gray = ImageOps.grayscale(image)
        mask = gray.point(lambda p: 255 if p < threshold else 0)
        bbox = mask.getbbox()
        if not bbox:
            return image.copy()
        left, top, right, bottom = bbox
        return image.crop((max(0, left - padding), max(0, top - padding), min(image.width, right + padding), min(image.height, bottom + padding)))
    core, gui = _qt_core_gui()
    gray_format = _qt_enum(gui.QImage, "Format", "Format_Grayscale8")
    gray = image.convertToFormat(gray_format)
    data = _qimage_memory(gray)
    stride = gray.bytesPerLine()
    left, top, right, bottom = gray.width(), gray.height(), -1, -1
    for y in range(gray.height()):
        base = y * stride
        for x in range(gray.width()):
            if data[base + x] < threshold:
                left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
    if right < left or bottom < top:
        return image.copy()
    rect = core.QRect(max(0, left - padding), max(0, top - padding), min(image.width() - max(0, left - padding), right - left + 1 + padding * 2), min(image.height() - max(0, top - padding), bottom - top + 1 + padding * 2))
    return image.copy(rect)


def _clear_edge_frame_pillow(rgba) -> None:
    """Remove restos das linhas-guia do formulário sem tocar no miolo."""
    pixels = rgba.load()
    width, height = rgba.size
    edge_x = max(4, int(width * 0.14))
    edge_y = max(4, int(height * 0.16))
    strong_cols = []
    for x in list(range(edge_x)) + list(range(max(edge_x, width - edge_x), width)):
        if sum(1 for y in range(height) if pixels[x, y][3] > 30) >= height * 0.42:
            strong_cols.append(x)
    strong_rows = []
    for y in list(range(edge_y)) + list(range(max(edge_y, height - edge_y), height)):
        if sum(1 for x in range(width) if pixels[x, y][3] > 30) >= width * 0.42:
            strong_rows.append(y)
    for x in strong_cols:
        for xx in range(max(0, x - 3), min(width, x + 4)):
            for y in range(height):
                red, green, blue, _ = pixels[xx, y]
                pixels[xx, y] = (red, green, blue, 0)
    for y in strong_rows:
        for yy in range(max(0, y - 3), min(height, y + 4)):
            for x in range(width):
                red, green, blue, _ = pixels[x, yy]
                pixels[x, yy] = (red, green, blue, 0)
    # As marcas grossas do formulário ficam encostadas às bordas. A folha
    # orienta o usuário a não assinar nessa margem, então ela pode ser limpa
    # integralmente sem reduzir o traço útil.
    strip_x = max(3, int(width * 0.045))
    strip_y = max(3, int(height * 0.055))
    for y in range(height):
        for x in list(range(strip_x)) + list(range(max(strip_x, width - strip_x), width)):
            red, green, blue, _ = pixels[x, y]
            pixels[x, y] = (red, green, blue, 0)
    for y in list(range(strip_y)) + list(range(max(strip_y, height - strip_y), height)):
        for x in range(width):
            red, green, blue, _ = pixels[x, y]
            pixels[x, y] = (red, green, blue, 0)


def _clear_edge_frame_qt(rgba, data, stride: int) -> None:
    width, height = rgba.width(), rgba.height()
    edge_x = max(4, int(width * 0.14))
    edge_y = max(4, int(height * 0.16))
    strong_cols = []
    for x in list(range(edge_x)) + list(range(max(edge_x, width - edge_x), width)):
        count = 0
        for y in range(height):
            if data[y * stride + x * 4 + 3] > 30:
                count += 1
        if count >= height * 0.42:
            strong_cols.append(x)
    strong_rows = []
    for y in list(range(edge_y)) + list(range(max(edge_y, height - edge_y), height)):
        base = y * stride
        count = sum(1 for x in range(width) if data[base + x * 4 + 3] > 30)
        if count >= width * 0.42:
            strong_rows.append(y)
    for x in strong_cols:
        for xx in range(max(0, x - 3), min(width, x + 4)):
            for y in range(height):
                data[y * stride + xx * 4 + 3] = 0
    for y in strong_rows:
        for yy in range(max(0, y - 3), min(height, y + 4)):
            base = yy * stride
            for x in range(width):
                data[base + x * 4 + 3] = 0
    strip_x = max(3, int(width * 0.045))
    strip_y = max(3, int(height * 0.055))
    for y in range(height):
        base = y * stride
        for x in list(range(strip_x)) + list(range(max(strip_x, width - strip_x), width)):
            data[base + x * 4 + 3] = 0
    for y in list(range(strip_y)) + list(range(max(strip_y, height - strip_y), height)):
        base = y * stride
        for x in range(width):
            data[base + x * 4 + 3] = 0


def _process_signature_qt(source: Path, output: Path, threshold: int) -> dict[str, Any]:
    core, gui = _qt_core_gui()
    image = _qt_load_qimage(source)
    box, detection = _detect_registration_box_details(image)
    if box:
        left, top, right, bottom = box
        cropped = image.copy(core.QRect(left, top, max(1, right - left), max(1, bottom - top)))
        detection = f"{detection} (modo Qt)"
    else:
        cropped = _crop_to_nonwhite(image, threshold=250, padding=max(12, int(min(image.width(), image.height()) * 0.01)))
        detection = "quadro não localizado; utilizada a área com conteúdo (modo Qt)"
    if max(cropped.width(), cropped.height()) > 1800:
        aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
        smooth = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
        cropped = cropped.scaled(1800, 1800, aspect, smooth)
    rgba_format = _qt_enum(gui.QImage, "Format", "Format_RGBA8888")
    rgba = cropped.convertToFormat(rgba_format)
    data = _qimage_memory(rgba)
    stride = rgba.bytesPerLine()
    threshold = max(205, min(252, int(threshold)))
    softness = max(6, 255 - threshold)
    left, top, right, bottom = rgba.width(), rgba.height(), -1, -1
    for y in range(rgba.height()):
        base = y * stride
        for x in range(rgba.width()):
            offset = base + x * 4
            red, green, blue = int(data[offset]), int(data[offset + 1]), int(data[offset + 2])
            # Contraste leve equivalente ao backend Pillow.
            red = max(0, min(255, int((red - 128) * 1.12 + 128)))
            green = max(0, min(255, int((green - 128) * 1.12 + 128)))
            blue = max(0, min(255, int((blue - 128) * 1.12 + 128)))
            light, minimum = max(red, green, blue), min(red, green, blue)
            if light >= threshold and minimum >= threshold - 10:
                alpha = 0
            else:
                luminance = int(0.2126 * red + 0.7152 * green + 0.0722 * blue)
                alpha = max(0, min(255, int((255 - luminance) * (255 / max(1, softness)))))
                if light - minimum > 18:
                    alpha = max(alpha, 170)
                alpha = max(alpha, 38 if luminance < 225 else 0)
            data[offset], data[offset + 1], data[offset + 2], data[offset + 3] = red, green, blue, alpha
            if alpha > 0:
                left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
    _clear_edge_frame_qt(rgba, data, stride)
    left, top, right, bottom = rgba.width(), rgba.height(), -1, -1
    for y in range(rgba.height()):
        base = y * stride
        for x in range(rgba.width()):
            if data[base + x * 4 + 3] > 0:
                left, top, right, bottom = min(left, x), min(top, y), max(right, x), max(bottom, y)
    if right < left or bottom < top:
        raise RuntimeError("Nenhum traço de assinatura foi encontrado após a remoção do fundo.")
    pad = max(8, int(min(rgba.width(), rgba.height()) * 0.025))
    crop_left, crop_top = max(0, left - pad), max(0, top - pad)
    final = rgba.copy(core.QRect(crop_left, crop_top, min(rgba.width() - crop_left, right - left + 1 + pad * 2), min(rgba.height() - crop_top, bottom - top + 1 + pad * 2)))
    output.parent.mkdir(parents=True, exist_ok=True)
    if not final.save(str(output), "PNG"):
        raise RuntimeError("O modo compatível Qt não conseguiu salvar a assinatura tratada.")
    return {
        "source": str(source), "output": str(output), "width": final.width(), "height": final.height(),
        "threshold": threshold, "detection": detection, "backend": "Qt",
        "source_sha256": _sha256_file(source), "output_sha256": _sha256_file(output),
    }


def process_signature_image(source: Path, output: Path, threshold: int = 242) -> dict[str, Any]:
    """Recorta o quadro e transforma o fundo claro em transparência."""
    if Image is None:
        return _process_signature_qt(Path(source), Path(output), threshold)
    image = _load_image(Path(source))
    box, detection = _detect_registration_box_details(image)
    if box:
        cropped = image.crop(box)
    else:
        cropped = _crop_to_nonwhite(image, threshold=250, padding=max(12, int(min(image.size) * 0.01)))
        detection = "quadro não localizado; utilizada a área com conteúdo"
    cropped = ImageOps.exif_transpose(cropped).convert("RGB")
    cropped = ImageEnhance.Contrast(cropped).enhance(1.12)
    if max(cropped.size) > 1800:
        cropped.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    rgba = cropped.convert("RGBA")
    pixels = rgba.load()
    threshold = max(205, min(252, int(threshold)))
    softness = max(6, 255 - threshold)
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, _ = pixels[x, y]
            light, minimum = max(red, green, blue), min(red, green, blue)
            if light >= threshold and minimum >= threshold - 10:
                alpha = 0
            else:
                luminance = int(0.2126 * red + 0.7152 * green + 0.0722 * blue)
                alpha = max(0, min(255, int((255 - luminance) * (255 / max(1, softness)))))
                if light - minimum > 18:
                    alpha = max(alpha, 170)
                alpha = max(alpha, 38 if luminance < 225 else 0)
            pixels[x, y] = (red, green, blue, alpha)
    _clear_edge_frame_pillow(rgba)
    bbox = rgba.getchannel("A").getbbox()
    if not bbox:
        raise RuntimeError("Nenhum traço de assinatura foi encontrado após a remoção do fundo.")
    left, top, right, bottom = bbox
    pad = max(8, int(min(rgba.size) * 0.025))
    rgba = rgba.crop((max(0, left - pad), max(0, top - pad), min(rgba.width, right + pad), min(rgba.height, bottom + pad)))
    output.parent.mkdir(parents=True, exist_ok=True)
    rgba.save(output, "PNG", optimize=True)
    return {
        "source": str(source), "output": str(output), "width": rgba.width, "height": rgba.height,
        "threshold": threshold, "detection": detection, "backend": "Pillow",
        "source_sha256": _sha256_file(Path(source)), "output_sha256": _sha256_file(output),
    }


# ---------------------------------------------------------------------------
# Assinatura no HTML
# ---------------------------------------------------------------------------
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
    """Retorna margem esquerda e superior da regra @page usada pelo PDF final.

    As coordenadas salvas pelo editor são físicas na folha A4. O Chromium,
    porém, posiciona o elemento .page dentro da margem de impressão. Esta
    função lê essa margem para que o HTML converta coordenadas físicas em
    coordenadas locais sem deslocar o carimbo no PDF final.
    """
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
    chosen_position = position or profile.position or "custom"
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


# ---------------------------------------------------------------------------
# Renderização PDF via navegador instalado
# ---------------------------------------------------------------------------
def _no_window_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def find_browser() -> Optional[Path]:
    names = ["msedge", "msedge.exe", "chrome", "chrome.exe", "google-chrome", "chromium", "chromium.exe"]
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found)
    env = os.environ
    candidates = [
        Path(env.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(env.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(env.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(env.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
        Path(env.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(env.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if str(candidate) and candidate.exists():
            return candidate
    return None




def _wait_for_pdf_output(output_path: Path, timeout_seconds: float = 12.0, minimum_size: int = 800) -> bool:
    """Aguarda o Edge/Chrome terminar de gravar o PDF.

    Em algumas versões do Edge o processo headless retorna código 0 antes de o
    arquivo ficar visível no disco. A RC6 verificava imediatamente e caía na
    prévia genérica mesmo quando a impressão ainda estava sendo finalizada.
    """
    output_path = Path(output_path)
    deadline = time.monotonic() + max(0.5, float(timeout_seconds))
    stable_size = -1
    stable_hits = 0
    while time.monotonic() < deadline:
        try:
            if output_path.exists():
                size = output_path.stat().st_size
                if size >= int(minimum_size):
                    with output_path.open("rb") as stream:
                        valid_header = stream.read(5) == b"%PDF-"
                    if valid_header:
                        if size == stable_size:
                            stable_hits += 1
                        else:
                            stable_size = size
                            stable_hits = 0
                        if stable_hits >= 2:
                            return True
        except (OSError, PermissionError):
            pass
        time.sleep(0.15)
    try:
        return output_path.exists() and output_path.stat().st_size >= int(minimum_size) and output_path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False

def html_file_to_pdf(html_path: Path, output_path: Path, browser: Optional[Path] = None, timeout: int = 100) -> Path:
    browser = Path(browser) if browser else find_browser()
    if browser is None:
        raise RuntimeError("Microsoft Edge ou Google Chrome não foi localizado. Instale/ative um deles para gerar PDF confiável.")
    html_path = Path(html_path).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    profiles_root = Path(tempfile.gettempdir()) / "cte_browser_profiles"
    profiles_root.mkdir(parents=True, exist_ok=True)
    profile_dir = profiles_root / f"profile_{uuid.uuid4().hex}"
    profile_dir.mkdir(parents=True, exist_ok=True)

    process = None
    stderr = ""
    try:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--hide-scrollbars",
            "--no-first-run",
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=2200",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={output_path}",
            html_path.as_uri(),
        ]
        if os.name != "nt":
            command.insert(1, "--no-sandbox")
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            creationflags=_no_window_flags(),
        )
        first_ready = _wait_for_pdf_output(output_path, timeout_seconds=8.0)
        if (process.returncode != 0 or not first_ready) and "--headless=new" in command:
            fallback_command = ["--headless" if item == "--headless=new" else item for item in command]
            process = subprocess.run(
                fallback_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                creationflags=_no_window_flags(),
            )
            _wait_for_pdf_output(output_path, timeout_seconds=12.0)
        stderr = process.stderr.decode("utf-8", errors="replace")[-1800:] if process else ""
    finally:
        for _ in range(10):
            try:
                shutil.rmtree(profile_dir, ignore_errors=False)
                break
            except Exception:
                time.sleep(0.25)
        shutil.rmtree(profile_dir, ignore_errors=True)

    pdf_ready = _wait_for_pdf_output(output_path, timeout_seconds=4.0)
    if process is None or process.returncode != 0 or not pdf_ready:
        raise RuntimeError(f"O navegador não conseguiu gerar o PDF (código {getattr(process, 'returncode', 'desconhecido')}).\n{stderr}")
    with output_path.open("rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise RuntimeError("O arquivo produzido não possui uma assinatura PDF válida.")
    return output_path


def html_text_to_pdf(document_html: str, output_path: Path, browser: Optional[Path] = None) -> Path:
    with tempfile.TemporaryDirectory(prefix="cte_html_pdf_") as tmp:
        html_path = Path(tmp) / "documento.html"
        html_path.write_text(document_html, encoding="utf-8")
        return html_file_to_pdf(html_path, output_path, browser=browser)


class PdfBatchExporter:
    def __init__(self, runtime_dir: Path, engine: Any, store: SignatureProfileStore):
        self.runtime_dir = Path(runtime_dir)
        self.engine = engine
        self.store = store

    def export(
        self,
        infos: list[dict[str, Any]],
        profile: SignatureProfile,
        date_text: str,
        output_root: Optional[Path] = None,
        individuals: bool = True,
        batch: bool = True,
        position: Optional[str] = None,
        stamp_size: str = "official",
        source_description: str = "marcados",
    ) -> dict[str, Any]:
        if not infos:
            raise RuntimeError("Nenhum CT-e foi selecionado.")
        if not individuals and not batch:
            raise RuntimeError("Selecione PDF separado, lote único ou ambos.")
        if not profile.ready or not Path(profile.processed_file).exists():
            raise RuntimeError("O perfil ainda não possui uma assinatura digitalizada e tratada.")
        browser = find_browser()
        if browser is None:
            raise RuntimeError("Microsoft Edge ou Google Chrome não foi localizado para a conversão em PDF.")

        stamp_size = normalize_stamp_size(stamp_size or profile.stamp_size)
        timestamp = datetime.now().strftime("%Y-%m-%d %H%M%S")
        root = Path(output_root) if output_root else self.runtime_dir / "saida_pdf" / timestamp
        individuals_dir = root / "individuais"
        batch_dir = root / "lote"
        logs_dir = root
        root.mkdir(parents=True, exist_ok=True)
        generated: list[Path] = []
        failures: list[dict[str, str]] = []
        used: set[str] = set()

        if individuals:
            individuals_dir.mkdir(parents=True, exist_ok=True)
            for info in infos:
                basename = cte_output_basename(info, used)
                target = _unique_path(individuals_dir / f"{basename}.pdf")
                try:
                    document = render_signed_html(self.engine, info, profile, date_text, position, stamp_size)
                    html_text_to_pdf(document, target, browser=browser)
                    generated.append(target)
                except Exception as exc:
                    failures.append({"cte": str(info.get("numero") or ""), "arquivo": str(target), "erro": str(exc)})

        batch_path = None
        if batch:
            batch_dir.mkdir(parents=True, exist_ok=True)
            batch_path = _unique_path(batch_dir / f"Lote CT-e {datetime.now():%Y-%m-%d} {len(infos)} documentos.pdf")
            try:
                document = render_signed_batch_html(self.engine, infos, profile, date_text, position, stamp_size)
                html_text_to_pdf(document, batch_path, browser=browser, )
                generated.append(batch_path)
            except Exception as exc:
                failures.append({"cte": "LOTE", "arquivo": str(batch_path), "erro": str(exc)})
                batch_path = None

        manifest = {
            "version": VERSION,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "selection_source": source_description,
            "requested": len(infos),
            "individuals_requested": individuals,
            "batch_requested": batch,
            "profile": asdict(profile),
            "date": date_text,
            "position": position or profile.position,
            "stamp_size": stamp_size,
            "stamp_size_label": STAMP_SIZE_LABELS.get(stamp_size, "Oficial - 85 x 32 mm"),
            "browser": str(browser),
            "generated": [str(path) for path in generated],
            "failures": failures,
            "xml_originals_modified": False,
        }
        manifest_path = logs_dir / "manifestacao_geracao.json"
        _atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
        txt_path = logs_dir / "manifestacao_geracao.txt"
        lines = [
            f"Central CT-e / DACTE - Assinatura e PDF {VERSION}",
            f"Data: {datetime.now():%d/%m/%Y %H:%M:%S}",
            f"Origem da seleção: {source_description}",
            f"CT-es solicitados: {len(infos)}",
            f"Arquivos gerados: {len(generated)}",
            f"Falhas: {len(failures)}",
            f"Perfil: {profile.name} ({profile.id})",
            f"Responsável: {profile.person_name}",
            f"Data impressa: {date_text}",
            f"Tamanho do carimbo: {STAMP_SIZE_LABELS.get(stamp_size, 'Oficial - 85 x 32 mm')}",
            f"XML fiscal original alterado: NÃO",
            "",
            "ARQUIVOS GERADOS:",
            *[str(path) for path in generated],
        ]
        if failures:
            lines.extend(["", "FALHAS:"])
            lines.extend(f"CT-e {item['cte']}: {item['erro']}" for item in failures)
        _atomic_write_text(txt_path, "\n".join(lines))

        profile.stamp_size = stamp_size
        profile.last_used_at = datetime.now().isoformat(timespec="seconds")
        self.store.upsert(profile)
        return {
            "root": root,
            "generated": generated,
            "failures": failures,
            "batch": batch_path,
            "manifest": manifest_path,
        }


# ---------------------------------------------------------------------------
# Interface PySide6, carregada somente dentro do programa
# ---------------------------------------------------------------------------
def _qt():
    widgets = importlib.import_module("PySide6.QtWidgets")
    core = importlib.import_module("PySide6.QtCore")
    gui = importlib.import_module("PySide6.QtGui")
    return widgets, core, gui


def _message(parent, kind: str, text: str):
    widgets, _, _ = _qt()
    box = widgets.QMessageBox
    function = getattr(box, kind)
    return function(parent, "Central CT-e / DACTE", text)


def _yes(parent, text: str) -> bool:
    widgets, _, _ = _qt()
    answer = widgets.QMessageBox.question(parent, "Central CT-e / DACTE", text)
    enum = getattr(widgets.QMessageBox, "StandardButton", widgets.QMessageBox)
    return answer == getattr(enum, "Yes", getattr(widgets.QMessageBox, "Yes", answer))


def _preview_pixmap(path: Path, max_w: int = 430, max_h: int = 230):
    _, core, gui = _qt()
    pixmap = gui.QPixmap(str(path))
    aspect = getattr(getattr(core.Qt, "AspectRatioMode", core.Qt), "KeepAspectRatio")
    transform = getattr(getattr(core.Qt, "TransformationMode", core.Qt), "SmoothTransformation")
    return pixmap.scaled(max_w, max_h, aspect, transform)



def _generic_dacte_preview_info() -> dict[str, Any]:
    """Dados inteiramente genéricos para renderizar a mesma estrutura HTML do DACTE real."""
    party = {
        "nome": "EMPRESA EXEMPLO LTDA",
        "ender": "AV. EXEMPLO, 0000 - BAIRRO",
        "mun": "CIDADE EXEMPLO - UF",
        "cep": "00000-000",
        "cnpjcpf": "00.000.000/0000-00",
        "ie": "000000000",
        "fone": "(00) 0000-0000",
        "pais": "BRASIL",
    }
    emit = dict(party)
    emit["nome"] = "TRANSPORTADORA EXEMPLO LTDA"
    toma = dict(party)
    toma["nome"] = "TOMADOR EXEMPLO LTDA"
    return {
        "tipo": "CT-e",
        "arquivo": "CT-e 00000000 XML EXEMPLO.xml",
        "numero": "00000000",
        "serie": "0",
        "modelo": "57",
        "data_br": "00/00/0000 00:00:00",
        "chave": "0" * 44,
        "emit": emit,
        "rem": dict(party, nome="REMETENTE EXEMPLO LTDA"),
        "dest": dict(party, nome="DESTINATÁRIO EXEMPLO LTDA"),
        "exped": dict(party, nome="EXPEDIDOR EXEMPLO LTDA"),
        "receb": dict(party, nome="RECEBEDOR EXEMPLO LTDA"),
        "toma": toma,
        "prot": {"nProt": "000000000000000", "dhRecbto": "00/00/0000 00:00:00"},
        "imposto": {"sit": "60 - ICMS COBRADO ANTERIORMENTE", "base": "0", "aliq": "0", "valor": "0", "red": "0", "st": "0"},
        "seguro": {"seguradora": "SEGURADORA EXEMPLO", "resp": "REMETENTE", "apolice": "00000000", "averbacao": "00000000"},
        "componentes": [
            {"nome": "FRETE VALOR", "valor": "0"},
            {"nome": "GRIS", "valor": "0"},
            {"nome": "PEDÁGIO", "valor": "0"},
        ],
        "docs": [{"tipo": "NF-e", "n_doc": "00000000", "cnpj": "00.000.000/0000-00", "serie_numero": "001 / 00000000", "chave": "0" * 44}],
        "modal": "RODOVIÁRIO",
        "tpCTe": "NORMAL",
        "tpServ": "SUBCONTRATAÇÃO",
        "toma_txt": "TOMADOR EXEMPLO",
        "forma_pagamento": "A PAGAR",
        "cfop": "0000",
        "natOp": "OPERAÇÃO EXEMPLO",
        "origem": "CIDADE ORIGEM - UF - 0000000",
        "destino": "CIDADE DESTINO - UF - 0000000",
        "produto": "MERCADORIA EXEMPLO",
        "outras_carac": "INFORMAÇÕES GENÉRICAS",
        "valor_carga": "0",
        "peso_bruto": "0",
        "peso_base": "0",
        "peso_aferido": "0",
        "cubagem": "0",
        "volumes": "0,0000 UNIDADES",
        "vTPrest": "0",
        "vRec": "0",
        "obs_principal": "PRÉVIA GENÉRICA PARA POSICIONAMENTO DA ASSINATURA. NÚMEROS DE EXEMPLO: 00000000.",
        "obs": "PRÉVIA GENÉRICA PARA POSICIONAMENTO DA ASSINATURA.",
        "rntrc": "00000000",
        "uso_exclusivo": "1: INFORMAÇÃO GENÉRICA 00000000\n2: INFORMAÇÃO GENÉRICA 00000000\n3: INFORMAÇÃO GENÉRICA 00000000",
    }



def _qt_html_document_to_png(document_html: str, output_path: Path) -> Path:
    """Renderiza o HTML real do DACTE sem depender do navegador externo.

    É uma contingência visual baseada em QTextDocument. Ela usa o HTML e os
    dados do CT-e selecionado, portanto nunca substitui a folha real por aquela
    antiga transportadora de exemplo.
    """
    core, gui = _qt_core_gui()
    page_width_css = 210.0 * 96.0 / 25.4
    page_height_css = 297.0 * 96.0 / 25.4
    render_scale = 2.0
    fallback_css = """
<style id="central-cte-editor-qt-fallback-css">
html, body { margin:0; padding:0; background:#fff; }
.printbar { display:none; }
.page { width:210mm; min-height:297mm; margin:0; box-sizing:border-box; box-shadow:none; }
</style>
"""
    html_doc = document_html.replace("</head>", fallback_css + "</head>", 1)
    document = gui.QTextDocument()
    document.setDocumentMargin(0.0)
    document.setPageSize(core.QSizeF(page_width_css, page_height_css))
    document.setHtml(html_doc)
    image_format = _qt_enum(gui.QImage, "Format", "Format_ARGB32_Premultiplied")
    image = gui.QImage(
        max(1, int(round(page_width_css * render_scale))),
        max(1, int(round(page_height_css * render_scale))),
        image_format,
    )
    image.fill(gui.QColor("#ffffff"))
    painter = gui.QPainter(image)
    painter.setRenderHint(gui.QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(gui.QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(gui.QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.scale(render_scale, render_scale)
    document.drawContents(painter, core.QRectF(0.0, 0.0, page_width_css, page_height_css))
    painter.end()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if image.isNull() or not image.save(str(output_path), "PNG"):
        raise RuntimeError("O renderizador Qt não conseguiu criar a prévia do DACTE real.")
    return output_path

def _html_preview_to_png(document_html: str, output_path: Path, browser: Optional[Path] = None) -> tuple[Path, str]:
    """Renderiza a primeira página real do DACTE para o editor.

    Primeiro tenta o mesmo fluxo HTML -> PDF do resultado final. Se o Edge ou
    Chrome devolver código 0 antes de gravar o arquivo, aguarda a conclusão.
    Se o navegador realmente falhar, usa o HTML real pelo Qt, nunca a folha
    antiga com dados de exemplo.
    """
    # Não injeta CSS de geometria aqui. A prévia precisa ser produzida com
    # exatamente as mesmas regras @media print / @page do PDF final.
    html_doc = document_html
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    browser_error = None
    try:
        with tempfile.TemporaryDirectory(prefix="cte_editor_html_") as tmp:
            pdf_path = Path(tmp) / "preview.pdf"
            html_text_to_pdf(html_doc, pdf_path, browser=browser)
            image = _qt_load_qimage(pdf_path, max_side=2200)
            if image.isNull():
                raise RuntimeError("A primeira página do DACTE não pôde ser convertida em imagem.")
            if not image.save(str(output_path), "PNG"):
                raise RuntimeError("O Qt não conseguiu salvar a imagem da prévia HTML real.")
        return output_path, "PDF real pelo Edge/Chrome"
    except Exception as exc:
        browser_error = exc
    try:
        _qt_html_document_to_png(html_doc, output_path)
        return output_path, "HTML real pelo Qt (contingência sem folha genérica)"
    except Exception as qt_exc:
        raise RuntimeError(
            f"A prévia real falhou no navegador ({browser_error}) e no Qt ({qt_exc})."
        ) from qt_exc


class SignatureLayoutEditorDialog:
    PAGE_W_MM = 210.0
    PAGE_H_MM = 297.0

    def __init__(self, parent, profile: SignatureProfile, store: SignatureProfileStore, engine: Any, date_text: str = "", preview_infos: Optional[Iterable[dict[str, Any]]] = None):
        self.widgets, self.core, self.gui = _qt()
        self.profile = profile
        self.store = store
        self.engine = engine
        self.date_text = str(date_text or datetime.now().strftime("%d/%m/%Y"))
        self.preview_infos = [item for item in (preview_infos or []) if isinstance(item, dict)]
        self.preview_info = self.preview_infos[0] if self.preview_infos else _generic_dacte_preview_info()
        self._syncing = False
        self.dialog = self.widgets.QDialog(parent)
        self.dialog.setWindowTitle("Editar posição da assinatura no DACTE real")
        self.dialog.resize(1220, 860)
        self._build()

    def _build(self):
        W, C, G = self.widgets, self.core, self.gui
        root = W.QHBoxLayout(self.dialog)
        self.scene = W.QGraphicsScene(0.0, 0.0, self.PAGE_W_MM, self.PAGE_H_MM, self.dialog)
        self.scene.setBackgroundBrush(G.QBrush(G.QColor("#d9dde3")))
        self._draw_generic_dacte()
        self.view = W.QGraphicsView(self.scene)
        self.view.setRenderHint(G.QPainter.RenderHint.Antialiasing, True)
        self.view.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, True)
        self.view.setMinimumSize(720, 720)
        root.addWidget(self.view, 1)
        self.signature_pixmap = G.QPixmap(str(self.profile.processed_file))
        Item = self._item_class()
        self.item = Item(self._make_solid_preview_pixmap(self.date_text),
                         _layout_value(self.profile, "custom_width_mm", STAMP_STANDARD_WIDTH_MM), self._item_changed)
        self.item.setPos(_layout_value(self.profile, "custom_x_mm", STAMP_OFFICIAL_X_MM), _layout_value(self.profile, "custom_y_mm", STAMP_OFFICIAL_Y_MM))
        self.item.setRotation(_layout_value(self.profile, "custom_rotation_deg", STAMP_OFFICIAL_ROTATION_DEG))
        self.scene.addItem(self.item); self.item.setSelected(True)
        panel = W.QWidget(); panel.setFixedWidth(410); side = W.QVBoxLayout(panel)
        title = W.QLabel("Posição e tamanho"); title.setStyleSheet("font-size:17px;font-weight:800;"); side.addWidget(title)
        help_label = W.QLabel("A página ao lado usa o CT-e real selecionado e as mesmas regras de impressão do PDF final. As coordenadas X e Y representam a posição física na folha A4; a margem do navegador é compensada automaticamente. Arraste o carimbo e use o quadrado azul para redimensionar. Os controles abaixo ajustam somente a assinatura, sem mudar o carimbo.")
        help_label.setWordWrap(True); side.addWidget(help_label)
        reference = W.QLabel(self._preview_reference_text())
        reference.setWordWrap(True)
        reference.setStyleSheet("padding:7px;border:1px solid #9eb9dc;background:#eef5ff;font-weight:700;color:#0b3f80;")
        side.addWidget(reference)
        form = W.QFormLayout()
        self.x_spin=self._spin(-5,210,.1," mm"); self.y_spin=self._spin(-5,297,.1," mm")
        self.w_spin=self._spin(STAMP_MIN_WIDTH_MM,STAMP_MAX_WIDTH_MM,.1," mm"); self.h_spin=self._spin(STAMP_MIN_WIDTH_MM/STAMP_STANDARD_ASPECT,STAMP_MAX_WIDTH_MM/STAMP_STANDARD_ASPECT,.1," mm"); self.r_spin=self._spin(-180,180,.5,"°")
        self.date_edit=W.QLineEdit(self.date_text); self.date_edit.setInputMask("00/00/0000;_")
        self.size_preset=W.QComboBox()
        self.size_preset.addItem("Personalizado", None)
        self.size_preset.addItem("Oficial - 85 mm", 85.0)
        self.size_preset.addItem("Compacto - 68 mm", 68.0)
        self.size_preset.addItem("Reduzido - 55 mm", 55.0)
        self.size_preset.addItem("Mínimo - 42 mm", 42.0)
        for label,widget in (("Horizontal (X)",self.x_spin),("Vertical (Y)",self.y_spin),("Largura",self.w_spin),("Altura",self.h_spin),("Tamanho rápido",self.size_preset),("Rotação",self.r_spin),("Data da prévia",self.date_edit)):
            form.addRow(label,widget)
        side.addLayout(form)

        signature_group = W.QGroupBox("Assinatura dentro do carimbo")
        signature_form = W.QFormLayout(signature_group)
        self.sig_scale_spin = self._spin(SIGNATURE_SCALE_MIN_PERCENT, SIGNATURE_SCALE_MAX_PERCENT, 5.0, "%")
        self.sig_x_spin = self._spin(-SIGNATURE_OFFSET_LIMIT_MM, SIGNATURE_OFFSET_LIMIT_MM, 0.25, " mm")
        self.sig_y_spin = self._spin(-SIGNATURE_OFFSET_LIMIT_MM, SIGNATURE_OFFSET_LIMIT_MM, 0.25, " mm")
        self.sig_scale_spin.setValue(_layout_value(self.profile, "signature_scale_percent", 100.0))
        self.sig_x_spin.setValue(_layout_value(self.profile, "signature_offset_x_mm", 0.0))
        self.sig_y_spin.setValue(_layout_value(self.profile, "signature_offset_y_mm", 0.0))
        self.sig_scale_spin.setToolTip("Aumenta ou diminui somente a assinatura, sem alterar o tamanho do carimbo.")
        self.sig_x_spin.setToolTip("Move somente a assinatura para a esquerda ou direita dentro do carimbo.")
        self.sig_y_spin.setToolTip("Move somente a assinatura para cima ou para baixo dentro do carimbo.")
        signature_form.addRow("Tamanho da assinatura", self.sig_scale_spin)
        signature_form.addRow("Mover horizontalmente", self.sig_x_spin)
        signature_form.addRow("Mover verticalmente", self.sig_y_spin)
        signature_buttons = W.QHBoxLayout()
        center_signature = W.QPushButton("Centralizar")
        restore_signature = W.QPushButton("Padrão 100%")
        center_signature.clicked.connect(self._center_signature)
        restore_signature.clicked.connect(self._restore_signature_defaults)
        signature_buttons.addWidget(center_signature)
        signature_buttons.addWidget(restore_signature)
        signature_form.addRow("", signature_buttons)
        side.addWidget(signature_group)

        grid=W.QCheckBox("Mostrar grade de 5 mm"); grid.setChecked(True); grid.toggled.connect(self._toggle_grid); side.addWidget(grid)
        self.zoom=W.QSlider(C.Qt.Orientation.Horizontal); self.zoom.setRange(60,240); self.zoom.setValue(150); self.zoom.valueChanged.connect(self._apply_zoom)
        side.addWidget(W.QLabel("Zoom")); side.addWidget(self.zoom)
        backend_label=W.QLabel(f"Fundo da prévia: {getattr(self, 'preview_backend', 'carregando')}\nAlinhamento: coordenadas físicas A4 sincronizadas com o PDF final")
        backend_label.setWordWrap(True); backend_label.setStyleSheet("font-size:11px;color:#4f5968;"); side.addWidget(backend_label)
        restore=W.QPushButton("Restaurar padrão referência"); restore.clicked.connect(self._restore_reference); side.addWidget(restore)
        center=W.QPushButton("Centralizar horizontalmente"); center.clicked.connect(self._center_horizontal); side.addWidget(center)
        side.addStretch(1)
        sample=W.QLabel("Formato final:\nREDESPACHO\ndd/mm/aaaa\n[assinatura]\n__________________________")
        sample.setStyleSheet("padding:8px;border:1px solid #b9bec7;background:#f6f7f9;font-family:monospace;"); side.addWidget(sample)
        buttons=W.QDialogButtonBox(W.QDialogButtonBox.StandardButton.Save|W.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(W.QDialogButtonBox.StandardButton.Save).setText("Salvar posição"); buttons.accepted.connect(self._accept); buttons.rejected.connect(self.dialog.reject); side.addWidget(buttons)
        root.addWidget(panel)
        for spin in (self.x_spin,self.y_spin,self.r_spin): spin.valueChanged.connect(self._controls_changed)
        self.w_spin.valueChanged.connect(self._width_changed)
        self.h_spin.valueChanged.connect(self._height_changed)
        self.size_preset.currentIndexChanged.connect(self._preset_size_changed)
        for spin in (self.sig_scale_spin, self.sig_x_spin, self.sig_y_spin):
            spin.valueChanged.connect(self._signature_controls_changed)
        self.date_edit.textChanged.connect(self._date_changed); self._refresh_stamp_pixmap(); self._item_changed(); C.QTimer.singleShot(0,self._fit_page)

    def _spin(self,a,b,step,suffix):
        s=self.widgets.QDoubleSpinBox(); s.setRange(a,b); s.setDecimals(2); s.setSingleStep(step); s.setSuffix(suffix); return s

    def _preview_reference_text(self) -> str:
        info = self.preview_info or {}
        number = str(info.get("numero") or "00000000")
        partner = partner_name_from_info(info)
        if self.preview_infos:
            suffix = f" (primeiro de {len(self.preview_infos)} selecionados)" if len(self.preview_infos) > 1 else ""
            return f"Prévia real: CT-e {number} - {partner}{suffix}"
        return "Prévia genérica de contingência. Selecione um CT-e antes de abrir o editor para usar a página real."

    def _preset_size_changed(self, index: int):
        if self._syncing or not hasattr(self, "item"):
            return
        width = self.size_preset.itemData(index)
        if width is None:
            return
        self.item.set_width(float(width))
        self._item_changed()

    def _signature_visual_values(self) -> tuple[float, float, float]:
        if hasattr(self, "sig_scale_spin"):
            scale_percent = float(self.sig_scale_spin.value())
            offset_x_mm = float(self.sig_x_spin.value())
            offset_y_mm = float(self.sig_y_spin.value())
        else:
            scale_percent = _layout_value(self.profile, "signature_scale_percent", 100.0)
            offset_x_mm = _layout_value(self.profile, "signature_offset_x_mm", 0.0)
            offset_y_mm = _layout_value(self.profile, "signature_offset_y_mm", 0.0)
        scale_percent = max(SIGNATURE_SCALE_MIN_PERCENT, min(SIGNATURE_SCALE_MAX_PERCENT, scale_percent))
        offset_x_mm = max(-SIGNATURE_OFFSET_LIMIT_MM, min(SIGNATURE_OFFSET_LIMIT_MM, offset_x_mm))
        offset_y_mm = max(-SIGNATURE_OFFSET_LIMIT_MM, min(SIGNATURE_OFFSET_LIMIT_MM, offset_y_mm))
        return scale_percent, offset_x_mm, offset_y_mm

    def _refresh_stamp_pixmap(self):
        if hasattr(self, "item"):
            self.item.set_content(self._make_solid_preview_pixmap(self.date_edit.text() if hasattr(self, "date_edit") else self.date_text))

    def _make_solid_preview_pixmap(self, date_text: str):
        G, C = self.gui, self.core
        canvas = G.QPixmap(1000, 376)
        canvas.fill(C.Qt.GlobalColor.transparent)
        painter = G.QPainter(canvas)
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, True)
        color = G.QColor("#111")
        painter.setPen(color)
        font = G.QFont("Arial", 38); font.setBold(True); painter.setFont(font)
        painter.drawText(C.QRectF(30, 18, 940, 92), C.Qt.AlignmentFlag.AlignCenter, str(self.profile.title or "REDESPACHO").upper())
        font = G.QFont("Arial", 40); font.setBold(True); painter.setFont(font)
        painter.drawText(C.QRectF(30, 95, 940, 58), C.Qt.AlignmentFlag.AlignCenter, str(date_text or ""))

        # Linha e rótulo ficam atrás da assinatura, igual ao SVG usado no PDF final.
        painter.setPen(G.QPen(color, 4))
        font = G.QFont("Arial", 43); font.setBold(True); painter.setFont(font)
        painter.drawText(C.QRectF(34, 264, 130, 70), C.Qt.AlignmentFlag.AlignCenter, "Ass:")
        painter.drawLine(C.QPointF(160, 313), C.QPointF(955, 313))

        if not self.signature_pixmap.isNull():
            scale_percent, offset_x_mm, offset_y_mm = self._signature_visual_values()
            scale = scale_percent / 100.0
            base_target = C.QRectF(165, 128, 790, 204)
            target_width = max(1, int(round(base_target.width() * scale)))
            target_height = max(1, int(round(base_target.height() * scale)))
            scaled = self.signature_pixmap.scaled(
                target_width, target_height,
                C.Qt.AspectRatioMode.KeepAspectRatio,
                C.Qt.TransformationMode.SmoothTransformation,
            )
            offset_x_px = offset_x_mm * (1000.0 / STAMP_STANDARD_WIDTH_MM)
            offset_y_px = offset_y_mm * (376.0 / STAMP_STANDARD_HEIGHT_MM)
            px = base_target.center().x() - scaled.width() / 2.0 + offset_x_px
            py = base_target.center().y() - scaled.height() / 2.0 + offset_y_px
            painter.drawPixmap(C.QPointF(px, py), scaled)

        painter.setPen(G.QPen(color, 4))
        painter.drawRect(C.QRectF(7, 7, 986, 362))
        painter.end()
        return canvas

    def _item_class(self):
        W,C,G=self.widgets,self.core,self.gui
        class Item(W.QGraphicsItem):
            HANDLE=4.0
            ASPECT=STAMP_STANDARD_ASPECT
            MIN_W=STAMP_MIN_WIDTH_MM
            MAX_W=STAMP_MAX_WIDTH_MM
            def __init__(self,pixmap,width,callback):
                super().__init__(); self.pixmap=pixmap; self.callback=callback; self.resizing=False
                self.width=max(self.MIN_W,min(self.MAX_W,float(width))); self.height=self.width/self.ASPECT
                f=W.QGraphicsItem.GraphicsItemFlag; self.setFlags(f.ItemIsMovable|f.ItemIsSelectable|f.ItemSendsGeometryChanges); self.setAcceptHoverEvents(True); self.setTransformOriginPoint(self.width/2,self.height/2)
            def boundingRect(self): return C.QRectF(0,0,self.width+self.HANDLE,self.height+self.HANDLE)
            def handleRect(self): return C.QRectF(self.width-self.HANDLE/2,self.height-self.HANDLE/2,self.HANDLE,self.HANDLE)
            def paint(self,painter,option,widget=None):
                painter.save(); painter.setRenderHint(G.QPainter.RenderHint.Antialiasing,True); painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform,True); rect=C.QRectF(0,0,self.width,self.height)
                if not self.pixmap.isNull(): painter.drawPixmap(rect,self.pixmap,C.QRectF(self.pixmap.rect()))
                if self.isSelected():
                    painter.setPen(G.QPen(G.QColor("#1565c0"),.45,C.Qt.PenStyle.DashLine)); painter.setBrush(C.Qt.BrushStyle.NoBrush); painter.drawRect(rect)
                    painter.setPen(C.Qt.PenStyle.NoPen); painter.setBrush(G.QColor("#1565c0")); painter.drawRect(self.handleRect())
                painter.restore()
            def hoverMoveEvent(self,event): self.setCursor(C.Qt.CursorShape.SizeFDiagCursor if self.handleRect().contains(event.pos()) else C.Qt.CursorShape.SizeAllCursor); super().hoverMoveEvent(event)
            def mousePressEvent(self,event):
                if event.button()==C.Qt.MouseButton.LeftButton and self.handleRect().contains(event.pos()): self.resizing=True; event.accept(); return
                super().mousePressEvent(event)
            def _apply_width(self,width):
                self.prepareGeometryChange(); self.width=max(self.MIN_W,min(self.MAX_W,float(width))); self.height=self.width/self.ASPECT; self.setTransformOriginPoint(self.width/2,self.height/2); self.update()
            def mouseMoveEvent(self,event):
                if self.resizing:
                    requested=max(float(event.pos().x()),float(event.pos().y())*self.ASPECT); self._apply_width(requested); self.callback(); event.accept(); return
                super().mouseMoveEvent(event); self.callback()
            def mouseReleaseEvent(self,event): self.resizing=False; super().mouseReleaseEvent(event); self.callback()
            def set_width(self,w): self._apply_width(w)
            def set_height(self,h): self._apply_width(float(h)*self.ASPECT)
            def set_size(self,w,h=None): self._apply_width(w)
            def set_content(self,pixmap): self.pixmap=pixmap; self.update()
        return Item

    def _make_generic_dacte_pixmap(self):
        """Renderiza o CT-e real selecionado; o desenho manual é somente contingência."""
        try:
            renderer = _resolve_render_document(self.engine)
            info = self.preview_info or _generic_dacte_preview_info()
            document_html = renderer([info], with_button=False)
            cache_dir = self.store.root / "cache_editor"
            cache_dir.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(info, ensure_ascii=False, sort_keys=True, default=str)
            fingerprint = hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:12]
            number = _safe_filename(info.get("numero"), "00000000", 24)
            target = cache_dir / f"dacte_real_{number}_{fingerprint}_{VERSION.replace('.', '_')}.png"
            _, preview_backend = _html_preview_to_png(document_html, target)
            pixmap = self.gui.QPixmap(str(target))
            if not pixmap.isNull():
                self.preview_backend = f"{preview_backend}: CT-e {info.get('numero') or '00000000'}"
                return pixmap
        except Exception as exc:
            self.preview_backend = f"falha na prévia real: {exc}"
        if self.preview_infos:
            return self._make_preview_failure_pixmap(str(self.preview_backend))
        return self._make_fallback_generic_dacte_pixmap()

    def _make_preview_failure_pixmap(self, message: str):
        """Evita mostrar a folha antiga como se fosse o CT-e selecionado."""
        C, G = self.core, self.gui
        px_per_mm = 5.0
        image_format = _qt_enum(G.QImage, "Format", "Format_ARGB32_Premultiplied")
        image = G.QImage(int(self.PAGE_W_MM * px_per_mm), int(self.PAGE_H_MM * px_per_mm), image_format)
        image.fill(G.QColor("#ffffff"))
        painter = G.QPainter(image)
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing, True)
        painter.setPen(G.QPen(G.QColor("#b42318"), 3.0))
        painter.setBrush(G.QColor("#fff4f2"))
        rect = C.QRectF(60.0, 140.0, image.width() - 120.0, 310.0)
        painter.drawRoundedRect(rect, 12.0, 12.0)
        font = G.QFont("Arial", 24); font.setBold(True); painter.setFont(font)
        painter.drawText(C.QRectF(90.0, 175.0, image.width() - 180.0, 55.0), int(C.Qt.AlignmentFlag.AlignCenter), "PRÉVIA REAL INDISPONÍVEL")
        font = G.QFont("Arial", 14); font.setBold(False); painter.setFont(font)
        painter.setPen(G.QColor("#5f1a14"))
        painter.drawText(C.QRectF(105.0, 245.0, image.width() - 210.0, 140.0), int(C.Qt.AlignmentFlag.AlignCenter | C.Qt.TextFlag.TextWordWrap), str(message))
        painter.drawText(C.QRectF(105.0, 385.0, image.width() - 210.0, 42.0), int(C.Qt.AlignmentFlag.AlignCenter), "A folha genérica foi bloqueada para não induzir o posicionamento ao erro.")
        painter.end()
        return G.QPixmap.fromImage(image)

    def _make_fallback_generic_dacte_pixmap(self):
        """Desenha uma prévia genérica simplificada e legível do DACTE para posicionar a assinatura."""
        C, G = self.core, self.gui
        px_per_mm = 5.0
        width_px = int(self.PAGE_W_MM * px_per_mm)
        height_px = int(self.PAGE_H_MM * px_per_mm)
        image_format = _qt_enum(G.QImage, "Format", "Format_ARGB32_Premultiplied")
        image = G.QImage(width_px, height_px, image_format)
        image.fill(G.QColor("#ffffff"))
        painter = G.QPainter(image)
        painter.setRenderHint(G.QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(G.QPainter.RenderHint.TextAntialiasing, True)
        black = G.QColor("#151515")
        gray = G.QColor("#f4f6f8")
        line_pen = G.QPen(black, 1.0)
        thin_pen = G.QPen(black, 0.75)
        painter.setPen(line_pen)

        def mm(value):
            return float(value) * px_per_mm

        def box(x, y, w, h, fill=None, pen=None):
            painter.save()
            painter.setPen(pen or line_pen)
            painter.setBrush(G.QBrush(fill or G.QColor("#ffffff")))
            painter.drawRect(mm(x), mm(y), mm(w), mm(h))
            painter.restore()

        def label(text, x, y, w, h, size=7.0, bold=False, align=None, wrap=False, color=black):
            painter.save()
            font = G.QFont("Arial", int(round(size * 1.65)))
            font.setBold(bool(bold))
            painter.setFont(font)
            painter.setPen(color)
            rect = C.QRectF(mm(x), mm(y), mm(w), mm(h))
            flags = align or (C.Qt.AlignmentFlag.AlignLeft | C.Qt.AlignmentFlag.AlignTop)
            if wrap:
                flags |= C.Qt.TextFlag.TextWordWrap
            painter.drawText(rect, int(flags), str(text))
            painter.restore()

        def header(text, x, y, w, h=4.2):
            box(x, y, w, h, gray)
            label(text, x, y + .2, w, h - .4, 6.4, True, C.Qt.AlignmentFlag.AlignCenter | C.Qt.AlignmentFlag.AlignVCenter)

        def hline(y, x=8, w=194):
            painter.save(); painter.setPen(thin_pen); painter.drawLine(mm(x), mm(y), mm(x + w), mm(y)); painter.restore()

        margin = 8.0
        content_w = 194.0
        box(margin, 8, content_w, 281)

        header("DECLARO QUE RECEBI OS VOLUMES DESTE CONHECIMENTO EM PERFEITO ESTADO", margin, 8, content_w, 7)
        box(margin, 15, 58, 20)
        label("NOME", margin + 1, 16, 12, 3, 5.6, True)
        hline(24, margin + 1, 52)
        label("RG", margin + 1, 25.5, 12, 3, 5.6, True)
        hline(33, margin + 1, 52)
        box(margin + 58, 15, 85, 20)
        label("ASSINATURA / CARIMBO", margin + 58, 22.5, 85, 4, 6.2, True, C.Qt.AlignmentFlag.AlignCenter | C.Qt.AlignmentFlag.AlignVCenter)
        box(margin + 143, 15, 28, 20)
        label("CHEGADA DATA/HORA", margin + 143, 17, 28, 3, 4.8, True, C.Qt.AlignmentFlag.AlignCenter | C.Qt.AlignmentFlag.AlignVCenter)
        hline(23, margin + 146, 22)
        label("SAÍDA DATA/HORA", margin + 143, 26, 28, 3, 4.8, True, C.Qt.AlignmentFlag.AlignCenter | C.Qt.AlignmentFlag.AlignVCenter)
        hline(32, margin + 146, 22)
        box(margin + 171, 15, 23, 20)
        label("CT-e\\nNº 00000000\\nSÉRIE: 0", margin + 171, 17, 23, 14, 7.0, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter, wrap=True)

        y = 35
        box(margin, y, 72, 42)
        label("TRANSPORTADORA EXEMPLO LTDA", margin + 2, y + 3, 68, 8, 8.4, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignTop, wrap=True)
        label("AV. EXEMPLO, 0000 - CENTRO\\nCIDADE EXEMPLO - UF\\nCEP: 00000-000\\nCNPJ: 00.000.000/0000-00\\nINSCRIÇÃO ESTADUAL: 000000000\\nTELEFONE: (00) 0000-0000", margin + 3, y + 12, 66, 24, 6.1, False, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignTop, wrap=True)
        box(margin + 72, y, 86, 42)
        label("DACTE", margin + 72, y + 2, 86, 6, 11.0, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter)
        label("Documento Auxiliar do Conhecimento de Transporte Eletrônico", margin + 74, y + 8.5, 82, 4, 5.4, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter)
        header("MODELO      SÉRIE      NÚMERO        FOLHA      DATA/HORA EMISSÃO", margin + 72, y + 13.5, 86, 4.5)
        label("57             0         00000000       01/01      00/00/0000 00:00:00", margin + 74, y + 18, 82, 4, 5.6, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter)
        box(margin + 84, y + 23.5, 62, 8)
        painter.save(); painter.setPen(thin_pen)
        for i in range(35):
            x = margin + 86 + i*1.6
            thickness = 1.3 if i % 5 == 0 else 0.75
            painter.setPen(G.QPen(black, thickness))
            painter.drawLine(C.QPointF(mm(x), mm(y + 24.2)), C.QPointF(mm(x), mm(y + 30.8)))
        painter.restore()
        label("Chave de acesso 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000", margin + 74, y + 32.5, 82, 3.5, 5.0, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter)
        box(margin + 158, y, 36, 42)
        label("MODAL\\nRODOVIÁRIO", margin + 160, y + 5, 32, 10, 8.2, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter, wrap=True)
        label("INSC. SUFRAMA DO DESTINATÁRIO", margin + 160, y + 22, 32, 4, 4.8, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter, wrap=True)

        y = 77
        box(margin, y, 72, 14)
        label("TIPO DO CT-e", margin + 1, y + 1, 20, 3, 5.1, True)
        label("NORMAL", margin + 1, y + 4, 25, 4, 6.4, True)
        label("TIPO DO SERVIÇO", margin + 37, y + 1, 25, 3, 5.1, True)
        label("SUBCONTRATAÇÃO", margin + 37, y + 4, 32, 4, 6.2, True)
        box(margin + 72, y, 122, 14)
        label("PROTOCOLO DE AUTORIZAÇÃO DE USO 000000000000000 00/00/0000 00:00:00", margin + 74, y + 4.5, 118, 4, 5.4, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter)

        y = 91
        box(margin, y, content_w, 11)
        label("CFOP / NATUREZA DA OPERAÇÃO", margin + 1, y + 1, 44, 3, 5.1, True)
        label("6932 - TRANSPORTE INTERESTADUAL", margin + 1, y + 4, 60, 3, 6.1, True)
        label("ORIGEM DA PRESTAÇÃO", margin + 1, y + 7, 35, 2.5, 5.0, True)
        label("CIDADE ORIGEM - UF", margin + 28, y + 7, 35, 2.5, 5.8, True)
        label("DESTINO DA PRESTAÇÃO", margin + 102, y + 7, 36, 2.5, 5.0, True)
        label("CIDADE DESTINO - UF", margin + 133, y + 7, 35, 2.5, 5.8, True)

        blocks = [
            (102, "REMETENTE", "EMPRESA REMETENTE LTDA", "ENDEREÇO MODELO, 0000 - BAIRRO\\nMUNICÍPIO EXEMPLO - UF\\nCEP 00000-000    CNPJ/CPF 00.000.000/0000-00\\nIE 000000000    FONE (00) 0000-0000"),
            (102, "DESTINATÁRIO", "EMPRESA DESTINO LTDA", "ENDEREÇO MODELO, 0000 - BAIRRO\\nMUNICÍPIO DESTINO - UF\\nCEP 00000-000    CNPJ/CPF 00.000.000/0000-00\\nIE 000000000    FONE (00) 0000-0000"),
            (131, "EXPEDIDOR", "EMPRESA EXPEDIDORA LTDA", "ENDEREÇO MODELO, 0000 - BAIRRO\\nMUNICÍPIO EXPEDIÇÃO - UF\\nCEP 00000-000    CNPJ/CPF 00.000.000/0000-00\\nIE 000000000    FONE (00) 0000-0000"),
            (131, "RECEBEDOR", "EMPRESA RECEBEDORA LTDA", "ENDEREÇO MODELO, 0000 - BAIRRO\\nMUNICÍPIO RECEBIMENTO - UF\\nCEP 00000-000    CNPJ/CPF 00.000.000/0000-00\\nIE 000000000    FONE (00) 0000-0000"),
        ]
        for idx, (row_y, title_txt, name_txt, info_txt) in enumerate(blocks):
            x = margin if idx % 2 == 0 else margin + 97
            box(x, row_y, 97, 29)
            label(title_txt, x + 1, row_y + .8, 25, 2.8, 5.1, True)
            label(name_txt, x + 1, row_y + 4, 94, 4, 6.5, True)
            label(info_txt, x + 1, row_y + 8.5, 94, 16, 5.5, False, wrap=True)

        y = 160
        box(margin, y, content_w, 14)
        label("TOMADOR DO SERVIÇO", margin + 1, y + .8, 35, 3, 5.1, True)
        label("RODOVITOR TRANSPORTES E LOCAÇÃO DE VEÍCULOS LTDA", margin + 1, y + 4, 105, 3.5, 6.4, True)
        label("ENDEREÇO EXEMPLO - CIDADE/UF - CNPJ 00.000.000/0000-00", margin + 1, y + 7.2, 110, 3.2, 5.4, False)
        label("PRODUTO PREDOMINANTE", margin + 1, y + 10.2, 40, 2.5, 5.0, True)
        label("MERCADORIA EXEMPLO", margin + 38, y + 10.2, 50, 2.5, 5.8, True)
        label("VALOR TOTAL DA MERCADORIA: R$ 0,00", margin + 124, y + 10.2, 68, 2.5, 5.4, True, C.Qt.AlignmentFlag.AlignRight | C.Qt.AlignmentFlag.AlignVCenter)

        y = 174
        header("PESO BRUTO   PESO BASE CÁLC.   CUBAGEM   QTDE. VOLUMES   SEGURADORA / APÓLICE", margin, y, content_w, 4.5)
        box(margin, y + 4.5, content_w, 8)
        label("0,0000            0,0000              0,0000          0,0000               -", margin + 1, y + 6, 190, 3, 5.7, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter)
        header("COMPONENTES DO VALOR DA PRESTAÇÃO DE SERVIÇO", margin, y + 12.5, content_w, 4.5)
        box(margin, y + 17, content_w, 16)
        label("FRETE VALOR: R$ 0,00", margin + 2, y + 19, 45, 3, 6.0, True)
        label("GRIS: R$ 0,00", margin + 50, y + 19, 30, 3, 6.0, True)
        label("PEDÁGIO: R$ 0,00", margin + 85, y + 19, 35, 3, 6.0, True)
        label("VALOR TOTAL DO SERVIÇO: R$ 0,00", margin + 125, y + 19, 66, 3, 5.8, True, C.Qt.AlignmentFlag.AlignRight | C.Qt.AlignmentFlag.AlignVCenter)
        box(margin, y + 33, content_w, 13, G.QColor("#eef8ee"))
        label("CONTROLE INTERNO - PARCEIRO EXEMPLO", margin + 1, y + 34, 80, 2.8, 5.6, True)
        label("Frete calculado: R$ 0,00 | XML: R$ 0,00 | Diferença: R$ 0,00 | Validação: OK", margin + 1, y + 36.5, 190, 3, 5.4, False)
        label("INFORMAÇÃO COMPLEMENTAR", margin + 1, y + 39.5, 50, 2.5, 5.4, True)
        label("AGUARDANDO FATURA", margin + 1, y + 42, 70, 2.5, 5.4, False)

        y = 220
        header("INFORMAÇÕES RELATIVAS AO IMPOSTO", margin, y, content_w, 4.5)
        box(margin, y + 4.5, content_w, 10)
        label("SITUAÇÃO TRIBUTÁRIA: 60 - ICMS COBRADO ANTERIORMENTE POR SUBSTITUIÇÃO TRIBUTÁRIA", margin + 1, y + 7, 175, 3, 5.3, True)
        header("DOCUMENTOS ORIGINÁRIOS", margin, y + 14.5, content_w, 4.5)
        box(margin, y + 19, content_w, 12)
        label("TP DOC. NF-e 00000000   CNPJ/CPF EMITENTE 00.000.000/0000-00   SÉRIE/NRO. DOCUMENTO 001 / 00000000", margin + 1, y + 20.4, 190, 3.5, 5.4, False, wrap=True)
        label("0000 0000 0000 0000 0000 0000 0000 0000 0000 0000 0000", margin + 1, y + 24.2, 190, 3.2, 5.2, False)
        header("OBSERVAÇÕES", margin, y + 31, content_w, 4.5)
        box(margin, y + 35.5, content_w, 12)
        label("PRÉVIA GENÉRICA PARA POSICIONAMENTO DA ASSINATURA. TODOS OS NÚMEROS SÃO EXEMPLOS 00000000.", margin + 1, y + 37.5, 188, 5, 5.5, False, wrap=True)

        y = 272.5
        header("DADOS ESPECÍFICOS DO MODAL RODOVIÁRIO", margin, y, content_w, 4.5)
        box(margin, y + 4.5, content_w, 5.5)
        label("RNTRC 00000000     DATA PREVISTA DE ENTREGA     ESTE CONHECIMENTO ATENDE À LEGISLAÇÃO", margin + 1, y + 5.5, 190, 3.5, 5.2, True, C.Qt.AlignmentFlag.AlignHCenter | C.Qt.AlignmentFlag.AlignVCenter)
        header("USO EXCLUSIVO DO EMISSOR DO CT-e", margin, y + 10, 135, 4.5)
        header("RESERVADO AO FISCO", margin + 135, y + 10, 59, 4.5)
        box(margin, y + 14.5, 135, 10)
        box(margin + 135, y + 14.5, 59, 10)
        label("1: INFORMAÇÃO GENÉRICA 00000000\\n2: INFORMAÇÃO GENÉRICA 00000000\\n3: INFORMAÇÃO GENÉRICA 00000000", margin + 1, y + 15.5, 130, 8, 5.1, False, wrap=True)

        painter.end()
        return G.QPixmap.fromImage(image)


    def _draw_generic_dacte(self):
        G = self.gui
        page = self.scene.addRect(0, 0, self.PAGE_W_MM, self.PAGE_H_MM, G.QPen(G.QColor("#8b9097"), .35), G.QBrush(G.QColor("white")))
        page.setZValue(-30)
        pixmap = self._make_generic_dacte_pixmap()
        background = self.scene.addPixmap(pixmap)
        transform = G.QTransform()
        transform.scale(self.PAGE_W_MM / max(1.0, float(pixmap.width())), self.PAGE_H_MM / max(1.0, float(pixmap.height())))
        background.setTransform(transform)
        background.setZValue(-20)
        self._grid_items = []
        for x in range(5, 210, 5):
            item = self.scene.addLine(x, 0, x, 297, G.QPen(G.QColor(80, 140, 210, 48), .07))
            item.setZValue(-10)
            self._grid_items.append(item)
        for y in range(5, 297, 5):
            item = self.scene.addLine(0, y, 210, y, G.QPen(G.QColor(80, 140, 210, 48), .07))
            item.setZValue(-10)
            self._grid_items.append(item)

    def _toggle_grid(self,v):
        for i in self._grid_items: i.setVisible(bool(v))
    def _fit_page(self): self.view.fitInView(self.scene.sceneRect(),self.core.Qt.AspectRatioMode.KeepAspectRatio); self.zoom.setValue(150)
    def _apply_zoom(self,v): self.view.resetTransform(); self.view.fitInView(self.scene.sceneRect(),self.core.Qt.AspectRatioMode.KeepAspectRatio); self.view.scale(max(.45,v/100),max(.45,v/100))
    def _item_changed(self):
        if self._syncing or not hasattr(self,"item"): return
        self._syncing=True
        try:
            min_margin = 5.0
            x = max(min_margin, min(self.PAGE_W_MM - self.item.width - min_margin, self.item.pos().x()))
            y = max(min_margin, min(self.PAGE_H_MM - self.item.height - min_margin, self.item.pos().y()))
            if abs(x - self.item.pos().x()) > 0.001 or abs(y - self.item.pos().y()) > 0.001:
                self.item.setPos(x, y)
            self.x_spin.setValue(x); self.y_spin.setValue(y); self.w_spin.setValue(self.item.width); self.h_spin.setValue(self.item.height); self.r_spin.setValue(self.item.rotation())
        finally: self._syncing=False
    def _controls_changed(self):
        if self._syncing or not hasattr(self,"item"): return
        self._syncing=True
        try: self.item.setPos(self.x_spin.value(),self.y_spin.value()); self.item.setRotation(self.r_spin.value())
        finally: self._syncing=False
    def _width_changed(self,v):
        if self._syncing or not hasattr(self,"item"): return
        self.item.set_width(v); self._item_changed()
    def _height_changed(self,v):
        if self._syncing or not hasattr(self,"item"): return
        self.item.set_height(v); self._item_changed()
    def _signature_controls_changed(self, _value=None):
        if self._syncing or not hasattr(self, "item"):
            return
        self._refresh_stamp_pixmap()
    def _center_signature(self):
        self.sig_x_spin.setValue(0.0); self.sig_y_spin.setValue(0.0); self._refresh_stamp_pixmap()
    def _restore_signature_defaults(self):
        self.sig_scale_spin.setValue(100.0); self.sig_x_spin.setValue(0.0); self.sig_y_spin.setValue(0.0); self._refresh_stamp_pixmap()
    def _date_changed(self,v):
        self._refresh_stamp_pixmap()
    def _restore_reference(self): self.item.setPos(STAMP_OFFICIAL_X_MM,STAMP_OFFICIAL_Y_MM); self.item.set_width(STAMP_STANDARD_WIDTH_MM); self.item.setRotation(STAMP_OFFICIAL_ROTATION_DEG); self._item_changed()
    def _center_horizontal(self): self.item.setX((210-self.item.width)/2); self._item_changed()
    def _accept(self):
        try: datetime.strptime(self.date_edit.text().strip(),"%d/%m/%Y")
        except Exception: _message(self.dialog,"warning","Informe uma data válida no formato dd/mm/aaaa."); return
        p=self.profile; p.position="custom"; p.stamp_size="custom"; p.custom_x_mm=round(self.item.pos().x(),2); p.custom_y_mm=round(self.item.pos().y(),2); p.custom_width_mm=round(self.item.width,2); p.custom_height_mm=round(self.item.width/STAMP_STANDARD_ASPECT,2); p.custom_rotation_deg=round(self.item.rotation(),2); p.signature_scale_percent=round(self.sig_scale_spin.value(),2); p.signature_offset_x_mm=round(self.sig_x_spin.value(),2); p.signature_offset_y_mm=round(self.sig_y_spin.value(),2); self.store.upsert(p); self.dialog.accept()
    def exec(self): return self.dialog.exec()


class SignatureManagerDialog:
    def __init__(self, parent, runtime_dir: Path, engine: Any, infos_provider: Callable[[], tuple[list[dict[str, Any]], str]]):
        self.parent = parent
        self.runtime_dir = Path(runtime_dir)
        self.engine = engine
        self.infos_provider = infos_provider
        self.store = SignatureProfileStore(self.runtime_dir)
        self.widgets, self.core, self.gui = _qt()
        self.dialog = self.widgets.QDialog(parent)
        self.dialog.setWindowTitle(f"Assinaturas e PDF - {VERSION}")
        self.dialog.resize(920, 570)
        self._build()
        self.refresh()

    def exec(self):
        return self.dialog.exec()

    def _build(self):
        W = self.widgets
        layout = W.QVBoxLayout(self.dialog)
        title = W.QLabel("Cadastro de assinaturas e geração de PDF")
        title.setStyleSheet("font-size:18px;font-weight:800;")
        layout.addWidget(title)
        backend_name, backend_description = image_backend_status()
        note = W.QLabel(f"A assinatura é visual e será aplicada somente ao HTML/PDF. O XML fiscal autorizado permanece intacto.\nTratamento da imagem: {backend_name} — {backend_description}.")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = W.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Perfil", "Responsável", "Título", "Situação", "Posição", "Último uso"])
        self.table.setSelectionBehavior(getattr(getattr(W.QAbstractItemView, "SelectionBehavior", W.QAbstractItemView), "SelectRows"))
        self.table.setSelectionMode(getattr(getattr(W.QAbstractItemView, "SelectionMode", W.QAbstractItemView), "SingleSelection"))
        self.table.setEditTriggers(getattr(getattr(W.QAbstractItemView, "EditTrigger", W.QAbstractItemView), "NoEditTriggers"))
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        actions = W.QHBoxLayout()
        for text, callback in (
            ("Novo cadastro", self.new_profile),
            ("Editar cadastro", self.edit_profile),
            ("Gerar folha para assinar", self.generate_sheet),
            ("Importar folha assinada", self.import_signed_sheet),
            ("Visualizar assinatura", self.preview_signature),
            ("Excluir", self.delete_profile),
        ):
            button = W.QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)

        bottom = W.QHBoxLayout()
        bottom.addStretch(1)
        close = W.QPushButton("Fechar")
        generate = W.QPushButton("Assinar e gerar PDFs")
        generate.setStyleSheet("font-weight:800;padding:8px 15px;")
        close.clicked.connect(self.dialog.reject)
        generate.clicked.connect(self.generate_pdfs)
        bottom.addWidget(close)
        bottom.addWidget(generate)
        layout.addLayout(bottom)

    def profiles(self) -> list[SignatureProfile]:
        return self.store.load()

    def refresh(self, select_id: str = ""):
        profiles = self.profiles()
        self.table.setRowCount(len(profiles))
        selected_row = -1
        for row, profile in enumerate(profiles):
            values = [
                profile.name,
                profile.person_name,
                profile.title,
                "Pronta" if profile.ready and Path(profile.processed_file).exists() else "Pendente de digitalização",
                {"custom": "Personalizado", "reference-docs": "Padrão referência", "signature-field": "Campo legado", "signature-field-legacy": "Campo legado", "top-left": "Superior esquerdo", "top-right": "Superior direito", "bottom-left": "Inferior esquerdo", "bottom-right": "Inferior direito"}.get(profile.position, profile.position),
                profile.last_used_at.replace("T", " ") if profile.last_used_at else "Nunca",
            ]
            for col, value in enumerate(values):
                self.table.setItem(row, col, self.widgets.QTableWidgetItem(str(value)))
            self.table.item(row, 0).setData(self._user_role(), profile.id)
            if profile.id == select_id:
                selected_row = row
        self.table.resizeColumnsToContents()
        if selected_row < 0 and profiles:
            ranked = sorted(enumerate(profiles), key=lambda pair: ((pair[1].last_used_at or ""), pair[1].updated_at or pair[1].created_at or ""), reverse=True)
            selected_row = ranked[0][0] if ranked else 0
        if selected_row >= 0:
            self.table.selectRow(selected_row)

    def _user_role(self):
        return getattr(getattr(self.core.Qt, "ItemDataRole", self.core.Qt), "UserRole", getattr(self.core.Qt, "UserRole", 256))

    def selected_profile(self, require: bool = True) -> Optional[SignatureProfile]:
        row = self.table.currentRow()
        if row < 0:
            if require:
                _message(self.dialog, "information", "Selecione um perfil de assinatura.")
            return None
        item = self.table.item(row, 0)
        profile_id = str(item.data(self._user_role()) or "") if item else ""
        profile = self.store.get(profile_id)
        if profile is None and require:
            _message(self.dialog, "warning", "O perfil selecionado não foi encontrado.")
        return profile

    def _profile_form(self, profile: Optional[SignatureProfile] = None) -> Optional[dict[str, str]]:
        W = self.widgets
        dialog = W.QDialog(self.dialog)
        dialog.setWindowTitle("Cadastro de assinatura")
        form = W.QFormLayout(dialog)
        name = W.QLineEdit(profile.name if profile else "")
        person = W.QLineEdit(profile.person_name if profile else "")
        role = W.QLineEdit(profile.role if profile else "")
        title = W.QLineEdit(profile.title if profile else "REDESPACHO")
        position = W.QComboBox()
        positions = [
            ("Carimbo oficial 85 x 32 mm", "official-stamp"),
            ("Personalizado pelo editor visual", "custom"),
            ("Padrão inclinado -6°", "reference-docs"),
            ("Campo Assinatura / Carimbo (legado)", "signature-field-legacy"),
            ("Superior esquerdo", "top-left"), ("Superior direito", "top-right"),
            ("Inferior esquerdo", "bottom-left"), ("Inferior direito", "bottom-right"),
        ]
        for label, value in positions:
            position.addItem(label, value)
        current_pos = (profile.position if profile else "official-stamp")
        for index in range(position.count()):
            if position.itemData(index) == current_pos:
                position.setCurrentIndex(index)
                break
        form.addRow("Nome do perfil", name)
        form.addRow("Responsável", person)
        form.addRow("Cargo / setor", role)
        form.addRow("Título no documento", title)
        form.addRow("Posição padrão", position)
        buttons = W.QDialogButtonBox(getattr(W.QDialogButtonBox, "StandardButton", W.QDialogButtonBox).Ok | getattr(W.QDialogButtonBox, "StandardButton", W.QDialogButtonBox).Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != W.QDialog.DialogCode.Accepted:
            return None
        if not name.text().strip() or not person.text().strip():
            _message(self.dialog, "warning", "Informe o nome do perfil e o responsável.")
            return None
        return {
            "name": name.text().strip()[:MAX_PROFILE_NAME],
            "person_name": person.text().strip()[:MAX_PERSON_NAME],
            "role": role.text().strip()[:MAX_PERSON_NAME],
            "title": title.text().strip()[:MAX_TITLE],
            "position": str(position.currentData() or "official-stamp"),
        }

    def new_profile(self):
        data = self._profile_form()
        if not data:
            return
        profile = self.store.create_profile(**data)
        self.refresh(profile.id)
        if _yes(self.dialog, "Cadastro criado. Gerar agora a folha em PDF para imprimir e assinar?"):
            self._generate_sheet(profile)

    def edit_profile(self):
        profile = self.selected_profile()
        if profile is None:
            return
        data = self._profile_form(profile)
        if not data:
            return
        for key, value in data.items():
            setattr(profile, key, value)
        self.store.upsert(profile)
        self.refresh(profile.id)

    def generate_sheet(self):
        profile = self.selected_profile()
        if profile:
            self._generate_sheet(profile)

    def _generate_sheet(self, profile: SignatureProfile):
        html_text = registration_sheet_html(profile)
        html_path = self.store.sheets / f"{_safe_filename(profile.id)}_cadastro.html"
        pdf_path = self.store.sheets / f"{_safe_filename(profile.id)}_cadastro.pdf"
        html_path.write_text(html_text, encoding="utf-8")
        try:
            html_file_to_pdf(html_path, pdf_path)
            _message(self.dialog, "information", f"Folha de cadastro gerada em:\n{pdf_path}\n\nImprima em tamanho A4, assine e importe a página digitalizada.")
            _open_path(pdf_path)
        except Exception as exc:
            _message(self.dialog, "warning", f"Não foi possível criar o PDF automaticamente:\n{exc}\n\nO HTML para impressão foi salvo em:\n{html_path}")
            _open_path(html_path)

    def import_signed_sheet(self):
        profile = self.selected_profile()
        if profile is None:
            return
        file_path, _ = self.widgets.QFileDialog.getOpenFileName(self.dialog, "Selecionar folha assinada", "", "PDF ou imagem (*.pdf *.jpg *.jpeg *.png *.bmp *.tif *.tiff)")
        if not file_path:
            return
        source = Path(file_path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_target = self.store.originals / f"{_safe_filename(profile.id)}_{stamp}{source.suffix.lower()}"
        processed_target = self.store.processed / f"{_safe_filename(profile.id)}_assinatura.png"
        preview_target = self.store.processed / f"{_safe_filename(profile.id)}_preview_{stamp}.png"
        try:
            shutil.copy2(source, original_target)
            result = process_signature_image(original_target, preview_target, threshold=profile.threshold)
        except Exception as exc:
            _message(self.dialog, "critical", f"Não foi possível tratar a assinatura:\n\n{exc}")
            return

        preview = self.widgets.QDialog(self.dialog)
        preview.setWindowTitle("Prévia da assinatura tratada")
        preview.resize(620, 360)
        layout = self.widgets.QVBoxLayout(preview)
        label = self.widgets.QLabel()
        label.setAlignment(getattr(getattr(self.core.Qt, "AlignmentFlag", self.core.Qt), "AlignCenter"))
        label.setPixmap(_preview_pixmap(preview_target, 560, 230))
        layout.addWidget(label, 1)
        description = self.widgets.QLabel(f"{result['detection']}\nBackend: {result.get('backend', image_backend_status()[0])}\nTamanho final: {result['width']} x {result['height']} px")
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = self.widgets.QDialogButtonBox(getattr(self.widgets.QDialogButtonBox, "StandardButton", self.widgets.QDialogButtonBox).Save | getattr(self.widgets.QDialogButtonBox, "StandardButton", self.widgets.QDialogButtonBox).Cancel)
        try:
            buttons.button(getattr(self.widgets.QDialogButtonBox, "StandardButton", self.widgets.QDialogButtonBox).Save).setText("Salvar")
            buttons.button(getattr(self.widgets.QDialogButtonBox, "StandardButton", self.widgets.QDialogButtonBox).Cancel).setText("Cancelar")
        except Exception:
            pass
        buttons.accepted.connect(preview.accept)
        buttons.rejected.connect(preview.reject)
        layout.addWidget(buttons)
        if preview.exec() != self.widgets.QDialog.DialogCode.Accepted:
            try:
                preview_target.unlink(missing_ok=True)
                original_target.unlink(missing_ok=True)
            except Exception:
                pass
            return
        try:
            preview_target.replace(processed_target)
        except Exception:
            shutil.copy2(preview_target, processed_target)
            preview_target.unlink(missing_ok=True)
        profile.original_file = str(original_target)
        profile.processed_file = str(processed_target)
        profile.original_sha256 = result["source_sha256"]
        self.store.upsert(profile)
        profile.last_used_at = datetime.now().isoformat(timespec="seconds")
        self.store.upsert(profile)
        self.refresh(profile.id)
        _message(self.dialog, "information", "Assinatura cadastrada, armazenada e pronta para uso.")

    def preview_signature(self):
        profile = self.selected_profile()
        if profile is None:
            return
        path = Path(profile.processed_file)
        if not path.exists():
            _message(self.dialog, "information", "Este perfil ainda não possui uma folha assinada importada.")
            return
        dialog = self.widgets.QDialog(self.dialog)
        dialog.setWindowTitle(f"Assinatura - {profile.name}")
        layout = self.widgets.QVBoxLayout(dialog)
        label = self.widgets.QLabel()
        label.setAlignment(getattr(getattr(self.core.Qt, "AlignmentFlag", self.core.Qt), "AlignCenter"))
        label.setPixmap(_preview_pixmap(path, 700, 340))
        layout.addWidget(label)
        close = self.widgets.QPushButton("Fechar")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    def delete_profile(self):
        profile = self.selected_profile()
        if profile is None:
            return
        if not _yes(self.dialog, f"Excluir o perfil '{profile.name}' e seus arquivos de assinatura?"):
            return
        self.store.delete(profile.id)
        self.refresh()

    def edit_signature_layout(self, profile: SignatureProfile, date_text: str = "", preview_infos: Optional[Iterable[dict[str, Any]]] = None) -> bool:
        if not profile.ready or not Path(profile.processed_file).exists():
            _message(self.dialog, "warning", "Importe a folha assinada antes de editar a posição.")
            return False
        editor = SignatureLayoutEditorDialog(self.dialog, profile, self.store, self.engine, date_text, preview_infos=preview_infos)
        accepted = editor.exec() == self.widgets.QDialog.DialogCode.Accepted
        if accepted: self.refresh(profile.id)
        return accepted

    def generate_pdfs(self):
        profile = self.selected_profile()
        if profile is None:
            return
        if not profile.ready or not Path(profile.processed_file).exists():
            _message(self.dialog, "warning", "Importe a folha assinada antes de gerar PDFs.")
            return
        infos, source = self.infos_provider()
        if not infos:
            _message(self.dialog, "information", "Nenhum XML marcado ou visível para gerar PDF.")
            return
        W = self.widgets
        dialog = W.QDialog(self.dialog)
        dialog.setWindowTitle("Assinar e gerar PDFs")
        dialog.resize(560, 350)
        layout = W.QVBoxLayout(dialog)
        heading = W.QLabel(f"{len(infos)} CT-e(s) {source}")
        heading.setStyleSheet("font-size:16px;font-weight:800;")
        layout.addWidget(heading)
        note = W.QLabel(f"Perfil: {profile.name} - {profile.person_name}\nAssinatura interna: {_layout_value(profile, 'signature_scale_percent', 100.0):.0f}%\nO XML fiscal original não será alterado.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = W.QFormLayout()
        date_edit = W.QLineEdit(datetime.now().strftime("%d/%m/%Y"))
        position = W.QComboBox()
        pos_values = [
            ("Carimbo oficial 85 x 32 mm", "official-stamp"),
            ("Personalizado pelo editor visual", "custom"),
            ("Padrão inclinado -6°", "reference-docs"),
            ("Campo Assinatura / Carimbo (legado)", "signature-field-legacy"),
            ("Superior esquerdo", "top-left"), ("Superior direito", "top-right"),
            ("Inferior esquerdo", "bottom-left"), ("Inferior direito", "bottom-right"),
        ]
        for label, value in pos_values: position.addItem(label, value)
        current_position = "official-stamp" if profile.position in ("signature-field", "") else profile.position
        for index in range(position.count()):
            if position.itemData(index) == current_position: position.setCurrentIndex(index); break
        edit_layout = W.QPushButton("Editar posição assinatura")
        edit_layout.setToolTip("Abre o primeiro CT-e real selecionado para posicionar o carimbo exatamente como sairá no PDF.")
        position_row = W.QHBoxLayout(); position_row.addWidget(position, 1); position_row.addWidget(edit_layout)
        stamp_size = W.QComboBox()
        for label, value in (("Oficial - 85 x 32 mm","official"),("Amplo - 76 x 28,6 mm","medium"),("Compacto - 68 x 25,6 mm","small"),("Personalizado pelo editor","custom")): stamp_size.addItem(label,value)
        saved_size = normalize_stamp_size(getattr(profile, "stamp_size", "official"))
        for index in range(stamp_size.count()):
            if stamp_size.itemData(index) == saved_size: stamp_size.setCurrentIndex(index); break
        output = W.QLineEdit(str(self.runtime_dir / "saida_pdf" / datetime.now().strftime("%Y-%m-%d_%H%M%S")))
        browse = W.QPushButton("Escolher pasta")
        output_row = W.QHBoxLayout(); output_row.addWidget(output, 1); output_row.addWidget(browse)
        individual = W.QCheckBox("Gerar PDFs separados e renomeados")
        batch = W.QCheckBox("Gerar um PDF único com todo o lote")
        individual.setChecked(True); batch.setChecked(True)
        form.addRow("Data impressa", date_edit)
        form.addRow("Posição", position_row)
        form.addRow("Tamanho do carimbo", stamp_size)
        form.addRow("Pasta de saída", output_row)
        form.addRow("", individual)
        form.addRow("", batch)
        layout.addLayout(form)
        buttons = W.QDialogButtonBox(getattr(W.QDialogButtonBox, "StandardButton", W.QDialogButtonBox).Ok | getattr(W.QDialogButtonBox, "StandardButton", W.QDialogButtonBox).Cancel)
        buttons.button(getattr(W.QDialogButtonBox, "StandardButton", W.QDialogButtonBox).Ok).setText("Gerar PDFs")
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def choose_folder():
            folder = W.QFileDialog.getExistingDirectory(dialog, "Selecionar pasta de saída", output.text())
            if folder:
                output.setText(folder)
        browse.clicked.connect(choose_folder)
        def open_layout_editor():
            if self.edit_signature_layout(profile, date_edit.text().strip(), preview_infos=infos):
                for i in range(position.count()):
                    if position.itemData(i)=="custom": position.setCurrentIndex(i); break
                for i in range(stamp_size.count()):
                    if stamp_size.itemData(i)=="custom": stamp_size.setCurrentIndex(i); break
        edit_layout.clicked.connect(open_layout_editor)
        def toggle_size_for_position():
            custom=str(position.currentData() or "")=="custom"; stamp_size.setEnabled(not custom)
            if custom:
                for i in range(stamp_size.count()):
                    if stamp_size.itemData(i)=="custom": stamp_size.setCurrentIndex(i); break
        position.currentIndexChanged.connect(toggle_size_for_position); toggle_size_for_position()
        if dialog.exec() != W.QDialog.DialogCode.Accepted:
            return
        if not individual.isChecked() and not batch.isChecked():
            _message(dialog, "warning", "Marque ao menos uma forma de geração.")
            return
        if not date_edit.text().strip():
            _message(dialog, "warning", "Informe a data que será impressa.")
            return
        try: datetime.strptime(date_edit.text().strip(), "%d/%m/%Y")
        except Exception:
            _message(dialog, "warning", "Informe a data no formato dd/mm/aaaa.")
            return
        if not _yes(dialog, f"Aplicar a assinatura '{profile.name}' em {len(infos)} CT-e(s) {source} e gerar os PDFs?\n\nTamanho do carimbo: {STAMP_SIZE_LABELS.get(str(stamp_size.currentData()), 'Oficial - 85 x 32 mm')}\nTamanho interno da assinatura: {_layout_value(profile, 'signature_scale_percent', 100.0):.0f}%\nOs XMLs fiscais originais permanecerão intactos."):
            return
        try:
            W.QApplication.setOverrideCursor(getattr(getattr(self.core.Qt, "CursorShape", self.core.Qt), "WaitCursor"))
            exporter = PdfBatchExporter(self.runtime_dir, self.engine, self.store)
            result = exporter.export(
                infos=infos,
                profile=profile,
                date_text=date_edit.text().strip(),
                output_root=Path(output.text().strip()),
                individuals=individual.isChecked(),
                batch=batch.isChecked(),
                position=str(position.currentData() or profile.position),
                stamp_size=str(stamp_size.currentData() or profile.stamp_size or "official"),
                source_description=source,
            )
        except Exception as exc:
            _message(dialog, "critical", f"Erro ao gerar PDFs:\n\n{exc}")
            return
        finally:
            try:
                W.QApplication.restoreOverrideCursor()
            except Exception:
                pass
        profile.last_used_at = datetime.now().isoformat(timespec="seconds")
        self.store.upsert(profile)
        generated = len(result["generated"])
        failures = len(result["failures"])
        _message(self.dialog, "information", f"Geração concluída.\n\nArquivos gerados: {generated}\nFalhas: {failures}\nPasta: {result['root']}")
        _open_path(result["root"])
        self.refresh(profile.id)


def _open_path(path: Path):
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            import webbrowser
            webbrowser.open(Path(path).resolve().as_uri())
    except Exception:
        pass


def install_cte_page_integration(
    defining_module: Any,
    CTePage: type,
    engine: Any,
    selected_infos_func: Callable[[Any], tuple[list[dict[str, Any]], str]],
    runtime_dir_func: Callable[[], Path],
) -> bool:
    """Instala uma ponte pequena na página XMLs do EXE."""
    if not isinstance(CTePage, type) or getattr(CTePage, "_assinatura_pdf_266518", False):
        return False
    previous_build_actions = getattr(CTePage, "build_actions", None)

    def action(self):
        try:
            runtime = Path(runtime_dir_func())
            infos_provider = lambda: selected_infos_func(self)
            SignatureManagerDialog(self, runtime, engine, infos_provider).exec()
        except Exception as exc:
            try:
                _message(self, "critical", f"Não foi possível abrir Assinaturas e PDF:\n\n{exc}")
            except Exception:
                pass

    def patched_build_actions(self, root, *args, **kwargs):
        result = previous_build_actions(self, root, *args, **kwargs) if callable(previous_build_actions) else None
        try:
            W, _, G = _qt()
            inserted = False
            for menu in self.findChildren(W.QMenu):
                actions = menu.actions()
                texts = [str(item.text() or "").strip() for item in actions]
                if not any(text in texts for text in ("Adicionar informação complementar", "Gerar HTML único dos marcados", "Gerar HTMLs dos marcados", "Auditar peso")):
                    continue
                if "Assinaturas e PDF" in texts:
                    inserted = True
                    break
                action_obj = G.QAction("Assinaturas e PDF", menu)
                action_obj.setToolTip("Cadastrar assinatura física digitalizada e gerar PDFs individuais ou em lote.")
                action_obj.triggered.connect(self.signature_pdf_action_266518)
                menu.addSeparator()
                menu.addAction(action_obj)
                inserted = True
                break
            # Fallback: adiciona ao primeiro menu disponível.
            if not inserted:
                menus = self.findChildren(W.QMenu)
                if menus:
                    action_obj = G.QAction("Assinaturas e PDF", menus[0])
                    action_obj.triggered.connect(self.signature_pdf_action_266518)
                    menus[0].addAction(action_obj)
        except Exception:
            pass
        return result

    CTePage.signature_pdf_action_266518 = action
    CTePage.build_actions = patched_build_actions
    CTePage._assinatura_pdf_266518 = True
    try:
        defining_module.APP_VERSION = "2.7.0 RC21 — Guarda Final do Cálculo Compacto"
    except Exception:
        pass
    return True


__all__ = [
    "VERSION", "SignatureProfile", "SignatureProfileStore", "PdfBatchExporter",
    "registration_sheet_html", "process_signature_image", "detect_registration_box", "image_backend_status",
    "inject_signature_html", "render_signed_html", "render_signed_batch_html",
    "find_browser", "html_file_to_pdf", "html_text_to_pdf", "cte_output_basename",
    "partner_name_from_info", "install_cte_page_integration",
]
