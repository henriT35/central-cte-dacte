from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from .etree_helpers import (
    ElementIndex,
    all_of,
    build_index,
    child,
    first,
    inf_id,
    observation_parts,
    parse_root,
    text,
)
from ..infrastructure.formatting import (
    date_br,
    format_cep,
    format_chave,
    format_cnpj_cpf,
    only_digits,
    qty,
)

PARSER_VERSION = "2.7.0-rc18-classificacao-fiscal"


def map_tp_cte(value: str) -> str:
    return {"0": "NORMAL", "1": "COMPLEMENTO", "2": "ANULAÇÃO", "3": "SUBSTITUIÇÃO"}.get(str(value or ""), str(value or ""))


def map_tp_serv(value: str) -> str:
    return {"0": "NORMAL", "1": "SUBCONTRATAÇÃO", "2": "REDESPACHO", "3": "REDESPACHO INTERMEDIÁRIO", "4": "SERVIÇO VINCULADO A MULTIMODAL"}.get(str(value or ""), str(value or ""))


def map_tomador(value: str) -> str:
    return {"0": "REMETENTE", "1": "EXPEDIDOR", "2": "RECEBEDOR", "3": "DESTINATÁRIO", "4": "OUTROS"}.get(str(value or ""), str(value or ""))


def map_modal(value: str) -> str:
    return {"01": "RODOVIÁRIO", "02": "AÉREO", "03": "AQUAVIÁRIO", "04": "FERROVIÁRIO", "05": "DUTOVIÁRIO", "06": "MULTIMODAL"}.get(str(value or ""), str(value or ""))


def map_cst(value: str) -> str:
    return {
        "00": "00 - TRIBUTAÇÃO NORMAL ICMS", "20": "20 - COM REDUÇÃO DE BASE DE CÁLCULO",
        "40": "40 - ICMS ISENTO", "41": "41 - ICMS NÃO TRIBUTADO", "51": "51 - ICMS DIFERIDO",
        "60": "60 - ICMS COBRADO ANTERIORMENTE POR SUBSTITUIÇÃO TRIBUTÁRIA", "90": "90 - ICMS OUTROS",
    }.get(value or "", value or "")


def _address_node(person: Optional[ET.Element]) -> Optional[ET.Element]:
    if person is None:
        return None
    for name in ("enderEmit", "enderDest", "enderToma", "enderReme", "enderReceb", "enderExped"):
        node = child(person, name)
        if node is not None:
            return node
    return None


def person_info(person: Optional[ET.Element], issuer: bool = False) -> dict[str, str]:
    address = _address_node(person)
    street = " ".join(value for value in (text(address, "xLgr"), text(address, "nro"), text(address, "xCpl")) if value).strip()
    district = text(address, "xBairro")
    if district:
        street = f"{street} - {district}" if street else district
    result = {
        "nome": text(person, "xNome"),
        "cnpjcpf": format_cnpj_cpf(text(person, "CNPJ") or text(person, "CPF")),
        "ie": text(person, "IE"),
        "ender": street,
        "mun": " - ".join(value for value in (text(address, "xMun"), text(address, "UF")) if value),
        "cep": format_cep(text(address, "CEP")),
        "pais": text(address, "xPais") or text(address, "cPais"),
        "fone": text(address, "fone"),
    }
    if issuer:
        result["fant"] = text(person, "xFant")
    return result


def extract_nfe_number(key: str) -> str:
    digits = only_digits(key)
    return digits[25:34] if len(digits) >= 34 else ""


def extract_nfe_cnpj(key: str) -> str:
    digits = only_digits(key)
    return digits[6:20] if len(digits) == 44 else ""


def extract_nfe_series(key: str) -> str:
    digits = only_digits(key)
    return digits[22:25] if len(digits) >= 25 else ""


def cargo_measures(source: ET.Element | ElementIndex) -> dict[str, str]:
    result = {"peso_bruto": "", "peso_base": "", "peso_aferido": "", "cubagem": "", "volumes": ""}
    for node in all_of(source, "infQ"):
        measure = text(node, "tpMed")
        kind = measure.upper()
        unit = text(node, "cUnid")
        amount = text(node, "qCarga")
        if "CUB" in kind or unit == "00":
            result["cubagem"] = amount
        elif "BASE" in kind:
            result["peso_base"] = amount
        elif "AFER" in kind:
            result["peso_aferido"] = amount
        elif "VOLUME" in kind or "UNID" in kind or unit == "03":
            result["volumes"] = f"{qty(amount, 4)} {measure}".strip()
        elif "BRUTO" in kind or unit == "01":
            result["peso_bruto"] = amount
        elif not result["volumes"]:
            result["volumes"] = f"{qty(amount, 4)} {measure}".strip()
    return result


