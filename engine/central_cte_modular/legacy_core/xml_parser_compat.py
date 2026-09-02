from __future__ import annotations

"""Parser XML/CT-e histórico preservado exclusivamente como fallback de compatibilidade."""

from typing import Any, MutableMapping

from .function_rebinder import install_rebound_functions

def local_name(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag

def first(root, name):
    for elem in root.iter():
        if local_name(elem.tag) == name:
            return elem
    return None

def all_of(root, name):
    return [e for e in root.iter() if local_name(e.tag) == name]

def child(parent, name):
    if parent is None:
        return None
    for c in list(parent):
        if local_name(c.tag) == name:
            return c
    return None

def text(parent, name=None, default=""):
    elem = child(parent, name) if name else parent
    if elem is not None and elem.text:
        return elem.text.strip()
    return default

def only_digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())

def extract_cnpjs(value):
    """Extrai um ou mais CNPJs de uma célula.

    Aceita:
    - 15.186.966/0001-32
    - 15186966000132
    - 15.186.966/0001-32; 00.000.000/0001-00
    """
    text = str(value or "")
    if not text.strip():
        return []
    found = []
    for match in re.findall(r"\d{2}\D?\d{3}\D?\d{3}\D?\d{4}\D?\d{2}", text):
        digits = only_digits(match)
        if len(digits) == 14 and digits not in found:
            found.append(digits)
    if not found:
        digits = only_digits(text)
        if len(digits) == 14:
            found.append(digits)
    return found

def format_cnpj_cpf(value):
    d = only_digits(value)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return value or ""

def format_cep(value):
    d = only_digits(value)
    if len(d) == 8:
        return f"{d[:5]}-{d[5:]}"
    return value or ""

def money(v):
    if v in (None, ""):
        return ""
    try:
        return f"{float(str(v).replace(',', '.')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)

def money_float(v):
    try:
        return float(str(v or "0").replace(",", "."))
    except Exception:
        return 0.0

def qty(v, casas=4):
    if v in (None, ""):
        return ""
    try:
        return f"{float(str(v).replace(',', '.')):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)

def date_br(v):
    if not v:
        return ""
    try:
        return f"{v[8:10]}/{v[5:7]}/{v[0:4]} {v[11:19]}"
    except Exception:
        return v

def format_chave(chave):
    d = only_digits(chave)
    return " ".join(d[i:i+4] for i in range(0, len(d), 4))

def map_tp_cte(value):
    return {"0": "NORMAL", "1": "COMPLEMENTO", "2": "ANULAÇÃO", "3": "SUBSTITUIÇÃO"}.get(str(value or ""), str(value or ""))

def map_tp_serv(value):
    return {
        "0": "NORMAL",
        "1": "SUBCONTRATAÇÃO",
        "2": "REDESPACHO",
        "3": "REDESPACHO INTERMEDIÁRIO",
        "4": "SERVIÇO VINCULADO A MULTIMODAL",
    }.get(str(value or ""), str(value or ""))

def map_tomador(value):
    return {"0": "REMETENTE", "1": "EXPEDIDOR", "2": "RECEBEDOR", "3": "DESTINATÁRIO", "4": "OUTROS"}.get(str(value or ""), str(value or ""))

def map_modal(value):
    return {
        "01": "RODOVIÁRIO", "02": "AÉREO", "03": "AQUAVIÁRIO",
        "04": "FERROVIÁRIO", "05": "DUTOVIÁRIO", "06": "MULTIMODAL",
    }.get(str(value or ""), str(value or ""))

def map_cst(value):
    if not value:
        return ""
    return {
        "00": "00 - TRIBUTAÇÃO NORMAL ICMS",
        "20": "20 - COM REDUÇÃO DE BASE DE CÁLCULO",
        "40": "40 - ICMS ISENTO",
        "41": "41 - ICMS NÃO TRIBUTADO",
        "51": "51 - ICMS DIFERIDO",
        "60": "60 - ICMS COBRADO ANTERIORMENTE POR SUBSTITUIÇÃO TRIBUTÁRIA",
        "90": "90 - ICMS OUTROS",
    }.get(value, value)

