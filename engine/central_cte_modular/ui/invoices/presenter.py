from __future__ import annotations

"""Presenter direto da página de faturas.

O presenter coordena a vista e os serviços modulares sem monkeypatch, manifesto
de hotfix ou descoberta de classes em ``sys.modules``.
"""

import time
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

from .audit import InvoicePresenterAuditEvent, InvoicePresenterAuditWriter
from .services import InvoicePageServices
from .read_model import build_invoice_read_model

PRESENTER_VERSION = "2.7.0-rc26.5-segundo-pente-fino"


class InvoicePagePresenter:
    version = PRESENTER_VERSION

    def __init__(
        self,
        view: Any,
        *,
        services: InvoicePageServices | None = None,
        audit_writer: InvoicePresenterAuditWriter | None = None,
    ) -> None:
        self.view = view
        self.services = services or InvoicePageServices()
        self.audit_writer = audit_writer or InvoicePresenterAuditWriter(None)
        self.last_event: dict[str, Any] = {}

    @staticmethod
    def money(value: Any) -> str:
        try:
            return "R$ " + f"{float(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return "R$ 0,00"

    def _event(self, action: str) -> tuple[InvoicePresenterAuditEvent, float]:
        return (
            InvoicePresenterAuditEvent(
                action=action,
                status="EM_EXECUCAO",
                started_at=datetime.now().isoformat(timespec="seconds"),
            ),
            time.perf_counter(),
        )

    def _finish(self, event: InvoicePresenterAuditEvent, started: float, *, status: str = "OK", error: Exception | None = None) -> None:
        event.elapsed_ms = (time.perf_counter() - started) * 1000.0
        event.status = "ERRO" if error is not None else status
        if error is not None:
            event.error = f"{type(error).__name__}: {error}"
        event.documents = len(getattr(self.view, "invoice_docs", []) or [])
        event.invoices = len(getattr(self.view, "invoice_rows", []) or [])
        event.items = len(getattr(self.view, "invoice_detail_records", []) or [])
        event.total_value = sum(
            float(record.get("Valor fatura") or record.get("billed_value") or 0.0)
            for record in list(getattr(self.view, "invoice_detail_records", []) or [])
            if isinstance(record, Mapping)
        )
        event.blocked_value = sum(
            float(record.get("Valor pendente") or record.get("Valor não pagar") or record.get("blocked_value") or 0.0)
            for record in list(getattr(self.view, "invoice_detail_records", []) or [])
            if isinstance(record, Mapping)
        )
        event.payable_value = max(event.total_value - event.blocked_value, 0.0)
        self.last_event = event.to_dict()
        try:
            self.view._modular_invoice_presenter_last_2694 = dict(self.last_event)
            self.view._modular_invoice_presenter_last_2693 = dict(self.last_event)
        except Exception:
            pass
        self.audit_writer.write(event)

    def add_invoices(self, paths: Iterable[str | Path] | str | Path | None = None) -> int:
        event, started = self._event("add_invoices")
        added = duplicate = errors = 0
        error_messages: list[str] = []
        try:
            if paths is None:
                paths = self.view._choose_invoice_paths()
            if isinstance(paths, (str, Path)):
                paths = [paths]
            for raw in paths or []:
                path = Path(raw)
                if not path.exists() or not path.is_file():
                    errors += 1
                    error_messages.append(f"{path.name or path}: arquivo não encontrado ou inválido")
                    continue
                if path.suffix.lower() != ".pdf":
                    errors += 1
                    error_messages.append(f"{path.name}: formato não suportado; selecione um PDF")
                    continue
                try:
                    digest = sha256(path.read_bytes()).hexdigest()
                    if digest in self.view._invoice_hashes:
                        duplicate += 1
                        continue
                    text, backend = self.services.read_pdf(
                        path,
                        fallback=self.view._pdf_text_fallback(),
                    )
                    document = {
                        "path": str(path),
                        "arquivo": str(path),
                        "texto": text,
                        "text_backend": backend,
                        "document_hash": digest,
                    }
                    self.view.invoice_docs.append(document)
                    self.view.files.append(str(path))
                    self.view.selected_paths.add(str(path))
                    self.view._invoice_hashes.add(digest)
                    self.view._modular_invoice_full_text_2671[str(path)] = text
                    self.view._modular_invoice_full_text_2671[path.name] = text
                    added += 1
                except Exception as exc:
                    errors += 1
                    error_messages.append(f"{path.name}: {exc}")
            self.view.set_status(
                f"Faturas adicionadas: {added}; repetidas ignoradas: {duplicate}; erros: {errors}."
            )
            self.update_cards()
            if errors:
                rejected = "\n".join(f"• {item}" for item in error_messages[:12])
                if len(error_messages) > 12:
                    rejected += f"\n• ... e mais {len(error_messages) - 12} arquivo(s)"
                prefix = (
                    f"{errors} fatura(s) foram rejeitadas durante a importação parcial."
                    if added
                    else "Não foi possível ler as faturas selecionadas."
                )
                notifier = getattr(self.view, "_notify_warning", None)
                if not callable(notifier):
                    notifier = getattr(self.view, "_notify_error", None)
                if callable(notifier):
                    notifier(prefix + "\n\n" + rejected)
            event.details.update({
                "added": added,
                "duplicates": duplicate,
                "errors": errors,
                "rejected_files": list(error_messages),
            })
            self._finish(event, started)
            return added
        except Exception as exc:
            self._finish(event, started, error=exc)
            raise

    def parse_invoice_text(self, text: Any, path: Any = "") -> dict[str, Any]:
        return self.services.parse_text(text, path)

    def snapshot_to_cache(self, snapshot: Any) -> None:
        model = build_invoice_read_model(snapshot, money=self.money)
        self.view.invoice_detail_records = [dict(record) for record in model.records]
        self.view.invoice_rows = [list(row) for row in model.rows]
        self.view.detail_rows_by_invoice = {
            key: [list(row) for row in rows]
            for key, rows in model.details_by_invoice.items()
        }
        self.view._invoice_read_model_rc13 = model

    def process_invoices(self) -> Any:
        event, started = self._event("process_invoices")
        try:
            if not self.view.invoice_docs:
                self.view.set_status("Adicione ao menos uma fatura antes de processar.")
                self._finish(event, started, status="SEM_DADOS")
                return None
            base_path = Path(str(self.view._base_path() or ""))
            base_ready = (base_path.is_dir() and any(base_path.glob("*.sswweb"))) or (base_path.suffix.lower() == ".sswweb" and base_path.is_file())
            if not base_ready:
                message = "Base SSW não localizada. Adicione ao menos um arquivo .sswweb na pasta bases antes de processar faturas."
                self.view.set_status(message)
                notifier = getattr(self.view, "_notify_error", None)
                if callable(notifier):
                    notifier(message)
                self._finish(event, started, status="SEM_BASE")
                return None
            self.view.set_status("Processando faturas pelo motor modular direto...")
            result = self.services.process(
                self.view.invoice_docs,
                base_path=base_path,
            )
            self.view._last_input_snapshot = result.input_snapshot
            self.view._last_decision_snapshot = result.decision_snapshot
            self.snapshot_to_cache(result.decision_snapshot)
            current_model = self.view._invoice_read_model_rc13
            self.view._modular_invoice_decision_last = {
                "official_source": "modular_presenter_rc26_5",
                "invoice_count": result.invoices,
                "item_count": result.items,
                "future_value": current_model.future_value,
                "internal_problem_value": current_model.internal_problem_value,
                "payable_value": result.payable_value,
            }
            self.view._invoice_base_info_rc14 = dict(result.base_info or {})
            self.view._rc14_base_source = str((result.base_info or {}).get("path") or "")
            self.refresh_partner_filter()
            self.refresh_table()
            self.update_cards()
            self.view.set_status(
                f"Processamento concluído: {current_model.ok_invoice_count} faturas OK, "
                f"{current_model.partial_invoice_count} parciais, "
                f"{current_model.future_invoice_count} com pagamento futuro e "
                f"{current_model.internal_problem_invoice_count} com problema interno."
            )
            event.details.update({
                "official_source": "modular_presenter_rc13",
                "input_fingerprint": getattr(result.decision_snapshot, "input_fingerprint", ""),
            })
            self._finish(event, started)
            return result.decision_snapshot
        except Exception as exc:
            self.view.set_status(f"Erro ao processar faturas: {exc}")
            self._finish(event, started, error=exc)
            raise

    def add_invoice_row(self, row: Iterable[Any]) -> None:
        values = list(row or [])
        while len(values) < self.view.invoice_table.columnCount():
            values.append("")
        index = self.view.invoice_table.rowCount()
        self.view.invoice_table.insertRow(index)
        for column, value in enumerate(values[: self.view.invoice_table.columnCount()]):
            self.view.invoice_table.setItem(
                index, column, self.view._invoice_cell(value)
            )

    def current_invoice_values(self) -> list[str]:
        row = self.view.invoice_table.currentRow()
        return self.view.invoice_table.values(row) if row >= 0 else []

    def refresh_table(self) -> int:
        partner = str(self.view.partner_filter_var.get() or "TODOS")
        status = str(self.view.status_filter_var.get() or "TODOS")
        search = str(self.view.search_filter_var.get() or "").strip().upper()
        self.view.invoice_table.setRowCount(0)
        for row in self.view.invoice_rows:
            values = [str(value or "") for value in row]
            if partner != "TODOS" and (len(values) < 2 or values[1] != partner):
                continue
            if status != "TODOS" and (len(values) < 10 or status not in values[9].upper()):
                continue
            if search and search not in " ".join(values).upper():
                continue
            self.add_invoice_row(values)
        return self.view.invoice_table.rowCount()

    def refresh_partner_filter(self) -> tuple[str, ...]:
        partners = sorted(
            {
                str(row[1])
                for row in self.view.invoice_rows
                if len(row) > 1 and row[1]
            }
        )
        values = ("TODOS", *partners)
        try:
            self.view.partner_filter.configure(values=values)
        except Exception:
            pass
        if self.view.partner_filter_var.get() not in values:
            self.view.partner_filter_var.set("TODOS")
        return values

    def load_details_for_selected(self) -> list[list[Any]]:
        for item in self.view.detail_tree.get_children(""):
            self.view.detail_tree.delete(item)
        values = self.current_invoice_values()
        if not values:
            return []
        invoice = str(values[0] or "")
        rows = list(self.view.detail_rows_by_invoice.get(invoice, []) or [])
        for row in rows:
            values = list(row)
            while len(values) < len(self.view.DETAIL_COLUMNS):
                values.append("")
            self.view.detail_tree.insert(
                "", "end", values=values[: len(self.view.DETAIL_COLUMNS)]
            )
        return rows

    def update_cards(self) -> dict[str, Any]:
        snapshot = getattr(self.view, "_last_decision_snapshot", None)
        if snapshot is not None:
            model = build_invoice_read_model(snapshot, money=self.money)
        else:
            class _EmptyModel:
                invoice_count = len(getattr(self.view, "invoice_rows", []) or [])
                ok_invoice_count = 0
                future_invoice_count = 0
                internal_problem_invoice_count = 0
                future_value = 0.0
                internal_problem_value = 0.0
                payable_value = 0.0
            model = _EmptyModel()
        self.view.card_faturas.set_values(
            str(model.invoice_count),
            f"{len(self.view.invoice_docs)} documentos",
        )
        self.view.card_itens.set_values(
            str(model.future_invoice_count),
            self.money(model.future_value),
        )
        self.view.card_ok.set_values(str(model.ok_invoice_count), self.money(model.payable_value))
        self.view.card_bloqueado.set_values(
            self.money(model.internal_problem_value),
            f"{model.internal_problem_invoice_count} faturas para conferir",
        )
        return {
            "faturas": model.invoice_count,
            "ok_faturas": model.ok_invoice_count,
            "faturas_pagamento_futuro": model.future_invoice_count,
            "valor_pagamento_futuro": model.future_value,
            "faturas_problema_interno": model.internal_problem_invoice_count,
            "valor_problema_interno": model.internal_problem_value,
        }

    def build_invoice_report_sheets(self, only_problem_invoices: bool = False) -> list[Any]:
        return self.services.build_report(self.view, only_problem_invoices)

    def export_report(self) -> str | None:
        event, started = self._event("export_report")
        try:
            sheets = self.build_invoice_report_sheets(False)
            report_dir = self.view._report_dir()
            report_dir.mkdir(parents=True, exist_ok=True)
            path = report_dir / f"relatorio_faturas_dinamico_RC26_5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            self.services.write_report(path, sheets)
            self.view.set_status(f"Relatório gerado: {path}")
            self.view._notify_info(f"Relatório gerado com sucesso:\n\n{path}")
            event.details.update({"path": str(path), "sheet_count": len(sheets)})
            self._finish(event, started)
            return str(path)
        except Exception as exc:
            self.view._notify_error(f"Erro ao gerar relatório de faturas.\n{exc}")
            self._finish(event, started, error=exc)
            return None

    def clear_invoices(self) -> bool:
        event, started = self._event("clear_invoices")
        try:
            self.view.files.clear()
            self.view.selected_paths.clear()
            self.view.invoice_docs.clear()
            self.view.invoice_rows.clear()
            self.view.invoice_detail_records.clear()
            self.view.detail_rows_by_invoice.clear()
            self.view._invoice_hashes.clear()
            self.view._modular_invoice_full_text_2671.clear()
            for attribute in (
                "_last_input_snapshot", "_last_decision_snapshot", "_invoice_read_model_rc13",
                "_invoice_read_model_rc14", "_invoice_read_model_rc15", "_modular_invoice_decision_last",
                "_invoice_base_info_rc14", "_invoice_base_info_rc15", "_rc14_base_source",
                "_rc15_base_source", "_rc13_processed_source_signature", "_rc13_invoice_card_state",
            ):
                try:
                    setattr(self.view, attribute, None)
                except Exception:
                    pass
            self.view.invoice_table.setRowCount(0)
            for item in self.view.detail_tree.get_children(""):
                self.view.detail_tree.delete(item)
            self.view.partner_filter_var.set("TODOS")
            self.view.status_filter_var.set("TODOS")
            self.view.search_filter_var.set("")
            self.refresh_partner_filter()
            self.update_cards()
            self.view.set_status("Lista de faturas limpa. Nenhum resultado anterior permanece ativo.")
            self._finish(event, started)
            return True
        except Exception as exc:
            self._finish(event, started, error=exc)
            raise

__all__ = ["PRESENTER_VERSION", "InvoicePagePresenter"]
