from __future__ import annotations

"""Política de componentes financeiros opcionais do CT-e.

A RC24 torna o cálculo do pedágio independente do parceiro. A mesma função
respeita a modalidade cadastrada na regra: por CT-e ou por fração de peso.
"""

import math
import re
import unicodedata
from typing import Any, Mapping


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().upper() in {"S", "SIM", "YES", "TRUE", "1", "ATIVO", "OK"}


def _normalize_mode(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).upper()
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def _toll_mode(kind: Any, fraction: float) -> str:
    """Resolve a modalidade com prioridade para declarações explícitas.

    Uma regra declarada como ``CTE`` nunca pode virar regra por peso apenas
    porque algum enriquecedor legado inseriu uma fração padrão de 100 kg.
    """

    normalized = _normalize_mode(kind)
    compact = normalized.replace(" ", "")
    explicit_cte = (
        compact in {"CTE", "CTRC", "CONHECIMENTO", "EMISSAO"}
        or "POR CTE" in normalized
        or "POR CONHECIMENTO" in normalized
        or "POR EMISSAO" in normalized
    )
    if explicit_cte:
        return "CTE"
    explicit_weight = any(token in normalized for token in ("KG", "PESO", "FRACAO"))
    return "KG" if explicit_weight or fraction > 0 else "CTE"


def validar_componente_opcional(
    nome: str,
    valor_cobrado: Any,
    valor_esperado_quando_cobrado: Any,
    tolerancia: Any = 1.0,
) -> dict[str, Any]:
    charged = _float(valor_cobrado)
    expected = _float(valor_esperado_quando_cobrado)
    tolerance = max(0.0, _float(tolerancia))
    difference = charged - expected
    if charged <= 0:
        return {
            "nome": nome,
            "cobrado": False,
            "ignorado": True,
            "esperado": 0.0,
            "diferenca": 0.0,
            "status": "OPCIONAL NÃO COBRADO — IGNORADO",
        }
    if abs(difference) <= tolerance:
        status = "COMPONENTE OPCIONAL OK"
    elif difference > 0:
        status = "DIVERGENTE COMPONENTE OPCIONAL +"
    else:
        status = "DIVERGENTE COMPONENTE OPCIONAL -"
    return {
        "nome": nome,
        "cobrado": True,
        "ignorado": False,
        "esperado": expected,
        "diferenca": difference,
        "status": status,
    }


def calcular_pedagio_regra(
    regra: Mapping[str, Any] | None,
    valor_cobrado_xml: Any,
    *,
    peso_kg: Any = 0.0,
    tolerancia: Any = 1.0,
) -> dict[str, Any]:
    """Calcula e audita o pedágio conforme a regra comercial selecionada.

    Modos suportados:
    - ``CTE``: uma tarifa por conhecimento;
    - ``KG``: teto(peso / fração) multiplicado pela tarifa da fração.

    O componente continua opcional: quando não é cobrado no XML, não é somado
    ao esperado. Se for cobrado sem peso disponível em uma regra por KG, o
    resultado pede revisão em vez de fingir que uma única fração é suficiente.
    """

    rule = regra or {}
    configured = _float(rule.get("valor_pedagio") or rule.get("pedagio_valor"))
    active = _enabled(rule.get("pedagio_ativo")) or configured > 0
    charged = _float(valor_cobrado_xml)
    kind = rule.get("tipo_pedagio") or rule.get("pedagio_tipo") or ""
    fraction = _float(rule.get("fracao_pedagio_kg") or rule.get("pedagio_fracao_kg"))
    weight = _float(peso_kg)
    mode = _toll_mode(kind, fraction)

    base = {
        "configurado": configured,
        "tipo": mode,
        "fracao_kg": (fraction or 100.0) if mode == "KG" else 0.0,
        "peso_kg": weight,
        "quantidade": 0,
    }

    if charged <= 0:
        result = validar_componente_opcional("PEDÁGIO", 0.0, 0.0, tolerancia)
        result.update(base)
        result["detalhe"] = "pedágio opcional ausente no XML; não somado ao valor esperado"
        return result

    if not active or configured <= 0:
        result = validar_componente_opcional("PEDÁGIO", charged, 0.0, tolerancia)
        result.update(base)
        result.update({
            "status": "PEDÁGIO COBRADO — SEM REGRA ATIVA",
            "revisar": True,
            "detalhe": "pedágio cobrado no XML, mas a regra selecionada não possui tarifa ativa",
        })
        return result

    is_weight_rule = mode == "KG"
    if is_weight_rule:
        fraction = fraction or 100.0
        base["tipo"] = "KG"
        base["fracao_kg"] = fraction
        if weight <= 0:
            result = validar_componente_opcional("PEDÁGIO", charged, 0.0, tolerancia)
            result.update(base)
            result.update({
                "status": "PEDÁGIO COBRADO — REVISAR PESO",
                "revisar": True,
                "detalhe": f"regra por fração de {fraction:g} kg, mas o peso não está disponível",
            })
            return result
        units = int(math.ceil((weight - 1e-9) / fraction))
        expected = units * configured
        detail = f"teto({weight:g}/{fraction:g}) = {units} fração(ões) de {fraction:g} kg"
    else:
        units = 1
        expected = configured
        detail = "1 CT-e"
        base["tipo"] = "CTE"
        base["fracao_kg"] = 0.0

    result = validar_componente_opcional("PEDÁGIO", charged, expected, tolerancia)
    base["quantidade"] = units
    result.update(base)
    result.update({"detalhe": detail, "revisar": False})
    return result


def calcular_pedagio_jsp(
    regra: Mapping[str, Any] | None,
    valor_cobrado_xml: Any,
    *,
    peso_kg: Any = 0.0,
    tolerancia: Any = 1.0,
) -> dict[str, Any]:
    """Alias compatível. O cálculo agora é genérico para qualquer parceiro."""

    return calcular_pedagio_regra(
        regra,
        valor_cobrado_xml,
        peso_kg=peso_kg,
        tolerancia=tolerancia,
    )


__all__ = [
    "validar_componente_opcional",
    "calcular_pedagio_regra",
    "calcular_pedagio_jsp",
]
