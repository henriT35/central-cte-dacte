from __future__ import annotations

"""Leitura XLSX, Base Rodovitor e tabelas de parceiros extraídas do núcleo legado.

As funções são mantidas bytecode-equivalentes ao bloco histórico e, durante a
composição, são religadas ao namespace do runtime para preservar dependências
e fallbacks já homologados.
"""

from typing import Any, MutableMapping

from .function_rebinder import install_rebound_functions

def norm_text(value):
    value = str(value or "").replace("\xa0", " ").strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"\s+", " ", value).upper().strip()
    return value


def norm_location(value):
    text = norm_text(value)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_header(value):
    return re.sub(r"[^A-Z0-9]", "", norm_text(value))


def normalize_nf(value):
    digits = only_digits(value)
    if digits:
        return digits.lstrip("0") or "0"
    return norm_text(value)


def parse_number_br(value):
    """Converte números no padrão BR/Excel com mais tolerância.

    Exemplos aceitos:
    - 1234.56 vindo do Excel como número
    - "1.234,56"
    - "1234,56"
    - "1,234.56"
    - "1.234" como milhar brasileiro
    - "0,01"
    """
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).replace("\xa0", " ").strip()
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if not s or s in {"-", ".", ","}:
        return 0.0

    neg = s.startswith("-")
    s = s.replace("-", "")

    if "," in s and "." in s:
        # O separador decimal normalmente é o último que aparece.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        # "1.234" ou "12.345.678" são milhar no padrão BR.
        if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]) and len(parts[0]) <= 3:
            s = "".join(parts)
        # Caso contrário, mantém como decimal no padrão internacional.

    try:
        n = float(s)
        return -n if neg else n
    except Exception:
        return 0.0


def parse_percent(value):
    if value in (None, ""):
        return 0.0
    raw = str(value).strip()
    n = parse_number_br(value)
    if "%" in raw:
        return n / 100.0
    if n > 1:
        return n / 100.0
    return n


def parse_optional_single_money(value):
    """Lê valor monetário simples.

    Se a célula tiver uma lista/faixa como "350/500/600" ou "150 a 300",
    retorna 0 para não transformar vários valores em um número gigante.
    Esses casos ficam para revisão manual/regra detalhada.
    """
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    # Dois ou mais números separados por barra/ponto-e-vírgula indicam tabela manual.
    if re.search(r"\d\s*[\/;]\s*\d", raw):
        return 0.0
    # Faixas textuais também são melhor tratadas como manual por enquanto.
    if re.search(r"\d\s+(A|ATE|ATÉ)\s+\d", norm_text(raw)):
        return 0.0
    return parse_number_br(raw)


def fmt_percent(value):
    if value in (None, ""):
        return ""
    try:
        txt = f"{float(value) * 100:.2f}%".replace(".", ",")
        return txt.replace(",00%", "%")
    except Exception:
        return str(value)


def safe_get(row, idx):
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return row[idx]


