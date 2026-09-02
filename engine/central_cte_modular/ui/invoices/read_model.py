from __future__ import annotations

"""Read model oficial da página de faturas RC26.5.

A interface recebe a mesma decisão usada no relatório. O valor pendente é
separado em duas naturezas: pagamento futuro por comprovante e retenção por
problema interno. Nenhum parceiro é bloqueado por nome, CNPJ ou ausência de
tabela comercial.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable

READ_MODEL_VERSION = "2.7.0-rc26.5-segundo-pente-fino"
_OK_CODES = {"OK", "OK_COMPLEMENTAR"}


def _decision_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _financial_nature(decision: Any) -> tuple[float, float]:
    """Retorna (pagamento_futuro, problema_interno) para um CT-e."""
    if not bool(getattr(decision, "financial_counted", True)):
        return 0.0, 0.0
    value = round(float(getattr(decision, "billed_value", 0.0) or 0.0), 2)
    code = _decision_code(getattr(decision, "decision_code", ""))
    proof = str(getattr(decision, "proof_status", "") or "").strip().upper()
    if code == "SEM_COMPROVANTE":
        return value, 0.0
    if code == "FORA_DA_BASE":
        if proof == "S":
            return 0.0, 0.0
        return value, 0.0
    if code not in _OK_CODES:
        return 0.0, value
    return 0.0, 0.0


@dataclass(frozen=True)
class InvoiceReadModel:
    records: tuple[dict[str, Any], ...]
    rows: tuple[tuple[Any, ...], ...]
    details_by_invoice: dict[str, tuple[tuple[Any, ...], ...]]
    invoice_count: int
    ok_invoice_count: int
    partial_invoice_count: int
    future_invoice_count: int
    internal_problem_invoice_count: int
    blocked_invoice_count: int
    no_pay_invoice_count: int
    review_invoice_count: int
    item_count: int
    ok_item_count: int
    problem_item_count: int
    total_value: float
    blocked_value: float
    future_value: float
    internal_problem_value: float
    payable_value: float


def build_invoice_read_model(
    snapshot: Any,
    *,
    money: Callable[[Any], str],
) -> InvoiceReadModel:
    records: list[dict[str, Any]] = []
    details: dict[str, list[tuple[Any, ...]]] = {}
    financial_by_invoice: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"future": 0.0, "internal": 0.0, "future_count": 0, "internal_count": 0}
    )

    for decision in tuple(getattr(snapshot, "decisions", ()) or ()):
        rec = decision.to_dict()
        future_item, internal_item = _financial_nature(decision)
        group_key = str(getattr(decision, "invoice_number", "") or getattr(decision, "invoice_key", "") or "")
        financial_by_invoice[group_key]["future"] = round(
            float(financial_by_invoice[group_key]["future"]) + future_item, 2
        )
        financial_by_invoice[group_key]["internal"] = round(
            float(financial_by_invoice[group_key]["internal"]) + internal_item, 2
        )
        if future_item > 0:
            financial_by_invoice[group_key]["future_count"] = int(financial_by_invoice[group_key]["future_count"]) + 1
        if internal_item > 0:
            financial_by_invoice[group_key]["internal_count"] = int(financial_by_invoice[group_key]["internal_count"]) + 1

        mapped = {
            **rec,
            "Fatura": decision.invoice_number,
            "Fatura chave": decision.invoice_key,
            "Parceiro": decision.partner,
            "CT-e": decision.cte_number,
            "CT-e fatura": decision.cte_number,
            "NF": decision.nf_number,
            "NF fatura": decision.nf_number,
            "Valor fatura": decision.billed_value,
            "Valor base": decision.base_value,
            "Frete CTRC Origem fatura": float(getattr(decision, "base_freight_value", 0.0) or 0.0),
            "Fonte frete base": str(getattr(decision, "base_freight_source", "") or ""),
            # Campo legado preservado para consumidores antigos. Na interface e
            # no XLSX os dois destinos abaixo são exibidos separadamente.
            "Valor não pagar": decision.blocked_value,
            "Valor pendente": decision.blocked_value,
            "Valor para pagamento futuro": future_item,
            "Valor retido por problema interno": internal_item,
            "Valor a pagar": decision.payable_value,
            "Status final CT-e": decision.status,
            "Status CT-e": decision.status,
            "Status valor": decision.value_status,
            "Conferência do valor": (
                f"{decision.value_status} (informativo)"
                if str(decision.status or "").upper().startswith("OK")
                and str(decision.value_status or "").upper() == "DIVERGENTE"
                else decision.value_status
            ),
            "Fatura Base": decision.base_invoice,
            "Comprovante": decision.proof_status,
            "DY": decision.proof_status,
            "Tipo documento base": decision.document_type,
            "CT-e base": decision.base_cte,
            "NF base": decision.base_nf,
            "Motivo": decision.reason,
            "Ação recomendada": decision.recommended_action,
            "Método de busca": decision.link_mode,
            "Match base": decision.link_mode,
            "Confiança validação valor": decision.link_confidence,
            "Caminho do status": decision.decision_path,
            "Arquivo fatura": decision.source_file,
            "Sequência item": decision.sequence,
            "NFs ignoradas": ", ".join(decision.ignored_nf_numbers),
            "Avisos auditoria": "; ".join(decision.warnings),
            "Financeiro contabilizado": bool(decision.financial_counted),
            "Código decisão": decision.decision_code,
        }
        records.append(mapped)
        display_value_status = (
            f"{decision.value_status} (informativo)"
            if str(decision.status or "").upper().startswith("OK")
            and str(decision.value_status or "").upper() == "DIVERGENTE"
            else decision.value_status
        )
        details.setdefault(decision.invoice_number, []).append(
            (
                decision.cte_number or "-",
                decision.nf_number or "-",
                decision.billed_value,
                decision.base_value,
                display_value_status,
                decision.base_invoice or "-",
                decision.proof_status or "-",
                "-",
                decision.status,
                decision.reason,
            )
        )

    rows: list[tuple[Any, ...]] = []
    ok_invoices = partial_invoices = 0
    future_invoices = internal_invoices = integral_internal_invoices = 0
    for summary in tuple(getattr(snapshot, "invoices", ()) or ()):
        group_key = str(getattr(summary, "invoice_number", "") or getattr(summary, "invoice_key", "") or "")
        nature = financial_by_invoice.get(group_key, {})
        future = round(float(nature.get("future", 0.0) or 0.0), 2)
        internal = round(float(nature.get("internal", 0.0) or 0.0), 2)
        future_count = int(nature.get("future_count", 0) or 0)
        internal_count = int(nature.get("internal_count", 0) or 0)
        payable = round(float(getattr(summary, "payable_value", 0.0) or 0.0), 2)
        pending_total = round(future + internal, 2)
        values = (
            f"Fatura {money(summary.total_value)} | "
            f"Pagar agora {money(payable)} | "
            f"Futuro {money(future)} | "
            f"Problema interno {money(internal)}"
        )
        proof = (
            f"Liberados {summary.ok_count + summary.complementary_count} | "
            f"Comprovante pendente {future_count} | "
            f"Problema interno {internal_count}"
        )
        rows.append(
            (
                summary.invoice_number,
                summary.partner,
                str(summary.item_count),
                str(summary.ok_count + summary.complementary_count),
                str(future_count + internal_count),
                money(summary.total_value),
                money(pending_total),
                values,
                proof,
                summary.status,
            )
        )
        status = str(summary.status or "").upper()
        if status == "OK PAGAR":
            ok_invoices += 1
        if status.startswith("PAGAR PARCIAL"):
            partial_invoices += 1
        if future > 0:
            future_invoices += 1
        if internal > 0:
            internal_invoices += 1
        if status.startswith("RETIDO INTEGRAL / PROBLEMA INTERNO"):
            integral_internal_invoices += 1

    counted = [record for record in records if record.get("Financeiro contabilizado", True)]
    ok_items = sum(
        1
        for record in counted
        if float(record.get("Valor para pagamento futuro") or 0.0) <= 0
        and float(record.get("Valor retido por problema interno") or 0.0) <= 0
    )
    problem_items = max(len(counted) - ok_items, 0)
    future_value = round(sum(float(record.get("Valor para pagamento futuro") or 0.0) for record in counted), 2)
    internal_value = round(sum(float(record.get("Valor retido por problema interno") or 0.0) for record in counted), 2)
    blocked_value = round(future_value + internal_value, 2)

    return InvoiceReadModel(
        records=tuple(records),
        rows=tuple(rows),
        details_by_invoice={key: tuple(value) for key, value in details.items()},
        invoice_count=len(rows),
        ok_invoice_count=ok_invoices,
        partial_invoice_count=partial_invoices,
        future_invoice_count=future_invoices,
        internal_problem_invoice_count=internal_invoices,
        blocked_invoice_count=internal_invoices,
        no_pay_invoice_count=integral_internal_invoices,
        review_invoice_count=internal_invoices,
        item_count=len(records),
        ok_item_count=ok_items,
        problem_item_count=problem_items,
        total_value=round(float(getattr(snapshot, "total_value", 0.0) or 0.0), 2),
        blocked_value=blocked_value,
        future_value=future_value,
        internal_problem_value=internal_value,
        payable_value=round(float(getattr(snapshot, "payable_value", 0.0) or 0.0), 2),
    )


__all__ = ["READ_MODEL_VERSION", "InvoiceReadModel", "build_invoice_read_model"]
