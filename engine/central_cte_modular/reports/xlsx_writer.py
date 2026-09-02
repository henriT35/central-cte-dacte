from __future__ import annotations

from datetime import datetime
from html import escape
import os
from pathlib import Path
import re
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

from ..invoices.normalization import normalize_token, strip_accents


def _column_name(index: int) -> str:
    index += 1
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _safe_sheet_name(name: Any, used: set[str]) -> str:
    cleaned = re.sub(r"[\\/?*\[\]:]", "_", str(name or "Sheet")).strip() or "Sheet"
    cleaned = cleaned[:31]
    base = cleaned
    suffix = 2
    while cleaned in used:
        tail = f"_{suffix}"
        cleaned = (base[:31 - len(tail)] + tail)[:31]
        suffix += 1
    used.add(cleaned)
    return cleaned


def _cell_xml(row: int, column: int, value: Any, style: int = 0) -> str:
    ref = f"{_column_name(column)}{row}"
    style_attr = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value != value:
            return f'<c r="{ref}"{style_attr}/>'
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    text = escape(str(value), quote=True)
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t xml:space="preserve">{text}</t></is></c>'


def _sheet_xml(rows: list[list[Any]], widths: list[float] | None = None) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    max_rows = max(len(rows), 1)
    dimension = f"A1:{_column_name(max_cols - 1)}{max_rows}"
    columns = ""
    if widths:
        columns = "<cols>" + "".join(
            f'<col min="{index + 1}" max="{index + 1}" width="{widths[index] if index < len(widths) else 14}" customWidth="1"/>'
            for index in range(max_cols)
        ) + "</cols>"
    row_xml: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            style = 1 if row_index == 1 else (2 if isinstance(value, (int, float)) else 0)
            cells.append(_cell_xml(row_index, column_index, value, style))
        row_xml.append(f'<row r="{row_index}">' + "".join(cells) + "</row>")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<dimension ref="{dimension}"/>
