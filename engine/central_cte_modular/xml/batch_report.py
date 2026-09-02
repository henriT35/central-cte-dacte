from __future__ import annotations

"""Relatório único por lote de importação XML.

Evita o comportamento antigo de reescrever JSON/TXT/HTML após cada documento.
"""

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
import json

BATCH_REPORT_VERSION = "2.7.0-rc17-import-report-1"


class XmlImportBatchReporter:
    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def record(self, log: Mapping[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        session_id = now.strftime("%Y%m%d_%H%M%S_%f")
        payload = dict(log or {})
        payload.update({
            "report_version": BATCH_REPORT_VERSION,
            "generated_at": now.isoformat(timespec="milliseconds"),
            "session_id": session_id,
        })
        with self._lock:
            session_path = self.directory / f"importacao_xml_{session_id}.json"
            self._atomic_write(session_path, json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n")
            self._atomic_write(
                self.directory / "ultima_importacao_xml.json",
                json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            )
            self._atomic_write(
                self.directory / "ultima_importacao_xml.txt",
                self.render_text(payload),
            )
        return payload

    @staticmethod
    def render_text(log: Mapping[str, Any]) -> str:
        perf = dict(log.get("performance") or {})
        lines = [
            "CENTRAL CT-e / DACTE - IMPORTAÇÃO XML EM LOTE",
            f"Gerado em: {log.get('generated_at', '')}",
            f"Modo: {perf.get('mode', log.get('mode', ''))}",
            "",
            f"Selecionados: {log.get('selected', 0)}",
            f"Adicionados: {log.get('added', 0)}",
            f"Repetidos ignorados: {log.get('skipped', 0)}",
            f"Erros: {log.get('errors_count', 0)}",
            f"Total real: {log.get('total', 0)}",
            "",
            f"XMLs solicitados ao processador: {perf.get('requested_xml', 0)}",
            f"Resultados recuperados do cache: {perf.get('cache_hits', 0)}",
            f"XMLs efetivamente processados: {perf.get('parsed_xml', 0)}",
            f"Backend do cache: {perf.get('cache_backend', 'disabled')}",
            f"Processamento paralelo: {'SIM' if perf.get('parallel') else 'NÃO'}",
            f"Workers: {perf.get('workers', 1)}",
            f"Tempo do parser/cache: {float(perf.get('elapsed_ms', 0) or 0):.1f} ms",
            f"Tempo total da importação: {float(perf.get('total_elapsed_ms', 0) or 0):.1f} ms",
        ]
        if perf.get("parallel_fallback"):
            lines.append(f"Fallback do paralelismo: {perf['parallel_fallback']}")
        errors = list(log.get("errors") or [])
        if errors:
            lines.extend(["", "ERROS:"])
            lines.extend(f"- {item}" for item in errors[:250])
        duplicates = list(log.get("duplicates") or [])
        if duplicates:
            lines.extend(["", "REPETIDOS IGNORADOS:"])
            for item in duplicates[:500]:
                lines.append(
                    f"- {item.get('arquivo', '')} | {item.get('motivo', '')} | {item.get('key', '')}"
                )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)


__all__ = ["BATCH_REPORT_VERSION", "XmlImportBatchReporter"]
