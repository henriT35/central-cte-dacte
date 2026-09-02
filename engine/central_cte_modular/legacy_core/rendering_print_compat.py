from __future__ import annotations

"""Renderizador DACTE/HTML e abertura de impressão históricos preservados como fallback."""

from typing import Any, MutableMapping

from .function_rebinder import install_rebound_functions

CODE128_PATTERNS = [
    "212222","222122","222221","121223","121322","131222","122213","122312","132212","221213",
    "221312","231212","112232","122132","122231","113222","123122","123221","223211","221132",
    "221231","213212","223112","312131","311222","321122","321221","312212","322112","322211",
    "212123","212321","232121","111323","131123","131321","112313","132113","132311","211313",
    "231113","231311","112133","112331","132131","113123","113321","133121","313121","211331",
    "231131","213113","213311","213131","311123","311321","331121","312113","312311","332111",
    "314111","221411","431111","111224","111422","121124","121421","141122","141221","112214",
    "112412","122114","122411","142112","142211","241211","221114","413111","241112","134111",
    "111242","121142","121241","114212","124112","124211","411212","421112","421211","212141",
    "214121","412121","111143","111341","131141","114113","114311","411113","411311","113141",
    "114131","311141","411131","211412","211214","211232","2331112"
]

CSS = r"""
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: #000; font-family: "Times New Roman", Arial, sans-serif; font-size: 8.8px; }
.printbar { position: sticky; top: 0; z-index: 10; padding: 9px; background: #efefef; border-bottom: 1px solid #bbb; text-align: center; font-family: Arial, sans-serif; }
.printbar button { padding: 8px 14px; cursor: pointer; }
.page { width: 210mm; min-height: 297mm; margin: 0 auto; background: #fff; padding: 7mm; page-break-after: always; }
.page:last-child { page-break-after: auto; }
.dacte { width: 100%; border: 1px solid #111; background: white; }
.decl { border-bottom: 1px solid #111; }
.decl-title { text-align: center; font-size: 8px; font-weight: bold; padding: 2px; border-bottom: 1px solid #111; }
.decl-grid { display: grid; grid-template-columns: 27% 38% 16% 19%; min-height: 43px; }
.decl-grid > div { border-right: 1px solid #111; padding: 3px 5px; }
.decl-grid > div:last-child { border-right: 0; }
.sig-space { height: 24px; border-bottom: 1px solid #111; }
.date-line { font-weight: bold; font-size: 8px; border-bottom: 1px solid #111; margin: 2px 8px; }
.header-main { display: grid; grid-template-columns: 43% 39% 18%; border-bottom: 1px solid #111; min-height: 94px; }
.header-main > div { border-right: 1px solid #111; }
.header-main > div:last-child { border-right: 0; }
.emitente { text-align: center; padding: 8px 8px 4px; line-height: 1.18; }
.emitente .nome { font-size: 13px; font-weight: bold; margin-bottom: 12px; }
.dacte-center { display: grid; grid-template-rows: 23px 12px 23px 40px 23px; }
.dacte-title { text-align: center; font-size: 17px; font-weight: bold; padding-top: 2px; }
.dacte-subtitle { text-align: center; font-size: 8px; font-weight: bold; }
.doc-grid { display: grid; grid-template-columns: 13% 11% 24% 14% 38%; border-top: 1px solid #111; border-bottom: 1px solid #111; }
.doc-grid > div { border-right: 1px solid #111; padding: 1px 2px; text-align: center; }
.doc-grid > div:last-child { border-right: 0; }
.lbl { font-size: 6.8px; text-transform: uppercase; line-height: 1.05; }
.val { font-weight: bold; font-size: 8.5px; line-height: 1.1; overflow-wrap: anywhere; }
.number { font-size: 13px; font-weight: bold; }
.barcode-wrap { padding: 2px 20px; }
.barcode-svg { width: 100%; height: 36px; display: block; }
.chave { padding: 4px 5px; font-size: 8px; font-weight: bold; }
.modal { text-align: center; display: grid; grid-template-rows: 52px 42px; }
.modal-title { padding-top: 14px; font-size: 12px; font-weight: bold; }
.modal-title b { font-size: 14px; }
.modal-suframa { border-top: 1px solid #111; padding: 4px; }
.info-service { display: grid; grid-template-columns: 43% 57%; border-bottom: 1px solid #111; }
.info-service > div { border-right: 1px solid #111; }
.info-service > div:last-child { border-right: 0; }
.service-left { display: grid; grid-template-columns: 1fr 1fr; }
.service-left > div { min-height: 26px; border-right: 1px solid #111; border-bottom: 1px solid #111; padding: 3px 5px; }
.service-left > div:nth-child(even) { border-right: 0; }
.service-left > div:nth-last-child(-n+2) { border-bottom: 0; }
.service-right { display: grid; grid-template-rows: 38px 14px; }
.consulta { text-align: center; font-weight: bold; font-size: 10px; padding: 5px; border-bottom: 1px solid #111; }
.protocol { text-align: center; font-weight: bold; font-size: 8.5px; padding: 1px; }
.full-cell { border-bottom: 1px solid #111; padding: 4px 6px; min-height: 24px; }
.route { display: grid; grid-template-columns: 1fr 1fr; border-bottom: 1px solid #111; }
.route > div { padding: 3px 6px; border-right: 1px solid #111; }
.route > div:last-child { border-right: 0; }
.people { display: grid; grid-template-columns: 1fr 1fr; border-bottom: 1px solid #111; }
.person-box { min-height: 66px; border-right: 1px solid #111; border-bottom: 1px solid #111; padding: 3px 6px; overflow: hidden; }
.person-box:nth-child(even) { border-right: 0; }
.people .person-box:nth-last-child(-n+2) { border-bottom: 0; }
.person-title { font-size: 6.8px; text-transform: uppercase; line-height: 1; }
.person-name { font-size: 9px; font-weight: bold; line-height: 1.05; min-height: 10px; overflow-wrap: anywhere; }
.addr-line { line-height: 1.05; min-height: 10px; overflow-wrap: anywhere; }
.addr-line span, .person-grid span, .tomador-grid span, .tomador-docs span { font-size: 6.2px; text-transform: uppercase; font-weight: normal; }
.pfield { min-width: 0; overflow: hidden; line-height: 1.03; }
.pfield b { display: block; font-size: 7.4px; line-height: 1.03; overflow-wrap: anywhere; word-break: normal; hyphens: auto; }
.person-grid { display: grid; grid-template-columns: 24% 12% 23% 19% 12% 10%; column-gap: 0; align-items: start; line-height: 1.03; width: 100%; overflow: hidden; padding-top: 1px; }
.tomador-box { display: grid; grid-template-columns: 52% 48%; border-bottom: 1px solid #111; }
.tomador-box > div { min-height: 37px; border-right: 1px solid #111; padding: 3px 6px; overflow: hidden; }
.tomador-box > div:last-child { border-right: 0; }
.tomador-docs { display: grid; grid-template-columns: 42% 58%; column-gap: 0; margin-top: 1px; }
.tomador-grid { display: grid; grid-template-columns: 42% 16% 20% 22%; column-gap: 0; align-items: start; width: 100%; overflow: hidden; }
.carga-top { display: grid; grid-template-columns: 40% 34% 26%; border-bottom: 1px solid #111; }
.carga-top > div { border-right: 1px solid #111; padding: 3px 6px; min-height: 28px; }
.carga-top > div:last-child { border-right: 0; }
.carga-bottom { display: grid; grid-template-columns: 11% 11% 11% 10% 13% 20% 12% 12%; border-bottom: 1px solid #111; }
.carga-bottom > div { border-right: 1px solid #111; padding: 3px 4px; min-height: 48px; text-align: center; }
.carga-bottom > div:last-child { border-right: 0; }
.section-title { text-align: center; font-size: 10px; font-weight: normal; padding: 2px; border-bottom: 1px solid #111; }
.comps { display: grid; grid-template-columns: 24% 24% 24% 28%; min-height: 72px; border-bottom: 1px solid #111; }
.comps > div { border-right: 1px solid #111; }
.comps > div:last-child { border-right: 0; }
.comp-table { width: 100%; border-collapse: collapse; }
.comp-table td, .comp-table th { border: 0; padding: 3px 5px; text-align: left; }
.comp-table th { font-size: 7px; font-weight: normal; }
.total-box { display: grid; grid-template-rows: 1fr 1fr; }
.total-box > div { padding: 4px 6px; }
.total-box > div:first-child { border-bottom: 1px solid #111; }
.tax-grid { display: grid; grid-template-columns: 45% 14% 10% 13% 10% 8%; border-bottom: 1px solid #111; }
.tax-grid > div { border-right: 1px solid #111; padding: 3px 6px; min-height: 28px; }
.tax-grid > div:last-child { border-right: 0; }
.docs { display: grid; grid-template-columns: 1fr 1fr; min-height: 64px; border-bottom: 1px solid #111; }
.docs > div { border-right: 1px solid #111; padding: 4px 6px; }
.docs > div:last-child { border-right: 0; }
.doc-line { margin-bottom: 3px; }
.obs { min-height: 45px; padding: 5px 7px; border-bottom: 1px solid #111; line-height: 1.2; white-space: pre-line; }
.rodo { display: grid; grid-template-columns: 23% 16% 61%; border-bottom: 1px solid #111; }
.rodo > div { border-right: 1px solid #111; padding: 4px 6px; min-height: 32px; }
.rodo > div:last-child { border-right: 0; }
.footer { display: grid; grid-template-columns: 68% 32%; min-height: 54px; }
.footer > div { border-right: 1px solid #111; padding: 5px 7px; white-space: pre-line; }
.footer > div:last-child { border-right: 0; }
.footer-title { text-align: center; border-bottom: 1px solid #111; margin: -5px -7px 5px; padding: 2px; font-size: 10px; }
.center { text-align: center; }
.right { text-align: right; }
.bold { font-weight: bold; }
@media print {
    body { background: #fff; }
    .printbar { display: none; }
    .page { width: auto; min-height: auto; margin: 0; padding: 4mm; }
    @page { size: A4 portrait; margin: 4mm; }
}
"""

