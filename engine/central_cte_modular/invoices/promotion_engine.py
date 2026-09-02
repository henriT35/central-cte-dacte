from __future__ import annotations

from collections import Counter, defaultdict, deque
from copy import deepcopy
import re
import time
from typing import Any, Iterable, Mapping

from .decision_models import InvoiceDecisionAuditResult, InvoiceItemDecision
from .input_models import InvoiceInputAuditResult
from .normalization import cte_key, invoice_key, nf_key, parse_money, strip_accents
from .promotion_models import InvoicePromotionResult


_ALLOWED_CODES = {"OK", "OK_COMPLEMENTAR", "SEM_COMPROVANTE", "FORA_DA_BASE", "BASE_AMBIGUA", "BASE_NAO_CARREGADA", "NF_IGNORADA"}


def _norm(value: Any) -> str:
    return " ".join(strip_accents(value).upper().split())


def _money(value: Any) -> str:
    number = parse_money(value)
    formatted = f"{number:,.2f}"
    return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _record_signature(record: Mapping[str, Any]) -> tuple[str, str, str, float]:
    return (
        invoice_key(record.get("Fatura") or record.get("fatura") or ""),
        cte_key(record.get("CT-e fatura") or record.get("CT-e") or record.get("Subcontrato") or ""),
        nf_key(record.get("NF fatura") or record.get("NF") or record.get("NF base") or ""),
        round(parse_money(record.get("Valor fatura") or record.get("Valor CT-e") or record.get("valor") or 0.0), 2),
    )


def _decision_signature(decision: InvoiceItemDecision) -> tuple[str, str, str, float]:
    return (
        decision.invoice_key,
        decision.cte_key,
        decision.nf_key,
        round(float(decision.billed_value or 0.0), 2),
    )


def _difference_invoice(key: Any) -> str:
    text = str(key or "")
    match = re.search(r"(?:^|\|)FAT=([^|]+)", text, flags=re.IGNORECASE)
    return invoice_key(match.group(1)) if match else ""


def _is_problem(record: Mapping[str, Any]) -> bool:
    if record.get("Financeiro contabilizado") is False:
        return False
    status = _norm(record.get("Status final CT-e") or record.get("Status CT-e") or "")
    if status in {"OK", "OK COMPLEMENTAR", "NF IGNORADA - VINCULO CONFIAVEL EM OUTRA NF"}:
        return False
    return any(token in status for token in ("SEM COMPROVANTE", "FORA DA BASE", "PROBLEMA INTERNO", "DIVERG", "REVISAR"))



def _financial_kind(record: Mapping[str, Any]) -> str:
    if record.get("Financeiro contabilizado") is False:
        return "NAO_CONTABILIZADO"
    code = _norm(record.get("Código decisão modular") or record.get("Código decisão") or "")
    if code in {"SEM_COMPROVANTE", "FORA_DA_BASE"}:
        return "FUTURO"
    if code in {"OK", "OK_COMPLEMENTAR", "NF_IGNORADA"}:
        return "OK"
    status = _norm(record.get("Status final CT-e") or record.get("Status CT-e") or "")
    if status in {"OK", "OK COMPLEMENTAR", "NF IGNORADA - VINCULO CONFIAVEL EM OUTRA NF"}:
        return "OK"
    if "SEM COMPROVANTE" in status:
        return "FUTURO"
    return "INTERNO"

def _detail_row(record: Mapping[str, Any]) -> tuple[Any, ...]:
    scan = " ".join(
        part for part in (
            str(record.get("Data escaneamento") or "").strip(),
            str(record.get("Hora escaneamento") or "").strip(),
        ) if part
    ) or "-"
    return (
        record.get("CT-e fatura") or record.get("CT-e") or "-",
        record.get("NF fatura") or record.get("NF") or "-",
        record.get("Valor fatura") or 0.0,
        record.get("Valor base") or "-",
        record.get("Status valor") or "OK",
        record.get("Fatura Base") or "-",
        record.get("Comprovante") or "-",
        scan,
        record.get("Status final CT-e") or record.get("Status CT-e") or "-",
        record.get("Motivo") or "-",
    )


def _append_text(original: Any, extra: str) -> str:
    pieces = []
    for part in (str(original or "").strip(), str(extra or "").strip()):
        if part and part != "-" and part not in pieces:
            pieces.append(part)
    return " | ".join(pieces) if pieces else "-"


