from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

AUDIT_VERSION = "2.6.69.4"


@dataclass
class CTePresenterAuditEvent:
    action: str
    status: str
    started_at: str
    elapsed_ms: float = 0.0
    documents: int = 0
    selected: int = 0
    visible: int = 0
    generated: int = 0
    source: str = ""
    error: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["version"] = AUDIT_VERSION
        return payload


class CTePresenterAuditWriter:
    def __init__(self, report_dir: str | Path | None) -> None:
        self.report_dir = Path(report_dir) if report_dir else None
        self.last_event: dict[str, Any] = {}

    def write(self, event: CTePresenterAuditEvent) -> dict[str, Any]:
        payload = event.to_dict()
        self.last_event = payload
        if self.report_dir is None:
            return payload
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            (self.report_dir / "ultima_auditoria_presenter_cte.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            lines = [
                f"Central CT-e Presenter CT-e Modular {AUDIT_VERSION}",
                f"Ação: {payload['action']}",
                f"Status: {payload['status']}",
                f"Início: {payload['started_at']}",
                f"Tempo: {payload['elapsed_ms']:.3f} ms",
                f"Documentos: {payload['documents']}",
                f"Selecionados: {payload['selected']}",
                f"Visíveis: {payload['visible']}",
                f"Gerados: {payload['generated']}",
                f"Fonte: {payload['source'] or '-'}",
                f"Erro: {payload['error'] or '-'}",
            ]
            (self.report_dir / "ultima_auditoria_presenter_cte.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
            with (self.report_dir / "ultima_auditoria_presenter_cte.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["CAMPO", "VALOR"])
                for key, value in payload.items():
                    if key == "details":
                        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                    writer.writerow([key, value])
            with (self.report_dir / "presenter_cte.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception:
            pass
        return payload


__all__ = ["AUDIT_VERSION", "CTePresenterAuditEvent", "CTePresenterAuditWriter"]
