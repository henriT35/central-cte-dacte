from __future__ import annotations

import time
import webbrowser
from threading import Thread
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .audit import CTePresenterAuditEvent, CTePresenterAuditWriter
from .services import CTePageServices
from ...xml.import_service import XmlImportService

PRESENTER_VERSION = "2.7.0"


class CTePagePresenter:
    version = PRESENTER_VERSION

    def __init__(
        self,
        view: Any,
        *,
        services: CTePageServices | None = None,
        audit_writer: CTePresenterAuditWriter | None = None,
        render_document: Callable[..., str] | None = None,
        cleaner: Callable[..., str] | None = None,
        complementary_applier: Callable[..., int] | None = None,
        max_complementary_chars: int = 600,
        runtime_dir: Callable[[], Path] | None = None,
        engine_dir: Callable[[], Path] | None = None,
        xml_import_service: XmlImportService | None = None,
        parse_document: Callable[[Path], Any] | None = None,
    ) -> None:
        self.view = view
        self.services = services or CTePageServices()
        self.audit_writer = audit_writer or CTePresenterAuditWriter(None)
        self.render_document = render_document
        self.cleaner = cleaner
        self.complementary_applier = complementary_applier
        self.max_complementary_chars = int(max_complementary_chars)
        self.runtime_dir = runtime_dir or (lambda: Path.cwd())
        self.engine_dir = engine_dir or (lambda: Path.cwd())
        self.parse_document = parse_document
        self.xml_import_service = xml_import_service or XmlImportService(parse_document)
        self.last_event: dict[str, Any] = {}

    def _event(self, action: str) -> tuple[CTePresenterAuditEvent, float]:
        return (
            CTePresenterAuditEvent(
                action=action,
                status="EM_EXECUCAO",
                started_at=datetime.now().isoformat(timespec="seconds"),
            ),
            time.perf_counter(),
        )

    def _finish(
        self,
        event: CTePresenterAuditEvent,
        started: float,
        *,
        status: str = "OK",
        error: Exception | None = None,
    ) -> None:
        event.elapsed_ms = (time.perf_counter() - started) * 1000.0
        event.status = "ERRO" if error is not None else status
        if error is not None:
            event.error = f"{type(error).__name__}: {error}"
        event.documents = len(list(getattr(self.view, "files", []) or []))
        try:
            event.selected = len(list(self.view.selected_infos() or []))
        except Exception:
            event.selected = 0
        try:
            event.visible = len(list(self.view.filtered_files() or []))
        except Exception:
            event.visible = event.documents
        self.last_event = event.to_dict()
        try:
            self.view._modular_cte_presenter_last_2694 = dict(self.last_event)
        except Exception:
            pass
        self.audit_writer.write(event)

    def _apply_import_result(
        self,
        result: Any,
        *,
        show_log: bool,
        event: CTePresenterAuditEvent,
        started: float,
    ) -> dict[str, Any]:
        self.view.files = list(result.files)
        for method_name in ("refresh_table", "update_stats"):
            callback = getattr(self.view, method_name, None)
            if callable(callback):
                callback()
        log = result.to_log()
        self.view.last_import_log = dict(log)
        performance = dict(log.get("performance") or {})
        elapsed_ms = float(performance.get("total_elapsed_ms", 0) or 0)
        cache_hits = int(performance.get("cache_hits", 0) or 0)
        self.view.set_status(
            "Importação XML: "
            f"{result.added} adicionado(s), {result.skipped} repetido(s) ignorado(s). "
            f"Cache: {cache_hits}. Tempo: {elapsed_ms / 1000.0:.2f}s. "
            f"Total real: {result.total}."
        )
        if result.errors:
            warning = getattr(self.view, "_notify_warning", None)
            if not callable(warning):
                warning = getattr(self.view, "_notify_error", None)
            if callable(warning):
                warning(
                    "Alguns arquivos não foram carregados:\n\n"
                    + "\n".join(result.errors[:10])
                )
        if show_log and result.should_show_log:
            show = getattr(self.view, "show_xml_import_log_2640", None)
            if callable(show):
                show(log)
        event.generated = result.added
        event.source = "importador XML rápido em lote"
        event.details.update(
            {
                "selected": result.selected,
                "added": result.added,
                "skipped": result.skipped,
                "cleaned": result.cleaned,
                "errors": len(result.errors),
                "total": result.total,
                "performance": performance,
                "service_version": self.xml_import_service.version,
            }
        )
        self._finish(event, started, status="OK" if result.selected else "SEM_DADOS")
        return log

    def _progress_callback(self) -> Callable[[int, int, str], None]:
        state = {"last_percent": -1}

        def update(done: int, total: int, stage: str) -> None:
            total = max(1, int(total or 1))
            percent = min(100, int(int(done or 0) * 100 / total))
            if percent < 100 and percent < state["last_percent"] + 5:
                return
            state["last_percent"] = percent
            text = f"Lendo XMLs: {done}/{total} ({percent}%) · {stage.replace('_', ' ')}"
            after = getattr(self.view, "after", None)
            if callable(after):
                try:
                    after(0, lambda message=text: self.view.set_status(message))
                except Exception:
                    pass

        return update

    def import_paths(self, paths: Any, *, show_log: bool = True) -> dict[str, Any]:
        event, started = self._event("import_paths")
        if getattr(self.view, "_xml_import_busy_2697", False):
            previous = getattr(self.view, "last_import_log", None)
            self._finish(event, started, status="IGNORADO_REENTRANTE")
            return dict(previous or {})
        self.view._xml_import_busy_2697 = True
        try:
            result = self.xml_import_service.import_paths(
                list(getattr(self.view, "files", []) or []),
                paths,
                parser=self.parse_document,
                progress=self._progress_callback(),
            )
            return self._apply_import_result(
                result,
                show_log=show_log,
                event=event,
                started=started,
            )
        except Exception as exc:
            self._finish(event, started, error=exc)
            raise
        finally:
            self.view._xml_import_busy_2697 = False

    def import_paths_async(self, paths: Any, *, show_log: bool = True) -> dict[str, Any]:
        """Executa leitura e cache fora da thread da interface Tk.

        A atualização de tabela, cards e diálogos permanece na thread principal.
        """
        event, started = self._event("import_paths_async")
        if getattr(self.view, "_xml_import_busy_2697", False):
            self._finish(event, started, status="IGNORADO_REENTRANTE")
            return {"scheduled": False, "reason": "busy"}

        self.view._xml_import_busy_2697 = True
        existing = list(getattr(self.view, "files", []) or [])
        try:
            self.view.set_status("Preparando importação rápida dos XMLs...")
        except Exception:
            pass

        def schedule(callback: Callable[[], None]) -> None:
            after = getattr(self.view, "after", None)
            if callable(after):
                try:
                    after(0, callback)
                    return
                except Exception:
                    pass
            callback()

        def worker() -> None:
            try:
                result = self.xml_import_service.import_paths(
                    existing,
                    paths,
                    parser=self.parse_document,
                    progress=self._progress_callback(),
                )
            except Exception as exc:
                def fail(error: Exception = exc) -> None:
                    try:
                        self._finish(event, started, error=error)
                        notifier = getattr(self.view, "_notify_error", None)
                        if callable(notifier):
                            notifier(f"Falha na importação XML: {error}")
                    finally:
                        self.view._xml_import_busy_2697 = False
                schedule(fail)
                return

            def finish() -> None:
                try:
                    self._apply_import_result(
                        result,
                        show_log=show_log,
                        event=event,
                        started=started,
                    )
                finally:
                    self.view._xml_import_busy_2697 = False

            schedule(finish)

        Thread(target=worker, name="central-cte-xml-import", daemon=True).start()
        return {"scheduled": True, "mode": "background"}

    def selected_or_visible_infos(self) -> tuple[list[dict[str, Any]], str]:
        return self.services.selected_or_visible(self.view)

    def exact_status_values(self) -> tuple[str, ...]:
        return self.services.exact_status_values(
            list(getattr(self.view, "files", []) or [])
        )

    def matches_advanced_filters(self, info: Mapping[str, Any]) -> bool:
        return self.services.matches_advanced_filters(
            info,
            exact_status=getattr(self.view, "filter_exact_status_var").get(),
            manual_review=getattr(self.view, "filter_manual_review_var").get(),
            observation=getattr(self.view, "filter_observation_var").get(),
            ignored_nfs=getattr(self.view, "filter_ignored_nf_var").get(),
        )

    def apply_complementary_information(self, text: Any, *, infos: list[dict[str, Any]] | None = None, source: str | None = None) -> int:
        event, started = self._event("apply_complementary_information")
        try:
            if infos is None:
                infos, resolved_source = self.selected_or_visible_infos()
                source = source or resolved_source
            infos = [info for info in list(infos or []) if self.services.is_cte(info)]
            if not infos:
                raise ValueError("Adicione ao menos um XML de CT-e antes de inserir a informação complementar.")
            if not callable(self.cleaner) or not callable(self.complementary_applier):
                raise RuntimeError("O serviço de informação complementar não foi conectado.")
            count = self.services.apply_complementary_information(
                infos,
                text,
                cleaner=self.cleaner,
                applier=self.complementary_applier,
                max_chars=self.max_complementary_chars,
            )
            event.generated = count
            event.source = source or "seleção atual"
            self._finish(event, started)
            return count
        except Exception as exc:
            self._finish(event, started, error=exc)
            raise

    def generate_htmls(self, output_dir: str | Path | None = None) -> list[Path]:
        event, started = self._event("generate_htmls")
        try:
            infos, source = self.selected_or_visible_infos()
            if not infos:
                self.view._notify_info("Nenhum XML marcado ou visível para gerar HTML.")
                self._finish(event, started, status="SEM_DADOS")
                return []
            if not callable(self.render_document):
                raise RuntimeError("O renderizador de DACTE não foi conectado.")
            target = Path(output_dir) if output_dir else self.view._choose_html_output_dir()
            if not target:
                self._finish(event, started, status="CANCELADO")
                return []
            generated = self.services.write_individual_htmls(
                infos,
                target,
                self.render_document,
            )
            self.view.set_status(
                f"{len(generated)} HTML(s) dos XMLs {source} salvo(s) em {target}"
            )
            self.view._notify_info(
                f"{len(generated)} HTML(s) gerado(s) a partir dos XMLs {source}."
            )
            event.generated = len(generated)
            event.source = source
            event.details["output_dir"] = str(target)
            self._finish(event, started)
            return generated
        except Exception as exc:
            self.view._notify_error(f"Erro ao gerar HTMLs:\n\n{exc}")
            self._finish(event, started, error=exc)
            return []

    def generate_single_html(self, output_path: str | Path | None = None) -> Path | None:
        event, started = self._event("generate_single_html")
        try:
            infos, source = self.selected_or_visible_infos()
            if not infos:
                self.view._notify_info("Nenhum XML marcado ou visível para gerar HTML único.")
                self._finish(event, started, status="SEM_DADOS")
                return None
            if not callable(self.render_document):
                raise RuntimeError("O renderizador de DACTE não foi conectado.")
            target = Path(output_path) if output_path else self.view._choose_batch_html_path(len(infos))
            if not target:
                self._finish(event, started, status="CANCELADO")
                return None
            generated = self.services.write_batch_html(
                infos,
                target,
                self.render_document,
            )
            try:
                webbrowser.open(generated.resolve().as_uri())
            except Exception:
                pass
            self.view.set_status(
                f"HTML único dos XMLs {source} salvo em {generated}"
            )
            self.view._notify_info(
                f"HTML único gerado com {len(infos)} XML(s) {source}."
            )
            event.generated = 1
            event.source = source
            event.details.update({"output_path": str(generated), "documents": len(infos)})
            self._finish(event, started)
            return generated
        except Exception as exc:
            self.view._notify_error(f"Erro ao gerar HTML único:\n\n{exc}")
            self._finish(event, started, error=exc)
            return None

    def open_signature_pdf(self) -> bool:
        event, started = self._event("open_signature_pdf")
        try:
            if not callable(self.render_document):
                raise RuntimeError("O renderizador de DACTE não foi conectado.")
            self.services.open_signature_manager(
                runtime_dir=self.runtime_dir(),
                engine_dir=self.engine_dir(),
                render_document=self.render_document,
                infos_provider=self.selected_or_visible_infos,
            )
            event.source = "interface assinatura/PDF sob demanda"
            self._finish(event, started)
            return True
        except Exception as exc:
            self.view._notify_error(
                f"Não foi possível abrir Assinaturas e PDF:\n\n{exc}"
            )
            self._finish(event, started, error=exc)
            return False


__all__ = ["PRESENTER_VERSION", "CTePagePresenter"]
