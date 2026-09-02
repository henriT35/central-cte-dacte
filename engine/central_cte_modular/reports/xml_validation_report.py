from __future__ import annotations

"""Consolidação RC26.6 do relatório executivo de validação dos XMLs de CT-e.

Este módulo não classifica nem recalcula o frete. Ele transforma a fotografia
final produzida pelo motor em quatro visões de relatório e corrige somente a
auditoria separada do pedágio quando o próprio resultado comercial já contém
o valor completo da regra aplicada.
"""

from dataclasses import dataclass, field
from datetime import datetime
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .xlsx_openxml import Formula
from .xml_validation_xlsx import XmlValidationXlsxWriter


REPORT_VERSION = "2.7.0-RC26.6"
LEGACY_AUDIT_COLUMN_COUNT = 60


AUDIT_HEADERS: tuple[str, ...] = (
    "Status", "CT-e", "Série", "Parceiro XML", "CNPJ Parceiro", "NF",
    "Validação Parcial", "NFs Ignoradas", "Destinatário",
    "Cidade/UF Destino XML", "Valor Total XML", "Valor Comparado XML",
    "Componente Comparado", "Frete Base", "Base Cálculo", "Modo Cálculo",
    "Peso Base KG", "R$/Ton", "R$/KG", "Frete Peso Calc.",
    "Adicionais XML", "Percentual", "Frete Mínimo", "Valor Esperado",
    "Diferença", "Tolerância", "Parceiro ID", "Tipo cobrança extra",
    "Regra extra", "Detalhe", "Revisão manual", "Observação manual",
    "Data revisão", "Diagnóstico", "Fonte Peso XML", "Pesos XML",
    "Peso Reverso KG", "Dif. Peso KG", "Auditoria Peso", "Obs. Peso",
    "Arquivo XML", "Caminho", "Tipo fiscal oficial", "Código tpCTe",
    "Fonte tipo fiscal", "Gatilho tipo fiscal", "Cobrança extra detectada",
    "Campo da cobrança extra", "Texto/gatilho da cobrança extra",
    "Fonte da cobrança extra", "Explicação da classificação",
    "Destino comercial utilizado", "Regra comercial aplicada",
    "Componentes cobrados no XML", "Componentes opcionais ignorados",
    "Pedágio cobrado XML", "Pedágio esperado se cobrado",
    "Diferença pedágio", "Status pedágio", "Detalhe pedágio",
    "Fonte do Frete Base / Receita", "Fonte do Frete Cobrado",
    "Lucro Bruto Estimado", "Margem Bruta Estimada",
    "Classificação da Margem", "Memória da Rentabilidade",
)

DETAIL_HEADERS: tuple[str, ...] = (
    "CT-e", "Parceiro", "CNPJ", "NF", "Emissão", "Origem",
    "Destino XML", "Destino comercial", "Peso (kg)", "Valor da mercadoria",
    "Valor Total do CT-e", "Valor Comparado", "Componente Comparado",
    "Valor Esperado", "Diferença", "Pedágio cobrado", "Pedágio esperado",
    "Regra aplicada", "Status", "Motivo", "Frete Base / Receita",
    "Frete Cobrado pelo Parceiro", "Lucro Bruto Estimado",
    "Margem Bruta Estimada", "Classificação da Margem",
)

ATTENTION_HEADERS: tuple[str, ...] = (
    "CT-e", "Parceiro", "CNPJ", "NF", "Origem", "Destino comercial",
    "Valor do CT-e", "Valor esperado", "Diferença", "Status",
    "Tipo do alerta", "Motivo", "Regra aplicada", "Ação recomendada",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value).upper())
    return re.sub(r"\s+", " ", "".join(ch for ch in text if not unicodedata.combining(ch))).strip()


