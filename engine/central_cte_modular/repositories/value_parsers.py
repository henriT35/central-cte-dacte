from __future__ import annotations

import re
from typing import Any

from ..infrastructure.normalization import norm_text, normalize_header


def parse_number_br(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("\xa0", " ").strip()
    text = re.sub(r"[^0-9,\.\-]", "", text)
    if not text or text in {"-", ".", ","}:
        return 0.0
    negative = text.startswith("-")
    text = text.replace("-", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif "." in text:
        parts = text.split(".")
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]) and len(parts[0]) <= 3:
            text = "".join(parts)
    try:
        number = float(text)
        return -number if negative else number
    except Exception:
        return 0.0


def parse_percent(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    raw = str(value).strip()
    number = parse_number_br(value)
    if "%" in raw or number > 1:
        return number / 100.0
    return number


def parse_optional_single_money(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    if re.search(r"\d\s*[\/;]\s*\d", raw):
        return 0.0
    if re.search(r"\d\s+(A|ATE|ATÉ)\s+\d", norm_text(raw)):
        return 0.0
    return parse_number_br(raw)


def safe_get(row: list[Any] | tuple[Any, ...], index: int | None) -> Any:
    if index is None or index < 0 or index >= len(row):
        return ""
    return row[index]


def rows_to_dicts(rows: list[list[Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not rows:
        return [], {}
    headers = [str(header or "").strip() for header in rows[0]]
    index = {normalize_header(header): position for position, header in enumerate(headers) if str(header or "").strip()}
    records: list[dict[str, Any]] = []
    for row in rows[1:]:
        if not any(str(value or "").strip() for value in row):
            continue
        records.append({header: safe_get(row, position) for header, position in index.items()})
    return records, index


def pick_col(index: dict[str, int], *names: str) -> int | None:
    for name in names:
        key = normalize_header(name)
        if key in index:
            return index[key]
    return None


def normalize_base_calculo(value: Any) -> str:
    text = norm_text(value or "ORIGINAL")
    if not text:
        return "ORIGINAL"
    text = text.replace("-", " ").replace("_", " ")
    if ("SEM" in text and "ICMS" in text) or ("FRETE" in text and "SEMICMS" in text):
        return "SEM_ICMS"
    if "MERCADORIA" in text or "VALOR CARGA" in text or "VALOR DA CARGA" in text:
        return "MERCADORIA"
    if "ORIGEM" in text:
        return "ORIGEM"
    return "ORIGINAL"
