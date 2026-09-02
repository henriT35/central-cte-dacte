# -*- coding: utf-8 -*-
"""Página modular de faturas 2.7.0.

A vista contém apenas construção visual e delegadores. Importação, vínculo,
decisão, filtros, cards e exportação são coordenados por um presenter modular
direto, sem os 19 monkeypatches históricos da ``FaturasPage``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from central_cte_modular.ui.invoices import (
    InvoicePagePresenter,
    InvoicePageServices,
    InvoicePresenterAuditWriter,
)


class _InvoiceCell:
    def __init__(self, value: Any = "") -> None:
        self._value = "" if value is None else str(value)

    def text(self) -> str:
        return self._value


class TkInvoiceTableAdapter:
    """Pequeno adaptador QTableWidget-like sobre ``ttk.Treeview``.

    O adaptador conserva o pequeno contrato QTableWidget-like utilizado por
    componentes compartilhados, sem inicializar uma segunda toolkit gráfica.
    """

    def __init__(self, tree, columns: tuple[str, ...]) -> None:
        self.tree = tree
        self.columns = tuple(columns)
        self._rows: list[list[str]] = []
        self._item_ids: list[str] = []

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        getter = getattr(value, "text", None)
        if callable(getter):
            try:
                return str(getter() or "")
            except Exception:
                pass
        label = getattr(value, "label", None)
        getter = getattr(label, "text", None)
        if callable(getter):
            try:
                return str(getter() or "")
            except Exception:
                pass
        return str(value)

    def columnCount(self) -> int:
        return len(self.columns)

    def rowCount(self) -> int:
        return len(self._rows)

    def setRowCount(self, count: int) -> None:
        count = max(int(count or 0), 0)
        if count == 0:
            for item_id in list(self._item_ids):
                try:
                    self.tree.delete(item_id)
                except Exception:
                    pass
            self._rows.clear()
            self._item_ids.clear()
            return
        while len(self._rows) < count:
            self.insertRow(len(self._rows))
        while len(self._rows) > count:
            item_id = self._item_ids.pop()
            self._rows.pop()
            try:
                self.tree.delete(item_id)
            except Exception:
                pass

    def insertRow(self, row: int) -> None:
        row = max(0, min(int(row), len(self._rows)))
        values = ["" for _ in self.columns]
        item_id = self.tree.insert("", row, values=values)
        self._rows.insert(row, values)
        self._item_ids.insert(row, item_id)

    def setItem(self, row: int, column: int, item: Any) -> None:
        while len(self._rows) <= row:
            self.insertRow(len(self._rows))
        if not 0 <= column < self.columnCount():
            return
        self._rows[row][column] = self._text(item)
        try:
            self.tree.item(self._item_ids[row], values=self._rows[row])
        except Exception:
            pass

    def setCellWidget(self, row: int, column: int, widget: Any) -> None:
        self.setItem(row, column, widget)

    def setRowHeight(self, row: int, height: int) -> None:
        return None

    def currentRow(self) -> int:
        try:
            selected = self.tree.selection()
            if not selected:
                return -1
            return self._item_ids.index(selected[0])
        except Exception:
            return -1

    def item(self, row: int, column: int) -> _InvoiceCell | None:
        try:
            return _InvoiceCell(self._rows[row][column])
        except Exception:
            return None

    def cellWidget(self, row: int, column: int) -> None:
        return None

    def values(self, row: int) -> list[str]:
        try:
            return list(self._rows[row])
        except Exception:
            return []


class FaturasPage(tk.Frame):
    _invoice_presenter_modular_2694 = True
    _motor_faturas_sombra_2672 = True
    _motor_faturas_promocao_2673 = True
    _relatorios_modulares_2674 = True

    COLUMNS = (
        "Fatura", "Parceiro", "Qtd.", "OK", "Pendências",
        "Valor Fatura", "Valor Pendente", "Valores", "Comprovantes", "Status",
    )
    DETAIL_COLUMNS = ("CT-e", "NF", "Valor", "Base", "Conferência do valor", "Fatura base", "DY", "Escaneamento", "Decisão financeira", "Motivo")

    def __init__(self, master, app=None):
        super().__init__(master, bg=BG)
        self.app = app or master
        self.files: list[str] = []
        self.selected_paths: set[str] = set()
        self.invoice_docs: list[dict[str, Any]] = []
        self.invoice_rows: list[list[Any]] = []
        self.invoice_detail_records: list[dict[str, Any]] = []
        self.detail_rows_by_invoice: dict[str, list[list[Any]]] = {}
        self._invoice_hashes: set[str] = set()
        self._modular_invoice_full_text_2671: dict[str, str] = {}
        self._modular_invoice_full_text_2672 = self._modular_invoice_full_text_2671
        self.partner_filter_var = tk.StringVar(value="TODOS")
        self.status_filter_var = tk.StringVar(value="TODOS")
        self.search_filter_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Pronto para carregar faturas.")
        self._last_input_snapshot = None
        self._last_decision_snapshot = None
        self._invoice_presenter_modular_2694 = True
        self._motor_faturas_sombra_2672 = True
        self._motor_faturas_promocao_2673 = True
        self._relatorios_modulares_2674 = True
        self._build_view()
        audit_dir = self._report_dir() / "presenter_faturas_modular"
        self.invoice_services = InvoicePageServices()
        self.invoice_presenter = InvoicePagePresenter(
            self,
            services=self.invoice_services,
            audit_writer=InvoicePresenterAuditWriter(audit_dir),
        )
        self.after(220, lambda: self.set_base_ready(bool(self._base_path())))

    def _build_view(self):
        self._build_header()
        self._build_actions()
        self._build_filters()
        self._build_cards()
        self._build_tables()
        self._build_status()

    def _build_header(self):
        header = tk.Frame(self, bg="#ffffff", height=92)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Faturas de Parceiros", bg="#ffffff", fg=BLUE_DARK,
                 font=("Segoe UI", 22, "bold"), anchor="w").pack(anchor="w", padx=24, pady=(15, 0))
        tk.Label(header, text="Importação, vínculo CT-e × NF × base e decisão de pagamento",
                 bg="#ffffff", fg=MUTED, font=("Segoe UI", 10), anchor="w").pack(anchor="w", padx=25, pady=(2, 0))
        tk.Frame(header, bg=LINE, height=1).pack(side="bottom", fill="x")

    def _build_actions(self):
        panel = tk.Frame(self, bg=BG, height=70)
        panel.pack(fill="x", padx=24, pady=(10, 4))
        panel.pack_propagate(False)
        actions = (
            ("icon_add", "Adicionar faturas", self.add_invoices, False, 170),
            ("icon_money", "Processar", self.process_invoices, False, 132),
            ("icon_doc", "Exportar relatório", self.export_report, False, 172),
            ("icon_eye", "Abrir detalhes", self.load_details_for_selected, False, 150),
            ("icon_trash", "Limpar", self.clear_invoices, True, 120),
        )
        for icon, text_, command, danger, width in actions:
            button = ImageButton(panel, icon, text_, command, danger=danger, width=width, height=52)
            button.pack(side="left", padx=(0, 10), pady=6)
            if text_ == "Processar":
                self.process_button = button

    def _build_filters(self):
        frame = tk.Frame(self, bg="#ffffff", highlightbackground=LINE, highlightthickness=1)
        frame.pack(fill="x", padx=24, pady=(4, 8))
        tk.Label(frame, text="Parceiro", bg="#ffffff", fg=MUTED, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(12, 5), pady=8)
        self.partner_filter = ttk.Combobox(frame, textvariable=self.partner_filter_var, values=("TODOS",), state="readonly", width=26)
        self.partner_filter.pack(side="left", padx=(0, 12), pady=7)
        tk.Label(frame, text="Status", bg="#ffffff", fg=MUTED, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 5), pady=8)
        self.status_filter = ttk.Combobox(frame, textvariable=self.status_filter_var,
                                         values=("TODOS", "OK PAGAR", "PAGAR PARCIAL / SALDO FUTURO", "PENDENTE INTEGRAL / PAGAMENTO FUTURO", "PAGAR PARCIAL / PROBLEMA INTERNO", "RETIDO INTEGRAL / PROBLEMA INTERNO", "INCONSISTENTE"), state="readonly", width=34)
        self.status_filter.pack(side="left", padx=(0, 12), pady=7)
        tk.Label(frame, text="Busca rápida", bg="#ffffff", fg=MUTED, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 5), pady=8)
        self.search_entry = ttk.Entry(frame, textvariable=self.search_filter_var, width=30)
        self.search_entry.pack(side="left", padx=(0, 8), pady=7)
        tk.Button(frame, text="Aplicar", command=self.apply_filters, bg="#eaf4ff", fg=BLUE_DARK, relief="flat", padx=12).pack(side="left", pady=7)
        self.partner_filter.bind("<<ComboboxSelected>>", lambda _e: self.apply_filters())
        self.status_filter.bind("<<ComboboxSelected>>", lambda _e: self.apply_filters())
        self.search_entry.bind("<Return>", lambda _e: self.apply_filters())

    def _build_cards(self):
        cards = tk.Frame(self, bg=BG, height=106)
        cards.pack(fill="x", padx=24, pady=(0, 8))
        cards.pack_propagate(False)
        self.card_faturas = StatCard(cards, "icon_doc", "0", "Faturas", "0 documentos")
        self.card_itens = StatCard(cards, "icon_sheet", "0", "Pagamento futuro", "R$ 0,00")
        self.card_ok = StatCard(cards, "icon_print_check", "0", "Liberados", "R$ 0,00")
        self.card_bloqueado = StatCard(cards, "icon_money", "R$ 0,00", "Problema interno", "0 faturas para conferir", color=RED)
        for card in (self.card_faturas, self.card_itens, self.card_ok, self.card_bloqueado):
            card.pack(side="left", fill="x", expand=True, padx=(0, 10))

    def _build_tables(self):
        body = tk.PanedWindow(self, orient="vertical", bg=BG, sashwidth=7, bd=0)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        self._invoice_paned = body
        summary_wrap = tk.Frame(body, bg="#ffffff", highlightbackground=LINE, highlightthickness=1)
        detail_wrap = tk.Frame(body, bg="#ffffff", highlightbackground=LINE, highlightthickness=1)
        # Os mínimos antigos (260 + 180) não cabiam na área útil de 1366×768
        # e o Tk esmagava o painel inferior para cerca de 25 px.
        body.add(summary_wrap, minsize=150, stretch="always")
        body.add(detail_wrap, minsize=135, stretch="always")
        self._invoice_summary_wrap = summary_wrap
        self._invoice_detail_wrap = detail_wrap

        self.invoice_tree = ttk.Treeview(
            summary_wrap,
            columns=self.COLUMNS,
            displaycolumns=("Fatura", "Parceiro", "Qtd.", "OK", "Pendências", "Valor Fatura", "Valor Pendente", "Status"),
            show="headings",
            selectmode="browse",
        )
        summary_widths = {
            "Fatura": 120,
            "Parceiro": 360,
            "Qtd.": 62,
            "OK": 54,
            "Pendências": 82,
            "Valor Fatura": 128,
            "Valor Pendente": 132,
            "Status": 150,
        }
        numeric_columns = {"Qtd.", "OK", "Pendências"}
        money_columns = {"Valor Fatura", "Valor Pendente"}
        for name in self.COLUMNS:
            self.invoice_tree.heading(name, text=name)
            width = summary_widths.get(name, 120)
            anchor = "center" if name in numeric_columns else "e" if name in money_columns else "w"
            self.invoice_tree.column(
                name,
                width=width,
                minwidth=54 if name in numeric_columns else 90,
                anchor=anchor,
                stretch=(name == "Parceiro"),
            )
        ybar = ttk.Scrollbar(summary_wrap, orient="vertical", command=self.invoice_tree.yview)
        xbar = ttk.Scrollbar(summary_wrap, orient="horizontal", command=self.invoice_tree.xview)
        self.invoice_tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.invoice_tree.pack(side="top", fill="both", expand=True)
        xbar.pack(side="bottom", fill="x")
        ybar.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")
        self.invoice_tree.bind("<<TreeviewSelect>>", lambda _e: self.load_details_for_selected())
        summary_wrap.bind("<Configure>", self._resize_invoice_columns, add="+")
        self.invoice_table = TkInvoiceTableAdapter(self.invoice_tree, self.COLUMNS)

        tk.Label(detail_wrap, text="Detalhes da fatura selecionada", bg="#ffffff", fg=BLUE_DARK,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=(7, 3))
        self.detail_tree = ttk.Treeview(detail_wrap, columns=self.DETAIL_COLUMNS, show="headings")
        for index, name in enumerate(self.DETAIL_COLUMNS):
            self.detail_tree.heading(name, text=name)
            self.detail_tree.column(name, width=125 if index != 9 else 360, minwidth=70, anchor="w")
        detail_y = ttk.Scrollbar(detail_wrap, orient="vertical", command=self.detail_tree.yview)
        detail_x = ttk.Scrollbar(detail_wrap, orient="horizontal", command=self.detail_tree.xview)
        self.detail_tree.configure(yscrollcommand=detail_y.set, xscrollcommand=detail_x.set)
        self.detail_tree.pack(side="top", fill="both", expand=True)
        detail_x.pack(side="bottom", fill="x")
        detail_y.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

    def _resize_invoice_columns(self, event=None):
        """Reserva espaço real para o parceiro e separa colunas numéricas."""
        try:
            width = int(getattr(event, "width", 0) or self.invoice_tree.winfo_width() or 0)
            if width <= 200:
                return
            usable = max(width - 34, 760)
            fixed = {
                "Fatura": 120,
                "Qtd.": 62,
                "OK": 54,
                "Pendências": 82,
                "Valor Fatura": 128,
                "Valor Pendente": 132,
                "Status": 150,
            }
            for name, column_width in fixed.items():
                self.invoice_tree.column(name, width=column_width)
            partner_width = max(220, usable - sum(fixed.values()))
            self.invoice_tree.column("Parceiro", width=partner_width, minwidth=220, stretch=True)
        except Exception:
            pass

    def _build_status(self):
        bar = tk.Frame(self, bg="#ffffff", height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=LINE, height=1).pack(fill="x")
        self.status_label = tk.Label(bar, textvariable=self.status_var, bg="#ffffff", fg=MUTED, font=("Segoe UI", 9), anchor="w")
        self.status_label.pack(fill="both", expand=True, padx=12)

    def set_status(self, text):
        self.status_var.set(str(text or ""))
        try:
            self.update_idletasks()
        except Exception:
            pass

    def set_base_ready(self, ready):
        ready = bool(ready)
        self._base_ready = ready
        button = getattr(self, "process_button", None)
        if button is not None and callable(getattr(button, "set_enabled", None)):
            button.set_enabled(ready, "Adicione ao menos um arquivo .sswweb na pasta bases.")
        if not ready:
            self.set_status("Base SSW não localizada. O processamento de faturas está bloqueado.")
        return ready

    def _base_path(self) -> str:
        for obj in (self, getattr(self, "app", None), getattr(getattr(self, "app", None), "cte_page", None)):
            value = getattr(obj, "base_path", "") if obj is not None else ""
            if value:
                return str(value)
        try:
            candidate = find_default_base_file()
            return str(candidate or "")
        except Exception:
            return ""

    def _read_pdf(self, path: Path) -> tuple[str, str]:
        return self.invoice_services.read_pdf(path, fallback=self._pdf_text_fallback())

    def _pdf_text_fallback(self):
        fallback = globals().get("extract_pdf_text")
        return fallback if callable(fallback) else None

    def _choose_invoice_paths(self):
        from tkinter import filedialog
        return filedialog.askopenfilenames(
            parent=self,
            title="Selecionar faturas",
            filetypes=(("Faturas PDF", "*.pdf"), ("Todos os arquivos", "*.*")),
        )

    def _report_dir(self) -> Path:
        try:
            work = ensure_work_folders()
            return Path(
                work.get("reports")
                or work.get("relatorios")
                or app_runtime_dir() / "relatorios"
            )
        except Exception:
            return Path.cwd() / "relatorios"

    def _notify_info(self, text: str) -> None:
        try:
            from tkinter import messagebox
            messagebox.showinfo("Central CT-e / DACTE", text, parent=self)
        except Exception:
            pass

    def _notify_error(self, text: str) -> None:
        try:
            from tkinter import messagebox
            messagebox.showerror("Central CT-e / DACTE", text, parent=self)
        except Exception:
            pass

    def _notify_warning(self, text: str) -> None:
        try:
            from tkinter import messagebox
            messagebox.showwarning("Central CT-e / DACTE", text, parent=self)
        except Exception:
            pass

    @staticmethod
    def _invoice_cell(value: Any = "") -> _InvoiceCell:
        return _InvoiceCell(value)

    def add_invoices(self, paths=None):
        return self.invoice_presenter.add_invoices(paths)

    add_invoice_files = add_invoices
    add_faturas = add_invoices
    add_invoice_docs = add_invoices
    add_files = add_invoices
    load_invoices = add_invoices
    load_invoice_files = add_invoices
    load_faturas = add_invoices

    def parse_invoice_text(self, text, path=""):
        return self.invoice_presenter.parse_invoice_text(text, path)

    def parse_ssw_len_invoice_text(self, text, path=""):
        return self.invoice_presenter.parse_invoice_text(text, path)

    @staticmethod
    def _money(value: Any) -> str:
        return InvoicePagePresenter.money(value)

    def _snapshot_to_cache(self, snapshot):
        return self.invoice_presenter.snapshot_to_cache(snapshot)

    def process_invoices(self):
        return self.invoice_presenter.process_invoices()

    def add_invoice_row(self, row):
        return self.invoice_presenter.add_invoice_row(row)

    def current_invoice_values(self):
        return self.invoice_presenter.current_invoice_values()

    def refresh_table(self):
        return self.invoice_presenter.refresh_table()

    refresh_invoice_list = refresh_table
    refresh_faturas_list = refresh_table
    refresh_docs = refresh_table

    def apply_filters(self):
        return self.invoice_presenter.refresh_table()

    def refresh_partner_filter(self):
        return self.invoice_presenter.refresh_partner_filter()

    update_partner_filter = refresh_partner_filter
    refresh_filters = refresh_partner_filter
    update_filters = refresh_partner_filter

    def _ensure_detail_panel_visible(self):
        pane = getattr(self, "_invoice_paned", None)
        if pane is None:
            return
        try:
            pane.update_idletasks()
            total = max(int(pane.winfo_height() or 0), 1)
            # Reserva no mínimo 38% para os detalhes e evita que o resumo
            # consuma praticamente toda a área em telas de 768 px de altura.
            summary_height = max(145, min(int(total * 0.58), total - 135))
            pane.sash_place(0, 0, summary_height)
        except Exception:
            pass

    def load_details_for_selected(self):
        rows = self.invoice_presenter.load_details_for_selected()
        if rows:
            try:
                self.after_idle(self._ensure_detail_panel_visible)
            except Exception:
                self._ensure_detail_panel_visible()
        return rows

    def update_cards(self):
        return self.invoice_presenter.update_cards()

    def build_invoice_report_sheets(self, only_problem_invoices=False):
        return self.invoice_presenter.build_invoice_report_sheets(only_problem_invoices)

    def export_report(self):
        return self.invoice_presenter.export_report()

    export_invoice_report = export_report
    exportar_relatorio = export_report
    exportar_relatorio_faturas = export_report
    export_faturas_report = export_report

    def clear_invoices(self):
        return self.invoice_presenter.clear_invoices()

    clear_list = clear_invoices
    clear_faturas = clear_invoices
    clear_invoice_list = clear_invoices
    clear_all = clear_invoices
    clear_files = clear_invoices
    clear_docs = clear_invoices
    clear_documents = clear_invoices
    clear_faturas_list = clear_invoices
    clear_invoice_docs = clear_invoices
    reset_invoices = clear_invoices
    limpar_lista = clear_invoices
    limpar_faturas = clear_invoices
    limpar_documentos = clear_invoices
    remove_all_invoices = clear_invoices


__all__ = ["TkInvoiceTableAdapter", "FaturasPage"]
