from __future__ import annotations

"""Classificação fiscal e operacional de CT-e sem colisões de substring.

O tipo fiscal pertence ao campo estruturado ``ide/tpCTe``. Cobranças extras
são uma dimensão separada e só podem nascer de componentes financeiros ou de
campos operacionais confiáveis; descrição da mercadoria e natureza da operação
não participam da decisão.
"""

import re
import unicodedata
from typing import Any, Mapping


FISCAL_TYPES = {
    "0": "NORMAL",
    "1": "COMPLEMENTAR",
    "2": "ANULACAO",
    "3": "SUBSTITUICAO",
}

_FISCAL_LABELS = {
    "NORMAL": "NORMAL",
    "COMPLEMENTO": "COMPLEMENTAR",
    "COMPLEMENTAR": "COMPLEMENTAR",
    "ANULACAO": "ANULACAO",
    "SUBSTITUICAO": "SUBSTITUICAO",
}


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.upper().split())


def _number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace("R$", "").replace(" ", "")
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return 0.0


def buscar_sigla_como_token(texto: Any, sigla: str) -> bool:
    """Localiza sigla como token alfanumérico completo.

    ``TDE`` casa com ``ENTREGA (TDE)``, mas não com ``QTDE``.
    """

    normalized = _normalize(texto)
    wanted = re.escape(_normalize(sigla))
    return bool(wanted and re.search(rf"(?<![A-Z0-9]){wanted}(?![A-Z0-9])", normalized))


def resolve_tipo_cte_oficial(info: Mapping[str, Any] | None) -> dict[str, str]:
    """Resolve exclusivamente o tipo fiscal oficial do CT-e."""

    source = info or {}
    raw_code = str(source.get("tpCTe_codigo") or "").strip()
    raw_label = str(source.get("tpCTe") or "").strip()

    if raw_code in FISCAL_TYPES:
        fiscal_type = FISCAL_TYPES[raw_code]
        return {
            "codigo": raw_code,
            "tipo": fiscal_type,
            "fonte": "XML ide/tpCTe",
            "gatilho": f"tpCTe={raw_code}",
        }

    if raw_label in FISCAL_TYPES:
        fiscal_type = FISCAL_TYPES[raw_label]
        return {
            "codigo": raw_label,
            "tipo": fiscal_type,
            "fonte": "XML ide/tpCTe",
            "gatilho": f"tpCTe={raw_label}",
        }

    normalized_label = _normalize(raw_label)
    fiscal_type = _FISCAL_LABELS.get(normalized_label)
    if fiscal_type:
        reverse_code = next((code for code, name in FISCAL_TYPES.items() if name == fiscal_type), "")
        return {
            "codigo": reverse_code,
            "tipo": fiscal_type,
            "fonte": "XML ide/tpCTe (rótulo normalizado)",
            "gatilho": f"tpCTe={raw_label or normalized_label}",
        }

    return {
        "codigo": "",
        "tipo": "NORMAL",
        "fonte": "fallback seguro: tpCTe ausente ou inválido",
        "gatilho": "nenhum tipo fiscal especial confirmado",
    }


def _charge_context(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "COBRANCA", "COBRADO", "COBRAR", "CUSTO EXTRA", "TAXA ",
            "VALOR DE ", "VALOR DA ", "PAGAMENTO DE ", "FRETE COMPLEMENTAR",
            "ADICIONAL DE ", "REEMBOLSO",
        )
    )


