from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta
import time
from typing import Any, Iterable

from .decision_models import InvoiceDecisionSnapshot, InvoiceDecisionSummary, InvoiceItemDecision
from .input_models import InvoiceBaseLink, InvoiceInputItem, InvoiceInputSnapshot
from .normalization import cte_key, invoice_key, nf_key, stable_hash, strip_accents


_OK_CODES = {"OK", "OK_COMPLEMENTAR"}
_VALUE_TOLERANCE = 0.06

def _norm(value: Any) -> str:
    return " ".join(strip_accents(value).upper().split())


def _is_complementary(value: Any) -> bool:
    text = _norm(value)
    return any(token in text for token in ("COMPLEMENT", "COMPL", "CUSTO EXTRA", "CUSTO ADICIONAL"))


def _is_courtesy(value: Any) -> bool:
    text = _norm(value)
    return any(token in text for token in ("CORTESIA", "DEVOLU"))


def _proof_ok(value: Any) -> bool:
    return _norm(value) in {"S", "SIM", "OK", "COMPROVANTE OK", "TRUE", "1"}


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    if " " in text and text.count("/") == 2:
        text = text.split(" ", 1)[0]
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except Exception:
            continue
    try:
        numeric = float(text.replace(",", "."))
        if numeric > 1000:
            return (datetime(1899, 12, 30) + timedelta(days=numeric)).date()
    except Exception:
        pass
    return None


def _sla(item: InvoiceInputItem, link: InvoiceBaseLink) -> tuple[str, int | None]:
    invoice_date = _parse_date(getattr(item, "invoice_issue_date", ""))
    cte_date = _parse_date(getattr(link, "cte_issue_date", ""))
    if not invoice_date or not cte_date:
        return "NÃO AVALIADO", None
    days = (invoice_date - cte_date).days
    if days < 0:
        return "REVISAR - FATURA ANTERIOR AO CT-e", days
    # O prazo comercial de 30 dias é registrado para auditoria. Nesta fase
    # sombra ele não altera pagamento, pois a política operacional ainda será
    # homologada separadamente.
    if days < 30:
        return "INFORMATIVO - MENOS DE 30 DIAS", days
    return "OK - 30 DIAS OU MAIS", days


def _link_key(item: InvoiceInputItem) -> tuple[str, str, str, float]:
    return (item.invoice_key, item.cte_key, item.nf_key, round(float(item.billed_value or 0.0), 2))


def _financial_group_key(item: InvoiceInputItem) -> tuple[str, str, float]:
    return (item.invoice_key, item.cte_key, round(float(item.billed_value or 0.0), 2))