def code128c_svg(digits, height=46):
    digits = only_digits(digits)
    if len(digits) % 2 != 0:
        digits = "0" + digits

    values = [int(digits[i:i+2]) for i in range(0, len(digits), 2)]
    checksum = 105
    for i, val in enumerate(values, start=1):
        checksum += val * i
    checksum %= 103

    codes = [105] + values + [checksum, 106]
    quiet = 10
    x = quiet
    rects = []

    for code in codes:
        pattern = CODE128_PATTERNS[code]
        black = True
        for width_char in pattern:
            w = int(width_char)
            if black:
                rects.append(f"<rect x='{x}' y='0' width='{w}' height='{height}'/>")
            x += w
            black = not black

    total_width = x + quiet
    return f"<svg class='barcode-svg' viewBox='0 0 {total_width} {height}' preserveAspectRatio='none'>{''.join(rects)}</svg>"

def cell(label, value="", cls=""):
    return f"<div class='cell {cls}'><div class='lbl'>{escape(label)}</div><div class='val'>{value}</div></div>"

def fmt_field(label, value):
    return f"<div class='pfield'><span>{escape(label)}</span><b>{escape(value or '')}</b></div>"

def person_box(title, p):
    return f"""
    <div class="person-box">
        <div class="person-title">{escape(title)}</div>
        <div class="person-name">{escape(p.get("nome", ""))}</div>
        <div class="addr-line"><span>ENDEREÇO</span> {escape(p.get("ender", ""))}</div>
        <div class="person-grid">
            {fmt_field("MUNICÍPIO", p.get("mun", ""))}
            {fmt_field("CEP", p.get("cep", ""))}
            {fmt_field("CNPJ/CPF", p.get("cnpjcpf", ""))}
            {fmt_field("INSCRIÇÃO ESTADUAL", p.get("ie", ""))}
            {fmt_field("FONE", p.get("fone", ""))}
            {fmt_field("PAÍS", p.get("pais", ""))}
        </div>
    </div>
    """