def addr_lines(pessoa):
    if pessoa is None:
        return {"ender": "", "mun": "", "cep": "", "pais": "", "fone": ""}

    ender = (
        child(pessoa, "enderEmit") or child(pessoa, "enderDest") or child(pessoa, "enderToma")
        or child(pessoa, "enderReme") or child(pessoa, "enderReceb") or child(pessoa, "enderExped")
    )

    xLgr = text(ender, "xLgr")
    nro = text(ender, "nro")
    xCpl = text(ender, "xCpl")
    xBairro = text(ender, "xBairro")
    xMun = text(ender, "xMun")
    uf = text(ender, "UF")
    cep = format_cep(text(ender, "CEP"))
    pais = text(ender, "xPais") or text(ender, "cPais")
    fone = text(ender, "fone")

    end_line = " ".join(x for x in [xLgr, nro, xCpl] if x).strip()
    if xBairro:
        end_line = f"{end_line} - {xBairro}" if end_line else xBairro

    mun = " - ".join(x for x in [xMun, uf] if x)

    return {"ender": end_line, "mun": mun, "cep": cep, "pais": pais, "fone": fone}

def pessoa_info(pessoa):
    lines = addr_lines(pessoa)
    return {
        "nome": text(pessoa, "xNome"),
        "cnpjcpf": format_cnpj_cpf(text(pessoa, "CNPJ") or text(pessoa, "CPF")),
        "ie": text(pessoa, "IE"),
        "ender": lines["ender"],
        "mun": lines["mun"],
        "cep": lines["cep"],
        "pais": lines["pais"],
        "fone": lines["fone"],
    }

def pessoa_emit_info(emit):
    info = pessoa_info(emit)
    info["fant"] = text(emit, "xFant")
    return info

def get_inf_id(inf):
    if inf is None:
        return ""
    raw = inf.attrib.get("Id", "")
    return raw.replace("CTe", "").replace("NFe", "").replace("MDFe", "")

def extract_nfe_number_from_key(chave):
    d = only_digits(chave)
    if len(d) >= 34:
        return d[25:34]
    return ""

def extract_cnpj_from_nfe_key(chave):
    """Extrai o CNPJ do emitente da chave NF-e (posições 7 a 20)."""
    d = only_digits(chave)
    if len(d) == 44:
        return d[6:20]
    return ""

def extract_series_from_key(chave):
    d = only_digits(chave)
    if len(d) >= 25:
        return d[22:25]
    return ""

def find_medidas(root):
    result = {"peso_bruto": "", "peso_base": "", "peso_aferido": "", "cubagem": "", "volumes": ""}
    for infq in all_of(root, "infQ"):
        tp = (text(infq, "tpMed") or "").upper()
        c_unid = text(infq, "cUnid")
        q = text(infq, "qCarga")
        unidade = text(infq, "tpMed") or ""
        if "CUB" in tp or c_unid == "00":
            result["cubagem"] = q
        elif "BASE" in tp:
            result["peso_base"] = q
        elif "AFER" in tp:
            result["peso_aferido"] = q
        elif "VOLUME" in tp or "UNID" in tp or c_unid == "03":
            result["volumes"] = f"{qty(q, 4)} {unidade}".strip()
        elif "BRUTO" in tp or c_unid == "01":
            result["peso_bruto"] = q
        elif not result["volumes"]:
            result["volumes"] = f"{qty(q, 4)} {unidade}".strip()
    return result

def get_protocol(root):
    inf_prot = first(root, "infProt")
    return {"nProt": text(inf_prot, "nProt"), "dhRecbto": date_br(text(inf_prot, "dhRecbto"))}

def get_seguro(root):
    seg = first(root, "seg")
    if seg is None:
        return {"seguradora": "", "resp": "", "apolice": "", "averbacao": ""}
    resp = text(seg, "respSeg")
    resp_txt = {"0": "REMETENTE", "1": "EXPEDIDOR", "2": "RECEBEDOR", "3": "DESTINATÁRIO", "4": "EMITENTE", "5": "TOMADOR"}.get(resp, resp)
    return {"seguradora": text(seg, "xSeg"), "resp": resp_txt, "apolice": text(seg, "nApol"), "averbacao": text(seg, "nAver")}

def get_imposto(root):
    imp = first(root, "imp")
    if imp is None:
        return {"sit": "", "base": "", "aliq": "", "valor": "", "red": "", "st": ""}

    icms_node = first(imp, "ICMS")
    detalhe = None
    if icms_node is not None and len(list(icms_node)) > 0:
        detalhe = list(icms_node)[0]

    cst = text(detalhe, "CST") or text(detalhe, "CSOSN")
    return {
        "sit": map_cst(cst),
        "base": text(detalhe, "vBC"),
        "aliq": text(detalhe, "pICMS"),
        "valor": text(detalhe, "vICMS"),
        "red": text(detalhe, "pRedBC"),
        "st": text(detalhe, "vICMSST"),
    }

