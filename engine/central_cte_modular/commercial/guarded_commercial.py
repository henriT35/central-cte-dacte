from __future__ import annotations

import csv
import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

MODE_LEGACY_SHADOW = "legacy_shadow"
MODE_MODULAR_GUARDED = "modular_guarded"
VALID_MODES = {MODE_LEGACY_SHADOW, MODE_MODULAR_GUARDED}


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    except Exception:
        return repr(value)


def _sha(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8", errors="replace")).hexdigest()


def _first_difference(legacy: Any, modular: Any, path: str = "$") -> dict[str, Any] | None:
    if type(legacy) is not type(modular):
        return {"path": path, "legacy": legacy, "modular": modular}
    if isinstance(legacy, Mapping):
        keys = list(dict.fromkeys([*legacy.keys(), *modular.keys()]))
        for key in keys:
            if key not in legacy or key not in modular:
                return {"path": f"{path}.{key}", "legacy": legacy.get(key), "modular": modular.get(key)}
            difference = _first_difference(legacy[key], modular[key], f"{path}.{key}")
            if difference:
                return difference
        return None
    if isinstance(legacy, (list, tuple)):
        if len(legacy) != len(modular):
            return {"path": f"{path}.length", "legacy": len(legacy), "modular": len(modular)}
        for index, (legacy_value, modular_value) in enumerate(zip(legacy, modular)):
            difference = _first_difference(legacy_value, modular_value, f"{path}[{index}]")
            if difference:
                return difference
        return None
    if legacy != modular:
        return {"path": path, "legacy": legacy, "modular": modular}
    return None


class CommercialAuditReport:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.jsonl_path = self.directory / f"motor_comercial_{self.session_id}.jsonl"
        self._records: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        self._lock = threading.RLock()

    def record(self, payload: Mapping[str, Any], *, deduplicate: bool = True) -> dict[str, Any]:
        item = dict(payload)
        signature = str(item.get("signature") or "")
        with self._lock:
            if deduplicate and signature and signature in self._seen:
                return item
            if signature:
                self._seen.add(signature)
            self._records.append(item)
            with self.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            self._write_latest()
        return item

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
        totals = {
            "operations": len(records),
            "modular_selected": sum(1 for item in records if item.get("selected") == "modular"),
            "legacy_selected": sum(1 for item in records if item.get("selected") == "legacy"),
            "exact_equal": sum(1 for item in records if item.get("exact_equal") is True),
            "differences": sum(1 for item in records if item.get("reason") == "result_different"),
            "errors": sum(1 for item in records if item.get("reason") in {"modular_error", "legacy_error"}),
        }
        by_operation: dict[str, dict[str, int]] = {}
        for item in records:
            operation = str(item.get("operation") or "")
            bucket = by_operation.setdefault(operation, {"total": 0, "modular": 0, "legacy": 0, "differences": 0, "errors": 0})
            bucket["total"] += 1
            bucket[str(item.get("selected") or "legacy")] += 1
            if item.get("reason") == "result_different":
                bucket["differences"] += 1
            if item.get("reason") in {"modular_error", "legacy_error"}:
                bucket["errors"] += 1
        return {
            "version": "2.6.66.8",
            "session_id": self.session_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "totals": totals,
            "by_operation": by_operation,
            "records": records,
        }

    def _write_latest(self) -> None:
        snapshot = self.snapshot()
        (self.directory / "ultima_auditoria_comercial.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        totals = snapshot["totals"]
        lines = [
            "CENTRAL CT-e / DACTE 2.6.66.8 - MOTOR COMERCIAL MODULAR CONTROLADO",
            f"Sessão: {snapshot['session_id']}",
            f"Operações únicas auditadas: {totals['operations']}",
            f"Modular selecionado: {totals['modular_selected']}",
            f"Legado selecionado: {totals['legacy_selected']}",
            f"Resultados idênticos: {totals['exact_equal']}",
            f"Divergências: {totals['differences']}",
            f"Erros: {totals['errors']}",
            "",
        ]
        for operation, counts in snapshot["by_operation"].items():
            lines.append(
                f"{operation}: total={counts['total']} modular={counts['modular']} legado={counts['legacy']} "
                f"divergências={counts['differences']} erros={counts['errors']}"
            )
        lines.append("")
        for item in snapshot["records"]:
            lines.append(
                f"{item.get('timestamp', '')} | {item.get('operation', '')} | selecionado={item.get('selected', '')} | "
                f"motivo={item.get('reason', '')} | contexto={item.get('context', '')}"
            )
            difference = item.get("first_difference") or {}
            if difference:
                lines.append(
                    f"  {difference.get('path', '')}: legado={difference.get('legacy', '')}; modular={difference.get('modular', '')}"
                )
        (self.directory / "ultima_auditoria_comercial.txt").write_text("\n".join(lines), encoding="utf-8")
        with (self.directory / "ultima_auditoria_comercial.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            fields = [
                "timestamp", "operation", "context", "selected", "reason", "exact_equal",
                "legacy_seconds", "modular_seconds", "legacy_sha256", "modular_sha256",
                "first_difference_path", "first_legacy", "first_modular", "modular_error", "legacy_error",
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


class CommercialFunctionGuard:
    """Compara uma função comercial legada com sua equivalente modular.

    O controle local evita que uma função legada chame acidentalmente outra
    função já promovida durante a própria medição. Assim a auditoria compara
    duas trilhas realmente separadas.
    """

    def __init__(self, report: CommercialAuditReport, get_mode: Callable[[], str]) -> None:
        self.report = report
        self.get_mode = get_mode
        self._local = threading.local()

    def wrap(
        self,
        operation: str,
        legacy: Callable[..., Any],
        modular: Callable[..., Any],
        context_builder: Callable[..., Any] | None = None,
    ) -> Callable[..., Any]:
        def guarded(*args: Any, **kwargs: Any) -> Any:
            if getattr(self._local, "inside_legacy", False):
                return legacy(*args, **kwargs)
            if getattr(self._local, "inside_modular", False):
                return modular(*args, **kwargs)

            legacy_error = ""
            legacy_exception: Exception | None = None
            modular_error = ""
            legacy_value: Any = None
            modular_value: Any = None
            legacy_started = time.perf_counter()
            try:
                self._local.inside_legacy = True
                legacy_value = legacy(*args, **kwargs)
            except Exception as exc:
                legacy_exception = exc
                legacy_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._local.inside_legacy = False
            legacy_seconds = time.perf_counter() - legacy_started
            if legacy_error:
                self.report.record({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "operation": operation,
                    "context": self._context(context_builder, args, kwargs),
                    "selected": "legacy",
                    "reason": "legacy_error",
                    "exact_equal": False,
                    "legacy_seconds": round(legacy_seconds, 6),
                    "modular_seconds": 0.0,
                    "legacy_error": legacy_error,
                    "modular_error": "",
                    "signature": _sha([operation, self._context(context_builder, args, kwargs), legacy_error]),
                }, deduplicate=False)
                assert legacy_exception is not None
                raise legacy_exception

            modular_started = time.perf_counter()
            try:
                self._local.inside_modular = True
                modular_value = modular(*args, **kwargs)
            except Exception as exc:
                modular_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._local.inside_modular = False
            modular_seconds = time.perf_counter() - modular_started

            exact = not modular_error and legacy_value == modular_value
            mode = str(self.get_mode() or MODE_MODULAR_GUARDED).strip().lower()
            if mode not in VALID_MODES:
                mode = MODE_MODULAR_GUARDED
            if modular_error:
                selected, reason, output = "legacy", "modular_error", legacy_value
            elif mode == MODE_LEGACY_SHADOW:
                selected, reason, output = "legacy", "legacy_forced", legacy_value
            elif exact:
                selected, reason, output = "modular", "equivalencia_exata", modular_value
            else:
                selected, reason, output = "legacy", "result_different", legacy_value

            context = self._context(context_builder, args, kwargs)
            signature = _sha([operation, context, selected, reason, legacy_value, modular_value, modular_error])
            self.report.record({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "operation": operation,
                "context": context,
                "selected": selected,
                "reason": reason,
                "exact_equal": bool(exact),
                "legacy_seconds": round(legacy_seconds, 6),
                "modular_seconds": round(modular_seconds, 6),
                "legacy_sha256": _sha(legacy_value),
                "modular_sha256": _sha(modular_value) if not modular_error else "",
                "modular_error": modular_error,
                "legacy_error": "",
                "first_difference": _first_difference(legacy_value, modular_value) if not exact and not modular_error else None,
                "signature": signature,
            })
            return output

        guarded.__name__ = getattr(legacy, "__name__", operation)
        guarded.__doc__ = getattr(legacy, "__doc__", None)
        guarded.__wrapped__ = legacy
        guarded._commercial_operation = operation
        return guarded

    @staticmethod
    def _context(builder: Callable[..., Any] | None, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if builder is None:
            return ""
        try:
            return builder(*args, **kwargs)
        except Exception:
            return ""
