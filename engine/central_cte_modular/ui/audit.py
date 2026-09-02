from __future__ import annotations

import csv
import json
from pathlib import Path
import threading
from typing import Iterable

from .models import UIActionAudit


class UIAuditWriter:
    """Persistência simples e resistente para a auditoria dos controladores."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._session_path: Path | None = None

    def _history_path(self, audit: UIActionAudit) -> Path:
        if self._session_path is None:
            stamp = audit.timestamp.replace("-", "").replace(":", "").replace("T", "_")
            self._session_path = self.directory / f"controladores_ui_{stamp}.jsonl"
        return self._session_path

    def write(self, audit: UIActionAudit) -> None:
        payload = audit.to_dict()
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / "ultima_acao_ui.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (self.directory / "ultima_acao_ui.txt").write_text(self._to_text(audit), encoding="utf-8")
            self._write_csv(self.directory / "ultima_acao_ui.csv", [audit])
            with self._history_path(audit).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")

    @staticmethod
    def _to_text(audit: UIActionAudit) -> str:
        before = audit.before
        after = audit.after
        lines = [
            "AUDITORIA DOS CONTROLADORES DE INTERFACE",
            "=" * 72,
            f"Versão: {audit.version}",
            f"Data/hora: {audit.timestamp}",
            f"Controlador: {audit.controller}",
            f"Página: {audit.page_module}.{audit.page_class}",
            f"Ação: {audit.action}",
            f"Método: {audit.method}",
            f"Modo: {audit.mode}",
            f"Classificação: {audit.classification}",
            f"Tempo: {audit.elapsed_ms:.3f} ms",
            f"Fonte oficial: {audit.official_source or '-'}",
            "",
            "ESTADO ANTES / DEPOIS",
            f"Arquivos: {before.files_count} -> {after.files_count}",
            f"Documentos de fatura: {before.invoice_docs_count} -> {after.invoice_docs_count}",
            f"Linhas de fatura: {before.invoice_rows_count} -> {after.invoice_rows_count}",
            f"Detalhes de fatura: {before.invoice_details_count} -> {after.invoice_details_count}",
            f"Selecionados: {before.selected_count} -> {after.selected_count}",
            f"Linhas visuais: {before.table_rows} -> {after.table_rows}",
        ]
        if audit.error:
            lines.extend(["", "ERRO", audit.error])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _write_csv(path: Path, audits: Iterable[UIActionAudit]) -> None:
        columns = [
            "timestamp", "controller", "page", "action", "method", "mode",
            "classification", "elapsed_ms", "official_source", "files_before",
            "files_after", "invoice_docs_before", "invoice_docs_after",
            "invoice_rows_before", "invoice_rows_after", "details_before",
            "details_after", "table_before", "table_after", "error",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";")
            writer.writeheader()
            for audit in audits:
                writer.writerow({
                    "timestamp": audit.timestamp,
                    "controller": audit.controller,
                    "page": f"{audit.page_module}.{audit.page_class}",
                    "action": audit.action,
                    "method": audit.method,
                    "mode": audit.mode,
                    "classification": audit.classification,
                    "elapsed_ms": f"{audit.elapsed_ms:.3f}".replace(".", ","),
                    "official_source": audit.official_source,
                    "files_before": audit.before.files_count,
                    "files_after": audit.after.files_count,
                    "invoice_docs_before": audit.before.invoice_docs_count,
                    "invoice_docs_after": audit.after.invoice_docs_count,
                    "invoice_rows_before": audit.before.invoice_rows_count,
                    "invoice_rows_after": audit.after.invoice_rows_count,
                    "details_before": audit.before.invoice_details_count,
                    "details_after": audit.after.invoice_details_count,
                    "table_before": audit.before.table_rows,
                    "table_after": audit.after.table_rows,
                    "error": audit.error,
                })
