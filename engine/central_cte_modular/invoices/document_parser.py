from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Mapping

from .input_models import InvoiceInputDocument, InvoiceInputItem
from .normalization import (
    cte_key,
    invoice_key,
    nf_key,
    normalize_cte,
    normalize_invoice_number,
    normalize_nf,
    normalize_space,
    parse_money,
    stable_hash,
    strip_accents,
)


_MONEY_PATTERN = re.compile(r"(?:R\$\s*)?\d{1,3}(?:\.\d{3})*,\d{2}|(?:R\$\s*)?\d+,\d{2}")


def _token(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", strip_accents(value).upper())


def _money_values(line: str) -> list[str]:
    return _MONEY_PATTERN.findall(str(line or ""))


def _parse_weight(value: Any) -> float:
    text = normalize_space(value)
    if not text:
        return 0.0
    text = re.sub(r"[^0-9,.-]+", "", text)
    if not text:
        return 0.0
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return round(float(text), 3)
    except Exception:
        return 0.0


def _extract_origin_cte(line: str) -> str:
    text = normalize_space(line)
    patterns = (
        r"\b\d{4}\s*/\s*\d{5,12}\s*[-/]\s*\d\b",
        r"\b[A-Z]{2,8}\s*/?\s*\d{3,12}\s*[-/]\s*\d\b",
        r"\b0*\d{5,12}\s*[-/]\s*\d\b",
    )
    for pattern in patterns:
        matches = list(re.finditer(pattern, text, re.I))
        if matches:
            return normalize_space(matches[-1].group(0))
    return ""


def _valid_cte(value: Any) -> bool:
    key = cte_key(value)
    if not key or len(key) < 4 or len(set(key)) <= 1:
        return False
    return key not in {"111111111", "111111114", "11111111", "1111"}


def _is_nf_number_header(line: str) -> bool:
    return _token(line) in {"NFISCALN", "NFISCALNO", "NFISCALNUMERO", "NUMERONFISCAL"}


def _is_nf_value_header(line: str) -> bool:
    return _token(line) in {"NFISCALR", "NFISCALRS", "VALORNFISCAL"}


def _line_is_money(line: str) -> bool:
    return bool(re.fullmatch(_MONEY_PATTERN, normalize_space(line)))


def _extract_nf_list(lines: list[str], start: int) -> list[str]:
    result: list[str] = []
    for line in lines[start + 1 : min(len(lines), start + 220)]:
        text = normalize_space(line)
        token = _token(text)
        if not text or token in {"NFISCAL", "R", "RS"}:
            continue
        if _is_nf_number_header(text) or _is_nf_value_header(text):
            if result:
                break
            continue
        if any(word in token for word in ("PESOKG", "PESO", "BCALCULO", "ICMS", "FRETE", "CTRCORIGEM", "TRATAMENTO", "QUANTIDADE", "RESUMO", "TOTAL")):
            if result:
                break
            continue
        if _line_is_money(text) or "," in text:
            continue
        match = re.match(r"^\s*(?:(\d{1,3})\s+)?(\d{1,12})\s*$", text)
        if match:
            nf = normalize_nf(match.group(2))
            if nf:
                result.append(nf)
            continue
        if any(word in token for word in ("BENEFICIARIOFINAL", "PAGADOR", "LOCALDEPAGAMENTO", "CODIGOBENEFICIARIO")):
            break
    return result


def _extract_all_nfs(lines: list[str]) -> list[str]:
    result: list[str] = []
    for index, line in enumerate(lines):
        if _is_nf_number_header(line):
            result.extend(_extract_nf_list(lines, index))
    return result


def _extract_nf_from_freight_row(line: str) -> str:
    text = normalize_space(line)
    values = _money_values(text)
    match = re.search(
        r"(?:^|\s)(\d{1,3})\s+(\d{9})(?=(?:\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}))",
        text,
    )
    if match:
        return normalize_nf(match.group(2))
    before_money = text.split(values[0], 1)[0].rstrip() if values else text
    match = re.search(r"(?:^|\s)(\d{1,3})\s+0*(\d{1,12})\s*$", before_money)
    if match:
        return normalize_nf(match.group(2))
    parts = re.split(r"\d{2}/\d{2}/\d{2}", text, maxsplit=1)
    if len(parts) < 2:
        return ""
    prefix = parts[1].split(" - ", 1)[0]
    cnpj = re.search(r"(\d{14})\s*$", prefix)
    if cnpj:
        prefix = prefix[: cnpj.start(1)]
    for raw in reversed(re.findall(r"\d+", prefix)):
        nf = normalize_nf(raw)
        if 1 <= len(nf) <= 12:
            return nf
    return ""


def _extract_freight_fields(line: str) -> dict[str, Any]:
    text = str(line or "")
    matches = list(_MONEY_PATTERN.finditer(text))
    values = [parse_money(match.group(0)) for match in matches]
    result: dict[str, Any] = {
        "valor_nota_fatura": 0.0,
        "peso_fatura": 0.0,
        "icms_fatura": 0.0,
        "comissao_fatura": 0.0,
        "frete_origem_fatura": 0.0,
        "icms_origem_fatura": 0.0,
        "peso_valor_candidatos": [],
    }
    if len(values) < 5:
        return result
    result.update(
        valor_nota_fatura=round(values[0], 2),
        icms_fatura=round(values[1], 2),
        comissao_fatura=round(values[2], 2),
        frete_origem_fatura=round(values[-2], 2),
        icms_origem_fatura=round(values[-1], 2),
    )
    between = text[matches[0].end() : matches[1].start()]
    weight_match = re.search(r"(?<!\d)(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)(?!\d)", between)
    if not weight_match and matches[0].start() > 0 and text[matches[0].start() - 1].isspace():
        weight_match = re.search(r"(?<![\d.,])(\d{1,6}(?:[.,]\d{1,3})?)(?![\d.,])\s*$", text[: matches[0].start()])
    if weight_match:
        result["peso_fatura"] = _parse_weight(weight_match.group(1))
    return result


def _extract_value_before_origin(line: str, origin: str) -> float:
    values = _money_values(line)
    if not values:
        return 0.0
    if origin and origin in line:
        before = line.split(origin, 1)[0]
        local = _money_values(before)
        if local:
            values = local
    return parse_money(values[-3] if len(values) >= 5 else values[-1])


def _extract_frete_terceiro(text: str) -> list[dict[str, Any]]:
    raw = str(text or "").replace("\xa0", " ")
    upper = strip_accents(raw).upper()
    if "SUBCONTRATO" not in upper and "FRETE TERCEIRO PAGADOR" not in upper:
        return []
    lines = [normalize_space(line) for line in raw.splitlines() if normalize_space(line)]
    sub_index = next((i for i, line in enumerate(lines) if _token(line) == "SUBCONTRATO"), None)
    nfs = _extract_all_nfs(lines)
    rows: list[dict[str, Any]] = []
    start = (sub_index + 1) if sub_index is not None else 0
    for index in range(start, min(len(lines), start + 300)):
        line = lines[index]
        token = _token(line)
        if "QUANTIDADEDESUBCONTRATOS" in token or token.startswith("RESUMO"):
            break
        match = re.match(r"^\s*(\d{1,4})\s+0*(\d{5,12})\s+\d{2}/\d{2}/\d{2}\b", line)
        if match:
            cte = normalize_cte(match.group(2))
        else:
            alternate = re.match(r"^\s*([A-Z]{2,8}\s*0*\d{3,12}\s*[-/]\s*\d)(?:\s*/\s*\d+)?\s+\d{2}/\d{2}/\d{2}\b", line, re.I)
            if not alternate:
                continue
            cte = normalize_cte(alternate.group(1))
        joined = line
        continuations: list[str] = []
        if not _extract_origin_cte(joined) or not _extract_nf_from_freight_row(joined):
            for next_line in lines[index + 1 : min(len(lines), index + 3)]:
                if re.match(r"^\s*\d{1,4}\s+0*\d{5,12}\s+\d{2}/\d{2}/\d{2}\b", next_line):
                    break
                next_token = _token(next_line)
                if "QUANTIDADEDESUBCONTRATOS" in next_token or next_token.startswith("RESUMO"):
                    break
                continuations.append(next_line)
                joined = normalize_space(joined + " " + next_line)
                if _extract_origin_cte(joined) and _extract_nf_from_freight_row(joined):
                    break
        origin = _extract_origin_cte(joined)
        nf = _extract_nf_from_freight_row(joined)
        if not nf and continuations:
            match_nf = re.match(r"^\s*(\d{1,3})\s+0*(\d{1,12})(?=\s|$)", normalize_space(" ".join(continuations)))
            if match_nf:
                nf = normalize_nf(match_nf.group(2))
        if not nf and len(rows) < len(nfs):
            nf = nfs[len(rows)]
        fields = _extract_freight_fields(joined)
        value = fields.get("comissao_fatura") or _extract_value_before_origin(joined, origin)
        rows.append(
            {
                "cte": cte,
                "nf": normalize_nf(nf),
                "valor": round(float(value or 0.0), 2),
                "base_cte": origin if _valid_cte(origin) else "",
                "layout": "FRETE TERCEIRO PAGADOR",
                **fields,
            }
        )
    return rows



def _extract_cte_rps_fields(line: str) -> dict[str, Any]:
    text = str(line or "")
    matches = list(_MONEY_PATTERN.finditer(text))
    values = [parse_money(match.group(0)) for match in matches]
    result: dict[str, Any] = {
        "valor_nota_fatura": 0.0,
        "peso_fatura": 0.0,
        "icms_fatura": 0.0,
        "comissao_fatura": 0.0,
        "frete_origem_fatura": 0.0,
        "icms_origem_fatura": 0.0,
        "peso_valor_candidatos": [],
    }
    if not values:
        return result
    result["valor_nota_fatura"] = round(values[0], 2)
    result["comissao_fatura"] = round(values[-1], 2)
    if len(values) >= 3:
        result["icms_fatura"] = round(values[2], 2)
    if len(matches) >= 2:
        between = text[matches[0].end() : matches[1].start()]
        weight_matches = list(re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)(?!\d)", between))
        if weight_matches:
            result["peso_fatura"] = _parse_weight(weight_matches[-1].group(1))
    return result

def _extract_cte_rps(text: str) -> list[dict[str, Any]]:
    raw = str(text or "").replace("\xa0", " ")
    upper = strip_accents(raw).upper()
    if "CT-E / RPS / NFS-E" not in upper and "CTE / RPS / NFSE" not in upper and "CTERPSNFSE" not in _token(raw[:2500]):
        return []
    lines = [normalize_space(line) for line in raw.splitlines() if normalize_space(line)]
    nfs = _extract_all_nfs(lines)
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not re.search(r"\d{2}/\d{2}/\d{2}", line):
            continue
        match = re.match(r"^\s*(\d{1,4})\s+0*(\d{5,12})\s+\d{2}/\d{2}/\d{2}\b", line)
        if match:
            cte = normalize_cte(match.group(2))
        else:
            alternate = re.match(r"^\s*([A-Z]{2,8}\s*0*\d{3,12}\s*[-/]\s*\d)(?:\s*/\s*\d+)?\s+\d{2}/\d{2}/\d{2}\b", line, re.I)
            if not alternate:
                continue
            cte = normalize_cte(alternate.group(1))
        values = _money_values(line)
        fields = _extract_cte_rps_fields(line)
        value = fields.get("comissao_fatura") or (parse_money(values[-1]) if values else 0.0)
        first_money = _MONEY_PATTERN.search(line)
        prefix = line[: first_money.start()] if first_money else line
        after_date = re.split(r"\d{2}/\d{2}/\d{2}", prefix, maxsplit=1)
        nf = ""
        if len(after_date) == 2:
            candidates = []
            for raw_nf in re.findall(r"(?<!\d)0*(\d{1,14})(?!\d)", after_date[1]):
                candidate = normalize_nf(raw_nf)
                if candidate and len(candidate) <= 12 and cte_key(candidate) != cte_key(cte):
                    candidates.append(candidate)
            if candidates:
                nf = candidates[-1]
        if not nf:
            nf = _extract_nf_from_freight_row(line)
        if not nf and len(rows) < len(nfs):
            nf = nfs[len(rows)]
        rows.append(
            {
                "cte": cte,
                "nf": normalize_nf(nf),
                "valor": round(float(value or 0.0), 2),
                "base_cte": "",
                "layout": "CT-e/RPS/NFS-e",
                **fields,
            }
        )
    return rows


def _existing_items(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    source: Any = []
    for key in ("items", "itens", "ctes", "rows"):
        if isinstance(document.get(key), list):
            source = document.get(key)
            break
    result: list[dict[str, Any]] = []
    for item in source or []:
        if not isinstance(item, Mapping):
            continue
        cte = normalize_cte(item.get("subcontrato") or item.get("cte") or item.get("CT-e") or item.get("CT-e fatura"))
        if not cte:
            continue
        value = parse_money(item.get("valor_fatura") or item.get("valor") or item.get("frete") or item.get("Valor fatura") or item.get("Valor CT-e"))
        result.append(
            {
                "cte": cte,
                "nf": normalize_nf(item.get("nf") or item.get("NF") or item.get("nota") or item.get("NF fatura")),
                "valor": value,
                "base_cte": normalize_space(item.get("base_cte") or item.get("ctrc_origem_raw") or ""),
                "layout": normalize_space(item.get("layout") or "DOC_ITEMS"),
                "valor_nota_fatura": parse_money(item.get("valor_nota_fatura") or item.get("N Fiscal R$")),
                "peso_fatura": _parse_weight(item.get("peso_fatura") or item.get("Peso Kg")),
                "comissao_fatura": parse_money(item.get("comissao_fatura") or item.get("Comissão R$") or value),
                "frete_origem_fatura": parse_money(item.get("frete_origem_fatura") or item.get("Frete Origem R$")),
            }
        )
    return result


def _valid_invoice_display(value: Any) -> str:
    normalized = normalize_invoice_number(value)
    if re.fullmatch(r"\d{7}-\d", normalized):
        return normalized
    return ""


def _invoice_from_document(document: Mapping[str, Any], text: str, path: str) -> str:
    """Extrai a fatura do conteúdo antes de aceitar metadados legados.

    O fluxo antigo preenchia ``fatura`` com fragmentos como ``Emiss`` e esse
    valor tinha prioridade sobre o PDF. Agora somente um número canônico
    ``0000000-0`` é aceito e o conteúdo do documento é a fonte principal.
    """
    patterns = (
        r"N\s*[ºO°.]?\s*do\s+Documento\s*:?\s*(0*\d{3,9}\s*[-/]\s*\d)",
        r"FATU?RA\s*(?:N[ºO°.]*)?\s*[:#-]?\s*(?:Emiss[aã]o\s*:\s*\d{2}/\d{2}/\d{4})?\s*(0*\d{3,9}\s*[-/]\s*\d)",
        r"(?m)^\s*(0*\d{3,9}\s*[-/]\s*\d)\s*(?:FATURA|RECIBO|BOLETO)?\s*$",
    )
    for pattern in patterns:
        match = re.search(pattern, str(text or ""), re.I)
        if match:
            value = _valid_invoice_display(match.group(1))
            if value:
                return value

    for key in ("fatura", "Fatura", "numero_fatura", "invoice"):
        value = _valid_invoice_display(document.get(key))
        if value:
            return value

    stem = Path(path).stem
    match = re.search(r"(?:FAT(?:URA|UARA)?\.?|Fat)\s*0*(\d{3,9})\s*[- ]\s*(\d)(?!\d)", stem, re.I)
    if match:
        return f"{(match.group(1).lstrip('0') or '0').zfill(7)}-{match.group(2)}"
    return ""



def _invoice_issue_date(text: str) -> str:
    patterns = (
        r"FATURA\s*(?:N[ºO°.]*)?[^\n\r]{0,80}?Emiss[aã]o\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        r"Emiss[aã]o\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
        r"Data\s+do\s+Documento\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})",
    )
    for pattern in patterns:
        match = re.search(pattern, str(text or ""), re.I)
        if match:
            return match.group(1)
    return ""

def _valid_partner(value: Any) -> str:
    candidate = normalize_space(value)
    if len(candidate) < 5:
        return ""
    token = _token(candidate)
    if not token or token in {"FATURA", "FATURAMENSAL", "RODOVITOR", "EMISS", "EMISSAO"}:
        return ""
    if token.startswith(("FATURA", "FATPDF", "ARQUIVO")) or token.isdigit():
        return ""
    return candidate[:100]


def _partner_from_document(document: Mapping[str, Any], text: str) -> str:
    """Lê o beneficiário do PDF antes do nome de arquivo/metadado legado."""
    invalid = (
        "AGENCIA", "CODIGO DO BENEFICIARIO", "NOSSO NUMERO", "VENCIMENTO",
        "VALOR DO DOCUMENTO", "PROCESSADO POR", "DATA DO DOCUMENTO",
    )
    lines = [normalize_space(line) for line in str(text or "").splitlines() if normalize_space(line)]
    for anchor in ("RECIBO DO PAGADOR",):
        for index, line in enumerate(lines):
            if anchor not in strip_accents(line).upper():
                continue
            for candidate in lines[index + 1 : index + 5]:
                normalized = strip_accents(candidate).upper()
                if "RODOVITOR" in normalized or any(token in normalized for token in invalid):
                    continue
                candidate = re.sub(r"\s+P[áa]g\s*:\s*\d+\s*/\s*\d+.*$", "", candidate, flags=re.I)
                candidate = re.sub(r"\s+\d{3}\s+\d{3,4}(?:[- /]\d+)+.*$", "", candidate)
                value = _valid_partner(candidate)
                if value:
                    return value
    for index, line in enumerate(lines):
        normalized = strip_accents(line).upper()
        if "BENEFICIARIO" not in normalized or "AGENCIA" not in normalized:
            continue
        for candidate in lines[index + 1 : index + 5]:
            candidate_normalized = strip_accents(candidate).upper()
            if "RODOVITOR" in candidate_normalized or any(token in candidate_normalized for token in invalid):
                continue
            candidate = re.sub(r"\s+\d{3}\s+\d{3,4}(?:[- /]\d+)+.*$", "", candidate)
            value = _valid_partner(candidate)
            if value:
                return value
    patterns = (
        r"Transportador\s*[:\-]?\s*([^\n\r]+)",
        r"Cedente\s*[:\-]?\s*([^\n\r]+)",
        r"(?m)^\s*([A-Z0-9À-Ü&. /'\-]{5,100}?)\s+P[áa]g\s*:\s*\d+\s*/\s*\d+",
        r"Benefici[áa]rio[^\n\r]*[\n\r]+\s*([^\n\r]+)",
        r"Benefici[áa]rio\s*[:\-]?\s*([^\n\r]+)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, str(text or ""), re.I):
            value = normalize_space(match.group(1))
            upper = strip_accents(value).upper()
            if not value or any(token in upper for token in invalid):
                continue
            value = re.split(r"\s+-\s+CNPJ\s*:|\s+CNPJ\s*:", value, maxsplit=1, flags=re.I)[0]
            value = _valid_partner(value)
            if value:
                return value

    for key in ("parceiro", "Parceiro", "partner", "nome_parceiro"):
        value = _valid_partner(document.get(key))
        if value:
            return value
    return ""



class InvoiceDocumentParser:
    VERSION = "2.7.0-rc17-estabilizacao"

    def parse(self, document: Mapping[str, Any]) -> InvoiceInputDocument:
        path = normalize_space(document.get("path") or document.get("arquivo") or "")
        text = str(document.get("texto") or document.get("text") or "").replace("\xa0", " ")
        invoice = _invoice_from_document(document, text, path)
        issue_date = _invoice_issue_date(text)
        partner = _partner_from_document(document, text) or "Parceiro não identificado"
        warnings: list[str] = []
        parser_source = "texto_pdf"
        rows = _extract_frete_terceiro(text)
        if not rows:
            rows = _extract_cte_rps(text)
        if not rows:
            rows = _existing_items(document)
            parser_source = "itens_legados" if rows else "sem_itens"
        if not invoice:
            warnings.append("Número da fatura não identificado.")
        if not rows:
            warnings.append("Nenhum item de CT-e foi extraído.")
        text_hash = sha256(text.encode("utf-8", errors="replace")).hexdigest()
        document_hash = stable_hash((invoice_key(invoice), text_hash, len(text)))
        items: list[InvoiceInputItem] = []
        for sequence, row in enumerate(rows, 1):
            cte = normalize_cte(row.get("cte") or row.get("subcontrato"))
            if not cte:
                continue
            nf = normalize_nf(row.get("nf"))
            value = round(parse_money(row.get("valor")), 2)
            items.append(
                InvoiceInputItem(
                    invoice_number=invoice,
                    invoice_key=invoice_key(invoice),
                    partner=partner,
                    cte_number=cte,
                    cte_key=cte_key(cte),
                    nf_number=nf,
                    nf_key=nf_key(nf),
                    billed_value=value,
                    layout=normalize_space(row.get("layout") or "FATURA"),
                    source_file=path,
                    source_document_hash=document_hash,
                    sequence=sequence,
                    base_cte=normalize_space(row.get("base_cte") or ""),
                    weight=round(float(row.get("peso_fatura") or 0.0), 3),
                    merchandise_value=round(parse_money(row.get("valor_nota_fatura")), 2),
                    commission_value=round(parse_money(row.get("comissao_fatura") or value), 2),
                    freight_origin_value=round(parse_money(row.get("frete_origem_fatura")), 2),
                    invoice_issue_date=issue_date,
                    raw=dict(row),
                )
            )
        layout = items[0].layout if items else "NÃO IDENTIFICADO"
        return InvoiceInputDocument(
            invoice_number=invoice,
            invoice_key=invoice_key(invoice),
            partner=partner,
            source_file=path,
            document_hash=document_hash,
            text_hash=text_hash,
            parser_source=parser_source,
            layout=layout,
            items=tuple(items),
            invoice_issue_date=issue_date,
            warnings=tuple(warnings),
        )
