from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from .document_parser import InvoiceDocumentParser
from .input_models import InvoiceInputDocument, InvoiceInputSnapshot
from .normalization import stable_hash
from .pdf_reader import InvoicePdfTextReader


class InvoiceInputCatalog:
    VERSION = "2.7.0-rc17-estabilizacao"

    def __init__(
        self,
        parser: InvoiceDocumentParser | None = None,
        pdf_reader: InvoicePdfTextReader | None = None,
    ) -> None:
        self.parser = parser or InvoiceDocumentParser()
        self.pdf_reader = pdf_reader or InvoicePdfTextReader()

    @staticmethod
    def capture_documents(page: Any) -> list[dict[str, Any]]:
        captured: list[dict[str, Any]] = []
        full_text_cache = getattr(page, "_modular_invoice_full_text_2672", None) or getattr(page, "_modular_invoice_full_text_2671", {}) or {}
        for raw in list(getattr(page, "invoice_docs", []) or []):
            if isinstance(raw, Mapping):
                # Mantém apenas dados simples. Isso evita que a thread sombra
                # retenha widgets ou objetos do Qt por acidente.
                path_value = raw.get("path") or raw.get("arquivo") or ""
                cached_text = full_text_cache.get(str(path_value)) or full_text_cache.get(Path(str(path_value)).name) or ""
                has_pdf = bool(path_value and Path(str(path_value)).is_file())
                document = {
                    # Quando há PDF disponível, o conteúdo é a fonte oficial.
                    # Metadados e itens legados ficam apenas como fallback para
                    # documentos sem arquivo, evitando "Emiss" e clones.
                    "fatura": "" if has_pdf else (raw.get("fatura") or raw.get("Fatura") or raw.get("numero_fatura") or raw.get("invoice") or ""),
                    "parceiro": "" if has_pdf else (raw.get("parceiro") or raw.get("Parceiro") or raw.get("partner") or raw.get("nome_parceiro") or ""),
                    "path": path_value,
                    "arquivo": raw.get("arquivo") or "",
                    "texto": cached_text or raw.get("texto") or raw.get("text") or "",
                    "items": [] if has_pdf else deepcopy(raw.get("items") or raw.get("itens") or raw.get("ctes") or raw.get("rows") or []),
                }
                captured.append(document)
        return captured

    def _ensure_text(self, document: dict[str, Any]) -> tuple[dict[str, Any], str]:
        text = str(document.get("texto") or document.get("text") or "")
        path = str(document.get("path") or document.get("arquivo") or "")
        if path and Path(path).exists():
            try:
                extracted, backend = self.pdf_reader.read(path)
                if extracted.strip() and len(extracted) >= len(text):
                    enriched = dict(document)
                    enriched["texto"] = extracted
                    return enriched, backend
            except Exception:
                pass
        if text.strip():
            return document, "texto_legado"
        return document, "sem_texto"

    def build(self, documents: Iterable[Mapping[str, Any]]) -> InvoiceInputSnapshot:
        started = time.perf_counter()
        raw_documents = [dict(item) for item in documents if isinstance(item, Mapping)]
        parsed: list[InvoiceInputDocument] = []
        warnings: list[str] = []
        parser_errors = 0
        seen: set[str] = set()
        duplicate_count = 0
        hashes: list[str] = []
        seen_items: set[tuple[str, str, str, float, str]] = set()
        duplicate_item_count = 0

        for index, raw in enumerate(raw_documents, 1):
            try:
                document, text_source = self._ensure_text(raw)
                parsed_document = self.parser.parse(document)
                if text_source not in {"texto_legado", "sem_texto"}:
                    parsed_document = InvoiceInputDocument(
                        **{**parsed_document.__dict__, "parser_source": f"{parsed_document.parser_source}+{text_source}"}
                    )
                if parsed_document.document_hash in seen:
                    duplicate_count += 1
                    continue
                seen.add(parsed_document.document_hash)
                hashes.append(parsed_document.document_hash)
                unique_items = []
                for item in parsed_document.items:
                    item_key = (
                        item.invoice_key,
                        item.cte_key,
                        item.nf_key,
                        round(float(item.billed_value or 0.0), 2),
                        str(item.layout or "").upper(),
                    )
                    if item_key in seen_items:
                        duplicate_item_count += 1
                        continue
                    seen_items.add(item_key)
                    unique_items.append(item)
                if len(unique_items) != len(parsed_document.items):
                    parsed_document = replace(
                        parsed_document,
                        items=tuple(unique_items),
                        warnings=tuple(dict.fromkeys((*parsed_document.warnings, "Itens duplicados foram ignorados pelo vínculo canônico."))),
                    )
                parsed.append(parsed_document)
            except Exception as exc:
                parser_errors += 1
                warnings.append(f"Documento {index}: {type(exc).__name__}: {exc}")

        if duplicate_item_count:
            warnings.append(f"Itens duplicados ignorados: {duplicate_item_count}.")
        items = [item for document in parsed for item in document.items]
        invoices = {document.invoice_key or document.invoice_number for document in parsed if document.invoice_key or document.invoice_number}
        elapsed = (time.perf_counter() - started) * 1000.0
        return InvoiceInputSnapshot(
            document_count=len(raw_documents),
            unique_document_count=len(parsed),
            duplicate_document_count=duplicate_count,
            invoice_count=len(invoices),
            item_count=len(items),
            empty_nf_count=sum(1 for item in items if not item.nf_key),
            parser_error_count=parser_errors,
            documents=tuple(parsed),
            links=(),
            input_fingerprint=stable_hash(sorted(hashes)),
            elapsed_ms=elapsed,
            warnings=tuple(warnings),
        )