def _apply_decision(record: Mapping[str, Any], decision: InvoiceItemDecision) -> dict[str, Any]:
    promoted = deepcopy(dict(record))
    status = {
        "OK": "OK",
        "OK_COMPLEMENTAR": "OK COMPLEMENTAR",
        "SEM_COMPROVANTE": "SEM COMPROVANTE",
        "FORA_DA_BASE": "FORA DA BASE - AUDITORIA",
        "BASE_AMBIGUA": "PROBLEMA INTERNO - BASE AMBÍGUA",
        "BASE_NAO_CARREGADA": "PROBLEMA INTERNO - BASE NÃO CARREGADA",
        "NF_IGNORADA": "NF IGNORADA - VÍNCULO CONFIÁVEL EM OUTRA NF",
    }[decision.decision_code]
    proof = {
        "OK": "COMPROVANTE OK",
        "OK_COMPLEMENTAR": "NÃO EXIGIDO - COMPLEMENTAR",
        "SEM_COMPROVANTE": "SEM COMPROVANTE",
        "FORA_DA_BASE": "-",
        "BASE_AMBIGUA": "NÃO VERIFICADO - PROBLEMA INTERNO",
        "BASE_NAO_CARREGADA": "NÃO VERIFICADO - PROBLEMA INTERNO",
        "NF_IGNORADA": "NÃO CONTABILIZADO - NF IGNORADA",
    }[decision.decision_code]
    divergence = {
        "OK": "-",
        "OK_COMPLEMENTAR": "-",
        "SEM_COMPROVANTE": "Comprovante",
        "FORA_DA_BASE": "Base (informativo)",
        "BASE_AMBIGUA": "Problema interno / base ambígua",
        "BASE_NAO_CARREGADA": "Problema interno / base não carregada",
        "NF_IGNORADA": "NF ignorada",
    }[decision.decision_code]
    ignored = ", ".join(decision.ignored_nf_numbers)
    warnings = " | ".join(decision.warnings)

    promoted.update({
        "Status final CT-e": status,
        "Status CT-e": status,
        "Valor não pagar": round(float(decision.blocked_value or 0.0), 2),
        "Comprovante": proof,
        "Motivo": decision.reason,
        "Ação recomendada": decision.recommended_action,
        "Tipo Divergência": divergence,
        "Caminho do status": decision.decision_path,
        "Motor decisão": "MODULAR 2.7.0 RC26.5",
        "Código decisão modular": decision.decision_code,
        "Fingerprint decisão modular": decision.fingerprint,
        "Fallback decisão modular": "NÃO",
        "Confiança vínculo modular": decision.link_confidence,
        "Método vínculo modular": decision.link_mode,
        "Valor pagável modular": round(float(decision.payable_value or 0.0), 2),
        "Financeiro contabilizado": bool(decision.financial_counted),
        "NFs ignoradas modular": ignored or "-",
    })
    if warnings:
        promoted["Avisos auditoria"] = _append_text(promoted.get("Avisos auditoria"), warnings)
    if ignored:
        promoted["Avisos auditoria"] = _append_text(
            promoted.get("Avisos auditoria"), f"NFs ignoradas pelo motor modular: {ignored}"
        )
    return promoted


def _fallback_record(record: Mapping[str, Any], reason: str) -> dict[str, Any]:
    fallback = deepcopy(dict(record))
    fallback["Motor decisão"] = "LEGADO 2.6.65.20.2"
    fallback["Fallback decisão modular"] = "SIM"
    fallback["Motivo fallback modular"] = reason or "Divergência crítica ou condição de segurança."
    return fallback


