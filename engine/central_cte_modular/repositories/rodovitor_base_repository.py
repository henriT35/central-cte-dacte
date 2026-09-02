from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from ..infrastructure.formatting import only_digits
from ..infrastructure.normalization import norm_location, norm_text, normalize_header, normalize_nf
from .value_parsers import parse_number_br, pick_col, safe_get
from .sswweb_reader import SswWebBaseReader
from .xlsx_reader import StandardLibraryXlsxReader

BASE_ROW_FIELDS = (
    "nf",
    "cte",
    "chave",
    "tipo_doc",
    "tipo_base",
    "cte_origem",
    "ctrc_origem",
    "valor_frete",
    "valor_frete_planilha",
    "valor_frete_origem",
    "fonte_frete",
    "valor_frete_sem_icms",
    "valor_mercadoria",
    "destino_cidade",
    "destino_uf",
    "origem_cidade",
    "origem_uf",
    "cnpj_remetente",
    "cnpj_destinatario",
    "cnpj_pagador",
    "cnpj_recebedor",
)


def classify_base_cte(document_type: Any) -> str:
    text = norm_text(document_type)
    if "COMPLEMENT" in text or "COMPL" in text:
        return "COMPLEMENTAR"
    if "ANUL" in text:
        return "ANULACAO"
    if "SUBSTIT" in text:
        return "SUBSTITUICAO"
    if "DEVOL" in text:
        return "DEVOLUCAO"
    return "NORMAL"


