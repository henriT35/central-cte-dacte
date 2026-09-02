from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import threading
from typing import Any

from .models import InvoiceShadowResult


class InvoiceAuditReport:
    VERSION = "2.6.67.1"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.history_path = self.directory / f"motor_faturas_{self.session_id}.jsonl"
        self._lock = threading.RLock()

    def write(self, result: InvoiceShadowResult, *, consumer: str, append_history: bool = True) -> None:
        payload = {
            "version": self.VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "session_id": self.session_id,
            "consumer": str(consumer or ""),
            **result.to_dict(include_items=True),
        }
        with self._lock:
            if append_history:
                with self.history_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._write_latest(payload)

    def _write_latest(self, payload: dict[str, Any]) -> None:
        json_path = self.directory / "ultima_auditoria_faturas.json"
        txt_path = self.directory / "ultima_auditoria_faturas.txt"
        csv_path = self.directory / "ultima_auditoria_faturas.csv"
        divergence_path = self.directory / "divergencias_faturas.csv"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        modular = payload.get("modular") or {}
        legacy = payload.get("legacy") or {}
        differences = payload.get("differences") or []
        lines = [
            "CENTRAL CT-e / DACTE 2.6.67.1 - MOTOR DE FATURAS MODULAR EM MODO SOMBRA",
            "=" * 86,
            f"Gerado em: {payload.get('generated_at', '')}",
            f"Consumidor: {payload.get('consumer', '')}",
            f"Classificação: {payload.get('classification', '')}",
            f"Tempo do comparador: {payload.get('elapsed_ms', 0)} ms",
            "",
            "MODULAR SOMBRA",
            f"Faturas: {modular.get('invoice_count', 0)} | Itens: {modular.get('item_count', 0)} | Clones: {modular.get('clone_count', 0)} | NFs vazias: {modular.get('empty_nf_count', 0)}",
            f"Valor total: {float(modular.get('total_value', 0) or 0):.2f} | Não pagar: {float(modular.get('blocked_value', 0) or 0):.2f} | A pagar: {float(modular.get('payable_value', 0) or 0):.2f}",
            "",
            "LEGADO OFICIAL",
            f"Faturas: {legacy.get('invoice_count', 0)} | Itens: {legacy.get('item_count', 0)} | Clones: {legacy.get('clone_count', 0)} | NFs vazias: {legacy.get('empty_nf_count', 0)}",
            f"Valor total: {float(legacy.get('total_value', 0) or 0):.2f} | Não pagar: {float(legacy.get('blocked_value', 0) or 0):.2f} | A pagar: {float(legacy.get('payable_value', 0) or 0):.2f}",
            "",
            f"Divergências: {len(differences)}",
        ]
        for item in differences[:300]:
            lines.append(
                f"[{item.get('severity')}] {item.get('scope')} {item.get('key')} | {item.get('field')} | modular={item.get('modular')} | legado={item.get('legacy')}"
            )
            lines.append(f"  {item.get('message', '')}")
        golden = payload.get("golden_batch") or {}
        lines.extend(["", f"Contrato do lote dourado: {golden.get('status', 'NÃO AVALIADO')}"])
        if payload.get("error"):
            lines.extend(["", f"ERRO: {payload.get('error')}"])
        txt_path.write_text("\n".join(lines), encoding="utf-8")

        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Origem", "Faturas", "Itens", "Clones", "NFs vazias", "Valor total", "Valor não pagar", "Valor a pagar", "Classificação"])
            writer.writerow(["MODULAR", modular.get("invoice_count", 0), modular.get("item_count", 0), modular.get("clone_count", 0), modular.get("empty_nf_count", 0), modular.get("total_value", 0), modular.get("blocked_value", 0), modular.get("payable_value", 0), payload.get("classification", "")])
            writer.writerow(["LEGADO", legacy.get("invoice_count", 0), legacy.get("item_count", 0), legacy.get("clone_count", 0), legacy.get("empty_nf_count", 0), legacy.get("total_value", 0), legacy.get("blocked_value", 0), legacy.get("payable_value", 0), payload.get("classification", "")])

        with divergence_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Severidade", "Escopo", "Chave", "Campo", "Modular", "Legado", "Mensagem"])
            for item in differences:
                writer.writerow([
                    item.get("severity", ""),
                    item.get("scope", ""),
                    item.get("key", ""),
                    item.get("field", ""),
                    json.dumps(item.get("modular"), ensure_ascii=False, default=str),
                    json.dumps(item.get("legacy"), ensure_ascii=False, default=str),
                    item.get("message", ""),
                ])