def _cte_obs_line(campo, txt):
    campo = (campo or "").strip()
    txt = (txt or "").strip()
    if not txt:
        return ""
    if campo:
        # Evita duplicar prefixo quando o texto já vem como "RESPSEG: ..." etc.
        if txt.upper().startswith((campo + ":").upper()):
            return txt
        return f"{campo}: {txt}"
    return txt

def get_obs_parts(root):
    """Separa as observações do DACTE sem duplicar informações.

    - OBSERVAÇÕES: usa somente <compl><xObs>, como no DACTE referência.
    - USO EXCLUSIVO DO EMISSOR DO CT-e: usa ObsCont/ObsFisco em linhas próprias.

    Antes o programa juntava xObs + ObsCont + ObsFisco em um único campo e
    imprimia esse mesmo texto em OBSERVAÇÕES e USO EXCLUSIVO, criando repetição.
    """
    compl = first(root, "compl")
    principal = (text(compl, "xObs") or "").strip()

    uso_lines = []
    seen = set()
    for tag in ("ObsCont", "ObsFisco"):
        for obs in all_of(root, tag):
            campo = obs.attrib.get("xCampo", "")
            txt = text(obs, "xTexto")
            line = _cte_obs_line(campo, txt)
            if not line:
                continue
            key = re.sub(r"\s+", " ", line).strip().upper()
            if key in seen:
                continue
            seen.add(key)
            uso_lines.append(line)

    return {
        "principal": principal,
        "uso_exclusivo": "\n".join(uso_lines).strip(),
    }

def get_obs(root):
    # Mantido por compatibilidade: em relatórios/DACTE, o campo OBSERVAÇÕES deve
    # representar o xObs fiscal, sem ObsCont concatenado.
    parts = get_obs_parts(root)
    return parts.get("principal", "")

def parse_cte(root, path):
    inf = first(root, "infCte")
    ide = first(root, "ide")
    emit = first(root, "emit")
    rem = first(root, "rem")
    dest = first(root, "dest")
    exped = first(root, "exped")
    receb = first(root, "receb")
    toma3 = first(root, "toma3")
    toma4 = first(root, "toma4")
    vprest = first(root, "vPrest")
    rodo = first(root, "rodo")
    infCarga = first(root, "infCarga")
    prot = get_protocol(root)
    medidas = find_medidas(root)
    seguro = get_seguro(root)
    imposto = get_imposto(root)
    obs_parts = get_obs_parts(root)

    toma = toma4
    toma_code = text(toma3, "toma")
    if toma is None:
        if toma_code == "0":
            toma = rem
        elif toma_code == "1":
            toma = exped
        elif toma_code == "2":
            toma = receb
        elif toma_code == "3":
            toma = dest

    comps = []
    for comp in all_of(root, "Comp"):
        comps.append({"nome": text(comp, "xNome"), "valor": text(comp, "vComp")})

    docs = []
    for infNFe in all_of(root, "infNFe"):
        chave = text(infNFe, "chave")
        if chave:
            docs.append({
                "tipo": "NF-e",
                "cnpj": format_cnpj_cpf(extract_cnpj_from_nfe_key(chave)),
                "serie_numero": f"{extract_series_from_key(chave)} / {extract_nfe_number_from_key(chave)}".strip(" /"),
                "chave": format_chave(chave),
                "n_doc": extract_nfe_number_from_key(chave),
            })
    for infNF in all_of(root, "infNF"):
        docs.append({
            "tipo": "NF",
            "cnpj": format_cnpj_cpf(text(infNF, "CNPJ")),
            "serie_numero": text(infNF, "serie") + " / " + text(infNF, "nDoc"),
            "chave": "",
            "n_doc": text(infNF, "nDoc"),
        })
    for infOutros in all_of(root, "infOutros"):
        docs.append({
            "tipo": text(infOutros, "tpDoc") or "Doc.",
            "cnpj": "",
            "serie_numero": text(infOutros, "nDoc"),
            "chave": "",
            "n_doc": text(infOutros, "nDoc"),
        })

    doc_ant_chaves = []
    for doc_ant in all_of(root, "docAnt"):
        for chave_node in all_of(doc_ant, "chCTe"):
            chave = only_digits(chave_node.text or "")
            if len(chave) == 44 and chave not in doc_ant_chaves:
                doc_ant_chaves.append(chave)

    emit_info = pessoa_emit_info(emit)
    rem_info = pessoa_info(rem)
    dest_info = pessoa_info(dest)
    exped_info = pessoa_info(exped)
    receb_info = pessoa_info(receb)
    toma_info = pessoa_info(toma)

    info = {
        "arquivo": path.name,
        "tipo": "CT-e",
        "path": str(path),
        "chave": get_inf_id(inf),
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
        "emit": emit_info,
        "rem": rem_info,
        "dest": dest_info,
        "exped": exped_info,
        "receb": receb_info,
        "toma": toma_info,
        "vTPrest": text(vprest, "vTPrest"),
        "vRec": text(vprest, "vRec"),
        "componentes": comps,
        "docs": docs,
        "doc_ant_chaves": doc_ant_chaves,
        "doc_ant_chave": doc_ant_chaves[0] if doc_ant_chaves else "",
        "obs": obs_parts.get("principal", ""),
        "obs_principal": obs_parts.get("principal", ""),
        "uso_exclusivo": obs_parts.get("uso_exclusivo", ""),
        "produto": text(infCarga, "proPred"),
        "outras_carac": text(infCarga, "xOutCat"),
        "valor_carga": text(infCarga, "vCarga"),
        "peso_bruto": medidas["peso_bruto"],
        "peso_base": medidas["peso_base"],
        "peso_aferido": medidas["peso_aferido"],
        "cubagem": medidas["cubagem"],
        "volumes": medidas["volumes"],
        "rntrc": text(rodo, "RNTRC"),
        "prot": prot,
        "seguro": seguro,
        "imposto": imposto,
    }
    info["emitente"] = emit_info["nome"]
    info["destinatario"] = dest_info["nome"]
    info["valor"] = info["vTPrest"]
    return info

