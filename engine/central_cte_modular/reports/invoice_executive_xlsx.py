from __future__ import annotations

"""Escritor OpenXML do relatório executivo e dinâmico de faturas RC26.6.

O arquivo é criado diretamente pelo programa, somente com a biblioteca padrão.
As fórmulas partem da aba CT_ES, separam pagamento futuro e problema interno e mantêm a auditoria técnica ligada ao estado atual.
"""

from collections import defaultdict
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

from ..invoices.normalization import normalize_status, parse_money
from .invoice_report import (
    ATTENTION_HEADERS,
    AUDIT_HEADERS,
    CTE_HEADERS,
    FATURAS_HEADERS,
    STATUS_EXCLUDED,
    STATUS_FUTURE,
    STATUS_OK,
    STATUS_REVIEW,
)
from .xlsx_openxml import (
    AMBER,
    BLUE,
    Formula,
    GREEN,
    NAVY,
    ORANGE,
    PURPLE,
    RED,
    TEAL,
    _app_xml,
    _chart_xml,
    _column_name,
    _conditional_margin_xml,
    _conditional_status_xml,
    _content_types_xml,
    _core_xml,
    _drawing_relationships_xml,
    _drawing_sheet_relationship_xml,
    _drawing_xml,
    _list_validation_xml,
    _root_relationships_xml,
    _row_xml,
    _styles_xml,
    _table_sheet_relationship_xml,
    _table_xml,
    _workbook_relationships_xml,
    _workbook_xml,
    _worksheet_xml,
    formula_value,
    validate_xlsx,
)


EXPECTED_SHEETS = ("PAINEL", "FATURAS", "ATENÇÃO", "CT_ES", "AUDITORIA_TÉCNICA")
CHART_COUNT = 5
TABLE_COUNT = 4


def _index(headers: Sequence[str], name: str) -> int:
    try:
        return list(headers).index(name)
    except ValueError as exc:
        raise ValueError(f"Coluna obrigatória ausente no relatório de faturas: {name}") from exc


def _value(cell: Any) -> Any:
    return formula_value(cell)


def _column_styles(sheet_name: str, headers: Sequence[str]) -> tuple[list[int], set[int]]:
    currency = {
        "Frete Cobrado pelo Parceiro", "Frete Base / Receita", "Diferença da Validação",
        "Valor para Pagamento Futuro", "Valor Retido por Problema Interno",
        "Valor Histórico em Conferência", "Valor em Conferência Histórica",
        "Valor Liberado Agora",
        "Valor Total Financeiro da Fatura", "Valor a Pagar Agora",
        "Frete Base Total", "Custo Total do Parceiro", "Lucro Bruto Estimado",
        "Valor CT-e", "Valor Base/Comissão", "Frete CTRC Origem Fatura",
        "Comissão Fatura", "Base Cálculo Tabela", "Mínimo Tabela",
        "Valor Esperado Tabela", "Diferença Tabela", "Tolerância Tabela",
        "Valor XML", "Diferença XML", "Valor a Pagar Agora Atual",
        "Valor para Pagamento Futuro Atual", "Valor Retido por Problema Interno Atual",
        "Reserva Técnica Legada Atual",
    }
    percentages = {"Percentual Liberado", "Margem Bruta Estimada", "Percentual Tabela"}
    weights = {"Peso Fatura", "Peso Usado Tabela"}
    centered_fragments = (
        "CT-E", "NF", "SEQ.", "COMPROVANTE", "STATUS", "SITUAÇÃO", "SITUACAO",
        "QUANTIDADE", "CONSISTÊNCIA", "CONFERÊNCIA", "CÓDIGO", "CLASSE",
    )
    styles: list[int] = []
    text_columns: set[int] = set()
    for column, header in enumerate(headers):
        token = normalize_status(header)
        if sheet_name == "CT_ES" and header in {"Frete Cobrado pelo Parceiro", "Frete Base / Receita"}:
            styles.append(31)
        elif sheet_name == "CT_ES" and header == "Comprovante":
            styles.append(30)
            text_columns.add(column)
        elif header in percentages:
            styles.append(18)
        elif header in weights:
            styles.append(19)
        elif header in currency or any(fragment in token for fragment in ("VALOR ", "FRETE ", "LUCRO ", "CUSTO ")):
            styles.append(17)
        elif any(fragment in token for fragment in centered_fragments):
            styles.append(37)
            text_columns.add(column)
        elif any(fragment in token for fragment in (
            "MOTIVO", "AÇÃO", "ACAO", "MENSAGEM", "PENDÊNCIA", "PENDENCIA",
            "MEMÓRIA", "MEMORIA", "CAMINHO", "AVISO", "OBSERVAÇÃO",
            "OBSERVACAO", "DETALHE",
        )):
            styles.append(15)
            text_columns.add(column)
        else:
            styles.append(36)
            text_columns.add(column)
    return styles, text_columns


