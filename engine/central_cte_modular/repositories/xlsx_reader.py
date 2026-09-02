from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from ..infrastructure.normalization import norm_text


class StandardLibraryXlsxReader:
    MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    OFFICE_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    PACKAGE_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

    @staticmethod
    def column_to_index(column: str) -> int:
        number = 0
        for character in column:
            number = number * 26 + ord(character.upper()) - 64
        return number - 1

    def _shared_strings(self, archive: ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        strings: list[str] = []
        with archive.open("xl/sharedStrings.xml") as stream:
            for event, element in ET.iterparse(stream, events=("end",)):
                if element.tag == f"{self.MAIN_NS}si":
                    strings.append("".join(node.text or "" for node in element.iter(f"{self.MAIN_NS}t")))
                    element.clear()
        return strings

    def _sheet_paths(self, archive: ZipFile) -> dict[str, str]:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            relation.attrib.get("Id", ""): relation.attrib.get("Target", "")
            for relation in relations.findall(f"{self.PACKAGE_REL_NS}Relationship")
        }
        result: dict[str, str] = {}
        for sheet in workbook.findall(f".//{self.MAIN_NS}sheets/{self.MAIN_NS}sheet"):
            name = sheet.attrib.get("name", "")
            relation_id = sheet.attrib.get(f"{self.OFFICE_REL_NS}id", "")
            target = targets.get(relation_id, "")
            if target:
                result[name] = target.lstrip("/") if target.startswith("/") else "xl/" + target
        return result

    def _resolve_sheet(self, archive: ZipFile, sheet_name: str | None) -> str:
        sheets = self._sheet_paths(archive)
        if not sheets:
            raise ValueError("Nenhuma aba encontrada no XLSX.")
        if sheet_name and sheet_name in sheets:
            return sheets[sheet_name]
        if sheet_name:
            wanted = norm_text(sheet_name)
            for name, path in sheets.items():
                if norm_text(name) == wanted:
                    return path
            raise ValueError(f"Aba '{sheet_name}' não encontrada. Abas disponíveis: {', '.join(sheets)}")
        return next(iter(sheets.values()))

    def _iter_rows(self, archive: ZipFile, sheet_path: str, shared: list[str]) -> Iterator[list[Any]]:
        with archive.open(sheet_path) as stream:
            for event, element in ET.iterparse(stream, events=("end",)):
                if element.tag != f"{self.MAIN_NS}row":
                    continue
                values: list[Any] = []
                for cell in element.findall(f"{self.MAIN_NS}c"):
                    reference = cell.attrib.get("r", "A1")
                    match = re.match(r"[A-Z]+", reference)
                    if not match:
                        continue
                    index = self.column_to_index(match.group(0))
                    while len(values) <= index:
                        values.append("")
                    cell_type = cell.attrib.get("t")
                    value: Any = ""
                    if cell_type == "inlineStr":
                        value = "".join(node.text or "" for node in cell.iter(f"{self.MAIN_NS}t"))
                    else:
                        node = cell.find(f"{self.MAIN_NS}v")
                        if node is not None:
                            value = node.text or ""
                            if cell_type == "s" and value != "":
                                value = shared[int(value)]
                    values[index] = value
                while values and values[-1] == "":
                    values.pop()
                yield values
                element.clear()

    def iter_sheet(self, file_path: str | Path, sheet_name: str | None = None) -> Iterator[list[Any]]:
        """Itera linhas sem materializar a planilha inteira em memória.

        O gerador mantém o ZIP aberto até o fim da iteração. É usado pelo
        vínculo modular de faturas para varrer a base grande com memória
        limitada.
        """
        path = Path(file_path)
        with ZipFile(path) as archive:
            shared = self._shared_strings(archive)
            sheet_path = self._resolve_sheet(archive, sheet_name)
            yield from self._iter_rows(archive, sheet_path, shared)

    def read_sheet(self, file_path: str | Path, sheet_name: str | None = None) -> list[list[Any]]:
        return list(self.iter_sheet(file_path, sheet_name))

    def read_sheet_sample(self, file_path: str | Path, max_data_rows: int = 500) -> list[list[Any]]:
        path = Path(file_path)
        limit = max(1, int(max_data_rows)) + 1
        with ZipFile(path) as archive:
            shared = self._shared_strings(archive)
            sheet_path = self._resolve_sheet(archive, None)
            rows: list[list[Any]] = []
            for row in self._iter_rows(archive, sheet_path, shared):
                rows.append(row)
                if len(rows) >= limit:
                    break
            return rows

    def try_read_sheet(self, file_path: str | Path, sheet_name: str) -> list[list[Any]]:
        try:
            return self.read_sheet(file_path, sheet_name)
        except Exception:
            return []