def _number(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        try:
            return default if math.isnan(float(value)) else float(value)
        except Exception:
            return default
    text = _text(value).replace("R$", "").replace("%", "").replace("\u00a0", " ")
    text = re.sub(r"[^0-9,.-]", "", text)
    if not text:
        return default
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except Exception:
        return default


def _money_br(value: Any) -> str:
    number = _number(value)
    signal = "-" if number < 0 else ""
    integer, decimal = f"{abs(number):,.2f}".split(".")
    return f"{signal}R$ {integer.replace(',', '.')},{decimal}"


def _margin_class(base: float | None, cost_present: bool, margin: float | None,
                  low: float = 0.10, high: float = 0.25) -> str:
    if not cost_present:
        return "SEM DADOS"
    if base is None or base <= 0.0 or margin is None:
        return "SEM FRETE BASE"
    if margin < 0.0:
        return "MARGEM NEGATIVA"
    if margin < low:
        return "MARGEM BAIXA"
    if margin < high:
        return "MARGEM SAUDÁVEL"
    return "MARGEM ALTA"


def _nf_from_info(info: Mapping[str, Any]) -> str:
    result = info.get("validacao") or {}
    if _text(result.get("nf")):
        return _text(result.get("nf"))
    values: list[str] = []
    for doc in info.get("docs") or []:
        value = _text((doc or {}).get("n_doc") or (doc or {}).get("numero"))
        if value and value not in values:
            values.append(value)
    return ", ".join(values)


def _fallback_audit_row(info: Mapping[str, Any]) -> list[Any]:
    """Espelha as 60 colunas históricas quando o callback legado não existe."""

    result = info.get("validacao") or {}
    emit = info.get("emit") or {}
    dest = info.get("dest") or {}
    trace = " | ".join(_text(item) for item in (result.get("trace") or []) if _text(item))
    ignored = list(result.get("nfs_nao_encontradas") or [])
    ignored.extend(f"{nf} (INCOMPATÍVEL)" for nf in (result.get("nfs_incompativeis") or []))
    return [
        result.get("status") or "NÃO VALIDADO",
        info.get("numero", ""), info.get("serie", ""), info.get("emitente", ""),
        emit.get("cnpjcpf", ""), _nf_from_info(info),
        "SIM" if result.get("validacao_parcial") else "", ", ".join(map(str, ignored)),
        info.get("destinatario", ""), dest.get("mun", ""), _number(info.get("valor")),
        result.get("valor_comparado"), result.get("componente_comparado", ""),
        result.get("base_frete"), result.get("base_calculo", ""),
        result.get("modo_calculo", ""), result.get("peso_base_kg"),
        result.get("tonelagem_taxa"), result.get("taxa_kg"),
        result.get("frete_peso_calculado"), result.get("adicionais_xml"),
        result.get("percentual"), result.get("frete_minimo"), result.get("esperado"),
        result.get("diferenca"), result.get("tolerancia"), result.get("partner_id", ""),
        result.get("tipo_cobranca", ""), result.get("regra_extra", ""),
        result.get("detalhe", ""), info.get("revisao_manual", ""),
        info.get("observacao_manual", ""), info.get("revisao_data", ""), trace,
        result.get("peso_xml_fonte", ""), result.get("peso_xml_todos", ""),
        result.get("peso_reverso_kg"), result.get("dif_peso_kg"),
        result.get("auditoria_peso_status", ""), result.get("auditoria_peso_obs", ""),
        info.get("arquivo", ""), info.get("path", ""),
        result.get("tipo_fiscal_oficial", info.get("tpCTe", "")),
        result.get("codigo_tpcte", info.get("tpCTe_codigo", "")),
        result.get("fonte_tipo_fiscal", info.get("tpCTe_fonte", "")),
        result.get("gatilho_tipo_fiscal", ""), result.get("tipo_cobranca_extra", "NORMAL"),
        result.get("campo_tipo_extra", ""), result.get("gatilho_tipo_extra", ""),
        result.get("fonte_tipo_extra", ""),
        result.get("explicacao_classificacao", "NORMAL — SEM INDÍCIO CONFIÁVEL DE EXTRA"),
        result.get("destino_comercial", ""), result.get("regra_comercial", ""),
        result.get("componentes_cobrados_xml", ""),
        result.get("componentes_opcionais_ignorados", ""),
        result.get("pedagio_componente_cobrado"),
        result.get("pedagio_componente_esperado"),
        result.get("pedagio_componente_diferenca"),
        result.get("pedagio_componente_status", ""),
        result.get("pedagio_componente_detalhe", ""),
    ]


def is_approved(status: Any) -> bool:
    return _norm(status).startswith("OK")


def operational_status(status: Any) -> str:
    normalized = _norm(status)
    if normalized.startswith("OK"):
        return "OK PARA PAGAMENTO"
    critical = (
        "DIVERGENTE", "NAO PAGAR", "REGRA NAO", "SEM REGRA", "PARCEIRO SEM",
        "ROTA INVALIDA", "ORIGINAL NAO", "DOCUMENTO FORA", "NF FORA",
        "NF NAO", "SEM BASE", "COMPROVANTE INVALIDO", "SEM COMPROVANTE",
        "FALHA", "ERRO", "INCONSISTENCIA",
    )
    if any(token in normalized for token in critical):
        return "PROBLEMA INTERNO / CONFERÊNCIA"
    review = ("REVISAR", "REVISAO", "PENDENTE", "CONFERIR", "INFORMATIVO", "IGNORADO", "ANULACAO")
    if any(token in normalized for token in review):
        return "PROBLEMA INTERNO / CONFERÊNCIA"
    return "PROBLEMA INTERNO / CONFERÊNCIA"


def _critical_status(status: Any) -> bool:
    normalized = _norm(status)
    return any(token in normalized for token in (
        "DIVERGENTE", "REGRA NAO", "SEM REGRA", "PARCEIRO SEM",
        "ROTA INVALIDA", "ORIGINAL NAO", "DOCUMENTO FORA", "NF FORA",
        "NF NAO", "SEM BASE", "COMPROVANTE INVALIDO", "SEM COMPROVANTE",
        "FALHA", "ERRO", "INCONSISTENCIA",
    ))


def _rule_not_found(
    status: Any,
    audit: Mapping[str, Any],
    result: Mapping[str, Any],
) -> bool:
    """Identifica ausência explícita de regra sem inventar valores dependentes."""

    normalized = _norm(status)
    if any(token in normalized for token in (
        "REGRA NAO ENCONTRADA", "SEM REGRA", "PARCEIRO SEM TABELA",
    )):
        return True
    rule = _norm(
        audit.get("Regra comercial aplicada")
        or result.get("regra_comercial")
        or result.get("regra_aplicada")
    )
    return rule in {"NAO ENCONTRADA", "REGRA NAO ENCONTRADA"}


def _partner_label(info: Mapping[str, Any], audit: Mapping[str, Any]) -> str:
    partner_id = _text(audit.get("Parceiro ID"))
    known = {
        "W_S_TRANSPORTES": "W S Transportes",
        "MB_SERVICOS_LOG": "MB Serviços",
        "MF_LOBATO": "MF Lobato",
        "MILAYDE_LOBATO": "Milayde Patricia",
        "MRV_TRANSPORTES": "MRV Transportes",
        "EUNUQUES_LOPES": "Eunuques Lopes",
        "GN_NORTE": "GN Norte",
        "JSP": "JSP",
        "FENIX": "Fênix",
    }
    if partner_id in known:
        return known[partner_id]
    name = _text(audit.get("Parceiro XML") or info.get("emitente") or partner_id)
    if not name:
        return "Não identificado"
    common_suffixes = (
        " TRANSPORTES DE CARGAS E LOGISTICA LTDA", " TRANSPORTES E LOGISTICA LTDA",
        " SERVICOS DE TRANSPORTES E LOGISTICA LTDA", " LTDA", " EIRELI", " - ME",
    )
    cleaned = name
    for suffix in common_suffixes:
        if _norm(cleaned).endswith(_norm(suffix)):
            cleaned = cleaned[: -len(suffix)].strip()
            break
    return cleaned[:42]


@dataclass(frozen=True)
class TollAudit:
    charged: float
    expected: float
    difference: float
    status: str
    detail: str
    corrected_false_divergence: bool = False


def resolve_toll_audit(info: Mapping[str, Any]) -> TollAudit:
    """Resolve a auditoria com os mesmos dados da regra aplicada pelo motor.

    ``pedagio_regra`` é o valor integral calculado pelo validador (por CT-e,
    por fração ou pela regra específica). ``pedagio_componente_esperado`` era
    apenas o valor unitário no caminho RC21 para parceiros não JSP. A prioridade
    abaixo evita transformar R$ 3,50 em regra global e preserva JSP e rotas sem
    pedágio exatamente como foram calculadas.
    """

    result = info.get("validacao") or {}
    charged = _number(result.get("pedagio_componente_cobrado"))
    if charged <= 0:
        charged = _number(result.get("pedagio_xml_separado"))
    prior_expected = _number(result.get("pedagio_componente_esperado"))
    prior_status = _text(result.get("pedagio_componente_status"))
    tolerance = max(0.0, _number(result.get("tolerancia"), 1.0))
    partner_id = _norm(result.get("partner_id"))
    detail = _text(result.get("pedagio_detalhe") or result.get("pedagio_componente_detalhe"))

    if charged <= 0:
        return TollAudit(
            charged=0.0,
            expected=0.0,
            difference=0.0,
            status="OPCIONAL NÃO COBRADO — IGNORADO",
            detail=detail or "Pedágio não cobrado no XML; nenhum valor foi inventado.",
        )

    if partner_id == "JSP":
        expected = prior_expected
    else:
        explicit_rule_value = result.get("pedagio_regra")
        if explicit_rule_value not in (None, ""):
            expected = _number(explicit_rule_value)
        else:
            expected = prior_expected
            fraction_match = re.search(r"(\d+)\s+fracao\(oes\)", _norm(detail))
            if fraction_match and int(fraction_match.group(1)) > 1 and prior_expected > 0:
                expected = prior_expected * int(fraction_match.group(1))
            else:
                trace_text = " | ".join(_text(item) for item in (result.get("trace") or []))
                compact_match = re.search(
                    r"PEDAGIO:\s*(\d+)\s*[X×]\s*([\d.,]+)\s*=",
                    _norm(trace_text),
                )
                if compact_match:
                    units = int(compact_match.group(1))
                    unit_value = _number(compact_match.group(2))
                    expected = units * unit_value
                    detail = detail or f"{units} fração(ões) × {_money_br(unit_value)}"

    difference = charged - expected
    if abs(difference) <= tolerance:
        status = "COMPONENTE OPCIONAL OK"
    elif difference > 0:
        status = "DIVERGENTE COMPONENTE OPCIONAL +"
    else:
        status = "DIVERGENTE COMPONENTE OPCIONAL -"

    corrected = (
        abs(expected - prior_expected) > 0.005
        and _norm(prior_status).startswith("DIVERGENTE COMPONENTE OPCIONAL")
        and status == "COMPONENTE OPCIONAL OK"
    )
    if corrected:
        detail = (
            f"Auditoria RC22 corrigida pela regra realmente aplicada: {detail or 'pedágio por fração'}; "
            f"cobrado {_money_br(charged)}, esperado {_money_br(expected)}."
        )
    elif not detail:
        detail = f"Cobrado {_money_br(charged)}; esperado {_money_br(expected)} conforme a regra selecionada."
    return TollAudit(charged, expected, difference, status, detail, corrected)


def _attention_kind(status: Any) -> tuple[str, str]:
    normalized = _norm(status)
    if "DIVERGENTE" in normalized:
        return "DIVERGÊNCIA REAL DE VALOR", "Conferir cálculo e solicitar correção ou retirada do CT-e da cobrança."
    if "REGRA" in normalized:
        return "REGRA NÃO ENCONTRADA", "Confirmar rota e cadastrar a regra comercial antes do pagamento."
    if "PARCEIRO" in normalized:
        return "PARCEIRO SEM TABELA APLICÁVEL", "Confirmar CNPJ/alias e vincular a tabela comercial correta."
    if "ROTA" in normalized:
        return "ROTA INVÁLIDA", "Conferir o município comercial e a rota selecionada."
    if any(token in normalized for token in ("ORIGINAL", "BASE", "NF FORA", "NF NAO")):
        return "DOCUMENTO FORA DA BASE", "Localizar o documento originário na base oficial antes do pagamento."
    if "COMPROVANTE" in normalized:
        return "COMPROVANTE INVÁLIDO", "Regularizar o comprovante antes do pagamento."
    if "EXTRA" in normalized:
        return "CUSTO EXTRA NÃO VALIDADO", "Validar a cobrança extra e sua previsão comercial."
    if any(token in normalized for token in ("ERRO", "FALHA", "INCONSISTENCIA")):
        return "FALHA DE CLASSIFICAÇÃO", "Reprocessar o XML e revisar o diagnóstico técnico."
    return "CONFERÊNCIA HUMANA", "Conferir o diagnóstico e registrar a decisão manual."


def _reason(status: Any, result: Mapping[str, Any], difference: float) -> str:
    normalized = _norm(status)
    detail = _text(result.get("detalhe"))
    if "DIVERGENTE" in normalized:
        direction = "acima" if difference > 0 else "abaixo"
        return f"Valor comparado {direction} do esperado; diferença de {_money_br(difference)}. {detail}".strip()
    if "REGRA" in normalized:
        return detail or "Parceiro identificado, mas nenhuma regra comercial correspondeu à rota."
    if "PARCEIRO" in normalized:
        return detail or "Parceiro/CNPJ sem tabela comercial aplicável."
    if any(token in normalized for token in ("ORIGINAL", "BASE", "NF FORA", "NF NAO")):
        return detail or "Documento originário ou vínculo confiável não foi localizado na base oficial."
    if "EXTRA" in normalized:
        return detail or "Cobrança extra requer validação comercial."
    if detail:
        return detail
    trace = result.get("trace") or []
    return _text(trace[-1]) if trace else _text(status)


@dataclass
class XmlValidationReportModel:
    generated_at: datetime
    metrics: dict[str, Any]
    attention_rows: list[list[Any]]
    detail_rows: list[list[Any]]
    audit_rows: list[list[Any]]
    status_summary: list[dict[str, Any]]
    partner_summary: list[dict[str, Any]]
    corrected_toll_false_divergences: int = 0
    source_count: int = 0


class XmlValidationReportConsolidator:
    def __init__(self, legacy_export_row: Callable[[Mapping[str, Any]], Sequence[Any]] | None = None):
        self._legacy_export_row = legacy_export_row or _fallback_audit_row

    def build(self, files: Iterable[Mapping[str, Any]]) -> XmlValidationReportModel:
        infos = list(files)
        audit_rows: list[list[Any]] = []
        detail_rows: list[list[Any]] = []
        attention_rows: list[list[Any]] = []
        status_groups: dict[str, dict[str, Any]] = {}
        partner_groups: dict[str, dict[str, Any]] = {}
        corrected_tolls = 0

        total_compared = total_expected = total_difference = total_cte = 0.0
        total_base = total_profit = 0.0
        base_count = 0
        approved = no_pay = review = 0
        risk_value = 0.0

        for info in infos:
            result = info.get("validacao") or {}
            row = list(self._legacy_export_row(info))
            if len(row) != LEGACY_AUDIT_COLUMN_COUNT:
                raise ValueError(
                    f"Auditoria técnica incompatível: {len(row)} colunas; esperado {LEGACY_AUDIT_COLUMN_COUNT}."
                )
            audit = dict(zip(AUDIT_HEADERS[:LEGACY_AUDIT_COLUMN_COUNT], row))
            status = _text(audit.get("Status")) or "NÃO VALIDADO"
            rule_missing = _rule_not_found(status, audit, result)
            toll = resolve_toll_audit(info)
            if rule_missing:
                # Esses campos dependem de uma regra comercial. Zero significaria
                # uma regra de valor zero; aqui a informação correta é N/A.
                row[11] = ""
                row[12] = "N/A — REGRA NÃO ENCONTRADA"
                row[23] = ""
                row[24] = ""
                row[25] = ""
                row[52] = "NÃO ENCONTRADA"
                row[55] = toll.charged
                row[56] = ""
                row[57] = ""
                row[58] = "N/A — REGRA NÃO ENCONTRADA"
                row[59] = "Regra aplicada: NÃO ENCONTRADA; valores dependentes não se aplicam."
            else:
                row[55] = toll.charged
                row[56] = toll.expected
                row[57] = toll.difference
                row[58] = toll.status
                row[59] = toll.detail
            if toll.corrected_false_divergence and not rule_missing:
                corrected_tolls += 1
                audit["Diagnóstico"] = (
                    _text(audit.get("Diagnóstico"))
                    + " | "
                    + toll.detail
                ).strip(" |")
                row[33] = audit["Diagnóstico"]
            audit = dict(zip(AUDIT_HEADERS[:LEGACY_AUDIT_COLUMN_COUNT], row))

            operation = operational_status(status)
            if operation == "OK PARA PAGAMENTO":
                approved += 1
            elif _critical_status(status):
                no_pay += 1
            else:
                review += 1

            cte_value = _number(audit.get("Valor Total XML"))
            cost_present = audit.get("Valor Total XML") not in (None, "") or info.get("valor") not in (None, "")
            compared_raw = audit.get("Valor Comparado XML")
            expected_raw = audit.get("Valor Esperado")
            compared = _number(compared_raw) if compared_raw not in (None, "") else None
            expected = _number(expected_raw) if expected_raw not in (None, "") else None
            difference = (
                round(compared - expected, 2)
                if compared is not None and expected is not None
                else None
            )
            raw_base = audit.get("Frete Base")
            freight_base = _number(raw_base)
            base_value: float | None = round(freight_base, 2) if freight_base > 0.0 else None
            gross_profit = round(base_value - cte_value, 2) if base_value is not None and cost_present else None
            margin = gross_profit / base_value if gross_profit is not None and base_value and base_value > 0.0 else None
            margin_class = _margin_class(base_value, cost_present, margin)
            base_source = "Auditoria técnica › Frete Base" if base_value is not None else "NÃO INFORMADO / ZERO"
            cost_source = "XML › Valor Total XML" if cost_present else "NÃO INFORMADO"
            if base_value is None:
                profitability_memory = (
                    f"Frete base/receita não informado; custo do parceiro {_money_br(cte_value)}; "
                    f"classe {margin_class}."
                )
            else:
                profitability_memory = (
                    f"Frete base {_money_br(base_value)} - custo parceiro {_money_br(cte_value)} = "
                    f"lucro bruto {_money_br(gross_profit or 0.0)}; margem {margin:.2%}; classe {margin_class}."
                )
            row.extend([
                base_source, cost_source,
                gross_profit if gross_profit is not None else "",
                margin if margin is not None else "",
                margin_class, profitability_memory,
            ])
            if len(row) != len(AUDIT_HEADERS):
                raise ValueError(f"Auditoria RC26.6 incompatível: {len(row)} colunas; esperado {len(AUDIT_HEADERS)}.")
            audit_rows.append(row)
            tolerance = (
                max(0.0, _number(audit.get("Tolerância"), 1.0))
                if not rule_missing
                else None
            )
            total_cte += cte_value
            total_compared += compared or 0.0
            total_expected += expected or 0.0
            total_difference += difference or 0.0
            if base_value is not None:
                total_base += base_value
                total_profit += gross_profit or 0.0
                base_count += 1
            if _critical_status(status) and (
                "DIVERGENTE" in _norm(status)
                or (
                    difference is not None
                    and tolerance is not None
                    and abs(difference) > tolerance
                )
            ):
                risk_value += abs(difference or 0.0)

            status_group = status_groups.setdefault(status, {
                "status": status, "operation": operation, "quantity": 0,
                "cte_value": 0.0, "compared": 0.0, "expected": 0.0, "difference": 0.0,
            })
            status_group["quantity"] += 1
            status_group["cte_value"] += cte_value
            status_group["compared"] += compared or 0.0
            status_group["expected"] += expected or 0.0
            status_group["difference"] += difference or 0.0

            partner = _partner_label(info, audit)
            partner_group = partner_groups.setdefault(partner, {
                "partner": partner, "quantity": 0, "cte_value": 0.0,
                "compared": 0.0, "expected": 0.0, "difference": 0.0,
                "freight_base": 0.0, "partner_cost": 0.0, "gross_profit": 0.0,
                "base_count": 0,
            })
            partner_group["quantity"] += 1
            partner_group["cte_value"] += cte_value
            partner_group["compared"] += compared or 0.0
            partner_group["expected"] += expected or 0.0
            partner_group["difference"] += difference or 0.0
            partner_group["partner_cost"] += cte_value
            if base_value is not None:
                partner_group["freight_base"] += base_value
                partner_group["gross_profit"] += gross_profit or 0.0
                partner_group["base_count"] += 1

            origin = _text(info.get("origem"))
            destination = _text(info.get("destino") or audit.get("Cidade/UF Destino XML"))
            commercial_destination = _text(audit.get("Destino comercial utilizado")) or destination
            weight = _number(audit.get("Peso Base KG")) or _number(info.get("peso_base") or info.get("peso_bruto"))
            merchandise = _number(info.get("valor_carga"))
            reason = _reason(status, result, difference or 0.0)
            excel_row = 6 + len(detail_rows)
            component = _text(audit.get("Componente Comparado"))
            rule_applied = _text(audit.get("Regra comercial aplicada"))
            if rule_missing:
                component = "N/A — REGRA NÃO ENCONTRADA"
                rule_applied = "NÃO ENCONTRADA"
            detail_rows.append([
                _text(audit.get("CT-e")), partner, _text(audit.get("CNPJ Parceiro")),
                _text(audit.get("NF")), _text(info.get("data_br") or info.get("data_emissao")),
                origin, destination, commercial_destination, weight, merchandise, cte_value,
                compared if compared is not None else "", component,
                expected if expected is not None else "",
                Formula(
                    f'IF(OR($L{excel_row}="",$N{excel_row}=""),"",$L{excel_row}-$N{excel_row})',
                    difference if difference is not None else "",
                ),
                toll.charged,
                toll.expected if not rule_missing else "",
                rule_applied, status, reason,
                base_value,
                Formula(f"$K{excel_row}", cte_value),
                Formula(
                    f'IF(OR($U{excel_row}="",$U{excel_row}<=0,$V{excel_row}=""),"",$U{excel_row}-$V{excel_row})',
                    gross_profit if gross_profit is not None else "",
                ),
                Formula(
                    f'IF(OR($U{excel_row}="",$U{excel_row}<=0,$W{excel_row}=""),"",$W{excel_row}/$U{excel_row})',
                    margin if margin is not None else "",
                ),
                Formula(
                    f'IF($V{excel_row}="","SEM DADOS",IF(OR($U{excel_row}="",$U{excel_row}<=0),"SEM FRETE BASE",IF($X{excel_row}<0,"MARGEM NEGATIVA",IF($X{excel_row}<\'PAINEL\'!$T$79,"MARGEM BAIXA",IF($X{excel_row}<\'PAINEL\'!$T$80,"MARGEM SAUDÁVEL","MARGEM ALTA")))))',
                    margin_class,
                ),
            ])

            manual_pending = _norm(info.get("revisao_manual")) in {"SIM", "PENDENTE", "REVISAR", "CONFERIR"}
            if operation != "OK PARA PAGAMENTO" or manual_pending:
                alert_type, action = _attention_kind(status)
                attention_rows.append([
                    _text(audit.get("CT-e")), partner, _text(audit.get("CNPJ Parceiro")),
                    _text(audit.get("NF")), origin, commercial_destination, cte_value,
                    expected if expected is not None else "",
                    difference if difference is not None else "",
                    status, alert_type, reason, rule_applied, action,
                ])

        operation_order = {
            "PROBLEMA INTERNO / CONFERÊNCIA": 0,
            "OK PARA PAGAMENTO": 2,
        }
        attention_rows.sort(key=lambda row: (
            operation_order.get(operational_status(row[9]), 9),
            -abs(_number(row[8])), _text(row[0]),
        ))
        status_summary = sorted(
            status_groups.values(),
            key=lambda item: (operation_order.get(item["operation"], 9), -item["quantity"], item["status"]),
        )
        for partner_group in partner_groups.values():
            partner_base = float(partner_group["freight_base"] or 0.0)
            partner_profit = float(partner_group["gross_profit"] or 0.0)
            partner_margin = partner_profit / partner_base if partner_base > 0.0 else None
            partner_group["margin"] = partner_margin
            partner_group["margin_class"] = _margin_class(
                partner_base if partner_base > 0.0 else None,
                bool(partner_group["quantity"]),
                partner_margin,
            )
        partner_summary = sorted(
            partner_groups.values(),
            key=lambda item: (-item["partner_cost"], item["partner"]),
        )
        total = len(infos)
        metrics = {
            "total": total,
            "approved": approved,
            "no_pay": no_pay,
            "review": review,
            "approval_rate": (approved / total) if total else 0.0,
            "total_cte": total_cte,
            "total_compared": total_compared,
            "total_expected": total_expected,
            "total_difference": total_difference,
            "risk_value": risk_value,
            "partners": len(partner_groups),
            "total_base": total_base,
            "total_partner_cost": total_cte,
            "total_profit": total_profit,
            "overall_margin": (total_profit / total_base) if total_base else 0.0,
            "base_count": base_count,
        }
        return XmlValidationReportModel(
            generated_at=datetime.now(), metrics=metrics, attention_rows=attention_rows,
            detail_rows=detail_rows, audit_rows=audit_rows,
            status_summary=status_summary, partner_summary=partner_summary,
            corrected_toll_false_divergences=corrected_tolls, source_count=total,
        )


class XmlValidationReportGenerator:
    VERSION = REPORT_VERSION

    def __init__(self, legacy_export_row: Callable[[Mapping[str, Any]], Sequence[Any]] | None = None):
        self.consolidator = XmlValidationReportConsolidator(legacy_export_row)
        self.writer = XmlValidationXlsxWriter()
        self.last_model: XmlValidationReportModel | None = None

    def build(self, files: Iterable[Mapping[str, Any]]) -> XmlValidationReportModel:
        self.last_model = self.consolidator.build(files)
        return self.last_model

    def write(self, file_path: str | Path, files: Iterable[Mapping[str, Any]]) -> XmlValidationReportModel:
        model = self.build(files)
        self.writer.write(Path(file_path), model)
        return model


__all__ = [
    "ATTENTION_HEADERS", "AUDIT_HEADERS", "DETAIL_HEADERS", "REPORT_VERSION",
    "TollAudit", "XmlValidationReportConsolidator", "XmlValidationReportGenerator",
    "XmlValidationReportModel", "is_approved", "operational_status", "resolve_toll_audit",
]