def xlsx_col_to_index(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def xlsx_load_shared_strings(z):
    strings = []
    if "xl/sharedStrings.xml" not in z.namelist():
        return strings
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    for si in root.findall(f"{ns}si"):
        parts = []
        for t in si.iter(f"{ns}t"):
            parts.append(t.text or "")
        strings.append("".join(parts))
    return strings


def xlsx_sheet_paths(z):
    ns_main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ns_rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    ns_pkg = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {}
    for rel in rels.findall(f"{ns_pkg}Relationship"):
        rid_to_target[rel.attrib.get("Id", "")] = rel.attrib.get("Target", "")
    result = {}
    for sh in wb.findall(f".//{ns_main}sheets/{ns_main}sheet"):
        name = sh.attrib.get("name", "")
        rid = sh.attrib.get(f"{ns_rel}id", "")
        target = rid_to_target.get(rid, "")
        if not target:
            continue
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = "xl/" + target
        result[name] = path
    return result


def read_xlsx_sheet(file_path, sheet_name=None):
    file_path = Path(file_path)
    with ZipFile(file_path) as z:
        shared = xlsx_load_shared_strings(z)
        sheets = xlsx_sheet_paths(z)
        if not sheets:
            raise ValueError("Nenhuma aba encontrada no XLSX.")
        if sheet_name and sheet_name in sheets:
            sheet_path = sheets[sheet_name]
        elif sheet_name:
            wanted = norm_text(sheet_name)
            matches = [name for name in sheets if norm_text(name) == wanted]
            if not matches:
                abas = ", ".join(sheets.keys())
                raise ValueError(f"Aba '{sheet_name}' não encontrada. Abas disponíveis: {abas}")
            sheet_path = sheets[matches[0]]
        else:
            sheet_path = next(iter(sheets.values()))
        root = ET.fromstring(z.read(sheet_path))
        ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        rows = []
        for row in root.findall(f".//{ns}sheetData/{ns}row"):
            values = []
            for c in row.findall(f"{ns}c"):
                ref = c.attrib.get("r", "A1")
                col_match = re.match(r"[A-Z]+", ref)
                if not col_match:
                    continue
                col = col_match.group(0)
                idx = xlsx_col_to_index(col)
                while len(values) <= idx:
                    values.append("")
                cell_type = c.attrib.get("t")
                val = ""
                if cell_type == "inlineStr":
                    parts = []
                    for t in c.iter(f"{ns}t"):
                        parts.append(t.text or "")
                    val = "".join(parts)
                else:
                    v = c.find(f"{ns}v")
                    if v is not None:
                        val = v.text or ""
                        if cell_type == "s" and val != "":
                            val = shared[int(val)]
                values[idx] = val
            while values and values[-1] == "":
                values.pop()
            rows.append(values)
        return rows


def try_read_xlsx_sheet(file_path, sheet_name):
    try:
        return read_xlsx_sheet(file_path, sheet_name)
    except Exception:
        return []

def resolve_xlsx_sheet_path(z, sheet_name):
    sheets = xlsx_sheet_paths(z)
    if sheet_name in sheets:
        return sheets[sheet_name]
    wanted = norm_text(sheet_name)
    for name, path in sheets.items():
        if norm_text(name) == wanted:
            return path
    abas = ", ".join(sheets.keys())
    raise ValueError(f"Aba '{sheet_name}' não encontrada. Abas disponíveis: {abas}")


def append_rows_to_xlsx_sheet(file_path, sheet_name, new_rows):
    """Acrescenta linhas em uma aba do XLSX preservando as demais abas.

    Usa somente a biblioteca padrão. As células novas são gravadas como inlineStr
    para evitar reescrever sharedStrings e preservar a planilha original.
    """
    file_path = Path(file_path)
    if not new_rows:
        return 0
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    tmp = file_path.with_name(file_path.stem + ".tmp_cadastro" + file_path.suffix)
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    ET.register_namespace('', "http://schemas.openxmlformats.org/spreadsheetml/2006/main")
    ET.register_namespace('r', "http://schemas.openxmlformats.org/officeDocument/2006/relationships")

    with ZipFile(file_path, "r") as zin:
        sheet_path = resolve_xlsx_sheet_path(zin, sheet_name)
        original_sheet_xml = zin.read(sheet_path)
        root = ET.fromstring(original_sheet_xml)
        sheet_data = root.find(f"{ns}sheetData")
        if sheet_data is None:
            sheet_data = ET.SubElement(root, f"{ns}sheetData")

        existing_rows = sheet_data.findall(f"{ns}row")
        max_row = 0
        max_col = 1
        for row_el in existing_rows:
            try:
                max_row = max(max_row, int(row_el.attrib.get("r", "0") or 0))
            except Exception:
                pass
            for c in row_el.findall(f"{ns}c"):
                ref = c.attrib.get("r", "")
                m = re.match(r"([A-Z]+)(\d+)", ref)
                if m:
                    max_col = max(max_col, xlsx_col_to_index(m.group(1)) + 1)

        for row_values in new_rows:
            max_row += 1
            max_col = max(max_col, len(row_values))
            row_el = ET.SubElement(sheet_data, f"{ns}row", {"r": str(max_row)})
            for c_idx, value in enumerate(row_values):
                if value is None:
                    value = ""
                text_value = str(value)
                ref = f"{excel_column_name(c_idx)}{max_row}"
                c_el = ET.SubElement(row_el, f"{ns}c", {"r": ref, "t": "inlineStr"})
                is_el = ET.SubElement(c_el, f"{ns}is")
                t_el = ET.SubElement(is_el, f"{ns}t")
                t_el.text = text_value

        dim = root.find(f"{ns}dimension")
        if dim is not None:
            dim.attrib["ref"] = f"A1:{excel_column_name(max_col - 1)}{max_row}"
        auto_filter = root.find(f"{ns}autoFilter")
        if auto_filter is not None:
            auto_filter.attrib["ref"] = f"A1:{excel_column_name(max_col - 1)}{max_row}"

        new_sheet_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        with ZipFile(tmp, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == sheet_path:
                    data = new_sheet_xml
                zout.writestr(item, data)
    shutil.move(str(tmp), str(file_path))
    return len(new_rows)


def append_dicts_to_xlsx_sheet(file_path, sheet_name, dict_rows):
    rows = read_xlsx_sheet(file_path, sheet_name)
    if not rows:
        raise ValueError(f"Aba {sheet_name} está vazia ou não foi encontrada.")
    headers = [str(h or "").strip() for h in rows[0]]
    out_rows = []
    for data in dict_rows:
        normalized = {normalize_header(k): v for k, v in (data or {}).items()}
        out_rows.append([normalized.get(normalize_header(h), "") for h in headers])
    return append_rows_to_xlsx_sheet(file_path, sheet_name, out_rows)


def make_partner_id_from_name(name, fallback="PARCEIRO"):
    base = norm_text(name or fallback)
    base = re.sub(r"[^A-Z0-9]+", "_", base).strip("_")
    if not base:
        base = fallback
    return base[:34]


def next_region_id(existing_rows):
    max_n = 0
    for row in existing_rows[1:]:
        val = str(safe_get(row, 0) or "")
        m = re.search(r"(\d+)$", val)
        if m:
            try:
                max_n = max(max_n, int(m.group(1)))
            except Exception:
                pass
    return f"REG_{max_n + 1:04d}"


def normalize_percent_text(value):
    t = str(value or "").strip()
    if not t:
        return ""
    if "%" in t:
        return t
    return t.replace(".", ",") + "%"


def cadastro_tabela_salvar_xlsx(file_path, data):
    """Cadastra/atualiza tabela operacional escrevendo somente na planilha XLSX."""
    file_path = Path(file_path)
    if file_path.name.startswith("~$"):
        raise ValueError("Feche a planilha no Excel antes de salvar. O arquivo está temporário/bloqueado.")
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    backup_dir = file_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{file_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_path.suffix}"
    shutil.copy2(file_path, backup_path)

    partner_name = str(data.get("partner_name", "")).strip()
    alias = str(data.get("alias", "")).strip() or partner_name
    cnpj = str(data.get("cnpj", "")).strip()
    partner_id = str(data.get("partner_id", "")).strip() or make_partner_id_from_name(partner_name or alias or cnpj)
    partner_id = make_partner_id_from_name(partner_id, "PARCEIRO")

    parceiros_rows, _ = rows_to_dicts(read_xlsx_sheet(file_path, "PARCEIROS"))
    existing_pid = {str(r.get("PARCEIROID", "")).strip() for r in parceiros_rows}
    existing_cnpjs = set()
    for r in parceiros_rows:
        for k, v in r.items():
            if "CNPJ" in k:
                for c in extract_cnpjs(v):
                    existing_cnpjs.add(c)

    partner_inserted = False
    if partner_id not in existing_pid and (not only_digits(cnpj) or only_digits(cnpj) not in existing_cnpjs):
        append_dicts_to_xlsx_sheet(file_path, "PARCEIROS", [{
            "Parceiro ID": partner_id,
            "Nome Parceiro": partner_name or alias or partner_id,
            "CNPJ": cnpj,
            "Nome no XML / Alias principal": alias or partner_name,
            "Origem base": data.get("origem_cidade", ""),
            "UF base": data.get("origem_uf", ""),
            "Tipo tabela principal": data.get("tipo_tabela", "Cadastro manual pelo programa"),
            "Status": "ATIVO",
            "Fonte PDF": data.get("fonte", "Cadastro manual"),
            "Páginas": "",
            "Observação": data.get("observacao", "Cadastro feito pelo programa"),
        }])
        partner_inserted = True

    regioes_raw = read_xlsx_sheet(file_path, "REGIOES")
    region_id = next_region_id(regioes_raw)
    cidade = str(data.get("cidade", "")).strip()
    uf = str(data.get("uf", "")).strip().upper()
    regiao = str(data.get("regiao", "")).strip() or f"CAD {cidade} {uf}".strip()
    append_dicts_to_xlsx_sheet(file_path, "REGIOES", [{
        "Região ID": region_id,
        "Parceiro ID": partner_id,
        "Região/Base": regiao,
        "Cidade": cidade,
        "UF": uf,
        "Percentual Default": normalize_percent_text(data.get("percentual", "")),
        "Frete Mínimo Default": data.get("frete_minimo", ""),
        "Prazo Default": data.get("prazo", ""),
        "Fonte PDF": data.get("fonte", "Cadastro manual"),
        "Página": "",
        "Status Revisão": data.get("status_revisao", "REVISAR_OK"),
        "Tonelagem Mínima (R$/Ton)": data.get("tonelagem", ""),
        "Modal": data.get("modal", ""),
        "Data Proposta": data.get("data_proposta", datetime.now().strftime("%d/%m/%Y")),
        "Observação Conferência": data.get("observacao", "Cadastro feito pelo programa"),
        "Base Cálculo": data.get("base_calculo", "ORIGINAL"),
    }])

    return {
        "partner_id": partner_id,
        "partner_inserted": partner_inserted,
        "region_id": region_id,
        "backup_path": str(backup_path),
        "file_path": str(file_path),
    }

def rows_to_dicts(rows):
    if not rows:
        return [], {}
    headers = [str(h or "").strip() for h in rows[0]]
    idx = {normalize_header(h): i for i, h in enumerate(headers) if str(h or "").strip()}
    dicts = []
    for row in rows[1:]:
        if not any(str(v or "").strip() for v in row):
            continue
        d = {}
        for h, i in idx.items():
            d[h] = safe_get(row, i)
        dicts.append(d)
    return dicts, idx


def pick_col(idx, *names):
    for name in names:
        key = normalize_header(name)
        if key in idx:
            return idx[key]
    return None


def classify_base_cte(tipo_doc):
    t = norm_text(tipo_doc)
    if "COMPLEMENT" in t or "COMPL" in t:
        return "COMPLEMENTAR"
    if "ANUL" in t:
        return "ANULACAO"
    if "SUBSTIT" in t:
        return "SUBSTITUICAO"
    if "DEVOL" in t:
        return "DEVOLUCAO"
    # REDESPACHO, SUBC FORM CTRC e SUBC FORM LISO podem ser operação normal.
    return "NORMAL"


XML_VALIDATION_PARTNER_POLICIES = {
    # Política isolada para a validação XML da M. B. Serviços.
    # Não altera faturas, DACTE, comprovantes ou regras de outros parceiros.
    "MB_SERVICOS_LOG": {
        "complementar_herda_regra_normal": True,
        "aceitar_complementar_exato_base": True,
        "aceitar_substituto_com_vinculo_forte": True,
        "fallback_regional_interior_ap": True,
    },
}


def xml_validation_partner_policy(partner_id):
    return XML_VALIDATION_PARTNER_POLICIES.get(str(partner_id or "").strip(), {})


def doc_identity_for_nf(info, nf):
    wanted = normalize_nf(nf)
    for doc in info.get("docs", []) or []:
        if normalize_nf(doc.get("n_doc", "")) == wanted:
            return {
                "nf": wanted,
                "cnpj_emitente": only_digits(doc.get("cnpj", "")),
                "chave": only_digits(doc.get("chave", "")),
                "tipo": norm_text(doc.get("tipo", "")),
            }
    return {"nf": wanted, "cnpj_emitente": "", "chave": "", "tipo": ""}


def split_city_uf(value):
    raw = norm_text(value)
    if not raw:
        return "", ""
    parts = [part.strip() for part in re.split(r"\s+-\s+", raw) if part.strip()]
    if len(parts) >= 2 and len(parts[-1]) == 2:
        return norm_location(" ".join(parts[:-1])), parts[-1]
    return norm_location(raw), ""


def cnpj_match_score(xml_value, base_value, score):
    a = only_digits(xml_value)
    b = only_digits(base_value)
    if a and b and a == b:
        return score
    return 0


def city_match_score(xml_city, base_city, score):
    a = norm_location(xml_city)
    b = norm_location(base_city)
    if not a or not b:
        return 0
    if a == b:
        return score
    if a in b or b in a:
        return max(1, score // 2)
    return 0


def base_cache_key(file_path):
    p = Path(file_path)
    try:
        st = p.stat()
        return {
            "name": p.name,
            "size": int(st.st_size),
            "loader": "base-cache-v2-location",
        }
    except Exception:
        return {
            "name": p.name,
            "size": 0,
            "loader": "base-cache-v2-location",
        }


def base_cache_file(file_path):
    p = Path(file_path)
    cache_dir = app_runtime_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", p.stem).strip("_") or "base"
    return cache_dir / f"{safe_name}_cache.json"


def load_rodovitor_base_cached(file_path, force=False):
    """Carrega a base Rodovitor com cache JSON.

    A primeira leitura de XLSX ainda pode ser mais pesada. Depois disso, o programa
    usa cache baseado em nome/tamanho do arquivo, que é muito mais leve para iniciar.
    """
    p = Path(file_path)
    key = base_cache_key(p)
    cache_path = base_cache_file(p)

    if not force and cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("key") == key and isinstance(payload.get("data"), dict):
                data = payload["data"]
                data["path"] = str(p)
                data["_cache"] = {
                    "status": "HIT",
                    "cache_path": str(cache_path),
                    "arquivo": p.name,
                }
                return data
        except Exception as e:
            write_app_log("cache_base.log", f"Cache ignorado para {p}: {e}")

    started = time.perf_counter()
    data = load_rodovitor_base(p)
    elapsed = time.perf_counter() - started
    data["_cache"] = {
        "status": "MISS",
        "cache_path": str(cache_path),
        "arquivo": p.name,
        "seconds": round(elapsed, 2),
    }
    try:
        payload = {"key": key, "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "data": data}
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as e:
        write_app_log("cache_base.log", f"Falha ao salvar cache da base {p}: {e}")
    return data


def load_rodovitor_base(file_path):
    rows = read_xlsx_sheet(file_path)
    if not rows:
        raise ValueError("Planilha base vazia.")
    header = rows[0]
    idx = {normalize_header(h): i for i, h in enumerate(header) if str(h or "").strip()}
    c_nf = pick_col(idx, "Numero da Nota Fiscal", "Número da Nota Fiscal", "Nota Fiscal", "NF")
    c_tipo = pick_col(idx, "Tipo do Documento")
    c_cte = pick_col(idx, "Serie/Numero CT-e", "Série/Número CT-e", "Serie/Numero CTe")
    c_chave = pick_col(idx, "Chave CT-e")
    c_frete = pick_col(idx, "Valor do Frete")
    c_frete_sem = pick_col(idx, "Valor do Frete sem ICMS")
    c_frete_origem = pick_col(idx, "Valor do Frete do CTRC Origem", "Valor do Frete CT-e Origem", "Valor Frete Origem")
    c_cte_origem = pick_col(idx, "CTe Origem", "CT-e Origem")
    c_ctrc_origem = pick_col(idx, "CTRC Origem")
    c_merc = pick_col(idx, "Valor da Mercadoria")
    c_cid_ent = pick_col(idx, "Cidade de Entrega", "Cidade do Destinatario", "Cidade do Destinatário")
    c_uf_ent = pick_col(idx, "UF de Entrega", "UF do Destinatario", "UF do Destinatário")
    c_cid_rem = pick_col(idx, "Cidade origem da prestacao", "Cidade origem da prestação", "Cidade do Remetente")
    c_uf_rem = pick_col(idx, "UF origem da prestacao", "UF origem da prestação", "UF do Remetente")
    c_cnpj_rem = pick_col(idx, "CNPJ Remetente")
    c_cnpj_dest = pick_col(idx, "CNPJ Destinatario", "CNPJ Destinatário")
    c_cnpj_pag = pick_col(idx, "CNPJ Pagador")
    c_cnpj_receb = pick_col(idx, "CNPJ Recebedor")
    if c_nf is None or c_frete is None:
        raise ValueError("A base precisa ter pelo menos 'Numero da Nota Fiscal' e 'Valor do Frete'.")
    index = {}
    base_rows = []
    for row in rows[1:]:
        nf = normalize_nf(safe_get(row, c_nf))
        if not nf:
            continue
        tipo_doc = str(safe_get(row, c_tipo)).strip() if c_tipo is not None else ""
        tipo_base = classify_base_cte(tipo_doc)
        frete_planilha = parse_number_br(safe_get(row, c_frete))
        frete_origem = parse_number_br(safe_get(row, c_frete_origem)) if c_frete_origem is not None else 0.0
        cte_origem = str(safe_get(row, c_cte_origem)).replace("\xa0", "").strip() if c_cte_origem is not None else ""
        ctrc_origem = str(safe_get(row, c_ctrc_origem)).replace("\xa0", "").strip() if c_ctrc_origem is not None else ""
        # Em relatórios de subcontratação, o "Valor do Frete" pode vir como 0,01.
        # Nesses casos, a base real costuma estar em "Valor do Frete do CTRC Origem".
        usar_frete_origem = frete_origem > 0 and (frete_planilha <= 1.0 or "SUBC" in norm_text(tipo_doc) or cte_origem or ctrc_origem)
        valor_base = frete_origem if usar_frete_origem else frete_planilha
        item = {
            "nf": nf,
            "cte": str(safe_get(row, c_cte)).strip() if c_cte is not None else "",
            "chave": str(safe_get(row, c_chave)).replace("\xa0", "").strip() if c_chave is not None else "",
            "tipo_doc": tipo_doc,
            "tipo_base": tipo_base,
            "cte_origem": cte_origem,
            "ctrc_origem": ctrc_origem,
            "valor_frete": valor_base,
            "valor_frete_planilha": frete_planilha,
            "valor_frete_origem": frete_origem,
            "fonte_frete": "ORIGEM" if usar_frete_origem else "PLANILHA",
            "valor_frete_sem_icms": parse_number_br(safe_get(row, c_frete_sem)) if c_frete_sem is not None else 0.0,
            "valor_mercadoria": parse_number_br(safe_get(row, c_merc)) if c_merc is not None else 0.0,
            "destino_cidade": norm_location(safe_get(row, c_cid_ent)) if c_cid_ent is not None else "",
            "destino_uf": norm_text(safe_get(row, c_uf_ent)) if c_uf_ent is not None else "",
            "origem_cidade": norm_location(safe_get(row, c_cid_rem)) if c_cid_rem is not None else "",
            "origem_uf": norm_text(safe_get(row, c_uf_rem)) if c_uf_rem is not None else "",
            "cnpj_remetente": only_digits(safe_get(row, c_cnpj_rem)) if c_cnpj_rem is not None else "",
            "cnpj_destinatario": only_digits(safe_get(row, c_cnpj_dest)) if c_cnpj_dest is not None else "",
            "cnpj_pagador": only_digits(safe_get(row, c_cnpj_pag)) if c_cnpj_pag is not None else "",
            "cnpj_recebedor": only_digits(safe_get(row, c_cnpj_receb)) if c_cnpj_receb is not None else "",
        }
        base_rows.append(item)
        index.setdefault(nf, []).append(item)
    return {"path": str(file_path), "rows": base_rows, "index": index}


def score_base_candidate(candidate, info, nf=None):
    if not info:
        return 0
    score = 0
    rem = info.get("rem", {}) or {}
    dest = info.get("dest", {}) or {}
    toma = info.get("toma", {}) or {}
    receb = info.get("receb", {}) or {}
    rem_city, rem_uf = split_city_uf(rem.get("mun", ""))
    dest_city, dest_uf = split_city_uf(dest.get("mun", ""))

    # A chave NF-e contém o CNPJ do emitente e é o vínculo mais forte para
    # impedir que uma NF repetida de outro emissor seja aceita por engano.
    doc_id = doc_identity_for_nf(info, nf) if nf else {}
    doc_cnpj = only_digits(doc_id.get("cnpj_emitente", ""))
    base_rem_cnpj = only_digits(candidate.get("cnpj_remetente", ""))
    if doc_cnpj and base_rem_cnpj:
        if doc_cnpj == base_rem_cnpj:
            score += 140
        else:
            score -= 140

    score += cnpj_match_score(rem.get("cnpjcpf", ""), candidate.get("cnpj_remetente", ""), 80)
    score += cnpj_match_score(dest.get("cnpjcpf", ""), candidate.get("cnpj_destinatario", ""), 100)
    score += cnpj_match_score(toma.get("cnpjcpf", ""), candidate.get("cnpj_pagador", ""), 55)
    score += cnpj_match_score(receb.get("cnpjcpf", ""), candidate.get("cnpj_recebedor", ""), 45)
    score += city_match_score(dest_city, candidate.get("destino_cidade", ""), 35)
    score += city_match_score(rem_city, candidate.get("origem_cidade", ""), 20)
    if dest_uf and dest_uf == candidate.get("destino_uf", ""):
        score += 10
    if rem_uf and rem_uf == candidate.get("origem_uf", ""):
        score += 6
    if norm_text(candidate.get("tipo_doc", "")) == "NORMAL":
        score += 3
    if (candidate.get("valor_frete_planilha", 0) or candidate.get("valor_frete", 0)) > 1:
        score += 2
    return score


def _select_best_base_candidate(pool, info, nf, *, require_compatibility=False,
                                compatibility_threshold=40, status_ok="BASE OK",
                                status_tie="NF AMBÍGUA"):
    if not pool:
        return None, status_tie
    scored = [(score_base_candidate(r, info, nf), r) for r in pool]
    scored.sort(key=lambda x: (x[0], x[1].get("valor_frete_planilha", 0) or x[1].get("valor_frete", 0)), reverse=True)
    best_score, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else -10**9
    if require_compatibility and best_score < compatibility_threshold:
        return None, "NF INCOMPATÍVEL"
    if len(scored) == 1:
        return best, status_ok
    if best_score > second_score:
        return best, status_ok + " - DESEMPATADA"
    return best, status_tie


def find_base_by_nf(base_data, nf, info=None, *, preferred_type="", actual_value=None,
                    tolerance=1.0, allow_substitute=False, require_compatibility=False):
    nf_norm = normalize_nf(nf)
    candidates = base_data.get("index", {}).get(nf_norm, []) if base_data else []
    if not candidates:
        return None, "NF NÃO ENCONTRADA", []

    doc_ant_keys = {only_digits(value) for value in (info or {}).get("doc_ant_chaves", []) if len(only_digits(value)) == 44}
    if doc_ant_keys:
        exact_doc_ant = [row for row in candidates if only_digits(row.get("chave", "")) in doc_ant_keys]
        if exact_doc_ant:
            normal_exact = [row for row in exact_doc_ant if row.get("tipo_base") == "NORMAL"] or exact_doc_ant
            chosen, status = _select_best_base_candidate(
                normal_exact, info, nf_norm, require_compatibility=False,
                status_ok="BASE DOCANT EXATA", status_tie="DOCANT AMBÍGUA"
            )
            return chosen, status, candidates

    preferred = norm_text(preferred_type)
    if preferred == "COMPLEMENTAR":
        complementares = [r for r in candidates if r.get("tipo_base") == "COMPLEMENTAR"]
        if actual_value is not None:
            exact = []
            for r in complementares:
                base_val = r.get("valor_frete_planilha", 0.0) or r.get("valor_frete", 0.0) or 0.0
                if abs(base_val - actual_value) <= max(float(tolerance or 0), 0.01):
                    exact.append(r)
            if exact:
                chosen, status = _select_best_base_candidate(
                    exact, info, nf_norm, require_compatibility=require_compatibility,
                    status_ok="BASE COMPLEMENTAR EXATA", status_tie="COMPLEMENTAR AMBÍGUO"
                )
                return chosen, status, candidates

    normals = [r for r in candidates if r.get("tipo_base") == "NORMAL"]
    if normals:
        chosen, status = _select_best_base_candidate(
            normals, info, nf_norm, require_compatibility=require_compatibility,
            status_ok="BASE OK", status_tie="NF AMBÍGUA"
        )
        return chosen, status, candidates

    if allow_substitute:
        substitutes = [r for r in candidates if r.get("tipo_base") == "SUBSTITUICAO"]
        if substitutes:
            chosen, status = _select_best_base_candidate(
                substitutes, info, nf_norm, require_compatibility=True,
                compatibility_threshold=80, status_ok="BASE SUBSTITUTA OK",
                status_tie="SUBSTITUTO AMBÍGUO"
            )
            return chosen, status, candidates

    return None, "ORIGINAL NÃO ENCONTRADO", candidates


def load_partner_tables(file_path):
    parceiros_rows, _ = rows_to_dicts(read_xlsx_sheet(file_path, "PARCEIROS"))
    regras_rows, _ = rows_to_dicts(read_xlsx_sheet(file_path, "REGRAS_PERCENTUAL"))
    config_rows, _ = rows_to_dicts(try_read_xlsx_sheet(file_path, "CONFIG_PROGRAMA"))
    regioes_rows, _ = rows_to_dicts(try_read_xlsx_sheet(file_path, "REGIOES"))
    extras_rows, _ = rows_to_dicts(try_read_xlsx_sheet(file_path, "REGRAS_EXTRAS"))
    alias_rows, _ = rows_to_dicts(try_read_xlsx_sheet(file_path, "ALIAS_PARCEIROS"))
    peso_especial_rows, _ = rows_to_dicts(try_read_xlsx_sheet(file_path, "REGRAS_PESO_ESPECIAL"))
    partners = {}
    cnpj_to_id = {}
    aliases = []
    for r in parceiros_rows:
        pid = str(r.get("PARCEIROID", "")).strip()
        if not pid:
            continue
        name = str(r.get("NOMEPARCEIRO", "")).strip()
        alias = str(r.get("NOMENOXMLALIASPRINCIPAL", "")).strip()

        cnpjs = []
        for key in (
            "CNPJ",
            "CNPJ2",
            "CNPJ3",
            "CNPJALTERNATIVO",
            "CNPJALTERNATIVO2",
            "CNPJSECUNDARIO",
            "CNPJSALTERNATIVOS",
            "OUTROSCNPJS",
        ):
            for cnpj in extract_cnpjs(r.get(key, "")):
                if cnpj not in cnpjs:
                    cnpjs.append(cnpj)

        existing = partners.get(pid)
        if existing:
            if name and not existing.get("name"):
                existing["name"] = name
            if alias and not existing.get("alias"):
                existing["alias"] = alias
            for cnpj in cnpjs:
                if cnpj not in existing.setdefault("cnpjs", []):
                    existing["cnpjs"].append(cnpj)
            if existing.get("cnpjs"):
                existing["cnpj"] = existing["cnpjs"][0]
        else:
            partners[pid] = {
                "id": pid,
                "name": name,
                "cnpj": cnpjs[0] if cnpjs else "",
                "cnpjs": cnpjs,
                "alias": alias,
            }

        for cnpj in cnpjs:
            cnpj_to_id[cnpj] = pid
        for n in (name, alias):
            if n:
                aliases.append((norm_text(n), pid))
    # Aba opcional para nomes alternativos do parceiro no XML.
    for r in alias_rows:
        pid = str(r.get("PARCEIROID", "") or r.get("IDPARCEIRO", "")).strip()
        alias_name = str(r.get("NOMENOXML", "") or r.get("NOMEALIAS", "") or r.get("ALIAS", "") or r.get("NOMENOXMLALIASPRINCIPAL", "")).strip()
        if pid and alias_name:
            aliases.append((norm_text(alias_name), pid))

    rules = []
    for r in regras_rows:
        pid = str(r.get("PARCEIROID", "")).strip()
        if not pid:
            continue
        percent = parse_percent(r.get("PERCENTUAL", ""))
        minimum = parse_number_br(r.get("FRETEMINIMO", ""))
        rules.append({
            "partner_id": pid,
            "origem_cidade": norm_location(r.get("ORIGEMCIDADE", "")),
            "origem_uf": norm_text(r.get("ORIGEMUF", "")),
            "destino_cidade": norm_location(r.get("DESTINOCIDADE", "")),
            "destino_uf": norm_text(r.get("DESTINOUF", "")),
            "regiao": norm_text(r.get("REGIAOBASE", "")),
            "percent": percent,
            "minimum": minimum,
            "ton_rate": parse_number_br(
                r.get("TONELAGEMMINIMARTON", "") or
                r.get("TONELAGEMMINIMA", "") or
                r.get("TONELAGEM", "") or
                r.get("RSTON", "") or
                r.get("VALORTON", "")
            ) if pid == "AC_LOG_C_VARGAS" else 0.0,
            "modo_calculo": norm_text(
                r.get("MODOCALCULO", "") or
                r.get("TIPOCALCULO", "") or
                r.get("FORMACALCULO", "") or
                (r.get("TIPOCALCULOCOMPACTO", "") if pid == "AC_LOG_C_VARGAS" else "") or
                (r.get("MODOCALCULOCOMPACTO", "") if pid == "AC_LOG_C_VARGAS" else "")
            ),
            "base_calculo": normalize_base_calculo(r.get("BASECALCULO", "ORIGINAL")),
            "inclui_complementar": norm_text(r.get("INCLUICOMPLEMENTAR", "NAO")),
            "status_revisao": norm_text(r.get("STATUSREVISAO", "")),
            "gris_ativo": norm_text(r.get("GRISATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
            "percentual_gris": parse_percent(r.get("PERCENTUALGRIS", "")),
            "pedagio_ativo": norm_text(r.get("PEDAGIOATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
            "valor_pedagio": parse_number_br(r.get("VALORPEDAGIO", "") or r.get("PEDAGIO", "")),
            "fracao_pedagio_kg": parse_number_br(r.get("FRACAOPEDAGIOKG", "")),
            "tipo_pedagio": norm_text(r.get("TIPOPEDAGIO", "")),
            "raw": r,
            "source": "REGRAS_PERCENTUAL",
        })
    regions = []
    for r in regioes_rows:
        pid = str(r.get("PARCEIROID", "")).strip()
        if not pid:
            continue
        regions.append({
            "partner_id": pid,
            "regiao": norm_text(r.get("REGIAOBASE", "")),
            "cidade": norm_location(r.get("CIDADE", "")),
            "uf": norm_text(r.get("UF", "")),
            "percent": parse_percent(r.get("PERCENTUALDEFAULT", "")),
            "minimum": parse_number_br(r.get("FRETEMINIMODEFAULT", "")),
            "ton_rate": parse_number_br(
                r.get("TONELAGEMMINIMARTON", "") or
                r.get("TONELAGEMMINIMA", "") or
                r.get("TONELAGEM", "") or
                r.get("RSTON", "") or
                r.get("VALORTON", "")
            ),
            "modo_calculo": norm_text(
                r.get("MODOCALCULO", "") or
                r.get("TIPOCALCULO", "") or
                r.get("FORMACALCULO", "") or
                (r.get("TIPOCALCULOCOMPACTO", "") if pid == "AC_LOG_C_VARGAS" else "") or
                (r.get("MODOCALCULOCOMPACTO", "") if pid == "AC_LOG_C_VARGAS" else "")
            ),
            "base_calculo": normalize_base_calculo(r.get("BASECALCULO", "ORIGINAL")),
            "status_revisao": norm_text(r.get("STATUSREVISAO", "")),
            "gris_ativo": norm_text(r.get("GRISATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
            "percentual_gris": parse_percent(r.get("PERCENTUALGRIS", "")),
            "pedagio_ativo": norm_text(r.get("PEDAGIOATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
            "valor_pedagio": parse_number_br(r.get("VALORPEDAGIO", "")),
            "fracao_pedagio_kg": parse_number_br(r.get("FRACAOPEDAGIOKG", "")),
            "tipo_pedagio": norm_text(r.get("TIPOPEDAGIO", "")),
            "raw": r,
        })
    extras = []
    for r in extras_rows:
        pid = str(r.get("PARCEIROID", "") or r.get("IDPARCEIRO", "")).strip()
        if not pid:
            continue
        tipo_extra = norm_text(
            r.get("TIPOEXTRA", "") or
            r.get("TIPO", "") or
            r.get("EVENTO", "") or
            r.get("REGRA", "") or
            r.get("DESCRICAO", "")
        )
        percent = parse_percent(
            r.get("PERCENTUAL", "") or
            r.get("PERCENTUALSOBREFRETE", "") or
            r.get("VALORPERCENTUAL", "")
        )
        valor_fixo = parse_optional_single_money(
            r.get("VALORFIXO", "") or
            r.get("VALOR", "") or
            r.get("TAXA", "")
        )
        minimum = parse_optional_single_money(
            r.get("FRETEMINIMO", "") or
            r.get("VALORMINIMO", "") or
            r.get("MINIMO", "")
        )
        extras.append({
            "partner_id": pid,
            "tipo_extra": tipo_extra,
            "percent": percent,
            "valor_fixo": valor_fixo,
            "minimum": minimum,
            "base_calculo": normalize_base_calculo(r.get("BASECALCULO", "FRETE_ORIGEM")),
            "condicao": str(r.get("CONDICAO", "") or "").strip(),
            "status_revisao": norm_text(r.get("STATUSREVISAO", "")),
            "observacao": str(r.get("OBSERVACAO", "") or r.get("OBS", "") or r.get("DESCRICAO", "")).strip(),
            "raw": r,
            "source": "REGRAS_EXTRAS",
        })

    peso_especial = []
    for r in peso_especial_rows:
        pid = str(r.get("PARCEIROID", "") or r.get("IDPARCEIRO", "")).strip()
        if not pid:
            continue
        peso_min = parse_number_br(
            r.get("PESOMINIMOKG", "") or
            r.get("PESOLIMITEKG", "") or
            r.get("PESOACIMADEKG", "") or
            r.get("LIMITEKG", "")
        )
        percent = parse_percent(
            r.get("PERCENTUAL", "") or
            r.get("PERCENTUALSOBREFRETE", "") or
            r.get("VALORPERCENTUAL", "")
        )
        minimum = parse_number_br(
            r.get("FRETEMINIMO", "") or
            r.get("VALORMINIMO", "") or
            r.get("MINIMO", "")
        )
        peso_especial.append({
            "partner_id": pid,
            "destino_cidade": norm_location(r.get("DESTINOCIDADE", "") or r.get("CIDADE", "")),
            "destino_uf": norm_text(r.get("DESTINOUF", "") or r.get("UF", "")),
            "regiao": norm_text(r.get("REGIAOBASE", "") or r.get("REGIAO", "")),
            "peso_min_kg": peso_min,
            "percent": percent,
            "minimum": minimum,
            "base_calculo": normalize_base_calculo(r.get("BASECALCULO", "ORIGEM")),
            "modo_calculo": norm_text(r.get("MODOCALCULO", "") or r.get("TIPOCALCULO", "") or "PESO_ESPECIAL"),
            "status_revisao": norm_text(r.get("STATUSREVISAO", "")),
            "observacao": str(r.get("OBSERVACAO", "") or r.get("OBS", "") or "").strip(),
            "raw": r,
            "source": "REGRAS_PESO_ESPECIAL",
        })

    tolerance = 1.0
    for r in config_rows:
        key = norm_text(r.get("CHAVE", ""))
        if "TOLER" in key and "PERCENT" not in key:
            tolerance = parse_number_br(r.get("VALOR", "1")) or 1.0
    return {"path": str(file_path), "partners": partners, "cnpj_to_id": cnpj_to_id, "aliases": aliases, "rules": rules, "regions": regions, "extras": extras, "peso_especial": peso_especial, "tolerance": tolerance}


EXPORTED_FUNCTIONS = ('norm_text', 'norm_location', 'normalize_header', 'normalize_nf', 'parse_number_br', 'parse_percent', 'parse_optional_single_money', 'fmt_percent', 'safe_get', 'xlsx_col_to_index', 'xlsx_load_shared_strings', 'xlsx_sheet_paths', 'read_xlsx_sheet', 'try_read_xlsx_sheet', 'resolve_xlsx_sheet_path', 'append_rows_to_xlsx_sheet', 'append_dicts_to_xlsx_sheet', 'make_partner_id_from_name', 'next_region_id', 'normalize_percent_text', 'cadastro_tabela_salvar_xlsx', 'rows_to_dicts', 'pick_col', 'classify_base_cte', 'xml_validation_partner_policy', 'doc_identity_for_nf', 'split_city_uf', 'cnpj_match_score', 'city_match_score', 'base_cache_key', 'base_cache_file', 'load_rodovitor_base_cached', 'load_rodovitor_base', 'score_base_candidate', '_select_best_base_candidate', 'find_base_by_nf', 'load_partner_tables')
EXPORTED_CONSTANTS = ('XML_VALIDATION_PARTNER_POLICIES',)
EXTRACTION_VERSION = "2.7.0-rc17"


def install_base_repository_compat(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
    for name in EXPORTED_CONSTANTS:
        target_globals[name] = globals()[name]
    installed = install_rebound_functions(globals(), target_globals, EXPORTED_FUNCTIONS)
    state = {
        "version": EXTRACTION_VERSION,
        "module": __name__,
        "functions": list(installed),
        "constants": list(EXPORTED_CONSTANTS),
        "active": True,
    }
    target_globals["CENTRAL_CTE_BASE_REPOSITORY_COMPAT_STATE"] = state
    return state


__all__ = ["install_base_repository_compat", "EXPORTED_FUNCTIONS", "EXPORTED_CONSTANTS"]