def _status_for(item: InvoiceInputItem, link: InvoiceBaseLink) -> dict[str, Any]:
    billed = round(float(item.billed_value or 0.0), 2)
    linked = str(link.status or "").upper() == "VINCULADO"
    complementary = linked and _is_complementary(link.document_type)
    courtesy = linked and _is_courtesy(link.document_type)
    proof_required = linked and not complementary
    proof_ok = linked and (complementary or _proof_ok(link.proof_status))
    base_value = round(float(link.base_value or 0.0), 2)
    difference = round(billed - base_value, 2) if linked else 0.0

    if not linked:
        value_status = "NÃO VALIDADO - FORA DA BASE"
    elif courtesy and abs(difference) > _VALUE_TOLERANCE:
        value_status = "DIVERGENTE INFORMATIVO - CORTESIA/DEVOLUÇÃO"
    elif abs(difference) <= _VALUE_TOLERANCE:
        value_status = "OK"
    else:
        value_status = "DIVERGENTE"

    sla_status, sla_days = _sla(item, link)
    warnings: list[str] = []
    if value_status.startswith("DIVERGENTE INFORMATIVO"):
        warnings.append("Diferença de valor tratada como informativa para cortesia/devolução.")
    if sla_status.startswith("INFORMATIVO"):
        warnings.append("Prazo de 30 dias registrado em modo sombra, sem alterar pagamento.")

    if not linked:
        raw = str(link.status or "").upper()
        if raw == "AMBIGUO":
            code, status = "BASE_AMBIGUA", "REVISAR - BASE AMBÍGUA"
            reason = "Mais de uma linha da base recebeu a mesma pontuação máxima."
            action = "Conferir manualmente a linha correta da base antes do pagamento."
        elif raw == "BASE_NAO_CARREGADA":
            code, status = "BASE_NAO_CARREGADA", "REVISAR - BASE NÃO CARREGADA"
            reason = "A base Rodovitor não estava disponível para validar o item."
            action = "Carregar a base Rodovitor e processar novamente."
        else:
            code, status = "FORA_DA_BASE", "FORA DA BASE - AUDITORIA"
            reason = "CT-e/NF não localizado na Base Rodovitor; ocorrência mantida apenas para auditoria."
            action = "Verificar o comprovante: S libera o pagamento; N, vazio ou '-' mantém o valor para pagamento futuro."
        blocked = billed
    elif complementary:
        code, status = "OK_COMPLEMENTAR", "OK COMPLEMENTAR"
        reason = "CT-e complementar/custo extra localizado na base; comprovante de entrega dispensado."
        action = "Liberar se o valor estiver conferido."
        blocked = 0.0
    elif not proof_ok:
        code, status = "SEM_COMPROVANTE", "SEM COMPROVANTE"
        reason = "Sem comprovante de entrega na base (DY=N ou vazio)."
        action = "Retirar este CT-e da fatura atual e reapresentar após regularização do comprovante."
        blocked = billed
    else:
        # O valor gravado na base nem sempre representa a comissão efetivamente
        # cobrada na fatura. Nesta fase sombra, diferenças entre esses dois
        # campos continuam visíveis na auditoria, mas não podem criar um falso
        # bloqueio financeiro. A validação comercial por tabela permanece em
        # sua trilha própria até a homologação da decisão modular completa.
        code, status = "OK", "OK"
        if value_status == "DIVERGENTE":
            reason = "Vínculo e comprovante localizados; diferença de valor registrada apenas para auditoria."
            action = "Liberar conforme a decisão financeira atual e conferir a divergência na auditoria comercial."
            warnings.append("Divergência de valor em modo sombra; não altera status financeiro nesta versão.")
        else:
            reason = "Vínculo e comprovante localizados na base."
            action = "Liberar pagamento deste CT-e."
        blocked = 0.0

    path = " → ".join(
        (
            f"Fatura {item.invoice_number or '-'} / CT-e {item.cte_number or '-'} / NF {item.nf_number or '-'}",
            f"Vínculo {link.mode or link.status or '-'} ({link.confidence or '-'})",
            f"Documento {link.document_type or '-'}",
            "Comprovante dispensado" if complementary else ("Comprovante DY=S" if proof_ok else "Comprovante ausente"),
            f"Valor {value_status}; cobrado {billed:.2f}; base {base_value:.2f}; diferença {difference:.2f}",
            f"SLA {sla_status}" + (f" ({sla_days} dias)" if sla_days is not None else ""),
            f"STATUS FINAL {status}",
        )
    )
    fingerprint = stable_hash(
        (
            item.invoice_key,
            item.cte_key,
            item.nf_key,
            billed,
            link.status,
            link.mode,
            link.base_nf,
            link.base_cte,
            base_value,
            round(float(getattr(link, "base_freight_value", 0.0) or 0.0), 2),
            link.proof_status,
            link.document_type,
            code,
            blocked,
        )
    )
    return {
        "invoice_number": item.invoice_number,
        "invoice_key": item.invoice_key,
        "partner": item.partner,
        "cte_number": item.cte_number,
        "cte_key": item.cte_key,
        "nf_number": item.nf_number,
        "nf_key": item.nf_key,
        "billed_value": billed,
        "base_status": link.status,
        "link_mode": link.mode,
        "link_confidence": link.confidence,
        "base_nf": link.base_nf,
        "base_cte": link.base_cte,
        "base_value": base_value,
        "base_invoice": link.base_invoice,
        "proof_status": link.proof_status,
        "document_type": link.document_type,
        "is_complementary": complementary,
        "is_courtesy": courtesy,
        "proof_required": proof_required,
        "proof_ok": proof_ok,
        "value_status": value_status,
        "value_difference": difference,
        "sla_status": sla_status,
        "sla_days": sla_days,
        "decision_code": code,
        "status": status,
        "blocked_value": round(blocked, 2),
        "payable_value": round(max(billed - blocked, 0.0), 2),
        "financial_counted": True,
        "reason": reason,
        "recommended_action": action,
        "decision_path": path,
        "ignored_nf_numbers": (),
        "warnings": tuple(warnings),
        "source_file": item.source_file,
        "sequence": int(item.sequence or 0),
        "fingerprint": fingerprint,
        "base_freight_value": round(float(getattr(link, "base_freight_value", 0.0) or 0.0), 2),
        "base_freight_source": str(getattr(link, "base_freight_source", "") or ""),
    }