<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
{columns}<sheetData>{''.join(row_xml)}</sheetData><autoFilter ref="{dimension}"/>
</worksheet>'''


class ModularXlsxWriter:
    VERSION = "2.7.0-RC18"

    def write(self, path: Path, sheets: Iterable[Any]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        used: set[str] = set()
        normalized = [(_safe_sheet_name(name, used), list(rows or []), list(widths or [])) for name, rows, widths in list(sheets or [])]
        overrides, workbook_sheets, workbook_rels = [], [], []
        for index, (name, _rows, _widths) in enumerate(normalized, start=1):
            overrides.append(f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
            workbook_sheets.append(f'<sheet name="{escape(name, quote=True)}" sheetId="{index}" r:id="rId{index}"{(" state=\"hidden\"" if "Log_Status" in name else "")}/>')
            workbook_rels.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
        styles_rid = len(normalized) + 1
        workbook_rels.append(f'<Relationship Id="rId{styles_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
        content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>{''.join(overrides)}</Types>'''
        root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>'''
        workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{''.join(workbook_sheets)}</sheets></workbook>'''
        rels = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(workbook_rels)}</Relationships>'''
        styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="2"><numFmt numFmtId="164" formatCode="&quot;R$&quot; #.##0,00"/><numFmt numFmtId="165" formatCode="#.##0,00"/></numFmts><fonts count="6"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FF006100"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FF9C6500"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FF9C0006"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FF0B3B78"/><name val="Calibri"/></font></fonts><fills count="7"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0B4F9F"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFC6EFCE"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFEB9C"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD9E2F3"/></left><right style="thin"><color rgb="FFD9E2F3"/></right><top style="thin"><color rgb="FFD9E2F3"/></top><bottom style="thin"><color rgb="FFD9E2F3"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="10"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/><xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/><xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/><xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="165" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"><alignment vertical="center"/></xf><xf numFmtId="164" fontId="5" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyNumberFormat="1" applyBorder="1"/><xf numFmtId="0" fontId="5" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        core = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>Central CT-e / DACTE</dc:creator><cp:lastModifiedBy>Central CT-e / DACTE</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>'''
        app = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Central CT-e / DACTE</Application></Properties>'''
        temp = path.with_suffix(path.suffix + ".tmp")
        with ZipFile(temp, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("_rels/.rels", root_rels)
            archive.writestr("docProps/core.xml", core)
            archive.writestr("docProps/app.xml", app)
            archive.writestr("xl/workbook.xml", workbook)
            archive.writestr("xl/_rels/workbook.xml.rels", rels)
            archive.writestr("xl/styles.xml", styles)
            for index, (_name, rows, widths) in enumerate(normalized, start=1):
                archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows, widths))
        os.replace(temp, path)
        self._apply_presentation(path)
        return path

    def _apply_presentation(self, path: Path) -> None:
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ET.register_namespace("", ns)
        q = lambda tag: f"{{{ns}}}{tag}"
        with ZipFile(path, "r") as source:
            files = {name: source.read(name) for name in source.namelist()}
        technical_details = {"ORIGEMVALIDACAOVALOR", "REGRATABELA", "FONTEBASETABELA", "CONFIANCAVALOR", "CAMINHOCALCULOTABELA", "CAMINHODOSTATUS", "AVISOS"}
        technical_log = {"CHAVEFATURA", "CTRCORIGEMPDF", "FATURABASEEXP", "FATURABASEREC", "FONTEREGRA", "BASECALCULOTABELA", "FONTEBASETABELA", "PERCENTUALTABELA", "MINIMOTABELA", "TOLERANCIATABELA", "MODOTABELA", "VALORXML", "DIFERENCAXML", "ORIGEMVALIDACAOVALOR", "CONFIANCAVALOR", "VINCULOVALIDACAOVALOR", "REGRAAPLICADA", "STATUSVALORLEGADO"}
        count_headers = {"QTD", "OK", "PROBLEMA", "QTDCTESSEMCOMPROVANTE", "RESULTADO"}
        money_headers = {"VALORFATURA", "VALORNAOPAGAR", "VALORAPAGAR", "VALORCTE", "VALORBLOQUEADOPORCOMPROVANTE", "VALORBASECOMISSAO", "VALORESPERADOTABELA", "DIFERENCATABELA"}
        decimal_headers = {"PESOFATURA", "FRECTRCORIGEMFATURA", "TAMANHODABASEMB", "PERCENTUALTABELA", "MINIMOTABELA", "TOLERANCIATABELA", "VALORXML", "DIFERENCAXML"}

        def cell_text(cell: ET.Element) -> str:
            if cell.get("t") == "inlineStr":
                return "".join((node.text or "") for node in cell.iter(q("t")))
            node = cell.find(q("v"))
            return node.text if node is not None else ""

        def column_number(ref: str) -> int:
            letters = re.match(r"[A-Z]+", ref or "")
            total = 0
            for char in letters.group(0) if letters else "":
                total = total * 26 + ord(char) - 64
            return total

        for name, raw in list(files.items()):
            if not name.startswith("xl/worksheets/sheet") or not name.endswith(".xml"):
                continue
            root = ET.fromstring(raw)
            data = root.find(q("sheetData"))
            rows = data.findall(q("row")) if data is not None else []
            if not rows:
                continue
            header_by_col: dict[int, str] = {}
            for cell in rows[0].findall(q("c")):
                header_by_col[column_number(cell.get("r", ""))] = normalize_token(cell_text(cell))
            headers = set(header_by_col.values())
            rows[0].set("ht", "30")
            rows[0].set("customHeight", "1")
            is_base = {"INDICADOR", "RESULTADO", "OBSERVACAO"}.issubset(headers)
            is_summary = {"NUMERODAFATURA", "NOMEDOPARCEIRO", "QTD", "VALORFATURA", "STATUS"}.issubset(headers)
            is_details = {"FATURA", "PARCEIRO", "CTE", "NF", "STATUSCTE", "CAMINHODOSTATUS"}.issubset(headers)
            is_log = {"FATURA", "PARCEIRO", "SEQ", "ARQUIVOPDF", "STATUSFINAL", "CAMINHODOSTATUS"}.issubset(headers)
            if is_details or is_log:
                views = root.find(q("sheetViews"))
                view = views.find(q("sheetView")) if views is not None else None
                pane = view.find(q("pane")) if view is not None else None
                if pane is not None:
                    pane.set("xSplit", "4")
                    pane.set("ySplit", "1")
                    pane.set("topLeftCell", "E2")
                    pane.set("activePane", "bottomRight")
                    pane.set("state", "frozen")
            hidden_set = technical_details if is_details else (technical_log if is_log else set())
            if hidden_set:
                cols = root.find(q("cols"))
                if cols is not None:
                    for col in cols.findall(q("col")):
                        try:
                            index = int(col.get("min", "0"))
                        except Exception:
                            continue
                        if header_by_col.get(index) in hidden_set:
                            col.set("hidden", "1")
            for row in rows[1:]:
                first_cell = row.find(q("c"))
                first_value = strip_accents(cell_text(first_cell)).upper() if first_cell is not None else ""
                is_total = first_value == "TOTAL GERAL"
                if is_total:
                    row.set("ht", "24")
                    row.set("customHeight", "1")
                elif is_base:
                    row.set("ht", "22")
                    row.set("customHeight", "1")
                for cell in row.findall(q("c")):
                    col = column_number(cell.get("r", ""))
                    header = header_by_col.get(col, "")
                    value = strip_accents(cell_text(cell)).upper()
                    if is_total:
                        cell.set("s", "8" if header in money_headers else "9")
                        continue
                    if is_base and header == "RESULTADO":
                        if first_value.startswith("VALOR "):
                            cell.set("s", "2")
                        elif "TAMANHO" in first_value:
                            cell.set("s", "7")
                        elif value.replace(".", "", 1).isdigit():
                            cell.set("s", "6")
                        continue
                    if header in count_headers and not is_base:
                        cell.set("s", "6")
                        continue
                    if header in money_headers:
                        cell.set("s", "2")
                    elif header in decimal_headers:
                        cell.set("s", "7")
                    if header not in {"STATUS", "STATUSDOVALORINFORMATIVO", "STATUSVALOR", "STATUSTABELAPARCEIRO", "STATUSCTE", "STATUSFINAL"}:
                        continue
                    if any(token in value for token in ("NAO PAGAR", "NÃO PAGAR", "SEM COMPROVANTE", "FORA DA BASE")):
                        cell.set("s", "5")
                    elif "PAGAR PARCIAL" in value or "PARCIAL" in value or "REVISAR" in value:
                        cell.set("s", "4")
                    elif value.startswith("OK"):
                        cell.set("s", "3")
                    else:
                        cell.set("s", "4")
            files[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        temp = path.with_suffix(path.suffix + ".style.tmp")
        with ZipFile(temp, "w", compression=ZIP_DEFLATED) as target:
            for name, data in files.items():
                target.writestr(name, data)
        os.replace(temp, path)
