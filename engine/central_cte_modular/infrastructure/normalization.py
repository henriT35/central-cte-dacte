from __future__ import annotations

import re
import unicodedata
from typing import Any

from .formatting import only_digits


def norm_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).upper().strip()


def norm_location(value: Any) -> str:
    """Normaliza municípios/rotas removendo acentos, hífens e pontuação.

    Exemplos equivalentes: ``Jaci-Paraná``, ``JACI PARANA`` e ``Jaci / Paraná``.
    A normalização fica restrita a campos geográficos para não alterar textos
    comerciais, observações ou identificadores.
    """
    text = norm_text(value)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_header(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", norm_text(value))


def normalize_nf(value: Any) -> str:
    digits = only_digits(value)
    if digits:
        return digits.lstrip("0") or "0"
    return norm_text(value)