def tomador_box(toma):
    return f"""
    <div class="tomador-box">
        <div class="tomador-left">
            <div class="person-title">TOMADOR DO SERVIÇO</div>
            <div class="person-name">{escape(toma.get("nome", ""))}</div>
            <div class="addr-line"><span>ENDEREÇO</span> {escape(toma.get("ender", ""))}</div>
            <div class="tomador-docs">
                {fmt_field("CNPJ/CPF", toma.get("cnpjcpf", ""))}
                {fmt_field("INSCRIÇÃO ESTADUAL", toma.get("ie", ""))}
            </div>
        </div>
        <div class="tomador-right">
            <div class="tomador-grid">
                {fmt_field("MUNICÍPIO", toma.get("mun", ""))}
                {fmt_field("CEP", toma.get("cep", ""))}
                {fmt_field("PAÍS", toma.get("pais", ""))}
                {fmt_field("FONE", toma.get("fone", ""))}
            </div>
        </div>
    </div>
    """

def render_dacte_page(info):
    emit = info["emit"]
    rem = info["rem"]
    dest = info["dest"]
    exped = info["exped"]
    receb = info["receb"]
    toma = info["toma"]
    prot = info["prot"]
    imp = info["imposto"]
    seg = info["seguro"]
    chave = info.get("chave", "")

    comp_cols = ["", "", ""]
    comps = info.get("componentes", [])
    for idx, comp in enumerate(comps[:3]):
        comp_cols[idx] = f"""
        <table class="comp-table">
            <tr><th>NOME</th><th class="right">VALOR</th></tr>
            <tr><td>{escape(comp.get("nome", ""))}</td><td class="right">{money(comp.get("valor", ""))}</td></tr>
        </table>
        """
    if not comps:
        comp_cols[0] = f"""
        <table class="comp-table">
            <tr><th>NOME</th><th class="right">VALOR</th></tr>
            <tr><td>FRETE VALOR</td><td class="right">{money(info.get("vTPrest", ""))}</td></tr>
        </table>
        """

    docs = info.get("docs", [])
    left_docs = docs[0::2]
    right_docs = docs[1::2]

    def docs_block(items):
        if not items:
            return '<div class="doc-line"><span class="lbl">TP DOC.</span> &nbsp; <span class="lbl">CNPJ/CPF EMITENTE</span> &nbsp; <span class="lbl">SÉRIE/NRO. DOCUMENTO</span></div>'
        rows = []
        for d in items:
            tipo_label = f"{d['tipo']} {d.get('n_doc', '')}".strip()
            serie_num = d.get("serie_numero", "")
            chave_doc = d.get("chave", "")
            rows.append(
                f"<div class='doc-line'><span class='lbl'>TP DOC.</span> <b>{escape(tipo_label)}</b> &nbsp; "
                f"<span class='lbl'>CNPJ/CPF EMITENTE</span> {escape(d.get('cnpj', ''))} &nbsp; "
                f"<span class='lbl'>SÉRIE/NRO. DOCUMENTO</span> {escape(serie_num)}<br>"
                f"{escape(chave_doc)}</div>"
            )
        return "".join(rows)

    return f"""
<div class="page">
<div class="dacte">
    <div class="decl">
        <div class="decl-title">DECLARO QUE RECEBI OS VOLUMES DESTE CONHECIMENTO EM PERFEITO ESTADO PELO QUE DOU POR CUMPRIDO O PRESENTE CONTRATO DE TRANSPORTE</div>
        <div class="decl-grid">
            <div><div>NOME</div><div class="sig-space"></div><div>RG</div></div>
            <div class="center"><div style="height:30px;"></div><div>ASSINATURA / CARIMBO</div></div>
            <div class="center"><div class="lbl">CHEGADA DATA/HORA</div><div class="date-line">__/__/____ &nbsp; __:__</div><div class="lbl">SAÍDA DATA/HORA</div><div class="date-line">__/__/____ &nbsp; __:__</div></div>
            <div class="center"><div style="font-size:13px;font-weight:bold;">CT-e</div><div>Nº <span class="number">{escape(info.get("numero", ""))}</span></div><div>SÉRIE: <b>{escape(info.get("serie", ""))}</b></div></div>
        </div>
    </div>

    <div class="header-main">
        <div class="emitente">
            <div class="nome">{escape(emit.get("nome", ""))}</div>
            <div>{escape(emit.get("ender", ""))}</div>
            <div>{escape(emit.get("mun", ""))}</div>
            <div>CEP: {escape(emit.get("cep", ""))}</div>
            <div>CNPJ: {escape(emit.get("cnpjcpf", ""))}</div>
            <div>INSCRIÇÃO ESTADUAL: {escape(emit.get("ie", ""))}</div>
            <div>TELEFONE: {escape(emit.get("fone", ""))}</div>
        </div>
        <div class="dacte-center">
            <div class="dacte-title">DACTE</div>
            <div class="dacte-subtitle">Documento Auxiliar do Conhecimento de Transporte Eletrônico</div>
            <div class="doc-grid">
                <div>{cell("Modelo", escape(info.get("modelo", "")))}</div>
                <div>{cell("Série", escape(info.get("serie", "")))}</div>
                <div>{cell("Número", escape(info.get("numero", "")))}</div>
                <div>{cell("Folha", "01/01")}</div>
                <div>{cell("Data e Hora de Emissão", escape(info.get("data_br", "")))}</div>
            </div>
            <div class="barcode-wrap">{code128c_svg(chave)}</div>
            <div class="chave">Chave de acesso &nbsp; {escape(format_chave(chave))}</div>
        </div>
        <div class="modal">
            <div class="modal-title">MODAL<br><b>{escape(info.get("modal", ""))}</b></div>
            <div class="modal-suframa"><div class="lbl">INSC. SUFRAMA DO DESTINATÁRIO</div></div>
        </div>
    </div>

    <div class="info-service">
        <div class="service-left">
            <div>{cell("Tipo do CT-e", escape(info.get("tpCTe", "")))}</div>
            <div>{cell("Tipo do Serviço", escape(info.get("tpServ", "")))}</div>
            <div>{cell("Tomador do Serviço", escape(info.get("toma_txt", "")))}</div>
            <div>{cell("Forma de Pagamento", escape(info.get("forma_pagamento", "")))}</div>
        </div>
        <div class="service-right">
            <div class="consulta">Consulta de autenticidade no portal nacional do CT-e, no site da Sefaz Autorizadora, ou em http://www.cte.fazenda.gov.br/portal</div>
            <div class="protocol"><span class="lbl">PROTOCOLO DE AUTORIZAÇÃO DE USO</span> &nbsp; {escape(prot.get("nProt", ""))} &nbsp; {escape(prot.get("dhRecbto", ""))}</div>
        </div>
    </div>

    <div class="full-cell"><div class="lbl">CFOP - NATUREZA DA OPERAÇÃO</div><div class="val">{escape(info.get("cfop", ""))} - {escape(info.get("natOp", ""))}</div></div>
    <div class="route"><div>{cell("Origem da Prestação", escape(info.get("origem", "")))}</div><div>{cell("Destino da Prestação", escape(info.get("destino", "")))}</div></div>
    <div class="people">{person_box("Remetente", rem)}{person_box("Destinatário", dest)}{person_box("Expedidor", exped)}{person_box("Recebedor", receb)}</div>
    {tomador_box(toma)}

    <div class="carga-top">
        <div>{cell("Produto Predominante", escape(info.get("produto", "")))}</div>
        <div>{cell("Outras Características da Carga", escape(info.get("outras_carac", "")))}</div>
        <div>{cell("Valor Total da Mercadoria", money(info.get("valor_carga", "")), "right")}</div>
    </div>

    <div class="carga-bottom">
        <div>{cell("Peso Bruto (Kg)", qty(info.get("peso_bruto", ""), 4))}</div>
        <div>{cell("Peso Base Cálc. (Kg)", qty(info.get("peso_base", ""), 4))}</div>
        <div>{cell("Peso Aferido (Kg)", qty(info.get("peso_aferido", ""), 4))}</div>
        <div>{cell("Cubagem (m³)", qty(info.get("cubagem", ""), 4))}</div>
        <div>{cell("Qtde. Volumes (Unid)", escape(info.get("volumes", "")))}</div>
        <div>{cell("Nome da Seguradora", escape(seg.get("seguradora", "")))}</div>
        <div>{cell("Responsável", escape(seg.get("resp", "")))}</div>
        <div>{cell("Número da Apólice", escape(seg.get("apolice", "")))}<br>{cell("Número da Averbação", escape(seg.get("averbacao", "")))}</div>
    </div>

    <div class="section-title">COMPONENTES DO VALOR DA PRESTAÇÃO DE SERVIÇO</div>
    <div class="comps">
        <div>{comp_cols[0]}</div><div>{comp_cols[1]}</div><div>{comp_cols[2]}</div>
        <div class="total-box">
            <div><div class="lbl">VALOR TOTAL DO SERVIÇO</div><div class="val right">{money(info.get("vTPrest", ""))}</div></div>
            <div><div class="lbl">VALOR A RECEBER</div><div class="val right">{money(info.get("vRec", ""))}</div></div>
        </div>
    </div>

    <div class="section-title">INFORMAÇÕES RELATIVAS AO IMPOSTO</div>
    <div class="tax-grid">
        <div>{cell("Situação Tributária", escape(imp.get("sit", "")))}</div>
        <div>{cell("Base de Cálculo", money(imp.get("base", "")), "right")}</div>
        <div>{cell("Alíq. ICMS", escape(imp.get("aliq", "")), "right")}</div>
        <div>{cell("Valor ICMS", money(imp.get("valor", "")), "right")}</div>
        <div>{cell("% Red.BC Calc.", escape(imp.get("red", "")), "right")}</div>
        <div>{cell("ICMS ST", money(imp.get("st", "")), "right")}</div>
    </div>

    <div class="section-title">DOCUMENTOS ORIGINÁRIOS</div>
    <div class="docs"><div>{docs_block(left_docs)}</div><div>{docs_block(right_docs)}</div></div>
    <div class="section-title">OBSERVAÇÕES</div>
    <div class="obs">{escape(info.get("obs_principal") or info.get("obs") or "")}</div>
    <div class="section-title">DADOS ESPECÍFICOS DO MODAL RODOVIÁRIO</div>
    <div class="rodo">
        <div>{cell("RNTRC da Empresa", escape(info.get("rntrc", "")))}</div>
        <div>{cell("Data Prevista de Entrega", "")}</div>
        <div>{cell("Este conhecimento de transporte atende à legislação de transporte rodoviário em vigor", "")}</div>
    </div>
    <div class="footer">
        <div><div class="footer-title">USO EXCLUSIVO DO EMISSOR DO CT-e</div>{escape(info.get("uso_exclusivo") or "")}</div>
        <div><div class="footer-title">RESERVADO AO FISCO</div></div>
    </div>
</div>
</div>
"""

