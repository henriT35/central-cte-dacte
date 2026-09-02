from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .invoice_report import normalize_sheets
from ..invoices.normalization import stable_hash


@dataclass(frozen=True)
class ReportDifference:
    severity: str
    scope: str
    field: str
    legacy: Any
    modular: Any
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "scope": self.scope,
            "field": self.field,
            "legacy": self.legacy,
            "modular": self.modular,
            "message": self.message,
        }


@dataclass
class InvoiceReportAuditResult:
    version: str
    classification: str
    official_source: str
    legacy_fingerprint: str
    modular_fingerprint: str
    differences: list[ReportDifference] = field(default_factory=list)
    error: str = ""
    elapsed_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "classification": self.classification,
            "official_source": self.official_source,
            "legacy_fingerprint": self.legacy_fingerprint,
            "modular_fingerprint": self.modular_fingerprint,
            "difference_count": len(self.differences),
            "critical_count": sum(1 for item in self.differences if item.severity == "CRITICA"),
            "informative_count": sum(1 for item in self.differences if item.severity == "INFORMATIVA"),
            "differences": [item.to_dict() for item in self.differences],
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "created_at": self.created_at,
        }


class InvoiceReportAuditor:
    VERSION = "2.6.67.4"

    def compare(self, legacy_sheets: Iterable[Any], modular_sheets: Iterable[Any], *, official_source: str) -> InvoiceReportAuditResult:
        left = normalize_sheets(legacy_sheets)
        right = normalize_sheets(modular_sheets)
        left_hash = stable_hash(left)
        right_hash = stable_hash(right)
        differences: list[ReportDifference] = []
        if left_hash != right_hash:
            if len(left) != len(right):
                differences.append(ReportDifference("CRITICA", "PASTA", "quantidade_abas", len(left), len(right), "Quantidade de abas diferente."))
            for index in range(max(len(left), len(right))):
                if index >= len(left) or index >= len(right):
                    continue
                l_name, l_rows, l_widths = left[index]
                r_name, r_rows, r_widths = right[index]
                if l_name != r_name:
                    differences.append(ReportDifference("CRITICA", f"ABA_{index + 1}", "nome", l_name, r_name, "Nome da aba diferente."))
                if l_widths != r_widths:
                    differences.append(ReportDifference("INFORMATIVA", l_name, "larguras", l_widths, r_widths, "Larguras de colunas diferentes."))
                if len(l_rows) != len(r_rows):
                    differences.append(ReportDifference("CRITICA", l_name, "quantidade_linhas", len(l_rows), len(r_rows), "Quantidade de linhas diferente."))
                row_limit = min(len(l_rows), len(r_rows))
                for row_index in range(row_limit):
                    l_row, r_row = l_rows[row_index], r_rows[row_index]
                    if l_row == r_row:
                        continue
                    differences.append(ReportDifference(
                        "CRITICA", l_name, f"linha_{row_index + 1}", l_row, r_row,
                        "Conteúdo da linha diferente entre relatório legado e modular.",
                    ))
                    if len(differences) >= 250:
                        break
                if len(differences) >= 250:
                    break
        critical = any(item.severity == "CRITICA" for item in differences)
        informative = any(item.severity == "INFORMATIVA" for item in differences)
        classification = "CRITICA" if critical else ("INFORMATIVA" if informative else "IGUAL")
        return InvoiceReportAuditResult(
            version=self.VERSION,
            classification=classification,
            official_source=official_source,
            legacy_fingerprint=left_hash,
            modular_fingerprint=right_hash,
            differences=differences,
        )


class InvoiceReportAuditWriter:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, result: InvoiceReportAuditResult, *, consumer: str = "manual") -> dict[str, str]:
        payload = result.to_dict()
        payload["consumer"] = consumer
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        json_path = self.directory / "ultima_auditoria_relatorio.json"
        txt_path = self.directory / "ultima_auditoria_relatorio.txt"
        csv_path = self.directory / "ultima_auditoria_relatorio.csv"
        history_path = self.directory / f"relatorio_faturas_{stamp}.jsonl"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        txt_lines = [
            "AUDITORIA DO RELATÓRIO MODULAR DE FATURAS 2.6.67.4",
            "=" * 72,
            f"Classificação: {result.classification}",
            f"Fonte oficial: {result.official_source}",
            f"Diferenças: {len(result.differences)}",
            f"Fingerprint legado: {result.legacy_fingerprint}",
            f"Fingerprint modular: {result.modular_fingerprint}",
            f"Erro: {result.error or '-'}",
            "",
        ]
        for item in result.differences:
            txt_lines.append(f"[{item.severity}] {item.scope} / {item.field}: {item.message}")
        txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(["Severidade", "Escopo", "Campo", "Legado", "Modular", "Mensagem"])
            for item in result.differences:
                writer.writerow([item.severity, item.scope, item.field, json.dumps(item.legacy, ensure_ascii=False, default=str), json.dumps(item.modular, ensure_ascii=False, default=str), item.message])
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        return {"json": str(json_path), "txt": str(txt_path), "csv": str(csv_path), "history": str(history_path)}
