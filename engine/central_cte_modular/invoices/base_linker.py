from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any, Iterable

from ..infrastructure.normalization import normalize_header
from ..repositories.value_parsers import parse_number_br, pick_col, safe_get
from ..repositories.sswweb_reader import SswWebBaseReader
from ..repositories.xlsx_reader import StandardLibraryXlsxReader
from .input_models import InvoiceBaseLink, InvoiceInputItem
from .normalization import cte_key, invoice_key, nf_key, normalize_nf, normalize_space, strip_accents


def _valid_cte(value: Any) -> bool:
    key = cte_key(value)
    return bool(key and len(key) >= 4 and len(set(key)) > 1 and key not in {"1111", "11111111", "111111111", "111111114"})


def _is_complementary(row: dict[str, Any]) -> bool:
    text = strip_accents(row.get("tipo_doc") or "").upper()
    return any(token in text for token in ("COMPLEMENT", "COMPL", "CUSTO EXTRA", "CUSTO ADICIONAL"))


def _value_close(left: Any, right: Any, tolerance: float = 0.06) -> bool:
    try:
        return abs(float(left or 0.0) - float(right or 0.0)) <= tolerance
    except Exception:
        return False


def _row_values(row: dict[str, Any], invoice: str) -> list[float]:
    values: list[float] = []
    if invoice and row.get("fatura_exp_key") == invoice:
        values.append(float(row.get("comissao_exp") or 0.0))
    if invoice and row.get("fatura_rec_key") == invoice:
        values.append(float(row.get("comissao_rec") or 0.0))
    if not values:
        values.append(float(row.get("valor") or 0.0))
    return list(dict.fromkeys(round(value, 2) for value in values))


def _row_value(row: dict[str, Any], invoice: str, billed_value: float) -> float:
    values = _row_values(row, invoice)
    return min(values, key=lambda value: abs(value - billed_value)) if values else 0.0


def _row_has_cte(row: dict[str, Any], value: Any) -> bool:
    key = cte_key(value)
    if not key or not _valid_cte(value):
        return False
    return any(cte_key(row.get(field)) == key for field in ("cte", "ctrc", "ctrc_origem", "cte_origem"))


