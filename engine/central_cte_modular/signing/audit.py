from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any


def text_sha256(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


class SignaturePdfAuditWriter:
    """Persistência leve da promoção de assinatura/PDF.

    Os arquivos ``ultima_*`` representam a sessão atual. O JSONL mantém o
    histórico detalhado sem interferir na geração oficial.
    """

    def __init__(self, report_dir: Path) -> None:
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.jsonl_path = self.report_dir / f"assinatura_pdf_{self.session_id}.jsonl"
        self._records: list[dict[str, Any]] = []
        self._lock = RLock()

    def record(self, operation: str, **payload: Any) -> dict[str, Any]:
        item = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_id": self.session_id,
            "operation": str(operation),
            **payload,
        }
        with self._lock:
            self._records.append(item)
            with self.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            self._write_latest()
        return item

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
        counts: dict[str, int] = {}
        fallback = 0
        critical = 0
        for item in records:
            key = str(item.get("classification") or item.get("official") or "OUTRO")
            counts[key] = counts.get(key, 0) + 1
            fallback += int(bool(item.get("fallback")))
            critical += int(str(item.get("classification") or "").upper() == "CRITICA")
        return {
            "version": "2.6.67.6",
            "session_id": self.session_id,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "operations": len(records),
            "fallbacks": fallback,
            "critical": critical,
            "counts": counts,
            "records": records,
        }

    def _write_latest(self) -> None:
        snapshot = self.snapshot()
        json_path = self.report_dir / "ultima_auditoria_assinatura_pdf.json"
        txt_path = self.report_dir / "ultima_auditoria_assinatura_pdf.txt"
        csv_path = self.report_dir / "ultima_auditoria_assinatura_pdf.csv"
        json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        lines = [
            "Central CT-e / DACTE - Auditoria Assinatura e PDF 2.6.67.6",
            f"Sessão: {snapshot['session_id']}",
            f"Operações: {snapshot['operations']}",
            f"Fallbacks: {snapshot['fallbacks']}",
            f"Críticas: {snapshot['critical']}",
            "",
        ]
        for item in snapshot["records"]:
            lines.append(
                f"{item.get('timestamp')} | {item.get('operation')} | "
                f"{item.get('classification', '-')} | oficial={item.get('official', '-')} | "
                f"fallback={item.get('fallback', False)} | {item.get('reason', '')}"
            )
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        fields = [
            "timestamp", "operation", "classification", "official", "fallback", "reason",
            "cte", "profile_id", "legacy_sha256", "modular_sha256", "output", "error",
            "xml_originals_modified",
        ]
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", delimiter=";")
            writer.writeheader()
            writer.writerows(snapshot["records"])
