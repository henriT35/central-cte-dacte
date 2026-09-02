from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional
from xml.etree import ElementTree as ET


class ElementIndex:
    """Índice leve de tags criado em uma única passagem pela árvore XML.

    O parser antigo percorria ``root.iter()`` repetidamente para cada campo.
    Este índice mantém as mesmas referências de ``ElementTree`` agrupadas pelo
    nome local da tag, eliminando dezenas de varreduras completas por documento.
    """

    __slots__ = ("root", "_by_name")

    def __init__(self, root: ET.Element) -> None:
        self.root = root
        grouped: dict[str, list[ET.Element]] = defaultdict(list)
        for element in root.iter():
            grouped[local_name(str(element.tag))].append(element)
        self._by_name = dict(grouped)

    def first(self, name: str) -> Optional[ET.Element]:
        items = self._by_name.get(str(name), ())
        return items[0] if items else None

    def all(self, name: str) -> list[ET.Element]:
        return list(self._by_name.get(str(name), ()))

    def count(self, name: str) -> int:
        return len(self._by_name.get(str(name), ()))


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def build_index(root: ET.Element) -> ElementIndex:
    return ElementIndex(root)


def first(root: ET.Element | ElementIndex, name: str) -> Optional[ET.Element]:
    if isinstance(root, ElementIndex):
        return root.first(name)
    for elem in root.iter():
        if local_name(str(elem.tag)) == name:
            return elem
    return None


def all_of(root: ET.Element | ElementIndex, name: str) -> list[ET.Element]:
    if isinstance(root, ElementIndex):
        return root.all(name)
    return [elem for elem in root.iter() if local_name(str(elem.tag)) == name]


def child(parent: Optional[ET.Element], name: str) -> Optional[ET.Element]:
    if parent is None:
        return None
    for elem in list(parent):
        if local_name(str(elem.tag)) == name:
            return elem
    return None


def text(parent: Optional[ET.Element], name: str | None = None, default: str = "") -> str:
    elem = child(parent, name) if name else parent
    if elem is not None and elem.text:
        return elem.text.strip()
    return default


def parse_root(path: Path) -> ET.Element:
    return ET.parse(path).getroot()


def inf_id(inf: Optional[ET.Element]) -> str:
    if inf is None:
        return ""
    raw = inf.attrib.get("Id", "")
    return raw.replace("CTe", "").replace("NFe", "").replace("MDFe", "")


def observation_line(field: str, value: str) -> str:
    field = (field or "").strip()
    value = (value or "").strip()
    if not value:
        return ""
    if field and not value.upper().startswith((field + ":").upper()):
        return f"{field}: {value}"
    return value


def observation_parts(root: ET.Element | ElementIndex) -> dict[str, str]:
    compl = first(root, "compl")
    principal = text(compl, "xObs").strip()
    lines: list[str] = []
    seen: set[str] = set()
    for tag in ("ObsCont", "ObsFisco"):
        for obs in all_of(root, tag):
            line = observation_line(obs.attrib.get("xCampo", ""), text(obs, "xTexto"))
            key = re.sub(r"\s+", " ", line).strip().upper()
            if line and key not in seen:
                seen.add(key)
                lines.append(line)
    return {"principal": principal, "uso_exclusivo": "\n".join(lines).strip()}


__all__ = [
    "ElementIndex",
    "all_of",
    "build_index",
    "child",
    "first",
    "inf_id",
    "local_name",
    "observation_line",
    "observation_parts",
    "parse_root",
    "text",
]
