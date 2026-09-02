from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import threading
from typing import Any

from .input_models import InvoiceInputAuditResult


class InvoiceInputAuditReport:
    VERSION = "2.6.67.3"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.history_path = self.directory / f"entrada_faturas_{self.session_id}.jsonl"
        self._lock = threading.RLock()

    def write(self, result: InvoiceInputAuditResult, *, consumer: str) -> None:
        payload = {
            "version": self.VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "session_id": self.session_id,
            "consumer": consumer,
            **result.to_dict(include_documents=True),
        }
        with self._lock:
            with self.history_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._write_latest(payload)

    def _write_latest(self, payload: dict[str, Any]) -> None:
        snapshot = payload.get("snapshot") or {}
        links = snapshot.get("links") or []
        differences = payload.get("differences") or []
        (self.directory / "ultima_auditoria_entrada_faturas.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        linked = sum(1 for item in links if item.get("status") == "VINCULADO")
        ambiguous = sum(1 for item in links if item.get("status") == "AMBIGUO")
        missing = sum(1 for item in links if item.get("status") == "NAO_LOCALIZADO")
        lines = [
            "CENTRAL CT-e / DACTE 2.6.67.3 - ENTRADA DE FATURAS E VÍNCULO BASE EM MODO SOMBRA",
            "=" * 94,
            f"Gerado em: {payload.get('generated_at', '')}",
            f"Consumidor: {payload.get('consumer', '')}",
            f"Classificação: {payload.get('classification', '')}",
            f"Documentos recebidos: {snapshot.get('document_count', 0)}",
            f"Documentos únicos: {snapshot.get('unique_document_count', 0)}",
            f"Documentos duplicados: {snapshot.get('duplicate_document_count', 0)}",
            f"Faturas: {snapshot.get('invoice_count', 0)}",
            f"Itens extraídos: {snapshot.get('item_count', 0)}",
            f"NFs vazias: {snapshot.get('empty_nf_count', 0)}",
            f"Erros de parser: {snapshot.get('parser_error_count', 0)}",
            f"Vínculos: {linked} vinculados | {ambiguous} ambíguos | {missing} não localizados",
            f"Tempo: {snapshot.get('elapsed_ms', 0)} ms",
            "",
            f"Divergências: {len(differences)}",
        ]
        for item in differences[:500]:
            lines.append(
                f"[{item.get('severity')}] {item.get('scope')} {item.get('key')} | {item.get('field')} | modular={item.get('modular')} | legado={item.get('legacy')}"
            )
            lines.append(f"  {item.get('message', '')}")
        if payload.get("error"):
            lines.extend(["", f"ERRO: {payload.get('error')}"])
        (self.directory / "ultima_auditoria_entrada_faturas.txt").write_text("\n".join(lines), encoding="utf-8")

        with (self.directory / "ultima_auditoria_entrada_faturas.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Fatura", "CT-e", "NF", "Valor", "Status vínculo", "Modo", "Confiança", "CT-e base", "NF base", "Valor base", "Comprovante", "Tipo documento"])
            for item in links:
                writer.writerow([
                    item.get("invoice_number", ""), item.get("cte_number", ""), item.get("nf_number", ""), item.get("billed_value", 0),
                    item.get("status", ""), item.get("mode", ""), item.get("confidence", ""), item.get("base_cte", ""),
                    item.get("base_nf", ""), item.get("base_value", 0), item.get("proof_status", ""), item.get("document_type", ""),
                ])

        with (self.directory / "divergencias_entrada_faturas.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Severidade", "Escopo", "Chave", "Campo", "Modular", "Legado", "Mensagem"])
            for item in differences:
                writer.writerow([
                    item.get("severity", ""), item.get("scope", ""), item.get("key", ""), item.get("field", ""),
                    json.dumps(item.get("modular"), ensure_ascii=False, default=str),
                    json.dumps(item.get("legacy"), ensure_ascii=False, default=str), item.get("message", ""),
                ])
