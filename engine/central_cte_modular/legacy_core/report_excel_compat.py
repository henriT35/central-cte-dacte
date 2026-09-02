from __future__ import annotations

"""Geração XLSX e relatórios de auditoria extraídos do núcleo legado.

Os corpos permanecem idênticos ao contrato histórico, mas são instalados no
namespace composto para consumir as decisões e helpers oficiais já carregados.
"""

from typing import Any, MutableMapping

from .function_rebinder import install_rebound_functions

def xml_escape(value):
    return escape(str(value if value is not None else ""), quote=True)


def excel_column_name(index):
    index += 1
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def safe_sheet_name(name, used=None):
    used = used or set()
    cleaned = re.sub(r"[\\/\?\*\[\]:]", "_", str(name or "Sheet")).strip() or "Sheet"
    cleaned = cleaned[:31]
    base = cleaned
    n = 2
    while cleaned in used:
        suffix = f"_{n}"
        cleaned = (base[:31 - len(suffix)] + suffix)[:31]
        n += 1
    used.add(cleaned)
    return cleaned


def xlsx_cell_xml(row_idx, col_idx, value, style=0):
    ref = f"{excel_column_name(col_idx)}{row_idx}"
    style_attr = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)):
        try:
            if isinstance(value, float) and (value != value):
                return f'<c r="{ref}"{style_attr}/>'
            return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
        except Exception:
            pass
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{xml_escape(value)}</t></is></c>'