class InvoiceDecisionEngine:
    """Decide comprovante, natureza, valor bloqueado e status em modo sombra."""

    VERSION = "2.7.0-RC26.5"

    @staticmethod
    def _links_by_item(snapshot: InvoiceInputSnapshot) -> dict[tuple[str, str, str, float], list[InvoiceBaseLink]]:
        result: dict[tuple[str, str, str, float], list[InvoiceBaseLink]] = defaultdict(list)
        for link in snapshot.links:
            key = (
                invoice_key(link.invoice_number),
                cte_key(link.cte_number),
                nf_key(link.nf_number),
                round(float(link.billed_value or 0.0), 2),
            )
            result[key].append(link)
        return result

    def decide(self, snapshot: InvoiceInputSnapshot) -> InvoiceDecisionSnapshot:
        started = time.perf_counter()
        items = [item for document in snapshot.documents for item in document.items]
        link_map = self._links_by_item(snapshot)
        preliminary: list[InvoiceItemDecision] = []
        warnings = list(snapshot.warnings)

        for item in items:
            key = _link_key(item)
            bucket = link_map.get(key) or []
            if bucket:
                link = bucket.pop(0)
            else:
                link = InvoiceBaseLink(
                    invoice_number=item.invoice_number,
                    cte_number=item.cte_number,
                    nf_number=item.nf_number,
                    billed_value=item.billed_value,
                    status="NAO_LOCALIZADO",
                    mode="NÃO LOCALIZADO NA BASE",
                    confidence="NENHUMA",
                    message="O vínculo modular não foi produzido para este item.",
                )
            preliminary.append(InvoiceItemDecision(**_status_for(item, link)))

        # XMLs e alguns layouts podem expor várias NFs candidatas para a mesma
        # cobrança. Quando existe ao menos uma NF com vínculo confiável e valor
        # correto, as demais NFs do mesmo CT-e/valor são informativas e não
        # transformam o documento em falso bloqueio.
        groups: dict[tuple[str, str, float], list[int]] = defaultdict(list)
        for index, item in enumerate(items):
            groups[_financial_group_key(item)].append(index)
        resolved = list(preliminary)
        for indexes in groups.values():
            if len(indexes) < 2:
                continue
            valid = [
                index for index in indexes
                if resolved[index].decision_code in _OK_CODES
                and resolved[index].link_confidence in {"ALTA", "MEDIA"}
                and resolved[index].value_status in {"OK", "DIVERGENTE INFORMATIVO - CORTESIA/DEVOLUÇÃO"}
            ]
            if not valid:
                continue
            winner_index = sorted(
                valid,
                key=lambda index: (
                    0 if resolved[index].link_confidence == "ALTA" else 1,
                    0 if resolved[index].link_mode == "FATURA_EN_ER" else 1,
                    resolved[index].sequence,
                ),
            )[0]
            ignored = tuple(
                resolved[index].nf_number
                for index in indexes
                if index != winner_index and resolved[index].nf_number
            )
            winner = resolved[winner_index]
            resolved[winner_index] = replace(
                winner,
                ignored_nf_numbers=ignored,
                warnings=tuple(dict.fromkeys((*winner.warnings, f"NFs ignoradas: {', '.join(ignored)}"))) if ignored else winner.warnings,
            )
            for index in indexes:
                if index == winner_index:
                    continue
                current = resolved[index]
                resolved[index] = replace(
                    current,
                    decision_code="NF_IGNORADA",
                    status="NF IGNORADA - VÍNCULO CONFIÁVEL EM OUTRA NF",
                    blocked_value=0.0,
                    payable_value=0.0,
                    financial_counted=False,
                    reason=f"A NF {current.nf_number or '-'} foi ignorada porque outra NF do mesmo CT-e/valor possui vínculo confiável.",
                    recommended_action="Manter apenas como evidência de auditoria; não bloquear nem somar novamente.",
                    decision_path=current.decision_path + " → NF IGNORADA POR VÍNCULO CONFIÁVEL DO GRUPO",
                    warnings=tuple(dict.fromkeys((*current.warnings, "NF ignorada sem alterar o status financeiro."))),
                )

        invoice_groups: dict[str, list[InvoiceItemDecision]] = defaultdict(list)
        invoice_order: list[str] = []
        for decision in resolved:
            key = decision.invoice_key or decision.invoice_number
            if key not in invoice_groups:
                invoice_order.append(key)
            invoice_groups[key].append(decision)

        summaries: list[InvoiceDecisionSummary] = []
        for key in invoice_order:
            decisions = invoice_groups[key]
            counted = [item for item in decisions if item.financial_counted]
            ok = [item for item in counted if item.decision_code in _OK_CODES]
            problems = [item for item in counted if item.decision_code not in _OK_CODES]
            total = round(sum(item.billed_value for item in counted), 2)
            blocked = round(sum(item.blocked_value for item in counted), 2)
            future_pending = [
                item for item in counted
                if item.decision_code in {"SEM_COMPROVANTE", "FORA_DA_BASE"}
            ]
            internal_problems = [
                item for item in counted
                if item.decision_code not in _OK_CODES | {"SEM_COMPROVANTE", "FORA_DA_BASE"}
            ]
            if not counted:
                status = "REVISAR PARSER"
            elif internal_problems:
                if ok or future_pending:
                    status = "PAGAR PARCIAL / PENDÊNCIAS MISTAS"
                else:
                    status = "RETIDO INTEGRAL / PROBLEMA INTERNO"
            elif future_pending and ok:
                status = "PAGAR PARCIAL / SALDO FUTURO"
            elif future_pending:
                status = "PENDENTE INTEGRAL / PAGAMENTO FUTURO"
            else:
                status = "OK PAGAR"
            summaries.append(
                InvoiceDecisionSummary(
                    invoice_number=decisions[0].invoice_number if decisions else "",
                    invoice_key=decisions[0].invoice_key if decisions else key,
                    partner=decisions[0].partner if decisions else "",
                    item_count=len(decisions),
                    counted_item_count=len(counted),
                    ok_count=sum(1 for item in counted if item.decision_code == "OK"),
                    complementary_count=sum(1 for item in counted if item.decision_code == "OK_COMPLEMENTAR"),
                    missing_proof_count=sum(1 for item in counted if item.decision_code == "SEM_COMPROVANTE"),
                    outside_base_count=sum(1 for item in counted if item.decision_code == "FORA_DA_BASE"),
                    review_count=sum(1 for item in counted if item.decision_code not in _OK_CODES | {"SEM_COMPROVANTE", "FORA_DA_BASE"}),
                    ignored_nf_count=sum(1 for item in decisions if item.decision_code == "NF_IGNORADA"),
                    total_value=total,
                    blocked_value=blocked,
                    payable_value=round(max(total - blocked, 0.0), 2),
                    status=status,
                    item_fingerprints=tuple(item.fingerprint for item in decisions),
                )
            )

        counted_all = [item for item in resolved if item.financial_counted]
        total_value = round(sum(item.billed_value for item in counted_all), 2)
        blocked_value = round(sum(item.blocked_value for item in counted_all), 2)
        elapsed = (time.perf_counter() - started) * 1000.0
        return InvoiceDecisionSnapshot(
            invoice_count=len(summaries),
            item_count=len(resolved),
            counted_item_count=len(counted_all),
            ok_count=sum(1 for item in counted_all if item.decision_code == "OK"),
            complementary_count=sum(1 for item in counted_all if item.decision_code == "OK_COMPLEMENTAR"),
            missing_proof_count=sum(1 for item in counted_all if item.decision_code == "SEM_COMPROVANTE"),
            outside_base_count=sum(1 for item in counted_all if item.decision_code == "FORA_DA_BASE"),
            review_count=sum(1 for item in counted_all if item.decision_code not in _OK_CODES | {"SEM_COMPROVANTE", "FORA_DA_BASE"}),
            ignored_nf_count=sum(1 for item in resolved if item.decision_code == "NF_IGNORADA"),
            total_value=total_value,
            blocked_value=blocked_value,
            payable_value=round(max(total_value - blocked_value, 0.0), 2),
            invoices=tuple(summaries),
            decisions=tuple(resolved),
            input_fingerprint=stable_hash(tuple(item.fingerprint for item in resolved)),
            elapsed_ms=elapsed,
            warnings=tuple(warnings),
        )
