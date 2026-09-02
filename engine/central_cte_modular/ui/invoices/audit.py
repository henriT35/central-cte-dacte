from __future__ import annotations

"""Auditoria leve das ações do presenter de faturas."""

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

AUDIT_VERSION = "2.7.0-RC26.5"


@dataclass(slots=True)
class InvoicePresenterAuditEvent:
    action: str
    status: str
    started_at: str
    elapsed_ms: float = 0.0
    documents: int = 0
    invoices: int = 0
    items: int = 0
    total_value: float = 0.0
    blocked_value: float = 0.0
    payable_value: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    version: str = AUDIT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InvoicePresenterAuditWriter:
    def __init__(self, report_dir: str | Path | None) -> None:
        self.report_dir = Path(report_dir) if report_dir else None

    def write(self, event: InvoicePresenterAuditEvent) -> None:
        if self.report_dir is None:
            return
        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
            payload = event.to_dict()
            (self.report_dir / "ultima_auditoria_presenter_faturas.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            lines = [
                f"Central CT-e Presenter de Faturas {AUDIT_VERSION}",
                f"Ação: {event.action}",
                f"Status: {event.status}",
                f"Início: {event.started_at}",
                f"Tempo: {event.elapsed_ms:.3f} ms",
                f"Documentos: {event.documents}",
                f"Faturas: {event.invoices}",
                f"Itens: {event.items}",
                f"Total: {event.total_value:.2f}",
                f"Valor pendente total: {event.blocked_value:.2f}",
                f"A pagar: {event.payable_value:.2f}",
                f"Erro: {event.error or '-'}",
            ]
            if event.details:
                lines.extend(["", "Detalhes:"])
                lines.extend(f"- {key}: {value}" for key, value in sorted(event.details.items()))
            (self.report_dir / "ultima_auditoria_presenter_faturas.txt").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
            with (self.report_dir / "ultima_auditoria_presenter_faturas.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(["CAMPO", "VALOR"])
                for key, value in payload.items():
                    writer.writerow([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
            with (self.report_dir / "presenter_faturas.jsonl").open(
                "a", encoding="utf-8"
            ) as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        except Exception:
            return


__all__ = [
    "AUDIT_VERSION",
    "InvoicePresenterAuditEvent",
    "InvoicePresenterAuditWriter",
]
