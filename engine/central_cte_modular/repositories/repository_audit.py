from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import threading
import time
from typing import Any, Callable, Mapping

MODE_LEGACY_SHADOW = "legacy_shadow"
MODE_MODULAR_GUARDED = "modular_guarded"
VALID_MODES = {MODE_LEGACY_SHADOW, MODE_MODULAR_GUARDED}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _short(value: Any, limit: int = 240) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _first_difference(left: Any, right: Any, path: str = "$") -> dict[str, str] | None:
    if left == right:
        return None
    if type(left) is not type(right):
        return {"path": path, "legacy": _short(left), "modular": _short(right)}
    if isinstance(left, Mapping):
        keys = sorted(set(left) | set(right), key=str)
        for key in keys:
            if key not in left:
                return {"path": f"{path}.{key}", "legacy": "<ausente>", "modular": _short(right[key])}
            if key not in right:
                return {"path": f"{path}.{key}", "legacy": _short(left[key]), "modular": "<ausente>"}
            found = _first_difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(left, (list, tuple)):
        if len(left) != len(right):
            return {"path": path, "legacy": f"len={len(left)}", "modular": f"len={len(right)}"}
        for index, (a, b) in enumerate(zip(left, right)):
            found = _first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
        return None
    return {"path": path, "legacy": _short(left), "modular": _short(right)}


