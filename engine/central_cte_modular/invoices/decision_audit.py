from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .decision_engine import InvoiceDecisionEngine
from .decision_models import (
    InvoiceDecisionAuditResult,
    InvoiceDecisionDifference,
    InvoiceDecisionSnapshot,
    InvoiceItemDecision,
)
from .input_models import InvoiceInputSnapshot
from .normalization import cte_key, invoice_key, nf_key, parse_money, strip_accents


_STATUS_ALIASES = {
    "OK": "OK",
    "OK PAGAR": "OK",
    "PAGAR": "OK",
    "OK COMPLEMENTAR": "OK_COMPLEMENTAR",
    "SEM COMPROVANTE": "SEM_COMPROVANTE",
    "FORA DA BASE": "FORA_DA_BASE",
    "NAO LOCALIZADO": "FORA_DA_BASE",
    "NÃO LOCALIZADO": "FORA_DA_BASE",
    "REVISAR - VALOR DIVERGENTE": "DIVERGENTE_VALOR",
    "DIVERGENTE": "DIVERGENTE_VALOR",
}


def _norm(value: Any) -> str:
    return " ".join(strip_accents(value).upper().split())


def _status_code(value: Any) -> str:
    text = _norm(value)
    if text in _STATUS_ALIASES:
        return _STATUS_ALIASES[text]
    for key, result in _STATUS_ALIASES.items():
        if key in text:
            return result
    if "REVISAR" in text:
        return "REVISAR"
    return text.replace(" ", "_") or ""


def _legacy_signature(record: Mapping[str, Any]) -> tuple[str, str, str, float]:
    return (
        invoice_key(record.get("Fatura") or record.get("Número da Fatura") or record.get("fatura") or ""),
        cte_key(record.get("CT-e fatura") or record.get("CT-e") or record.get("Subcontrato") or ""),
        nf_key(record.get("NF fatura") or record.get("NF") or record.get("NF base") or ""),
        round(parse_money(record.get("Valor fatura") or record.get("Valor CT-e") or record.get("valor") or 0.0), 2),
    )


def _decision_signature(decision: InvoiceItemDecision) -> tuple[str, str, str, float]:
    return (decision.invoice_key, decision.cte_key, decision.nf_key, round(decision.billed_value, 2))