class InvoiceBaseLinker:
    """Vínculo CT-e × NF × base com varredura de memória limitada."""

    VERSION = "2.7.0 RC17 FATURAS SSWWEB EXCLUSIVA"

    def __init__(
        self,
        reader: StandardLibraryXlsxReader | None = None,
        ssw_reader: SswWebBaseReader | None = None,
    ) -> None:
        self.reader = reader or StandardLibraryXlsxReader()  # assinatura legada; não utilizado
        self.ssw_reader = ssw_reader or SswWebBaseReader()
        self.last_base_info: dict[str, Any] = {}

    @staticmethod
    def _prefer_ssw_source(base_path: str | Path) -> Path:
        path = Path(base_path)
        if path.suffix.lower() == SswWebBaseReader.SUFFIX:
            return path.parent if any(path.parent.glob("*.sswweb")) else path
        if path.is_dir() and any(path.glob("*.sswweb")):
            return path
        if path.parent.is_dir() and any(path.parent.glob("*.sswweb")):
            return path.parent
        raise ValueError("A base XLSX antiga foi desativada. Utilize somente arquivos .sswweb.")

    def _iter_base_rows(self, base_path: str | Path):
        path = self._prefer_ssw_source(base_path)
        return self.ssw_reader.iter_sheet(path)

    def _candidate_rows(self, base_path: str | Path, items: Iterable[InvoiceInputItem]) -> list[dict[str, Any]]:
        item_list = list(items)
        wanted_nfs = {item.nf_key for item in item_list if item.nf_key}
        wanted_invoices = {item.invoice_key for item in item_list if item.invoice_key}
        wanted_ctes = {key for item in item_list for key in (item.cte_key, cte_key(item.base_cte)) if key}
        source = self._prefer_ssw_source(base_path)
        source_files = self.ssw_reader.source_files(source)
        rows = self._iter_base_rows(source)
        try:
            header = next(rows)
        except StopIteration:
            return []
        index = {normalize_header(value): position for position, value in enumerate(header) if str(value or "").strip()}
        column = lambda *names: pick_col(index, *names)
        c_nf = column("Numero da Nota Fiscal", "Número da Nota Fiscal", "Nota Fiscal", "NF")
        c_ctrc = column("Serie/Numero CTRC", "Série/Número CTRC")
        c_cte = column("Serie/Numero CT-e", "Série/Número CT-e", "Serie/Numero CTe")
        c_tipo = column("Tipo do Documento")
        c_val = column("Valor do Frete")
        c_val_origin = column("Valor do Frete do CTRC Origem", "Valor do Frete CT-e Origem", "Valor Frete Origem")
        c_comm_exp = column("Valor da Comissao de Expedicao")
        c_comm_rec = column("Valor da Comissao de Recepcao")
        c_proof = column("Compr. de Entrega Escaneado", "Comprovante de Entrega Escaneado", "Comprovante")
        c_issue_date = column("Data de Emissao", "Data de Emissão")
        c_scan_date = column("Data do Escaneamento", "Data Escaneamento")
        c_scan_time = column("Hora do Escaneamento", "Hora Escaneamento")
        c_ctrc_origin = column("CTRC Origem")
        c_cte_origin = column("CTe Origem", "CT-e Origem")
        c_invoice_exp = column("Fatura do Subcon Exp Conferida Opcao 607")
        c_invoice_rec = column("Fatura do Subcon Rec Conferida Opcao 607")
        if c_nf is None:
            return []

        selected: list[dict[str, Any]] = []
        total_records = 0
        for raw in rows:
            total_records += 1
            nf = normalize_nf(safe_get(raw, c_nf))
            nf_key_value = nf_key(nf)
            cte = normalize_space(safe_get(raw, c_cte)) if c_cte is not None else ""
            ctrc = normalize_space(safe_get(raw, c_ctrc)) if c_ctrc is not None else ""
            ctrc_origin = normalize_space(safe_get(raw, c_ctrc_origin)) if c_ctrc_origin is not None else ""
            cte_origin = normalize_space(safe_get(raw, c_cte_origin)) if c_cte_origin is not None else ""
            invoice_exp_raw = safe_get(raw, c_invoice_exp) if c_invoice_exp is not None else ""
            invoice_rec_raw = safe_get(raw, c_invoice_rec) if c_invoice_rec is not None else ""
            invoice_exp = invoice_key(invoice_exp_raw)
            invoice_rec = invoice_key(invoice_rec_raw)
            row_ctes = {cte_key(value) for value in (cte, ctrc, ctrc_origin, cte_origin) if cte_key(value)}
            if nf_key_value not in wanted_nfs and not ({invoice_exp, invoice_rec} & wanted_invoices) and not (row_ctes & wanted_ctes):
                continue
            selected.append(
                {
                    "nf": nf,
                    "nf_key": nf_key_value,
                    "cte": cte,
                    "ctrc": ctrc,
                    "ctrc_origem": ctrc_origin,
                    "cte_origem": cte_origin,
                    "tipo_doc": normalize_space(safe_get(raw, c_tipo)) if c_tipo is not None else "",
                    "valor": round(parse_number_br(safe_get(raw, c_val)), 2) if c_val is not None else 0.0,
                    "valor_origem": round(parse_number_br(safe_get(raw, c_val_origin)), 2) if c_val_origin is not None else 0.0,
                    "comissao_exp": round(parse_number_br(safe_get(raw, c_comm_exp)), 2) if c_comm_exp is not None else 0.0,
                    "comissao_rec": round(parse_number_br(safe_get(raw, c_comm_rec)), 2) if c_comm_rec is not None else 0.0,
                    "dy": normalize_space(safe_get(raw, c_proof)).upper() if c_proof is not None else "",
                    "cte_issue_date": str(safe_get(raw, c_issue_date) or "").strip() if c_issue_date is not None else "",
                    "scan_date": str(safe_get(raw, c_scan_date) or "").strip() if c_scan_date is not None else "",
                    "scan_time": str(safe_get(raw, c_scan_time) or "").strip() if c_scan_time is not None else "",
                    "fatura_exp": normalize_space(invoice_exp_raw),
                    "fatura_rec": normalize_space(invoice_rec_raw),
                    "fatura_exp_key": invoice_exp,
                    "fatura_rec_key": invoice_rec,
                    "fatura_keys": tuple(key for key in (invoice_exp, invoice_rec) if key),
                }
            )
        self.last_base_info = {
            "format": "sswweb",
            "path": str(source),
            "source_files": [str(item) for item in source_files],
            "file_count": len(source_files),
            "total_bytes": sum(item.stat().st_size for item in source_files),
            "row_count": total_records,
            "candidate_row_count": len(selected),
        }
        return selected

    def link(self, base_path: str | Path, items: Iterable[InvoiceInputItem]) -> tuple[InvoiceBaseLink, ...]:
        item_list = list(items)
        if not item_list:
            return ()
        path = self._prefer_ssw_source(base_path)
        if not path.exists():
            return tuple(
                InvoiceBaseLink(
                    invoice_number=item.invoice_number,
                    cte_number=item.cte_number,
                    nf_number=item.nf_number,
                    billed_value=item.billed_value,
                    status="BASE_NAO_CARREGADA",
                    mode="BASE NÃO CARREGADA",
                    confidence="NENHUMA",
                    message=f"Base não encontrada: {path}",
                )
                for item in item_list
            )

        rows = self._candidate_rows(path, item_list)
        by_nf: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_invoice: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_cte: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("nf_key"):
                by_nf[row["nf_key"]].append(row)
            for key in row.get("fatura_keys") or ():
                by_invoice[key].append(row)
            for value in (row.get("cte"), row.get("ctrc"), row.get("ctrc_origem"), row.get("cte_origem")):
                key = cte_key(value)
                if key and _valid_cte(value):
                    by_cte[key].append(row)

        links: list[InvoiceBaseLink] = []
        for item in item_list:
            candidates: list[tuple[int, dict[str, Any], str]] = []
            invoice = item.invoice_key
            nf = item.nf_key
            value = item.billed_value
            layout = re.sub(r"[^A-Z0-9]+", "", strip_accents(item.layout).upper())

            if nf and value:
                complementary = [
                    row for row in by_nf.get(nf, [])
                    if _is_complementary(row) and _value_close(_row_value(row, invoice, value), value)
                ]
                anchors = [anchor for anchor in (item.base_cte, item.cte_number) if _valid_cte(anchor)]
                anchored = [row for row in complementary if any(_row_has_cte(row, anchor) for anchor in anchors)]
                selected = anchored if len(anchored) == 1 else complementary
                normal_same_value = [
                    row for row in by_nf.get(nf, [])
                    if not _is_complementary(row) and _value_close(_row_value(row, invoice, value), value)
                ]
                if len(selected) == 1 and (anchored or not normal_same_value):
                    candidates.append((1000, selected[0], "COMPLEMENTAR_NF_VALOR_PRIORITARIO"))

            invoice_rows = list(by_invoice.get(invoice, [])) if invoice else []
            if invoice_rows:
                scoped = [row for row in invoice_rows if nf and row.get("nf_key") == nf]
                if not nf:
                    anchors = [anchor for anchor in (item.base_cte, item.cte_number if "FRETETERCEIRO" not in layout else "") if _valid_cte(anchor)]
                    scoped = [row for row in invoice_rows if any(_row_has_cte(row, anchor) for anchor in anchors)]
                for row in scoped:
                    expected = _row_value(row, invoice, value)
                    score = 200
                    if nf and row.get("nf_key") == nf:
                        score += 100
                    if _valid_cte(item.base_cte) and _row_has_cte(row, item.base_cte):
                        score += 80
                    if "FRETETERCEIRO" not in layout and _valid_cte(item.cte_number) and _row_has_cte(row, item.cte_number):
                        score += 70
                    if value and _value_close(expected, value):
                        score += 60
                    elif value:
                        score -= min(int(abs(expected - value)), 60)
                    if _is_complementary(row):
                        score += 5
                    candidates.append((score, row, "FATURA_EN_ER"))

            if not candidates:
                anchors: list[tuple[str, str]] = []
                if _valid_cte(item.base_cte):
                    anchors.append((item.base_cte, "CTRC_ORIGEM_EXATO"))
                if "FRETETERCEIRO" not in layout and _valid_cte(item.cte_number):
                    anchors.append((item.cte_number, "CTE_CTRC_EXATO"))
                seen_rows: set[int] = set()
                for anchor, mode in anchors:
                    for row in by_cte.get(cte_key(anchor), []):
                        if id(row) in seen_rows:
                            continue
                        seen_rows.add(id(row))
                        keys = set(row.get("fatura_keys") or ())
                        if keys and invoice not in keys:
                            continue
                        if nf and row.get("nf_key") != nf:
                            continue
                        score = 180 + (80 if nf and row.get("nf_key") == nf else 0)
                        if value and _value_close(_row_value(row, invoice, value), value):
                            score += 30
                        candidates.append((score, row, mode))

            if not candidates and nf:
                nf_rows = list(by_nf.get(nf, []))
                chosen: list[dict[str, Any]] = []
                if len(nf_rows) == 1:
                    chosen = nf_rows
                elif nf_rows:
                    anchors = [anchor for anchor in (item.base_cte, item.cte_number if "FRETETERCEIRO" not in layout else "") if _valid_cte(anchor)]
                    anchored = [row for row in nf_rows if any(_row_has_cte(row, anchor) for anchor in anchors)]
                    if len(anchored) == 1:
                        chosen = anchored
                    else:
                        valued = [row for row in nf_rows if value and _value_close(_row_value(row, invoice, value), value)]
                        if len(valued) == 1:
                            chosen = valued
                for row in chosen:
                    candidates.append((120, row, "NF_GLOBAL_REAPRESENTACAO"))

            if not candidates:
                links.append(
                    InvoiceBaseLink(
                        invoice_number=item.invoice_number,
                        cte_number=item.cte_number,
                        nf_number=item.nf_number,
                        billed_value=value,
                        status="NAO_LOCALIZADO",
                        mode="NÃO LOCALIZADO NA BASE",
                        confidence="NENHUMA",
                        candidate_count=0,
                        message="Nenhuma linha determinística localizada por fatura, NF, CT-e ou valor.",
                    )
                )
                continue

            candidates.sort(key=lambda candidate: candidate[0], reverse=True)
            best_score, best, mode = candidates[0]
            if len(candidates) > 1 and candidates[1][0] == best_score and candidates[1][1] is not best:
                links.append(
                    InvoiceBaseLink(
                        invoice_number=item.invoice_number,
                        cte_number=item.cte_number,
                        nf_number=item.nf_number,
                        billed_value=value,
                        status="AMBIGUO",
                        mode="MATCH AMBÍGUO NA BASE",
                        confidence="BAIXA",
                        candidate_count=len(candidates),
                        message="Dois ou mais candidatos receberam a mesma pontuação máxima.",
                    )
                )
                continue

            base_value = _row_value(best, invoice, value)
            origin_freight = round(float(best.get("valor_origem") or 0.0), 2)
            row_freight = round(float(best.get("valor") or 0.0), 2)
            base_freight_value = origin_freight if origin_freight > 0.0 else row_freight
            base_freight_source = (
                "Valor do Frete do CTRC Origem"
                if origin_freight > 0.0
                else "Valor do Frete da linha vinculada" if row_freight > 0.0
                else "NÃO INFORMADO / ZERO"
            )
            links.append(
                InvoiceBaseLink(
                    invoice_number=item.invoice_number,
                    cte_number=item.cte_number,
                    nf_number=item.nf_number,
                    billed_value=value,
                    status="VINCULADO",
                    mode=mode,
                    confidence="ALTA" if best_score >= 200 else "MEDIA",
                    base_nf=best.get("nf") or "",
                    base_cte=best.get("cte") or best.get("ctrc") or best.get("ctrc_origem") or best.get("cte_origem") or "",
                    base_value=base_value,
                    base_invoice=best.get("fatura_exp") or best.get("fatura_rec") or "",
                    proof_status=best.get("dy") or "",
                    document_type=best.get("tipo_doc") or "",
                    candidate_count=len(candidates),
                    cte_issue_date=best.get("cte_issue_date") or "",
                    scan_date=best.get("scan_date") or "",
                    scan_time=best.get("scan_time") or "",
                    message="Vínculo modular independente localizado.",
                    base_freight_value=base_freight_value,
                    base_freight_source=base_freight_source,
                )
            )
        return tuple(links)