class RepositoryAuditReport:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.jsonl_path = self.directory / f"repositorios_{self.session_id}.jsonl"
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
            "audits": len(records),
            "partner_modular_selected": sum(1 for item in records if item.get("kind") == "tabelas_parceiros" and item.get("selected") == "modular"),
            "partner_legacy_selected": sum(1 for item in records if item.get("kind") == "tabelas_parceiros" and item.get("selected") == "legacy"),
            "base_modular_selected": sum(1 for item in records if item.get("kind") == "base_rodovitor_completa" and item.get("selected") == "modular"),
            "base_legacy_selected": sum(1 for item in records if item.get("kind") == "base_rodovitor_completa" and item.get("selected") == "legacy"),
            "base_cache_hits": sum(1 for item in records if item.get("kind") == "base_rodovitor_completa" and item.get("cache_status") == "HIT"),
            "base_full_loads": sum(1 for item in records if item.get("kind") == "base_rodovitor_completa" and item.get("reason") in {"modular_xlsx_loaded", "modular_sswweb_loaded"}),
            "base_sswweb_loads": sum(1 for item in records if item.get("kind") == "base_rodovitor_completa" and item.get("reason") == "modular_sswweb_loaded"),
            "base_fallbacks": sum(1 for item in records if item.get("kind") == "base_rodovitor_completa" and item.get("reason") == "modular_error_fallback_legacy"),
            "base_samples_equal": sum(1 for item in records if item.get("kind") == "base_rodovitor_amostra" and item.get("exact_equal") is True),
            "differences": sum(1 for item in records if item.get("reason") in {"data_different", "sample_different", "shadow_different"}),
            "errors": sum(1 for item in records if item.get("reason") in {"modular_error", "sample_error", "modular_error_fallback_legacy"}),
        }
        return {
            "version": "2.6.67.7",
            "session_id": self.session_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "totals": totals,
            "records": records,
        }

    def _write_latest(self) -> None:
        snapshot = self.snapshot()
        (self.directory / "ultima_auditoria_repositorios.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        totals = snapshot["totals"]
        lines = [
            "CENTRAL CT-e / DACTE 2.6.67.7 - BASE RODOVITOR TOTALMENTE MODULAR",
            f"Sessão: {snapshot['session_id']}",
            f"Auditorias: {totals['audits']}",
            f"Tabelas com modular selecionado: {totals['partner_modular_selected']}",
            f"Tabelas com legado selecionado: {totals['partner_legacy_selected']}",
            f"Cargas completas da base no modular: {totals['base_modular_selected']}",
            f"Cargas completas da base no legado: {totals['base_legacy_selected']}",
            f"Acertos do cache modular: {totals['base_cache_hits']}",
            f"Leituras completas modulares: {totals['base_full_loads']}",
            f"Leituras SSW Web completas: {totals.get('base_sswweb_loads', 0)}",
            f"Fallbacks da base para o legado: {totals['base_fallbacks']}",
            f"Amostras históricas idênticas: {totals['base_samples_equal']}",
            f"Diferenças: {totals['differences']}",
            f"Erros: {totals['errors']}",
            "",
        ]
        for item in snapshot["records"]:
            lines.append(
                f"{item.get('timestamp', '')} | {item.get('kind', '')} | {Path(item.get('file_path', '')).name} | "
                f"selecionado={item.get('selected', '')} | motivo={item.get('reason', '')} | "
                f"amostra={item.get('sample_rows', '')} | iguais={item.get('matched_rows', '')} | "
                f"linhas={item.get('total_rows', '')} | nfs={item.get('total_nfs', '')} | cache={item.get('cache_status', '')}"
            )
            difference = item.get("first_difference") or {}
            if difference:
                lines.append(
                    f"  {difference.get('path', '')}: legado={difference.get('legacy', '')}; modular={difference.get('modular', '')}"
                )
        (self.directory / "ultima_auditoria_repositorios.txt").write_text("\n".join(lines), encoding="utf-8")
        with (self.directory / "ultima_auditoria_repositorios.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            fields = [
                "timestamp", "kind", "file_path", "selected", "reason", "exact_equal",
                "legacy_seconds", "modular_seconds", "sample_rows", "matched_rows", "mismatched_rows",
                "total_rows", "total_nfs", "cache_status", "cache_path", "source_sha256", "mode",
                "legacy_sha256", "modular_sha256", "modular_error", "first_difference_path", "first_legacy", "first_modular",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            for item in snapshot["records"]:
                difference = item.get("first_difference") or {}
                writer.writerow({
                    **item,
                    "first_difference_path": difference.get("path", ""),
                    "first_legacy": difference.get("legacy", ""),
                    "first_modular": difference.get("modular", ""),
                })


class PartnerTableGuard:
    """Promove tabelas modulares somente em igualdade estrutural completa."""

    def __init__(
        self,
        legacy_loader: Callable[[str | Path], dict[str, Any]],
        modular_loader: Callable[[str | Path], dict[str, Any]],
        report: RepositoryAuditReport,
        get_mode: Callable[[], str],
    ) -> None:
        self.legacy_loader = legacy_loader
        self.modular_loader = modular_loader
        self.report = report
        self.get_mode = get_mode

    def load(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        started = time.perf_counter()
        legacy = self.legacy_loader(path)
        legacy_seconds = time.perf_counter() - started
        modular: dict[str, Any] | None = None
        modular_error = ""
        started = time.perf_counter()
        try:
            modular = self.modular_loader(path)
        except Exception as exc:
            modular_error = f"{type(exc).__name__}: {exc}"
        modular_seconds = time.perf_counter() - started
        exact = not modular_error and legacy == modular
        mode = str(self.get_mode() or MODE_MODULAR_GUARDED).strip().lower()
        if mode not in VALID_MODES:
            mode = MODE_MODULAR_GUARDED
        if modular_error:
            selected, reason, output = "legacy", "modular_error", legacy
        elif mode == MODE_LEGACY_SHADOW:
            selected, reason, output = "legacy", "legacy_forced", legacy
        elif exact:
            selected, reason, output = "modular", "equivalencia_estrutural_exata", modular
        else:
            selected, reason, output = "legacy", "data_different", legacy
        self.report.record({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "kind": "tabelas_parceiros",
            "file_path": str(path),
            "selected": selected,
            "reason": reason,
            "exact_equal": bool(exact),
            "legacy_seconds": round(legacy_seconds, 4),
            "modular_seconds": round(modular_seconds, 4),
            "legacy_sha256": _sha(legacy),
            "modular_sha256": _sha(modular) if modular is not None else "",
            "sample_rows": "",
            "matched_rows": "",
            "mismatched_rows": "",
            "modular_error": modular_error,
            "first_difference": _first_difference(legacy, modular) if not exact and modular is not None else None,
        })
        return output


class BaseSampleAuditor:
    """Audita uma amostra limitada da base sem duplicar a carga completa em memória."""

    def __init__(self, repository: Any, report: RepositoryAuditReport, sample_size: int = 500) -> None:
        self.repository = repository
        self.report = report
        self.sample_size = max(1, int(sample_size))

    def audit(self, file_path: str | Path, legacy_data: Mapping[str, Any]) -> dict[str, Any]:
        path = Path(file_path)
        started = time.perf_counter()
        try:
            modular_sample = self.repository.load_sample(path, self.sample_size)
            modular_seconds = time.perf_counter() - started
            sample_rows = list(modular_sample.get("rows", []) or [])
            sampled_nfs = {str(row.get("nf") or "") for row in sample_rows}
            legacy_counters: dict[str, Counter[str]] = {}
            legacy_originals: dict[tuple[str, str], dict[str, Any]] = {}
            legacy_index = legacy_data.get("index", {}) if isinstance(legacy_data, Mapping) else {}
            for nf in sampled_nfs:
                counter: Counter[str] = Counter()
                for row in legacy_index.get(nf, []) or []:
                    key = _json(row)
                    counter[key] += 1
                    legacy_originals[(nf, key)] = row
                legacy_counters[nf] = counter

            matched = 0
            mismatches: list[dict[str, Any]] = []
            for row in sample_rows:
                nf = str(row.get("nf") or "")
                key = _json(row)
                counter = legacy_counters.get(nf)
                if counter and counter.get(key, 0) > 0:
                    counter[key] -= 1
                    matched += 1
                    continue
                candidates = list(legacy_index.get(nf, []) or [])
                mismatches.append({
                    "nf": nf,
                    "modular": row,
                    "legacy": candidates[0] if candidates else None,
                })

            exact = bool(sample_rows) and not mismatches and matched == len(sample_rows)
            first = None
            if mismatches:
                mismatch = mismatches[0]
                first = _first_difference(mismatch.get("legacy"), mismatch.get("modular"), f"$.nf[{mismatch.get('nf', '')}]")
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "kind": "base_rodovitor_amostra",
                "file_path": str(path),
                "selected": "legacy",
                "reason": "sample_equal" if exact else "sample_different",
                "exact_equal": exact,
                "legacy_seconds": 0.0,
                "modular_seconds": round(modular_seconds, 4),
                "sample_rows": len(sample_rows),
                "matched_rows": matched,
                "mismatched_rows": len(mismatches),
                "total_legacy_rows": len(legacy_data.get("rows", []) or []) if isinstance(legacy_data, Mapping) else 0,
                "legacy_sha256": "",
                "modular_sha256": _sha(sample_rows),
                "first_difference": first,
                "note": "A base completa permanece legada; somente uma amostra limitada é auditada nesta etapa.",
            }
        except Exception as exc:
            payload = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "kind": "base_rodovitor_amostra",
                "file_path": str(path),
                "selected": "legacy",
                "reason": "sample_error",
                "exact_equal": False,
                "legacy_seconds": 0.0,
                "modular_seconds": round(time.perf_counter() - started, 4),
                "sample_rows": 0,
                "matched_rows": 0,
                "mismatched_rows": 0,
                "legacy_sha256": "",
                "modular_sha256": "",
                "modular_error": f"{type(exc).__name__}: {exc}",
                "first_difference": None,
            }
        self.report.record(payload)
        return payload
