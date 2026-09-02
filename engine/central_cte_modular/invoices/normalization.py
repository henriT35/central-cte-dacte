from __future__ import annotations

from hashlib import sha256
import json
import re
import unicodedata
from typing import Any, Iterable


def strip_accents(value: Any) -> str:
    text = str(value or "")
    try:
        return "".join(char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn")
    except Exception:
        return text


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalize_token(value: Any) -> str:
    text = strip_accents(value).upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def clean_number(value: Any) -> str:
    raw = digits(value)
    return raw.lstrip("0") or ("0" if raw else "")


def normalize_invoice_number(value: Any) -> str:
    text = normalize_space(value)
    if not text:
        return ""
    patterns = (
        r"(?<!\d)(0*\d{3,9})\s*[-/]\s*(\d)(?!\d)",
        r"\bFAT(?:URA|UARA)?\.?\s*0*(\d{3,9})\s*[-/]\s*(\d)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return f"{(clean_number(match.group(1)) or '0').zfill(7)}-{match.group(2)}"
    return text


def invoice_key(value: Any) -> str:
    if isinstance(value, (int, float)):
        try:
            return str(int(value))
        except Exception:
            return ""
    text = normalize_space(value)
    if not text:
        return ""
    match = re.search(r"(?<!\d)0*(\d{1,9})\s*[-/]\s*\d(?!\d)", text)
    if match:
        return clean_number(match.group(1))
    match = re.search(r"(?<!\d)0*(\d{1,9})(?:[.,]0+)?(?!\d)", text)
    return clean_number(match.group(1)) if match else ""


def normalize_cte(value: Any) -> str:
    text = normalize_space(value)
    if not text or text.upper() in {"-", "NONE", "NAN", "NULL"}:
        return ""
    text = re.sub(r"\b(CT\s*-?\s*E|CTE|CTRC|SUBCONTRATO|ORIGEM)\b", "", text, flags=re.I)
    text = normalize_space(text.strip(" :-"))
    match = re.search(r"[A-Z]{2,8}\s*/?\s*0*(\d{3,12})\s*[-/]\s*(\d)", text, re.I)
    if match:
        return f"{clean_number(match.group(1))}-{match.group(2)}"
    match = re.search(r"\b0*(\d{3,12})\s*[-/]\s*(\d)\b", text)
    if match:
        return f"{clean_number(match.group(1))}-{match.group(2)}"
    match = re.search(r"(?:^|\s)\d{1,4}\s+0*(\d{5,12})(?:\s|$)", text)
    if match:
        return clean_number(match.group(1))
    match = re.search(r"\b0*(\d{3,12})\b", text)
    return clean_number(match.group(1)) if match else text


def cte_key(value: Any) -> str:
    normalized = normalize_cte(value)
    raw = digits(normalized)
    return raw.lstrip("0") or raw


def normalize_nf(value: Any) -> str:
    text = normalize_space(value)
    if not text or text.upper() in {"-", "NONE", "NAN", "NULL"}:
        return ""
    match = re.match(r"^\s*\d{1,3}\s+0*(\d{1,12})\s*$", text)
    if match:
        return clean_number(match.group(1))
    match = re.search(r"\b0*(\d{1,12})\b", text)
    return clean_number(match.group(1)) if match else text


def nf_key(value: Any) -> str:
    normalized = normalize_nf(value)
    raw = digits(normalized)
    return raw.lstrip("0") or raw


def parse_money(value: Any) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return round(float(value or 0.0), 2)
    text = normalize_space(value).replace("R$", "").strip()
    if not text or text.upper() in {"-", "NONE", "NAN", "NULL"}:
        return 0.0
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    text = re.sub(r"[^0-9,.-]+", "", text)
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        number = float(text)
    except Exception:
        return 0.0
    return round(-number if negative else number, 2)


def normalize_status(value: Any) -> str:
    return re.sub(r"\s+", " ", strip_accents(value).upper()).strip()


def is_problem_status(value: Any) -> bool:
    status = normalize_status(value)
    if not status:
        return True
    if status == "OK" or status.startswith("OK COMPLEMENTAR") or status == "OK PAGAR":
        return False
    problem_tokens = (
        "SEM COMPROVANTE",
        "FORA DA BASE",
        "DIVERG",
        "REVISAR",
        "NAO PAGAR",
        "ERRO",
        "NAO VALIDADO",
        "PENDENTE",
        "AMBIG",
    )
    if any(token in status for token in problem_tokens):
        return True
    # Em modo sombra, status desconhecido é tratado como revisão. A camada não
    # altera pagamento, apenas impede que uma novidade passe silenciosamente.
    return not status.startswith("OK")


def canonical_invoice_status(item_count: int, ok_count: int, problem_count: int) -> str:
    if item_count <= 0:
        return "REVISAR PARSER"
    if problem_count <= 0:
        return "OK PAGAR"
    if ok_count > 0:
        return "PAGAR PARCIAL"
    return "NÃO PAGAR"


def stable_hash(parts: Iterable[Any]) -> str:
    payload = json.dumps(list(parts), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def status_equal(left: Any, right: Any) -> bool:
    return normalize_status(left) == normalize_status(right)