def xlsx_sheet_xml(rows, widths=None):
    max_cols = max((len(r) for r in rows), default=1)
    max_rows = max(len(rows), 1)
    dim = f"A1:{excel_column_name(max_cols - 1)}{max_rows}"
    cols_xml = ""
    if widths:
        parts = []
        for i in range(max_cols):
            width = widths[i] if i < len(widths) else 14
            parts.append(f'<col min="{i+1}" max="{i+1}" width="{width}" customWidth="1"/>')
        cols_xml = "<cols>" + "".join(parts) + "</cols>"
    row_xml = []
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, value in enumerate(row):
            style = 1 if r_idx == 1 else 0
            if r_idx > 1 and isinstance(value, (int, float)):
                style = 2
            cells.append(xlsx_cell_xml(r_idx, c_idx, value, style))
        row_xml.append(f'<row r="{r_idx}">' + "".join(cells) + '</row>')
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<dimension ref="{dim}"/>
<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
{cols_xml}
<sheetData>{''.join(row_xml)}</sheetData>
<autoFilter ref="{dim}"/>
</worksheet>'''


def write_simple_xlsx(file_path, sheets):
    file_path = Path(file_path)
    used = set()
    normalized_sheets = []
    for sheet_name, rows, widths in sheets:
        normalized_sheets.append((safe_sheet_name(sheet_name, used), rows, widths))

    content_types_overrides = []
    workbook_sheets = []
    workbook_rels = []
    for idx, (sheet_name, _rows, _widths) in enumerate(normalized_sheets, start=1):
        content_types_overrides.append(f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        workbook_sheets.append(f'<sheet name="{xml_escape(sheet_name)}" sheetId="{idx}" r:id="rId{idx}"/>')
        workbook_rels.append(f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>')
    styles_rid = len(normalized_sheets) + 1
    workbook_rels.append(f'<Relationship Id="rId{styles_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')

    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
{''.join(content_types_overrides)}
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''
    workbook_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{''.join(workbook_sheets)}</sheets></workbook>'''
    workbook_rels_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(workbook_rels)}</Relationships>'''
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0B4F9F"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD9E2F3"/></left><right style="thin"><color rgb="FFD9E2F3"/></right><top style="thin"><color rgb="FFD9E2F3"/></top><bottom style="thin"><color rgb="FFD9E2F3"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/><xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    core_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>Central CT-e / DACTE</dc:creator><cp:lastModifiedBy>Central CT-e / DACTE</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified></cp:coreProperties>'''
    app_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Central CT-e / DACTE</Application></Properties>'''
    with ZipFile(file_path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("docProps/core.xml", core_xml)
        z.writestr("docProps/app.xml", app_xml)
        z.writestr("xl/workbook.xml", workbook_xml)
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        z.writestr("xl/styles.xml", styles_xml)
        for idx, (_sheet_name, rows, widths) in enumerate(normalized_sheets, start=1):
            z.writestr(f"xl/worksheets/sheet{idx}.xml", xlsx_sheet_xml(rows, widths))


def audit_issue(rows, severity, sheet, partner_id, partner_name, field, problem, suggestion="", key=""):
    rows.append([severity, sheet, partner_id or "", partner_name or "", field or "", problem or "", suggestion or "", key or ""])


def partner_name_for_audit(tables, pid):
    p = (tables.get("partners", {}) or {}).get(pid, {}) if tables else {}
    return p.get("name", "") or p.get("alias", "") or pid or ""


def audit_partner_tables(tables):
    """Audita a planilha operacional de parceiros já carregada no programa.

    Retorna linhas no formato:
    Severidade, Aba, Parceiro ID, Parceiro, Campo, Problema, Sugestão, Linha/Chave
    """
    issues = []
    if not tables:
        audit_issue(issues, "CRÍTICO", "GERAL", "", "", "Arquivo", "Tabelas de parceiros não carregadas.", "Carregue cadastro_tabelas_parceiros.xlsx antes de auditar.")
        return issues

    partners = tables.get("partners", {}) or {}
    rules = tables.get("rules", []) or []
    regions = tables.get("regions", []) or []
    extras = tables.get("extras", []) or []
    aliases = tables.get("aliases", []) or []
    cnpj_to_id = tables.get("cnpj_to_id", {}) or {}

    if not partners:
        audit_issue(issues, "CRÍTICO", "PARCEIROS", "", "", "PARCEIROID", "Nenhum parceiro válido foi carregado.", "Confira se a aba PARCEIROS existe e se a coluna PARCEIROID está preenchida.")

    # PARCEIROS
    cnpj_seen = {}
    for pid, p in partners.items():
        name = p.get("name", "")
        cnpjs = p.get("cnpjs") or ([p.get("cnpj")] if p.get("cnpj") else [])
        cnpjs = [only_digits(c) for c in cnpjs if only_digits(c)]
        alias = p.get("alias", "")
        if not name:
            audit_issue(issues, "ALTO", "PARCEIROS", pid, name, "NOMEPARCEIRO", "Parceiro sem nome cadastrado.", "Preencha NOMEPARCEIRO.")
        if not cnpjs:
            audit_issue(issues, "MÉDIO", "PARCEIROS", pid, name, "CNPJ", "Parceiro sem CNPJ.", "Preencha o CNPJ para identificar melhor o emitente do XML.")
        for cnpj in cnpjs:
            if len(cnpj) != 14:
                audit_issue(issues, "ALTO", "PARCEIROS", pid, name, "CNPJ", f"CNPJ com {len(cnpj)} dígito(s).", "Confira o CNPJ. O esperado é 14 dígitos.", cnpj)
            if cnpj in cnpj_seen and cnpj_seen[cnpj] != pid:
                audit_issue(issues, "ALTO", "PARCEIROS", pid, name, "CNPJ", "CNPJ duplicado em mais de um parceiro.", f"Também aparece no parceiro {cnpj_seen[cnpj]}.", cnpj)
            cnpj_seen[cnpj] = pid
        if len(cnpjs) > 1:
            audit_issue(issues, "BAIXO", "PARCEIROS", pid, name, "CNPJ", f"Parceiro com {len(cnpjs)} CNPJs cadastrados.", "Ok se for a mesma transportadora com filiais/empresas do mesmo contrato.", "; ".join(cnpjs))
        if not alias:
            audit_issue(issues, "BAIXO", "PARCEIROS", pid, name, "NOMENOXMLALIASPRINCIPAL", "Parceiro sem alias principal do XML.", "Preencha com o nome que costuma aparecer no XML para melhorar a identificação.")
        has_rule = any(r.get("partner_id") == pid for r in rules)
        has_extra = any(e.get("partner_id") == pid for e in extras)
        if not has_rule and not has_extra:
            audit_issue(issues, "ALTO", "PARCEIROS", pid, name, "REGRAS", "Parceiro sem regra percentual e sem regra extra.", "Cadastre ao menos uma regra em REGRAS_PERCENTUAL ou REGRAS_EXTRAS.")

    # Alias duplicado para parceiro diferente
    alias_map = {}
    for alias, pid in aliases:
        if not alias:
            continue
        if alias in alias_map and alias_map[alias] != pid:
            audit_issue(issues, "MÉDIO", "ALIAS_PARCEIROS", pid, partner_name_for_audit(tables, pid), "ALIAS", "Mesmo alias aponta para parceiros diferentes.", f"Também aponta para {alias_map[alias]}.", alias)
        alias_map[alias] = pid

    # REGRAS_PERCENTUAL
    rule_keys = {}
    for i, r in enumerate(rules, start=2):
        pid = r.get("partner_id", "")
        pname = partner_name_for_audit(tables, pid)
        percent = r.get("percent") or 0
        minimum = r.get("minimum") or 0
        dest_city = r.get("destino_cidade", "")
        dest_uf = r.get("destino_uf", "")
        orig_city = r.get("origem_cidade", "")
        orig_uf = r.get("origem_uf", "")
        regiao = r.get("regiao", "")
        key = f"Linha aproximada {i}"
        if pid not in partners:
            audit_issue(issues, "CRÍTICO", "REGRAS_PERCENTUAL", pid, pname, "PARCEIROID", "Regra aponta para parceiro inexistente.", "Cadastre o parceiro na aba PARCEIROS ou corrija o PARCEIROID.", key)
        if percent <= 0 and minimum <= 0:
            audit_issue(issues, "CRÍTICO", "REGRAS_PERCENTUAL", pid, pname, "PERCENTUAL/FRETEMINIMO", "Regra sem percentual e sem frete mínimo.", "Preencha percentual, frete mínimo ou remova a regra.", key)
        if percent < 0 or percent > 1:
            audit_issue(issues, "ALTO", "REGRAS_PERCENTUAL", pid, pname, "PERCENTUAL", f"Percentual fora do esperado: {percent}.", "Use 25%, 0,25 ou 25 para 25%. Evite percentuais acima de 100%.", key)
        if minimum < 0:
            audit_issue(issues, "ALTO", "REGRAS_PERCENTUAL", pid, pname, "FRETEMINIMO", "Frete mínimo negativo.", "Corrija o valor do frete mínimo.", key)
        if not any([dest_city, dest_uf, regiao]):
            audit_issue(issues, "ALTO", "REGRAS_PERCENTUAL", pid, pname, "DESTINO/REGIAO", "Regra muito ampla, sem destino, UF ou região.", "Informe cidade/UF de destino ou REGIAOBASE para evitar aplicação indevida.", key)
        if dest_city and not dest_uf and not regiao:
            audit_issue(issues, "BAIXO", "REGRAS_PERCENTUAL", pid, pname, "DESTINOUF", "Regra com cidade de destino sem UF.", "Preencha DESTINOUF para evitar homônimos de cidade.", key)
        if orig_city and not orig_uf:
            audit_issue(issues, "BAIXO", "REGRAS_PERCENTUAL", pid, pname, "ORIGEMUF", "Regra com cidade de origem sem UF.", "Preencha ORIGEMUF.")
        status_rev = r.get("status_revisao", "")
        if any(x in status_rev for x in ["PENDENTE", "REVISAR", "DUVIDA", "DÚVIDA"]):
            audit_issue(issues, "MÉDIO", "REGRAS_PERCENTUAL", pid, pname, "STATUSREVISAO", f"Regra marcada como {status_rev}.", "Revise os dados antes de confiar no cálculo.", key)
        dup_key = (pid, orig_city, orig_uf, dest_city, dest_uf, regiao)
        if dup_key in rule_keys:
            audit_issue(issues, "MÉDIO", "REGRAS_PERCENTUAL", pid, pname, "DUPLICIDADE", "Possível regra duplicada para o mesmo parceiro/rota/região.", f"Também encontrada na {rule_keys[dup_key]}.", key)
        else:
            rule_keys[dup_key] = key

    # REGIOES
    region_keys = {}
    region_rule_names = {(r.get("partner_id"), r.get("regiao")) for r in rules if r.get("regiao")}
    for i, reg in enumerate(regions, start=2):
        pid = reg.get("partner_id", "")
        pname = partner_name_for_audit(tables, pid)
        cidade = reg.get("cidade", "")
        uf = reg.get("uf", "")
        regiao = reg.get("regiao", "")
        percent = reg.get("percent") or 0
        minimum = reg.get("minimum") or 0
        key = f"Linha aproximada {i}"
        if pid not in partners:
            audit_issue(issues, "CRÍTICO", "REGIOES", pid, pname, "PARCEIROID", "Região aponta para parceiro inexistente.", "Cadastre o parceiro ou corrija PARCEIROID.", key)
        if not regiao:
            audit_issue(issues, "ALTO", "REGIOES", pid, pname, "REGIAOBASE", "Cidade/região sem nome de região.", "Preencha REGIAOBASE.", key)
        if not cidade:
            audit_issue(issues, "ALTO", "REGIOES", pid, pname, "CIDADE", "Registro de região sem cidade.", "Preencha CIDADE.", key)
        if cidade and not uf:
            audit_issue(issues, "BAIXO", "REGIOES", pid, pname, "UF", "Cidade na região sem UF.", "Preencha UF para evitar confusão entre cidades.", key)
        if regiao and (pid, regiao) not in region_rule_names and percent <= 0 and minimum <= 0:
            audit_issue(issues, "ALTO", "REGIOES", pid, pname, "REGIAOBASE", "Região sem regra percentual correspondente e sem percentual/mínimo padrão.", "Crie uma regra em REGRAS_PERCENTUAL com a mesma REGIAOBASE ou preencha percentual/mínimo default.", key)
        dup_key = (pid, cidade, uf)
        if dup_key in region_keys:
            audit_issue(issues, "MÉDIO", "REGIOES", pid, pname, "DUPLICIDADE", "Mesma cidade/UF aparece mais de uma vez para o parceiro.", f"Também encontrada na {region_keys[dup_key]}.", key)
        else:
            region_keys[dup_key] = key

    # REGRAS_EXTRAS
    extra_keys = {}
    for i, extra in enumerate(extras, start=2):
        pid = extra.get("partner_id", "")
        pname = partner_name_for_audit(tables, pid)
        tipo = extra.get("tipo_extra", "")
        percent = extra.get("percent") or 0
        fixed = extra.get("valor_fixo")
        minimum = extra.get("minimum")
        key = f"Linha aproximada {i}"
        fixed_val = fixed if fixed is not None else 0
        min_val = minimum if minimum is not None else 0
        if pid not in partners:
            audit_issue(issues, "CRÍTICO", "REGRAS_EXTRAS", pid, pname, "PARCEIROID", "Regra extra aponta para parceiro inexistente.", "Cadastre o parceiro ou corrija PARCEIROID.", key)
        if not tipo:
            audit_issue(issues, "ALTO", "REGRAS_EXTRAS", pid, pname, "TIPOEXTRA", "Regra extra sem tipo.", "Informe REENTREGA, DEVOLUCAO, COMPLEMENTAR, PEDAGIO, TDE etc.", key)
        if percent <= 0 and fixed_val <= 0 and min_val <= 0:
            audit_issue(issues, "ALTO", "REGRAS_EXTRAS", pid, pname, "VALOR", "Regra extra sem percentual, valor fixo ou mínimo.", "Preencha alguma forma de cálculo para a cobrança extra.", key)
        if percent < 0 or percent > 1:
            audit_issue(issues, "ALTO", "REGRAS_EXTRAS", pid, pname, "PERCENTUAL", f"Percentual extra fora do esperado: {percent}.", "Use 50%, 0,5 ou 50 para 50%.", key)
        status_rev = extra.get("status_revisao", "")
        if any(x in status_rev for x in ["PENDENTE", "REVISAR", "DUVIDA", "DÚVIDA"]):
            audit_issue(issues, "MÉDIO", "REGRAS_EXTRAS", pid, pname, "STATUSREVISAO", f"Extra marcado como {status_rev}.", "Revise antes de aprovar cobranças especiais.", key)
        dup_key = (pid, tipo)
        if dup_key in extra_keys:
            audit_issue(issues, "BAIXO", "REGRAS_EXTRAS", pid, pname, "DUPLICIDADE", "Mesmo tipo de extra aparece mais de uma vez para o parceiro.", f"Também encontrado na {extra_keys[dup_key]}.", key)
        else:
            extra_keys[dup_key] = key

    if not issues:
        audit_issue(issues, "OK", "GERAL", "", "", "AUDITORIA", "Nenhum problema encontrado nas regras carregadas.", "Ainda assim, confira os valores com as tabelas originais antes do uso final.")
    return issues


def build_partner_audit_sheets(tables):
    headers = ["Severidade", "Aba", "Parceiro ID", "Parceiro", "Campo", "Problema", "Sugestão", "Linha/Chave"]
    widths = [14, 22, 16, 34, 22, 58, 58, 22]
    issues = audit_partner_tables(tables)
    issue_rows = [headers] + issues

    counts = {}
    for row in issues:
        counts[row[0]] = counts.get(row[0], 0) + 1
    sev_order = ["CRÍTICO", "ALTO", "MÉDIO", "BAIXO", "OK"]
    resumo = [["Item", "Quantidade"]]
    for sev in sev_order:
        if sev in counts:
            resumo.append([sev, counts[sev]])
    resumo += [
        ["Parceiros carregados", len((tables or {}).get("partners", {}) or {})],
        ["Regras percentuais", len((tables or {}).get("rules", []) or [])],
        ["Regiões", len((tables or {}).get("regions", []) or [])],
        ["Regras extras", len((tables or {}).get("extras", []) or [])],
        ["Tolerância", (tables or {}).get("tolerance", "")],
    ]
    return [("RESUMO", resumo, [28, 16]), ("PROBLEMAS", issue_rows, widths)]


def write_partner_audit_xlsx(file_path, tables):
    write_simple_xlsx(file_path, build_partner_audit_sheets(tables))


def partner_audit_text(tables):
    issues = audit_partner_tables(tables)
    counts = {}
    for row in issues:
        counts[row[0]] = counts.get(row[0], 0) + 1
    lines = []
    lines.append(f"{APP_TITLE} - {APP_VERSION}")
    lines.append("AUDITORIA DAS TABELAS DOS PARCEIROS")
    lines.append("=" * 72)
    lines.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append(f"Arquivo: {(tables or {}).get('path', 'não carregado')}")
    lines.append("")
    lines.append("RESUMO")
    lines.append("-" * 72)
    for sev in ["CRÍTICO", "ALTO", "MÉDIO", "BAIXO", "OK"]:
        if sev in counts:
            lines.append(f"{sev}: {counts[sev]}")
    lines.append("")
    lines.append("PRINCIPAIS APONTAMENTOS")
    lines.append("-" * 72)
    for row in issues[:30]:
        lines.append(f"[{row[0]}] {row[1]} • Parceiro {row[2] or '-'} • {row[4]}: {row[5]}")
        if row[6]:
            lines.append(f"  Sugestão: {row[6]}")
    if len(issues) > 30:
        lines.append(f"... mais {len(issues) - 30} apontamento(s) no relatório Excel.")
    return "\n".join(lines)


def base_audit_issue(rows, severity, group, nf, cte, tipo_base, field, problem, suggestion="", value=""):
    rows.append([severity, group, nf or "", cte or "", tipo_base or "", field or "", problem or "", suggestion or "", value or ""])


def audit_rodovitor_base(base_data):
    """Audita a base Rodovitor carregada.

    Retorna linhas no formato:
    Severidade, Grupo, NF, CT-e, Tipo Base, Campo, Problema, Sugestão, Valor/Chave
    """
    issues = []
    if not base_data:
        base_audit_issue(issues, "CRÍTICO", "GERAL", "", "", "", "Arquivo", "Base Rodovitor não carregada.", "Carregue a base antes de auditar.")
        return issues

    rows = base_data.get("rows", []) or []
    index = base_data.get("index", {}) or {}

    if not rows:
        base_audit_issue(issues, "CRÍTICO", "GERAL", "", "", "", "Linhas", "Nenhuma linha válida foi carregada da base.", "Confira se a planilha tem NF e Valor do Frete preenchidos.")
        return issues

    chave_seen = {}
    cte_seen = {}
    for i, row in enumerate(rows, start=2):
        nf = row.get("nf", "")
        cte = row.get("cte", "")
        tipo = row.get("tipo_base", "")
        key = f"Linha aproximada {i}"
        valor = row.get("valor_frete", 0) or 0
        valor_planilha = row.get("valor_frete_planilha", 0) or 0
        valor_origem = row.get("valor_frete_origem", 0) or 0
        fonte = row.get("fonte_frete", "")

        if not cte:
            base_audit_issue(issues, "MÉDIO", "IDENTIFICAÇÃO", nf, cte, tipo, "Serie/Numero CT-e", "Linha sem número de CT-e.", "Confira a coluna Serie/Numero CT-e.", key)

        chave = only_digits(row.get("chave", ""))
        if chave:
            if len(chave) != 44:
                base_audit_issue(issues, "BAIXO", "IDENTIFICAÇÃO", nf, cte, tipo, "Chave CT-e", f"Chave com {len(chave)} dígito(s).", "Uma chave CT-e normalmente tem 44 dígitos.", chave)
            if chave in chave_seen:
                base_audit_issue(issues, "MÉDIO", "DUPLICIDADE", nf, cte, tipo, "Chave CT-e", "Chave CT-e repetida na base.", f"Também aparece na {chave_seen[chave]}.", chave)
            else:
                chave_seen[chave] = key
        else:
            base_audit_issue(issues, "BAIXO", "IDENTIFICAÇÃO", nf, cte, tipo, "Chave CT-e", "Linha sem chave CT-e.", "Não impede a validação por NF, mas dificulta rastreio.", key)

        if cte:
            cte_key = (cte, tipo)
            if cte_key in cte_seen:
                base_audit_issue(issues, "MÉDIO", "DUPLICIDADE", nf, cte, tipo, "CT-e", "Mesmo número de CT-e/tipo aparece mais de uma vez.", f"Também aparece na {cte_seen[cte_key]}.", key)
            else:
                cte_seen[cte_key] = key

        if valor <= 0:
            base_audit_issue(issues, "CRÍTICO", "VALOR", nf, cte, tipo, "Valor do Frete", "Valor base de frete zerado ou negativo.", "Essa NF não terá cálculo confiável. Confira Valor do Frete e Valor do Frete do CTRC Origem.", f"Frete usado: {valor}")
        elif valor <= 1 and valor_origem <= 0:
            base_audit_issue(issues, "ALTO", "VALOR", nf, cte, tipo, "Valor do Frete", "Valor de frete muito baixo e sem frete de origem.", "Pode ser subcontratação/CTRC origem não preenchido. Confira a base.", f"Frete planilha: {valor_planilha}")
        if valor_planilha <= 1 and valor_origem > 0 and fonte == "ORIGEM":
            base_audit_issue(issues, "BAIXO", "VALOR", nf, cte, tipo, "Valor do Frete do CTRC Origem", "Programa usou frete de origem no lugar do frete da planilha.", "Isso é esperado em casos de subcontratação, mas vale conferir amostras.", f"Origem: {valor_origem}")

        if row.get("valor_mercadoria", 0) < 0:
            base_audit_issue(issues, "MÉDIO", "VALOR", nf, cte, tipo, "Valor da Mercadoria", "Valor da mercadoria negativo.", "Confira a linha na base.", key)
        if valor > 100000:
            base_audit_issue(issues, "MÉDIO", "VALOR", nf, cte, tipo, "Valor do Frete", "Frete muito alto para a média esperada.", "Confira se o valor foi importado corretamente.", f"Frete: {valor}")

        if not row.get("destino_cidade"):
            base_audit_issue(issues, "ALTO", "ROTA", nf, cte, tipo, "Cidade destino", "Destino sem cidade.", "A regra do parceiro depende da cidade/região de destino.", key)
        if not row.get("destino_uf"):
            base_audit_issue(issues, "ALTO", "ROTA", nf, cte, tipo, "UF destino", "Destino sem UF.", "Preencha UF para evitar regra errada.", key)
        if not row.get("origem_cidade"):
            base_audit_issue(issues, "BAIXO", "ROTA", nf, cte, tipo, "Cidade origem", "Origem sem cidade.", "Algumas regras usam origem. Confira a coluna da base.", key)
        if not row.get("origem_uf"):
            base_audit_issue(issues, "BAIXO", "ROTA", nf, cte, tipo, "UF origem", "Origem sem UF.", "Algumas regras usam UF de origem. Confira a coluna da base.", key)

        if not row.get("cnpj_destinatario"):
            base_audit_issue(issues, "MÉDIO", "CNPJ", nf, cte, tipo, "CNPJ Destinatário", "Linha sem CNPJ do destinatário.", "Dificulta desempatar NF repetida.", key)
        if not row.get("cnpj_remetente"):
            base_audit_issue(issues, "BAIXO", "CNPJ", nf, cte, tipo, "CNPJ Remetente", "Linha sem CNPJ do remetente.", "Pode dificultar desempate em NF repetida.", key)
        for field in ["cnpj_destinatario", "cnpj_remetente", "cnpj_pagador", "cnpj_recebedor"]:
            cnpj = row.get(field, "")
            if cnpj and len(cnpj) != 14:
                base_audit_issue(issues, "BAIXO", "CNPJ", nf, cte, tipo, field, f"CNPJ com {len(cnpj)} dígito(s).", "Confira se a base trouxe o CNPJ completo.", cnpj)

    # Problemas por NF agrupada.
    for nf, group_rows in index.items():
        normals = [r for r in group_rows if r.get("tipo_base") == "NORMAL"]
        complements = [r for r in group_rows if r.get("tipo_base") == "COMPLEMENTAR"]
        if len(group_rows) > 1:
            ctes = ", ".join(str(r.get("cte", "")) for r in group_rows[:5])
            base_audit_issue(issues, "BAIXO", "DUPLICIDADE", nf, "", "", "NF", f"NF aparece {len(group_rows)} vez(es) na base.", "Pode ser normal por haver complemento/substituição, mas exige desempate quando houver mais de um normal.", ctes)
        if len(normals) > 1:
            ctes = ", ".join(str(r.get("cte", "")) for r in normals[:8])
            base_audit_issue(issues, "ALTO", "DUPLICIDADE", nf, "", "NORMAL", "NF", "NF possui mais de um CT-e NORMAL.", "O programa tenta desempatar por CNPJ/cidade, mas essa NF merece conferência.", ctes)
        if complements and not normals:
            ctes = ", ".join(str(r.get("cte", "")) for r in complements[:8])
            base_audit_issue(issues, "ALTO", "COMPLEMENTAR", nf, "", "COMPLEMENTAR", "NF", "NF possui complementar, mas não possui CT-e normal/original carregado.", "Validação pode cair como ORIGINAL NÃO ENCONTRADO.", ctes)

    if not issues:
        base_audit_issue(issues, "OK", "GERAL", "", "", "", "AUDITORIA", "Nenhum problema encontrado na base carregada.", "Ainda assim, confira amostras antes do uso final.")
    return issues


def build_base_audit_sheets(base_data):
    headers = ["Severidade", "Grupo", "NF", "CT-e", "Tipo Base", "Campo", "Problema", "Sugestão", "Valor/Chave"]
    widths = [14, 18, 16, 16, 16, 24, 58, 62, 30]
    issues = audit_rodovitor_base(base_data)
    issue_rows = [headers] + issues
    counts = {}
    groups = {}
    for row in issues:
        counts[row[0]] = counts.get(row[0], 0) + 1
        groups[row[1]] = groups.get(row[1], 0) + 1

    rows = (base_data or {}).get("rows", []) or []
    index = (base_data or {}).get("index", {}) or {}
    resumo = [["Item", "Quantidade"]]
    for sev in ["CRÍTICO", "ALTO", "MÉDIO", "BAIXO", "OK"]:
        if sev in counts:
            resumo.append([sev, counts[sev]])
    resumo += [
        ["Linhas carregadas", len(rows)],
        ["NFs únicas", len(index)],
        ["CT-e NORMAL", sum(1 for r in rows if r.get("tipo_base") == "NORMAL")],
        ["CT-e COMPLEMENTAR", sum(1 for r in rows if r.get("tipo_base") == "COMPLEMENTAR")],
        ["Frete vindo do CTRC origem", sum(1 for r in rows if r.get("fonte_frete") == "ORIGEM")],
        ["Arquivo", (base_data or {}).get("path", "")],
    ]
    grupo_rows = [["Grupo", "Quantidade"]] + [[k, v] for k, v in sorted(groups.items(), key=lambda x: (-x[1], x[0]))]
    return [("RESUMO", resumo, [30, 22]), ("POR_GRUPO", grupo_rows, [24, 16]), ("PROBLEMAS", issue_rows, widths)]


def write_base_audit_xlsx(file_path, base_data):
    write_simple_xlsx(file_path, build_base_audit_sheets(base_data))


def base_audit_text(base_data):
    issues = audit_rodovitor_base(base_data)
    counts = {}
    for row in issues:
        counts[row[0]] = counts.get(row[0], 0) + 1
    rows = (base_data or {}).get("rows", []) or []
    index = (base_data or {}).get("index", {}) or {}
    lines = []
    lines.append(f"{APP_TITLE} - {APP_VERSION}")
    lines.append("AUDITORIA DA BASE RODOVITOR")
    lines.append("=" * 72)
    lines.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    lines.append(f"Arquivo: {(base_data or {}).get('path', 'não carregado')}")
    lines.append(f"Linhas carregadas: {len(rows)}")
    lines.append(f"NFs únicas: {len(index)}")
    lines.append("")
    lines.append("RESUMO")
    lines.append("-" * 72)
    for sev in ["CRÍTICO", "ALTO", "MÉDIO", "BAIXO", "OK"]:
        if sev in counts:
            lines.append(f"{sev}: {counts[sev]}")
    lines.append("")
    lines.append("PRINCIPAIS APONTAMENTOS")
    lines.append("-" * 72)
    for row in issues[:35]:
        lines.append(f"[{row[0]}] {row[1]} • NF {row[2] or '-'} • CT-e {row[3] or '-'} • {row[5]}: {row[6]}")
        if row[7]:
            lines.append(f"  Sugestão: {row[7]}")
    if len(issues) > 35:
        lines.append(f"... mais {len(issues) - 35} apontamento(s) no relatório Excel.")
    return "\n".join(lines)


def validation_export_row(info):
    result = info.get("validacao") or {}
    emit = info.get("emit", {}) or {}
    dest = info.get("dest", {}) or {}
    status = result.get("status") or "NÃO VALIDADO"
    trace = " | ".join(result.get("trace") or [])
    return [
        status,
        info.get("numero", ""),
        info.get("serie", ""),
        info.get("emitente", ""),
        emit.get("cnpjcpf", ""),
        result.get("nf", "") or get_nf_from_info(info),
        "SIM" if result.get("validacao_parcial") else "",
        ", ".join(list(result.get("nfs_nao_encontradas") or []) + [f"{nf} (INCOMPATÍVEL)" for nf in (result.get("nfs_incompativeis") or [])]),
        info.get("destinatario", ""),
        dest.get("mun", ""),
        parse_number_br(info.get("valor", "")),
        result.get("valor_comparado"),
        result.get("componente_comparado", ""),
        result.get("base_frete"),
        result.get("base_calculo", ""),
        result.get("modo_calculo", ""),
        result.get("peso_base_kg"),
        result.get("tonelagem_taxa"),
        result.get("taxa_kg"),
        result.get("frete_peso_calculado"),
        result.get("adicionais_xml"),
        result.get("percentual"),
        result.get("frete_minimo"),
        result.get("esperado"),
        result.get("diferenca"),
        result.get("tolerancia"),
        result.get("partner_id", ""),
        result.get("tipo_cobranca", ""),
        result.get("regra_extra", ""),
        result.get("detalhe", ""),
        info.get("revisao_manual", ""),
        info.get("observacao_manual", ""),
        info.get("revisao_data", ""),
        trace,
        result.get("peso_xml_fonte", ""),
        result.get("peso_xml_todos", ""),
        result.get("peso_reverso_kg"),
        result.get("dif_peso_kg"),
        result.get("auditoria_peso_status", ""),
        result.get("auditoria_peso_obs", ""),
        info.get("arquivo", ""),
        info.get("path", ""),
        result.get("tipo_fiscal_oficial", info.get("tpCTe", "")),
        result.get("codigo_tpcte", info.get("tpCTe_codigo", "")),
        result.get("fonte_tipo_fiscal", info.get("tpCTe_fonte", "")),
        result.get("gatilho_tipo_fiscal", ""),
        result.get("tipo_cobranca_extra", "NORMAL"),
        result.get("campo_tipo_extra", ""),
        result.get("gatilho_tipo_extra", ""),
        result.get("fonte_tipo_extra", ""),
        result.get("explicacao_classificacao", "NORMAL — SEM INDÍCIO CONFIÁVEL DE EXTRA"),
        result.get("destino_comercial", ""),
        result.get("regra_comercial", ""),
        result.get("componentes_cobrados_xml", ""),
        result.get("componentes_opcionais_ignorados", ""),
        result.get("pedagio_componente_cobrado"),
        result.get("pedagio_componente_esperado"),
        result.get("pedagio_componente_diferenca"),
        result.get("pedagio_componente_status", ""),
        result.get("pedagio_componente_detalhe", ""),
    ]


def report_bucket(status):
    st = norm_text(status)
    if st.startswith("OK"):
        return "OK"
    if "IGNORADO" in st or "ANULACAO" in st:
        return "OUTROS"
    if "DIVERGENTE" in st:
        return "DIVERGENTES"
    if "EXTRA" in st:
        return "REVISAO_ERROS"
    if "NF" in st or "ORIGINAL" in st or "BASE" in st or "ROTAS" in st:
        return "SEM_BASE"
    if "PARCEIRO" in st or "REGRA" in st or "TABELAS" in st:
        return "SEM_PARCEIRO_REGRA"
    if "ERRO" in st or "PENDENTE" in st or "VALID" in st:
        return "REVISAO_ERROS"
    return "OUTROS"


def report_float(value):
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except Exception:
        return parse_number_br(value)


def add_group_totals(group, key, valor_total_cte, valor_comparado, esperado, diferenca):
    if key not in group:
        group[key] = {
            "qtd": 0,
            "valor_total_cte": 0.0,
            "valor_comparado": 0.0,
            "esperado": 0.0,
            "diferenca": 0.0,
        }
    group[key]["qtd"] += 1
    group[key]["valor_total_cte"] += valor_total_cte
    group[key]["valor_comparado"] += valor_comparado
    group[key]["esperado"] += esperado
    group[key]["diferenca"] += diferenca


def build_group_rows(title, group):
    rows = [[
        title, "Quantidade", "Valor total CT-e", "Valor comparado",
        "Valor esperado", "Diferença",
    ]]
    for key, vals in sorted(group.items(), key=lambda x: (-abs(x[1]["diferenca"]), x[0])):
        rows.append([
            key or "-", vals["qtd"], vals["valor_total_cte"],
            vals["valor_comparado"], vals["esperado"], vals["diferenca"],
        ])
    return rows


def build_validation_report_sheets(files):
    headers = ["Status", "CT-e", "Série", "Parceiro XML", "CNPJ Parceiro", "NF", "Validação Parcial", "NFs Ignoradas", "Destinatário", "Cidade/UF Destino XML", "Valor Total XML", "Valor Comparado XML", "Componente Comparado", "Frete Base", "Base Cálculo", "Modo Cálculo", "Peso Base KG", "R$/Ton", "R$/KG", "Frete Peso Calc.", "Adicionais XML", "Percentual", "Frete Mínimo", "Valor Esperado", "Diferença", "Tolerância", "Parceiro ID", "Tipo cobrança extra", "Regra extra", "Detalhe", "Revisão manual", "Observação manual", "Data revisão", "Diagnóstico", "Fonte Peso XML", "Pesos XML", "Peso Reverso KG", "Dif. Peso KG", "Auditoria Peso", "Obs. Peso", "Arquivo XML", "Caminho", "Tipo fiscal oficial", "Código tpCTe", "Fonte tipo fiscal", "Gatilho tipo fiscal", "Cobrança extra detectada", "Campo da cobrança extra", "Texto/gatilho da cobrança extra", "Fonte da cobrança extra", "Explicação da classificação", "Destino comercial utilizado", "Regra comercial aplicada", "Componentes cobrados no XML", "Componentes opcionais ignorados", "Pedágio cobrado XML", "Pedágio esperado se cobrado", "Diferença pedágio", "Status pedágio", "Detalhe pedágio"]
    widths = [18, 12, 8, 34, 20, 18, 16, 24, 34, 26, 14, 16, 22, 14, 16, 15, 14, 12, 12, 16, 14, 12, 14, 14, 14, 12, 14, 18, 22, 45, 18, 45, 18, 80, 16, 42, 16, 14, 18, 55, 34, 55, 20, 14, 30, 24, 24, 24, 50, 30, 48, 26, 30, 55, 30, 18, 22, 18, 30, 40]
    all_rows = [headers]
    buckets = {}

    by_status = {}
    by_partner = {}
    by_partner_id = {}
    by_charge_type = {}
    by_fiscal_type = {}
    by_manual_review = {}
    top_diffs = []

    total_files = 0
    total_cte = 0.0
    total_compared = 0.0
    total_base = 0.0
    total_expected = 0.0
    total_diff = 0.0
    reviewed = 0
    with_obs = 0

    for info in files:
        row = validation_export_row(info)
        all_rows.append(row)
        buckets.setdefault(report_bucket(row[0]), [headers]).append(row)

        total_files += 1
        status = row[0] or "NÃO VALIDADO"
        partner_xml = row[3] or "-"
        partner_id = row[26] or "-"
        charge_type = row[27] or "-"
        fiscal_type = row[42] or "-"
        manual_review = row[30] or "-"
        valor_total_cte = report_float(row[10])
        valor_comparado = report_float(row[11])
        base_frete = report_float(row[13])
        esperado = report_float(row[23])
        diferenca = report_float(row[24])

        total_cte += valor_total_cte
        total_compared += valor_comparado
        total_base += base_frete
        total_expected += esperado
        total_diff += diferenca
        if row[30]:
            reviewed += 1
        if row[31]:
            with_obs += 1

        add_group_totals(by_status, status, valor_total_cte, valor_comparado, esperado, diferenca)
        add_group_totals(by_partner, partner_xml, valor_total_cte, valor_comparado, esperado, diferenca)
        add_group_totals(by_partner_id, partner_id, valor_total_cte, valor_comparado, esperado, diferenca)
        add_group_totals(by_charge_type, charge_type, valor_total_cte, valor_comparado, esperado, diferenca)
        add_group_totals(by_fiscal_type, fiscal_type, valor_total_cte, valor_comparado, esperado, diferenca)
        add_group_totals(by_manual_review, manual_review, valor_total_cte, valor_comparado, esperado, diferenca)

        if abs(diferenca) > 0:
            top_diffs.append([
                abs(diferenca),
                row[0], row[1], row[3], row[5], row[10], row[11], row[23], row[24], row[29], row[31], row[40]
            ])

    summary_counts = {}
    for row in all_rows[1:]:
        summary_counts[row[0]] = summary_counts.get(row[0], 0) + 1

    executive_rows = [
        ["Indicador", "Valor"],
        ["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")],
        ["Arquivos no relatório", total_files],
        ["Valor total dos CT-es", total_cte],
        ["Valor dos componentes comparados", total_compared],
        ["Frete base total", total_base],
        ["Valor esperado total", total_expected],
        ["Diferença total", total_diff],
        ["Itens revisados manualmente", reviewed],
        ["Itens com observação manual", with_obs],
        ["Status diferentes", len(summary_counts)],
        ["Parceiros XML diferentes", len(by_partner)],
    ]

    status_rows = [["Status", "Quantidade"]] + [[k or "NÃO VALIDADO", v] for k, v in sorted(summary_counts.items(), key=lambda x: (-x[1], x[0]))]
    top_diffs.sort(key=lambda r: r[0], reverse=True)
    top_rows = [[
        "Diferença absoluta", "Status", "CT-e", "Parceiro XML", "NF",
        "Valor total CT-e", "Valor comparado", "Valor esperado", "Diferença",
        "Detalhe", "Observação manual", "Arquivo XML",
    ]]
    top_rows += top_diffs[:100]

    sheets = [
        ("EXECUTIVO", executive_rows, [34, 22]),
        ("RESUMO_STATUS", status_rows, [28, 14]),
        ("POR_STATUS", build_group_rows("Status", by_status), [28, 14, 16, 16, 16, 16]),
        ("POR_PARCEIRO", build_group_rows("Parceiro XML", by_partner), [42, 14, 16, 16, 16, 16]),
        ("POR_PARCEIRO_ID", build_group_rows("Parceiro ID", by_partner_id), [20, 14, 16, 16, 16, 16]),
        ("POR_TIPO_COBRANCA", build_group_rows("Tipo cobrança", by_charge_type), [24, 14, 16, 16, 16, 16]),
        ("POR_TIPO_FISCAL", build_group_rows("Tipo fiscal oficial", by_fiscal_type), [24, 14, 16, 16, 16, 16]),
        ("POR_REVISAO", build_group_rows("Revisão manual", by_manual_review), [24, 14, 16, 16, 16, 16]),
        ("TOP_DIVERGENCIAS", top_rows, [18, 18, 12, 34, 18, 14, 14, 14, 14, 45, 45, 34]),
        ("TODOS", all_rows, widths),
    ]
    for name in ["OK", "DIVERGENTES", "SEM_BASE", "SEM_PARCEIRO_REGRA", "REVISAO_ERROS", "OUTROS"]:
        if name in buckets:
            sheets.append((name, buckets[name], widths))
    return sheets


def weight_audit_row(info):
    result = info.get("validacao") or {}
    emit = info.get("emit", {}) or {}
    dest = info.get("dest", {}) or {}
    return [
        result.get("status", "NÃO VALIDADO"),
        info.get("numero", ""),
        info.get("serie", ""),
        result.get("nf", "") or get_nf_from_info(info),
        info.get("emitente", ""),
        emit.get("cnpjcpf", ""),
        info.get("destinatario", ""),
        dest.get("mun", ""),
        result.get("componente_comparado", ""),
        result.get("valor_comparado"),
        result.get("peso_base_kg"),
        result.get("peso_xml_fonte", ""),
        result.get("peso_xml_todos", ""),
        result.get("tonelagem_taxa"),
        result.get("taxa_kg"),
        result.get("frete_peso_calculado"),
        result.get("peso_reverso_kg"),
        result.get("dif_peso_kg"),
        result.get("auditoria_peso_status", ""),
        result.get("auditoria_peso_obs", ""),
        info.get("arquivo", ""),
        info.get("path", ""),
    ]


def build_weight_audit_sheets(files):
    headers = [
        "Status", "CT-e", "Série", "NF", "Parceiro XML", "CNPJ Parceiro", "Destinatário", "Cidade/UF",
        "Componente Comparado", "Valor FRETE PESO XML", "Peso Usado KG", "Fonte Peso", "Pesos no XML",
        "R$/Ton", "R$/KG", "Frete Peso Calculado", "Peso Reverso KG", "Dif. Peso KG", "Auditoria", "Observação", "Arquivo XML", "Caminho"
    ]
    rows = [headers]
    frete_peso_infos = []
    for info in files:
        result = info.get("validacao") or {}
        modo = norm_text(result.get("modo_calculo", ""))
        status = norm_text(result.get("status", ""))
        comp = norm_text(result.get("componente_comparado", ""))
        if "FRETE_PESO" in modo or "FRETE PESO" in status or "FRETE PESO" in comp:
            frete_peso_infos.append(info)
            rows.append(weight_audit_row(info))

    counts = {}
    for info in frete_peso_infos:
        st = (info.get("validacao") or {}).get("auditoria_peso_status", "") or "SEM AUDITORIA"
        counts[st] = counts.get(st, 0) + 1

    resumo = [["Indicador", "Valor"]]
    resumo.append(["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M:%S")])
    resumo.append(["Itens FRETE PESO", len(frete_peso_infos)])
    for st, qtd in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        resumo.append([st, qtd])
    resumo.append(["Regra", "Peso reverso = Valor FRETE PESO XML / R$/KG"])
    resumo.append(["Tolerância peso OK", "0,05 kg"])
    resumo.append(["Observação", "Se houver frete mínimo, o peso reverso não representa o peso real."])
    widths = [18, 12, 8, 18, 34, 20, 34, 22, 22, 18, 16, 16, 45, 12, 12, 18, 18, 14, 18, 55, 34, 55]
    return [
        ("RESUMO_PESO", resumo, [34, 55]),
        ("AUDITORIA_PESO", rows, widths),
    ]


def write_weight_audit_xlsx(file_path, files):
    sheets = build_weight_audit_sheets(files)
    write_simple_xlsx(file_path, sheets)


def write_validation_report_xlsx(file_path, files):
    sheets = build_validation_report_sheets(files)
    write_simple_xlsx(file_path, sheets)


EXPORTED_FUNCTIONS = ('xml_escape', 'excel_column_name', 'safe_sheet_name', 'xlsx_cell_xml', 'xlsx_sheet_xml', 'write_simple_xlsx', 'audit_issue', 'partner_name_for_audit', 'audit_partner_tables', 'build_partner_audit_sheets', 'write_partner_audit_xlsx', 'partner_audit_text', 'base_audit_issue', 'audit_rodovitor_base', 'build_base_audit_sheets', 'write_base_audit_xlsx', 'base_audit_text', 'validation_export_row', 'report_bucket', 'report_float', 'add_group_totals', 'build_group_rows', 'build_validation_report_sheets', 'weight_audit_row', 'build_weight_audit_sheets', 'write_weight_audit_xlsx', 'write_validation_report_xlsx')
EXTRACTION_VERSION = "2.7.0-rc18"


def install_report_excel_compat(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
    installed = install_rebound_functions(globals(), target_globals, EXPORTED_FUNCTIONS)
    state = {
        "version": EXTRACTION_VERSION,
        "module": __name__,
        "functions": list(installed),
        "active": True,
    }
    target_globals["CENTRAL_CTE_REPORT_EXCEL_COMPAT_STATE"] = state
    return state


__all__ = ["install_report_excel_compat", "EXPORTED_FUNCTIONS"]
