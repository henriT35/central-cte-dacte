from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import threading
from typing import Any

from .promotion_models import InvoicePromotionResult


class InvoicePromotionReport:
    VERSION = "2.6.67.3"

    def __init__(self, report_dir: str | Path) -> None:
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def write(self, result: InvoicePromotionResult, *, consumer: str = "process_invoices") -> dict[str, str]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "consumer": consumer,
            **result.to_dict(include_records=False),
        }
        latest_json = self.report_dir / "ultima_promocao_faturas.json"
        latest_txt = self.report_dir / "ultima_promocao_faturas.txt"
        latest_csv = self.report_dir / "ultima_promocao_faturas.csv"
        fallback_csv = self.report_dir / "faturas_em_fallback.csv"
        history = self.report_dir / f"promocao_faturas_{stamp}.jsonl"
        with self._lock:
            latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            with history.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            lines = [
                "CENTRAL CT-e / DACTE 2.6.67.3 - PROMOÇÃO CONTROLADA DA DECISÃO DE FATURAS",
                "=" * 92,
                f"Gerado em: {payload['generated_at']}",
                f"Consumidor: {consumer}",
                f"Classificação: {result.classification}",
                f"Resultado oficial: {result.official_result}",
                f"Auditoria da entrada: {result.input_classification}",
                f"Auditoria da decisão: {result.decision_classification}",
                "",
                f"Faturas: {result.invoice_count} | Itens: {result.item_count}",
                f"Faturas modulares: {result.modular_invoice_count} | Faturas no legado: {result.legacy_invoice_count}",
                f"Itens modulares: {result.modular_item_count} | Itens no legado: {result.legacy_item_count}",
                f"Valor total: {result.total_value:.2f} | Não pagar: {result.blocked_value:.2f} | A pagar: {result.payable_value:.2f}",
                f"Tempo da promoção: {result.elapsed_ms:.3f} ms",
                "",
                "FATURAS NO LEGADO",
                ", ".join(result.legacy_invoices) or "Nenhuma",
                "",
                "MOTIVOS / TRAVAS",
            ]
            lines.extend(result.reasons or ("Nenhuma trava crítica.",))
            latest_txt.write_text("\n".join(lines), encoding="utf-8")

            with latest_csv.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow([
                    "Classificação", "Resultado oficial", "Faturas", "Itens",
                    "Faturas modulares", "Faturas legado", "Itens modulares", "Itens legado",
                    "Valor total", "Valor não pagar", "Valor a pagar",
                    "Auditoria entrada", "Auditoria decisão",
                ])
                writer.writerow([
                    result.classification, result.official_result, result.invoice_count, result.item_count,
                    result.modular_invoice_count, result.legacy_invoice_count,
                    result.modular_item_count, result.legacy_item_count,
                    result.total_value, result.blocked_value, result.payable_value,
                    result.input_classification, result.decision_classification,
                ])

            with fallback_csv.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["Fatura", "Motivo"])
                reasons = " | ".join(result.reasons)
                for invoice in result.legacy_invoices:
                    writer.writerow([invoice, reasons or "Fallback de segurança registrado no JSON."])
        return {
            "json": str(latest_json), "txt": str(latest_txt),
            "csv": str(latest_csv), "fallback_csv": str(fallback_csv),
            "history": str(history),
        }