def _tabular_sheet(
    *,
    sheet_name: str,
    title: str,
    subtitle: str,
    headers: Sequence[str],
    data: Sequence[Sequence[Any]],
    widths: Sequence[float],
    status_header: str,
    table_id: int,
    zoom: int = 88,
) -> tuple[str, str]:
    max_col = len(headers)
    last_letter = _column_name(max_col - 1)
    styles, text_columns = _column_styles(sheet_name, headers)
    rows_xml = [
        _row_xml(1, [title] + [None] * (max_col - 1), [1] + [0] * (max_col - 1), height=28),
        _row_xml(2, [None] * max_col, [1] + [0] * (max_col - 1), height=18),
        _row_xml(3, [subtitle] + [None] * (max_col - 1), [2] + [0] * (max_col - 1), height=24),
        _row_xml(4, [None] * max_col, [0] * max_col, height=8),
        _row_xml(5, headers, [35] * max_col, height=24, text_columns=set(range(max_col))),
    ]
    data_height = 24 if sheet_name in {"ATENÇÃO", "AUDITORIA_TÉCNICA"} else 20
    for row_index, values in enumerate(data, start=6):
        rows_xml.append(_row_xml(row_index, values, styles, height=data_height, text_columns=text_columns))
    last_row = max(5 + len(data), 5)
    table_ref = f"A5:{last_letter}{last_row}"
    conditional = ""
    if data:
        status_col = _column_name(_index(headers, status_header))
        margin_col = None
        if "Classificação da Margem" in headers:
            margin_col = _column_name(_index(headers, "Classificação da Margem"))
        elif "Rentabilidade" in headers:
            margin_col = _column_name(_index(headers, "Rentabilidade"))
        if margin_col:
            # A rentabilidade colore somente a própria coluna. O status operacional
            # permanece responsável pela cor da linha inteira.
            conditional += _conditional_margin_xml(
                f"{margin_col}6:{margin_col}{last_row}", margin_col, 6, priority_start=1
            )
            conditional += _conditional_status_xml(
                f"A6:{last_letter}{last_row}", status_col, 6, priority_start=5
            )
        else:
            conditional += _conditional_status_xml(
                f"A6:{last_letter}{last_row}", status_col, 6, priority_start=1
            )
    validation = ""
    if sheet_name == "CT_ES" and data:
        proof_col = _column_name(_index(headers, "Comprovante"))
        validation = _list_validation_xml(f"{proof_col}6:{proof_col}{last_row}", ("S", "N", "-"))
    table_parts = '<tableParts count="1"><tablePart r:id="rId1"/></tableParts>'
    xml = _worksheet_xml(
        rows_xml=rows_xml,
        widths=widths,
        max_row=last_row,
        max_col=max_col,
        merges=(f"A1:{last_letter}2", f"A3:{last_letter}3"),
        freeze_row=5,
        auto_filter=table_ref,
        conditional=conditional,
        data_validations=validation,
        table_parts=table_parts,
        zoom=zoom,
    )
    return xml, table_ref


