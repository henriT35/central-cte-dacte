from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .audit import SignaturePdfAuditWriter, text_sha256
from .exporter import PdfBatchExporter as ModularPdfBatchExporter
from .html_signer import render_signed_batch_html as modular_render_signed_batch_html
from .html_signer import render_signed_html as modular_render_signed_html
from .image_processing import process_signature_image as modular_process_signature_image
from .pdf_converter import html_file_to_pdf as modular_html_file_to_pdf
from .pdf_converter import html_text_to_pdf as modular_html_text_to_pdf
from .pdf_converter import validate_pdf_file


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _xml_hashes(infos: Iterable[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for info in infos:
        raw = info.get("path") or info.get("arquivo")
        if not raw:
            continue
        path = Path(str(raw))
        if path.suffix.lower() != ".xml" or not path.exists() or not path.is_file():
            continue
        try:
            result[str(path.resolve())] = _file_sha256(path)
        except Exception:
            continue
    return result


class GuardedSignaturePdfService:
    def __init__(
        self,
        legacy_api: Any,
        reporter: SignaturePdfAuditWriter,
        mode_provider: Callable[[], str],
        logger: Optional[Callable[..., None]] = None,
    ) -> None:
        self.legacy = legacy_api
        self.reporter = reporter
        self.mode_provider = mode_provider
        self.logger = logger or (lambda *args, **kwargs: None)

    def mode(self) -> str:
        value = str(self.mode_provider() or "modular_guarded").strip().lower()
        return value if value in {"modular_guarded", "shadow", "legacy"} else "modular_guarded"

    def render_signed_html(self, engine: Any, info: dict[str, Any], profile: Any, date_text: str,
                           position: Optional[str] = None, stamp_size: str = "medium") -> str:
        mode = self.mode()
        cte = str(info.get("numero") or "")
        if mode == "legacy":
            result = self.legacy.render_signed_html(engine, info, profile, date_text, position, stamp_size)
            self.reporter.record("render_html", classification="LEGADO", official="legacy", fallback=False,
                                 reason="modo legado", cte=cte, profile_id=getattr(profile, "id", ""),
                                 legacy_sha256=text_sha256(result), modular_sha256="")
            return result
        legacy_result = self.legacy.render_signed_html(engine, info, profile, date_text, position, stamp_size)
        try:
            modular_result = modular_render_signed_html(engine, info, profile, date_text, position, stamp_size)
            equal = legacy_result == modular_result
            official = "modular" if equal and mode == "modular_guarded" else "legacy"
            classification = "IGUAL" if equal else "CRITICA"
            chosen = modular_result if official == "modular" else legacy_result
            self.reporter.record(
                "render_html", classification=classification, official=official,
                fallback=not equal and mode == "modular_guarded",
                reason="HTML idêntico" if equal else "HTML modular divergiu do legado",
                cte=cte, profile_id=getattr(profile, "id", ""),
                legacy_sha256=text_sha256(legacy_result), modular_sha256=text_sha256(modular_result),
            )
            return chosen
        except Exception as exc:
            self.reporter.record("render_html", classification="CRITICA", official="legacy", fallback=True,
                                 reason="erro modular", cte=cte, profile_id=getattr(profile, "id", ""),
                                 legacy_sha256=text_sha256(legacy_result), modular_sha256="", error=str(exc))
            return legacy_result

    def render_signed_batch_html(self, engine: Any, infos: Iterable[dict[str, Any]], profile: Any, date_text: str,
                                 position: Optional[str] = None, stamp_size: str = "medium") -> str:
        items = list(infos)
        mode = self.mode()
        if mode == "legacy":
            result = self.legacy.render_signed_batch_html(engine, items, profile, date_text, position, stamp_size)
            self.reporter.record("render_batch_html", classification="LEGADO", official="legacy", fallback=False,
                                 reason="modo legado", profile_id=getattr(profile, "id", ""),
                                 legacy_sha256=text_sha256(result), modular_sha256="")
            return result
        legacy_result = self.legacy.render_signed_batch_html(engine, items, profile, date_text, position, stamp_size)
        try:
            modular_result = modular_render_signed_batch_html(engine, items, profile, date_text, position, stamp_size)
            equal = legacy_result == modular_result
            official = "modular" if equal and mode == "modular_guarded" else "legacy"
            chosen = modular_result if official == "modular" else legacy_result
            self.reporter.record(
                "render_batch_html", classification="IGUAL" if equal else "CRITICA", official=official,
                fallback=not equal and mode == "modular_guarded",
                reason="HTML de lote idêntico" if equal else "HTML de lote modular divergiu",
                profile_id=getattr(profile, "id", ""), legacy_sha256=text_sha256(legacy_result),
                modular_sha256=text_sha256(modular_result),
            )
            return chosen
        except Exception as exc:
            self.reporter.record("render_batch_html", classification="CRITICA", official="legacy", fallback=True,
                                 reason="erro modular", profile_id=getattr(profile, "id", ""),
                                 legacy_sha256=text_sha256(legacy_result), modular_sha256="", error=str(exc))
            return legacy_result

    def process_signature_image(self, source: Path, output: Path, threshold: int = 242) -> dict[str, Any]:
        source, output = Path(source), Path(output)
        mode = self.mode()
        if mode == "legacy":
            result = self.legacy.process_signature_image(source, output, threshold)
            self.reporter.record("process_signature", classification="LEGADO", official="legacy", fallback=False,
                                 reason="modo legado", output=str(output), modular_sha256="",
                                 legacy_sha256=_file_sha256(output) if output.exists() else "")
            return result
        with tempfile.TemporaryDirectory(prefix="cte_signature_compare_") as tmp:
            legacy_output = Path(tmp) / "legacy.png"
            try:
                legacy_result = self.legacy.process_signature_image(source, legacy_output, threshold)
            except Exception as exc:
                legacy_result = {"error": str(exc)}
                legacy_output = None
            try:
                modular_result = modular_process_signature_image(source, output, threshold)
                modular_hash = _file_sha256(output)
                legacy_hash = _file_sha256(legacy_output) if legacy_output is not None and legacy_output.exists() else ""
                equal = bool(legacy_hash and legacy_hash == modular_hash)
                if mode == "shadow":
                    if legacy_output is not None and legacy_output.exists():
                        shutil.copy2(legacy_output, output)
                    official, chosen = "legacy", legacy_result
                elif equal or not legacy_hash:
                    official, chosen = "modular", modular_result
                else:
                    shutil.copy2(legacy_output, output)
                    official, chosen = "legacy", legacy_result
                self.reporter.record(
                    "process_signature", classification="IGUAL" if equal else ("INFORMATIVA" if not legacy_hash else "CRITICA"),
                    official=official, fallback=official == "legacy" and mode == "modular_guarded",
                    reason="PNG idêntico" if equal else ("legado indisponível para comparação" if not legacy_hash else "PNG modular divergiu"),
                    output=str(output), legacy_sha256=legacy_hash, modular_sha256=modular_hash,
                )
                return chosen
            except Exception as exc:
                if legacy_output is not None and legacy_output.exists():
                    shutil.copy2(legacy_output, output)
                    self.reporter.record("process_signature", classification="CRITICA", official="legacy", fallback=True,
                                         reason="erro modular", output=str(output),
                                         legacy_sha256=_file_sha256(output), modular_sha256="", error=str(exc))
                    return legacy_result
                raise

    def html_file_to_pdf(self, html_path: Path, output_path: Path, browser: Optional[Path] = None,
                         timeout: int = 100) -> Path:
        mode = self.mode()
        converter = self.legacy.html_file_to_pdf if mode == "legacy" else modular_html_file_to_pdf
        try:
            result = converter(html_path, output_path, browser=browser, timeout=timeout)
            meta = validate_pdf_file(result)
            self.reporter.record("html_file_to_pdf", classification="VALIDO", official="legacy" if mode == "legacy" else "modular",
                                 fallback=False, reason="PDF válido", output=str(result), pdf_size=meta["size"],
                                 pages_detected=meta["pages_detected"])
            return result
        except Exception as exc:
            if mode == "legacy":
                raise
            try:
                result = self.legacy.html_file_to_pdf(html_path, output_path, browser=browser, timeout=timeout)
                meta = validate_pdf_file(result)
                self.reporter.record("html_file_to_pdf", classification="CRITICA", official="legacy", fallback=True,
                                     reason="conversor modular falhou", output=str(result), error=str(exc),
                                     pdf_size=meta["size"], pages_detected=meta["pages_detected"])
                return result
            except Exception:
                self.reporter.record("html_file_to_pdf", classification="CRITICA", official="nenhum", fallback=True,
                                     reason="conversores modular e legado falharam", output=str(output_path), error=str(exc))
                raise

    def html_text_to_pdf(self, document_html: str, output_path: Path, browser: Optional[Path] = None) -> Path:
        mode = self.mode()
        converter = self.legacy.html_text_to_pdf if mode == "legacy" else modular_html_text_to_pdf
        try:
            result = converter(document_html, output_path, browser=browser)
            meta = validate_pdf_file(result)
            self.reporter.record("html_text_to_pdf", classification="VALIDO", official="legacy" if mode == "legacy" else "modular",
                                 fallback=False, reason="PDF válido", output=str(result), pdf_size=meta["size"],
                                 pages_detected=meta["pages_detected"])
            return result
        except Exception as exc:
            if mode == "legacy":
                raise
            result = self.legacy.html_text_to_pdf(document_html, output_path, browser=browser)
            meta = validate_pdf_file(result)
            self.reporter.record("html_text_to_pdf", classification="CRITICA", official="legacy", fallback=True,
                                 reason="conversor modular falhou", output=str(result), error=str(exc),
                                 pdf_size=meta["size"], pages_detected=meta["pages_detected"])
            return result

    def export(self, runtime_dir: Path, engine: Any, store: Any, legacy_exporter_class: Any,
               infos: list[dict[str, Any]], profile: Any, date_text: str, **kwargs: Any) -> dict[str, Any]:
        before = _xml_hashes(infos)
        mode = self.mode()
        try:
            use_legacy = mode in {"legacy", "shadow"}
            exporter = legacy_exporter_class(runtime_dir, engine, store) if use_legacy else ModularPdfBatchExporter(runtime_dir, engine, store)
            result = exporter.export(infos, profile, date_text, **kwargs)
            official = "legacy" if use_legacy else "modular"
            fallback = False
            # O exportador trata falhas por documento. Se o caminho modular não
            # produzir nenhum PDF, tenta o exportador congelado uma única vez.
            if not use_legacy and not (result.get("generated") or []):
                legacy_result = legacy_exporter_class(runtime_dir, engine, store).export(infos, profile, date_text, **kwargs)
                if len(legacy_result.get("generated") or []) > 0:
                    result = legacy_result
                    official, fallback = "legacy", True
                    self.logger("assinatura_pdf_fallback", reason="modular_sem_arquivos")
        except Exception as exc:
            if mode in {"legacy", "shadow"}:
                raise
            exporter = legacy_exporter_class(runtime_dir, engine, store)
            result = exporter.export(infos, profile, date_text, **kwargs)
            official, fallback = "legacy", True
            self.logger("assinatura_pdf_fallback", error=str(exc))
        after = _xml_hashes(infos)
        modified = before != after
        self.reporter.record(
            "export_pdf", classification="CRITICA" if modified else "VALIDO", official=official,
            fallback=fallback, reason="XML original alterado" if modified else "XMLs preservados",
            profile_id=getattr(profile, "id", ""), output=str(result.get("root") or ""),
            generated=len(result.get("generated") or []), failures=len(result.get("failures") or []),
            xml_originals_modified=modified,
        )
        if modified:
            raise RuntimeError("A geração de PDF alterou ao menos um XML fiscal original. Operação bloqueada.")
        return result
