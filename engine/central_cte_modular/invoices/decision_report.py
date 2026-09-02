from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from .decision_models import InvoiceDecisionAuditResult


class InvoiceDecisionAuditReport:
    VERSION = "2.6.67.3"

    def __init__(self, report_dir: str | Path) -> None:
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _money(value: Any) -> str:
        try:
            return "R$ " + f"{float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return "R$ 0,00"

    def write(self, result: InvoiceDecisionAuditResult, *, consumer: str = "manual") -> dict[str, str]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        payload = result.to_dict(include_decisions=True)
        payload.update({"version": self.VERSION, "consumer": consumer, "generated_at": datetime.now().isoformat(timespec="seconds")})

        latest_json = self.report_dir / "ultima_auditoria_decisao_faturas.json"
        latest_txt = self.report_dir / "ultima_auditoria_decisao_faturas.txt"
        latest_csv = self.report_dir / "ultima_auditoria_decisao_faturas.csv"
        differences_csv = self.report_dir / "divergencias_decisao_faturas.csv"
        history = self.report_dir / f"decisao_faturas_{stamp}.jsonl"

        latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        history.write_text(json.dumps(payload, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

        snapshot = result.snapshot
        lines = [
            f"Central CT-e / DACTE {self.VERSION} - decisão modular de faturas em modo sombra",
            f"Classificação: {result.classification}",
            f"Consumidor: {consumer}",
            "",
            f"Faturas: {snapshot.invoice_count}",
            f"Itens extraídos: {snapshot.item_count}",
            f"Itens financeiros: {snapshot.counted_item_count}",
            f"OK normais: {snapshot.ok_count}",
            f"OK complementares: {snapshot.complementary_count}",
            f"Sem comprovante: {snapshot.missing_proof_count}",
            f"Fora da base: {snapshot.outside_base_count}",
            f"Revisar: {snapshot.review_count}",
            f"NFs ignoradas: {snapshot.ignored_nf_count}",
            f"Valor total: {self._money(snapshot.total_value)}",
            f"Valor não pagar: {self._money(snapshot.blocked_value)}",
            f"Valor a pagar: {self._money(snapshot.payable_value)}",
            f"Divergências: {len(result.differences)}",
            "",
        ]
        for difference in result.differences[:500]:
            lines.append(f"[{difference.severity}] {difference.scope} | {difference.key} | {difference.field}: modular={difference.modular!r} | legado={difference.legacy!r} | {difference.message}")
        if result.error:
            lines.extend(("", f"ERRO: {result.error}"))
        latest_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

        with latest_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow([
                "Fatura", "Parceiro", "CT-e", "NF", "Valor cobrado", "Valor base", "Diferença",
                "Vínculo", "Comprovante", "Tipo documento", "SLA", "Status", "Valor não pagar",
                "NFs ignoradas", "Motivo", "Caminho da decisão",
            ])
            for item in snapshot.decisions:
                writer.writerow([
                    item.invoice_number, item.partner, item.cte_number, item.nf_number,
                    f"{item.billed_value:.2f}", f"{item.base_value:.2f}", f"{item.value_difference:.2f}",
                    item.link_mode, item.proof_status, item.document_type,
                    item.sla_status + (f" ({item.sla_days} dias)" if item.sla_days is not None else ""),
                    item.status, f"{item.blocked_value:.2f}", " | ".join(item.ignored_nf_numbers),
                    item.reason, item.decision_path,
                ])

        with differences_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Severidade", "Escopo", "Chave", "Campo", "Modular", "Legado", "Mensagem"])
            for item in result.differences:
                writer.writerow([item.severity, item.scope, item.key, item.field, item.modular, item.legacy, item.message])

        return {
            "json": str(latest_json),
            "txt": str(latest_txt),
            "csv": str(latest_csv),
            "differences_csv": str(differences_csv),
            "history": str(history),
        }
