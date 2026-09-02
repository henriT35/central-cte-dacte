from __future__ import annotations

import re
from typing import Any


def only_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def extract_cnpjs(value: Any) -> list[str]:
    text = str(value or "")
    if not text.strip():
        return []
    found: list[str] = []
    for match in re.findall(r"\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2}", text):
        digits = only_digits(match)
        if len(digits) == 14 and digits not in found:
            found.append(digits)
    if not found:
        digits = only_digits(text)
        if len(digits) == 14:
            found.append(digits)
    return found


def format_cnpj_cpf(value: Any) -> str:
    digits = only_digits(value)
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    if len(digits) == 11:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"
    return value or ""


def format_cep(value: Any) -> str:
    digits = only_digits(value)
    if len(digits) == 8:
        return f"{digits[:5]}-{digits[5:]}"
    return value or ""


def money(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(str(value).replace(',', '.')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def money_float(value: Any) -> float:
    try:
        return float(str(value or "0").replace(",", "."))
    except Exception:
        return 0.0


def qty(value: Any, casas: int = 4) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(str(value).replace(',', '.')):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def date_br(value: Any) -> str:
    if not value:
        return ""
    try:
        return f"{value[8:10]}/{value[5:7]}/{value[0:4]} {value[11:19]}"
    except Exception:
        return value


def format_chave(value: Any) -> str:
    digits = only_digits(value)
    return " ".join(digits[index:index + 4] for index in range(0, len(digits), 4))
