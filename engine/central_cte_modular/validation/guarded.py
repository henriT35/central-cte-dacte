from __future__ import annotations

import csv
import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

MODE_MODULAR_GUARDED = "modular_guarded"
MODE_SHADOW = "shadow"
MODE_LEGACY = "legacy"
VALID_MODES = {MODE_MODULAR_GUARDED, MODE_SHADOW, MODE_LEGACY}
AUDIT_VERSION = "2.6.67.8"


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


def _context(info: Any) -> dict[str, Any]:
    if not isinstance(info, Mapping):
        return {}
    emit = info.get("emit", {}) or {}
    docs = info.get("documentos", []) or []
    nfs: list[str] = []
    for item in docs:
        if not isinstance(item, Mapping):
            continue
        number = str(item.get("numero") or item.get("nDoc") or "").strip()
        if number and number not in nfs:
            nfs.append(number)
    return {
        "cte": str(info.get("numero") or ""),
        "serie": str(info.get("serie") or ""),
        "chave": str(info.get("chave") or ""),
        "emitente": str(info.get("emitente") or emit.get("nome") or ""),
        "cnpj": str(emit.get("cnpjcpf") or emit.get("cnpj") or ""),
        "nfs": nfs,
    }


class ValidationAuditReport:
    """Persistência compacta da promoção do orquestrador de validação."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.jsonl_path = self.directory / f"orquestrador_validacao_{self.session_id}.jsonl"
        self._records: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def record(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        item = dict(payload)
        with self._lock:
            self._records.append(item)
            with self.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
            self._write_latest()
        return item

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = list(self._records)
        totals = {
            "validations": len(records),
            "modular_selected": sum(1 for item in records if item.get("selected") == "modular"),
            "legacy_selected": sum(1 for item in records if item.get("selected") == "legacy"),
            "legacy_invocations": sum(1 for item in records if item.get("legacy_invoked") is True),
            "shadow_comparisons": sum(1 for item in records if item.get("mode") == MODE_SHADOW),
            "exact_equal": sum(1 for item in records if item.get("exact_equal") is True),
            "differences": sum(1 for item in records if item.get("reason") == "result_different"),
            "fallbacks": sum(1 for item in records if str(item.get("reason") or "").startswith("fallback_")),
            "modular_errors": sum(1 for item in records if item.get("modular_error")),
            "legacy_errors": sum(1 for item in records if item.get("legacy_error")),
        }
        return {
            "version": AUDIT_VERSION,
            "session_id": self.session_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "totals": totals,
            "records": records,
        }

    def _write_latest(self) -> None:
        snapshot = self.snapshot()
        json_path = self.directory / "ultima_auditoria_orquestrador.json"
        txt_path = self.directory / "ultima_auditoria_orquestrador.txt"
        csv_path = self.directory / "ultima_auditoria_orquestrador.csv"
        json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        totals = snapshot["totals"]
        lines = [
            "CENTRAL CT-e / DACTE 2.6.67.8 - ORQUESTRADOR DE VALIDAÇÃO MODULAR",
            f"Sessão: {snapshot['session_id']}",
            f"Validações: {totals['validations']}",
            f"Modular selecionado: {totals['modular_selected']}",
            f"Legado selecionado: {totals['legacy_selected']}",
            f"Chamadas ao orquestrador legado: {totals['legacy_invocations']}",
            f"Comparações em sombra: {totals['shadow_comparisons']}",
            f"Resultados idênticos: {totals['exact_equal']}",
            f"Divergências: {totals['differences']}",
            f"Fallbacks: {totals['fallbacks']}",
            f"Erros modulares: {totals['modular_errors']}",
            f"Erros legados: {totals['legacy_errors']}",
            "",
        ]
        for item in snapshot["records"]:
            context = item.get("context") or {}
            lines.append(
                f"{item.get('timestamp', '')} | CT-e {context.get('cte', '-')}/{context.get('serie', '-')} | "
                f"modo={item.get('mode', '')} | selecionado={item.get('selected', '')} | motivo={item.get('reason', '')}"
            )
            difference = item.get("first_difference") or {}
            if difference:
                lines.append(
                    f"  {difference.get('path', '')}: legado={difference.get('legacy', '')}; modular={difference.get('modular', '')}"
                )
            if item.get("modular_error"):
                lines.append(f"  erro modular: {item.get('modular_error')}")
            if item.get("legacy_error"):
                lines.append(f"  erro legado: {item.get('legacy_error')}")
        txt_path.write_text("\n".join(lines), encoding="utf-8")

        fields = [
            "timestamp", "mode", "selected", "reason", "legacy_invoked", "exact_equal",
            "cte", "serie", "chave", "emitente", "cnpj", "nfs",
            "modular_seconds", "legacy_seconds", "modular_sha256", "legacy_sha256",
            "first_difference_path", "first_legacy", "first_modular", "modular_error", "legacy_error",
        ]
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter=";", extrasaction="ignore")
            writer.writeheader()
            for item in snapshot["records"]:
                context = item.get("context") or {}
                difference = item.get("first_difference") or {}
                writer.writerow({
                    **item,
                    **context,
                    "nfs": ", ".join(context.get("nfs") or []),
                    "first_difference_path": difference.get("path", ""),
                    "first_legacy": difference.get("legacy", ""),
                    "first_modular": difference.get("modular", ""),
                })


class GuardedValidationOrchestrator:
    """Promove o orquestrador modular sem dupla execução no fluxo padrão."""

    def __init__(
        self,
        modular_validate: Callable[[Any, Any, Any], Any],
        legacy_validate: Callable[[Any, Any, Any], Any],
        report: ValidationAuditReport,
        get_mode: Callable[[], str],
        *,
        postprocess: Callable[[Any, Any, Any, Any], Any] | None = None,
        contract_validator: Callable[[Any], Any] | None = None,
    ) -> None:
        self.modular_validate = modular_validate
        self.legacy_validate = legacy_validate
        self.report = report
        self.get_mode = get_mode
        self.postprocess = postprocess
        self.contract_validator = contract_validator
        self._local = threading.local()

    def _run_modular(self, info: Any, base_data: Any, tables: Any) -> Any:
        result = self.modular_validate(info, base_data, tables)
        if self.contract_validator is not None:
            result = self.contract_validator(result)
        if self.postprocess is not None:
            result = self.postprocess(result, info, base_data, tables)
        if self.contract_validator is not None:
            result = self.contract_validator(result)
        return result

    def validate(self, info: Any, base_data: Any, tables: Any) -> Any:
        # Evita recursão se alguma dependência indireta voltar ao ponto de entrada.
        if getattr(self._local, "inside_legacy", False):
            return self.legacy_validate(info, base_data, tables)
        if getattr(self._local, "inside_modular", False):
            return self._run_modular(info, base_data, tables)

        mode = self.get_mode()
        context = _context(info)
        timestamp = datetime.now().isoformat(timespec="seconds")

        if mode == MODE_LEGACY:
            started = time.perf_counter()
            try:
                self._local.inside_legacy = True
                result = self.legacy_validate(info, base_data, tables)
            finally:
                self._local.inside_legacy = False
            seconds = time.perf_counter() - started
            self.report.record({
                "timestamp": timestamp,
                "context": context,
                "mode": mode,
                "selected": "legacy",
                "reason": "legacy_forced",
                "legacy_invoked": True,
                "exact_equal": None,
                "legacy_seconds": round(seconds, 6),
                "modular_seconds": 0.0,
                "legacy_sha256": _sha(result),
                "modular_sha256": "",
                "legacy_error": "",
                "modular_error": "",
                "first_difference": None,
            })
            return result

        if mode == MODE_SHADOW:
            legacy_error = ""
            modular_error = ""
            legacy_value: Any = None
            modular_value: Any = None

            legacy_started = time.perf_counter()
            try:
                self._local.inside_legacy = True
                legacy_value = self.legacy_validate(info, base_data, tables)
            except Exception as exc:
                legacy_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._local.inside_legacy = False
            legacy_seconds = time.perf_counter() - legacy_started

            modular_started = time.perf_counter()
            try:
                self._local.inside_modular = True
                modular_value = self._run_modular(info, base_data, tables)
            except Exception as exc:
                modular_error = f"{type(exc).__name__}: {exc}"
            finally:
                self._local.inside_modular = False
            modular_seconds = time.perf_counter() - modular_started

            if legacy_error:
                self.report.record({
                    "timestamp": timestamp, "context": context, "mode": mode,
                    "selected": "legacy", "reason": "legacy_error", "legacy_invoked": True,
                    "exact_equal": False, "legacy_seconds": round(legacy_seconds, 6),
                    "modular_seconds": round(modular_seconds, 6), "legacy_sha256": "",
                    "modular_sha256": _sha(modular_value) if not modular_error else "",
                    "legacy_error": legacy_error, "modular_error": modular_error,
                    "first_difference": None,
                })
                raise RuntimeError(legacy_error)

            exact = not modular_error and legacy_value == modular_value
            self.report.record({
                "timestamp": timestamp,
                "context": context,
                "mode": mode,
                "selected": "legacy",
                "reason": "exact_shadow" if exact else ("modular_error" if modular_error else "result_different"),
                "legacy_invoked": True,
                "exact_equal": exact,
                "legacy_seconds": round(legacy_seconds, 6),
                "modular_seconds": round(modular_seconds, 6),
                "legacy_sha256": _sha(legacy_value),
                "modular_sha256": _sha(modular_value) if not modular_error else "",
                "legacy_error": "",
                "modular_error": modular_error,
                "first_difference": _first_difference(legacy_value, modular_value) if not exact and not modular_error else None,
            })
            return legacy_value

        # modular_guarded: o legado não é chamado no sucesso modular.
        modular_started = time.perf_counter()
        try:
            self._local.inside_modular = True
            modular_value = self._run_modular(info, base_data, tables)
        except Exception as exc:
            modular_error = f"{type(exc).__name__}: {exc}"
            modular_seconds = time.perf_counter() - modular_started
        else:
            modular_error = ""
            modular_seconds = time.perf_counter() - modular_started
        finally:
            self._local.inside_modular = False

        if not modular_error:
            self.report.record({
                "timestamp": timestamp,
                "context": context,
                "mode": mode,
                "selected": "modular",
                "reason": "modular_success",
                "legacy_invoked": False,
                "exact_equal": None,
                "legacy_seconds": 0.0,
                "modular_seconds": round(modular_seconds, 6),
                "legacy_sha256": "",
                "modular_sha256": _sha(modular_value),
                "legacy_error": "",
                "modular_error": "",
                "first_difference": None,
            })
            return modular_value

        legacy_started = time.perf_counter()
        try:
            self._local.inside_legacy = True
            legacy_value = self.legacy_validate(info, base_data, tables)
        except Exception as exc:
            legacy_error = f"{type(exc).__name__}: {exc}"
            legacy_seconds = time.perf_counter() - legacy_started
            self.report.record({
                "timestamp": timestamp,
                "context": context,
                "mode": mode,
                "selected": "legacy",
                "reason": "fallback_both_failed",
                "legacy_invoked": True,
                "exact_equal": False,
                "legacy_seconds": round(legacy_seconds, 6),
                "modular_seconds": round(modular_seconds, 6),
                "legacy_sha256": "",
                "modular_sha256": "",
                "legacy_error": legacy_error,
                "modular_error": modular_error,
                "first_difference": None,
            })
            raise
        finally:
            self._local.inside_legacy = False
        legacy_seconds = time.perf_counter() - legacy_started
        self.report.record({
            "timestamp": timestamp,
            "context": context,
            "mode": mode,
            "selected": "legacy",
            "reason": "fallback_modular_error",
            "legacy_invoked": True,
            "exact_equal": False,
            "legacy_seconds": round(legacy_seconds, 6),
            "modular_seconds": round(modular_seconds, 6),
            "legacy_sha256": _sha(legacy_value),
            "modular_sha256": "",
            "legacy_error": "",
            "modular_error": modular_error,
            "first_difference": None,
        })
        return legacy_value
