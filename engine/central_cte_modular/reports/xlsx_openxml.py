from __future__ import annotations

"""Primitivas OpenXML compartilhadas pelos relatórios executivos RC26.6.

O módulo usa somente a biblioteca padrão. Ele não interpreta regras comerciais:
apenas serializa valores, fórmulas, estilos, tabelas, validações e gráficos já
definidos pelos modelos de relatório.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.etree import ElementTree
from zipfile import ZipFile


NAVY = "123F5E"
BLUE = "1F78A9"
TEAL = "176B87"
ORANGE = "ED7D31"
GREEN = "178653"
RED = "C62828"
AMBER = "B36B00"
PURPLE = "6F42C1"
LIGHT_BLUE = "EAF3F8"
LIGHT_GREEN = "DCFCE7"
LIGHT_RED = "FEE2E2"
LIGHT_AMBER = "FEF3C7"
LIGHT_PURPLE = "F3E8FF"
LIGHT_EDIT = "FFF2CC"
LIGHT_GREY = "F5F7FA"
GRID = "D9E3EC"


@dataclass(frozen=True)
class Formula:
    """Fórmula Excel invariável com valor inicial em cache."""

    expression: str
    cached: Any = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "expression", str(self.expression or "").lstrip("="))


def formula_value(value: Any) -> Any:
    return value.cached if isinstance(value, Formula) else value


def _xml(value: Any) -> str:
    return escape("" if value is None else str(value), quote=True)


def _column_name(index: int) -> str:
    index += 1
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_ref(row: int, column: int) -> str:
    return f"{_column_name(column)}{row}"


def _finite_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number):
            return value if isinstance(value, int) else number
    return None


def _cell_xml(
    row: int,
    column: int,
    value: Any,
    style: int = 0,
    *,
    force_text: bool = False,
) -> str:
    reference = _cell_ref(row, column)
    style_attr = f' s="{style}"' if style else ""
    if isinstance(value, Formula):
        cached = value.cached
        formula = f"<f>{_xml(value.expression)}</f>"
        if isinstance(cached, bool):
            return f'<c r="{reference}" t="b"{style_attr}>{formula}<v>{1 if cached else 0}</v></c>'
        number = _finite_number(cached)
        if number is not None:
            return f'<c r="{reference}"{style_attr}>{formula}<v>{number}</v></c>'
        return f'<c r="{reference}" t="str"{style_attr}>{formula}<v>{_xml(cached)}</v></c>'
    if value is None or value == "":
        return f'<c r="{reference}"{style_attr}/>'
    if isinstance(value, bool) and not force_text:
        return f'<c r="{reference}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    number = None if force_text else _finite_number(value)
    if number is not None:
        return f'<c r="{reference}"{style_attr}><v>{number}</v></c>'
    text = str(value)
    space = ' xml:space="preserve"' if text != text.strip() or "\n" in text else ""
    return f'<c r="{reference}" t="inlineStr"{style_attr}><is><t{space}>{_xml(text)}</t></is></c>'


def _row_xml(
    row_index: int,
    values: Sequence[Any],
    styles: Sequence[int] | None = None,
    *,
    height: float | None = None,
    text_columns: set[int] | None = None,
    hidden: bool = False,
) -> str:
    styles = styles or []
    text_columns = text_columns or set()
    cells = [
        _cell_xml(
            row_index,
            column,
            value,
            styles[column] if column < len(styles) else 0,
            force_text=column in text_columns,
        )
        for column, value in enumerate(values)
    ]
    height_attr = f' ht="{height}" customHeight="1"' if height else ""
    hidden_attr = ' hidden="1"' if hidden else ""
    return f'<row r="{row_index}"{height_attr}{hidden_attr}>{"".join(cells)}</row>'


def _cols_xml(widths: Sequence[float]) -> str:
    columns: list[str] = []
    for index, width in enumerate(widths, start=1):
        numeric_width = float(width)
        hidden = ' hidden="1"' if numeric_width <= 0 else ""
        columns.append(
            f'<col min="{index}" max="{index}" width="{max(numeric_width, 0.0)}" customWidth="1"{hidden}/>'
        )
    return "<cols>" + "".join(columns) + "</cols>"


def _merge_xml(merges: Sequence[str]) -> str:
    if not merges:
        return ""
    return f'<mergeCells count="{len(merges)}">' + "".join(
        f'<mergeCell ref="{_xml(reference)}"/>' for reference in merges
    ) + "</mergeCells>"


def _sheet_view_xml(*, active: bool = False, freeze_row: int | None = None, zoom: int = 90) -> str:
    selected = ' tabSelected="1"' if active else ""
    if freeze_row:
        return (
            f'<sheetViews><sheetView showGridLines="0" zoomScale="{zoom}" zoomScaleNormal="{zoom}"'
            f'{selected} workbookViewId="0">'
            f'<pane ySplit="{freeze_row}" topLeftCell="A{freeze_row + 1}" activePane="bottomLeft" state="frozen"/>'
            f'<selection pane="bottomLeft" activeCell="A{freeze_row + 1}" sqref="A{freeze_row + 1}"/>'
            '</sheetView></sheetViews>'
        )
    return (
        f'<sheetViews><sheetView showGridLines="0" zoomScale="{zoom}" zoomScaleNormal="{zoom}"'
        f'{selected} workbookViewId="0"><selection activeCell="A1" sqref="A1"/></sheetView></sheetViews>'
    )


def _worksheet_xml(
    *,
    rows_xml: Sequence[str],
    widths: Sequence[float],
    max_row: int,
    max_col: int,
    merges: Sequence[str] = (),
    active: bool = False,
    freeze_row: int | None = None,
    auto_filter: str = "",
    conditional: str = "",
    drawing: bool = False,
    zoom: int = 90,
    landscape: bool = True,
    data_validations: str = "",
    table_parts: str = "",
) -> str:
    dimension = f"A1:{_column_name(max_col - 1)}{max(max_row, 1)}"
    # Tabelas nativas possuem o próprio <autoFilter> em xl/tables/tableN.xml.
    # Emitir também um AutoFilter no nível da planilha sobre o mesmo intervalo
    # cria duas definições concorrentes; o Microsoft Excel repara o arquivo
    # removendo o AutoFiltro e a própria tabela.
    filter_xml = (
        f'<autoFilter ref="{_xml(auto_filter)}"/>'
        if auto_filter and not table_parts
        else ""
    )
    drawing_xml = '<drawing r:id="rId1"/>' if drawing else ""
    orientation = ' orientation="landscape"' if landscape else ' orientation="portrait"'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetPr><outlinePr summaryBelow="1" summaryRight="1"/><pageSetUpPr fitToPage="1"/></sheetPr>
<dimension ref="{dimension}"/>
{_sheet_view_xml(active=active, freeze_row=freeze_row, zoom=zoom)}
<sheetFormatPr defaultRowHeight="18"/>
{_cols_xml(widths)}
<sheetData>{''.join(rows_xml)}</sheetData>
{filter_xml}
{_merge_xml(merges)}
{conditional}
{data_validations}
<printOptions horizontalCentered="0" verticalCentered="0"/>
<pageMargins left="0.25" right="0.25" top="0.4" bottom="0.4" header="0.2" footer="0.2"/>
<pageSetup paperSize="9" fitToWidth="1" fitToHeight="0"{orientation}/>
{drawing_xml}
{table_parts}
</worksheet>'''


def _list_validation_xml(cell_range: str, values: Sequence[str]) -> str:
    formula = '"' + ",".join(str(value) for value in values) + '"'
    return (
        '<dataValidations count="1">'
        f'<dataValidation type="list" allowBlank="1" showInputMessage="1" showErrorMessage="1" '
        f'errorStyle="stop" errorTitle="Valor inválido" error="Escolha S, N ou -." '
        f'promptTitle="Comprovante" prompt="Selecione S, N ou -." sqref="{_xml(cell_range)}">'
        f'<formula1>{_xml(formula)}</formula1></dataValidation></dataValidations>'
    )


def _conditional_status_xml(
    data_range: str,
    status_column: str,
    first_row: int,
    *,
    priority_start: int = 1,
) -> str:
    if not data_range:
        return ""
    cell = f"${status_column}{first_row}"
    green = f'OR(LEFT({cell},2)="OK",{cell}="OK PARA PAGAMENTO")'
    red_tokens = (
        "DIVERGENTE", "PROBLEMA INTERNO", "CONFERÊNCIA", "CONFERENCIA", "REGRA NÃO", "REGRA NAO",
        "SEM REGRA", "PARCEIRO SEM", "ORIGINAL NÃO", "ORIGINAL NAO", "NF FORA", "FORA DA BASE",
        "SEM BASE", "ROTA INVÁLIDA", "ROTA INVALIDA", "ERRO", "FALHA", "INCONSISTÊNCIA",
        "INCONSISTENCIA",
    )
    red = "OR(" + ",".join(f'ISNUMBER(SEARCH("{token}",{cell}))' for token in red_tokens) + ")"
    yellow = f'{cell}<>""'
    return (
        f'<conditionalFormatting sqref="{_xml(data_range)}">'
        f'<cfRule type="expression" dxfId="0" priority="{priority_start}" stopIfTrue="1"><formula>{_xml(green)}</formula></cfRule>'
        f'<cfRule type="expression" dxfId="1" priority="{priority_start + 1}" stopIfTrue="1"><formula>{_xml(red)}</formula></cfRule>'
        f'<cfRule type="expression" dxfId="2" priority="{priority_start + 2}" stopIfTrue="1"><formula>{_xml(yellow)}</formula></cfRule>'
        '</conditionalFormatting>'
    )


def _conditional_margin_xml(
    cell_range: str,
    column: str,
    first_row: int,
    *,
    priority_start: int = 1,
) -> str:
    if not cell_range:
        return ""
    cell = f"${column}{first_row}"
    rules = (
        (f'{cell}="MARGEM NEGATIVA"', 1, priority_start),
        (f'{cell}="MARGEM BAIXA"', 2, priority_start + 1),
        (f'OR({cell}="MARGEM SAUDÁVEL",{cell}="MARGEM ALTA")', 0, priority_start + 2),
        (f'OR({cell}="SEM FRETE BASE",{cell}="SEM DADOS")', 3, priority_start + 3),
    )
    body = "".join(
        f'<cfRule type="expression" dxfId="{dxf}" priority="{priority}" stopIfTrue="1"><formula>{_xml(formula)}</formula></cfRule>'
        for formula, dxf, priority in rules
    )
    return f'<conditionalFormatting sqref="{_xml(cell_range)}">{body}</conditionalFormatting>'


def _styles_xml() -> str:
    currency = '&quot;R$&quot; #,##0.00;[Red]-&quot;R$&quot; #,##0.00'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="4">
  <numFmt numFmtId="164" formatCode="{currency}"/>
  <numFmt numFmtId="165" formatCode="0.0%"/>
  <numFmt numFmtId="166" formatCode="#0.00 &quot;kg&quot;"/>
  <numFmt numFmtId="167" formatCode="dd/mm/yyyy hh:mm"/>
</numFmts>
<fonts count="11">
  <font><sz val="10"/><color rgb="FF26323F"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><i/><sz val="10"/><color rgb="FF{NAVY}"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="10"/><color rgb="FF5B6875"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="16"/><color rgb="FF{NAVY}"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="16"/><color rgb="FF{GREEN}"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="16"/><color rgb="FF{RED}"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="16"/><color rgb="FF{AMBER}"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><i/><sz val="9"/><color rgb="FF5B6875"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
  <font><b/><sz val="10"/><color rgb="FF1F4E78"/><name val="Calibri"/><family val="2"/><scheme val="minor"/></font>
</fonts>
<fills count="11">
  <fill><patternFill patternType="none"/></fill>
  <fill><patternFill patternType="gray125"/></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{NAVY}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_BLUE}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_GREEN}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_RED}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_AMBER}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{BLUE}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_GREY}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_EDIT}"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_PURPLE}"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
  <border><left/><right/><top/><bottom/><diagonal/></border>
  <border><left style="thin"><color rgb="FF{GRID}"/></left><right style="thin"><color rgb="FF{GRID}"/></right><top style="thin"><color rgb="FF{GRID}"/></top><bottom style="thin"><color rgb="FF{GRID}"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="39">
  <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
  <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="3" fontId="4" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="3" fontId="5" fillId="4" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="3" fontId="6" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="164" fontId="4" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="164" fontId="6" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="165" fontId="5" fillId="4" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="3" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="3" fontId="7" fillId="6" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="8" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>
  <xf numFmtId="3" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
  <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
  <xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
  <xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
  <xf numFmtId="0" fontId="8" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="9" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="3" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="3" fontId="4" fillId="8" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="164" fontId="4" fillId="8" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="9" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="164" fontId="5" fillId="4" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="0" fillId="8" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="164" fontId="7" fillId="6" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="10" fillId="9" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="164" fontId="10" fillId="9" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
  <xf numFmtId="3" fontId="4" fillId="10" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="3" fillId="10" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  <xf numFmtId="165" fontId="10" fillId="9" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
  <xf numFmtId="0" fontId="8" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>
  <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
  <xf numFmtId="0" fontId="10" fillId="9" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
<dxfs count="4">
  <dxf><font><color rgb="FF166534"/></font><fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_GREEN}"/><bgColor indexed="64"/></patternFill></fill></dxf>
  <dxf><font><color rgb="FF991B1B"/></font><fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_RED}"/><bgColor indexed="64"/></patternFill></fill></dxf>
  <dxf><font><color rgb="FF92400E"/></font><fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_AMBER}"/><bgColor indexed="64"/></patternFill></fill></dxf>
  <dxf><font><color rgb="FF6B21A8"/></font><fill><patternFill patternType="solid"><fgColor rgb="FF{LIGHT_PURPLE}"/><bgColor indexed="64"/></patternFill></fill></dxf>
</dxfs>
<tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''


def _table_xml(table_id: int, display_name: str, reference: str, headers: Sequence[str]) -> str:
    columns = "".join(
        f'<tableColumn id="{index}" name="{_xml(header)}"/>'
        for index, header in enumerate(headers, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<table xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" id="{table_id}" name="{display_name}" displayName="{display_name}" ref="{reference}" totalsRowShown="0">
<autoFilter ref="{reference}"/><tableColumns count="{len(headers)}">{columns}</tableColumns>
<tableStyleInfo name="TableStyleMedium2" showFirstColumn="0" showLastColumn="0" showRowStripes="1" showColumnStripes="0"/>
</table>'''


def _chart_title_xml(title: str) -> str:
    return (
        '<c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="pt-BR" sz="1100" b="1"/>'
        f'<a:t>{_xml(title)}</a:t></a:r></a:p></c:rich></c:tx><c:layout/><c:overlay val="0"/></c:title>'
    )


def _string_cache(values: Sequence[str]) -> str:
    points = "".join(f'<c:pt idx="{i}"><c:v>{_xml(value)}</c:v></c:pt>' for i, value in enumerate(values))
    return f'<c:ptCount val="{len(values)}"/>{points}'


def _number_cache(values: Sequence[float], format_code: str) -> str:
    points = "".join(f'<c:pt idx="{i}"><c:v>{float(value or 0.0)}</c:v></c:pt>' for i, value in enumerate(values))
    return f'<c:formatCode>{_xml(format_code)}</c:formatCode><c:ptCount val="{len(values)}"/>{points}'


def _series_xml(
    index: int,
    name: str,
    categories: Sequence[str],
    values: Sequence[float],
    category_formula: str,
    value_formula: str,
    color: str,
    number_format: str,
) -> str:
    return f'''<c:ser><c:idx val="{index}"/><c:order val="{index}"/>
<c:tx><c:v>{_xml(name)}</c:v></c:tx><c:spPr><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:ln><a:noFill/></a:ln></c:spPr>
<c:cat><c:strRef><c:f>{_xml(category_formula)}</c:f><c:strCache>{_string_cache(categories)}</c:strCache></c:strRef></c:cat>
<c:val><c:numRef><c:f>{_xml(value_formula)}</c:f><c:numCache>{_number_cache(values, number_format)}</c:numCache></c:numRef></c:val>
</c:ser>'''


def _chart_xml(
    *,
    title: str,
    categories: Sequence[str],
    series: Sequence[Mapping[str, Any]],
    bar_direction: str,
    currency_axis: bool,
    chart_id: int,
) -> str:
    cat_axis = 10_000_000 + chart_id * 2
    val_axis = cat_axis + 1
    series_xml = "".join(
        _series_xml(
            index,
            item["name"],
            categories,
            item["values"],
            item["category_formula"],
            item["value_formula"],
            item["color"],
            item.get("format_code", "General"),
        )
        for index, item in enumerate(series)
    )
    legend = '<c:legend><c:legendPos val="b"/><c:layout/><c:overlay val="0"/></c:legend>' if len(series) > 1 else ""
    if currency_axis:
        axis_format = '&quot;R$&quot; #,##0.00'
    elif series:
        axis_format = _xml(series[0].get("format_code", "General"))
    else:
        axis_format = "General"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<c:date1904 val="0"/><c:lang val="pt-BR"/><c:roundedCorners val="0"/>
<c:chart>{_chart_title_xml(title)}<c:autoTitleDeleted val="0"/>
<c:plotArea><c:layout/><c:barChart><c:barDir val="{bar_direction}"/><c:grouping val="clustered"/><c:varyColors val="0"/>{series_xml}<c:gapWidth val="85"/><c:overlap val="0"/><c:axId val="{cat_axis}"/><c:axId val="{val_axis}"/></c:barChart>
<c:catAx><c:axId val="{cat_axis}"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="l"/><c:tickLblPos val="nextTo"/><c:crossAx val="{val_axis}"/><c:crosses val="autoZero"/><c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/></c:catAx>
<c:valAx><c:axId val="{val_axis}"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="b"/><c:numFmt formatCode="{axis_format}" sourceLinked="0"/><c:majorGridlines/><c:tickLblPos val="nextTo"/><c:crossAx val="{cat_axis}"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx>
</c:plotArea>{legend}<c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/><c:showDLblsOverMax val="0"/></c:chart>
<c:printSettings><c:headerFooter/><c:pageMargins b="0.75" l="0.7" r="0.7" t="0.75" header="0.3" footer="0.3"/><c:pageSetup/></c:printSettings>
</c:chartSpace>'''


def _drawing_xml(anchors: Sequence[tuple[int, int, int, int]]) -> str:
    frames: list[str] = []
    for index, (from_col, from_row, to_col, to_row) in enumerate(anchors, start=1):
        frames.append(f'''<xdr:twoCellAnchor editAs="oneCell">
<xdr:from><xdr:col>{from_col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{from_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
<xdr:to><xdr:col>{to_col}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{to_row}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>
<xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="{index + 1}" name="Gráfico {index}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId{index}"/></a:graphicData></a:graphic></xdr:graphicFrame>
<xdr:clientData/></xdr:twoCellAnchor>''')
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">''' + "".join(frames) + "</xdr:wsDr>"


def _workbook_xml(sheet_names: Sequence[str]) -> str:
    sheets = "".join(
        f'<sheet name="{_xml(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<fileVersion appName="xl" lastEdited="7" lowestEdited="7"/><workbookPr date1904="0"/>
<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="14000" activeTab="0"/></bookViews>
<sheets>{sheets}</sheets><calcPr calcId="191029" calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/></workbook>'''


def _app_xml(sheet_names: Sequence[str], *, version: str) -> str:
    titles = "".join(f'<vt:lpstr>{_xml(name)}</vt:lpstr>' for name in sheet_names)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Central CT-e / DACTE</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>
<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Planilhas</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(sheet_names)}</vt:i4></vt:variant></vt:vector></HeadingPairs>
<TitlesOfParts><vt:vector size="{len(sheet_names)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>
<Company>Rodovitor Transportes</Company><AppVersion>{_xml(version)}</AppVersion></Properties>'''


def _core_xml(timestamp: datetime, *, title: str, description: str) -> str:
    stamp = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>{_xml(title)}</dc:title><dc:creator>Central CT-e / DACTE</dc:creator><cp:lastModifiedBy>Central CT-e / DACTE</cp:lastModifiedBy>
<dc:description>{_xml(description)}</dc:description>
<dcterms:created xsi:type="dcterms:W3CDTF">{stamp}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{stamp}</dcterms:modified></cp:coreProperties>'''


def _content_types_xml(*, sheet_count: int, chart_count: int, table_count: int) -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    charts = "".join(
        f'<Override PartName="/xl/charts/chart{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>'
        for index in range(1, chart_count + 1)
    )
    tables = "".join(
        f'<Override PartName="/xl/tables/table{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>'
        for index in range(1, table_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>
{sheets}{charts}{tables}</Types>'''


def _root_relationships_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''


def _workbook_relationships_xml(sheet_count: int) -> str:
    worksheets = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{worksheets}<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''


def _drawing_relationships_xml(chart_count: int) -> str:
    relationships = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart{index}.xml"/>'
        for index in range(1, chart_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{relationships}</Relationships>'''


def _drawing_sheet_relationship_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/></Relationships>'''


def _table_sheet_relationship_xml(table_id: int) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/table" Target="../tables/table{table_id}.xml"/></Relationships>'''


def validate_xlsx(
    path: Path,
    *,
    sheet_count: int,
    chart_count: int,
    table_count: int,
    require_formulas: bool,
    require_data_validation: bool = False,
) -> None:
    required = {"[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml", "xl/drawings/drawing1.xml"}
    required.update(f"xl/worksheets/sheet{index}.xml" for index in range(1, sheet_count + 1))
    required.update(f"xl/charts/chart{index}.xml" for index in range(1, chart_count + 1))
    required.update(f"xl/tables/table{index}.xml" for index in range(1, table_count + 1))
    with ZipFile(path, "r") as archive:
        names = set(archive.namelist())
        missing = required - names
        if missing:
            raise ValueError(f"XLSX incompleto: {sorted(missing)}")
        corrupt = archive.testzip()
        if corrupt:
            raise ValueError(f"Parte corrompida no XLSX: {corrupt}")
        for name in names:
            if name.endswith((".xml", ".rels")):
                ElementTree.fromstring(archive.read(name))
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        required_calc = ('activeTab="0"', 'calcMode="auto"', 'fullCalcOnLoad="1"', 'forceFullCalc="1"')
        if workbook.count("<sheet ") != sheet_count or any(token not in workbook for token in required_calc):
            raise ValueError("Workbook sem abas, aba ativa ou recálculo automático conforme o contrato RC25.")
        drawing = archive.read("xl/drawings/drawing1.xml").decode("utf-8")
        if drawing.count("<xdr:graphicFrame") != chart_count:
            raise ValueError(f"O PAINEL não contém os {chart_count} gráficos nativos.")
        all_xml = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith((".xml", ".rels"))
        )
        for error in ("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A"):
            if error in all_xml:
                raise ValueError(f"O XLSX contém erro de fórmula: {error}")
        formulas = []
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for index in range(1, sheet_count + 1):
            root = ElementTree.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml"))
            formulas.extend((node.text or "") for node in root.findall(".//x:f", namespace))
        if require_formulas and not formulas:
            raise ValueError("O XLSX deveria conter fórmulas, mas nenhuma foi encontrada.")
        if any("[" in formula or "]" in formula for formula in formulas):
            raise ValueError("O XLSX contém fórmula com possível referência externa.")
        if require_data_validation and "<dataValidation " not in all_xml:
            raise ValueError("O XLSX não contém a validação de dados obrigatória.")


__all__ = [
    "AMBER", "BLUE", "Formula", "GREEN", "NAVY", "ORANGE", "PURPLE", "RED", "TEAL",
    "_app_xml", "_chart_xml", "_column_name", "_conditional_margin_xml", "_conditional_status_xml",
    "_content_types_xml", "_core_xml", "_drawing_relationships_xml", "_drawing_sheet_relationship_xml",
    "_drawing_xml", "_list_validation_xml", "_root_relationships_xml", "_row_xml", "_styles_xml",
    "_table_sheet_relationship_xml", "_table_xml", "_workbook_relationships_xml", "_workbook_xml",
    "_worksheet_xml", "_xml", "formula_value", "validate_xlsx",
]
