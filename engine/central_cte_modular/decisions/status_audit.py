from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
import threading
from typing import Any


class StatusAuditReport:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.jsonl_path = self.directory / f"classificador_status_{self.session_id}.jsonl"
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}

    def record(self, *, status: str, consumer: str, modular: Any, legacy: Any = None, context: dict[str, Any] | None = None) -> None:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": str(status or ""),
            "consumer": str(consumer or ""),
            "modular": modular,
            "legacy": legacy,
            "equal": legacy is None or modular == legacy,
            "context": dict(context or {}),
        }
        key = json.dumps([record["status"], record["consumer"], modular, legacy], ensure_ascii=False, sort_keys=True, default=str)
        with self._lock:
            self._records[key] = record
            with self.jsonl_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._write_latest()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records.values())
        differences = sum(1 for item in records if not item.get("equal"))
        return {
            "version": "2.6.66.9",
            "session_id": self.session_id,
            "totals": {
                "unique_observations": len(records),
                "differences_vs_legacy": differences,
                "equal_vs_legacy": len(records) - differences,
            },
            "records": records,
        }

    def _write_latest(self) -> None:
        data = self.snapshot()
        json_path = self.directory / "ultima_auditoria_status.json"
        txt_path = self.directory / "ultima_auditoria_status.txt"
        csv_path = self.directory / "ultima_auditoria_status.csv"
        json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        lines = [
            "CENTRAL CT-e / DACTE 2.6.66.9 - AUDITORIA DO CLASSIFICADOR DE STATUS",
            "=" * 78,
            f"Sessão: {self.session_id}",
            f"Observações únicas: {data['totals']['unique_observations']}",
            f"Diferenças contra interpretação legada: {data['totals']['differences_vs_legacy']}",
            "",
        ]
        for item in data["records"]:
            marker = "IGUAL" if item.get("equal") else "DIFERENTE"
            lines.append(f"[{marker}] {item.get('consumer')} | {item.get('status')}")
            lines.append(f"  modular={item.get('modular')} | legado={item.get('legacy')}")
        txt_path.write_text("\n".join(lines), encoding="utf-8")

        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Status", "Consumidor", "Modular", "Legado", "Igual", "Contexto"])
            for item in data["records"]:
                writer.writerow([
                    item.get("status", ""),
                    item.get("consumer", ""),
                    json.dumps(item.get("modular"), ensure_ascii=False, default=str),
                    json.dumps(item.get("legacy"), ensure_ascii=False, default=str),
                    "SIM" if item.get("equal") else "NÃO",
                    json.dumps(item.get("context") or {}, ensure_ascii=False, default=str),
                ])