def _detect_from_text(text: str, *, structured_component: bool = False) -> str:
    if "COTACAO" in text and "AUTORIZ" in text:
        return "COTACAO_AUTORIZADA"
    if "FRETE REF" in text and (buscar_sigla_como_token(text, "COT") or "COTACAO" in text):
        return "COTACAO_ESPECIAL"
    if buscar_sigla_como_token(text, "TDA") or "DIFICULDADE DE ACESSO" in text:
        return "TDA"
    if buscar_sigla_como_token(text, "TDE") or "DIFICULDADE DE ENTREGA" in text:
        return "TDE"
    if "TABELA ANTIGA" in text or "FRETE ANTIGO" in text:
        return "TABELA_ANTIGA"
    if "REEMBOLSO" in text and "DESCARG" in text:
        return "REEMBOLSO_DESCARGA"
    if "TPD DESCARG" in text:
        return "REEMBOLSO_DESCARGA"
    if "TEMPO EXCEDIDO" in text or "PERMANENCIA EXCEDIDA" in text or "CUSTO EXTRA 5" in text:
        return "TEMPO_EXCEDIDO"
    if any(token in text for token in ("REENTREGA", "REEENTREGA", "RE ENTREGA", "SEGUNDA ENTREGA")):
        return "REENTREGA"

    charge_context = structured_component or _charge_context(text)
    if charge_context and ("DEVOLUCAO" in text or "RETORNO DE MERCADORIA" in text):
        return "DEVOLUCAO"
    if charge_context and "CAPATAZIA" in text:
        return "CAPATAZIA"
    if charge_context and "DESCARG" in text:
        return "REEMBOLSO_DESCARGA"
    if charge_context and ("FRETE COMPLEMENTAR" in text or buscar_sigla_como_token(text, "COMPL")):
        return "COMPLEMENTAR"
    if charge_context and "VEICULO DEDICADO" in text:
        return "VEICULO_DEDICADO"
    return ""


def detectar_cobranca_extra(info: Mapping[str, Any] | None) -> dict[str, str]:
    """Detecta cobrança extra sem ler produto, natureza fiscal ou CFOP."""

    source = info or {}
    for component in source.get("componentes", []) or []:
        name = _normalize((component or {}).get("nome", ""))
        value = _number((component or {}).get("valor", ""))
        if value <= 0:
            continue
        detected = _detect_from_text(name, structured_component=True)
        if detected:
            return {
                "tipo": detected,
                "fonte": "componente financeiro do CT-e",
                "campo": "componentes/vComp",
                "gatilho": f"{name} = {value:.2f}",
                "mensagem": f"{detected} — COMPONENTE FINANCEIRO CONFIRMADO",
            }

    trusted_fields = (
        "obs_cobranca",
        "info_complementar_operacional",
        "observacoes_operacionais",
        "obs_principal",
        "uso_exclusivo",
        "obs",
    )
    seen: set[str] = set()
    for field in trusted_fields:
        raw = str(source.get(field) or "").strip()
        normalized = _normalize(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        detected = _detect_from_text(normalized)
        if detected:
            return {
                "tipo": detected,
                "fonte": "observação operacional confiável",
                "campo": field,
                "gatilho": normalized[:240],
                "mensagem": f"{detected} — INDÍCIO OPERACIONAL CONFIÁVEL",
            }

    return {
        "tipo": "NORMAL",
        "fonte": "nenhum campo confiável acionou cobrança extra",
        "campo": "",
        "gatilho": "",
        "mensagem": "NORMAL — SEM INDÍCIO CONFIÁVEL DE EXTRA",
    }


def explicar_classificacao(info: Mapping[str, Any] | None) -> dict[str, str]:
    fiscal = resolve_tipo_cte_oficial(info)
    extra = detectar_cobranca_extra(info)
    operational_type = extra["tipo"] if extra["tipo"] != "NORMAL" else fiscal["tipo"]
    return {
        "tipo_fiscal": fiscal["tipo"],
        "codigo_tpcte": fiscal["codigo"],
        "fonte_tipo_fiscal": fiscal["fonte"],
        "gatilho_tipo_fiscal": fiscal["gatilho"],
        "tipo_extra": extra["tipo"],
        "fonte_tipo_extra": extra["fonte"],
        "campo_tipo_extra": extra["campo"],
        "gatilho_tipo_extra": extra["gatilho"],
        "mensagem_extra": extra["mensagem"],
        "tipo_operacional": operational_type,
    }


__all__ = [
    "buscar_sigla_como_token",
    "resolve_tipo_cte_oficial",
    "detectar_cobranca_extra",
    "explicar_classificacao",
]