def _legacy_totals(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [record for record in records if isinstance(record, Mapping)]
    total = round(sum(parse_money(record.get("Valor fatura") or record.get("Valor CT-e") or 0.0) for record in rows), 2)
    blocked = round(sum(parse_money(record.get("Valor não pagar") or record.get("Valor Nao Pagar") or 0.0) for record in rows), 2)
    statuses = [_status_code(record.get("Status final CT-e") or record.get("Status CT-e") or record.get("status") or "") for record in rows]
    invoices = {invoice_key(record.get("Fatura") or "") for record in rows if invoice_key(record.get("Fatura") or "")}
    return {
        "invoice_count": len(invoices),
        "item_count": len(rows),
        "ok_count": statuses.count("OK"),
        "complementary_count": statuses.count("OK_COMPLEMENTAR"),
        "missing_proof_count": statuses.count("SEM_COMPROVANTE"),
        "outside_base_count": statuses.count("FORA_DA_BASE"),
        "review_count": sum(1 for status in statuses if status not in {"OK", "OK_COMPLEMENTAR", "SEM_COMPROVANTE", "FORA_DA_BASE"}),
        "total_value": total,
        "blocked_value": blocked,
        "payable_value": round(max(total - blocked, 0.0), 2),
    }


class InvoiceDecisionAuditEngine:
    VERSION = "2.6.67.3"
    MONEY_TOLERANCE = 0.06

    def __init__(self, engine: InvoiceDecisionEngine | None = None, contract_path: str | Path | None = None) -> None:
        self.engine = engine or InvoiceDecisionEngine()
        self.contract_path = Path(contract_path) if contract_path else None

    def _golden_batch(self, snapshot: InvoiceDecisionSnapshot) -> dict[str, Any]:
        if not self.contract_path or not self.contract_path.exists():
            return {"active": False}
        try:
            contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"active": False, "error": f"{type(exc).__name__}: {exc}"}
        expected = contract.get("expected") if isinstance(contract, dict) else None
        if not isinstance(expected, dict):
            expected = contract if isinstance(contract, dict) else {}
        current = {
            "invoice_count": snapshot.invoice_count,
            "item_count": snapshot.counted_item_count,
            "clone_count": 0,
            "empty_nf_count": 0,
            "total_value": snapshot.total_value,
            "blocked_value": snapshot.blocked_value,
            "payable_value": snapshot.payable_value,
        }
        # O contrato de 86 faturas / 612 itens é um lote de regressão específico.
        # Em versões anteriores ele era aplicado a qualquer processamento menor,
        # criando divergência crítica falsa. Só ativa quando a identidade mínima
        # do lote corresponde aos contadores esperados.
        expected_invoice = next((expected.get(name) for name in ("invoice_count", "invoices", "faturas") if name in expected), None)
        expected_items = next((expected.get(name) for name in ("item_count", "cte_count", "items", "ctes") if name in expected), None)
        identity_checks = []
        if expected_invoice is not None:
            identity_checks.append(int(current["invoice_count"]) == int(expected_invoice))
        if expected_items is not None:
            identity_checks.append(int(current["item_count"]) == int(expected_items))
        if identity_checks and not all(identity_checks):
            return {
                "active": False,
                "applicable": False,
                "reason": "Lote atual não corresponde à identidade do lote dourado.",
                "expected_identity": {"invoice_count": expected_invoice, "item_count": expected_items},
                "actual_identity": {"invoice_count": current["invoice_count"], "item_count": current["item_count"]},
            }
        checks: dict[str, Any] = {}
        aliases = {
            "invoice_count": ("invoice_count", "invoices", "faturas"),
            "item_count": ("item_count", "cte_count", "items", "ctes"),
            "clone_count": ("clone_count", "clones"),
            "empty_nf_count": ("empty_nf_count", "empty_nfs", "nfs_vazias"),
            "total_value": ("total_value", "total_brl", "total", "valor_total"),
            "blocked_value": ("blocked_value", "not_payable", "valor_nao_pagar"),
            "payable_value": ("payable_value", "valor_pagar"),
        }
        for field, names in aliases.items():
            expected_value = next((expected.get(name) for name in names if name in expected), None)
            if expected_value is None:
                continue
            actual = current[field]
            if field.endswith("value"):
                ok = abs(float(actual) - float(expected_value)) <= self.MONEY_TOLERANCE
            else:
                ok = int(actual) == int(expected_value)
            checks[field] = {"expected": expected_value, "actual": actual, "ok": ok}
        return {"active": bool(checks), "checks": checks, "ok": all(item["ok"] for item in checks.values()) if checks else True}

    def audit(
        self,
        input_snapshot: InvoiceInputSnapshot,
        legacy_records: Iterable[Mapping[str, Any]] = (),
    ) -> InvoiceDecisionAuditResult:
        try:
            snapshot = self.engine.decide(input_snapshot)
            records = [dict(record) for record in legacy_records if isinstance(record, Mapping)]
            differences: list[InvoiceDecisionDifference] = []
            legacy_by_signature: dict[tuple[str, str, str, float], list[dict[str, Any]]] = defaultdict(list)
            for record in records:
                legacy_by_signature[_legacy_signature(record)].append(record)

            for decision in snapshot.decisions:
                if decision.decision_code == "NF_IGNORADA":
                    continue
                signature = _decision_signature(decision)
                candidates = legacy_by_signature.get(signature) or []
                if not candidates:
                    differences.append(
                        InvoiceDecisionDifference(
                            severity="CRITICA",
                            scope="ITEM",
                            key=f"FAT={decision.invoice_number}|CTE={decision.cte_number}|NF={decision.nf_number}",
                            field="existence",
                            modular=decision.status,
                            legacy="AUSENTE",
                            message="A decisão modular não encontrou item correspondente nos registros oficiais do legado.",
                        )
                    )
                    continue
                legacy = candidates.pop(0)
                legacy_status = _status_code(legacy.get("Status final CT-e") or legacy.get("Status CT-e") or "")
                if legacy_status != decision.decision_code:
                    # Ambiguidade/base indisponível são revisões internas do novo motor;
                    # o legado normalmente colapsa esses casos em FORA DA BASE.
                    equivalent = decision.decision_code in {"BASE_AMBIGUA", "BASE_NAO_CARREGADA"} and legacy_status in {"FORA_DA_BASE", "REVISAR"}
                    if not equivalent:
                        differences.append(
                            InvoiceDecisionDifference(
                                severity="CRITICA",
                                scope="ITEM",
                                key=f"FAT={decision.invoice_number}|CTE={decision.cte_number}|NF={decision.nf_number}",
                                field="status",
                                modular=decision.status,
                                legacy=legacy.get("Status final CT-e") or legacy.get("Status CT-e") or "",
                                message="O status financeiro modular difere do status oficial legado.",
                            )
                        )
                legacy_blocked = round(parse_money(legacy.get("Valor não pagar") or legacy.get("Valor Nao Pagar") or 0.0), 2)
                if abs(legacy_blocked - decision.blocked_value) > self.MONEY_TOLERANCE:
                    differences.append(
                        InvoiceDecisionDifference(
                            severity="CRITICA",
                            scope="ITEM",
                            key=f"FAT={decision.invoice_number}|CTE={decision.cte_number}|NF={decision.nf_number}",
                            field="blocked_value",
                            modular=decision.blocked_value,
                            legacy=legacy_blocked,
                            message="O valor bloqueado pelo módulo difere do registro oficial legado.",
                        )
                    )
                legacy_base = round(parse_money(legacy.get("Valor base") or 0.0), 2)
                if legacy_base and abs(legacy_base - decision.base_value) > self.MONEY_TOLERANCE:
                    differences.append(
                        InvoiceDecisionDifference(
                            severity="INFORMATIVA",
                            scope="ITEM",
                            key=f"FAT={decision.invoice_number}|CTE={decision.cte_number}|NF={decision.nf_number}",
                            field="base_value",
                            modular=decision.base_value,
                            legacy=legacy_base,
                            message="A linha escolhida existe nos dois caminhos, mas o valor base selecionado difere.",
                        )
                    )

            for signature, candidates in legacy_by_signature.items():
                for legacy in candidates:
                    differences.append(
                        InvoiceDecisionDifference(
                            severity="CRITICA",
                            scope="ITEM",
                            key=f"FAT={legacy.get('Fatura') or ''}|CTE={legacy.get('CT-e fatura') or legacy.get('CT-e') or ''}|NF={legacy.get('NF fatura') or legacy.get('NF') or ''}",
                            field="existence",
                            modular="AUSENTE",
                            legacy=legacy.get("Status final CT-e") or legacy.get("Status CT-e") or "PRESENTE",
                            message="O legado possui item financeiro sem decisão modular correspondente.",
                        )
                    )

            totals = _legacy_totals(records)
            if records:
                for field in ("invoice_count", "item_count", "total_value", "blocked_value", "payable_value"):
                    modular_value = snapshot.counted_item_count if field == "item_count" else getattr(snapshot, field)
                    legacy_value = totals[field]
                    if field.endswith("value"):
                        mismatch = abs(float(modular_value) - float(legacy_value)) > self.MONEY_TOLERANCE
                    else:
                        mismatch = int(modular_value) != int(legacy_value)
                    if mismatch:
                        differences.append(
                            InvoiceDecisionDifference(
                                severity="CRITICA",
                                scope="LOTE",
                                key="TOTAIS",
                                field=field,
                                modular=modular_value,
                                legacy=legacy_value,
                                message="O total do lote modular difere do total oficial legado.",
                            )
                        )

            golden = self._golden_batch(snapshot)
            for field, check in (golden.get("checks") or {}).items():
                if not check.get("ok"):
                    differences.append(
                        InvoiceDecisionDifference(
                            severity="CRITICA",
                            scope="LOTE_DOURADO",
                            key="CONTRATO",
                            field=field,
                            modular=check.get("actual"),
                            legacy=check.get("expected"),
                            message="A decisão modular não reproduziu o contrato do lote dourado.",
                        )
                    )

            severities = {item.severity for item in differences}
            classification = "CRITICA" if "CRITICA" in severities else ("INFORMATIVA" if differences else "IGUAL")
            return InvoiceDecisionAuditResult(
                classification=classification,
                snapshot=snapshot,
                differences=tuple(differences),
                legacy_totals=totals,
                golden_batch=golden,
            )
        except Exception as exc:
            empty = InvoiceDecisionSnapshot(
                invoice_count=0,
                item_count=0,
                counted_item_count=0,
                ok_count=0,
                complementary_count=0,
                missing_proof_count=0,
                outside_base_count=0,
                review_count=1,
                ignored_nf_count=0,
                total_value=0.0,
                blocked_value=0.0,
                payable_value=0.0,
                warnings=(f"{type(exc).__name__}: {exc}",),
            )
            return InvoiceDecisionAuditResult(classification="ERRO", snapshot=empty, error=f"{type(exc).__name__}: {exc}")
