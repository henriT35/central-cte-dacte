from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping
import csv
import hashlib
import json

from .shadow_parser import ParserShadowComparator, ShadowComparison

PROMOTION_VERSION = "2.7.0-rc17"
MODE_MODULAR_FAST = "modular_fast"
MODE_MODULAR_GUARDED = "modular_guarded"
MODE_LEGACY_SHADOW = "legacy_shadow"
VALID_MODES = frozenset({MODE_MODULAR_FAST, MODE_MODULAR_GUARDED, MODE_LEGACY_SHADOW})


@dataclass(frozen=True)
class PromotionDecision:
    path: str
    mode: str
    selected: str
    reason: str
    comparison: ShadowComparison
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        payload = self.comparison.to_dict()
        payload.update({
            "promotion_version": PROMOTION_VERSION,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "selected": self.selected,
            "reason": self.reason,
        })
        return payload


class ParserPromotionReport:
    """Registra qual parser forneceu o resultado oficial em cada XML.

    O relatório é independente da auditoria legado × modular. Ele mostra quando o
    resultado modular foi aceito e quando o legado assumiu automaticamente por
    divergência, erro ou modo de emergência.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.started_at = datetime.now()
        self.session_id = self._session_id()
        self.jsonl_path = self.directory / f"promocao_parser_{self.session_id}.jsonl"
        self._records: list[dict[str, Any]] = []
        self._seen: set[str] = set()
        self._lock = RLock()

    def _session_id(self) -> str:
        base = self.started_at.strftime("%Y%m%d_%H%M%S")
        candidate = base
        suffix = 1
        while (self.directory / f"promocao_parser_{candidate}.jsonl").exists():
            suffix += 1
            candidate = f"{base}_{suffix:02d}"
        return candidate

    def record(self, decision: PromotionDecision) -> bool:
        path = Path(decision.path)
        digest = self._sha256(path)
        unique = digest or f"path:{path}"
        with self._lock:
            if unique in self._seen:
                return False
            self._seen.add(unique)
            payload = decision.to_dict()
            payload.update({
                "session_id": self.session_id,
                "arquivo": path.name,
                "sha256": digest,
            })
            self._records.append(payload)
            with self.jsonl_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            self._write_latest()
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> dict[str, Any]:
        total = len(self._records)
        modular = sum(1 for item in self._records if item.get("selected") == "modular")
        legacy = sum(1 for item in self._records if item.get("selected") == "legacy")
        forced = sum(1 for item in self._records if item.get("reason") == "modo_legado_forcado")
        divergent = sum(1 for item in self._records if item.get("reason") == "divergencia_detectada")
        errors = sum(1 for item in self._records if item.get("legacy_error") or item.get("modular_error"))
        return {
            "version": PROMOTION_VERSION,
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "jsonl_file": self.jsonl_path.name,
            "totals": {
                "total": total,
                "selected_modular": modular,
                "selected_legacy": legacy,
                "legacy_forced": forced,
                "fallback_by_difference": divergent,
                "parser_errors": errors,
                "modular_share_percent": round((modular / total * 100.0), 2) if total else 0.0,
            },
            "records": list(self._records),
        }

    def _write_latest(self) -> None:
        snapshot = self._snapshot_unlocked()
        self._atomic_write(
            self.directory / "ultima_promocao_parser.json",
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        )
        self._atomic_write(self.directory / "ultima_promocao_parser.txt", self._render_text(snapshot))
        self._write_csv(self.directory / "ultima_promocao_parser.csv", snapshot.get("records") or [])

    @staticmethod
    def _render_text(snapshot: Mapping[str, Any]) -> str:
        totals = snapshot["totals"]
        lines = [
            "CENTRAL CT-e / DACTE 2.6.66.5 - PROMOÇÃO CONTROLADA DO PARSER MODULAR",
            f"Sessão: {snapshot['session_id']}",
            f"Início: {snapshot['started_at']}",
            f"Atualização: {snapshot['generated_at']}",
            "",
            f"XMLs processados: {totals['total']}",
            f"Resultado modular aceito: {totals['selected_modular']}",
            f"Fallback para legado: {totals['selected_legacy']}",
            f"Legado forçado: {totals['legacy_forced']}",
            f"Fallback por divergência: {totals['fallback_by_difference']}",
            f"Erros de parser: {totals['parser_errors']}",
            f"Participação modular: {totals['modular_share_percent']:.2f}%",
            "",
        ]
        for index, item in enumerate(snapshot.get("records") or [], start=1):
            fields = ", ".join((item.get("differences") or {}).keys()) or "nenhum"
            lines.extend([
                f"{index}. [{str(item.get('selected', '')).upper()}] {item.get('arquivo', '')}",
                f"   Modo: {item.get('mode', '')}",
                f"   Motivo: {item.get('reason', '')}",
                f"   Comparação: {item.get('status', '')}",
                f"   Campos divergentes: {fields}",
            ])
            if item.get("legacy_error"):
                lines.append(f"   Erro legado: {item['legacy_error']}")
            if item.get("modular_error"):
                lines.append(f"   Erro modular: {item['modular_error']}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _write_csv(path: Path, records: list[Mapping[str, Any]]) -> None:
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow([
                "Arquivo", "Modo", "Selecionado", "Motivo", "Comparação",
                "CT-e", "Série", "Chave", "Campos divergentes", "SHA-256",
            ])
            for item in records:
                legacy = item.get("legacy_summary") or {}
                modular = item.get("modular_summary") or {}
                writer.writerow([
                    item.get("arquivo", ""), item.get("mode", ""), item.get("selected", ""),
                    item.get("reason", ""), item.get("status", ""),
                    legacy.get("numero") or modular.get("numero") or "",
                    legacy.get("serie") or modular.get("serie") or "",
                    legacy.get("chave") or modular.get("chave") or "",
                    ", ".join((item.get("differences") or {}).keys()), item.get("sha256", ""),
                ])
        temp.replace(path)

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


class GuardedModularParser:
    """Promove o modular apenas quando o resultado é equivalente ao legado.

    Em modo padrão, cada XML é lido uma vez por cada parser. Se os resultados
    normalizados forem idênticos, o dicionário modular passa a ser o retorno
    oficial. Qualquer divergência ou falha modular aciona fallback automático para
    o mesmo resultado legado que a versão anterior usaria.
    """

    def __init__(
        self,
        legacy_parser: Callable[[Path], dict[str, Any]],
        modular_parser: Callable[[Path], dict[str, Any]],
        comparator: ParserShadowComparator,
        reporter: ParserPromotionReport,
        mode_resolver: Callable[[], str],
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.legacy_parser = legacy_parser
        self.modular_parser = modular_parser
        self.comparator = comparator
        self.reporter = reporter
        self.mode_resolver = mode_resolver
        self.logger = logger

    def build_parser(self) -> Callable[[Path | str], dict[str, Any]]:
        legacy_parser = self.legacy_parser

        @wraps(legacy_parser)
        def parse(path: Path | str) -> dict[str, Any]:
            path_obj = Path(path)
            mode = self._mode()
            if mode == MODE_MODULAR_FAST:
                # Uso normal: uma única leitura pelo parser modular. Auditoria
                # legado × modular permanece disponível nos modos de homologação.
                return self.modular_parser(path_obj)
            if mode == MODE_LEGACY_SHADOW:
                legacy_result = legacy_parser(path_obj)
                comparison = self.comparator.compare_with_legacy(path_obj, legacy_result)
                self._record(path_obj, mode, "legacy", "modo_legado_forcado", comparison)
                return legacy_result

            modular_result: dict[str, Any] = {}
            modular_error = ""
            try:
                modular_result = self.modular_parser(path_obj)
            except Exception as exc:
                modular_error = f"{type(exc).__name__}: {exc}"

            legacy_result: dict[str, Any] = {}
            legacy_error = ""
            legacy_exception: Exception | None = None
            try:
                legacy_result = legacy_parser(path_obj)
            except Exception as exc:
                legacy_exception = exc
                legacy_error = f"{type(exc).__name__}: {exc}"

            comparison = self.comparator.compare_results(
                path_obj,
                legacy_result,
                modular_result,
                legacy_error=legacy_error,
                modular_error=modular_error,
            )

            if legacy_exception is not None:
                self._record(path_obj, mode, "legacy", "erro_legado_preservado", comparison)
                raise legacy_exception
            if modular_error:
                self._record(path_obj, mode, "legacy", "erro_modular", comparison)
                return legacy_result
            if comparison.equal:
                self._record(path_obj, mode, "modular", "equivalencia_confirmada", comparison)
                return modular_result

            self._record(path_obj, mode, "legacy", "divergencia_detectada", comparison)
            return legacy_result

        parse.__name__ = getattr(legacy_parser, "__name__", "parse_xml")
        parse.__doc__ = getattr(legacy_parser, "__doc__", None)
        setattr(parse, "_central_cte_promotion_version", PROMOTION_VERSION)
        setattr(parse, "_central_cte_legacy_parser", legacy_parser)
        setattr(parse, "_central_cte_modular_parser", self.modular_parser)
        return parse

    def _mode(self) -> str:
        try:
            value = str(self.mode_resolver() or "").strip().lower()
        except Exception:
            value = ""
        return value if value in VALID_MODES else MODE_MODULAR_FAST

    def _record(
        self,
        path: Path,
        mode: str,
        selected: str,
        reason: str,
        comparison: ShadowComparison,
    ) -> None:
        decision = PromotionDecision(
            path=str(path),
            mode=mode,
            selected=selected,
            reason=reason,
            comparison=comparison,
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )
        try:
            self.reporter.record(decision)
        except Exception as exc:
            self._log(f"Falha ao registrar promoção do parser: {type(exc).__name__}: {exc}")

    def _log(self, text: str) -> None:
        if self.logger is None:
            return
        try:
            self.logger(str(text))
        except Exception:
            pass
