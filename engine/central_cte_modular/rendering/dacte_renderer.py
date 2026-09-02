from __future__ import annotations

from html import escape
from typing import Any, Mapping

from .overlays.compact_control import CompactControlOverlay

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


def only_digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def money(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(str(value).replace(',', '.')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def qty(value: Any, places: int = 4) -> str:
    if value in (None, ""):
        return ""
    try:
        return f"{float(str(value).replace(',', '.')):,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def format_access_key(value: Any) -> str:
    digits = only_digits(value)
    return " ".join(digits[index:index + 4] for index in range(0, len(digits), 4))


def code128c_svg(digits: Any, height: int = 46) -> str:
    number = only_digits(digits)
    if len(number) % 2 != 0:
        number = "0" + number
    values = [int(number[index:index + 2]) for index in range(0, len(number), 2)]
    checksum = 105
    for index, item in enumerate(values, start=1):
        checksum += item * index
    checksum %= 103
    codes = [105] + values + [checksum, 106]
    quiet = 10
    x = quiet
    rectangles: list[str] = []
    for code in codes:
        pattern = CODE128_PATTERNS[code]
        black = True
        for width_char in pattern:
            width = int(width_char)
            if black:
                rectangles.append(f"<rect x='{x}' y='0' width='{width}' height='{height}'/>")
            x += width
            black = not black
    total_width = x + quiet
    return (
        f"<svg class='barcode-svg' viewBox='0 0 {total_width} {height}' "
        f"preserveAspectRatio='none'>{''.join(rectangles)}</svg>"
    )


def cell(label: Any, value: Any = "", css_class: str = "") -> str:
    return f"<div class='cell {css_class}'><div class='lbl'>{escape(str(label or ''))}</div><div class='val'>{value}</div></div>"


def field(label: Any, value: Any) -> str:
    return f"<div class='pfield'><span>{escape(str(label or ''))}</span><b>{escape(str(value or ''))}</b></div>"


def person_box(title: str, person: Mapping[str, Any]) -> str:
    return f"""
    <div class="person-box">
        <div class="person-title">{escape(title)}</div>
        <div class="person-name">{escape(str(person.get("nome", "")))}</div>
        <div class="addr-line"><span>ENDEREÇO</span> {escape(str(person.get("ender", "")))}</div>
        <div class="person-grid">
            {field("MUNICÍPIO", person.get("mun", ""))}
            {field("CEP", person.get("cep", ""))}
            {field("CNPJ/CPF", person.get("cnpjcpf", ""))}
            {field("INSCRIÇÃO ESTADUAL", person.get("ie", ""))}
            {field("FONE", person.get("fone", ""))}
            {field("PAÍS", person.get("pais", ""))}
        </div>
    </div>
    """


def service_taker_box(person: Mapping[str, Any]) -> str:
    return f"""
    <div class="tomador-box">
        <div class="tomador-left">
            <div class="person-title">TOMADOR DO SERVIÇO</div>
            <div class="person-name">{escape(str(person.get("nome", "")))}</div>
            <div class="addr-line"><span>ENDEREÇO</span> {escape(str(person.get("ender", "")))}</div>
            <div class="tomador-docs">
                {field("CNPJ/CPF", person.get("cnpjcpf", ""))}
                {field("INSCRIÇÃO ESTADUAL", person.get("ie", ""))}
            </div>
        </div>
        <div class="tomador-right">
            <div class="tomador-grid">
                {field("MUNICÍPIO", person.get("mun", ""))}
                {field("CEP", person.get("cep", ""))}
                {field("PAÍS", person.get("pais", ""))}
                {field("FONE", person.get("fone", ""))}
            </div>
        </div>
    </div>
    """


class ModularDacteRenderer:
    """Renderiza DACTE e resumos sem depender das funções de layout do monólito."""

    def __init__(self, compact_overlay: CompactControlOverlay | None = None) -> None:
        self.compact_overlay = compact_overlay or CompactControlOverlay()

    def render_dacte_base(self, info: Mapping[str, Any]) -> str:
        emit = info["emit"]
        rem = info["rem"]
        dest = info["dest"]
        exped = info["exped"]
        receb = info["receb"]
        toma = info["toma"]
        prot = info["prot"]
        imp = info["imposto"]
        seg = info["seguro"]
        access_key = info.get("chave", "")

        component_columns = ["", "", ""]
        components = list(info.get("componentes", []) or [])
        for index, component in enumerate(components[:3]):
            component_columns[index] = f"""
        <table class="comp-table">
            <tr><th>NOME</th><th class="right">VALOR</th></tr>
            <tr><td>{escape(str(component.get("nome", "")))}</td><td class="right">{money(component.get("valor", ""))}</td></tr>
        </table>
        """
        if not components:
            component_columns[0] = f"""
        <table class="comp-table">
            <tr><th>NOME</th><th class="right">VALOR</th></tr>
            <tr><td>FRETE VALOR</td><td class="right">{money(info.get("vTPrest", ""))}</td></tr>
        </table>
        """

        documents = list(info.get("docs", []) or [])
        left_documents = documents[0::2]
        right_documents = documents[1::2]

        def documents_block(items: list[Mapping[str, Any]]) -> str:
            if not items:
                return '<div class="doc-line"><span class="lbl">TP DOC.</span> &nbsp; <span class="lbl">CNPJ/CPF EMITENTE</span> &nbsp; <span class="lbl">SÉRIE/NRO. DOCUMENTO</span></div>'
            rows: list[str] = []
            for document in items:
                type_label = f"{document['tipo']} {document.get('n_doc', '')}".strip()
                serial_number = document.get("serie_numero", "")
                document_key = document.get("chave", "")
                rows.append(
                    f"<div class='doc-line'><span class='lbl'>TP DOC.</span> <b>{escape(str(type_label))}</b> &nbsp; "
                    f"<span class='lbl'>CNPJ/CPF EMITENTE</span> {escape(str(document.get('cnpj', '')))} &nbsp; "
                    f"<span class='lbl'>SÉRIE/NRO. DOCUMENTO</span> {escape(str(serial_number))}<br>"
                    f"{escape(str(document_key))}</div>"
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
            <div class="center"><div style="font-size:13px;font-weight:bold;">CT-e</div><div>Nº <span class="number">{escape(str(info.get("numero", "")))}</span></div><div>SÉRIE: <b>{escape(str(info.get("serie", "")))}</b></div></div>
        </div>
    </div>

    <div class="header-main">
        <div class="emitente">
            <div class="nome">{escape(str(emit.get("nome", "")))}</div>
            <div>{escape(str(emit.get("ender", "")))}</div>
            <div>{escape(str(emit.get("mun", "")))}</div>
            <div>CEP: {escape(str(emit.get("cep", "")))}</div>
            <div>CNPJ: {escape(str(emit.get("cnpjcpf", "")))}</div>
            <div>INSCRIÇÃO ESTADUAL: {escape(str(emit.get("ie", "")))}</div>
            <div>TELEFONE: {escape(str(emit.get("fone", "")))}</div>
        </div>
        <div class="dacte-center">
            <div class="dacte-title">DACTE</div>
            <div class="dacte-subtitle">Documento Auxiliar do Conhecimento de Transporte Eletrônico</div>
            <div class="doc-grid">
                <div>{cell("Modelo", escape(str(info.get("modelo", ""))))}</div>
                <div>{cell("Série", escape(str(info.get("serie", ""))))}</div>
                <div>{cell("Número", escape(str(info.get("numero", ""))))}</div>
                <div>{cell("Folha", "01/01")}</div>
                <div>{cell("Data e Hora de Emissão", escape(str(info.get("data_br", ""))))}</div>
            </div>
            <div class="barcode-wrap">{code128c_svg(access_key)}</div>
            <div class="chave">Chave de acesso &nbsp; {escape(format_access_key(access_key))}</div>
        </div>
        <div class="modal">
            <div class="modal-title">MODAL<br><b>{escape(str(info.get("modal", "")))}</b></div>
            <div class="modal-suframa"><div class="lbl">INSC. SUFRAMA DO DESTINATÁRIO</div></div>
        </div>
    </div>

    <div class="info-service">
        <div class="service-left">
            <div>{cell("Tipo do CT-e", escape(str(info.get("tpCTe", ""))))}</div>
            <div>{cell("Tipo do Serviço", escape(str(info.get("tpServ", ""))))}</div>
            <div>{cell("Tomador do Serviço", escape(str(info.get("toma_txt", ""))))}</div>
            <div>{cell("Forma de Pagamento", escape(str(info.get("forma_pagamento", ""))))}</div>
        </div>
        <div class="service-right">
            <div class="consulta">Consulta de autenticidade no portal nacional do CT-e, no site da Sefaz Autorizadora, ou em http://www.cte.fazenda.gov.br/portal</div>
            <div class="protocol"><span class="lbl">PROTOCOLO DE AUTORIZAÇÃO DE USO</span> &nbsp; {escape(str(prot.get("nProt", "")))} &nbsp; {escape(str(prot.get("dhRecbto", "")))}</div>
        </div>
    </div>

    <div class="full-cell"><div class="lbl">CFOP - NATUREZA DA OPERAÇÃO</div><div class="val">{escape(str(info.get("cfop", "")))} - {escape(str(info.get("natOp", "")))}</div></div>
    <div class="route"><div>{cell("Origem da Prestação", escape(str(info.get("origem", ""))))}</div><div>{cell("Destino da Prestação", escape(str(info.get("destino", ""))))}</div></div>
    <div class="people">{person_box("Remetente", rem)}{person_box("Destinatário", dest)}{person_box("Expedidor", exped)}{person_box("Recebedor", receb)}</div>
    {service_taker_box(toma)}

    <div class="carga-top">
        <div>{cell("Produto Predominante", escape(str(info.get("produto", ""))))}</div>
        <div>{cell("Outras Características da Carga", escape(str(info.get("outras_carac", ""))))}</div>
        <div>{cell("Valor Total da Mercadoria", money(info.get("valor_carga", "")), "right")}</div>
    </div>

    <div class="carga-bottom">
        <div>{cell("Peso Bruto (Kg)", qty(info.get("peso_bruto", ""), 4))}</div>
        <div>{cell("Peso Base Cálc. (Kg)", qty(info.get("peso_base", ""), 4))}</div>
        <div>{cell("Peso Aferido (Kg)", qty(info.get("peso_aferido", ""), 4))}</div>
        <div>{cell("Cubagem (m³)", qty(info.get("cubagem", ""), 4))}</div>
        <div>{cell("Qtde. Volumes (Unid)", escape(str(info.get("volumes", ""))))}</div>
        <div>{cell("Nome da Seguradora", escape(str(seg.get("seguradora", ""))))}</div>
        <div>{cell("Responsável", escape(str(seg.get("resp", ""))))}</div>
        <div>{cell("Número da Apólice", escape(str(seg.get("apolice", ""))))}<br>{cell("Número da Averbação", escape(str(seg.get("averbacao", ""))))}</div>
    </div>

    <div class="section-title">COMPONENTES DO VALOR DA PRESTAÇÃO DE SERVIÇO</div>
    <div class="comps">
        <div>{component_columns[0]}</div><div>{component_columns[1]}</div><div>{component_columns[2]}</div>
        <div class="total-box">
            <div><div class="lbl">VALOR TOTAL DO SERVIÇO</div><div class="val right">{money(info.get("vTPrest", ""))}</div></div>
            <div><div class="lbl">VALOR A RECEBER</div><div class="val right">{money(info.get("vRec", ""))}</div></div>
        </div>
    </div>

    <div class="section-title">INFORMAÇÕES RELATIVAS AO IMPOSTO</div>
    <div class="tax-grid">
        <div>{cell("Situação Tributária", escape(str(imp.get("sit", ""))))}</div>
        <div>{cell("Base de Cálculo", money(imp.get("base", "")), "right")}</div>
        <div>{cell("Alíq. ICMS", escape(str(imp.get("aliq", ""))), "right")}</div>
        <div>{cell("Valor ICMS", money(imp.get("valor", "")), "right")}</div>
        <div>{cell("% Red.BC Calc.", escape(str(imp.get("red", ""))), "right")}</div>
        <div>{cell("ICMS ST", money(imp.get("st", "")), "right")}</div>
    </div>

    <div class="section-title">DOCUMENTOS ORIGINÁRIOS</div>
    <div class="docs"><div>{documents_block(left_documents)}</div><div>{documents_block(right_documents)}</div></div>
    <div class="section-title">OBSERVAÇÕES</div>
    <div class="obs">{escape(str(info.get("obs_principal") or info.get("obs") or ""))}</div>
    <div class="section-title">DADOS ESPECÍFICOS DO MODAL RODOVIÁRIO</div>
    <div class="rodo">
        <div>{cell("RNTRC da Empresa", escape(str(info.get("rntrc", ""))))}</div>
        <div>{cell("Data Prevista de Entrega", "")}</div>
        <div>{cell("Este conhecimento de transporte atende à legislação de transporte rodoviário em vigor", "")}</div>
    </div>
    <div class="footer">
        <div><div class="footer-title">USO EXCLUSIVO DO EMISSOR DO CT-e</div>{escape(str(info.get("uso_exclusivo") or ""))}</div>
        <div><div class="footer-title">RESERVADO AO FISCO</div></div>
    </div>
</div>
</div>
"""

    def render_dacte(self, info: Mapping[str, Any]) -> str:
        return self.compact_overlay.apply(info, self.render_dacte_base(info))

    def render_summary(self, info: Mapping[str, Any]) -> str:
        return f"""
<div class="page">
<div class="dacte" style="padding:20px;font-family:Arial,sans-serif;">
    <h2>Resumo do XML</h2>
    <table style="width:100%;border-collapse:collapse;">
        <tr><td style="border:1px solid #000;padding:8px;">Arquivo</td><td style="border:1px solid #000;padding:8px;">{escape(str(info.get("arquivo", "")))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Tipo</td><td style="border:1px solid #000;padding:8px;">{escape(str(info.get("tipo", "")))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Número</td><td style="border:1px solid #000;padding:8px;">{escape(str(info.get("numero", "")))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Série</td><td style="border:1px solid #000;padding:8px;">{escape(str(info.get("serie", "")))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Emitente</td><td style="border:1px solid #000;padding:8px;">{escape(str(info.get("emitente", "")))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Destinatário</td><td style="border:1px solid #000;padding:8px;">{escape(str(info.get("destinatario", "")))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Valor</td><td style="border:1px solid #000;padding:8px;">{money(info.get("valor", ""))}</td></tr>
        <tr><td style="border:1px solid #000;padding:8px;">Chave</td><td style="border:1px solid #000;padding:8px;">{escape(format_access_key(info.get("chave", "")))}</td></tr>
    </table>
</div>
</div>
"""