def _panel_sheet(
    sheets: Mapping[str, tuple[list[list[Any]], list[float]]],
    generated_at: datetime,
) -> tuple[str, list[str], list[Mapping[str, Any]]]:
    faturas = sheets["FATURAS"][0]
    ctes = sheets["CT_ES"][0]
    frows = faturas[1:]
    crows = ctes[1:]
    f_end = max(6, 5 + len(frows))
    c_end = max(6, 5 + len(crows))

    ci_partner = _index(CTE_HEADERS, "Parceiro")
    ci_cost = _index(CTE_HEADERS, "Frete Cobrado pelo Parceiro")
    ci_base = _index(CTE_HEADERS, "Frete Base / Receita")
    ci_block_class = _index(CTE_HEADERS, "Classe Financeira Canônica Original")
    ci_financial = _index(CTE_HEADERS, "Status Operacional Atual")
    ci_future = _index(CTE_HEADERS, "Valor para Pagamento Futuro")
    ci_review = _index(CTE_HEADERS, "Valor Retido por Problema Interno")
    ci_blocked = _index(CTE_HEADERS, "Valor Histórico em Conferência")
    ci_released = _index(CTE_HEADERS, "Valor Liberado Agora")
    ci_profit = _index(CTE_HEADERS, "Lucro Bruto Estimado")
    ci_margin_class = _index(CTE_HEADERS, "Classificação da Margem")
    fi_status = _index(FATURAS_HEADERS, "Status de Pagamento Atual da Fatura")
    fi_consistency = _index(FATURAS_HEADERS, "Consistência Financeira e Contábil")

    partners = sorted({
        str(_value(row[ci_partner]) or "Parceiro não identificado")
        for row in crows if str(_value(row[ci_partner]) or "").strip()
    }, key=str.casefold)
    if not partners:
        partners = ["SEM DADOS"]

    counted_rows = [row for row in crows if normalize_status(_value(row[ci_block_class])) != "NAO CONTABILIZADO"]
    base_total = round(sum(parse_money(_value(row[ci_base])) for row in counted_rows), 2)
    cost_total = round(sum(parse_money(_value(row[ci_cost])) for row in counted_rows), 2)
    released_total = round(sum(parse_money(_value(row[ci_released])) for row in crows), 2)
    future_total = round(sum(parse_money(_value(row[ci_future])) for row in crows), 2)
    review_total = round(sum(parse_money(_value(row[ci_review])) for row in crows), 2)
    blocked_total = round(sum(parse_money(_value(row[ci_blocked])) for row in crows), 2)
    profit_total = round(sum(parse_money(_value(row[ci_profit])) for row in counted_rows), 2)
    margin_total = profit_total / base_total if base_total > 0 else 0.0
    f_statuses = [normalize_status(_value(row[fi_status])) for row in frows]
    financial_statuses = [normalize_status(_value(row[ci_financial])) for row in crows]

    partner_initial: dict[str, dict[str, float]] = defaultdict(lambda: {"base": 0.0, "cost": 0.0, "profit": 0.0})
    for row in counted_rows:
        partner = str(_value(row[ci_partner]) or "Parceiro não identificado")
        partner_initial[partner]["base"] += parse_money(_value(row[ci_base]))
        partner_initial[partner]["cost"] += parse_money(_value(row[ci_cost]))
        partner_initial[partner]["profit"] += parse_money(_value(row[ci_profit]))

    margin_classes = (
        "MARGEM NEGATIVA", "MARGEM BAIXA", "MARGEM SAUDÁVEL", "MARGEM ALTA",
        "SEM FRETE BASE", "SEM DADOS", "NÃO CONTABILIZADO",
    )
    class_counts = {
        name: sum(normalize_status(_value(row[ci_margin_class])) == normalize_status(name) for row in crows)
        for name in margin_classes
    }
    financial_categories = (STATUS_OK, STATUS_FUTURE, STATUS_REVIEW)
    financial_values = (released_total, future_total, review_total + blocked_total)

    partner_start = 96
    partner_end = partner_start + len(partners) - 1
    class_start = 96
    class_end = class_start + len(margin_classes) - 1
    financial_start = 96
    financial_end = financial_start + len(financial_categories) - 1

    count_condition = f"'CT_ES'!$L$6:$L${c_end},\"<>NÃO CONTABILIZADO\""
    cards = (
        ("Faturas analisadas", Formula(f"COUNTA('FATURAS'!$A$6:$A${f_end})", len(frows)), 4),
        ("CT-es analisados", Formula(f"COUNTA('CT_ES'!$A$6:$A${c_end})", len(crows)), 4),
        ("Parceiros", Formula(f"COUNTA($A${partner_start}:$A${partner_end})", 0 if partners == ["SEM DADOS"] else len(partners)), 4),
        ("Faturas OK para pagamento", Formula(f'COUNTIF(\'FATURAS\'!$P$6:$P${f_end},"{STATUS_OK}")', f_statuses.count(normalize_status(STATUS_OK))), 5),
        ("Faturas em pagamento futuro", Formula(f'COUNTIF(\'FATURAS\'!$P$6:$P${f_end},"{STATUS_FUTURE}")', f_statuses.count(normalize_status(STATUS_FUTURE))), 13),
        ("Faturas com problema interno / conferência", Formula(f'COUNTIF(\'FATURAS\'!$P$6:$P${f_end},"{STATUS_REVIEW}")', f_statuses.count(normalize_status(STATUS_REVIEW))), 13),
        ("Faturas financeiramente coerentes", Formula(f'COUNTIF(\'FATURAS\'!$S$6:$S${f_end},"COERENTE")', sum(normalize_status(_value(row[fi_consistency])) == "COERENTE" for row in frows)), 5),
        ("CT-es OK para pagamento", Formula(f'COUNTIF(\'CT_ES\'!$M$6:$M${c_end},"{STATUS_OK}")', financial_statuses.count(normalize_status(STATUS_OK))), 5),
        ("CT-es em pagamento futuro", Formula(f'COUNTIF(\'CT_ES\'!$M$6:$M${c_end},"{STATUS_FUTURE}")', financial_statuses.count(normalize_status(STATUS_FUTURE))), 13),
        ("CT-es com problema interno / conferência", Formula(f'COUNTIF(\'CT_ES\'!$M$6:$M${c_end},"{STATUS_REVIEW}")', financial_statuses.count(normalize_status(STATUS_REVIEW))), 13),
        ("CT-es não contabilizados", Formula(f'COUNTIF(\'CT_ES\'!$M$6:$M${c_end},"{STATUS_EXCLUDED}")', financial_statuses.count(normalize_status(STATUS_EXCLUDED))), 6),
        ("Frete base total", Formula(f"SUMIFS('CT_ES'!$F$6:$F${c_end},{count_condition})", base_total), 7),
        ("Custo dos parceiros", Formula(f"SUMIFS('CT_ES'!$E$6:$E${c_end},{count_condition})", cost_total), 7),
        ("Lucro bruto estimado", Formula(f"SUMIFS('CT_ES'!$W$6:$W${c_end},{count_condition})", profit_total), 27 if profit_total >= 0 else 8),
        ("Margem bruta estimada", Formula(f"IF(SUMIFS('CT_ES'!$F$6:$F${c_end},{count_condition})>0,SUMIFS('CT_ES'!$W$6:$W${c_end},{count_condition})/SUMIFS('CT_ES'!$F$6:$F${c_end},{count_condition}),0)", margin_total), 9 if margin_total >= 0 else 6),
        ("Valor a pagar agora", Formula(f"SUM('CT_ES'!$Q$6:$Q${c_end})", released_total), 27),
        ("Valor para pagamento futuro", Formula(f"SUM('CT_ES'!$N$6:$N${c_end})", future_total), 29),
        ("Valor retido por problema interno", Formula(f"SUM('CT_ES'!$O$6:$O${c_end})+SUM('CT_ES'!$P$6:$P${c_end})", review_total + blocked_total), 29),
        ("CT-es sem frete base", Formula(f'COUNTIF(\'CT_ES\'!$Y$6:$Y${c_end},"SEM FRETE BASE")', class_counts["SEM FRETE BASE"]), 13),
    )

    rows: dict[int, tuple[list[Any], list[int], float]] = {}
    merges = ["A1:T2", "A3:T3"]
    rows[1] = (["CENTRAL CT-e | RELATÓRIO EXECUTIVO DE FATURAS"] + [None] * 19, [1] + [0] * 19, 28)
    rows[2] = ([None] * 20, [1] + [0] * 19, 18)
    rows[3] = ([
        f"Gerado em {generated_at.strftime('%d/%m/%Y %H:%M:%S')}  •  comprovante S paga, demais vão ao futuro  •  RC26.6"
    ] + [None] * 19, [2] + [0] * 19, 24)
    rows[4] = ([None] * 20, [0] * 20, 8)

    starts = (0, 5, 10, 15)
    for card_index, (label, value, value_style) in enumerate(cards):
        top = 5 + (card_index // 4) * 5
        start_col = starts[card_index % 4]
        end_col = start_col + 4
        first, last = _column_name(start_col), _column_name(end_col)
        merges.extend((f"{first}{top}:{last}{top + 1}", f"{first}{top + 2}:{last}{top + 3}"))
        for row_number in range(top, top + 4):
            rows.setdefault(row_number, ([None] * 20, [0] * 20, 20 if row_number < top + 2 else 24))
        rows[top][0][start_col] = label
        rows[top][1][start_col] = 3
        rows[top + 2][0][start_col] = value
        rows[top + 2][1][start_col] = value_style
        rows[top + 4] = ([None] * 20, [0] * 20, 8)

    rows[31] = ([None] * 5 + ["LEITURA OPERACIONAL"] + [None] * 14, [0] * 5 + [20] + [0] * 14, 20)
    merges.append("F31:T31")
    note = (
        "A fonte de verdade é o Status Operacional Atual: OK para pagamento, Pagamento futuro ou Problema interno / Conferência. "
        "Os campos originais são apenas fotografia histórica e ficam ocultos na CT_ES; a auditoria técnica mostra, lado a lado, "
        "a fotografia inicial e o estado atual."
    )
    rows[32] = ([None] * 5 + [note] + [None] * 14, [0] * 5 + [21] + [0] * 14, 42)
    rows[33] = ([None] * 20, [0] * 20, 20)
    rows[34] = ([None] * 20, [0] * 20, 20)
    merges.append("F32:T34")

    rows[90] = (["PARÂMETROS EDITÁVEIS DE RENTABILIDADE"] + [None] * 19, [20] + [0] * 19, 22)
    merges.append("A90:T90")
    rows[91] = (["Os limites ao lado alimentam CT_ES, FATURAS, cartões e gráficos."] + [None] * 17 + ["Margem baixa até", 0.10], [21] + [0] * 17 + [33, 34], 24)
    rows[92] = ([None] * 18 + ["Margem saudável até", 0.25], [0] * 18 + [33, 34], 24)
    merges.append("A91:R92")
    rows[93] = ([None] * 20, [0] * 20, 8)
    rows[94] = (["BASE AUXILIAR DINÂMICA DOS GRÁFICOS"] + [None] * 19, [20] + [0] * 19, 22)
    merges.append("A94:T94")
    rows[95] = ([
        "Parceiro", "Frete base", "Custo parceiro", "Lucro bruto", "Margem", None,
        "Rentabilidade", "CT-es", None, "Distribuição financeira", "Valor",
    ] + [None] * 9, [14, 14, 14, 14, 14, 0, 14, 14, 0, 14, 14] + [0] * 9, 32)

    chart_series_cache: list[Mapping[str, Any]] = []
    for offset, partner in enumerate(partners):
        row_number = partner_start + offset
        initial = partner_initial.get(partner, {"base": 0.0, "cost": 0.0, "profit": 0.0})
        base = round(initial["base"], 2)
        cost = round(initial["cost"], 2)
        profit = round(initial["profit"], 2)
        margin = profit / base if base > 0 else 0.0
        rows[row_number] = ([
            partner,
            Formula(f'SUMIFS(\'CT_ES\'!$F$6:$F${c_end},\'CT_ES\'!$B$6:$B${c_end},$A{row_number},\'CT_ES\'!$L$6:$L${c_end},"<>NÃO CONTABILIZADO")', base),
            Formula(f'SUMIFS(\'CT_ES\'!$E$6:$E${c_end},\'CT_ES\'!$B$6:$B${c_end},$A{row_number},\'CT_ES\'!$L$6:$L${c_end},"<>NÃO CONTABILIZADO")', cost),
            Formula(f'SUMIFS(\'CT_ES\'!$W$6:$W${c_end},\'CT_ES\'!$B$6:$B${c_end},$A{row_number},\'CT_ES\'!$L$6:$L${c_end},"<>NÃO CONTABILIZADO")', profit),
            Formula(f"IF($B{row_number}>0,$D{row_number}/$B{row_number},0)", margin),
        ] + [None] * 15, [15, 17, 17, 17, 18] + [0] * 15, 22)
        chart_series_cache.append({"partner": partner, "base": base, "cost": cost, "profit": profit, "margin": margin})

    for offset, margin_class in enumerate(margin_classes):
        row_number = class_start + offset
        existing = rows.get(row_number, ([None] * 20, [0] * 20, 22))
        existing[0][6] = margin_class
        existing[0][7] = Formula(f"COUNTIF('CT_ES'!$Y$6:$Y${c_end},$G{row_number})", class_counts[margin_class])
        existing[1][6:8] = [15, 16]
        rows[row_number] = existing

    financial_columns = ("Q", "N", "O")
    for offset, (category, cached) in enumerate(zip(financial_categories, financial_values)):
        row_number = financial_start + offset
        existing = rows.get(row_number, ([None] * 20, [0] * 20, 22))
        existing[0][9] = category
        existing[0][10] = Formula(
            f"SUM('CT_ES'!$O$6:$O${c_end})+SUM('CT_ES'!$P$6:$P${c_end})" if category == STATUS_REVIEW
            else f"SUM('CT_ES'!${financial_columns[offset]}$6:${financial_columns[offset]}${c_end})",
            cached,
        )
        existing[1][9:11] = [15, 17]
        rows[row_number] = existing

    max_row = max(max(rows), partner_end, class_end, financial_end)
    rows_xml = []
    for row_number in range(1, max_row + 1):
        values, styles, height = rows.get(row_number, ([None] * 20, [0] * 20, 18))
        rows_xml.append(_row_xml(row_number, values, styles, height=height))

    panel_xml = _worksheet_xml(
        rows_xml=rows_xml,
        widths=[16, 15, 15, 15, 15, 3, 25, 12, 3, 27, 17, 15, 15, 15, 15, 15, 15, 15, 23, 14],
        max_row=max_row,
        max_col=20,
        merges=merges,
        active=True,
        drawing=True,
        zoom=82,
    )

    partner_categories = [item["partner"] for item in chart_series_cache]
    charts = [
        _chart_xml(
            title="Frete base × custo por parceiro", categories=partner_categories,
            series=(
                {"name": "Frete base", "values": [item["base"] for item in chart_series_cache], "category_formula": f"'PAINEL'!$A${partner_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$B${partner_start}:$B${partner_end}", "color": BLUE, "format_code": "R$ #,##0.00"},
                {"name": "Custo parceiro", "values": [item["cost"] for item in chart_series_cache], "category_formula": f"'PAINEL'!$A${partner_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$C${partner_start}:$C${partner_end}", "color": ORANGE, "format_code": "R$ #,##0.00"},
            ), bar_direction="col", currency_axis=True, chart_id=1,
        ),
        _chart_xml(
            title="Lucro bruto por parceiro", categories=partner_categories,
            series=({"name": "Lucro bruto", "values": [item["profit"] for item in chart_series_cache], "category_formula": f"'PAINEL'!$A${partner_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$D${partner_start}:$D${partner_end}", "color": GREEN, "format_code": "R$ #,##0.00"},),
            bar_direction="col", currency_axis=True, chart_id=2,
        ),
        _chart_xml(
            title="Margem bruta por parceiro", categories=partner_categories,
            series=({"name": "Margem", "values": [item["margin"] for item in chart_series_cache], "category_formula": f"'PAINEL'!$A${partner_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$E${partner_start}:$E${partner_end}", "color": TEAL, "format_code": "0.0%"},),
            bar_direction="bar", currency_axis=False, chart_id=3,
        ),
        _chart_xml(
            title="CT-es por rentabilidade", categories=list(margin_classes),
            series=({"name": "CT-es", "values": [class_counts[name] for name in margin_classes], "category_formula": f"'PAINEL'!$G${class_start}:$G${class_end}", "value_formula": f"'PAINEL'!$H${class_start}:$H${class_end}", "color": PURPLE, "format_code": "0"},),
            bar_direction="bar", currency_axis=False, chart_id=4,
        ),
        _chart_xml(
            title="Distribuição financeira atual", categories=list(financial_categories),
            series=({"name": "Valor", "values": list(financial_values), "category_formula": f"'PAINEL'!$J${financial_start}:$J${financial_end}", "value_formula": f"'PAINEL'!$K${financial_start}:$K${financial_end}", "color": AMBER, "format_code": "R$ #,##0.00"},),
            bar_direction="col", currency_axis=True, chart_id=5,
        ),
    ]
    return panel_xml, partner_categories, charts


class InvoiceExecutiveXlsxWriter:
    VERSION = "2.7.0-RC26.6"

    def __init__(self) -> None:
        self.last_log_path: Path | None = None

    def write(self, path: Path, sheets: Sequence[Any]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = [
            (str(name), [list(row) for row in list(rows or [])], list(widths or []))
            for name, rows, widths in list(sheets or [])
        ]
        if tuple(name for name, _rows, _widths in normalized) != EXPECTED_SHEETS:
            raise ValueError(f"Relatório de faturas deve conter exatamente as abas {EXPECTED_SHEETS}.")
        sheet_map = {name: (rows, widths) for name, rows, widths in normalized}
        expected_headers = {
            "FATURAS": FATURAS_HEADERS,
            "ATENÇÃO": ATTENTION_HEADERS,
            "CT_ES": CTE_HEADERS,
            "AUDITORIA_TÉCNICA": AUDIT_HEADERS,
        }
        for name, expected in expected_headers.items():
            rows = sheet_map[name][0]
            if not rows or tuple(rows[0]) != tuple(expected):
                raise ValueError(f"Cabeçalho inválido na aba {name}.")
        if len(AUDIT_HEADERS) < 74:
            raise ValueError("A auditoria perdeu a fotografia técnica original ou as colunas operacionais atuais.")

        generated_at = datetime.now().astimezone()
        panel_xml, _partners, charts = _panel_sheet(sheet_map, generated_at)
        specs = (
            ("FATURAS", "FATURAS CONSOLIDADAS", f"Uma linha por fatura • {len(sheet_map['FATURAS'][0]) - 1} fatura(s) • três destinos financeiros separados e ligados à CT_ES.", "Status de Pagamento Atual da Fatura", "TabelaFaturas"),
            ("ATENÇÃO", "PENDÊNCIAS QUE EXIGEM AÇÃO", "Visão dinâmica: Pagamento futuro e Problema interno / Conferência aparecem em categorias distintas.", "Status Operacional Atual", "TabelaAtencao"),
            ("CT_ES", "VISÃO OPERACIONAL POR CT-e", f"Uma linha canônica por CT-e • {len(sheet_map['CT_ES'][0]) - 1} registro(s) • amarelo é editável; históricos ficam ocultos por padrão.", "Status Operacional Atual", "TabelaCTes"),
            ("AUDITORIA_TÉCNICA", "AUDITORIA TÉCNICA COMPLETA", f"{len(sheet_map['AUDITORIA_TÉCNICA'][0]) - 1} linha(s) • fotografia original e estado operacional atual lado a lado.", "Status Operacional Atual", "TabelaAuditoria"),
        )
        sheet_xmls = [panel_xml]
        table_refs: list[tuple[str, Sequence[str], str]] = []
        for table_id, (name, title, subtitle, status_header, table_name) in enumerate(specs, start=1):
            rows, widths = sheet_map[name]
            xml, table_ref = _tabular_sheet(
                sheet_name=name,
                title=title,
                subtitle=subtitle,
                headers=rows[0],
                data=rows[1:],
                widths=widths,
                status_header=status_header,
                table_id=table_id,
                zoom=70 if name == "AUDITORIA_TÉCNICA" else 86,
            )
            sheet_xmls.append(xml)
            table_refs.append((table_ref, rows[0], table_name))

        anchors = ((0, 35, 9, 51), (10, 35, 19, 51), (0, 52, 9, 68), (10, 52, 19, 68), (0, 69, 19, 85))
        temporary = path.with_name(path.name + ".tmp")
        with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("[Content_Types].xml", _content_types_xml(sheet_count=5, chart_count=CHART_COUNT, table_count=TABLE_COUNT))
            archive.writestr("_rels/.rels", _root_relationships_xml())
            archive.writestr("docProps/core.xml", _core_xml(generated_at, title="Relatório Executivo de Faturas RC26.6", description="Faturas com pagamento atual, pagamento futuro e retenção exclusiva por problema interno, derivados da mesma base por CT-e."))
            archive.writestr("docProps/app.xml", _app_xml(EXPECTED_SHEETS, version=self.VERSION))
            archive.writestr("xl/workbook.xml", _workbook_xml(EXPECTED_SHEETS))
            archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml(5))
            archive.writestr("xl/styles.xml", _styles_xml())
            for index, xml in enumerate(sheet_xmls, start=1):
                archive.writestr(f"xl/worksheets/sheet{index}.xml", xml)
            archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", _drawing_sheet_relationship_xml())
            for table_id, (reference, headers, display_name) in enumerate(table_refs, start=1):
                archive.writestr(f"xl/worksheets/_rels/sheet{table_id + 1}.xml.rels", _table_sheet_relationship_xml(table_id))
                archive.writestr(f"xl/tables/table{table_id}.xml", _table_xml(table_id, display_name, reference, headers))
            archive.writestr("xl/drawings/drawing1.xml", _drawing_xml(anchors))
            archive.writestr("xl/drawings/_rels/drawing1.xml.rels", _drawing_relationships_xml(CHART_COUNT))
            for index, chart in enumerate(charts, start=1):
                archive.writestr(f"xl/charts/chart{index}.xml", chart)

        validate_xlsx(
            temporary,
            sheet_count=5,
            chart_count=CHART_COUNT,
            table_count=TABLE_COUNT,
            require_formulas=True,
            require_data_validation=bool(sheet_map["CT_ES"][0][1:]),
        )
        os.replace(temporary, path)
        self.last_log_path = self._write_decision_log(path, sheet_map)
        return path

    @staticmethod
    def _write_decision_log(path: Path, sheets: Mapping[str, tuple[list[list[Any]], list[float]]]) -> Path:
        report_dir = path.parent
        root = report_dir.parent if normalize_status(report_dir.name).startswith("RELATORIO") else report_dir
        log_dir = root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"decisoes_iniciais_relatorio_faturas_RC26_6_{stamp}.txt"
        rows = sheets["FATURAS"][0]
        headers = rows[0]
        indices = {name: _index(headers, name) for name in (
            "Número da Fatura", "Parceiro", "Valor Total Financeiro da Fatura", "Valor a Pagar Agora",
            "Valor para Pagamento Futuro", "Valor Retido por Problema Interno",
            "Valor em Conferência Histórica", "Status de Pagamento Atual da Fatura",
            "Principais Pendências Atuais", "Consistência Financeira e Contábil",
        )}
        lines = [
            "CENTRAL CT-e / DACTE — FOTOGRAFIA INICIAL DO RELATÓRIO DE FATURAS RC26.6",
            "=" * 88,
            f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            f"Arquivo: {path.name}",
            f"Faturas: {len(rows) - 1}",
            "Observação: este TXT é uma fotografia do momento da geração. Alterações posteriores no Excel aparecem nas fórmulas do XLSX, não reescrevem este arquivo.",
            "",
        ]
        for row in rows[1:]:
            get = lambda name: _value(row[indices[name]])
            lines.extend((
                f"Fatura {get('Número da Fatura')} | Parceiro: {get('Parceiro')}",
                f"Resultado inicial: {get('Status de Pagamento Atual da Fatura')} | Total: {parse_money(get('Valor Total Financeiro da Fatura')):.2f} | Agora: {parse_money(get('Valor a Pagar Agora')):.2f} | Futuro: {parse_money(get('Valor para Pagamento Futuro')):.2f} | Problema interno: {parse_money(get('Valor Retido por Problema Interno')):.2f} | Histórico em conferência: {parse_money(get('Valor em Conferência Histórica')):.2f}",
                f"Pendências: {get('Principais Pendências Atuais')} | Consistência: {get('Consistência Financeira e Contábil')}",
                "-" * 88,
            ))
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return log_path


__all__ = ["EXPECTED_SHEETS", "InvoiceExecutiveXlsxWriter"]
