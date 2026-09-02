from __future__ import annotations

"""Escritor OpenXML do relatório executivo e dinâmico dos XMLs RC26.6.

O programa produz o XLSX sem pós-processamento nem dependências externas.
Frete base e frete cobrado permanecem editáveis no DETALHAMENTO; lucro,
margem, cartões, bases auxiliares e cinco gráficos são fórmulas nativas.
"""

from datetime import datetime
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

from .xlsx_openxml import (
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


EXPECTED_SHEETS = ("PAINEL", "ATENÇÃO", "DETALHAMENTO", "AUDITORIA_TÉCNICA")
CHART_COUNT = 5
TABLE_COUNT = 3


def _index(headers: Sequence[str], name: str) -> int:
    try:
        return list(headers).index(name)
    except ValueError as exc:
        raise ValueError(f"Coluna obrigatória ausente no relatório XML: {name}") from exc


def _value(cell: Any) -> Any:
    return formula_value(cell)


def _number(value: Any) -> float:
    value = _value(value)
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("R$", "").replace("%", "").replace("\u00a0", " ").strip()
    text = "".join(character for character in text if character in "0123456789,.-")
    if not text:
        return 0.0
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _column_styles(sheet_name: str, headers: Sequence[str]) -> tuple[list[int], set[int]]:
    currency_fragments = (
        "VALOR ", "FRETE ", "LUCRO ", "CUSTO ", "DIFERENÇA", "DIFERENCA",
        "PEDÁGIO", "PEDAGIO", "R$/",
    )
    percentage = {"Percentual", "Margem Bruta Estimada"}
    weights = {"Peso (kg)", "Peso Base KG", "Peso Reverso KG", "Dif. Peso KG"}
    centered_fragments = ("CT-E", "NF", "STATUS", "SÉRIE", "SERIE", "CÓDIGO", "CODIGO")
    styles: list[int] = []
    text_columns: set[int] = set()
    for column, header in enumerate(headers):
        token = str(header).upper()
        if sheet_name == "DETALHAMENTO" and header in {"Frete Base / Receita", "Frete Cobrado pelo Parceiro"}:
            styles.append(31)
        elif header in percentage:
            styles.append(18)
        elif header in weights:
            styles.append(19)
        elif any(fragment in token for fragment in currency_fragments):
            styles.append(17)
        elif any(fragment in token for fragment in centered_fragments):
            styles.append(37)
            text_columns.add(column)
        elif any(fragment in token for fragment in (
            "MOTIVO", "AÇÃO", "ACAO", "DETALHE", "DIAGNÓSTICO", "DIAGNOSTICO",
            "MEMÓRIA", "MEMORIA", "CAMINHO", "OBSERVAÇÃO", "OBSERVACAO",
            "EXPLICAÇÃO", "EXPLICACAO",
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
    zoom: int,
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
    for row_number, values in enumerate(data, start=6):
        rows_xml.append(_row_xml(row_number, values, styles, height=data_height, text_columns=text_columns))
    last_row = max(5 + len(data), 5)
    table_ref = f"A5:{last_letter}{last_row}"
    conditional = ""
    if data:
        status_column = _column_name(_index(headers, status_header))
        class_column = None
        if "Classificação da Margem" in headers:
            class_column = _column_name(_index(headers, "Classificação da Margem"))
        if class_column:
            # A margem colore somente a própria coluna; o status colore a linha.
            conditional += _conditional_margin_xml(
                f"{class_column}6:{class_column}{last_row}", class_column, 6, priority_start=1
            )
            conditional += _conditional_status_xml(
                f"A6:{last_letter}{last_row}", status_column, 6, priority_start=5
            )
        else:
            conditional += _conditional_status_xml(
                f"A6:{last_letter}{last_row}", status_column, 6, priority_start=1
            )
    return _worksheet_xml(
        rows_xml=rows_xml,
        widths=widths,
        max_row=last_row,
        max_col=max_col,
        merges=(f"A1:{last_letter}2", f"A3:{last_letter}3"),
        freeze_row=5,
        auto_filter=table_ref,
        conditional=conditional,
        table_parts='<tableParts count="1"><tablePart r:id="rId1"/></tableParts>',
        zoom=zoom,
    ), table_ref


def _panel_sheet(model: Any) -> tuple[str, list[str]]:
    from .xml_validation_report import DETAIL_HEADERS

    details = list(model.detail_rows)
    detail_end = max(6, 5 + len(details))
    ci_partner = _index(DETAIL_HEADERS, "Parceiro")
    ci_status = _index(DETAIL_HEADERS, "Status")
    ci_base = _index(DETAIL_HEADERS, "Frete Base / Receita")
    ci_cost = _index(DETAIL_HEADERS, "Frete Cobrado pelo Parceiro")
    ci_profit = _index(DETAIL_HEADERS, "Lucro Bruto Estimado")
    ci_margin_class = _index(DETAIL_HEADERS, "Classificação da Margem")
    partner_letter = _column_name(ci_partner)
    status_letter = _column_name(ci_status)
    base_letter = _column_name(ci_base)
    cost_letter = _column_name(ci_cost)
    profit_letter = _column_name(ci_profit)
    margin_class_letter = _column_name(ci_margin_class)

    partner_items = list(model.partner_summary)
    partners = [str(item.get("partner") or "Não identificado") for item in partner_items]
    if not partners:
        partners = ["SEM DADOS"]
    status_items = list(model.status_summary)
    statuses = [str(item.get("status") or "NÃO VALIDADO") for item in status_items]
    if not statuses:
        statuses = ["SEM DADOS"]

    initial_partner: dict[str, dict[str, float]] = {}
    for partner in partners:
        matching = [row for row in details if str(_value(row[ci_partner]) or "") == partner]
        base = round(sum(_number(row[ci_base]) for row in matching), 2)
        cost = round(sum(_number(row[ci_cost]) for row in matching), 2)
        profit = round(sum(_number(row[ci_profit]) for row in matching), 2)
        initial_partner[partner] = {"base": base, "cost": cost, "profit": profit, "margin": profit / base if base > 0 else 0.0}

    margin_classes = (
        "MARGEM NEGATIVA", "MARGEM BAIXA", "MARGEM SAUDÁVEL",
        "MARGEM ALTA", "SEM FRETE BASE", "SEM DADOS",
    )
    class_counts = {
        name: sum(str(_value(row[ci_margin_class]) or "").upper() == name for row in details)
        for name in margin_classes
    }
    status_counts = {
        name: sum(str(_value(row[ci_status]) or "") == name for row in details)
        for name in statuses
    }
    base_total = round(sum(_number(row[ci_base]) for row in details), 2)
    cost_total = round(sum(_number(row[ci_cost]) for row in details), 2)
    profit_total = round(sum(_number(row[ci_profit]) for row in details), 2)
    margin_total = profit_total / base_total if base_total > 0 else 0.0
    approved = sum(str(_value(row[ci_status]) or "").upper().startswith("OK") for row in details)
    attention = len(details) - approved
    risk_value = round(sum(
        _number(row[ci_cost]) for row in details
        if not str(_value(row[ci_status]) or "").upper().startswith("OK")
    ), 2)
    status_range = f"'DETALHAMENTO'!${status_letter}$6:${status_letter}${detail_end}"
    cost_range = f"'DETALHAMENTO'!${cost_letter}$6:${cost_letter}${detail_end}"
    total_count_formula = "COUNTA('DETALHAMENTO'!$A$6:$A$%d)" % detail_end
    approved_statuses = [
        name for name in statuses
        if str(name or "").upper().startswith("OK")
    ]
    approved_count_formula = "+".join(
        f'COUNTIF({status_range},\"{str(name).replace(chr(34), chr(34) * 2)}\")'
        for name in approved_statuses
    ) or "0"
    approved_value_formula = "+".join(
        f'SUMIF({status_range},\"{str(name).replace(chr(34), chr(34) * 2)}\",{cost_range})'
        for name in approved_statuses
    ) or "0"

    helper_start = 84
    partner_end = helper_start + len(partners) - 1
    class_end = helper_start + len(margin_classes) - 1
    status_end = helper_start + len(statuses) - 1
    cards = (
        ("CT-es analisados", Formula(total_count_formula, len(details)), 4),
        ("CT-es aprovados", Formula(approved_count_formula, approved), 5),
        ("Itens em atenção", Formula(f"{total_count_formula}-({approved_count_formula})", attention), 13),
        ("Parceiros", Formula(f"COUNTA($A${helper_start}:$A${partner_end})", 0 if partners == ["SEM DADOS"] else len(partners)), 4),
        ("Frete base total", Formula(f"SUM('DETALHAMENTO'!${base_letter}$6:${base_letter}${detail_end})", base_total), 7),
        ("Custo dos parceiros", Formula(f"SUM('DETALHAMENTO'!${cost_letter}$6:${cost_letter}${detail_end})", cost_total), 7),
        ("Lucro bruto estimado", Formula(f"SUM('DETALHAMENTO'!${profit_letter}$6:${profit_letter}${detail_end})", profit_total), 27 if profit_total >= 0 else 8),
        ("Margem bruta estimada", Formula(f"IF(SUM('DETALHAMENTO'!${base_letter}$6:${base_letter}${detail_end})>0,SUM('DETALHAMENTO'!${profit_letter}$6:${profit_letter}${detail_end})/SUM('DETALHAMENTO'!${base_letter}$6:${base_letter}${detail_end}),0)", margin_total), 9 if margin_total >= 0 else 6),
        ("Valor sob atenção", Formula(f"SUM({cost_range})-({approved_value_formula})", risk_value), 29),
        ("CT-es com margem negativa", Formula(f"COUNTIF('DETALHAMENTO'!${margin_class_letter}$6:${margin_class_letter}${detail_end},\"MARGEM NEGATIVA\")", class_counts["MARGEM NEGATIVA"]), 6),
        ("CT-es sem frete base", Formula(f"COUNTIF('DETALHAMENTO'!${margin_class_letter}$6:${margin_class_letter}${detail_end},\"SEM FRETE BASE\")", class_counts["SEM FRETE BASE"]), 13),
    )

    rows: dict[int, tuple[list[Any], list[int], float]] = {}
    merges = ["A1:T2", "A3:T3"]
    rows[1] = (["CENTRAL CT-e | VALIDAÇÃO EXECUTIVA DOS XMLs"] + [None] * 19, [1] + [0] * 19, 28)
    rows[2] = ([None] * 20, [1] + [0] * 19, 18)
    rows[3] = ([
        f"Gerado em {model.generated_at.strftime('%d/%m/%Y %H:%M:%S')}  •  validação comercial e rentabilidade separadas  •  RC26.6"
    ] + [None] * 19, [2] + [0] * 19, 24)
    rows[4] = ([None] * 20, [0] * 20, 8)
    starts = (0, 5, 10, 15)
    for card_index, (label, value, value_style) in enumerate(cards):
        top = 5 + (card_index // 4) * 5
        start = starts[card_index % 4]
        end = start + 4
        first, last = _column_name(start), _column_name(end)
        merges.extend((f"{first}{top}:{last}{top + 1}", f"{first}{top + 2}:{last}{top + 3}"))
        for row_number in range(top, top + 4):
            rows.setdefault(row_number, ([None] * 20, [0] * 20, 20 if row_number < top + 2 else 24))
        rows[top][0][start] = label
        rows[top][1][start] = 3
        rows[top + 2][0][start] = value
        rows[top + 2][1][start] = value_style
        rows[top + 4] = ([None] * 20, [0] * 20, 8)

    rows[20] = ([
        "A rentabilidade é gerencial e não altera o status comercial; itens SEM FRETE BASE ficam fora do lucro e da margem, sem serem tratados como prejuízo."
    ] + [None] * 19, [21] + [0] * 19, 30)
    merges.append("A20:T20")
    rows[78] = (["PARÂMETROS EDITÁVEIS DE RENTABILIDADE"] + [None] * 19, [20] + [0] * 19, 22)
    merges.append("A78:T78")
    rows[79] = ([
        "Margem bruta estimada antes de impostos, despesas internas e custos indiretos."
    ] + [None] * 17 + ["Margem baixa até", 0.10], [21] + [0] * 17 + [33, 34], 24)
    rows[80] = ([None] * 18 + ["Margem saudável até", 0.25], [0] * 18 + [33, 34], 24)
    merges.append("A79:R80")
    rows[81] = ([None] * 20, [0] * 20, 8)
    rows[82] = (["BASE AUXILIAR DINÂMICA DOS GRÁFICOS"] + [None] * 19, [20] + [0] * 19, 22)
    merges.append("A82:T82")
    rows[83] = ([
        "Parceiro", "Frete base", "Custo parceiro", "Lucro bruto", "Margem", None,
        "Classificação da margem", "CT-es", None, "Status de validação", "CT-es",
    ] + [None] * 9, [14, 14, 14, 14, 14, 0, 14, 14, 0, 14, 14] + [0] * 9, 32)

    for offset, partner in enumerate(partners):
        row_number = helper_start + offset
        initial = initial_partner[partner]
        rows[row_number] = ([
            partner,
            Formula(f"SUMIF('DETALHAMENTO'!${partner_letter}$6:${partner_letter}${detail_end},$A{row_number},'DETALHAMENTO'!${base_letter}$6:${base_letter}${detail_end})", initial["base"]),
            Formula(f"SUMIF('DETALHAMENTO'!${partner_letter}$6:${partner_letter}${detail_end},$A{row_number},'DETALHAMENTO'!${cost_letter}$6:${cost_letter}${detail_end})", initial["cost"]),
            Formula(f"SUMIF('DETALHAMENTO'!${partner_letter}$6:${partner_letter}${detail_end},$A{row_number},'DETALHAMENTO'!${profit_letter}$6:${profit_letter}${detail_end})", initial["profit"]),
            Formula(f"IF($B{row_number}>0,$D{row_number}/$B{row_number},0)", initial["margin"]),
        ] + [None] * 15, [15, 17, 17, 17, 18] + [0] * 15, 22)

    for offset, name in enumerate(margin_classes):
        row_number = helper_start + offset
        existing = rows.get(row_number, ([None] * 20, [0] * 20, 22))
        existing[0][6] = name
        existing[0][7] = Formula(f"COUNTIF('DETALHAMENTO'!${margin_class_letter}$6:${margin_class_letter}${detail_end},$G{row_number})", class_counts[name])
        existing[1][6:8] = [15, 16]
        rows[row_number] = existing

    for offset, name in enumerate(statuses):
        row_number = helper_start + offset
        existing = rows.get(row_number, ([None] * 20, [0] * 20, 22))
        existing[0][9] = name
        existing[0][10] = Formula(f"COUNTIF('DETALHAMENTO'!${status_letter}$6:${status_letter}${detail_end},$J{row_number})", status_counts[name])
        existing[1][9:11] = [15, 16]
        rows[row_number] = existing

    max_row = max(max(rows), partner_end, class_end, status_end)
    rows_xml = []
    for row_number in range(1, max_row + 1):
        values, styles, height = rows.get(row_number, ([None] * 20, [0] * 20, 18))
        rows_xml.append(_row_xml(row_number, values, styles, height=height))
    panel_xml = _worksheet_xml(
        rows_xml=rows_xml,
        widths=[16, 15, 15, 15, 15, 3, 27, 12, 3, 31, 12, 15, 15, 15, 15, 15, 15, 15, 23, 14],
        max_row=max_row,
        max_col=20,
        merges=merges,
        active=True,
        drawing=True,
        zoom=82,
    )

    partner_initial_rows = [initial_partner[name] for name in partners]
    charts = [
        _chart_xml(
            title="Frete base × custo por parceiro", categories=partners,
            series=(
                {"name": "Frete base", "values": [item["base"] for item in partner_initial_rows], "category_formula": f"'PAINEL'!$A${helper_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$B${helper_start}:$B${partner_end}", "color": BLUE, "format_code": "R$ #,##0.00"},
                {"name": "Custo parceiro", "values": [item["cost"] for item in partner_initial_rows], "category_formula": f"'PAINEL'!$A${helper_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$C${helper_start}:$C${partner_end}", "color": ORANGE, "format_code": "R$ #,##0.00"},
            ), bar_direction="col", currency_axis=True, chart_id=1,
        ),
        _chart_xml(
            title="Lucro bruto por parceiro", categories=partners,
            series=({"name": "Lucro bruto", "values": [item["profit"] for item in partner_initial_rows], "category_formula": f"'PAINEL'!$A${helper_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$D${helper_start}:$D${partner_end}", "color": GREEN, "format_code": "R$ #,##0.00"},),
            bar_direction="col", currency_axis=True, chart_id=2,
        ),
        _chart_xml(
            title="Margem bruta por parceiro", categories=partners,
            series=({"name": "Margem", "values": [item["margin"] for item in partner_initial_rows], "category_formula": f"'PAINEL'!$A${helper_start}:$A${partner_end}", "value_formula": f"'PAINEL'!$E${helper_start}:$E${partner_end}", "color": TEAL, "format_code": "0.0%"},),
            bar_direction="bar", currency_axis=False, chart_id=3,
        ),
        _chart_xml(
            title="Distribuição por classificação da margem", categories=list(margin_classes),
            series=({"name": "CT-es", "values": [class_counts[name] for name in margin_classes], "category_formula": f"'PAINEL'!$G${helper_start}:$G${class_end}", "value_formula": f"'PAINEL'!$H${helper_start}:$H${class_end}", "color": PURPLE, "format_code": "0"},),
            bar_direction="bar", currency_axis=False, chart_id=4,
        ),
        _chart_xml(
            title="Status de validação dos XMLs", categories=statuses,
            series=({"name": "CT-es", "values": [status_counts[name] for name in statuses], "category_formula": f"'PAINEL'!$J${helper_start}:$J${status_end}", "value_formula": f"'PAINEL'!$K${helper_start}:$K${status_end}", "color": RED, "format_code": "0"},),
            bar_direction="bar", currency_axis=False, chart_id=5,
        ),
    ]
    return panel_xml, charts


class XmlValidationXlsxWriter:
    VERSION = "2.7.0-RC26.6"

    ATTENTION_WIDTHS = (14, 24, 18, 14, 19, 22, 15, 15, 15, 24, 24, 42, 24, 42)
    DETAIL_WIDTHS = (
        14, 24, 18, 14, 16, 19, 20, 22, 12, 16, 17, 17, 24,
        16, 15, 16, 16, 22, 26, 42, 18, 18, 18, 15, 22,
    )
    AUDIT_WIDTHS = (
        22, 14, 8, 34, 20, 18, 16, 24, 34, 26, 16, 18, 22, 16, 16, 16,
        16, 14, 14, 18, 16, 14, 16, 16, 16, 14, 16, 20, 22, 48, 18, 48,
        18, 58, 18, 42, 18, 16, 20, 52, 34, 52, 22, 16, 30, 24, 26, 26,
        48, 30, 48, 28, 34, 52, 30, 18, 22, 18, 32, 48,
        34, 30, 20, 18, 24, 72,
    )

    def write(self, file_path: Path, model: Any) -> Path:
        from .xml_validation_report import ATTENTION_HEADERS, AUDIT_HEADERS, DETAIL_HEADERS

        if len(AUDIT_HEADERS) < 66:
            raise ValueError("A auditoria XML perdeu colunas técnicas da RC24.")
        if len(self.AUDIT_WIDTHS) != len(AUDIT_HEADERS):
            raise ValueError("As larguras da auditoria XML não acompanham o cabeçalho técnico.")

        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = file_path.with_name(file_path.name + ".tmp")
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass
        owner_file = file_path.with_name("~$" + file_path.name)
        if not file_path.exists():
            try:
                owner_file.unlink(missing_ok=True)
            except Exception:
                pass
        panel_xml, charts = _panel_sheet(model)
        specs = (
            ("ATENÇÃO", "ITENS QUE EXIGEM ATENÇÃO", f"{len(model.attention_rows)} ocorrência(s) comercial ou tecnicamente relevante(s); rentabilidade não altera o status.", ATTENTION_HEADERS, model.attention_rows, self.ATTENTION_WIDTHS, "Status", "TabelaAtencaoXML", 88),
            ("DETALHAMENTO", "DETALHAMENTO OPERACIONAL", f"Uma linha por CT-e • {len(model.detail_rows)} registro(s) • células amarelas de frete base e frete cobrado são editáveis.", DETAIL_HEADERS, model.detail_rows, self.DETAIL_WIDTHS, "Status", "TabelaDetalhamentoXML", 84),
            ("AUDITORIA_TÉCNICA", "AUDITORIA TÉCNICA COMPLETA", f"{len(model.audit_rows)} linha(s) • {len(AUDIT_HEADERS)} colunas técnicas preservadas e ampliadas • {model.corrected_toll_false_divergences} falsa(s) divergência(s) de pedágio corrigida(s).", AUDIT_HEADERS, model.audit_rows, self.AUDIT_WIDTHS, "Status", "TabelaAuditoriaXML", 68),
        )
        sheet_xmls = [panel_xml]
        table_refs: list[tuple[str, Sequence[str], str]] = []
        for table_id, (sheet_name, title, subtitle, headers, data, widths, status, table_name, zoom) in enumerate(specs, start=1):
            xml, reference = _tabular_sheet(
                sheet_name=sheet_name,
                title=title,
                subtitle=subtitle,
                headers=headers,
                data=data,
                widths=widths,
                status_header=status,
                table_id=table_id,
                zoom=zoom,
            )
            sheet_xmls.append(xml)
            table_refs.append((reference, headers, table_name))

        anchors = ((0, 20, 9, 36), (10, 20, 19, 36), (0, 37, 9, 53), (10, 37, 19, 53), (0, 54, 19, 70))
        with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("[Content_Types].xml", _content_types_xml(sheet_count=4, chart_count=CHART_COUNT, table_count=TABLE_COUNT))
            archive.writestr("_rels/.rels", _root_relationships_xml())
            archive.writestr("docProps/core.xml", _core_xml(model.generated_at, title="Relatório Executivo de Validação dos XMLs RC26.6", description="Validação comercial e rentabilidade derivadas da mesma base canônica por CT-e."))
            archive.writestr("docProps/app.xml", _app_xml(EXPECTED_SHEETS, version=self.VERSION))
            archive.writestr("xl/workbook.xml", _workbook_xml(EXPECTED_SHEETS))
            archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml(4))
            archive.writestr("xl/styles.xml", _styles_xml())
            for index, xml in enumerate(sheet_xmls, start=1):
                archive.writestr(f"xl/worksheets/sheet{index}.xml", xml)
            archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", _drawing_sheet_relationship_xml())
            for table_id, (reference, headers, table_name) in enumerate(table_refs, start=1):
                archive.writestr(f"xl/worksheets/_rels/sheet{table_id + 1}.xml.rels", _table_sheet_relationship_xml(table_id))
                archive.writestr(f"xl/tables/table{table_id}.xml", _table_xml(table_id, table_name, reference, headers))
            archive.writestr("xl/drawings/drawing1.xml", _drawing_xml(anchors))
            archive.writestr("xl/drawings/_rels/drawing1.xml.rels", _drawing_relationships_xml(CHART_COUNT))
            for index, chart in enumerate(charts, start=1):
                archive.writestr(f"xl/charts/chart{index}.xml", chart)

        validate_xlsx(
            temporary,
            sheet_count=4,
            chart_count=CHART_COUNT,
            table_count=TABLE_COUNT,
            require_formulas=True,
        )
        os.replace(temporary, file_path)
        with ZipFile(file_path, "r") as check:
            if check.testzip() is not None:
                raise ValueError("Relatório XML final contém entrada ZIP inválida.")
        return file_path


__all__ = ["XmlValidationXlsxWriter"]