def _build_caches(records: list[dict[str, Any]], original_rows: Iterable[Any]) -> tuple[list[list[Any]], dict[str, list[list[Any]]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    display: dict[str, str] = {}
    partner: dict[str, str] = {}
    for record in records:
        key = invoice_key(record.get("Fatura") or "") or str(record.get("Fatura") or "SEM_FATURA")
        grouped[key].append(record)
        display.setdefault(key, str(record.get("Fatura") or key))
        partner.setdefault(key, str(record.get("Parceiro") or "Parceiro não identificado"))

    order: list[str] = []
    for row in list(original_rows or []):
        try:
            key = invoice_key(row[0])
        except Exception:
            key = ""
        if key and key in grouped and key not in order:
            order.append(key)
    for key in grouped:
        if key not in order:
            order.append(key)

    invoice_rows: list[list[Any]] = []
    details: dict[str, list[list[Any]]] = {}
    stats = {
        "faturas": len(grouped), "itens": len(records), "ok": 0,
        "sem_comprovante": 0, "fora": 0, "complementares": 0,
        "revisar": 0, "valor_total": 0.0, "valor_nao_pagar": 0.0,
        "valor_futuro": 0.0, "valor_problema_interno": 0.0,
    }
    for key in order:
        recs = grouped[key]
        qtd = len(recs)
        counted = [rec for rec in recs if rec.get("Financeiro contabilizado", True) is not False]
        noncounted = [rec for rec in recs if rec.get("Financeiro contabilizado", True) is False]
        ok_count = sum(1 for rec in counted if _financial_kind(rec) == "OK")
        future_count = sum(1 for rec in counted if _financial_kind(rec) == "FUTURO")
        internal_count = sum(1 for rec in counted if _financial_kind(rec) == "INTERNO")
        problem_count = future_count + internal_count
        total = round(sum(parse_money(rec.get("Valor fatura") or 0.0) for rec in counted), 2)
        future_value = round(sum(parse_money(rec.get("Valor fatura") or 0.0) for rec in counted if _financial_kind(rec) == "FUTURO"), 2)
        internal_value = round(sum(parse_money(rec.get("Valor fatura") or 0.0) for rec in counted if _financial_kind(rec) == "INTERNO"), 2)
        blocked = round(future_value + internal_value, 2)
        ignored_only = bool(noncounted) and not counted and all(
            _norm(rec.get("Código decisão modular") or rec.get("Código decisão") or "") == "NF_IGNORADA"
            for rec in noncounted
        )
        if qtd == 0:
            status = "REVISAR PARSER"
        elif ignored_only:
            status = "SEM ITENS FINANCEIROS - NFS IGNORADAS"
        elif internal_count and (ok_count or future_count):
            status = "PAGAR PARCIAL / PROBLEMA INTERNO"
        elif internal_count:
            status = "RETIDO INTEGRAL / PROBLEMA INTERNO"
        elif future_count and ok_count:
            status = "PAGAR PARCIAL / SALDO FUTURO"
        elif future_count:
            status = "PENDENTE INTEGRAL / PAGAMENTO FUTURO"
        else:
            status = "OK PAGAR"
        review_count = sum(
            1 for rec in recs
            if any(token in _norm(rec.get("Status final CT-e") or "") for token in ("REVISAR", "DIVERGENTE"))
        )
        values = f"Fatura {_money(total)} | Pagar agora {_money(max(total - blocked, 0.0))} | Futuro {_money(future_value)} | Problema interno {_money(internal_value)}"
        proofs = f"Liberados {ok_count} | Comprovante pendente {future_count} | Problema interno {internal_count} | Não contabilizados {len(noncounted)}"
        invoice_rows.append([
            display[key], partner[key], str(qtd), str(ok_count), str(problem_count),
            _money(total), _money(blocked), values, proofs, status,
        ])
        details[display[key]] = [list(_detail_row(rec)) for rec in recs]

        stats["ok"] += sum(1 for rec in recs if _norm(rec.get("Status final CT-e")) == "OK")
        stats["complementares"] += sum(1 for rec in recs if _norm(rec.get("Status final CT-e")) == "OK COMPLEMENTAR")
        stats["sem_comprovante"] += sum(1 for rec in recs if _norm(rec.get("Status final CT-e")) == "SEM COMPROVANTE")
        stats["fora"] += sum(1 for rec in recs if _norm(rec.get("Status final CT-e")) == "FORA DA BASE")
        stats["revisar"] += review_count
        stats["valor_total"] += total
        stats["valor_nao_pagar"] += blocked
        stats["valor_futuro"] += future_value
        stats["valor_problema_interno"] += internal_value

    stats["valor_total"] = round(float(stats["valor_total"]), 2)
    stats["valor_nao_pagar"] = round(float(stats["valor_nao_pagar"]), 2)
    stats["valor_futuro"] = round(float(stats["valor_futuro"]), 2)
    stats["valor_problema_interno"] = round(float(stats["valor_problema_interno"]), 2)
    return invoice_rows, details, stats


class InvoicePromotionEngine:
    """Promove decisões modulares por fatura, com fallback granular ao legado."""

    VERSION = "2.7.0-RC26.5"

    def promote(
        self,
        page: Any,
        input_result: InvoiceInputAuditResult,
        decision_result: InvoiceDecisionAuditResult,
        *,
        force_legacy: bool = False,
        force_reason: str = "",
    ) -> InvoicePromotionResult:
        started = time.perf_counter()
        legacy_records = [deepcopy(record) for record in list(getattr(page, "invoice_detail_records", []) or []) if isinstance(record, Mapping)]
        original_rows = deepcopy(list(getattr(page, "invoice_rows", []) or []))
        invoice_keys = {invoice_key(record.get("Fatura") or "") for record in legacy_records if invoice_key(record.get("Fatura") or "")}
        critical_invoices: set[str] = set()
        global_reasons: list[str] = []
        invoice_reasons: dict[str, list[str]] = defaultdict(list)

        if force_legacy:
            global_reasons.append(force_reason or "Modo legado forçado por configuração ou arquivo de emergência.")
        if input_result.classification == "ERRO" or input_result.error:
            global_reasons.append(f"Erro na entrada modular: {input_result.error or input_result.classification}")
        if decision_result.classification == "ERRO" or decision_result.error:
            global_reasons.append(f"Erro na decisão modular: {decision_result.error or decision_result.classification}")

        for source, differences in (
            ("entrada", input_result.differences),
            ("decisão", decision_result.differences),
        ):
            for difference in differences:
                if str(difference.severity).upper() != "CRITICA":
                    continue
                inv = _difference_invoice(difference.key)
                message = f"{source}: {difference.scope}/{difference.field} - {difference.message}"
                if str(difference.scope).upper() in {"LOTE", "LOTE_DOURADO", "PARSER_PDF"} or not inv:
                    global_reasons.append(message)
                else:
                    critical_invoices.add(inv)
                    invoice_reasons[inv].append(message)

        decisions = list(decision_result.snapshot.decisions)
        unsupported = {item.invoice_key for item in decisions if item.decision_code not in _ALLOWED_CODES}
        for inv in unsupported:
            if inv:
                critical_invoices.add(inv)
                invoice_reasons[inv].append("Código modular ainda não homologado para promoção controlada.")

        record_counts = Counter(_record_signature(record) for record in legacy_records)
        decision_counts = Counter(_decision_signature(item) for item in decisions)
        for signature in set(record_counts) | set(decision_counts):
            if record_counts[signature] != decision_counts[signature]:
                inv = signature[0]
                if inv:
                    critical_invoices.add(inv)
                    invoice_reasons[inv].append(
                        f"Multiplicidade incompatível para CT-e {signature[1]} / NF {signature[2]} / valor {signature[3]:.2f}."
                    )
                else:
                    global_reasons.append("Multiplicidade incompatível em item sem fatura identificada.")

        global_fallback = bool(global_reasons)
        decision_queues: dict[tuple[str, str, str, float], deque[InvoiceItemDecision]] = defaultdict(deque)
        for decision in decisions:
            decision_queues[_decision_signature(decision)].append(decision)

        promoted_records: list[dict[str, Any]] = []
        modular_invoices: set[str] = set()
        legacy_invoices: set[str] = set()
        modular_items = 0
        legacy_items = 0
        for record in legacy_records:
            inv = invoice_key(record.get("Fatura") or "")
            reason = ""
            if global_fallback:
                reason = " | ".join(dict.fromkeys(global_reasons))
            elif inv in critical_invoices:
                reason = " | ".join(dict.fromkeys(invoice_reasons.get(inv) or ["Divergência crítica nesta fatura."]))
            queue = decision_queues.get(_record_signature(record))
            decision = queue.popleft() if queue else None
            if reason or decision is None:
                if not reason:
                    reason = "Decisão modular correspondente não localizada com assinatura exata."
                    critical_invoices.add(inv)
                promoted_records.append(_fallback_record(record, reason))
                legacy_invoices.add(inv)
                legacy_items += 1
            else:
                promoted_records.append(_apply_decision(record, decision))
                modular_invoices.add(inv)
                modular_items += 1

        # Segurança transacional por fatura: se qualquer item caiu no legado,
        # todos os itens daquela mesma fatura também voltam ao legado.
        if legacy_invoices and modular_invoices & legacy_invoices:
            mixed = modular_invoices & legacy_invoices
            restored: list[dict[str, Any]] = []
            legacy_by_signature: dict[tuple[str, str, str, float], deque[dict[str, Any]]] = defaultdict(deque)
            for record in legacy_records:
                legacy_by_signature[_record_signature(record)].append(record)
            for record in promoted_records:
                inv = invoice_key(record.get("Fatura") or "")
                if inv in mixed:
                    original_queue = legacy_by_signature.get(_record_signature(record))
                    original = original_queue.popleft() if original_queue else record
                    reason = "Fallback transacional: ao menos um item da fatura não pôde ser promovido."
                    restored.append(_fallback_record(original, reason))
                else:
                    restored.append(record)
            promoted_records = restored
            modular_invoices -= mixed
            legacy_invoices |= mixed
            modular_items = sum(1 for record in promoted_records if str(record.get("Fallback decisão modular") or "") == "NÃO")
            legacy_items = len(promoted_records) - modular_items

        invoice_rows, detail_map, stats = _build_caches(promoted_records, original_rows)
        counted_records = [record for record in promoted_records if record.get("Financeiro contabilizado", True) is not False]
        total = round(sum(parse_money(record.get("Valor fatura") or 0.0) for record in counted_records), 2)
        blocked = round(sum(parse_money(record.get("Valor não pagar") or 0.0) for record in counted_records), 2)

        if modular_invoices and not legacy_invoices:
            classification, official = "PROMOVIDO", "MODULAR"
        elif modular_invoices:
            classification, official = "PROMOCAO_PARCIAL", "MISTO"
        elif force_legacy:
            classification, official = "LEGADO_FORCADO", "LEGADO"
        else:
            classification, official = "FALLBACK_TOTAL", "LEGADO"

        reasons = list(dict.fromkeys(global_reasons))
        for inv in sorted(critical_invoices):
            for reason in invoice_reasons.get(inv, []):
                reasons.append(f"Fatura {inv}: {reason}")

        return InvoicePromotionResult(
            version=self.VERSION,
            mode="modular_guarded" if not force_legacy else "legacy",
            classification=classification,
            official_result=official,
            input_classification=input_result.classification,
            decision_classification=decision_result.classification,
            invoice_count=len(invoice_keys),
            item_count=len(promoted_records),
            modular_invoice_count=len(modular_invoices),
            legacy_invoice_count=len(legacy_invoices),
            modular_item_count=modular_items,
            legacy_item_count=legacy_items,
            total_value=total,
            blocked_value=blocked,
            payable_value=round(max(total - blocked, 0.0), 2),
            modular_invoices=tuple(sorted(inv for inv in modular_invoices if inv)),
            legacy_invoices=tuple(sorted(inv for inv in legacy_invoices if inv)),
            critical_invoices=tuple(sorted(inv for inv in critical_invoices if inv)),
            reasons=tuple(reasons),
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            records=tuple(promoted_records),
            invoice_rows=tuple(tuple(row) for row in invoice_rows),
            detail_rows_by_invoice={key: tuple(tuple(row) for row in rows) for key, rows in detail_map.items()},
            stats=stats,
        )

    @staticmethod
    def apply(page: Any, result: InvoicePromotionResult) -> None:
        # Backup do último estado legado antes de qualquer substituição.
        try:
            page._legacy_invoice_detail_records_2673 = deepcopy(list(getattr(page, "invoice_detail_records", []) or []))
            page._legacy_invoice_rows_2673 = deepcopy(list(getattr(page, "invoice_rows", []) or []))
            page._legacy_detail_rows_by_invoice_2673 = deepcopy(dict(getattr(page, "detail_rows_by_invoice", {}) or {}))
        except Exception:
            pass
        page.invoice_detail_records = [deepcopy(item) for item in result.records]
        page.invoice_rows = [list(item) for item in result.invoice_rows]
        page.detail_rows_by_invoice = {
            key: [list(row) for row in rows]
            for key, rows in result.detail_rows_by_invoice.items()
        }
        page._faturas_2664_stats = dict(result.stats)
        page._modular_invoice_promotion_last = result.to_dict(include_records=False)
