from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Iterable, Mapping
import csv
import io
import json

CATALOG_VERSION = "2.6.66.5"


class ParserAuditCatalog:
    """Consolida todas as sessões JSONL da auditoria do parser.

    O catálogo considera somente a ocorrência mais recente de cada conteúdo XML,
    identificado por SHA-256. Quando o hash não está disponível, usa o caminho do
    arquivo como chave de contingência. O XML fiscal nunca é alterado nem copiado.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def rebuild(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        self._write_outputs(snapshot)
        return snapshot

    def snapshot(self) -> dict[str, Any]:
        records, errors, sessions = self._load_records()
        unique = self._deduplicate(records)
        totals = self._counts(unique)
        return {
            "version": CATALOG_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "report_directory": str(self.directory),
            "sessions": sessions,
            "source_files": [path.name for path in self._jsonl_files()],
            "read_errors": errors,
            "totals": totals,
            "promotion": {
                "allowed_by_audit": totals["total"] > 0 and totals["critical"] == 0,
                "message": self._promotion_message(totals),
            },
            "records": unique,
        }

    def _jsonl_files(self) -> list[Path]:
        return sorted(self.directory.glob("auditoria_parser_*.jsonl"), key=lambda path: path.name)

    def _load_records(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        records: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        files = self._jsonl_files()
        for path in files:
            try:
                with path.open("r", encoding="utf-8") as stream:
                    for line_number, raw_line in enumerate(stream, start=1):
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except Exception as exc:
                            errors.append({
                                "file": path.name,
                                "line": line_number,
                                "error": f"{type(exc).__name__}: {exc}",
                            })
                            continue
                        if isinstance(payload, Mapping):
                            item = dict(payload)
                            item.setdefault("session_file", path.name)
                            records.append(item)
            except Exception as exc:
                errors.append({
                    "file": path.name,
                    "line": 0,
                    "error": f"{type(exc).__name__}: {exc}",
                })
        return records, errors, len(files)

    @staticmethod
    def _deduplicate(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for index, source in enumerate(records):
            item = dict(source)
            digest = str(item.get("sha256") or "").strip().lower()
            path = str(item.get("path") or item.get("arquivo") or "").strip()
            key = f"sha256:{digest}" if digest else f"path:{path.casefold()}"
            if key not in latest:
                order.append(key)
            item["catalog_sequence"] = index + 1
            latest[key] = item
        result = [latest[key] for key in order if key in latest]
        result.sort(key=lambda item: (
            str(item.get("status") or ""),
            str(item.get("cte") or item.get("arquivo") or ""),
            str(item.get("timestamp") or ""),
        ))
        return result

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
    def _promotion_message(totals: Mapping[str, int]) -> str:
        if int(totals.get("total", 0)) == 0:
            return "Aguardando importação de XMLs reais."
        if int(totals.get("critical", 0)):
            return f"Promoção bloqueada: {totals['critical']} XML(s) com divergência crítica no histórico consolidado."
        if int(totals.get("informative", 0)):
            return "Sem divergências críticas; diferenças informativas ainda precisam ser justificadas antes da promoção."
        return "Sem divergências detectadas no histórico consolidado; ainda exige homologação operacional no Windows."

    def _write_outputs(self, snapshot: dict[str, Any]) -> None:
        self._atomic_write(
            self.directory / "auditoria_consolidada.json",
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        )
        self._atomic_write(self.directory / "auditoria_consolidada.txt", self._render_text(snapshot))
        self._atomic_write(self.directory / "auditoria_consolidada.html", self._render_html(snapshot))
        self._atomic_write(self.directory / "divergencias.csv", self._render_csv(snapshot))

        records = list(snapshot.get("records") or [])
        filters = {
            "divergencias_criticas.json": [item for item in records if item.get("status") == "CRÍTICA"],
            "divergencias_informativas.json": [item for item in records if item.get("status") == "INFORMATIVA"],
            "xmls_iguais.json": [item for item in records if item.get("status") == "IGUAL"],
        }
        for filename, selected in filters.items():
            payload = {
                "version": CATALOG_VERSION,
                "generated_at": snapshot.get("generated_at"),
                "count": len(selected),
                "records": selected,
            }
            self._atomic_write(
                self.directory / filename,
                json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _render_text(snapshot: Mapping[str, Any]) -> str:
        totals = snapshot["totals"]
        lines = [
            "CENTRAL CT-e / DACTE 2.6.66.5 - AUDITORIA REAL CONSOLIDADA DO PARSER XML",
            f"Atualização: {snapshot.get('generated_at', '')}",
            f"Sessões lidas: {snapshot.get('sessions', 0)}",
            "",
            f"XMLs únicos auditados: {totals['total']}",
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
                f"   Caminho: {item.get('path', '')}",
                f"   CT-e: {item.get('cte', '')}  Série: {item.get('serie', '')}",
                f"   Chave: {item.get('chave', '')}",
                f"   SHA-256: {item.get('sha256', '')}",
                f"   Campos: {fields}",
                "",
            ])
        errors = snapshot.get("read_errors") or []
        if errors:
            lines.append("ERROS DE LEITURA DOS ARQUIVOS JSONL")
            for item in errors:
                lines.append(f"- {item.get('file')} linha {item.get('line')}: {item.get('error')}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _render_csv(snapshot: Mapping[str, Any]) -> str:
        output = io.StringIO()
        writer = csv.writer(output, delimiter=";", lineterminator="\n")
        writer.writerow([
            "Status", "Arquivo", "Caminho", "CT-e", "Série", "Chave",
            "SHA-256", "Campos divergentes", "Críticas", "Informativas", "Data auditoria",
        ])
        for item in snapshot.get("records") or []:
            differences = item.get("differences") or {}
            writer.writerow([
                item.get("status", ""),
                item.get("arquivo", ""),
                item.get("path", ""),
                item.get("cte", ""),
                item.get("serie", ""),
                item.get("chave", ""),
                item.get("sha256", ""),
                ", ".join(differences.keys()),
                item.get("critical_count", 0),
                item.get("informative_count", 0),
                item.get("timestamp", ""),
            ])
        return "\ufeff" + output.getvalue()

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
                        f"<td>{escape(str(field_name))}</td>"
                        f"<td>{escape(str(difference.get('severity', '')))}</td>"
                        f"<td><pre>{escape(legacy)}</pre></td>"
                        f"<td><pre>{escape(modular)}</pre></td>"
                        "</tr>"
                    )
                details.append(
                    f"<details class='detail {css}'><summary>{escape(str(item.get('arquivo', '')))} - {escape(status)}</summary>"
                    f"<div class='path'>{escape(str(item.get('path', '')))}</div>"
                    "<table><thead><tr><th>Campo</th><th>Classe</th><th>Legado</th><th>Modular</th></tr></thead>"
                    f"<tbody>{''.join(diff_rows)}</tbody></table></details>"
                )
        rows_html = "".join(rows) or "<tr><td colspan='6' class='empty'>Nenhum XML real auditado.</td></tr>"
        return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Auditoria consolidada do Parser XML 2.6.66.5</title>
<style>
:root{{--bg:#f4f6f8;--card:#fff;--text:#17212b;--muted:#64748b;--line:#dbe2ea;--ok:#15803d;--info:#a16207;--critical:#b91c1c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px Arial,sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}
h1{{margin:0 0 6px;font-size:25px}}.subtitle,.path{{color:var(--muted);overflow-wrap:anywhere}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px;margin:18px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}}.card b{{display:block;font-size:26px;margin-top:5px}}.promotion{{margin:12px 0 18px;border-left:5px solid var(--info)}}
table{{width:100%;border-collapse:collapse;background:var(--card)}}th,td{{border:1px solid var(--line);padding:9px;vertical-align:top;text-align:left}}th{{background:#eef2f6}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;font:12px Consolas,monospace}}
.badge{{display:inline-block;border-radius:999px;padding:4px 9px;font-weight:700;background:#e2e8f0}}.badge.ok{{background:#dcfce7;color:var(--ok)}}.badge.info{{background:#fef3c7;color:var(--info)}}.badge.critical{{background:#fee2e2;color:var(--critical)}}
.detail{{margin-top:12px;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--info);border-radius:10px;padding:10px}}.detail.critical{{border-left-color:var(--critical)}}.detail.ok{{border-left-color:var(--ok)}}summary{{cursor:pointer;font-weight:700;padding:5px}}.empty{{text-align:center;color:var(--muted);padding:30px}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr 1fr}}main{{padding:12px}}table{{font-size:12px}}}}
</style></head><body><main>
<h1>Auditoria real consolidada do parser XML</h1>
<div class="subtitle">Central CT-e / DACTE 2.6.66.5 · {snapshot.get('sessions', 0)} sessão(ões) · atualizado em {escape(str(snapshot.get('generated_at', '')))}</div>
<div class="grid"><div class="card">XMLs únicos<b>{totals['total']}</b></div><div class="card">Iguais<b>{totals['equal']}</b></div><div class="card">Informativas<b>{totals['informative']}</b></div><div class="card">Críticas<b>{totals['critical']}</b></div></div>
<div class="card promotion"><b style="font-size:17px">Regra de promoção</b>{escape(str(snapshot['promotion']['message']))}</div>
<div class="card"><table><thead><tr><th>#</th><th>Status</th><th>Arquivo</th><th>CT-e</th><th>Chave</th><th>Campos divergentes</th></tr></thead><tbody>{rows_html}</tbody></table></div>
{''.join(details)}
</main></body></html>"""
