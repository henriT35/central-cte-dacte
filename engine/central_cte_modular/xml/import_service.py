from __future__ import annotations

"""Importação modular de documentos da página CT-e.

RC17: leitura única por XML, validação de formato, cache persistente,
paralelismo controlado e relatório gravado somente ao final do lote.
"""

import hashlib
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

from .batch_processor import FastXmlBatchProcessor, ProgressCallback
from .batch_report import XmlImportBatchReporter
from .cache import XmlParseCache

XML_IMPORT_SERVICE_VERSION = "2.7.0-rc17-xml-fast-1"
SUPPORTED_SUFFIXES = (
    ".xml", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt",
    ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff",
)
_FILENAME_FISCAL_KEY = re.compile(r"(?<!\d)(\d{44})(?!\d)")


@dataclass
class XmlImportResult:
    files: list[Any]
    selected: int = 0
    added: int = 0
    skipped: int = 0
    cleaned_records: list[dict[str, str]] = field(default_factory=list)
    duplicates: list[dict[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    performance: dict[str, Any] = field(default_factory=dict)

    @property
    def cleaned(self) -> int:
        return len(self.cleaned_records)

    @property
    def total(self) -> int:
        return len(self.files)

    @property
    def should_show_log(self) -> bool:
        return bool(
            self.selected or self.added or self.skipped or self.cleaned_records or self.errors
        )

    def to_log(self) -> dict[str, Any]:
        return {
            "selected": self.selected,
            "added": self.added,
            "skipped": self.skipped,
            "cleaned": self.cleaned,
            "cleaned_records": list(self.cleaned_records),
            "errors_count": len(self.errors),
            "errors": list(self.errors),
            "duplicates": list(self.duplicates),
            "total": self.total,
            "performance": dict(self.performance),
            "service_version": XML_IMPORT_SERVICE_VERSION,
            "mode": "batch_fast_modular_service",
        }


class XmlImportService:
    version = XML_IMPORT_SERVICE_VERSION
    supported_suffixes = SUPPORTED_SUFFIXES

    def __init__(
        self,
        parser: Callable[[Path], Any] | None = None,
        *,
        batch_processor: FastXmlBatchProcessor | None = None,
        batch_reporter: XmlImportBatchReporter | None = None,
    ) -> None:
        self.parser = parser
        self.batch_processor = batch_processor
        self.batch_reporter = batch_reporter

    @staticmethod
    def digits(value: Any) -> str:
        return re.sub(r"\D", "", str(value or ""))

    @staticmethod
    def norm_text(value: Any) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        return " ".join(text.upper().split())

    @staticmethod
    def normalize_path(value: Any) -> str:
        try:
            return os.path.normcase(os.path.abspath(str(value or "")))
        except Exception:
            return str(value or "").strip().lower()

    @staticmethod
    def sha1_file(path: str | Path) -> str:
        try:
            digest = hashlib.sha1()
            with Path(path).open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except Exception:
            return ""

    @classmethod
    def filename_fiscal_key(cls, path: str | Path) -> str:
        match = _FILENAME_FISCAL_KEY.search(Path(path).name)
        return match.group(1) if match else ""

    def xml_key(self, path: str | Path, *, content_fallback: bool = True) -> str:
        candidate = Path(path)
        if not candidate.exists():
            return "MISS:" + self.normalize_path(path)
        if candidate.suffix.lower() != ".xml":
            return "PATH:" + self.normalize_path(path)

        # Exportações do SSW já trazem a chave de 44 dígitos no nome. Esta é a
        # rota rápida e evita abrir o XML apenas para deduplicá-lo.
        filename_key = self.filename_fiscal_key(candidate)
        if filename_key:
            return "CHAVE:" + filename_key
        if not content_fallback:
            return "PATH:" + self.normalize_path(candidate)

        try:
            root = ET.parse(candidate).getroot()
            for element in root.iter():
                tag = str(element.tag).split("}")[-1]
                if tag in {"infCte", "infNFe", "infMDFe"}:
                    key = self.digits(element.attrib.get("Id", ""))
                    if len(key) >= 44:
                        return "CHAVE:" + key[-44:]
            for element in root.iter():
                tag = str(element.tag).split("}")[-1]
                if tag in {"chCTe", "chNFe", "chMDFe", "chave"}:
                    key = self.digits(element.text or "")
                    if len(key) >= 44:
                        return "CHAVE:" + key[-44:]
        except Exception:
            pass
        digest = self.sha1_file(candidate)
        return "XMLSHA1:" + digest if digest else "PATH:" + self.normalize_path(path)

    @staticmethod
    def info_path(info: Any) -> str:
        if isinstance(info, Mapping):
            return str(
                info.get("path")
                or info.get("caminho")
                or info.get("arquivo_path")
                or info.get("filepath")
                or info.get("arquivo")
                or ""
            )
        for attribute in ("path", "caminho", "arquivo_path", "filepath", "filename", "arquivo"):
            try:
                value = getattr(info, attribute)
            except Exception:
                continue
            if value:
                return str(value)
        return str(info) if isinstance(info, (str, Path)) else ""

    def info_key(self, info: Any) -> str:
        if isinstance(info, Mapping):
            for field_name in (
                "dedup_key", "chave", "chCTe", "chcte", "chave_cte", "cte_chave",
                "chNFe", "chnfe", "chave_nfe", "id", "Id",
            ):
                value = info.get(field_name, "")
                if field_name == "dedup_key" and str(value or "").strip().startswith(
                    ("CHAVE:", "XMLSHA1:", "PATH:", "MISS:", "META:")
                ):
                    return str(value).strip()
                digits = self.digits(value)
                if len(digits) >= 44:
                    return "CHAVE:" + digits[-44:]
            path = self.info_path(info)
            if path:
                return self.xml_key(path) if str(path).lower().endswith(".xml") else "PATH:" + self.normalize_path(path)
            kind = self.norm_text(info.get("tipo") or info.get("Tipo") or "")
            number = self.digits(info.get("numero") or info.get("Número") or info.get("nCT") or "")
            series = self.digits(info.get("serie") or info.get("Série") or "")
            invoice = self.digits(info.get("nf") or info.get("NF") or "")
            issuer = self.norm_text(info.get("emitente") or info.get("Emitente") or "")
            value = str(info.get("valor") or info.get("vTPrest") or "").strip()
            if number and ("CT" in kind or issuer or series or invoice):
                return "META:" + "|".join([kind, number, series, invoice, issuer[:70], value])
        path = self.info_path(info)
        if path:
            return self.xml_key(path) if str(path).lower().endswith(".xml") else "PATH:" + self.normalize_path(path)
        return "OBJ:" + str(id(info))

    @staticmethod
    def key_label(key: Any) -> str:
        text = str(key or "")
        if text.startswith("CHAVE:"):
            return text.split(":", 1)[1][-12:]
        if text.startswith("META:"):
            return text.split(":", 1)[1][:80]
        if text.startswith(("PATH:", "MISS:")):
            return Path(text.split(":", 1)[1]).name
        if len(text) > 70:
            return text[:67] + "..."
        return text

    @staticmethod
    def coerce_paths(paths: Iterable[str | Path] | str | Path | None) -> list[str | Path]:
        if paths is None:
            return []
        if isinstance(paths, (str, Path)):
            return [paths]
        try:
            return list(paths)
        except TypeError:
            return [paths]

    def expand_paths(self, paths: Iterable[str | Path] | str | Path | None) -> list[Path]:
        expanded, _errors = self.expand_paths_checked(paths)
        return expanded

    def expand_paths_checked(self, paths: Iterable[str | Path] | str | Path | None) -> tuple[list[Path], list[str]]:
        expanded: list[Path] = []
        errors: list[str] = []
        for raw in self.coerce_paths(paths):
            try:
                candidate = Path(raw)
                if candidate.is_dir():
                    for item in sorted((entry for entry in candidate.iterdir() if entry.is_file()), key=lambda entry: entry.name.casefold()):
                        if item.suffix.lower() in self.supported_suffixes:
                            expanded.append(item)
                        else:
                            errors.append(f"{item.name}: formato não suportado ({item.suffix or 'sem extensão'})")
                elif candidate.suffix.lower() in self.supported_suffixes:
                    expanded.append(candidate)
                else:
                    errors.append(f"{candidate.name}: formato não suportado ({candidate.suffix or 'sem extensão'})")
            except Exception as exc:
                errors.append(f"{raw}: {type(exc).__name__}: {exc}")
        return expanded, errors

    def clean_loaded(self, files: Sequence[Any]) -> tuple[list[Any], list[dict[str, str]], set[str]]:
        fixed: list[Any] = []
        removed: list[dict[str, str]] = []
        seen: set[str] = set()
        for info in list(files or []):
            key = self.info_key(info)
            if key in seen:
                path = self.info_path(info)
                removed.append({
                    "key": key,
                    "arquivo": Path(path).name if path else "",
                    "motivo": "duplicado antigo removido da lista",
                })
                continue
            if isinstance(info, MutableMapping):
                info["dedup_key"] = key
            seen.add(key)
            fixed.append(info)
        return fixed, removed, seen

    @staticmethod
    def generic_document(path: Path) -> dict[str, Any]:
        return {
            "tipo": path.suffix.upper().replace(".", ""),
            "numero": "",
            "serie": "",
            "emitente": "",
            "destinatario": "",
            "valor": "",
            "arquivo": path.name,
            "path": str(path),
        }

    def import_paths(
        self,
        existing_files: Sequence[Any],
        paths: Iterable[str | Path],
        *,
        parser: Callable[[Path], Any] | None = None,
        progress: ProgressCallback | None = None,
    ) -> XmlImportResult:
        started = time.perf_counter()
        parse = parser or self.parser
        incoming, expansion_errors = self.expand_paths_checked(paths)
        fixed, cleaned_before, known_keys = self.clean_loaded(existing_files)
        known_paths = {
            self.normalize_path(path)
            for info in fixed
            for path in [self.info_path(info)]
            if path
        }
        reserved_keys = set(known_keys)
        result = XmlImportResult(files=list(fixed), selected=len(incoming) + len(expansion_errors))
        result.errors.extend(expansion_errors)
        result.cleaned_records.extend(cleaned_before)

        pending_xml: list[tuple[Path, str, str]] = []
        pending_generic: list[tuple[Path, str, str]] = []
        for path in incoming:
            try:
                if not path.exists():
                    result.errors.append(f"{path}: arquivo não encontrado")
                    continue
                normalized = self.normalize_path(path)
                pre_key = (
                    self.xml_key(path, content_fallback=False)
                    if path.suffix.lower() == ".xml"
                    else "PATH:" + normalized
                )
                if pre_key in reserved_keys or normalized in known_paths:
                    result.skipped += 1
                    result.duplicates.append({
                        "key": pre_key,
                        "arquivo": path.name,
                        "motivo": "já carregado ou duplicado no lote",
                    })
                    continue
                reserved_keys.add(pre_key)
                known_paths.add(normalized)
                target = pending_xml if path.suffix.lower() == ".xml" else pending_generic
                target.append((path, pre_key, normalized))
            except Exception as exc:
                result.errors.append(f"{getattr(path, 'name', path)}: {exc}")

        for path, pre_key, normalized in pending_generic:
            info = self.generic_document(path)
            self._append_parsed(result, info, path, pre_key, normalized, known_keys)

        batch_metrics: dict[str, Any] = {
            "requested_xml": len(pending_xml),
            "cache_hits": 0,
            "parsed_xml": 0,
            "workers": 1,
            "parallel": False,
            "cache_backend": "disabled",
            "elapsed_ms": 0.0,
            "mode": "direct",
        }
        if pending_xml:
            if self.batch_processor is not None:
                batch = self.batch_processor.parse_many(
                    [item[0] for item in pending_xml],
                    parser=parse,
                    progress=progress,
                )
                batch_metrics = batch.to_metrics()
                for path, pre_key, normalized in pending_xml:
                    canonical = XmlParseCache.canonical(path)
                    if canonical in batch.errors:
                        result.errors.append(f"{path.name}: {batch.errors[canonical]}")
                        continue
                    info = batch.results.get(canonical)
                    if info is None:
                        result.errors.append(f"{path.name}: parser não devolveu resultado")
                        continue
                    self._append_parsed(result, info, path, pre_key, normalized, known_keys)
            else:
                if not callable(parse):
                    result.errors.extend(f"{path.name}: parser XML não conectado" for path, _, _ in pending_xml)
                else:
                    parse_started = time.perf_counter()
                    for index, (path, pre_key, normalized) in enumerate(pending_xml, start=1):
                        try:
                            info = parse(path)
                            self._append_parsed(result, info, path, pre_key, normalized, known_keys)
                        except Exception as exc:
                            result.errors.append(f"{path.name}: {exc}")
                        if callable(progress):
                            try:
                                progress(index, len(pending_xml), "parser")
                            except Exception:
                                pass
                    batch_metrics["parsed_xml"] = len(pending_xml) - len(result.errors)
                    batch_metrics["elapsed_ms"] = (time.perf_counter() - parse_started) * 1000.0

        final_files, cleaned_after, _ = self.clean_loaded(result.files)
        result.files = final_files
        result.cleaned_records.extend(cleaned_after)
        batch_metrics["total_elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        result.performance = batch_metrics

        if self.batch_reporter is not None:
            try:
                report_payload = self.batch_reporter.record(result.to_log())
                result.performance["report_session_id"] = report_payload.get("session_id", "")
            except Exception as exc:
                result.performance["report_error"] = f"{type(exc).__name__}: {exc}"
        return result

    def _append_parsed(
        self,
        result: XmlImportResult,
        info: Any,
        path: Path,
        pre_key: str,
        normalized: str,
        known_keys: set[str],
    ) -> None:
        if isinstance(info, Mapping):
            kind = self.norm_text(info.get("tipo") or info.get("document_type") or "")
            parser_error = str(info.get("erro") or info.get("error") or "").strip()
            if "XML INVALIDO" in kind or (parser_error and not str(info.get("numero") or "").strip()):
                result.errors.append(f"{path.name}: {parser_error or 'XML inválido'}")
                return
            if path.suffix.lower() == ".xml" and kind not in {
                "CT-E", "CTE", "NF-E", "NFE", "MDF-E", "MDFE",
            }:
                result.errors.append(
                    f"{path.name}: XML válido, porém sem estrutura fiscal compatível "
                    "(CT-e/NF-e/MDF-e)"
                )
                return
        if isinstance(info, MutableMapping):
            info.setdefault("arquivo", path.name)
            info["path"] = str(path)
        post_key = self.info_key(info) or pre_key
        if post_key in known_keys:
            result.skipped += 1
            result.duplicates.append({
                "key": post_key,
                "arquivo": path.name,
                "motivo": "chave fiscal já carregada",
            })
            return
        if isinstance(info, MutableMapping):
            info["dedup_key"] = post_key
        result.files.append(info)
        known_keys.add(post_key)
        result.added += 1

    def build_log_text(self, log: Mapping[str, Any]) -> str:
        performance = dict(log.get("performance") or {})
        lines = [
            "LOG DE IMPORTAÇÃO DE XML/CT-e",
            "-" * 58,
            f"Arquivos selecionados: {log.get('selected', 0)}",
            f"CT-e adicionados nesta importação: {log.get('added', 0)}",
            f"CT-e repetidos ignorados: {log.get('skipped', 0)}",
        ]
        if log.get("cleaned"):
            lines.append(f"Duplicados antigos removidos da lista: {log.get('cleaned', 0)}")
        lines.extend([
            f"Erros: {log.get('errors_count', 0)}",
            f"Total real na lista: {log.get('total', 0)}",
        ])
        if performance:
            lines.extend([
                "",
                "DESEMPENHO DO LOTE",
                f"Modo do parser: {performance.get('mode', '-')}",
                f"XMLs recuperados do cache: {performance.get('cache_hits', 0)}",
                f"XMLs realmente processados: {performance.get('parsed_xml', 0)}",
                f"Cache: {performance.get('cache_backend', 'disabled')}",
                f"Processamento paralelo: {'SIM' if performance.get('parallel') else 'NÃO'}",
                f"Workers: {performance.get('workers', 1)}",
                f"Tempo parser/cache: {float(performance.get('elapsed_ms', 0) or 0):.1f} ms",
                f"Tempo total: {float(performance.get('total_elapsed_ms', 0) or 0):.1f} ms",
            ])
            if performance.get("parallel_fallback"):
                lines.append(f"Fallback do paralelismo: {performance['parallel_fallback']}")
        if log.get("duplicates"):
            lines.extend(["", "Repetidos ignorados:"])
            for record in list(log.get("duplicates") or [])[:250]:
                lines.append(
                    f"- {self.key_label(record.get('key'))} | "
                    f"{record.get('arquivo') or '-'} | {record.get('motivo') or 'repetido'}"
                )
        if log.get("cleaned_records"):
            lines.extend(["", "Duplicados antigos limpos:"])
            for record in list(log.get("cleaned_records") or [])[:120]:
                lines.append(
                    f"- {self.key_label(record.get('key'))} | {record.get('arquivo') or '-'}"
                )
        if log.get("errors"):
            lines.extend(["", "Erros:"])
            for error in list(log.get("errors") or [])[:120]:
                lines.append(f"- {error}")
        return "\n".join(lines)


__all__ = [
    "SUPPORTED_SUFFIXES",
    "XML_IMPORT_SERVICE_VERSION",
    "XmlImportResult",
    "XmlImportService",
]