def parse_xml(path):
    try:
        root = ET.parse(path).getroot()
    except Exception as e:
        return {"arquivo": path.name, "tipo": "XML inválido", "path": str(path), "numero": "", "serie": "", "emitente": "", "destinatario": "", "valor": "", "erro": str(e)}

    if first(root, "infCte") is not None:
        return parse_cte(root, path)

    if first(root, "infNFe") is not None:
        ide = first(root, "ide")
        emit = first(root, "emit")
        dest = first(root, "dest")
        total = first(root, "ICMSTot")
        inf = first(root, "infNFe")
        return {
            "arquivo": path.name,
            "tipo": "NF-e",
            "path": str(path),
            "numero": text(ide, "nNF"),
            "serie": text(ide, "serie"),
            "emitente": text(emit, "xNome"),
            "destinatario": text(dest, "xNome"),
            "valor": text(total, "vNF"),
            "chave": get_inf_id(inf),
        }

    return {"arquivo": path.name, "tipo": "XML", "path": str(path), "numero": "", "serie": "", "emitente": "", "destinatario": "", "valor": "", "chave": ""}

EXPORTED_FUNCTIONS = ('local_name', 'first', 'all_of', 'child', 'text', 'only_digits', 'extract_cnpjs', 'format_cnpj_cpf', 'format_cep', 'money', 'money_float', 'qty', 'date_br', 'format_chave', 'map_tp_cte', 'map_tp_serv', 'map_tomador', 'map_modal', 'map_cst', 'addr_lines', 'pessoa_info', 'pessoa_emit_info', 'get_inf_id', 'extract_nfe_number_from_key', 'extract_cnpj_from_nfe_key', 'extract_series_from_key', 'find_medidas', 'get_protocol', 'get_seguro', 'get_imposto', '_cte_obs_line', 'get_obs_parts', 'get_obs', 'parse_cte', 'parse_xml')
EXPORTED_CONSTANTS = ()
EXTRACTION_VERSION = "2.7.0-rc18"


def install_xml_parser_compat(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
    for name in EXPORTED_CONSTANTS:
        value = globals()[name]
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, list):
            value = list(value)
        target_globals[name] = value
    installed = install_rebound_functions(globals(), target_globals, EXPORTED_FUNCTIONS)
    state = {
        "version": EXTRACTION_VERSION,
        "module": __name__,
        "functions": list(installed),
        "constants": list(EXPORTED_CONSTANTS),
        "active": True,
    }
    target_globals["CENTRAL_CTE_XML_PARSER_COMPAT_STATE"] = state
    return state


__all__ = ["install_xml_parser_compat", "EXPORTED_FUNCTIONS", "EXPORTED_CONSTANTS"]