def protocol_info(source: ET.Element | ElementIndex) -> dict[str, str]:
    node = first(source, "infProt")
    return {"nProt": text(node, "nProt"), "dhRecbto": date_br(text(node, "dhRecbto"))}


def insurance_info(source: ET.Element | ElementIndex) -> dict[str, str]:
    node = first(source, "seg")
    if node is None:
        return {"seguradora": "", "resp": "", "apolice": "", "averbacao": ""}
    code = text(node, "respSeg")
    responsible = {"0": "REMETENTE", "1": "EXPEDIDOR", "2": "RECEBEDOR", "3": "DESTINATÁRIO", "4": "EMITENTE", "5": "TOMADOR"}.get(code, code)
    return {"seguradora": text(node, "xSeg"), "resp": responsible, "apolice": text(node, "nApol"), "averbacao": text(node, "nAver")}


def tax_info(source: ET.Element | ElementIndex) -> dict[str, str]:
    imp = first(source, "imp")
    if imp is None:
        return {"sit": "", "base": "", "aliq": "", "valor": "", "red": "", "st": ""}
    icms = first(ElementIndex(imp), "ICMS")
    detail = list(icms)[0] if icms is not None and list(icms) else None
    cst = text(detail, "CST") or text(detail, "CSOSN")
    return {"sit": map_cst(cst), "base": text(detail, "vBC"), "aliq": text(detail, "pICMS"), "valor": text(detail, "vICMS"), "red": text(detail, "pRedBC"), "st": text(detail, "vICMSST")}


