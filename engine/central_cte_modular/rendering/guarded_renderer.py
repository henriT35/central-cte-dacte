from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Callable, Mapping

MODE_LEGACY_SHADOW = "legacy_shadow"
MODE_MODULAR_GUARDED = "modular_guarded"
VALID_MODES = {MODE_LEGACY_SHADOW, MODE_MODULAR_GUARDED}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _first_difference(left: str, right: str) -> dict[str, Any] | None:
    if left == right:
        return None
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    start = max(0, index - 80)
    end_left = min(len(left), index + 160)
    end_right = min(len(right), index + 160)
    return {
        "index": index,
        "legacy_excerpt": left[start:end_left],
        "modular_excerpt": right[start:end_right],
    }


class RendererPromotionReport:
    """Mantém a trilha de seleção do renderizador sem guardar o HTML completo."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.jsonl_path = self.directory / f"renderizador_{self.session_id}.jsonl"
        self._records: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(payload)
        with self._lock:
            self._records.append(item)
            with self.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
            self._write_latest()
        return item

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
        totals = {
            "renders": len(records),
            "selected_modular": sum(1 for item in records if item.get("selected") == "modular"),
            "selected_legacy": sum(1 for item in records if item.get("selected") == "legacy"),
            "exact_equal": sum(1 for item in records if item.get("exact_equal") is True),
            "html_differences": sum(1 for item in records if item.get("reason") == "html_different"),
            "renderer_errors": sum(1 for item in records if item.get("reason") == "modular_error"),
            "legacy_forced": sum(1 for item in records if item.get("reason") == "legacy_forced"),
        }
        return {
            "version": "2.6.66.6",
            "session_id": self.session_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "totals": totals,
            "records": records,
        }

    def _write_latest(self) -> None:
        snapshot = self.snapshot()
        (self.directory / "ultima_renderizacao.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        totals = snapshot["totals"]
        lines = [
            "CENTRAL CT-e / DACTE 2.6.66.6 - RENDERIZADOR MODULAR CONTROLADO",
            f"Sessão: {snapshot['session_id']}",
            f"Renderizações: {totals['renders']}",
            f"Modular selecionado: {totals['selected_modular']}",
            f"Legado selecionado: {totals['selected_legacy']}",
            f"HTML idêntico: {totals['exact_equal']}",
            f"Diferenças HTML: {totals['html_differences']}",
            f"Erros modulares: {totals['renderer_errors']}",
            "",
        ]
        for item in snapshot["records"]:
            lines.append(
                f"{item.get('timestamp', '')} | {item.get('kind', '')} | CT-e {item.get('numero', '')} "
                f"série {item.get('serie', '')} | selecionado={item.get('selected', '')} | motivo={item.get('reason', '')}"
            )
        (self.directory / "ultima_renderizacao.txt").write_text("\n".join(lines), encoding="utf-8")
        with (self.directory / "ultima_renderizacao.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "timestamp", "kind", "numero", "serie", "chave", "selected", "reason",
                    "exact_equal", "legacy_length", "modular_length", "legacy_sha256", "modular_sha256",
                ],
                extrasaction="ignore",
                delimiter=";",
            )
            writer.writeheader()
            writer.writerows(snapshot["records"])


class GuardedHtmlRenderer:
    """Seleciona o modular somente quando o HTML é byte a byte equivalente."""

    def __init__(
        self,
        legacy_dacte: Callable[[Mapping[str, Any]], str],
        legacy_summary: Callable[[Mapping[str, Any]], str],
        modular_dacte: Callable[[Mapping[str, Any]], str],
        modular_summary: Callable[[Mapping[str, Any]], str],
        reporter: RendererPromotionReport,
        get_mode: Callable[[], str],
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.legacy_dacte = legacy_dacte
        self.legacy_summary = legacy_summary
        self.modular_dacte = modular_dacte
        self.modular_summary = modular_summary
        self.reporter = reporter
        self.get_mode = get_mode
        self.log = log or (lambda _message: None)

    def _render(
        self,
        kind: str,
        info: Mapping[str, Any],
        legacy_function: Callable[[Mapping[str, Any]], str],
        modular_function: Callable[[Mapping[str, Any]], str],
    ) -> str:
        legacy_html = str(legacy_function(info))
        modular_html = ""
        modular_error = ""
        try:
            modular_html = str(modular_function(info))
        except Exception as exc:
            modular_error = f"{type(exc).__name__}: {exc}"

        exact_equal = not modular_error and legacy_html == modular_html
        mode = str(self.get_mode() or MODE_MODULAR_GUARDED).strip().lower()
        if mode not in VALID_MODES:
            mode = MODE_MODULAR_GUARDED

        if modular_error:
            selected = "legacy"
            reason = "modular_error"
            output = legacy_html
        elif mode == MODE_LEGACY_SHADOW:
            selected = "legacy"
            reason = "legacy_forced"
            output = legacy_html
        elif exact_equal:
            selected = "modular"
            reason = "equivalencia_html_exata"
            output = modular_html
        else:
            selected = "legacy"
            reason = "html_different"
            output = legacy_html

        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "numero": str(info.get("numero") or ""),
            "serie": str(info.get("serie") or ""),
            "chave": str(info.get("chave") or ""),
            "arquivo": str(info.get("arquivo") or info.get("path") or ""),
            "mode": mode,
            "selected": selected,
            "reason": reason,
            "exact_equal": bool(exact_equal),
            "legacy_length": len(legacy_html),
            "modular_length": len(modular_html),
            "legacy_sha256": _sha256_text(legacy_html),
            "modular_sha256": _sha256_text(modular_html) if not modular_error else "",
            "modular_error": modular_error,
            "first_difference": _first_difference(legacy_html, modular_html) if not exact_equal and not modular_error else None,
        }
        try:
            self.reporter.record(payload)
        except Exception as exc:
            self.log(f"Falha ao gravar auditoria do renderizador: {exc}")
        return output

    def render_dacte(self, info: Mapping[str, Any]) -> str:
        return self._render("dacte", info, self.legacy_dacte, self.modular_dacte)

    def render_summary(self, info: Mapping[str, Any]) -> str:
        return self._render("summary", info, self.legacy_summary, self.modular_summary)
