from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
import json
import time
from typing import Any, Iterable, Mapping

from .models import (
    InvoiceShadowDifference,
    InvoiceShadowItem,
    InvoiceShadowResult,
    InvoiceShadowSnapshot,
    InvoiceShadowSummary,
)
from .normalization import (
    canonical_invoice_status,
    cte_key,
    invoice_key,
    is_problem_status,
    nf_key,
    normalize_cte,
    normalize_invoice_number,
    normalize_nf,
    normalize_space,
    normalize_status,
    parse_money,
    stable_hash,
    status_equal,
)


class InvoiceShadowEngine:
    """Constrói um read model de faturas sem modificar o estado oficial.

    O motor modular usa os registros detalhados produzidos pelo fluxo canônico
    legado e reconstrói, de forma independente, agrupamentos, totais, status e
    detecção de clones. A comparação é feita contra as linhas-resumo e o mapa
    de detalhes usados pela interface antiga.
    """

    VERSION = "2.6.67.1"
    MONEY_TOLERANCE = 0.01

    RECORD_KEYS = {
        "invoice": ("Fatura", "fatura", "Número da fatura", "Numero da fatura"),
        "partner": ("Parceiro", "parceiro", "Nome do parceiro"),
        "cte": ("CT-e fatura", "CT-e", "cte", "Subcontrato"),
        "nf": ("NF fatura", "NF", "nf", "Nota Fiscal"),
        "value": ("Valor fatura", "Valor CT-e", "valor", "Valor"),
        "blocked": ("Valor não pagar", "Valor nao pagar", "valor_nao_pagar"),
        "status": ("Status final CT-e", "Status CT-e", "Status final", "status"),
        "proof": ("Comprovante", "comprovante", "DY"),
        "base_link": ("Vínculo fatura", "Vinculo fatura", "Fatura Base"),
        "file": ("Arquivo fatura", "arquivo", "path"),
        "sequence": ("Sequência item", "Sequencia item", "sequencia"),
    }

    @staticmethod
    def _first(mapping: Mapping[str, Any], keys: Iterable[str], default: Any = "") -> Any:
        for key in keys:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
        return default

    def capture_input(self, page: Any) -> dict[str, Any]:
        documents = list(getattr(page, "invoice_docs", []) or [])
        invoice_numbers: list[str] = []
        fingerprints: list[str] = []
        duplicate_counter: Counter[str] = Counter()
        for index, document in enumerate(documents):
            if isinstance(document, Mapping):
                invoice = ""
                for key in ("fatura", "Fatura", "numero_fatura", "invoice"):
                    invoice = normalize_invoice_number(document.get(key))
                    if invoice:
                        break
                path = normalize_space(document.get("path") or document.get("arquivo") or "")
                text = str(document.get("texto") or document.get("text") or "")
                items = document.get("items") or document.get("itens") or document.get("ctes") or []
                item_count = len(items) if isinstance(items, list) else 0
                fp = stable_hash((invoice, path, len(text), text[:256], item_count))
            else:
                invoice = ""
                fp = stable_hash((index, type(document).__name__, str(document)[:256]))
            if invoice:
                invoice_numbers.append(invoice)
            fingerprints.append(fp)
            duplicate_counter[fp] += 1
        return {
            "document_count": len(documents),
            "invoice_numbers": sorted(set(invoice_numbers)),
            "duplicate_document_count": sum(count - 1 for count in duplicate_counter.values() if count > 1),
            "input_fingerprint": stable_hash(sorted(fingerprints)),
        }

    def _item_from_record(self, record: Mapping[str, Any], index: int) -> InvoiceShadowItem:
        invoice = normalize_invoice_number(self._first(record, self.RECORD_KEYS["invoice"]))
        partner = normalize_space(self._first(record, self.RECORD_KEYS["partner"]))
        cte = normalize_cte(self._first(record, self.RECORD_KEYS["cte"]))
        nf = normalize_nf(self._first(record, self.RECORD_KEYS["nf"]))
        billed = parse_money(self._first(record, self.RECORD_KEYS["value"], 0.0))
        blocked = parse_money(self._first(record, self.RECORD_KEYS["blocked"], 0.0))
        status = normalize_space(self._first(record, self.RECORD_KEYS["status"]))
        problem = is_problem_status(status)
        if problem and blocked <= 0.0 and billed > 0.0:
            # O legado canônico bloqueia o valor integral do item problemático.
            # Esse fallback também torna visível qualquer registro incompleto.
            blocked = billed
        if not problem:
            blocked = 0.0
        source_file = normalize_space(self._first(record, self.RECORD_KEYS["file"]))
        sequence = normalize_space(self._first(record, self.RECORD_KEYS["sequence"], index + 1))
        fingerprint = stable_hash((
            invoice_key(invoice), cte_key(cte), nf_key(nf), round(billed, 2),
            round(blocked, 2), normalize_status(status),
        ))
        return InvoiceShadowItem(
            invoice_number=invoice,
            invoice_key=invoice_key(invoice),
            partner=partner,
            cte_number=cte,
            cte_key=cte_key(cte),
            nf_number=nf,
            nf_key=nf_key(nf),
            billed_value=round(billed, 2),
            blocked_value=round(blocked, 2),
            status=status,
            is_problem=problem,
            proof_status=normalize_space(self._first(record, self.RECORD_KEYS["proof"])),
            base_link=normalize_space(self._first(record, self.RECORD_KEYS["base_link"])),
            source_file=source_file,
            sequence=sequence,
            fingerprint=fingerprint,
        )

    def _item_from_detail_row(self, invoice: str, partner: str, row: Any, index: int) -> InvoiceShadowItem | None:
        if not isinstance(row, (list, tuple)):
            return None
        values = list(row) + [""] * 10
        status = normalize_space(values[8])
        billed = parse_money(values[2])
        problem = is_problem_status(status)
        blocked = billed if problem else 0.0
        cte = normalize_cte(values[0])
        nf = normalize_nf(values[1])
        fingerprint = stable_hash((invoice_key(invoice), cte_key(cte), nf_key(nf), billed, blocked, normalize_status(status)))
        return InvoiceShadowItem(
            invoice_number=normalize_invoice_number(invoice),
            invoice_key=invoice_key(invoice),
            partner=normalize_space(partner),
            cte_number=cte,
            cte_key=cte_key(cte),
            nf_number=nf,
            nf_key=nf_key(nf),
            billed_value=billed,
            blocked_value=blocked,
            status=status,
            is_problem=problem,
            proof_status=normalize_space(values[6]),
            base_link=normalize_space(values[5]),
            sequence=str(index + 1),
            fingerprint=fingerprint,
        )

    def _summaries_from_items(self, items: list[InvoiceShadowItem]) -> tuple[list[InvoiceShadowSummary], list[InvoiceShadowItem], int]:
        grouped: dict[str, list[InvoiceShadowItem]] = defaultdict(list)
        display_number: dict[str, str] = {}
        partner_by_invoice: dict[str, str] = {}
        for item in items:
            key = item.invoice_key or item.invoice_number or "SEM_FATURA"
            grouped[key].append(item)
            display_number.setdefault(key, item.invoice_number or key)
            if item.partner and key not in partner_by_invoice:
                partner_by_invoice[key] = item.partner

        deduplicated_items: list[InvoiceShadowItem] = []
        summaries: list[InvoiceShadowSummary] = []
        total_clones = 0
        for key in sorted(grouped, key=lambda value: (value == "SEM_FATURA", value)):
            invoice_items = grouped[key]
            seen: set[str] = set()
            unique: list[InvoiceShadowItem] = []
            clones = 0
            for item in invoice_items:
                if item.fingerprint in seen:
                    clones += 1
                    continue
                seen.add(item.fingerprint)
                unique.append(item)
            total_clones += clones
            deduplicated_items.extend(unique)
            ok_count = sum(1 for item in unique if not item.is_problem)
            problem_count = len(unique) - ok_count
            total_value = round(sum(item.billed_value for item in unique), 2)
            blocked_value = round(sum(item.blocked_value for item in unique if item.is_problem), 2)
            blocked_value = min(blocked_value, total_value) if total_value >= 0 else blocked_value
            status = canonical_invoice_status(len(unique), ok_count, problem_count)
            summaries.append(InvoiceShadowSummary(
                invoice_number=display_number[key],
                invoice_key="" if key == "SEM_FATURA" else key,
                partner=partner_by_invoice.get(key, "Parceiro não identificado"),
                item_count=len(unique),
                ok_count=ok_count,
                problem_count=problem_count,
                total_value=total_value,
                blocked_value=blocked_value,
                payable_value=round(max(total_value - blocked_value, 0.0), 2),
                status=status,
                empty_nf_count=sum(1 for item in unique if not item.nf_key),
                clone_count=clones,
                item_fingerprints=tuple(item.fingerprint for item in unique),
            ))
        return summaries, deduplicated_items, total_clones

    def build_modular_snapshot(self, page: Any, input_state: Mapping[str, Any] | None = None) -> InvoiceShadowSnapshot:
        records = list(getattr(page, "invoice_detail_records", []) or [])
        items: list[InvoiceShadowItem] = []
        warnings: list[str] = []
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                warnings.append(f"Registro detalhado {index + 1} ignorado: tipo {type(record).__name__}.")
                continue
            items.append(self._item_from_record(record, index))

        if not items:
            detail_map = getattr(page, "detail_rows_by_invoice", {}) or {}
            partner_map: dict[str, str] = {}
            for row in list(getattr(page, "invoice_rows", []) or []):
                if isinstance(row, (list, tuple)) and row:
                    partner_map[normalize_invoice_number(row[0])] = normalize_space(row[1] if len(row) > 1 else "")
            if isinstance(detail_map, Mapping):
                for invoice, rows in detail_map.items():
                    normalized_invoice = normalize_invoice_number(invoice)
                    partner = partner_map.get(normalized_invoice, "")
                    for index, row in enumerate(rows or []):
                        item = self._item_from_detail_row(normalized_invoice, partner, row, index)
                        if item is not None:
                            items.append(item)
            if items:
                warnings.append("Snapshot modular reconstruído pelo mapa de detalhes porque invoice_detail_records estava vazio.")

        summaries, unique_items, clones = self._summaries_from_items(items)
        input_data = dict(input_state or self.capture_input(page))
        total = round(sum(invoice.total_value for invoice in summaries), 2)
        blocked = round(sum(invoice.blocked_value for invoice in summaries), 2)
        return InvoiceShadowSnapshot(
            source="MODULAR_SHADOW",
            document_count=int(input_data.get("document_count") or 0),
            invoice_count=len(summaries),
            item_count=len(unique_items),
            clone_count=clones,
            empty_nf_count=sum(invoice.empty_nf_count for invoice in summaries),
            total_value=total,
            blocked_value=blocked,
            payable_value=round(max(total - blocked, 0.0), 2),
            invoices=tuple(summaries),
            items=tuple(unique_items),
            document_invoice_numbers=tuple(input_data.get("invoice_numbers") or ()),
            input_fingerprint=str(input_data.get("input_fingerprint") or ""),
            warnings=tuple(warnings),
        )

    def build_legacy_snapshot(self, page: Any, input_state: Mapping[str, Any] | None = None) -> InvoiceShadowSnapshot:
        rows = list(getattr(page, "invoice_rows", []) or [])
        detail_map = getattr(page, "detail_rows_by_invoice", {}) or {}
        summaries: list[InvoiceShadowSummary] = []
        items: list[InvoiceShadowItem] = []
        warnings: list[str] = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, (list, tuple)) or not row:
                warnings.append(f"Linha-resumo legada {row_index + 1} ignorada.")
                continue
            values = list(row) + [""] * 10
            invoice = normalize_invoice_number(values[0])
            partner = normalize_space(values[1])
            item_count = int(parse_money(values[2]))
            ok_count = int(parse_money(values[3]))
            problem_count = int(parse_money(values[4]))
            total_value = parse_money(values[5])
            blocked_value = parse_money(values[6])
            status = normalize_space(values[9])
            invoice_rows = []
            if isinstance(detail_map, Mapping):
                invoice_rows = list(detail_map.get(values[0]) or detail_map.get(invoice) or [])
            fingerprints: list[str] = []
            empty_nf = 0
            for detail_index, detail in enumerate(invoice_rows):
                item = self._item_from_detail_row(invoice, partner, detail, detail_index)
                if item is None:
                    continue
                items.append(item)
                fingerprints.append(item.fingerprint)
                if not item.nf_key:
                    empty_nf += 1
            summaries.append(InvoiceShadowSummary(
                invoice_number=invoice,
                invoice_key=invoice_key(invoice),
                partner=partner,
                item_count=item_count,
                ok_count=ok_count,
                problem_count=problem_count,
                total_value=total_value,
                blocked_value=blocked_value,
                payable_value=round(max(total_value - blocked_value, 0.0), 2),
                status=status,
                empty_nf_count=empty_nf,
                clone_count=max(len(fingerprints) - len(set(fingerprints)), 0),
                item_fingerprints=tuple(fingerprints),
            ))
        input_data = dict(input_state or self.capture_input(page))
        total = round(sum(invoice.total_value for invoice in summaries), 2)
        blocked = round(sum(invoice.blocked_value for invoice in summaries), 2)
        clone_count = sum(invoice.clone_count for invoice in summaries)
        return InvoiceShadowSnapshot(
            source="LEGACY_OFFICIAL",
            document_count=int(input_data.get("document_count") or 0),
            invoice_count=len(summaries),
            item_count=sum(invoice.item_count for invoice in summaries),
            clone_count=clone_count,
            empty_nf_count=sum(invoice.empty_nf_count for invoice in summaries),
            total_value=total,
            blocked_value=blocked,
            payable_value=round(max(total - blocked, 0.0), 2),
            invoices=tuple(summaries),
            items=tuple(items),
            document_invoice_numbers=tuple(input_data.get("invoice_numbers") or ()),
            input_fingerprint=str(input_data.get("input_fingerprint") or ""),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _invoice_map(snapshot: InvoiceShadowSnapshot) -> dict[str, InvoiceShadowSummary]:
        return {(item.invoice_key or item.invoice_number): item for item in snapshot.invoices}

    def compare(self, modular: InvoiceShadowSnapshot, legacy: InvoiceShadowSnapshot) -> tuple[InvoiceShadowDifference, ...]:
        differences: list[InvoiceShadowDifference] = []

        def add(severity: str, scope: str, key: str, field: str, mod: Any, leg: Any, message: str) -> None:
            differences.append(InvoiceShadowDifference(severity, scope, key, field, mod, leg, message))

        for field in ("invoice_count", "item_count", "total_value", "blocked_value", "payable_value"):
            mod = getattr(modular, field)
            leg = getattr(legacy, field)
            if field.endswith("value"):
                equal = abs(float(mod) - float(leg)) <= self.MONEY_TOLERANCE
            else:
                equal = mod == leg
            if not equal:
                add("CRITICA", "LOTE", "LOTE", field, mod, leg, f"Divergência no total do lote: {field}.")

        if modular.clone_count:
            add("CRITICA", "LOTE", "LOTE", "clone_count", modular.clone_count, legacy.clone_count, "O read model modular detectou registros clonados.")
        if modular.empty_nf_count:
            add("CRITICA", "LOTE", "LOTE", "empty_nf_count", modular.empty_nf_count, legacy.empty_nf_count, "Existem itens sem NF no resultado canônico.")

        modular_map = self._invoice_map(modular)
        legacy_map = self._invoice_map(legacy)
        missing_modular = sorted(set(legacy_map) - set(modular_map))
        missing_legacy = sorted(set(modular_map) - set(legacy_map))
        for key in missing_modular:
            add("CRITICA", "FATURA", key, "presenca", "AUSENTE", "PRESENTE", "Fatura presente no legado e ausente no read model modular.")
        for key in missing_legacy:
            add("CRITICA", "FATURA", key, "presenca", "PRESENTE", "AUSENTE", "Fatura presente no modular e ausente no resumo legado.")

        for key in sorted(set(modular_map) & set(legacy_map)):
            mod = modular_map[key]
            leg = legacy_map[key]
            for field in ("item_count", "ok_count", "problem_count", "empty_nf_count", "clone_count"):
                if getattr(mod, field) != getattr(leg, field):
                    add("CRITICA", "FATURA", key, field, getattr(mod, field), getattr(leg, field), f"Fatura {mod.invoice_number}: {field} divergente.")
            for field in ("total_value", "blocked_value", "payable_value"):
                if abs(float(getattr(mod, field)) - float(getattr(leg, field))) > self.MONEY_TOLERANCE:
                    add("CRITICA", "FATURA", key, field, getattr(mod, field), getattr(leg, field), f"Fatura {mod.invoice_number}: valor divergente em {field}.")
            if not status_equal(mod.status, leg.status):
                add("CRITICA", "FATURA", key, "status", mod.status, leg.status, f"Fatura {mod.invoice_number}: decisão financeira divergente.")
            if normalize_space(mod.partner).upper() != normalize_space(leg.partner).upper():
                add("INFORMATIVA", "FATURA", key, "partner", mod.partner, leg.partner, f"Fatura {mod.invoice_number}: nome do parceiro diverge apenas na apresentação.")
            if leg.item_fingerprints and set(mod.item_fingerprints) != set(leg.item_fingerprints):
                add("CRITICA", "FATURA", key, "item_fingerprints", len(set(mod.item_fingerprints)), len(set(leg.item_fingerprints)), f"Fatura {mod.invoice_number}: conjunto CT-e/NF/valor/status diverge entre registros e mapa de detalhes.")

        if modular.document_count and modular.document_count != modular.invoice_count:
            add("INFORMATIVA", "ENTRADA", "DOCUMENTOS", "document_count_vs_invoice_count", modular.document_count, modular.invoice_count, "Quantidade de PDFs/documentos difere da quantidade de faturas reconstruídas.")
        return tuple(differences)

    def evaluate_golden_contract(self, snapshot: InvoiceShadowSnapshot, contract_path: Path | None) -> dict[str, Any]:
        if contract_path is None or not Path(contract_path).exists():
            return {"status": "CONTRATO_NAO_ENCONTRADO", "checks": []}
        try:
            contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
            expected = contract.get("expected") or {}
        except Exception as exc:
            return {"status": "ERRO_CONTRATO", "error": str(exc), "checks": []}
        actual = {
            "invoice_count": snapshot.invoice_count,
            "cte_count": snapshot.item_count,
            "clone_count": snapshot.clone_count,
            "empty_nf_count": snapshot.empty_nf_count,
            "total_brl": f"{snapshot.total_value:.2f}",
        }
        checks = []
        for key, expected_value in expected.items():
            actual_value = actual.get(key)
            equal = str(actual_value) == str(expected_value)
            checks.append({"field": key, "expected": expected_value, "actual": actual_value, "equal": equal})
        # Um lote parcial não falha o contrato; apenas não está apto a homologá-lo.
        eligible = snapshot.invoice_count == int(expected.get("invoice_count") or -1)
        if not eligible:
            status = "LOTE_DIFERENTE_DO_DOURADO"
        else:
            status = "APROVADO" if all(item["equal"] for item in checks) else "DIVERGENTE"
        return {"status": status, "eligible": eligible, "checks": checks}

    def audit_page(self, page: Any, *, input_state: Mapping[str, Any] | None = None, contract_path: Path | None = None) -> InvoiceShadowResult:
        started = time.perf_counter()
        modular = self.build_modular_snapshot(page, input_state)
        legacy = self.build_legacy_snapshot(page, input_state)
        differences = self.compare(modular, legacy)
        if modular.invoice_count == 0 and legacy.invoice_count == 0:
            classification = "SEM_DADOS"
        elif any(item.severity == "CRITICA" for item in differences):
            classification = "CRITICA"
        elif differences:
            classification = "INFORMATIVA"
        else:
            classification = "IGUAL"
        golden = self.evaluate_golden_contract(modular, contract_path)
        return InvoiceShadowResult(
            classification=classification,
            modular=modular,
            legacy=legacy,
            differences=differences,
            golden_batch=golden,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
        )


class InvoiceShadowService:
    def __init__(self, engine: InvoiceShadowEngine, reporter: Any, contract_path: Path | None = None) -> None:
        self.engine = engine
        self.reporter = reporter
        self.contract_path = Path(contract_path) if contract_path is not None else None
        self._last_fingerprint = ""
        self._last_result: InvoiceShadowResult | None = None

    def capture_input(self, page: Any) -> dict[str, Any]:
        return self.engine.capture_input(page)

    def audit(self, page: Any, *, input_state: Mapping[str, Any] | None = None, consumer: str = "process_invoices") -> InvoiceShadowResult:
        try:
            result = self.engine.audit_page(page, input_state=input_state, contract_path=self.contract_path)
        except Exception as exc:
            empty = InvoiceShadowSnapshot("MODULAR_SHADOW", 0, 0, 0, 0, 0, 0.0, 0.0, 0.0)
            result = InvoiceShadowResult("ERRO", empty, replace(empty, source="LEGACY_OFFICIAL"), error=str(exc))
        fingerprint = stable_hash((
            result.modular.input_fingerprint,
            result.modular.invoice_count,
            result.modular.item_count,
            result.modular.total_value,
            result.modular.blocked_value,
            result.classification,
            [(d.scope, d.key, d.field, d.modular, d.legacy) for d in result.differences],
        ))
        self._last_result = result
        # O relatório completo é regravado sempre; o JSONL evita repetição da
        # mesma fotografia quando processo e exportação consultam o mesmo lote.
        append_history = fingerprint != self._last_fingerprint
        self._last_fingerprint = fingerprint
        self.reporter.write(result, consumer=consumer, append_history=append_history)
        return result

    def snapshot(self) -> dict[str, Any]:
        if self._last_result is None:
            return {"version": self.engine.VERSION, "classification": "NAO_EXECUTADO"}
        return self._last_result.to_dict(include_items=False)
