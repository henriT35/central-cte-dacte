from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping
import hashlib
import json

from .audit_catalog import ParserAuditCatalog
from .shadow_parser import SHADOW_VERSION, ShadowComparison

REPORT_VERSION = "2.6.66.5"


class ParserShadowReport:
    """Persiste a auditoria automática por sessão e no histórico consolidado.

    Cada conteúdo XML é registrado uma vez por sessão, usando SHA-256. A abertura
    do programa não apaga mais ``ultima_auditoria.*`` da execução anterior. Após
    cada XML, também são reconstruídos os relatórios consolidados de todas as
    sessões existentes.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.started_at = datetime.now()
        self.session_id = self._make_session_id()
        self.jsonl_path = self.directory / f"auditoria_parser_{self.session_id}.jsonl"
        self._records: list[dict[str, Any]] = []
        self._seen_hashes: set[str] = set()
        self._lock = RLock()
        self.catalog = ParserAuditCatalog(self.directory)
        # Gera o consolidado vazio em uma instalação nova, mas preserva o último
        # relatório de sessão até que o primeiro XML desta execução seja auditado.
        if not (self.directory / "auditoria_consolidada.json").exists():
            self.catalog.rebuild()

    @property
    def records(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(self._records)

    def record(self, comparison: ShadowComparison) -> bool:
        path = Path(comparison.path)
        digest = self._sha256(path)
        unique_key = digest or f"path:{path.resolve() if path.exists() else path}"
        with self._lock:
            if unique_key in self._seen_hashes:
                return False
            self._seen_hashes.add(unique_key)
            record = self._build_record(comparison, path, digest)
            self._records.append(record)
            self._append_jsonl(record)
            self._write_latest_files()
            self.catalog.rebuild()
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def consolidated_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self.catalog.snapshot()

    def rebuild_consolidated(self) -> dict[str, Any]:
        with self._lock:
            return self.catalog.rebuild()

    def _make_session_id(self) -> str:
        base = self.started_at.strftime("%Y%m%d_%H%M%S")
        candidate = base
        suffix = 1
        while (self.directory / f"auditoria_parser_{candidate}.jsonl").exists():
            suffix += 1
            candidate = f"{base}_{suffix:02d}"
        return candidate

    def _build_record(self, comparison: ShadowComparison, path: Path, digest: str) -> dict[str, Any]:
        payload = comparison.to_dict()
        legacy = payload.get("legacy_summary") or {}
        modular = payload.get("modular_summary") or {}
        payload.update({
            "report_version": REPORT_VERSION,
            "session_id": self.session_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "arquivo": path.name,
            "sha256": digest,
            "cte": legacy.get("numero") or modular.get("numero") or "",
            "serie": legacy.get("serie") or modular.get("serie") or "",
            "chave": legacy.get("chave") or modular.get("chave") or "",
        })
        return payload

    @staticmethod
    def _counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
        items = list(records)
        return {
            "total": len(items),
            "equal": sum(1 for item in items if item.get("status") == "IGUAL"),
            "informative": sum(1 for item in items if item.get("status") == "INFORMATIVA"),
            "critical": sum(1 for item in items if item.get("status") == "CRÍTICA"),
            "differences": sum(len(item.get("differences") or {}) for item in items),
        }

    @staticmethod
    def _promotion_message(counts: Mapping[str, int]) -> str:
        if int(counts.get("total", 0)) == 0:
            return "Aguardando importação de XMLs reais nesta sessão."
        if int(counts.get("critical", 0)):
            return f"Promoção bloqueada: {counts['critical']} XML(s) com divergência crítica nesta sessão."
        if int(counts.get("informative", 0)):
            return "Sem divergências críticas nesta sessão; diferenças informativas ainda precisam ser justificadas."
        return "Sem divergências nesta sessão; consultar também o histórico consolidado e homologar no Windows."

    def _snapshot_unlocked(self) -> dict[str, Any]:
        counts = self._counts(self._records)
        return {
            "version": REPORT_VERSION,
            "parser_shadow_version": SHADOW_VERSION,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "report_directory": str(self.directory),
            "jsonl_file": self.jsonl_path.name,
            "totals": counts,
            "promotion": {
                "allowed_by_audit": counts["total"] > 0 and counts["critical"] == 0,
                "message": self._promotion_message(counts),
            },
            "records": list(self._records),
        }

    def _append_jsonl(self, record: Mapping[str, Any]) -> None:
        with self.jsonl_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(record), ensure_ascii=False, default=str) + "\n")

    def _write_latest_files(self) -> None:
        snapshot = self._snapshot_unlocked()
        self._atomic_write(
            self.directory / "ultima_auditoria.json",
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        )
        self._atomic_write(self.directory / "ultima_auditoria.txt", self._render_text(snapshot))
        self._atomic_write(self.directory / "ultima_auditoria.html", self._render_html(snapshot))

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _sha256(path: Path) -> str:
        try:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except Exception:
            return ""

    @staticmethod
    def _render_text(snapshot: Mapping[str, Any]) -> str:
        totals = snapshot["totals"]
        lines = [
            "CENTRAL CT-e / DACTE 2.6.66.5 - AUDITORIA AUTOMÁTICA DO PARSER XML",
            f"Sessão: {snapshot['session_id']}",
            f"Início: {snapshot['started_at']}",
            f"Atualização: {snapshot['generated_at']}",
            "",
            f"XMLs auditados: {totals['total']}",
            f"Iguais: {totals['equal']}",
            f"Divergência informativa: {totals['informative']}",
            f"Divergência crítica: {totals['critical']}",
            f"Campos divergentes: {totals['differences']}",
            "",
            str(snapshot["promotion"]["message"]),
            "",
        ]
        for index, item in enumerate(snapshot.get("records") or [], start=1):
            fields = ", ".join((item.get("differences") or {}).keys()) or "nenhum"
            lines.extend([
                f"{index}. [{item.get('status', '')}] {item.get('arquivo', '')}",
                f"   CT-e: {item.get('cte', '')}  Série: {item.get('serie', '')}",
                f"   Chave: {item.get('chave', '')}",
                f"   SHA-256: {item.get('sha256', '')}",
                f"   Campos: {fields}",
            ])
            if item.get("legacy_error"):
                lines.append(f"   Erro legado: {item['legacy_error']}")
            if item.get("modular_error"):
                lines.append(f"   Erro modular: {item['modular_error']}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _render_html(snapshot: Mapping[str, Any]) -> str:
        totals = snapshot["totals"]
        rows: list[str] = []
        details: list[str] = []
        for index, item in enumerate(snapshot.get("records") or [], start=1):
            status = str(item.get("status", ""))
            css = {"IGUAL": "ok", "INFORMATIVA": "info", "CRÍTICA": "critical"}.get(status, "")
            fields = ", ".join((item.get("differences") or {}).keys()) or "-"
            rows.append(
                "<tr>"
                f"<td>{index}</td><td><span class='badge {css}'>{escape(status)}</span></td>"
                f"<td>{escape(str(item.get('arquivo', '')))}</td>"
                f"<td>{escape(str(item.get('cte', '')))}</td>"
                f"<td>{escape(str(item.get('chave', '')))}</td>"
                f"<td>{escape(fields)}</td>"
                "</tr>"
            )
            if item.get("differences"):
                diff_rows: list[str] = []
                for field_name, difference in item["differences"].items():
                    legacy = json.dumps(difference.get("legacy"), ensure_ascii=False, indent=2, default=str)
                    modular = json.dumps(difference.get("modular"), ensure_ascii=False, indent=2, default=str)
                    diff_rows.append(
                        "<tr>"
                        f"<td>{escape(str(field_name))}</td><td>{escape(str(difference.get('severity', '')))}</td>"
                        f"<td><pre>{escape(legacy)}</pre></td><td><pre>{escape(modular)}</pre></td>"
                        "</tr>"
                    )
                details.append(
                    f"<details class='detail {css}'><summary>{escape(str(item.get('arquivo', '')))} - {escape(status)}</summary>"
                    "<table><thead><tr><th>Campo</th><th>Classe</th><th>Legado</th><th>Modular</th></tr></thead>"
                    f"<tbody>{''.join(diff_rows)}</tbody></table></details>"
                )
        rows_html = "".join(rows) or "<tr><td colspan='6' class='empty'>Nenhum XML importado nesta sessão.</td></tr>"
        return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auditoria do Parser XML 2.6.66.5</title>
<style>
:root{{--bg:#f4f6f8;--card:#fff;--text:#17212b;--muted:#64748b;--line:#dbe2ea;--ok:#15803d;--info:#a16207;--critical:#b91c1c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px Arial,sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}h1{{margin:0 0 6px;font-size:25px}}.subtitle{{color:var(--muted);margin-bottom:20px}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px;margin:18px 0}}.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}}.card b{{display:block;font-size:26px;margin-top:5px}}.promotion{{margin:12px 0 18px;border-left:5px solid var(--info)}}
table{{width:100%;border-collapse:collapse;background:var(--card)}}th,td{{border:1px solid var(--line);padding:9px;vertical-align:top;text-align:left}}th{{background:#eef2f6}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:12px Consolas,monospace}}
.badge{{display:inline-block;border-radius:999px;padding:4px 9px;font-weight:700;background:#e2e8f0}}.badge.ok{{background:#dcfce7;color:var(--ok)}}.badge.info{{background:#fef3c7;color:var(--info)}}.badge.critical{{background:#fee2e2;color:var(--critical)}}
.detail{{margin-top:12px;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--info);border-radius:10px;padding:10px}}.detail.critical{{border-left-color:var(--critical)}}.detail.ok{{border-left-color:var(--ok)}}summary{{cursor:pointer;font-weight:700;padding:5px}}.empty{{text-align:center;color:var(--muted);padding:30px}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr 1fr}}main{{padding:12px}}table{{font-size:12px}}}}
</style></head><body><main>
<h1>Auditoria automática do parser XML</h1><div class="subtitle">Central CT-e / DACTE 2.6.66.5 · sessão {escape(str(snapshot['session_id']))} · atualizado em {escape(str(snapshot['generated_at']))}</div>
<div class="grid"><div class="card">XMLs auditados<b>{totals['total']}</b></div><div class="card">Iguais<b>{totals['equal']}</b></div><div class="card">Informativas<b>{totals['informative']}</b></div><div class="card">Críticas<b>{totals['critical']}</b></div></div>
<div class="card promotion"><b style="font-size:17px">Regra de promoção</b>{escape(str(snapshot['promotion']['message']))}</div>
<div class="card"><table><thead><tr><th>#</th><th>Status</th><th>Arquivo</th><th>CT-e</th><th>Chave</th><th>Campos divergentes</th></tr></thead><tbody>{rows_html}</tbody></table></div>
{''.join(details)}
</main></body></html>"""