def summary_page(info):
    return f"""
<div class="page">
<div class="dacte" style="padding:20px;font-family:Arial,sans-serif;">
    <h2>Resumo do XML</h2>
    <table style="width:100%;border-collapse:collapse;">
        <tr><td style="border:1px solid #000;padding:8px;">Arquivo</td><td style="border:1px solid #000;padding:8px;">{escape(info.get("arquivo", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Tipo</td><td style="border:1px solid #000;padding:8px;">{escape(info.get("tipo", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Número</td><td style="border:1px solid #000;padding:8px;">{escape(info.get("numero", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Série</td><td style="border:1px solid #000;padding:8px;">{escape(info.get("serie", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Emitente</td><td style="border:1px solid #000;padding:8px;">{escape(info.get("emitente", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Destinatário</td><td style="border:1px solid #000;padding:8px;">{escape(info.get("destinatario", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Valor</td><td style="border:1px solid #000;padding:8px;">{money(info.get("valor", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Chave</td><td style="border:1px solid #000;padding:8px;">{escape(format_chave(info.get("chave", "")))}</td></tr>
    </table>
</div>
</div>
"""

def render_page(info):
    return render_dacte_page(info) if info.get("tipo") == "CT-e" else summary_page(info)

def render_document(infos, with_button=True, auto_print=False):
    button = '<div class="printbar"><button onclick="window.print()">Imprimir</button></div>' if with_button else ""
    auto_script = """
<script>
window.addEventListener('load', function() {
    setTimeout(function() { window.print(); }, 600);
});
</script>
""" if auto_print else ""
    pages = "\n".join(_central_cte_apply_complementary_information_html(info, render_page(info)) for info in infos)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>DACTE em Lote</title>
