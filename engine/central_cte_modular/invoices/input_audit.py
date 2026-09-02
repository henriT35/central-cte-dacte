from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
import time
from typing import Any, Iterable, Mapping

from .base_linker import InvoiceBaseLinker
from .input_catalog import InvoiceInputCatalog
from .input_models import (
    InvoiceBaseLink,
    InvoiceInputAuditResult,
    InvoiceInputDifference,
    InvoiceInputItem,
    InvoiceInputSnapshot,
)
from .normalization import (
    cte_key,
    invoice_key,
    nf_key,
    normalize_status,
    parse_money,
    stable_hash,
)


class InvoiceInputAuditEngine:
    VERSION = "2.6.67.3"
    MONEY_TOLERANCE = 0.06

    def __init__(
        self,
        catalog: InvoiceInputCatalog | None = None,
        linker: InvoiceBaseLinker | None = None,
    ) -> None:
        self.catalog = catalog or InvoiceInputCatalog()
        self.linker = linker or InvoiceBaseLinker()

    @staticmethod
    def capture(page: Any) -> dict[str, Any]:
        base_candidates: list[str] = []
        for owner in (page, getattr(page, "master", None), getattr(page, "app", None), getattr(page, "controller", None)):
            try:
                value = getattr(owner, "base_path", "")
            except Exception:
                value = ""
            if value:
                base_candidates.append(str(value))
        return {
            "documents": InvoiceInputCatalog.capture_documents(page),
            "base_candidates": base_candidates,
        }

    @staticmethod
    def _legacy_records(page: Any) -> list[Mapping[str, Any]]:
        return [record for record in list(getattr(page, "invoice_detail_records", []) or []) if isinstance(record, Mapping)]

    @staticmethod
    def _legacy_signature(record: Mapping[str, Any]) -> tuple[str, str, str, float]:
        return (
            invoice_key(record.get("Fatura") or record.get("fatura") or ""),
            cte_key(record.get("CT-e fatura") or record.get("CT-e") or record.get("Subcontrato") or ""),
            nf_key(record.get("NF fatura") or record.get("NF") or record.get("Nota Fiscal") or ""),
            round(parse_money(record.get("Valor fatura") or record.get("Valor CT-e") or record.get("valor") or 0.0), 2),
        )

    @staticmethod
    def _item_signature(item: InvoiceInputItem) -> tuple[str, str, str, float]:
        return (item.invoice_key, item.cte_key, item.nf_key, round(item.billed_value, 2))

    @staticmethod
    def _link_key(link: InvoiceBaseLink) -> tuple[str, str, str, float]:
        return (
            invoice_key(link.invoice_number),
            cte_key(link.cte_number),
            nf_key(link.nf_number),
            round(float(link.billed_value or 0.0), 2),
        )

    def _resolve_base_path(self, capture: Mapping[str, Any], default_base: str | Path | None) -> Path | None:
        candidates = list(capture.get("base_candidates") or [])
        if default_base:
            candidates.append(str(default_base))
        for candidate in candidates:
            path = Path(candidate)
            if path.exists():
                return path
        return None

    def _compare_items(
        self,
        modular_items: list[InvoiceInputItem],
        legacy_records: list[Mapping[str, Any]],
    ) -> list[InvoiceInputDifference]:
        differences: list[InvoiceInputDifference] = []
        modular_counter = Counter(self._item_signature(item) for item in modular_items)
        legacy_counter = Counter(self._legacy_signature(record) for record in legacy_records)
        if sum(modular_counter.values()) != sum(legacy_counter.values()):
            differences.append(
                InvoiceInputDifference(
                    severity="CRITICA",
                    scope="LOTE",
                    key="ITENS",
                    field="item_count",
                    modular=sum(modular_counter.values()),
                    legacy=sum(legacy_counter.values()),
                    message="A formação modular de itens não reproduziu a quantidade canônica.",
                )
            )
        for signature in sorted(set(modular_counter) | set(legacy_counter), key=str):
            left = modular_counter.get(signature, 0)
            right = legacy_counter.get(signature, 0)
            if left == right:
                continue
            invoice, cte, nf, value = signature
            differences.append(
                InvoiceInputDifference(
                    severity="CRITICA",
                    scope="ITEM",
                    key=f"FAT={invoice}|CTE={cte}|NF={nf}|VALOR={value:.2f}",
                    field="multiplicity",
                    modular=left,
                    legacy=right,
                    message="Item ausente, excedente ou extraído com CT-e/NF/valor diferente.",
                )
            )
        return differences

    def _compare_links(
        self,
        links: Iterable[InvoiceBaseLink],
        legacy_records: list[Mapping[str, Any]],
    ) -> list[InvoiceInputDifference]:
        differences: list[InvoiceInputDifference] = []
        records_by_signature: dict[tuple[str, str, str, float], list[Mapping[str, Any]]] = defaultdict(list)
        for record in legacy_records:
            records_by_signature[self._legacy_signature(record)].append(record)
        for link in links:
            signature = self._link_key(link)
            records = records_by_signature.get(signature) or []
            if not records:
                continue
            legacy = records[0]
            status = normalize_status(legacy.get("Status final CT-e") or legacy.get("Status CT-e") or legacy.get("status") or "")
            legacy_linked = "FORA DA BASE" not in status and "NAO LOCALIZADO" not in status and "REVISAR BASE" not in status
            modular_linked = link.status == "VINCULADO"
            if legacy_linked != modular_linked:
                differences.append(
                    InvoiceInputDifference(
                        severity="CRITICA",
                        scope="VINCULO_BASE",
                        key=f"FAT={signature[0]}|CTE={signature[1]}|NF={signature[2]}",
                        field="linked",
                        modular={"linked": modular_linked, "mode": link.mode, "base_cte": link.base_cte, "base_nf": link.base_nf},
                        legacy={"linked": legacy_linked, "status": status, "vinculo": legacy.get("Vínculo fatura") or legacy.get("Vinculo fatura") or legacy.get("Fatura Base") or ""},
                        message="O vínculo modular e a decisão canônica sobre existência na base não concordam.",
                    )
                )
                continue
            if modular_linked:
                legacy_base_value = parse_money(legacy.get("Valor base") or legacy.get("Valor Base") or 0.0)
                if legacy_base_value and abs(float(link.base_value or 0.0) - legacy_base_value) > self.MONEY_TOLERANCE:
                    differences.append(
                        InvoiceInputDifference(
                            severity="INFORMATIVA",
                            scope="VINCULO_BASE",
                            key=f"FAT={signature[0]}|CTE={signature[1]}|NF={signature[2]}",
                            field="base_value",
                            modular=round(float(link.base_value or 0.0), 2),
                            legacy=round(legacy_base_value, 2),
                            message="O vínculo existe nos dois motores, mas o valor de referência escolhido difere.",
                        )
                    )
        return differences

    def audit(
        self,
        page: Any,
        capture: Mapping[str, Any],
        *,
        default_base: str | Path | None = None,
    ) -> InvoiceInputAuditResult:
        started = time.perf_counter()
        try:
            snapshot = self.catalog.build(capture.get("documents") or [])
            modular_items = [item for document in snapshot.documents for item in document.items]
            base_path = self._resolve_base_path(capture, default_base)
            if base_path is not None:
                links = self.linker.link(base_path, modular_items)
            else:
                links = tuple(
                    InvoiceBaseLink(
                        invoice_number=item.invoice_number,
                        cte_number=item.cte_number,
                        nf_number=item.nf_number,
                        billed_value=item.billed_value,
                        status="BASE_NAO_CARREGADA",
                        mode="BASE NÃO CARREGADA",
                        confidence="NENHUMA",
                        message="Nenhum caminho válido da base Rodovitor foi localizado.",
                    )
                    for item in modular_items
                )
            elapsed = (time.perf_counter() - started) * 1000.0
            snapshot = replace(snapshot, links=tuple(links), elapsed_ms=elapsed)
            legacy_records = self._legacy_records(page)
            differences = self._compare_items(modular_items, legacy_records)
            differences.extend(self._compare_links(links, legacy_records))
            if snapshot.duplicate_document_count:
                differences.append(
                    InvoiceInputDifference(
                        severity="INFORMATIVA",
                        scope="ENTRADA",
                        key="DOCUMENTOS_DUPLICADOS",
                        field="duplicate_document_count",
                        modular=snapshot.duplicate_document_count,
                        legacy="deduplicação do fluxo canônico",
                        message="Documentos repetidos foram descartados pelo catálogo modular antes da formação dos itens.",
                    )
                )
            if snapshot.parser_error_count:
                differences.append(
                    InvoiceInputDifference(
                        severity="CRITICA",
                        scope="PARSER_PDF",
                        key="ERROS",
                        field="parser_error_count",
                        modular=snapshot.parser_error_count,
                        legacy=0,
                        message="Um ou mais documentos não puderam ser lidos pelo caminho modular.",
                    )
                )
            if snapshot.empty_nf_count:
                differences.append(
                    InvoiceInputDifference(
                        severity="CRITICA",
                        scope="PARSER_PDF",
                        key="NF_VAZIA",
                        field="empty_nf_count",
                        modular=snapshot.empty_nf_count,
                        legacy=sum(1 for record in legacy_records if not nf_key(record.get("NF fatura") or record.get("NF") or "")),
                        message="A formação modular produziu item sem número de NF.",
                    )
                )
            severities = {item.severity for item in differences}
            classification = "CRITICA" if "CRITICA" in severities else ("INFORMATIVA" if differences else "IGUAL")
            return InvoiceInputAuditResult(classification=classification, snapshot=snapshot, differences=tuple(differences))
        except Exception as exc:
            empty = InvoiceInputSnapshot(
                document_count=len(capture.get("documents") or []),
                unique_document_count=0,
                duplicate_document_count=0,
                invoice_count=0,
                item_count=0,
                empty_nf_count=0,
                parser_error_count=1,
                input_fingerprint=stable_hash(("erro", str(exc))),
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
                warnings=(f"{type(exc).__name__}: {exc}",),
            )
            return InvoiceInputAuditResult(classification="ERRO", snapshot=empty, error=f"{type(exc).__name__}: {exc}")
