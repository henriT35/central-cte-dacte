from __future__ import annotations

from contextlib import contextmanager
import threading
import time
from typing import Any, Callable
import weakref

from .audit import UIAuditWriter
from .models import UIActionAudit, UIStateSnapshot

CONTROLLER_VERSION = "2.6.67.5"


class BaseUIController:
    """Orquestra ações da tela sem conhecer Tkinter ou PySide6.

    A regra de negócio permanece nos serviços/motores. O controlador apenas
    define a fronteira da ação, impede dupla execução de operações pesadas e
    registra o estado antes/depois. O callback oficial é chamado exatamente
    uma vez.
    """

    controller_name = "base"
    guarded_actions = frozenset({"import", "process", "validate", "export", "print"})

    def __init__(self, page: Any, audit_writer: UIAuditWriter, mode_getter: Callable[[], str], logger: Any = None) -> None:
        try:
            self._page_ref = weakref.ref(page)
        except TypeError:
            self._page_ref = lambda: page
        self.audit_writer = audit_writer
        self.mode_getter = mode_getter
        self.logger = logger
        self._lock = threading.RLock()
        self._busy: set[str] = set()
        self._local = threading.local()

    @property
    def page(self) -> Any:
        return self._page_ref()

    @contextmanager
    def _top_level(self):
        depth = int(getattr(self._local, "depth", 0) or 0)
        self._local.depth = depth + 1
        try:
            yield depth == 0
        finally:
            self._local.depth = depth

    def _official_source(self, page: Any) -> str:
        for name in (
            "_modular_invoice_report_last_2674",
            "_modular_invoice_promotion_last",
            "_modular_invoice_decision_last",
            "_modular_xml_parser_last",
        ):
            try:
                payload = getattr(page, name, None)
                if isinstance(payload, dict):
                    value = (
                        payload.get("official_source")
                        or payload.get("official_result")
                        or payload.get("parser_used")
                        or payload.get("source")
                    )
                    if value:
                        return str(value)
            except Exception:
                pass
        return ""

    def _metadata(self, page: Any, action: str, method: str) -> dict[str, Any]:
        return {"action_group": action, "wrapped_method": method}

    def _log(self, message: str, **payload: Any) -> None:
        try:
            if self.logger is not None:
                self.logger.write("controladores_ui", message=message, controller=self.controller_name, **payload)
        except Exception:
            pass

    def dispatch(
        self,
        action: str,
        method: str,
        callback: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        page = self.page
        if page is None:
            return callback(*args, **kwargs)
        mode = str(self.mode_getter() or "modular_guarded")
        if mode == "legacy":
            return callback(*args, **kwargs)

        with self._top_level() as top_level:
            if not top_level:
                return callback(*args, **kwargs)

            guarded = mode == "modular_guarded" and action in self.guarded_actions
            if guarded:
                with self._lock:
                    if self._busy:
                        self._log(
                            "Ação concorrente bloqueada",
                            action=action,
                            method=method,
                            active_actions=sorted(self._busy),
                        )
                        return None
                    self._busy.add(action)

            before = UIStateSnapshot.capture(page)
            started = time.perf_counter()
            result: Any = None
            error = ""
            classification = "OK"
            try:
                result = callback(*args, **kwargs)
                return result
            except Exception as exc:
                classification = "ERRO"
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000
                after = UIStateSnapshot.capture(page)
                if guarded:
                    with self._lock:
                        self._busy.discard(action)
                audit = UIActionAudit.create(
                    version=CONTROLLER_VERSION,
                    controller=self.controller_name,
                    page=page,
                    action=action,
                    method=method,
                    mode=mode,
                    classification=classification,
                    elapsed_ms=elapsed_ms,
                    before=before,
                    after=after,
                    result=result,
                    error=error,
                    official_source=self._official_source(page),
                    thread_name=threading.current_thread().name,
                    metadata=self._metadata(page, action, method),
                )
                try:
                    self.audit_writer.write(audit)
                except Exception as exc:
                    self._log("Falha ao gravar auditoria da interface", error=f"{type(exc).__name__}: {exc}")


class ApplicationUIController(BaseUIController):
    controller_name = "application"


class CTeUIController(BaseUIController):
    controller_name = "cte"

    def _metadata(self, page: Any, action: str, method: str) -> dict[str, Any]:
        data = super()._metadata(page, action, method)
        try:
            data["filtered_count"] = len(page.filtered_files()) if callable(getattr(page, "filtered_files", None)) else 0
        except Exception:
            data["filtered_count"] = 0
        return data


class InvoiceUIController(BaseUIController):
    controller_name = "invoices"

    def _metadata(self, page: Any, action: str, method: str) -> dict[str, Any]:
        data = super()._metadata(page, action, method)
        for attr, key in (
            ("invoice_rows", "invoice_count"),
            ("invoice_detail_records", "item_count"),
            ("invoice_docs", "document_count"),
        ):
            try:
                data[key] = len(getattr(page, attr, None) or [])
            except Exception:
                data[key] = 0
        return data