def parse_cte_modular(
    root: ET.Element,
    path: Path,
    index: ElementIndex | None = None,
) -> dict[str, Any]:
    source = index or build_index(root)
    inf, ide, emit = first(source, "infCte"), first(source, "ide"), first(source, "emit")
    rem, dest, exped, receb = first(source, "rem"), first(source, "dest"), first(source, "exped"), first(source, "receb")
    toma3, toma4 = first(source, "toma3"), first(source, "toma4")
    vprest, rodo, cargo = first(source, "vPrest"), first(source, "rodo"), first(source, "infCarga")
    toma_code = text(toma3, "toma")
    toma = toma4
    if toma is None:
        toma = {"0": rem, "1": exped, "2": receb, "3": dest}.get(toma_code)

    components = [{"nome": text(node, "xNome"), "valor": text(node, "vComp")} for node in all_of(source, "Comp")]
    docs: list[dict[str, str]] = []
    for node in all_of(source, "infNFe"):
        key = text(node, "chave")
        if key:
            docs.append({
                "tipo": "NF-e",
                "cnpj": format_cnpj_cpf(extract_nfe_cnpj(key)),
                "serie_numero": f"{extract_nfe_series(key)} / {extract_nfe_number(key)}".strip(" /"),
                "chave": format_chave(key),
                "n_doc": extract_nfe_number(key),
            })
    for node in all_of(source, "infNF"):
        docs.append({
            "tipo": "NF",
            "cnpj": format_cnpj_cpf(text(node, "CNPJ")),
            "serie_numero": text(node, "serie") + " / " + text(node, "nDoc"),
            "chave": "",
            "n_doc": text(node, "nDoc"),
        })
    for node in all_of(source, "infOutros"):
        docs.append({
            "tipo": text(node, "tpDoc") or "Doc.",
            "cnpj": "",
            "serie_numero": text(node, "nDoc"),
            "chave": "",
            "n_doc": text(node, "nDoc"),
        })

    doc_ant_chaves: list[str] = []
    for node in all_of(source, "docAnt"):
        for chave_node in all_of(ElementIndex(node), "chCTe"):
            chave = only_digits(chave_node.text or "")
            if len(chave) == 44 and chave not in doc_ant_chaves:
                doc_ant_chaves.append(chave)

    issuer = person_info(emit, issuer=True)
    recipient = person_info(dest)
    observations = observation_parts(source)
    measures = cargo_measures(source)
    info: dict[str, Any] = {
        "arquivo": path.name,
        "tipo": "CT-e",
        "path": str(path),
        "chave": inf_id(inf),
        "numero": text(ide, "nCT"),
        "serie": text(ide, "serie"),
        "modelo": text(ide, "mod"),
        "data": text(ide, "dhEmi"),
        "data_br": date_br(text(ide, "dhEmi")),
        "natOp": text(ide, "natOp"),
        "modal": map_modal(text(ide, "modal")),
        "tpCTe": map_tp_cte(text(ide, "tpCTe")),
        "tpCTe_codigo": text(ide, "tpCTe"),
        "tpCTe_fonte": "XML ide/tpCTe",
        "tpServ": map_tp_serv(text(ide, "tpServ")),
        "toma_txt": map_tomador(toma_code),
        "cfop": text(ide, "CFOP"),
        "origem": f"{text(ide, 'xMunIni')} - {text(ide, 'UFIni')} - {text(ide, 'cMunIni')}",
        "destino": f"{text(ide, 'xMunFim')} - {text(ide, 'UFFim')} - {text(ide, 'cMunFim')}",
        "forma_pagamento": "PAGO" if text(ide, "forPag") == "0" else "A PAGAR" if text(ide, "forPag") == "1" else text(ide, "forPag"),
        "emit": issuer,
        "rem": person_info(rem),
        "dest": recipient,
        "exped": person_info(exped),
        "receb": person_info(receb),
        "toma": person_info(toma),
        "vTPrest": text(vprest, "vTPrest"),
        "vRec": text(vprest, "vRec"),
        "componentes": components,
        "docs": docs,
        "doc_ant_chaves": doc_ant_chaves,
        "doc_ant_chave": doc_ant_chaves[0] if doc_ant_chaves else "",
        "obs": observations["principal"],
        "obs_principal": observations["principal"],
        "uso_exclusivo": observations["uso_exclusivo"],
        "produto": text(cargo, "proPred"),
        "outras_carac": text(cargo, "xOutCat"),
        "valor_carga": text(cargo, "vCarga"),
        **measures,
        "rntrc": text(rodo, "RNTRC"),
        "prot": protocol_info(source),
        "seguro": insurance_info(source),
        "imposto": tax_info(source),
    }
    info["emitente"], info["destinatario"], info["valor"] = issuer["nome"], recipient["nome"], info["vTPrest"]
    return info


def parse_xml_modular(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    try:
        root = parse_root(path)
    except Exception as exc:
        return {
            "arquivo": path.name,
            "tipo": "XML inválido",
            "path": str(path),
            "numero": "",
            "serie": "",
            "emitente": "",
            "destinatario": "",
            "valor": "",
            "erro": str(exc),
        }
    source = build_index(root)
    if first(source, "infCte") is not None:
        return parse_cte_modular(root, path, source)
    if first(source, "infNFe") is not None:
        ide, emit, dest, total, inf = first(source, "ide"), first(source, "emit"), first(source, "dest"), first(source, "ICMSTot"), first(source, "infNFe")
        return {
            "arquivo": path.name,
            "tipo": "NF-e",
            "path": str(path),
            "numero": text(ide, "nNF"),
            "serie": text(ide, "serie"),
            "emitente": text(emit, "xNome"),
            "destinatario": text(dest, "xNome"),
            "valor": text(total, "vNF"),
            "chave": inf_id(inf),
        }
    return {
        "arquivo": path.name,
        "tipo": "XML",
        "path": str(path),
        "numero": "",
        "serie": "",
        "emitente": "",
        "destinatario": "",
        "valor": "",
        "chave": "",
    }


class ModularXmlParser:
    version = PARSER_VERSION

    def parse(self, path: Path | str) -> dict[str, Any]:
        return parse_xml_modular(path)


__all__ = [
    "ModularXmlParser",
    "PARSER_VERSION",
    "cargo_measures",
    "extract_nfe_cnpj",
    "extract_nfe_number",
    "extract_nfe_series",
    "insurance_info",
    "map_cst",
    "map_modal",
    "map_tomador",
    "map_tp_cte",
    "map_tp_serv",
    "parse_cte_modular",
    "parse_xml_modular",
    "person_info",
    "protocol_info",
    "tax_info",
]
