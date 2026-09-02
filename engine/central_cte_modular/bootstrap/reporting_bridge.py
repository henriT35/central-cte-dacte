from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from typing import Any, MutableMapping

from ..reports import InvoiceExecutiveXlsxWriter, InvoiceReportAuditor, InvoiceReportAuditResult, InvoiceReportAuditWriter, InvoiceReportBuilder

BRIDGE_VERSION = "2.7.0-RC25"


def install_reporting_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    paths = services.resolve("paths")
    logger = services.resolve("logger")
    settings = services.resolve("settings")
    audit_dir = Path(paths.reports) / "relatorios_modulares_sombra"
    audit_dir.mkdir(parents=True, exist_ok=True)
    force_legacy_flag = Path(paths.sessions) / "FORCAR_RELATORIOS_LEGADOS.flag"

    builder = InvoiceReportBuilder()
    auditor = InvoiceReportAuditor()
    audit_writer = InvoiceReportAuditWriter(audit_dir)
    xlsx_writer = InvoiceExecutiveXlsxWriter()

    for name, instance in (
        ("invoice_report_builder", builder),
        ("invoice_report_auditor", auditor),
        ("invoice_report_audit_writer", audit_writer),
        ("xlsx_writer", xlsx_writer),
    ):
        try:
            services.register_instance(name, instance)
        except Exception:
            pass

    patch_lock = threading.RLock()
    patched_classes: set[int] = set()

    def log(message: str, **extra: Any) -> None:
        try:
            logger.write("relatorios_modulares", message=str(message), **extra)
        except Exception:
            pass

    def _true(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "sim", "yes", "on"}

    def report_mode() -> str:
        if force_legacy_flag.exists() or _true(os.environ.get("CENTRAL_CTE_FORCE_LEGACY_REPORTS")):
            return "legacy"
        env = str(os.environ.get("CENTRAL_CTE_INVOICE_REPORT_MODE", "") or "").strip().lower()
        try:
            configured = str((settings.load() or {}).get("invoice_report_mode") or "").strip().lower()
        except Exception:
            configured = ""
        raw = env or configured or "modular_guarded"
        aliases = {
            "modular": "modular_guarded",
            "guarded": "modular_guarded",
            "modular_guarded": "modular_guarded",
            "promocao_controlada": "modular_guarded",
            "shadow": "shadow",
            "sombra": "shadow",
            "legacy": "legacy",
            "legado": "legacy",
        }
        return aliases.get(raw, "modular_guarded")

    def _notify(page: Any, title: str, text: str, *, error: bool = False) -> None:
        shown = False
        QMessageBox = module_globals.get("QMessageBox")
        if QMessageBox is None:
            for module in list(sys.modules.values()):
                try:
                    QMessageBox = getattr(module, "QMessageBox", None)
                    if QMessageBox is not None:
                        break
                except Exception:
                    continue
        try:
            if QMessageBox is not None:
                (QMessageBox.critical if error else QMessageBox.information)(page, title, text)
                shown = True
        except Exception:
            pass
        if not shown:
            try:
                import tkinter.messagebox as messagebox
                (messagebox.showerror if error else messagebox.showinfo)(title, text)
            except Exception:
                pass
        try:
            setter = getattr(page, "set_status", None)
            if callable(setter):
                setter(text.replace("\n", " "))
        except Exception:
            pass

    def _error_log(stage: str) -> Path | None:
        try:
            log_dir = Path(paths.logs)
            log_dir.mkdir(parents=True, exist_ok=True)
            path = log_dir / f"erro_relatorio_modular_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            path.write_text(
                "ERRO RELATÓRIO DINÂMICO DE FATURAS RC25\n" + "=" * 72 + "\n"
                + f"Etapa: {stage}\nData/hora: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                + traceback.format_exc(),
                encoding="utf-8",
            )
            return path
        except Exception:
            return None

    def _problem_flag(args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
        if "only_problem_invoices" in kwargs:
            return bool(kwargs.get("only_problem_invoices"))
        # Sinais clicked(bool) do Qt não devem alterar o conteúdo do relatório.
        if args and isinstance(args[0], bool):
            return False
        return bool(args[0]) if args else False

    def patch_class(cls: type) -> bool:
        with patch_lock:
            if id(cls) in patched_classes or getattr(cls, "_relatorios_modulares_2674", False):
                return True
            current_build = getattr(cls, "build_invoice_report_sheets", None)
            if not callable(current_build) or not getattr(cls, "_motor_faturas_promocao_2673", False):
                return False
            setattr(cls, "LEGACY_BUILD_INVOICE_REPORT_2674", current_build)

            def build_invoice_report_sheets(self: Any, *args: Any, **kwargs: Any) -> Any:
                started = time.perf_counter()
                only_problem = _problem_flag(args, kwargs)
                mode = report_mode()
                legacy_sheets: Any = None
                modular_result = None
                audit_result: InvoiceReportAuditResult
                if mode == "legacy":
                    result = current_build(self, only_problem)
                    try:
                        modular_result = builder.build(self, only_problem)
                        audit_result = auditor.compare(result, modular_result.sheets, official_source="LEGADO")
                        audit_result.elapsed_ms = (time.perf_counter() - started) * 1000
                        audit_writer.write(audit_result, consumer="build_legacy")
                        self._modular_invoice_report_last_2674 = audit_result.to_dict()
                    except Exception as exc:
                        log("Auditoria de relatório ignorada no modo legado", error=f"{type(exc).__name__}: {exc}")
                    return result

                try:
                    legacy_sheets = current_build(self, only_problem)
                except Exception as exc:
                    log("Gerador legado de relatório falhou", error=f"{type(exc).__name__}: {exc}")
                    raise

                try:
                    modular_result = builder.build(self, only_problem)
                    official = "LEGADO" if mode == "shadow" else "MODULAR"
                    audit_result = auditor.compare(legacy_sheets, modular_result.sheets, official_source=official)
                    # A diferença estrutural de seis para cinco abas é a migração
                    # esperada da RC25. O modo shadow continua preservando o legado;
                    # no modo promovido a fonte oficial é sempre o modelo canônico.
                    if mode == "shadow":
                        audit_result.official_source = "LEGADO"
                        official_sheets = legacy_sheets
                    else:
                        audit_result.official_source = "MODULAR"
                        official_sheets = modular_result.sheets
                    audit_result.elapsed_ms = (time.perf_counter() - started) * 1000
                    audit_writer.write(audit_result, consumer="build_invoice_report_sheets")
                    self._modular_invoice_report_last_2674 = audit_result.to_dict()
                    self._modular_invoice_report_build_2674 = modular_result.to_dict(include_sheets=False)
                    log(
                        "Relatório de faturas construído",
                        mode=mode,
                        classification=audit_result.classification,
                        official_source=audit_result.official_source,
                        invoice_count=modular_result.invoice_count,
                        item_count=modular_result.item_count,
                        blocked_value=modular_result.blocked_value,
                    )
                    return official_sheets
                except Exception as exc:
                    audit_result = InvoiceReportAuditResult(
                        version=BRIDGE_VERSION,
                        classification="ERRO",
                        official_source="LEGADO",
                        legacy_fingerprint="",
                        modular_fingerprint="",
                        error=f"{type(exc).__name__}: {exc}",
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                    )
                    try:
                        audit_writer.write(audit_result, consumer="build_fallback")
                        self._modular_invoice_report_last_2674 = audit_result.to_dict()
                    except Exception:
                        pass
                    log("Fallback do relatório modular", error=audit_result.error)
                    return legacy_sheets

            setattr(cls, "build_invoice_report_sheets", build_invoice_report_sheets)

            def export_report(self: Any, *args: Any, **kwargs: Any) -> str | None:
                try:
                    sheets = self.build_invoice_report_sheets(False)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = Path(paths.reports) / f"relatorio_faturas_dinamico_RC25_{stamp}.xlsx"
                    xlsx_writer.write(path, sheets)
                    source = str((getattr(self, "_modular_invoice_report_last_2674", {}) or {}).get("official_source") or "LEGADO")
                    _notify(self, "Central CT-e / DACTE", f"Relatório de faturas gerado com sucesso ({source.lower()} controlado):\n\n{path}")
                    try:
                        self._modular_invoice_report_export_2674 = {"path": str(path), "source": source, "version": BRIDGE_VERSION}
                    except Exception:
                        pass
                    return str(path)
                except Exception as exc:
                    error_path = _error_log("export_report")
                    extra = f"\n\nLog do erro:\n{error_path}" if error_path else ""
                    _notify(self, "Central CT-e / DACTE", f"Erro ao gerar relatório de faturas.\n{exc}{extra}", error=True)
                    return None

            for name in ("export_report", "export_invoice_report", "exportar_relatorio", "exportar_relatorio_faturas", "export_faturas_report", "exportar_relatorio_faturas_2663"):
                try:
                    setattr(cls, name, export_report)
                except Exception:
                    pass

            def audit_manual(self: Any) -> dict[str, Any]:
                legacy = current_build(self, False)
                modular = builder.build(self, False)
                result = auditor.compare(legacy, modular.sheets, official_source="LEGADO")
                audit_writer.write(result, consumer="manual")
                self._modular_invoice_report_last_2674 = result.to_dict()
                return result.to_dict()

            setattr(cls, "auditar_relatorio_faturas_modular_2674", audit_manual)
            setattr(cls, "exportar_relatorio_faturas_modular_2674", export_report)
            setattr(cls, "_relatorios_modulares_2674", True)
            patched_classes.add(id(cls))
            log("FaturasPage instrumentada para relatórios", class_module=getattr(cls, "__module__", ""), mode=report_mode())
            return True

    def scan_and_patch() -> int:
        found: list[type] = []
        direct = module_globals.get("FaturasPage")
        if isinstance(direct, type):
            found.append(direct)
        for exact in (True, False):
            for module in list(sys.modules.values()):
                try:
                    cls = getattr(module, "FaturasPage", None)
                    if not isinstance(cls, type) or cls in found:
                        continue
                    defining = getattr(cls, "__module__", "") == getattr(module, "__name__", "")
                    if defining == exact:
                        found.append(cls)
                except Exception:
                    continue
        return sum(1 for cls in found if patch_class(cls))

    patched_now = scan_and_patch()

    module_globals.update({
        "MODULAR_INVOICE_REPORT_BUILDER": builder,
        "MODULAR_INVOICE_REPORT_AUDITOR": auditor,
        "MODULAR_INVOICE_REPORT_AUDIT_WRITER": audit_writer,
        "MODULAR_XLSX_WRITER": xlsx_writer,
        "MODULAR_INVOICE_REPORT_DIR": audit_dir,
        "MODULAR_INVOICE_REPORT_FORCE_LEGACY_FLAG": force_legacy_flag,
        "MODULAR_INVOICE_REPORT_VERSION": BRIDGE_VERSION,
        "get_invoice_report_mode": report_mode,
        "rescan_reporting_bridge": scan_and_patch,
    })
    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": report_mode(),
        "patched_classes": patched_now,
        "audit_dir": str(audit_dir),
        "force_legacy_flag": str(force_legacy_flag),
        "official_result": "modular_rc25_dynamic_reports_in_guarded_mode",
        "activation": "event_driven_by_view_and_page_coordinator",
        "polling_thread": False,
    }