<style>{CSS}</style>
{auto_script}
</head>
<body>
{button}
{pages}
</body>
</html>"""

def print_file_windows(file_path):
    if os.name != "nt":
        raise RuntimeError("Impressão direta implementada apenas para Windows.")
    os.startfile(file_path, "print")

def open_html_for_print(html_path):
    """Abre HTML no navegador e deixa o próprio HTML chamar window.print().

    Isso evita o WinError 1155 do Windows, que acontece quando não existe
    associação para a ação "print" em arquivos .html.
    """
    path = Path(html_path)
    try:
        webbrowser.open(path.as_uri())
        return
    except Exception:
        pass
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return
    except Exception:
        pass
    webbrowser.open(str(path))

EXPORTED_FUNCTIONS = ('code128c_svg', 'cell', 'fmt_field', 'person_box', 'tomador_box', 'render_dacte_page', 'summary_page', 'render_page', 'render_document', 'print_file_windows', 'open_html_for_print')
EXPORTED_CONSTANTS = ('CODE128_PATTERNS', 'CSS')
EXTRACTION_VERSION = "2.6.68.8"


def install_rendering_print_compat(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
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
    target_globals["CENTRAL_CTE_RENDERING_PRINT_COMPAT_STATE"] = state
    return state


__all__ = ["install_rendering_print_compat", "EXPORTED_FUNCTIONS", "EXPORTED_CONSTANTS"]