def row_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    """Hash determinístico sem materializar um JSON gigante em memória."""
    digest = hashlib.sha256()
    for row in rows:
        encoded = json.dumps(
            dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def build_nf_index(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        nf = str(item.get("nf") or "")
        if nf:
            index.setdefault(nf, []).append(item)
    return index


class RodovitorBaseRepository:
    """Leitor canônico da base Rodovitor.

    A leitura oficial é feita em streaming: a planilha não é materializada duas
    vezes (linhas brutas + linhas normalizadas). O contrato retornado permanece
    compatível com o motor histórico: ``path``, ``rows`` e ``index``.
    """

    SCHEMA_VERSION = "rodovitor-base-v4-location"

    def __init__(
        self,
        reader: StandardLibraryXlsxReader | None = None,
        ssw_reader: SswWebBaseReader | None = None,
    ) -> None:
        self.reader = reader or StandardLibraryXlsxReader()  # compatibilidade de assinatura; XLSX desativado
        self.ssw_reader = ssw_reader or SswWebBaseReader()

    @staticmethod
    def is_ssw_source(file_path: str | Path) -> bool:
        path = Path(file_path)
        return path.is_dir() or path.suffix.lower() == SswWebBaseReader.SUFFIX

    def source_files(self, file_path: str | Path) -> list[Path]:
        path = Path(file_path)
        if self.is_ssw_source(path):
            return self.ssw_reader.source_files(path)
        raise ValueError("A base XLSX antiga foi desativada. Utilize somente arquivos .sswweb.")

    def load(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        if self.is_ssw_source(path):
            files = self.ssw_reader.source_files(path)
            data = self.load_iter(path, self.ssw_reader.iter_sheet(files))
            data["source_format"] = "sswweb"
            data["source_files"] = [str(item) for item in files]
            return data
        raise ValueError("A base XLSX antiga foi desativada. Utilize somente arquivos .sswweb.")

    def load_sample(self, file_path: str | Path, max_data_rows: int = 500) -> dict[str, Any]:
        path = Path(file_path)
        if self.is_ssw_source(path):
            files = self.ssw_reader.source_files(path)
            data = self.load_rows(
                path,
                self.ssw_reader.read_sheet_sample(files, max_data_rows=max_data_rows),
            )
            data["source_format"] = "sswweb"
            data["source_files"] = [str(item) for item in files]
            return data
        raise ValueError("A base XLSX antiga foi desativada. Utilize somente arquivos .sswweb.")

    def load_rows(self, file_path: str | Path, rows: list[list[Any]]) -> dict[str, Any]:
        return self.load_iter(file_path, iter(rows))

    def load_iter(self, file_path: str | Path, rows: Iterator[list[Any]]) -> dict[str, Any]:
        path = Path(file_path)
        try:
            header = next(rows)
        except StopIteration as exc:
            raise ValueError("Base Rodovitor vazia.") from exc

        columns = self._resolve_columns(header)
        base_rows: list[dict[str, Any]] = []
        nf_index: dict[str, list[dict[str, Any]]] = {}
        skipped_without_nf = 0

        for row in rows:
            item = self._parse_row(row, columns)
            if item is None:
                skipped_without_nf += 1
                continue
            base_rows.append(item)
            nf_index.setdefault(item["nf"], []).append(item)

        if not base_rows:
            raise ValueError("A base Rodovitor não possui registros com NF válida.")

        return {"path": str(path), "rows": base_rows, "index": nf_index}

    def rebuild_from_cached_rows(
        self,
        file_path: str | Path,
        rows: list[dict[str, Any]],
        *,
        fingerprint: str = "",
        skipped_without_nf: int = 0,
    ) -> dict[str, Any]:
        self.validate_rows(rows)
        index = build_nf_index(rows)
        actual_fingerprint = fingerprint or row_fingerprint(rows)
        return {"path": str(Path(file_path)), "rows": rows, "index": index}

    def validate_data(self, data: Mapping[str, Any]) -> dict[str, Any]:
        rows = data.get("rows") if isinstance(data, Mapping) else None
        index = data.get("index") if isinstance(data, Mapping) else None
        if not isinstance(rows, list) or not isinstance(index, dict):
            raise ValueError("Contrato inválido da base: rows/index ausentes.")
        self.validate_rows(rows)
        indexed_count = sum(len(items or []) for items in index.values())
        if indexed_count != len(rows):
            raise ValueError(
                f"Índice da base inconsistente: {indexed_count} referências para {len(rows)} registros."
            )
        for nf, items in index.items():
            for item in items or []:
                if str(item.get("nf") or "") != str(nf):
                    raise ValueError(f"Índice NF inconsistente para {nf}.")
        return {
            "row_count": len(rows),
            "nf_count": len(index),
            "fingerprint": row_fingerprint(rows),
            "schema": self.SCHEMA_VERSION,
        }

    @staticmethod
    def validate_rows(rows: list[dict[str, Any]]) -> None:
        if not rows:
            raise ValueError("A base Rodovitor está vazia.")
        for position, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                raise ValueError(f"Registro {position} da base não é um objeto.")
            missing = [field for field in BASE_ROW_FIELDS if field not in row]
            if missing:
                raise ValueError(
                    f"Registro {position} incompleto. Campos ausentes: {', '.join(missing)}"
                )
            if not str(row.get("nf") or ""):
                raise ValueError(f"Registro {position} sem NF normalizada.")

    @staticmethod
    def _resolve_columns(header: list[Any]) -> dict[str, int | None]:
        index_by_header = {
            normalize_header(header_value): index
            for index, header_value in enumerate(header)
            if str(header_value or "").strip()
        }
        columns = {
            "nf": pick_col(index_by_header, "Numero da Nota Fiscal", "Número da Nota Fiscal", "Nota Fiscal", "NF"),
            "tipo": pick_col(index_by_header, "Tipo do Documento"),
            "cte": pick_col(index_by_header, "Serie/Numero CT-e", "Série/Número CT-e", "Serie/Numero CTe"),
            "chave": pick_col(index_by_header, "Chave CT-e"),
            "frete": pick_col(index_by_header, "Valor do Frete"),
            "frete_sem": pick_col(index_by_header, "Valor do Frete sem ICMS"),
            "frete_origem": pick_col(index_by_header, "Valor do Frete do CTRC Origem", "Valor do Frete CT-e Origem", "Valor Frete Origem"),
            "cte_origem": pick_col(index_by_header, "CTe Origem", "CT-e Origem"),
            "ctrc_origem": pick_col(index_by_header, "CTRC Origem"),
            "mercadoria": pick_col(index_by_header, "Valor da Mercadoria"),
            "cidade_entrega": pick_col(index_by_header, "Cidade de Entrega", "Cidade do Destinatario", "Cidade do Destinatário"),
            "uf_entrega": pick_col(index_by_header, "UF de Entrega", "UF do Destinatario", "UF do Destinatário"),
            "cidade_origem": pick_col(index_by_header, "Cidade origem da prestacao", "Cidade origem da prestação", "Cidade do Remetente"),
            "uf_origem": pick_col(index_by_header, "UF origem da prestacao", "UF origem da prestação", "UF do Remetente"),
            "cnpj_remetente": pick_col(index_by_header, "CNPJ Remetente"),
            "cnpj_destinatario": pick_col(index_by_header, "CNPJ Destinatario", "CNPJ Destinatário"),
            "cnpj_pagador": pick_col(index_by_header, "CNPJ Pagador"),
            "cnpj_recebedor": pick_col(index_by_header, "CNPJ Recebedor"),
        }
        if columns["nf"] is None or columns["frete"] is None:
            raise ValueError("A base precisa ter pelo menos 'Numero da Nota Fiscal' e 'Valor do Frete'.")
        return columns

    @staticmethod
    def _parse_row(row: list[Any], columns: Mapping[str, int | None]) -> dict[str, Any] | None:
        c_nf = columns["nf"]
        c_frete = columns["frete"]
        assert c_nf is not None and c_frete is not None
        nf = normalize_nf(safe_get(row, c_nf))
        if not nf:
            return None

        c_tipo = columns["tipo"]
        document_type = str(safe_get(row, c_tipo)).strip() if c_tipo is not None else ""
        base_type = classify_base_cte(document_type)
        freight_sheet = parse_number_br(safe_get(row, c_frete))
        c_frete_origem = columns["frete_origem"]
        freight_origin = parse_number_br(safe_get(row, c_frete_origem)) if c_frete_origem is not None else 0.0
        c_cte_origem = columns["cte_origem"]
        c_ctrc_origem = columns["ctrc_origem"]
        cte_origin = str(safe_get(row, c_cte_origem)).replace("\xa0", "").strip() if c_cte_origem is not None else ""
        ctrc_origin = str(safe_get(row, c_ctrc_origem)).replace("\xa0", "").strip() if c_ctrc_origem is not None else ""
        use_origin = freight_origin > 0 and (
            freight_sheet <= 1.0 or "SUBC" in norm_text(document_type) or cte_origin or ctrc_origin
        )
        freight_value = freight_origin if use_origin else freight_sheet

        def text(column_name: str) -> str:
            column = columns[column_name]
            return str(safe_get(row, column)).strip() if column is not None else ""

        def clean_text(column_name: str) -> str:
            column = columns[column_name]
            return str(safe_get(row, column)).replace("\xa0", "").strip() if column is not None else ""

        def number(column_name: str) -> float:
            column = columns[column_name]
            return parse_number_br(safe_get(row, column)) if column is not None else 0.0

        def normalized(column_name: str) -> str:
            column = columns[column_name]
            return norm_text(safe_get(row, column)) if column is not None else ""

        def digits(column_name: str) -> str:
            column = columns[column_name]
            return only_digits(safe_get(row, column)) if column is not None else ""

        return {
            "nf": nf,
            "cte": text("cte"),
            "chave": clean_text("chave"),
            "tipo_doc": document_type,
            "tipo_base": base_type,
            "cte_origem": cte_origin,
            "ctrc_origem": ctrc_origin,
            "valor_frete": freight_value,
            "valor_frete_planilha": freight_sheet,
            "valor_frete_origem": freight_origin,
            "fonte_frete": "ORIGEM" if use_origin else "PLANILHA",
            "valor_frete_sem_icms": number("frete_sem"),
            "valor_mercadoria": number("mercadoria"),
            "destino_cidade": norm_location(safe_get(row, columns["cidade_entrega"])) if columns["cidade_entrega"] is not None else "",
            "destino_uf": normalized("uf_entrega"),
            "origem_cidade": norm_location(safe_get(row, columns["cidade_origem"])) if columns["cidade_origem"] is not None else "",
            "origem_uf": normalized("uf_origem"),
            "cnpj_remetente": digits("cnpj_remetente"),
            "cnpj_destinatario": digits("cnpj_destinatario"),
            "cnpj_pagador": digits("cnpj_pagador"),
            "cnpj_recebedor": digits("cnpj_recebedor"),
        }
