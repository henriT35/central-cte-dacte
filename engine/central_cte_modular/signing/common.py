from __future__ import annotations

import base64
import hashlib
import html
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Optional

VERSION = "2.6.67.9"
PROFILE_FILE = "perfis_assinatura.json"
MAX_PROFILE_NAME = 80
MAX_PERSON_NAME = 120
MAX_TITLE = 60
SIGNATURE_CSS_MARKER = "central-cte-signature-css-266518"
SIGNATURE_HTML_MARKER = 'data-central-signature="1"'

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
