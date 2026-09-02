# -*- coding: utf-8 -*-
"""Página CT-e modular 2.7.0.

O conteúdo operacional que antes vivia diretamente na janela ``App`` passa a
ser uma vista ``tk.Frame`` independente. A página continua usando os mesmos
serviços e o mesmo contrato de métodos, mas pode ser criada, testada e
substituída sem reconstruir a janela principal.
"""
from pathlib import Path
import math

from central_cte_modular.reports.filtered_package import create_filtered_validation_package
from central_cte_modular.version import APP_VERSION_SHORT

from central_cte_modular.ui.cte import (
    CTePagePresenter,
    CTePageServices,
    CTePresenterAuditWriter,
)
from central_cte_modular.xml import XmlImportService


class CTePage(tk.Frame):
    _cte_presenter_modular_2694 = True
    _hotfix_info_complementar_266516 = True
    _hotfix_filter_266517 = True
    _assinatura_pdf_266518 = True
    _xml_import_modular_2697 = True
    _cte_helpers_modulares_2698 = True

    def __init__(self, master, app=None):
        super().__init__(master, bg=BG)
        self.app = app or master
        self.files = []
        self.selected_paths = set()
        self.printed_count = 0
        self.images = {}
        self.base_data = None
        self.base_path = ""
        self.partner_tables = None
        self.partner_tables_path = ""
        self.work_folders = ensure_work_folders()
        self.filter_status_var = tk.StringVar(value="TODOS")
        self.filter_search_var = tk.StringVar(value="")
        self.filter_nf_var = tk.StringVar(value="")
        self.filter_partner_var = tk.StringVar(value="TODOS")
        self.filter_city_var = tk.StringVar(value="TODOS")
        self.filter_uf_var = tk.StringVar(value="TODOS")
        self.filter_charge_var = tk.StringVar(value="TODOS")
        self.filter_component_var = tk.StringVar(value="")
        self.filter_min_value_var = tk.StringVar(value="")
        self.filter_max_value_var = tk.StringVar(value="")
        self.filter_exact_status_var = tk.StringVar(value="TODOS")
        self.filter_manual_review_var = tk.StringVar(value="TODOS")
        self.filter_observation_var = tk.StringVar(value="TODOS")
        self.filter_ignored_nf_var = tk.StringVar(value="TODOS")
        self._filter_refresh_after = None
        self.last_validation_log_path = ""
        try:
            helper_service = get_modular_service("cte_helper_service")
        except Exception:
            helper_service = None
        self.cte_services = CTePageServices(helper_service)
        self.configure(bg=BG)
        self.setup_styles()
        self.create_widgets()
        audit_dir = Path(self.work_folders.get("relatorios", app_runtime_dir() / "relatorios")) / "presenter_cte_modular"
        try:
            self.xml_import_service = get_modular_service("xml_import")
        except Exception:
            self.xml_import_service = XmlImportService(parse_xml)
        self.cte_presenter = CTePagePresenter(
            self,
            services=self.cte_services,
            audit_writer=CTePresenterAuditWriter(audit_dir),
            render_document=render_document,
            cleaner=_central_cte_clean_complementary_information,
            complementary_applier=apply_complementary_print_information,
            max_complementary_chars=CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS,
            runtime_dir=lambda: Path(app_runtime_dir()),
            engine_dir=lambda: Path(__file__).resolve().parents[3],
            xml_import_service=self.xml_import_service,
            parse_document=parse_xml,
        )
        self.after(160, self.auto_load_default_files)

    # Contratos de compatibilidade. Nenhum monkeypatch é aplicado na 2.7.0.
    def build_actions(self):
        return getattr(self, "toolbar", None)

    def setup_table(self):
        return getattr(self, "tree", None)

    def build_filters(self):
        return getattr(self, "filter_panel", None)

    def apply_filters(self):
        self.refresh_table()
        return self.filtered_files()

    def clear_filters(self):
        return self.clear_filter()

    def clear_status_filter(self):
        try:
            self.filter_status_var.set("TODOS")
        except Exception:
            pass
        return self.clear_filter()

    def generate_htmls(self):
        return self.cte_presenter.generate_htmls()

    def generate_single_html(self):
        return self.cte_presenter.generate_single_html()

    def audit_weight(self):
        return self.audit_weight_action()

    def signature_pdf_action_2694(self):
        # A interface de contingência Tk não deve encerrar a ação com um erro
        # de importação quando o backend PySide6 não estiver disponível.
        try:
            import PySide6  # noqa: F401
        except Exception:
            messagebox.showinfo(
                APP_TITLE,
                "Assinaturas e PDF estão disponíveis no executável oficial para Windows. "
                "Este modo Tk é apenas uma interface de contingência e não possui o editor PySide6.",
                parent=self,
            )
            self.set_status("Assinaturas e PDF indisponíveis apenas no modo Tk de contingência.")
            return False
        return self.cte_presenter.open_signature_pdf()

    # Nome antigo preservado para consumidores históricos.
    signature_pdf_action_266518 = signature_pdf_action_2694

    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Treeview",
            background="#ffffff",
            foreground=TEXT,
            fieldbackground="#ffffff",
            rowheight=36,
            font=("Segoe UI", 9),
            bordercolor=LINE,
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#f5f8fc",
            foreground="#1b2f50",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padding=(4, 8),
        )
        style.map("Treeview", background=[("selected", "#dcecff")], foreground=[("selected", TEXT)])

        style.configure("TEntry", fieldbackground="#ffffff", foreground=TEXT, bordercolor="#cbdcf0", lightcolor="#cbdcf0", darkcolor="#cbdcf0", padding=5)
        style.configure("TCombobox", fieldbackground="#ffffff", background="#ffffff", foreground=TEXT, bordercolor="#cbdcf0", lightcolor="#cbdcf0", darkcolor="#cbdcf0", padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", "#ffffff")], selectbackground=[("readonly", "#ffffff")])


        style.configure("Treeview", background="#ffffff", foreground=TEXT, fieldbackground="#ffffff",
                        rowheight=46, font=("Segoe UI", 10), bordercolor=LINE, borderwidth=1)
        style.configure("Treeview.Heading", background="#f3f7fc", foreground=TEXT,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview", background=[("selected", "#dcecff")], foreground=[("selected", TEXT)])

    def create_widgets(self):
        self.create_header()
        self.create_toolbar()
        self.create_filter_bar()
        self.create_cards()
        self.create_status()
        self.create_table()

    def create_header(self):
        header = tk.Frame(self, bg="#ffffff", height=112)
        header.pack(fill="x")
        header.pack_propagate(False)

        original_logo = photo_asset("logo_rodovitor")
        try:
            scale = max(1, math.ceil(original_logo.width() / 230), math.ceil(original_logo.height() / 65))
            self.images["logo"] = original_logo.subsample(scale, scale)
        except Exception:
            self.images["logo"] = original_logo
        truck_original = photo_asset("truck_route")
        try:
            truck_scale = max(
                1,
                math.ceil(truck_original.width() / 225),
                math.ceil(truck_original.height() / 54),
            )
            self.images["truck"] = truck_original.subsample(truck_scale, truck_scale)
        except Exception:
            self.images["truck"] = truck_original

        logo_wrap = tk.Frame(header, bg="#ffffff", width=250, height=78)
        logo_wrap.place(x=24, y=13)
        logo_wrap.pack_propagate(False)
        tk.Label(logo_wrap, image=self.images["logo"], bg="#ffffff", bd=0).pack(expand=True)

        tk.Frame(header, bg=LINE, width=1, height=68).place(x=292, y=20)
        title_box = tk.Frame(header, bg="#ffffff")
        title_box.place(x=316, y=21, relwidth=0.48, height=70)
        tk.Label(
            title_box, text="Central CT-e / DACTE", bg="#ffffff", fg=BLUE_DARK,
            font=("Segoe UI", 23, "bold"), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_box, text="XML, DACTE, validação comercial e faturas", bg="#ffffff", fg=MUTED,
            font=("Segoe UI", 10), anchor="w",
        ).pack(anchor="w", pady=(3, 0))

        tk.Label(header, image=self.images["truck"], bg="#ffffff", bd=0).place(
            relx=1.0, x=-445, y=26, width=245, height=62
        )
        tk.Label(
            header, text=APP_VERSION_SHORT, bg=BLUE_LIGHT, fg=BLUE_DARK,
            font=("Segoe UI", 9, "bold"), padx=10, pady=4,
        ).place(relx=1.0, x=-182, y=21, width=150, height=34)
        tk.Label(
            header, text="Modo local  •  Operador", bg="#ffffff", fg=MUTED,
            font=("Segoe UI", 8), anchor="e",
        ).place(relx=1.0, x=-260, y=68, width=225)
        tk.Frame(header, bg=LINE, height=1).place(x=0, y=111, relwidth=1)

    def create_toolbar(self):
        panel = tk.Frame(self, bg=BG, height=66)
        panel.pack(fill="x", padx=24, pady=(10, 8))
        panel.pack_propagate(False)
        self.toolbar = panel
        self._base_required_buttons = []

        actions = (
            ("icon_add", "Adicionar arquivos", self.add_files, False, 150, False),
            ("icon_folder", "Adicionar pasta", self.add_folder, False, 142, False),
            ("icon_money", "Validar valores", self.validate_values, False, 162, True),
            ("icon_code", "Gerar HTML único", self.export_single_html, False, 152, False),
            ("icon_print_check", "Imprimir selecionados", self.print_selected, False, 174, False),
            ("icon_doc", "Exportar relatório", self.export_validation_report, False, 154, False),
        )
        for icon, text_, command, danger, width, needs_base in actions:
            button = ImageButton(panel, icon, text_, command, danger=danger, width=width, height=50)
            button.pack(side="left", padx=(0, 8), pady=7)
            if needs_base:
                self._base_required_buttons.append(button)

        more = tk.Menubutton(
            panel, text="Mais ações ▾", bg="#ffffff", fg=BLUE_DARK, activebackground="#eaf4ff",
            relief="flat", bd=0, highlightbackground="#d5e4f5", highlightthickness=1,
            font=("Segoe UI", 9, "bold"), cursor="hand2", padx=15, pady=10,
        )
        menu = tk.Menu(more, tearoff=False)
        secondary = (
            ("Processar pasta", self.process_work_folder, True),
            ("Gerar HTMLs individuais", self.export_htmls, False),
            ("Imprimir tudo", self.print_all, False),
            ("Carregar base SSW", self.load_base_file, False),
            ("Carregar tabelas", self.load_partner_tables_file, False),
            ("Cadastrar tabela", self.open_table_registration_dialog, False),
            ("Cálculo manual %", self.apply_manual_percentage, True),
            ("Ver detalhes da validação", self.show_validation_details, False),
            ("Informação complementar", self.audit_weight_action, False),
            ("Assinaturas e PDF", self.signature_pdf_action_2694, False),
            ("Auditar base", self.audit_base_action, True),
            ("Auditar tabelas", self.audit_partner_tables_action, False),
            ("Salvar sessão", self.save_session_file, False),
            ("Abrir sessão", self.load_session_file, False),
            ("Abrir pastas", self.open_work_folder, False),
            ("Resumo da validação", self.show_validation_summary, False),
            ("Exportar filtro", self.export_filtered_validation_report, False),
            ("Exportar seleção", self.export_selected_validation_report, False),
            ("Criar pacote do filtro", self.create_filtered_package, False),
        )
        for label, command, needs_base in secondary:
            menu.add_command(label=label, command=command)
            if needs_base:
                # índice do item para habilitar/desabilitar com a base
                self._base_required_menu_indexes = getattr(self, "_base_required_menu_indexes", [])
                self._base_required_menu_indexes.append(menu.index("end"))
        more.configure(menu=menu)
        more.pack(side="right", padx=(8, 0), pady=7)
        self._more_actions_menu = menu
        self._set_base_ready(bool(self.base_data), announce=False)

    def create_validation_bar(self):
        # Mantido apenas por compatibilidade com versões anteriores.
        return

    def _set_base_ready(self, ready, announce=False):
        ready = bool(ready)
        self._base_ready = ready
        for button in list(getattr(self, "_base_required_buttons", []) or []):
            try:
                button.set_enabled(ready, "Carregue ao menos um arquivo .sswweb na pasta bases.")
            except Exception:
                pass
        menu = getattr(self, "_more_actions_menu", None)
        state = "normal" if ready else "disabled"
        if menu is not None:
            for index in list(getattr(self, "_base_required_menu_indexes", []) or []):
                try:
                    menu.entryconfigure(index, state=state)
                except Exception:
                    pass
        try:
            faturas = getattr(self.app, "faturas_page", None)
            if faturas is not None and callable(getattr(faturas, "set_base_ready", None)):
                faturas.set_base_ready(ready)
        except Exception:
            pass
        if announce and not ready:
            messagebox.showwarning(
                APP_TITLE,
                "Base SSW não localizada. Adicione ao menos um arquivo .sswweb na pasta bases antes de validar ou processar.",
                parent=self,
            )
        return ready

    def _base_display_name(self, value=None):
        raw = str(value if value is not None else self.base_path or "")
        if not raw:
            return "não carregada"
        path = Path(raw)
        if path.is_dir():
            count = len(list(path.glob("*.sswweb")))
            return f"{path.name} ({count} arquivo(s) SSW)"
        return path.name

    def update_validation_status(self):
        base = self._base_display_name()
        tab = Path(self.partner_tables_path).name if self.partner_tables_path else "não carregadas"
        text = f"Base: {base}   •   Tabelas: {tab}"
        if hasattr(self, "validation_status"):
            self.validation_status.config(text=text)
        if hasattr(self, "status_hint"):
            self.status_hint.config(text=text)

    def open_work_folder(self):
        safe_open_folder(self.work_folders.get("raiz", app_runtime_dir()))

    def open_reports_folder(self):
        safe_open_folder(self.work_folders.get("relatorios", app_runtime_dir()))

    def find_default_base_file(self):
        base_dir = self.work_folders.get("bases", app_runtime_dir() / "bases")
        ssw_files = sorted(base_dir.glob("*.sswweb"), key=lambda item: item.name.lower())
        return base_dir if ssw_files else None

    def find_default_partner_tables_file(self):
        tab_dir = self.work_folders.get("tabelas", app_runtime_dir() / "tabelas")
        preferidos = ["cadastro_tabelas_parceiros.xlsx", "cadastro_tabelas_parceiros_v1.xlsx"]
        for name in preferidos:
            p = tab_dir / name
            if p.exists():
                return p
        candidates = sorted([p for p in tab_dir.glob("*.xlsx") if not p.name.startswith("~$")])
        return candidates[0] if candidates else None

    def auto_load_default_files(self):
        mensagens = []
        base_path = self.find_default_base_file()
        if base_path and not self.base_data:
            try:
                self._load_base_from_path(base_path, silent=True)
                mensagens.append(f"base: {self._base_display_name(base_path)}")
            except Exception as e:
                write_app_log("auto_carregamento.log", f"Erro ao carregar base padrão {base_path}: {e}")
                mensagens.append("base padrão com erro")

        tables_path = self.find_default_partner_tables_file()
        if tables_path and not self.partner_tables:
            try:
                self._load_partner_tables_from_path(tables_path, silent=True)
                mensagens.append(f"tabelas: {tables_path.name}")
            except Exception as e:
                write_app_log("auto_carregamento.log", f"Erro ao carregar tabela padrão {tables_path}: {e}")
                mensagens.append("tabelas padrão com erro")

        self._set_base_ready(bool(self.base_data), announce=False)
        self.update_validation_status()
        if not self.base_data:
            self.set_status("Base SSW não localizada. Copie ao menos um arquivo .sswweb para /bases antes de validar ou processar.")
            try:
                self.after(250, lambda: self._set_base_ready(False, announce=True))
            except Exception:
                pass
            return
        if mensagens:
            self.set_status("Carregamento automático concluído: " + " • ".join(mensagens))
        else:
            self.set_status("Pastas de trabalho prontas. Coloque XMLs em /xmls, base em /bases e tabelas em /tabelas.")

    def mini_button(self, parent, text, command, fg=BLUE_DARK, strong=False):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg="#ffffff",
            fg=fg,
            activebackground="#eaf4ff",
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightbackground="#d5e4f5",
            highlightthickness=1,
            font=("Segoe UI", 9, "bold" if strong else "normal"),
            cursor="hand2",
            padx=12,
            pady=5,
        )
        return btn


    def labeled_entry(self, parent, label, textvariable, width=18, placeholder=""):
        bgc = getattr(self, "_filter_card_bg", "#ffffff")
        wrap = tk.Frame(parent, bg=bgc)
        tk.Label(wrap, text=label, bg=bgc, fg="#1b2f50", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        ent = ttk.Entry(wrap, textvariable=textvariable, width=width)
        ent.pack(fill="x", ipady=4)
        ent.bind("<KeyRelease>", self.schedule_filter_refresh)
        ent.bind("<Return>", lambda _e: self.refresh_table())
        return wrap, ent


    def labeled_combo(self, parent, label, textvariable, width=18, values=None):
        bgc = getattr(self, "_filter_card_bg", "#ffffff")
        wrap = tk.Frame(parent, bg=bgc)
        tk.Label(wrap, text=label, bg=bgc, fg="#1b2f50", font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        cmb = ttk.Combobox(wrap, textvariable=textvariable, width=width, values=values or ["TODOS"])
        cmb.pack(fill="x", ipady=4)
        cmb.bind("<<ComboboxSelected>>", lambda _e: self.refresh_table())
        cmb.bind("<KeyRelease>", self.schedule_filter_refresh)
        cmb.bind("<Return>", lambda _e: self.refresh_table())
        return wrap, cmb


    def create_filter_bar(self):
        self._filter_card_bg = "#ffffff"
        panel = tk.Frame(self, bg="#ffffff", height=184, highlightbackground="#d8e5f4", highlightthickness=1)
        panel.pack(fill="x", padx=24, pady=(0, 10))
        panel.pack_propagate(False)
        self.filter_panel = panel

        form1 = tk.Frame(panel, bg="#ffffff", height=58)
        form1.pack(fill="x", padx=16, pady=(12, 4))
        form1.pack_propagate(False)
        w, self.search_entry = self.labeled_entry(form1, "Busca rápida", self.filter_search_var, width=34)
        w.pack(side="left", padx=(0, 12), fill="x")
        w, self.filter_combo = self.labeled_combo(form1, "Status", self.filter_status_var, width=20, values=self.filter_values())
        w.pack(side="left", padx=(0, 12))
        w, self.filter_nf_entry = self.labeled_entry(form1, "NF", self.filter_nf_var, width=15)
        w.pack(side="left", padx=(0, 12))
        w, self.filter_partner_combo = self.labeled_combo(form1, "Parceiro", self.filter_partner_var, width=27)
        w.pack(side="left", padx=(0, 12))
        w, self.filter_city_combo = self.labeled_combo(form1, "Cidade", self.filter_city_var, width=22)
        w.pack(side="left", padx=(0, 12))
        w, self.filter_uf_combo = self.labeled_combo(form1, "UF", self.filter_uf_var, width=7)
        w.pack(side="left")

        form2 = tk.Frame(panel, bg="#ffffff", height=58)
        form2.pack(fill="x", padx=16, pady=(0, 2))
        form2.pack_propagate(False)
        w, self.filter_charge_combo = self.labeled_combo(form2, "Tipo cobrança", self.filter_charge_var, width=19)
        w.pack(side="left", padx=(0, 12))
        w, self.filter_component_entry = self.labeled_entry(form2, "Componente XML", self.filter_component_var, width=25)
        w.pack(side="left", padx=(0, 12))
        w, self.filter_min_entry = self.labeled_entry(form2, "Valor mínimo", self.filter_min_value_var, width=14)
        w.pack(side="left", padx=(0, 12))
        w, self.filter_max_entry = self.labeled_entry(form2, "Valor máximo", self.filter_max_value_var, width=14)
        w.pack(side="left", padx=(0, 12))

        actions = tk.Frame(form2, bg="#ffffff")
        actions.pack(side="right", pady=(16, 0))
        self.mini_button(actions, "Mais filtros", self.open_advanced_filters_dialog, fg=BLUE_DARK).pack(side="left", padx=(0, 8), ipady=3)
        self.mini_button(actions, "Limpar", self.clear_filter, fg=RED).pack(side="left", padx=(0, 8), ipady=3)
        tk.Button(
            actions, text="Filtrar", command=self.refresh_table, bg=BLUE_DARK, fg="#ffffff",
            activebackground=BLUE, activeforeground="#ffffff", relief="flat", bd=0,
            font=("Segoe UI", 9, "bold"), cursor="hand2", padx=22, pady=7,
        ).pack(side="left")

        chip_row = tk.Frame(panel, bg="#ffffff", height=36)
        chip_row.pack(fill="x", padx=16, pady=(3, 0))
        chip_row.pack_propagate(False)
        self.filter_info_label = tk.Label(
            chip_row, text="Mostrando todos os arquivos.", bg="#ffffff", fg=MUTED,
            font=("Segoe UI", 8), anchor="w",
        )
        self.filter_info_label.pack(side="right", padx=(10, 0))
        tk.Label(chip_row, text="Filtros ativos:", bg="#ffffff", fg="#1b2f50", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        self.filter_chip_frame = tk.Frame(chip_row, bg="#ffffff")
        self.filter_chip_frame.pack(side="left", fill="x", expand=True)
        self.refresh_filter_chips()
        self._filter_card_bg = BG

    def open_advanced_filters_dialog(self):
        dialog = tk.Toplevel(self)
        dialog.title("Filtros avançados de CT-e")
        dialog.geometry("560x360")
        dialog.minsize(520, 330)
        try:
            dialog.transient(self.winfo_toplevel())
            dialog.grab_set()
        except Exception:
            pass

        body = tk.Frame(dialog, bg="#ffffff", padx=20, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text="Refine a lista sem alterar a validação",
            bg="#ffffff",
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text="Os filtros abaixo são combinados com busca, parceiro, cidade e faixa de valor.",
            bg="#ffffff",
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(4, 14))

        form = tk.Frame(body, bg="#ffffff")
        form.pack(fill="both", expand=True)
        exact_values = self.cte_presenter.exact_status_values()
        fields = (
            ("Status exato", self.filter_exact_status_var, exact_values),
            ("Revisão manual", self.filter_manual_review_var, ("TODOS", "REVISADO", "NÃO REVISADO")),
            ("Observação", self.filter_observation_var, ("TODOS", "COM OBSERVAÇÃO", "SEM OBSERVAÇÃO")),
            ("NFs adicionais", self.filter_ignored_nf_var, ("TODOS", "COM NFs IGNORADAS", "SEM NFs IGNORADAS")),
        )
        for row, (label, variable, values) in enumerate(fields):
            tk.Label(
                form, text=label, bg="#ffffff", fg=TEXT,
                font=("Segoe UI", 9, "bold"), anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=8)
            combo = ttk.Combobox(
                form, textvariable=variable, values=values, state="readonly", width=42
            )
            combo.grid(row=row, column=1, sticky="ew", pady=8)
        form.columnconfigure(1, weight=1)

        buttons = tk.Frame(body, bg="#ffffff")
        buttons.pack(fill="x", pady=(14, 0))

        def reset_filters():
            self.filter_exact_status_var.set("TODOS")
            self.filter_manual_review_var.set("TODOS")
            self.filter_observation_var.set("TODOS")
            self.filter_ignored_nf_var.set("TODOS")

        def apply_filters():
            self.refresh_table()
            dialog.destroy()

        tk.Button(
            buttons, text="Limpar avançados", command=reset_filters, width=18
        ).pack(side="left")
        tk.Button(
            buttons, text="Cancelar", command=dialog.destroy, width=14
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            buttons, text="Aplicar filtros", command=apply_filters, width=18,
            bg=BLUE, fg="#ffffff",
        ).pack(side="right")

    def schedule_filter_refresh(self, _event=None):
        try:
            if self._filter_refresh_after:
                self.after_cancel(self._filter_refresh_after)
        except Exception:
            pass
        self._filter_refresh_after = self.after(220, self.refresh_table)

    def clear_filter(self):
        self.filter_status_var.set("TODOS")
        self.filter_search_var.set("")
        self.filter_nf_var.set("")
        self.filter_partner_var.set("TODOS")
        self.filter_city_var.set("TODOS")
        self.filter_uf_var.set("TODOS")
        self.filter_charge_var.set("TODOS")
        self.filter_component_var.set("")
        self.filter_min_value_var.set("")
        self.filter_max_value_var.set("")
        self.filter_exact_status_var.set("TODOS")
        self.filter_manual_review_var.set("TODOS")
        self.filter_observation_var.set("TODOS")
        self.filter_ignored_nf_var.set("TODOS")
        self.refresh_table()

    def filter_token(self, value):
        return norm_text(str(value or "").strip())

    def filter_value_is_empty(self, value):
        return self.filter_token(value) in ("", "TODOS", "TODAS")

    def info_filter_text(self, info):
        result = info.get("validacao") or {}
        dest = info.get("dest", {}) or {}
        emit = info.get("emit", {}) or {}
        comps = []
        for comp in info.get("componentes", []) or []:
            comps.append(str(comp.get("nome", "")))
            comps.append(str(comp.get("valor", "")))
        docs = []
        for doc in info.get("docs", []) or []:
            docs.append(str(doc.get("n_doc", "")))
            docs.append(str(doc.get("serie_numero", "")))
            docs.append(str(doc.get("chave", "")))
        parts = [
            info.get("numero", ""), info.get("serie", ""), info.get("arquivo", ""), info.get("path", ""),
            info.get("emitente", ""), info.get("destinatario", ""), dest.get("mun", ""), emit.get("cnpjcpf", ""),
            result.get("status", ""), result.get("nf", ""), result.get("partner_id", ""), result.get("tipo_cobranca", ""),
            result.get("componente_comparado", ""), info.get("observacao_manual", ""), info.get("revisao_manual", ""),
        ] + comps + docs
        return norm_text(" ".join(str(p or "") for p in parts))

    def get_filter_nf_text(self, info):
        result = info.get("validacao") or {}
        nfs = [result.get("nf", "") or get_nf_from_info(info)]
        for doc in info.get("docs", []) or []:
            nfs.append(doc.get("n_doc", ""))
            nfs.append(doc.get("serie_numero", ""))
        return norm_text(" ".join(str(n or "") for n in nfs))

    def get_filter_partner_text(self, info):
        result = info.get("validacao") or {}
        emit = info.get("emit", {}) or {}
        return norm_text(" ".join(str(x or "") for x in [info.get("emitente", ""), emit.get("cnpjcpf", ""), result.get("partner_id", "")]))

    def get_filter_city_text(self, info):
        dest = info.get("dest", {}) or {}
        return norm_text(" ".join(str(x or "") for x in [dest.get("mun", ""), info.get("destino", "")]))

    def get_filter_component_text(self, info):
        result = info.get("validacao") or {}
        names = [result.get("componente_comparado", "")]
        for comp in info.get("componentes", []) or []:
            names.append(comp.get("nome", ""))
        return norm_text(" ".join(str(n or "") for n in names))

    def current_filter_summary(self):
        chips = []
        if self.filter_status_var.get() and self.filter_status_var.get() != "TODOS": chips.append(f"Status: {self.filter_status_var.get()}")
        if self.filter_search_var.get().strip(): chips.append(f"Busca: {self.filter_search_var.get().strip()}")
        if self.filter_nf_var.get().strip(): chips.append(f"NF: {self.filter_nf_var.get().strip()}")
        if not self.filter_value_is_empty(self.filter_partner_var.get()): chips.append(f"Parceiro: {self.filter_partner_var.get()}")
        if not self.filter_value_is_empty(self.filter_city_var.get()): chips.append(f"Cidade: {self.filter_city_var.get()}")
        if not self.filter_value_is_empty(self.filter_uf_var.get()): chips.append(f"UF: {self.filter_uf_var.get()}")
        if not self.filter_value_is_empty(self.filter_charge_var.get()): chips.append(f"Tipo: {self.filter_charge_var.get()}")
        if self.filter_component_var.get().strip(): chips.append(f"Comp.: {self.filter_component_var.get().strip()}")
        if self.filter_min_value_var.get().strip(): chips.append(f"Mín.: {self.filter_min_value_var.get().strip()}")
        if self.filter_max_value_var.get().strip(): chips.append(f"Máx.: {self.filter_max_value_var.get().strip()}")
        if not self.filter_value_is_empty(self.filter_exact_status_var.get()): chips.append(f"Status exato: {self.filter_exact_status_var.get()}")
        if not self.filter_value_is_empty(self.filter_manual_review_var.get()): chips.append(f"Revisão: {self.filter_manual_review_var.get()}")
        if not self.filter_value_is_empty(self.filter_observation_var.get()): chips.append(f"Observação: {self.filter_observation_var.get()}")
        if not self.filter_value_is_empty(self.filter_ignored_nf_var.get()): chips.append(f"NFs: {self.filter_ignored_nf_var.get()}")
        return chips


    def update_filter_info_label(self, shown):
        if hasattr(self, "filter_info_label"):
            self.filter_info_label.config(text=f"Mostrando {shown} de {len(self.files)} arquivo(s).")
        self.refresh_filter_chips()

    def refresh_filter_chips(self):
        if not hasattr(self, "filter_chip_frame"):
            return
        for child in self.filter_chip_frame.winfo_children():
            child.destroy()
        chips = self.current_filter_summary()
        if not chips:
            tk.Label(self.filter_chip_frame, text="Nenhum filtro ativo", bg="#ffffff", fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
            return
        for chip in chips[:6]:
            tk.Label(
                self.filter_chip_frame,
                text=f" {chip}  × ",
                bg="#eaf4ff",
                fg=BLUE_DARK,
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=4,
            ).pack(side="left", padx=(0, 8))
        if len(chips) > 6:
            tk.Label(self.filter_chip_frame, text=f"+{len(chips)-6}", bg="#f3f7fc", fg=MUTED, font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(side="left")


    def validation_status_of(self, info):
        result = info.get("validacao") or {}
        status = str(result.get("status") or "").strip()
        return status or "NÃO VALIDADO"

    def filter_values(self):
        fixed = ["TODOS", "NÃO VALIDADO", "OK", "DIVERGENTES", "REVISÃO", "SEM BASE", "SEM PARCEIRO/REGRA", "ERROS", "REVISADO", "COM OBSERVAÇÃO"]
        extras = []
        seen = set(fixed)
        for info in self.files:
            status = self.validation_status_of(info)
            entry = f"STATUS: {status}"
            if status and entry not in seen:
                seen.add(entry)
                extras.append(entry)
        return fixed + sorted(extras)

    def distinct_filter_values(self, kind):
        values = []
        seen = set()
        for info in self.files:
            result = info.get("validacao") or {}
            dest = info.get("dest", {}) or {}
            if kind == "partner":
                candidates = [info.get("emitente", ""), result.get("partner_id", "")]
            elif kind == "city":
                mun = str(dest.get("mun", "") or "")
                candidates = [mun.split("-")[0].strip() if mun else ""]
            elif kind == "uf":
                mun = str(dest.get("mun", "") or "")
                uf = ""
                if "-" in mun:
                    uf = mun.rsplit("-", 1)[-1].strip()
                candidates = [uf]
            elif kind == "charge":
                candidates = [result.get("tipo_cobranca", "")]
            else:
                candidates = []
            for raw in candidates:
                val = str(raw or "").strip()
                key = norm_text(val)
                if val and key not in seen:
                    seen.add(key)
                    values.append(val)
        return ["TODOS"] + sorted(values, key=lambda x: norm_text(x))

    def update_filter_options(self):
        if hasattr(self, "filter_combo"):
            values = self.filter_values()
            current = self.filter_status_var.get() or "TODOS"
            if current not in values:
                self.filter_status_var.set("TODOS")
            self.filter_combo.configure(values=values)
        if hasattr(self, "filter_partner_combo"):
            self.filter_partner_combo.configure(values=self.distinct_filter_values("partner"))
        if hasattr(self, "filter_city_combo"):
            self.filter_city_combo.configure(values=self.distinct_filter_values("city"))
        if hasattr(self, "filter_uf_combo"):
            self.filter_uf_combo.configure(values=self.distinct_filter_values("uf"))
        if hasattr(self, "filter_charge_combo"):
            self.filter_charge_combo.configure(values=self.distinct_filter_values("charge"))

    def status_matches_current_filter(self, status):
        current = self.filter_status_var.get() if hasattr(self, "filter_status_var") else "TODOS"
        return self.cte_services.matches_page_status_filter(status, current)

    def passes_current_filter(self, info):
        status = self.validation_status_of(info)
        if not self.status_matches_current_filter(status):
            return False

        if self.filter_status_var.get() == "REVISADO" and norm_text(info.get("revisao_manual", "")) != "REVISADO":
            return False
        if self.filter_status_var.get() == "COM OBSERVAÇÃO" and not str(info.get("observacao_manual", "")).strip():
            return False
        if hasattr(self, "cte_presenter") and not self.cte_presenter.matches_advanced_filters(info):
            return False

        full_text = self.info_filter_text(info)
        q = self.filter_token(self.filter_search_var.get())
        if q and q not in full_text:
            return False

        nf_q = self.filter_token(self.filter_nf_var.get())
        if nf_q and nf_q not in self.get_filter_nf_text(info):
            return False

        partner_q = self.filter_token(self.filter_partner_var.get())
        if not self.filter_value_is_empty(self.filter_partner_var.get()) and partner_q not in self.get_filter_partner_text(info):
            return False

        city_q = self.filter_token(self.filter_city_var.get())
        if not self.filter_value_is_empty(self.filter_city_var.get()) and city_q not in self.get_filter_city_text(info):
            return False

        uf_q = self.filter_token(self.filter_uf_var.get())
        if not self.filter_value_is_empty(self.filter_uf_var.get()):
            city_text = self.get_filter_city_text(info)
            if uf_q not in city_text.split() and uf_q not in city_text:
                return False

        charge_q = self.filter_token(self.filter_charge_var.get())
        if not self.filter_value_is_empty(self.filter_charge_var.get()):
            charge = self.filter_token((info.get("validacao") or {}).get("tipo_cobranca", ""))
            if charge_q not in charge:
                return False

        comp_q = self.filter_token(self.filter_component_var.get())
        if comp_q and comp_q not in self.get_filter_component_text(info):
            return False

        value_for_range = (info.get("validacao") or {}).get("valor_comparado")
        if value_for_range in (None, ""):
            value_for_range = info.get("valor", "")
        value_for_range = parse_number_br(value_for_range)
        min_q = parse_number_br(self.filter_min_value_var.get()) if self.filter_min_value_var.get().strip() else None
        max_q = parse_number_br(self.filter_max_value_var.get()) if self.filter_max_value_var.get().strip() else None
        if min_q is not None and value_for_range < min_q:
            return False
        if max_q is not None and value_for_range > max_q:
            return False
        return True

    def filtered_files(self):
        return [f for f in self.files if self.passes_current_filter(f)]

    def create_table(self):
        outer = tk.Frame(self, bg="#ffffff", highlightbackground="#d8e5f4", highlightthickness=1)
        outer.pack(fill="both", expand=True, padx=24, pady=(0, 0))
        self.table_container = outer

        columns = ("sel", "tipo", "numero", "serie", "emitente", "destinatario", "nf", "cidade", "tipo_cobranca", "comp_xml", "valor", "valor_comp", "base_frete", "percentual", "esperado", "diferenca", "status_val", "revisao", "arquivo", "path")
        self.tree = ttk.Treeview(outer, columns=columns, show="headings", selectmode="extended", height=9)
        labels = {
            "sel": "☐", "tipo": "Tipo", "numero": "Número", "serie": "Série",
            "emitente": "Emitente", "destinatario": "Destinatário", "nf": "NF",
            "cidade": "Cidade/UF", "tipo_cobranca": "Tipo cobrança", "comp_xml": "Componente XML",
            "valor": "Valor total", "valor_comp": "Valor calc.", "base_frete": "Frete base", "percentual": "%",
            "esperado": "Esperado", "diferenca": "Dif.", "status_val": "Status",
            "revisao": "Rev.", "arquivo": "Arquivo", "path": "Caminho",
        }
        widths = {
            "sel": 42, "tipo": 70, "numero": 92, "serie": 58, "emitente": 220,
            "destinatario": 240, "nf": 90, "cidade": 135, "tipo_cobranca": 115, "comp_xml": 135,
            "valor": 100, "valor_comp": 100, "base_frete": 100, "percentual": 62,
            "esperado": 100, "diferenca": 90, "status_val": 180, "revisao": 78,
            "arquivo": 220, "path": 300,
        }
        fixed = {"sel", "tipo", "numero", "serie", "nf", "cidade", "tipo_cobranca", "comp_xml", "valor", "valor_comp", "base_frete", "percentual", "esperado", "diferenca", "status_val", "revisao"}
        for col in columns:
            self.tree.heading(col, text=labels[col])
            self.tree.column(col, width=widths[col], minwidth=40, anchor="w", stretch=col not in fixed)
        self.tree.column("sel", anchor="center")
        for col in ("valor", "valor_comp", "base_frete", "esperado", "diferenca"):
            self.tree.column(col, anchor="e")

        yscroll = ttk.Scrollbar(outer, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(outer, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.tree.bind("<Double-1>", lambda _e: self.preview_selected())
        self.tree.tag_configure("ok", foreground=GREEN)
        self.tree.tag_configure("bad", foreground=RED)
        self.tree.tag_configure("warn", foreground="#9a6700")
        self.tree.tag_configure("info", foreground="#1769aa")

    def create_cards(self):
        cards = tk.Frame(self, bg=BG, height=108)
        cards.pack(fill="x", padx=24, pady=(10, 8))
        cards.pack_propagate(False)
        for index in range(5):
            cards.columnconfigure(index, weight=1, uniform="card")

        self.card_loaded = StatCard(cards, "icon_doc", "0", "Arquivos carregados", "0 CT-e(s)", BLUE)
        self.card_selected = StatCard(cards, "icon_select", "0", "Selecionados", "0 CT-e(s)", BLUE_DARK)
        self.card_value = StatCard(cards, "icon_money", "R$ 0,00", "Valor total", "CT-es carregados", GREEN)
        self.card_print = StatCard(cards, "icon_print", "0 / 0", "Impressão", "0 impressos • 0 pendentes", "#5b35bd")
        self.card_diff = StatCard(cards, "icon_broom", "0", "Divergências", "R$ 0,00", RED)
        for index, card in enumerate((self.card_loaded, self.card_selected, self.card_value, self.card_print, self.card_diff)):
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0 if index == 4 else 5))

    def create_status(self):
        status = tk.Frame(self, bg=BLUE, height=36)
        status.pack(fill="x", side="bottom")
        status.pack_propagate(False)

        self.status_label = tk.Label(
            status,
            text="ⓘ Pronto para carregar XMLs de CT-e.",
            bg=BLUE,
            fg="#ffffff",
            font=("Segoe UI", 9),
            anchor="w"
        )
        self.status_label.pack(side="left", padx=14)

        self.status_hint = tk.Label(
            status,
            text="Base: não carregada   •   Tabelas: não carregadas",
            bg=BLUE,
            fg="#ffffff",
            font=("Segoe UI", 9)
        )
        self.status_hint.pack(side="left", expand=True)

        self.version_label = tk.Label(
            status,
            text=APP_VERSION,
            bg=BLUE,
            fg="#ffffff",
            font=("Segoe UI", 9)
        )
        self.version_label.pack(side="right", padx=14)

    def set_status(self, text):
        if hasattr(self, "status_label"):
            self.status_label.config(text=f"ⓘ {text}")

    def _notify_info(self, text):
        return messagebox.showinfo(APP_TITLE, str(text), parent=self.winfo_toplevel())

    def _notify_error(self, text):
        return messagebox.showerror(APP_TITLE, str(text), parent=self.winfo_toplevel())

    def _notify_warning(self, text):
        return messagebox.showwarning(APP_TITLE, str(text), parent=self.winfo_toplevel())

    def _choose_html_output_dir(self):
        selected = filedialog.askdirectory(
            title="Escolha onde salvar os HTMLs",
            initialdir=str(self.work_folders.get("saida_html", app_runtime_dir())),
            parent=self.winfo_toplevel(),
        )
        return Path(selected) if selected else None

    def _choose_batch_html_path(self, document_count=0):
        default_name = f"Lote CT-e {datetime.now().strftime('%Y-%m-%d %H%M')} {int(document_count or 0)} documentos.html"
        selected = filedialog.asksaveasfilename(
            title="Salvar HTML único dos XMLs marcados",
            defaultextension=".html",
            initialdir=str(self.work_folders.get("saida_html", app_runtime_dir())),
            initialfile=default_name,
            filetypes=[("HTML", "*.html")],
            parent=self.winfo_toplevel(),
        )
        return Path(selected) if selected else None

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        col = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)

        if region == "heading" and col == "#1":
            self.toggle_all()
            return

        if not row_id:
            return

        if col == "#1":
            values = list(self.tree.item(row_id, "values"))
            path = values[-1]
            if path in self.selected_paths:
                self.selected_paths.remove(path)
                values[0] = "☐"
            else:
                self.selected_paths.add(path)
                values[0] = "☑"
            self.tree.item(row_id, values=values)
            self.update_stats()

    def toggle_all(self):
        visible_files = self.filtered_files() if hasattr(self, "filter_status_var") else self.files
        visible_paths = {f.get("path", "") for f in visible_files if f.get("path")}
        if visible_paths and visible_paths.issubset(self.selected_paths):
            self.selected_paths.difference_update(visible_paths)
        else:
            self.selected_paths.update(visible_paths)

        for item in self.tree.get_children():
            values = list(self.tree.item(item, "values"))
            values[0] = "☑" if values[-1] in self.selected_paths else "☐"
            self.tree.item(item, values=values)

        self.update_stats()

    def _load_base_from_path(self, path, silent=False):
        try:
            started = time.perf_counter()
            data = load_rodovitor_base_cached(path)
            elapsed = time.perf_counter() - started
            self.base_data = data
            self.base_path = str(path)
            self.update_validation_status()
            cache_info = data.get("_cache", {}) or {}
            source_format = str(cache_info.get("source_format") or data.get("source_format") or "sswweb")
            file_count = int(cache_info.get("file_count") or len(data.get("source_files") or []) or 1)
            if cache_info.get("status") == "HIT":
                origem = "cache validado"
            elif source_format == "sswweb":
                origem = f"{file_count} arquivo(s) SSW"
            else:
                origem = "arquivos SSW Web"
            display_name = self._base_display_name(path)
            self._set_base_ready(True, announce=False)
            self.set_status(f"Base carregada ({origem}): {display_name} ({len(data['rows'])} linha(s), {elapsed:.1f}s)")
            if not silent:
                messagebox.showinfo(
                    APP_TITLE,
                    f"Base carregada com sucesso.\n\nFonte: {display_name}\n"
                    f"Arquivos: {file_count}\nLinhas: {len(data['rows'])}\n"
                    f"Origem: {origem}\nTempo: {elapsed:.1f}s",
                )
            return data
        except Exception:
            self.base_data = None
            self.base_path = ""
            self._set_base_ready(False, announce=False)
            self.update_validation_status()
            raise

    def _load_partner_tables_from_path(self, path, silent=False):
        try:
            tables = load_partner_tables(path)
            self.partner_tables = tables
            self.partner_tables_path = str(path)
            self.update_validation_status()
            q_parceiros = len(tables.get("partners", {}))
            q_regras = len(tables.get("rules", []))
            q_regioes = len(tables.get("regions", []))
            q_extras = len(tables.get("extras", []))
            self.set_status(f"Tabelas carregadas: {q_parceiros} parceiro(s), {q_regras} regra(s), {q_regioes} região(ões), {q_extras} extra(s)")
            if not silent:
                messagebox.showinfo(APP_TITLE, f"Tabelas carregadas com sucesso.\n\nParceiros: {q_parceiros}\nRegras: {q_regras}\nRegiões: {q_regioes}\nExtras: {q_extras}")
            return tables
        except Exception:
            self.partner_tables = None
            self.partner_tables_path = ""
            self.update_validation_status()
            raise

    def audit_weight_action(self):
        infos, source = self.cte_presenter.selected_or_visible_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Adicione ao menos um XML de CT-e antes de inserir a informação complementar.")
            return

        dialog = tk.Toplevel(self)
        dialog.title("Adicionar informação complementar")
        dialog.geometry("650x400")
        dialog.minsize(560, 340)
        try:
            dialog.transient(self.winfo_toplevel())
            dialog.grab_set()
        except Exception:
            pass

        body = tk.Frame(dialog, bg="#ffffff", padx=18, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=f"A informação será aplicada aos {len(infos)} CT-e(s) {source}.",
            bg="#ffffff",
            fg=TEXT,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            body,
            text="Ela será impressa abaixo do cálculo compacto. Quando o cálculo não existir, ficará na posição reservada a ele. O XML fiscal original não será alterado.",
            bg="#ffffff",
            fg=MUTED,
            font=("Segoe UI", 9),
            justify="left",
            wraplength=600,
            anchor="w",
        ).pack(fill="x", pady=(5, 12))

        text_box = tk.Text(body, height=10, wrap="word", font=("Segoe UI", 10), relief="solid", borderwidth=1)
        text_box.pack(fill="both", expand=True)
        existing = {get_complementary_print_information(info) for info in infos}
        existing.discard("")
        if len(existing) == 1:
            text_box.insert("1.0", next(iter(existing)))

        counter_var = tk.StringVar(value=f"0/{CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS} caracteres")
        counter = tk.Label(body, textvariable=counter_var, bg="#ffffff", fg=MUTED, font=("Segoe UI", 8), anchor="e")
        counter.pack(fill="x", pady=(5, 10))

        def update_counter(_event=None):
            raw = text_box.get("1.0", "end-1c")
            counter_var.set(f"{len(raw)}/{CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS} caracteres")
            counter.configure(fg=RED if len(raw) > CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS else MUTED)

        def apply_text():
            raw = _central_cte_clean_complementary_information(text_box.get("1.0", "end-1c"), limit=False)
            if not raw:
                messagebox.showwarning(APP_TITLE, "Digite a informação complementar.", parent=dialog)
                return
            if len(raw) > CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS:
                messagebox.showwarning(
                    APP_TITLE,
                    f"O texto ultrapassa o limite de {CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS} caracteres.",
                    parent=dialog,
                )
                return
            if not messagebox.askyesno(
                APP_TITLE,
                f"Aplicar esta informação aos {len(infos)} CT-e(s) {source}?\n\nO XML fiscal original permanecerá intacto.",
                parent=dialog,
            ):
                return
            try:
                count = self.cte_presenter.apply_complementary_information(raw, infos=infos, source=source)
                self.set_status(f"Informação complementar aplicada a {count} CT-e(s).")
                dialog.destroy()
                messagebox.showinfo(APP_TITLE, f"Informação complementar aplicada a {count} CT-e(s).")
            except Exception as exc:
                messagebox.showerror(APP_TITLE, f"Erro ao aplicar a informação complementar:\n\n{exc}", parent=dialog)

        buttons = tk.Frame(body, bg="#ffffff")
        buttons.pack(fill="x")
        tk.Button(buttons, text="Cancelar", command=dialog.destroy, width=14).pack(side="right", padx=(8, 0))
        tk.Button(buttons, text="Aplicar aos selecionados" if source == "marcados" else "Aplicar aos filtrados", command=apply_text, width=22, bg=BLUE, fg="#ffffff").pack(side="right")
        text_box.bind("<KeyRelease>", update_counter)
        update_counter()
        text_box.focus_set()
        try:
            dialog.wait_window()
        except Exception:
            pass

    def audit_base_action(self):
        if not self.base_data:
            messagebox.showinfo(APP_TITLE, "Carregue a base Rodovitor antes de auditar.")
            return
        default_name = f"auditoria_base_rodovitor_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path = filedialog.asksaveasfilename(
            title="Salvar auditoria da base Rodovitor",
            defaultextension=".xlsx",
            initialdir=str(self.work_folders.get("relatorios", app_runtime_dir())),
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")]
        )
        if not path:
            return
        try:
            write_base_audit_xlsx(path, self.base_data)
            text = base_audit_text(self.base_data)
            self.set_status(f"Auditoria da base gerada: {path}")
            self.open_validation_detail_window(text)
            if messagebox.askyesno(APP_TITLE, f"Auditoria da base gerada com sucesso.\n\nArquivo:\n{path}\n\nDeseja abrir o arquivo agora?"):
                safe_open_file(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao auditar base:\n\n{e}")


    def audit_partner_tables_action(self):
        if not self.partner_tables:
            messagebox.showinfo(APP_TITLE, "Carregue as tabelas dos parceiros antes de auditar.")
            return
        default_name = f"auditoria_tabelas_parceiros_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        path = filedialog.asksaveasfilename(
            title="Salvar auditoria das tabelas",
            defaultextension=".xlsx",
            initialdir=str(self.work_folders.get("relatorios", app_runtime_dir())),
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")]
        )
        if not path:
            return
        try:
            write_partner_audit_xlsx(path, self.partner_tables)
            text = partner_audit_text(self.partner_tables)
            self.set_status(f"Auditoria das tabelas gerada: {path}")
            self.open_validation_detail_window(text)
            if messagebox.askyesno(APP_TITLE, f"Auditoria gerada com sucesso.\n\nArquivo:\n{path}\n\nDeseja abrir o arquivo agora?"):
                safe_open_file(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao auditar tabelas:\n\n{e}")


    def session_default_name(self):
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        return f"sessao_cte_{stamp}.json"

    def build_session_payload(self):
        return {
            "app": APP_TITLE,
            "version": APP_VERSION,
            "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "base_path": self.base_path,
            "partner_tables_path": self.partner_tables_path,
            "selected_paths": list(self.selected_paths),
            "printed_count": self.printed_count,
            "files": self.files,
        }

    def save_session_file(self):
        if not self.files and not self.base_path and not self.partner_tables_path:
            messagebox.showinfo(APP_TITLE, "Nada para salvar ainda. Carregue XMLs, base ou tabelas primeiro.")
            return
        initialdir = str(self.work_folders.get("sessoes", app_runtime_dir()))
        path = filedialog.asksaveasfilename(
            title="Salvar sessão de trabalho",
            defaultextension=".json",
            initialdir=initialdir,
            initialfile=self.session_default_name(),
            filetypes=[("Sessão Central CT-e", "*.json"), ("Todos", "*.*")]
        )
        if not path:
            return
        try:
            payload = self.build_session_payload()
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.set_status(f"Sessão salva: {path}")
            if messagebox.askyesno(APP_TITLE, f"Sessão salva com sucesso.\n\nArquivo:\n{path}\n\nDeseja abrir a pasta de sessões?"):
                safe_open_folder(Path(path).parent)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao salvar sessão:\n\n{e}")

    def load_session_file(self):
        initialdir = str(self.work_folders.get("sessoes", app_runtime_dir()))
        path = filedialog.askopenfilename(
            title="Abrir sessão de trabalho",
            initialdir=initialdir,
            filetypes=[("Sessão Central CT-e", "*.json"), ("Todos", "*.*")]
        )
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            files = data.get("files") or []
            if not isinstance(files, list):
                raise ValueError("Arquivo de sessão inválido: campo 'files' não é uma lista.")

            self.files = files
            valid_paths = {f.get("path", "") for f in self.files if f.get("path")}
            self.selected_paths = set(p for p in (data.get("selected_paths") or []) if p in valid_paths)
            self.printed_count = int(data.get("printed_count") or 0)

            self.base_data = None
            self.partner_tables = None
            self.base_path = ""
            self.partner_tables_path = ""
            warnings = []

            saved_base = data.get("base_path") or ""
            if saved_base and Path(saved_base).exists():
                try:
                    self._load_base_from_path(saved_base, silent=True)
                except Exception as e:
                    warnings.append(f"Base não carregada: {e}")
            elif saved_base:
                warnings.append(f"Base não encontrada no caminho salvo: {saved_base}")

            saved_tables = data.get("partner_tables_path") or ""
            if saved_tables and Path(saved_tables).exists():
                try:
                    self._load_partner_tables_from_path(saved_tables, silent=True)
                except Exception as e:
                    warnings.append(f"Tabelas não carregadas: {e}")
            elif saved_tables:
                warnings.append(f"Tabelas não encontradas no caminho salvo: {saved_tables}")

            missing_files = [f.get("path", "") for f in self.files if f.get("path") and not Path(f.get("path")).exists()]
            if missing_files:
                warnings.append(f"{len(missing_files)} arquivo(s) XML/documento não existem mais no caminho salvo. A validação salva continua visível, mas prévia/impressão podem falhar.")

            self.update_validation_status()
            self.refresh_table()
            self.update_stats()
            self.set_status(f"Sessão carregada: {Path(path).name} ({len(self.files)} arquivo(s))")

            if warnings:
                messagebox.showwarning(APP_TITLE, "Sessão carregada com avisos:\n\n" + "\n".join(warnings[:8]))
            else:
                messagebox.showinfo(APP_TITLE, f"Sessão carregada com sucesso.\n\nArquivos: {len(self.files)}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao abrir sessão:\n\n{e}")


    def run_validation_silent(self):
        counts = {}
        for info in self.files:
            try:
                result = validate_cte_value(info, self.base_data, self.partner_tables)
            except Exception as e:
                result = {
                    "nf": get_nf_from_info(info),
                    "base_frete": None,
                    "percentual": None,
                    "frete_minimo": None,
                    "esperado": None,
                    "diferenca": None,
                    "tolerancia": None,
                    "status": "ERRO VALIDAÇÃO",
                    "detalhe": str(e),
                    "partner_id": "",
                    "tipo_cobranca": "",
                    "regra_extra": "",
                    "trace": ["Erro inesperado durante a validação deste item.", str(e)],
                    "base_candidates_summary": [],
                }
            info["validacao"] = result
            counts[result.get("status", "")] = counts.get(result.get("status", ""), 0) + 1
        self.refresh_table()
        self.update_stats()
        log_path = ""
        try:
            log_path = str(self.write_validation_log(counts))
        except Exception as e:
            write_app_log("validacao_automatica_erro.log", f"Erro ao salvar log automático: {e}")
        return counts, log_path

    def process_work_folder(self):
        xml_dir = self.work_folders.get("xmls", app_runtime_dir() / "xmls")
        rel_dir = self.work_folders.get("relatorios", app_runtime_dir() / "relatorios")
        sess_dir = self.work_folders.get("sessoes", app_runtime_dir() / "sessoes")
        rel_dir.mkdir(parents=True, exist_ok=True)
        sess_dir.mkdir(parents=True, exist_ok=True)

        paths = sorted([p for p in xml_dir.rglob("*.xml") if p.is_file()])
        if not paths:
            messagebox.showinfo(APP_TITLE, f"Nenhum XML encontrado na pasta:\n\n{xml_dir}\n\nColoque os XMLs na pasta xmls/ e tente novamente.")
            return

        before = len(self.files)
        self.add_paths(paths)
        added = len(self.files) - before

        carregamentos = []
        avisos = []
        if not self.base_data:
            base_path = self.find_default_base_file()
            if base_path:
                try:
                    self._load_base_from_path(base_path, silent=True)
                    carregamentos.append(f"base: {base_path.name}")
                except Exception as e:
                    avisos.append(f"Erro ao carregar base padrão: {e}")
            else:
                avisos.append("Base Rodovitor não encontrada em /bases.")

        if not self.partner_tables:
            tables_path = self.find_default_partner_tables_file()
            if tables_path:
                try:
                    self._load_partner_tables_from_path(tables_path, silent=True)
                    carregamentos.append(f"tabelas: {tables_path.name}")
                except Exception as e:
                    avisos.append(f"Erro ao carregar tabelas padrão: {e}")
            else:
                avisos.append("Tabela de parceiros não encontrada em /tabelas.")

        if avisos:
            self.set_status("Processamento automático interrompido: " + " • ".join(avisos[:2]))
            messagebox.showwarning(APP_TITLE, "Não foi possível concluir o processamento automático:\n\n" + "\n".join(avisos))
            return

        if not self.files:
            messagebox.showinfo(APP_TITLE, "Nenhum arquivo válido ficou carregado para processar.")
            return

        counts, log_path = self.run_validation_silent()

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = rel_dir / f"relatorio_validacao_auto_{stamp}.xlsx"
        session_path = sess_dir / f"sessao_auto_{stamp}.json"

        try:
            write_validation_report_xlsx(report_path, self.files)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Validação concluída, mas o relatório automático não foi gerado:\n\n{e}")
            return

        try:
            session_path.write_text(json.dumps(self.build_session_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            write_app_log("sessao_automatica_erro.log", f"Erro ao salvar sessão automática: {e}")
            session_path = None

        resumo = "\n".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        msg = (
            "Processamento automático concluído.\n\n"
            f"XMLs encontrados na pasta: {len(paths)}\n"
            f"Novos adicionados: {added}\n"
            f"Total na lista: {len(self.files)}\n\n"
            f"{resumo}\n\n"
            f"Relatório:\n{report_path}"
        )
        if log_path:
            msg += f"\n\nLog:\n{log_path}"
        if session_path:
            msg += f"\n\nSessão:\n{session_path}"
        if carregamentos:
            msg += "\n\nCarregado automaticamente:\n" + "\n".join(carregamentos)

        self.set_status(f"Processamento automático concluído • Relatório: {report_path.name}")
        if messagebox.askyesno(APP_TITLE, msg + "\n\nDeseja abrir o relatório agora?"):
            safe_open_file(report_path)


    def open_table_registration_dialog(self):
        path = self.partner_tables_path or str(self.find_default_partner_tables_file() or "")
        if not path:
            messagebox.showinfo(APP_TITLE, "Nenhuma planilha de tabelas encontrada. Carregue ou coloque cadastro_tabelas_parceiros.xlsx na pasta /tabelas.")
            return

        win = tk.Toplevel(self)
        win.title("Cadastrar tabela / parceiro")
        win.geometry("760x650")
        win.minsize(720, 620)
        win.configure(bg="#ffffff")
        win.transient(self)
        win.grab_set()

        tk.Label(win, text="Cadastrar tabela na planilha", bg="#ffffff", fg=BLUE_DARK, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=22, pady=(18, 4))
        tk.Label(win, text="O programa só altera o arquivo cadastro_tabelas_parceiros.xlsx. Ele cria backup automático antes de salvar.", bg="#ffffff", fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", padx=22, pady=(0, 12))

        body = tk.Frame(win, bg="#ffffff")
        body.pack(fill="both", expand=True, padx=22, pady=6)
        for c in range(4):
            body.columnconfigure(c, weight=1)

        fields = {}
        def add_field(row, col, label, key, width=24, default="", combo=None, colspan=1):
            tk.Label(body, text=label, bg="#ffffff", fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=row*2, column=col, columnspan=colspan, sticky="w", padx=(0, 14), pady=(4, 1))
            var = tk.StringVar(value=default)
            if combo:
                widget = ttk.Combobox(body, textvariable=var, values=combo, state="readonly" if combo else "normal", width=width)
            else:
                widget = ttk.Entry(body, textvariable=var, width=width)
            widget.grid(row=row*2+1, column=col, columnspan=colspan, sticky="ew", padx=(0, 14), pady=(0, 8))
            fields[key] = var
            return widget

        add_field(0, 0, "Parceiro ID", "partner_id", default="")
        add_field(0, 1, "Nome do parceiro", "partner_name", colspan=2)
        add_field(0, 3, "CNPJ", "cnpj")

        add_field(1, 0, "Alias no XML", "alias", colspan=2)
        add_field(1, 2, "Origem base", "origem_cidade", default="Belém")
        add_field(1, 3, "UF origem", "origem_uf", default="PA", combo=["PA", "SP", "AC", "AP", "AM", "RO", "MT", "MA", "GO", "TO"])

        add_field(2, 0, "Cidade destino", "cidade", colspan=2)
        add_field(2, 2, "UF destino", "uf", combo=["PA", "SP", "AC", "AP", "AM", "RO", "MT", "MA", "GO", "TO", "MG", "RJ", "PR", "SC", "RS", "BA", "CE", "PE"])
        add_field(2, 3, "Região/Base", "regiao")

        add_field(3, 0, "Percentual", "percentual", default="")
        add_field(3, 1, "Frete mínimo", "frete_minimo", default="")
        add_field(3, 2, "R$/Ton", "tonelagem", default="")
        add_field(3, 3, "Base cálculo", "base_calculo", combo=["ORIGINAL", "SEM_ICMS", "ORIGEM"])

        add_field(4, 0, "Modal", "modal", default="")
        add_field(4, 1, "Prazo", "prazo", default="")
        add_field(4, 2, "Status revisão", "status_revisao", default="REVISAR_OK", combo=["REVISAR_OK", "PENDENTE", "CONFERIR", "ATIVO"])
        add_field(4, 3, "Data proposta", "data_proposta", default=datetime.now().strftime("%d/%m/%Y"))

        add_field(5, 0, "Fonte", "fonte", default="Cadastro manual", colspan=2)
        add_field(5, 2, "Tipo tabela", "tipo_tabela", default="Cadastro manual pelo programa", colspan=2)

        tk.Label(body, text="Observação", bg="#ffffff", fg=TEXT, font=("Segoe UI", 9, "bold")).grid(row=12, column=0, columnspan=4, sticky="w", pady=(4, 1))
        obs = tk.Text(body, height=4, wrap="word", bg="#ffffff", fg=TEXT, relief="solid", bd=1)
        obs.insert("1.0", "Cadastro feito pelo programa")
        obs.grid(row=13, column=0, columnspan=4, sticky="nsew", padx=(0, 14), pady=(0, 8))
        body.rowconfigure(13, weight=1)

        info = tk.Label(win, text=f"Planilha alvo: {path}", bg="#ffffff", fg=MUTED, font=("Segoe UI", 9), anchor="w", wraplength=690, justify="left")
        info.pack(fill="x", padx=22, pady=(2, 8))

        footer = tk.Frame(win, bg="#ffffff")
        footer.pack(fill="x", padx=22, pady=(0, 18))

        def salvar():
            data = {k: v.get().strip() for k, v in fields.items()}
            data["observacao"] = obs.get("1.0", "end").strip()
            if not (data.get("partner_name") or data.get("partner_id") or data.get("cnpj")):
                messagebox.showwarning(APP_TITLE, "Informe pelo menos parceiro, Parceiro ID ou CNPJ.")
                return
            if not data.get("cidade") or not data.get("uf"):
                messagebox.showwarning(APP_TITLE, "Informe cidade e UF de destino para cadastrar a regra/região.")
                return
            if not (data.get("percentual") or data.get("frete_minimo") or data.get("tonelagem")):
                messagebox.showwarning(APP_TITLE, "Informe percentual, frete mínimo ou R$/Ton.")
                return
            try:
                result = cadastro_tabela_salvar_xlsx(path, data)
                self._load_partner_tables_from_path(path, silent=True)
                self.set_status(f"Tabela cadastrada na planilha: {result['partner_id']} / {result['region_id']}")
                msg = (
                    "Cadastro salvo na planilha.\n\n"
                    f"Parceiro ID: {result['partner_id']}\n"
                    f"Região ID: {result['region_id']}\n"
                    f"Parceiro novo: {'sim' if result['partner_inserted'] else 'não, já existia'}\n\n"
                    f"Backup criado em:\n{result['backup_path']}"
                )
                messagebox.showinfo(APP_TITLE, msg)
                win.destroy()
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Erro ao salvar cadastro na planilha:\n\n{e}")

        tk.Button(footer, text="Salvar na planilha", command=salvar, bg=BLUE, fg="#ffffff", activebackground=BLUE_DARK, activeforeground="#ffffff", relief="flat", font=("Segoe UI", 10, "bold"), padx=18, pady=8, cursor="hand2").pack(side="right")
        tk.Button(footer, text="Cancelar", command=win.destroy, bg="#ffffff", fg=TEXT, relief="solid", bd=1, font=("Segoe UI", 10), padx=18, pady=8, cursor="hand2").pack(side="right", padx=(0, 10))

    def load_base_file(self):
        initialdir = str(self.work_folders.get("bases", app_runtime_dir()))
        path = filedialog.askopenfilename(
            title="Selecione um arquivo SSW da base",
            initialdir=initialdir,
            filetypes=[
                ("Base SSW Web", "*.sswweb"),
                ("Todos", "*.*"),
            ],
        )
        if not path:
            return
        selected = Path(path)
        source = selected.parent
        try:
            self._load_base_from_path(source)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao carregar base:\n\n{e}")

    def load_partner_tables_file(self):
        initialdir = str(self.work_folders.get("tabelas", app_runtime_dir()))
        path = filedialog.askopenfilename(
            title="Selecione cadastro/tabelas de parceiros",
            initialdir=initialdir,
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")]
        )
        if not path:
            return
        try:
            self._load_partner_tables_from_path(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao carregar tabelas:\n\n{e}")

    def validate_values(self):
        if not self.files:
            messagebox.showinfo(APP_TITLE, "Adicione XMLs antes de validar.")
            return
        if not self.base_data:
            messagebox.showinfo(APP_TITLE, "Carregue a base Rodovitor antes de validar.")
            return
        if not self.partner_tables:
            messagebox.showinfo(APP_TITLE, "Carregue as tabelas dos parceiros antes de validar.")
            return
        counts = {}
        for info in self.files:
            try:
                result = validate_cte_value(info, self.base_data, self.partner_tables)
            except Exception as e:
                result = {
                    "nf": get_nf_from_info(info),
                    "base_frete": None,
                    "percentual": None,
                    "frete_minimo": None,
                    "esperado": None,
                    "diferenca": None,
                    "tolerancia": None,
                    "status": "ERRO VALIDAÇÃO",
                    "detalhe": str(e),
                    "partner_id": "",
                    "tipo_cobranca": "",
                    "regra_extra": "",
                    "trace": ["Erro inesperado durante a validação deste item.", str(e)],
                    "base_candidates_summary": [],
                }
            info["validacao"] = result
            counts[result.get("status", "")] = counts.get(result.get("status", ""), 0) + 1
        self.refresh_table()
        self.update_stats()
        resumo = " | ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        log_path = ""
        try:
            log_path = str(self.write_validation_log(counts))
        except Exception as e:
            log_path = ""
            self.set_status(f"Validação concluída, mas o log não foi salvo: {e}")
        ok_count = sum(value for key, value in counts.items() if norm_text(key).startswith("OK"))
        review_count = max(0, len(self.files) - ok_count)
        concise = f"Validação concluída: {len(self.files)} CT-es • {ok_count} OK • {review_count} com atenção"
        if log_path:
            self.set_status(f"{concise} • Log: {Path(log_path).name}")
        else:
            self.set_status(concise)
        msg = "Validação concluída.\n\n" + "\n".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        if log_path:
            msg += f"\n\nLog salvo em:\n{log_path}"
        messagebox.showinfo(APP_TITLE, msg)

    def validation_summary_text(self, counts=None):
        counts = counts or {}
        if not counts:
            for info in self.files:
                status = self.validation_status_of(info)
                counts[status] = counts.get(status, 0) + 1
        total_xml = sum(1 for f in self.files if f.get("tipo") == "CT-e")
        total_valor_xml = sum(money_float(f.get("valor")) for f in self.files if f.get("tipo") == "CT-e")
        total_esperado = sum(money_float((f.get("validacao") or {}).get("esperado")) for f in self.files)
        total_diferenca = sum(money_float((f.get("validacao") or {}).get("diferenca")) for f in self.files)
        divergentes = sum(v for k, v in counts.items() if "DIVERGENTE" in norm_text(k))
        revisao = sum(v for k, v in counts.items() if any(x in norm_text(k) for x in ["REVISAR", "AMBIG", "MULTIPLAS", "REGRA SEM VALOR", "ERRO", "SEM", "NAO"]))
        revisados_manualmente = sum(1 for f in self.files if f.get("revisao_manual"))
        com_observacao_manual = sum(1 for f in self.files if f.get("observacao_manual"))

        lines = []
        lines.append(f"{APP_TITLE} - {APP_VERSION}")
        lines.append("RESUMO DA VALIDAÇÃO")
        lines.append("=" * 72)
        lines.append(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        lines.append(f"Arquivos na lista: {len(self.files)}")
        lines.append(f"CT-e(s): {total_xml}")
        lines.append(f"Valor XML total: R$ {money(total_valor_xml)}")
        lines.append(f"Valor esperado total: R$ {money(total_esperado)}")
        lines.append(f"Diferença total: R$ {money(total_diferenca)}")
        lines.append(f"Divergentes: {divergentes}")
        lines.append(f"Para revisão/erro/sem cadastro: {revisao}")
        lines.append(f"Revisados manualmente: {revisados_manualmente}")
        lines.append(f"Com observação manual: {com_observacao_manual}")
        lines.append("")
        lines.append("STATUS")
        lines.append("-" * 72)
        for status, qty in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
            lines.append(f"{status or 'NÃO VALIDADO'}: {qty}")
        lines.append("")
        lines.append("BASES CARREGADAS")
        lines.append("-" * 72)
        lines.append(f"Base Rodovitor: {self.base_path or 'não carregada'}")
        lines.append(f"Tabelas parceiros: {self.partner_tables_path or 'não carregadas'}")
        if self.last_validation_log_path:
            lines.append(f"Último log: {self.last_validation_log_path}")
        return "\n".join(lines)

    def manual_review_label(self, info):
        status = str(info.get("revisao_manual", "") or "").strip()
        obs = str(info.get("observacao_manual", "") or "").strip()
        if status and obs:
            return f"{status} + OBS"
        if status:
            return status
        if obs:
            return "OBS"
        return ""

    def ensure_base_frete_for_info(self, info):
        result = info.get("validacao") or {}
        base_frete = result.get("base_frete")
        if base_frete not in (None, ""):
            return report_float(base_frete), result.get("nf", "") or get_nf_from_info(info), result.get("base_candidates_summary", [])

        if not self.base_data:
            return None, get_nf_from_info(info), []

        nfs = get_nfs_from_info(info)
        if not nfs:
            return None, "", []

        base_rows = []
        all_candidates = []
        statuses = []
        for nf in nfs:
            base_row, base_status, candidates = find_base_by_nf(self.base_data, nf, info)
            statuses.append(base_status)
            all_candidates.extend(candidates)
            if base_row:
                base_rows.append(base_row)

        if not base_rows or len(base_rows) != len(nfs):
            return None, ", ".join(nfs), [candidate_summary(c) for c in all_candidates[:30]]

        if not base_rows_have_same_route(base_rows):
            return None, ", ".join(nfs), [candidate_summary(c) for c in all_candidates[:30]]

        total = sum(r.get("valor_frete", 0.0) for r in base_rows)
        return total, ", ".join(nfs), [candidate_summary(c) for c in all_candidates[:30]]

    def apply_manual_percentage(self):
        infos = self.manual_target_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Selecione uma ou mais linhas pela caixinha, ou clique em uma linha, para aplicar percentual manual.")
            return

        raw_percent = simpledialog.askstring(
            "Cálculo manual por percentual",
            "Informe o percentual do parceiro.\n\nExemplos: 25, 25% ou 0,25",
            parent=self
        )
        if raw_percent is None:
            return
        percent = parse_percent(raw_percent)
        if percent <= 0:
            messagebox.showerror(APP_TITLE, "Percentual inválido. Use algo como 25, 25% ou 0,25.")
            return

        raw_min = simpledialog.askstring(
            "Frete mínimo",
            "Informe o frete mínimo, se houver.\n\nPode deixar vazio ou 0.",
            initialvalue="0",
            parent=self
        )
        if raw_min is None:
            return
        minimum = parse_number_br(raw_min)
        if minimum < 0:
            messagebox.showerror(APP_TITLE, "Frete mínimo inválido.")
            return

        tolerance = 1.0
        if self.partner_tables:
            tolerance = self.partner_tables.get("tolerance", 1.0) or 1.0

        changed = 0
        skipped = []
        for info in infos:
            base_frete, nf_text, candidates_summary = self.ensure_base_frete_for_info(info)
            if base_frete is None:
                skipped.append(info.get("arquivo", "sem nome"))
                continue

            valor_xml = money_float(info.get("valor"))
            esperado = max(base_frete * percent, minimum)
            diferenca = valor_xml - esperado
            status = "OK MANUAL" if abs(diferenca) <= tolerance else "DIVERGENTE MANUAL"
            old_result = info.get("validacao") or {}
            trace = list(old_result.get("trace") or [])
            trace.append(
                f"Cálculo manual aplicado: base R$ {money(base_frete)}, percentual {fmt_percent(percent)}, "
                f"mínimo R$ {money(minimum)}, esperado R$ {money(esperado)}, diferença R$ {money(diferenca)}."
            )
            if old_result.get("status") == "PARCEIRO SEM CADASTRO":
                trace.append("O cálculo manual foi usado porque o parceiro emitente ainda não está cadastrado na tabela de parceiros.")

            info["validacao"] = {
                "nf": nf_text or old_result.get("nf", "") or get_nf_from_info(info),
                "base_frete": base_frete,
                "percentual": percent,
                "frete_minimo": minimum,
                "esperado": esperado,
                "diferenca": diferenca,
                "tolerancia": tolerance,
                "status": status,
                "detalhe": f"Cálculo manual aplicado; percentual {fmt_percent(percent)}; mínimo R$ {money(minimum)}",
                "partner_id": old_result.get("partner_id", "") or "MANUAL",
                "tipo_cobranca": old_result.get("tipo_cobranca", "") or detect_partner_charge_type(info),
                "regra_extra": old_result.get("regra_extra", ""),
                "trace": trace,
                "base_candidates_summary": old_result.get("base_candidates_summary") or candidates_summary,
            }
            info["observacao_manual"] = (info.get("observacao_manual", "") + " | " if info.get("observacao_manual") else "") + f"Cálculo manual: {fmt_percent(percent)}"
            info["revisao_data"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            changed += 1

        self.refresh_table()
        self.update_stats()

        if changed:
            self.set_status(f"Cálculo manual aplicado em {changed} item(ns).")
        if skipped:
            messagebox.showwarning(
                APP_TITLE,
                f"Cálculo manual aplicado em {changed} item(ns).\n\n"
                f"{len(skipped)} item(ns) ficaram sem cálculo porque não foi possível localizar o frete base.\n\n"
                + "\n".join(skipped[:10])
            )
        else:
            messagebox.showinfo(APP_TITLE, f"Cálculo manual aplicado em {changed} item(ns).")


    def manual_target_infos(self):
        infos = self.selected_infos()
        if infos:
            return infos
        focus = self.tree.focus()
        if focus:
            path = self.tree.item(focus, "values")[-1]
            return [f for f in self.files if f.get("path") == path]
        return []

    def mark_selected_reviewed(self):
        infos = self.manual_target_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Selecione uma ou mais linhas pela caixinha, ou clique em uma linha, para marcar como revisado.")
            return
        stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
        for info in infos:
            info["revisao_manual"] = "REVISADO"
            info["revisao_data"] = stamp
        self.refresh_table()
        self.update_stats()
        self.set_status(f"{len(infos)} item(ns) marcado(s) como revisado(s).")

    def clear_manual_review(self):
        infos = self.manual_target_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Selecione uma ou mais linhas pela caixinha, ou clique em uma linha, para limpar a revisão.")
            return
        if not messagebox.askyesno(APP_TITLE, f"Limpar revisão/observação manual de {len(infos)} item(ns)?"):
            return
        for info in infos:
            info.pop("revisao_manual", None)
            info.pop("observacao_manual", None)
            info.pop("revisao_data", None)
        self.refresh_table()
        self.update_stats()
        self.set_status(f"Revisão manual limpa em {len(infos)} item(ns).")

    def set_manual_observation(self):
        infos = self.manual_target_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Selecione uma ou mais linhas pela caixinha, ou clique em uma linha, para adicionar observação.")
            return
        initial = infos[0].get("observacao_manual", "") if len(infos) == 1 else ""
        prompt = "Digite a observação manual para o item selecionado:" if len(infos) == 1 else f"Digite a observação manual para {len(infos)} itens selecionados:"
        obs = simpledialog.askstring("Observação manual", prompt, initialvalue=initial, parent=self)
        if obs is None:
            return
        obs = obs.strip()
        stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
        for info in infos:
            if obs:
                info["observacao_manual"] = obs
                info["revisao_data"] = stamp
            else:
                info.pop("observacao_manual", None)
        self.refresh_table()
        self.update_stats()
        self.set_status(f"Observação manual atualizada em {len(infos)} item(ns).")


    def show_validation_summary(self):
        if not self.files:
            messagebox.showinfo(APP_TITLE, "Nenhum arquivo carregado para resumir.")
            return
        self.open_validation_detail_window(self.validation_summary_text())

    def write_validation_log(self, counts=None):
        log_dir = self.work_folders.get("logs", app_runtime_dir() / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = log_dir / f"validacao_{stamp}.txt"
        parts = [self.validation_summary_text(counts), "", "", "DETALHES POR ARQUIVO", "=" * 72]
        for info in self.files:
            parts.append(validation_report_text(info))
            parts.append("\n" + "-" * 72 + "\n")
        path.write_text("\n".join(parts), encoding="utf-8")
        self.last_validation_log_path = str(path)
        return path

    def show_validation_details(self):
        infos = self.selected_infos()
        if not infos:
            focus = self.tree.focus()
            if focus:
                path = self.tree.item(focus, "values")[-1]
                infos = [f for f in self.files if f.get("path") == path]
        if not infos:
            messagebox.showinfo(APP_TITLE, "Selecione um CT-e ou clique em uma linha para ver os detalhes da validação.")
            return
        text = "\n\n".join(validation_report_text(info) for info in infos)
        self.open_validation_detail_window(text)

    def _sanitize_report_label(self, text):
        label = norm_text(text or "RELATORIO")
        label = re.sub(r"[^A-Z0-9]+", "_", label).strip("_").lower()
        return label or "relatorio"

    def _active_filter_label(self):
        chips = self.current_filter_summary()
        if not chips:
            return "todos"
        if len(chips) == 1:
            return self._sanitize_report_label(chips[0])[:64]
        compact = "_".join(self._sanitize_report_label(chip) for chip in chips[:4])
        return (compact[:72].strip("_") or "filtro_personalizado")

    def export_validation_report_subset(self, infos, default_name, title, empty_message):
        if not infos:
            messagebox.showinfo(APP_TITLE, empty_message)
            return
        validated = sum(1 for info in infos if info.get("validacao"))
        if validated == 0:
            if not messagebox.askyesno(APP_TITLE, "Nenhum XML deste conjunto foi validado ainda. Deseja exportar mesmo assim como 'NÃO VALIDADO'?"):
                return
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".xlsx",
            initialdir=str(self.work_folders.get("relatorios", app_runtime_dir())),
            initialfile=default_name,
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")]
        )
        if not path:
            return
        try:
            target = Path(path)
            if target.exists() or target.with_name("~$" + target.name).exists():
                target = self.unique_destination_path(target.parent, target.name)
            write_validation_report_xlsx(target, infos)
            path = str(target)
            self.set_status(f"Relatório exportado: {path}")
            if messagebox.askyesno(APP_TITLE, f"Relatório exportado com sucesso.\n\nArquivo:\n{path}\n\nDeseja abrir o arquivo agora?"):
                safe_open_file(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Erro ao exportar relatório:\n\n{e}")

    def export_filtered_validation_report(self):
        if not self.files:
            messagebox.showinfo(APP_TITLE, "Adicione XMLs antes de exportar relatório.")
            return
        infos = self.filtered_files() if hasattr(self, "filter_status_var") else self.files
        label = self._active_filter_label()
        self.export_validation_report_subset(
            infos,
            f"relatorio_validacao_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "Salvar relatório do filtro atual",
            "O filtro atual não possui nenhum arquivo para exportar."
        )

    def export_selected_validation_report(self):
        infos = self.selected_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Selecione ao menos um arquivo na caixinha para exportar a seleção.")
            return
        self.export_validation_report_subset(
            infos,
            f"relatorio_validacao_selecionados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            "Salvar relatório dos selecionados",
            "Nenhum arquivo selecionado para exportar."
        )

    def open_last_validation_log(self):
        path = getattr(self, "last_validation_log_path", "")
        if path and Path(path).exists():
            safe_open_file(path)
            self.set_status(f"Abrindo último log: {Path(path).name}")
            return
        log_dir = self.work_folders.get("logs", app_runtime_dir() / "logs")
        logs = sorted(log_dir.glob("validacao_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True) if log_dir.exists() else []
        if not logs:
            messagebox.showinfo(APP_TITLE, "Nenhum log de validação encontrado ainda.")
            return
        safe_open_file(logs[0])
        self.last_validation_log_path = str(logs[0])
        self.set_status(f"Abrindo último log: {logs[0].name}")


    def unique_destination_path(self, dest_dir, file_name):
        dest = Path(dest_dir) / file_name
        if not dest.exists():
            return dest
        stem = dest.stem
        suffix = dest.suffix
        for i in range(2, 10000):
            candidate = Path(dest_dir) / f"{stem}_{i}{suffix}"
            if not candidate.exists():
                return candidate
        return Path(dest_dir) / f"{stem}_{datetime.now().strftime('%H%M%S')}{suffix}"

    def create_filtered_package(self):
        if not self.files:
            messagebox.showinfo(APP_TITLE, "Adicione XMLs antes de gerar pacote.")
            return

        infos = self.filtered_files() if hasattr(self, "filter_status_var") else self.files
        if not infos:
            messagebox.showinfo(APP_TITLE, "O filtro atual não possui nenhum arquivo para empacotar.")
            return

        label = self._active_filter_label()
        parent = self.work_folders.get("relatorios", app_runtime_dir() / "relatorios")
        try:
            package = create_filtered_validation_package(
                infos,
                parent_dir=parent,
                label=label,
                app_title=APP_TITLE,
                app_version=APP_VERSION,
                status_of=self.validation_status_of,
                bucket_of=self.cte_services.report_bucket,
                sanitize_label=self._sanitize_report_label,
                report_writer=write_validation_report_xlsx,
                render_document=render_document,
            )
        except Exception as exc:
            write_app_log("pacote_filtrado_erro.log", f"Erro ao gerar pacote {label}: {exc}")
            messagebox.showerror(
                APP_TITLE,
                "O pacote não foi gerado. Nenhuma pasta parcial foi mantida.\n\n" + str(exc),
            )
            return

        self.set_status(f"Pacote gerado: {package.root}")
        msg = (
            "Pacote de conferência gerado com sucesso.\n\n"
            f"Pasta:\n{package.root}\n\n"
            f"Arquivos no filtro: {len(infos)}\n"
            f"Arquivos copiados: {package.copied}\n"
            f"Relatório: {package.report_path.name if package.report_path else '-'}"
        )
        if package.missing:
            msg += f"\n\nAtenção: {len(package.missing)} arquivo(s) não foram encontrados no caminho original."
        if messagebox.askyesno(APP_TITLE, msg + "\n\nDeseja abrir a pasta do pacote?"):
            safe_open_folder(package.root)



    def export_validation_report(self):
        self.export_validation_report_subset(
            self.files,
            "relatorio_validacao_cte.xlsx",
            "Salvar relatório de validação",
            "Adicione XMLs antes de exportar relatório."
        )

    def open_validation_detail_window(self, text):
        win = tk.Toplevel(self)
        win.title("Detalhes da validação")
        win.geometry("980x680")
        win.minsize(760, 460)
        win.configure(bg=BG)

        header = tk.Frame(win, bg="#ffffff", height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Diagnóstico da validação", bg="#ffffff", fg=BLUE_DARK,
                 font=("Segoe UI", 16, "bold")).pack(side="left", padx=18)
        tk.Label(header, text="Use este log para entender exatamente por que o status foi gerado.", bg="#ffffff",
                 fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(6, 0))

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=14)
        txt = tk.Text(body, wrap="word", font=("Consolas", 10), bg="#ffffff", fg=TEXT, relief="solid", borderwidth=1)
        ybar = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=ybar.set)
        txt.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        footer = tk.Frame(win, bg=BG, height=54)
        footer.pack(fill="x", padx=14, pady=(0, 14))
        footer.pack_propagate(False)

        def copy_log():
            self.clipboard_clear()
            self.clipboard_append(text)
            self.set_status("Diagnóstico copiado para a área de transferência.")

        def save_log():
            path = filedialog.asksaveasfilename(
                title="Salvar diagnóstico",
                defaultextension=".txt",
                filetypes=[("Texto", "*.txt"), ("Todos", "*.*")]
            )
            if not path:
                return
            Path(path).write_text(text, encoding="utf-8")
            self.set_status(f"Diagnóstico salvo em {path}")

        tk.Button(footer, text="Copiar", command=copy_log, bg="#ffffff", fg=BLUE_DARK,
                  font=("Segoe UI", 10, "bold"), relief="solid", borderwidth=1, padx=18, pady=6).pack(side="right", padx=(8, 0))
        tk.Button(footer, text="Salvar .txt", command=save_log, bg="#ffffff", fg=BLUE_DARK,
                  font=("Segoe UI", 10, "bold"), relief="solid", borderwidth=1, padx=18, pady=6).pack(side="right", padx=(8, 0))
        tk.Button(footer, text="Fechar", command=win.destroy, bg="#ffffff", fg=TEXT,
                  font=("Segoe UI", 10), relief="solid", borderwidth=1, padx=18, pady=6).pack(side="right", padx=(8, 0))

    # ------------------------------------------------------------------
    # Importação XML modular direta e helpers CT-e modulares 2.7.0
    # A regra de chave fiscal, hash, deduplicação e contagem vive em
    # XmlImportService; a página mantém apenas diálogos e apresentação do log.
    # ------------------------------------------------------------------
    def _import_norm_path_2640(self, value):
        return self.xml_import_service.normalize_path(value)

    def _import_digits_2640(self, value):
        return self.xml_import_service.digits(value)

    def _import_sha1_file_2640(self, path):
        return self.xml_import_service.sha1_file(path)

    def _import_xml_key_from_file_2640(self, path):
        return self.xml_import_service.xml_key(path)

    def _import_info_path_2640(self, info):
        return self.xml_import_service.info_path(info)

    def _import_info_key_2640(self, info):
        return self.xml_import_service.info_key(info)

    def _import_key_label_2640(self, key):
        return self.xml_import_service.key_label(key)

    def _clean_loaded_files_2640(self):
        fixed, removed, seen = self.xml_import_service.clean_loaded(
            list(getattr(self, "files", []) or [])
        )
        self.files = list(fixed)
        return removed, seen

    def _build_xml_import_log_text_2640(self, log):
        return self.xml_import_service.build_log_text(log)

    def show_xml_import_log_2640(self, log):
        text = self._build_xml_import_log_text_2640(log)
        try:
            win = tk.Toplevel(self)
            win.title("Log de importação de XMLs")
            win.geometry("760x500")
            win.configure(bg="#f6faff")
            tk.Label(win, text="Log de importação de XML/CT-e", bg="#f6faff", fg=BLUE_DARK, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
            cards = tk.Frame(win, bg="#f6faff")
            cards.pack(fill="x", padx=14)

            def card(label, value, bg, fg):
                frame = tk.Frame(cards, bg=bg, highlightbackground="#d8e5f8", highlightthickness=1)
                tk.Label(frame, text=label, bg=bg, fg=fg, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 0))
                tk.Label(frame, text=str(value), bg=bg, fg=fg, font=("Segoe UI", 20, "bold")).pack(padx=10, pady=(0, 8))
                frame.pack(side="left", fill="x", expand=True, padx=4)

            card("Selecionados", log.get("selected", 0), "#eef4ff", BLUE_DARK)
            card("Adicionados", log.get("added", 0), "#dcfce7", GREEN)
            card("Repetidos", log.get("skipped", 0), "#fff7db", "#996b00")
            card("Total real", log.get("total", 0), "#eef4ff", BLUE_DARK)
            body = tk.Frame(win, bg="#f6faff")
            body.pack(fill="both", expand=True, padx=16, pady=12)
            txt = tk.Text(body, wrap="word", font=("Consolas", 10), bg="#ffffff", fg="#0b2341", relief="solid", borderwidth=1)
            scrollbar = ttk.Scrollbar(body, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=scrollbar.set)
            txt.grid(row=0, column=0, sticky="nsew")
            scrollbar.grid(row=0, column=1, sticky="ns")
            body.rowconfigure(0, weight=1)
            body.columnconfigure(0, weight=1)
            txt.insert("1.0", text)
            txt.configure(state="disabled")
            footer = tk.Frame(win, bg="#f6faff")
            footer.pack(fill="x", padx=16, pady=(0, 14))

            def copy_log():
                try:
                    self.clipboard_clear()
                    self.clipboard_append(text)
                    self.set_status("Log de importação copiado.")
                except Exception:
                    pass

            tk.Button(footer, text="Copiar log", command=copy_log, bg="#ffffff", fg=BLUE_DARK, font=("Segoe UI", 10, "bold"), relief="solid", borderwidth=1, padx=14, pady=5).pack(side="right", padx=(8, 0))
            tk.Button(footer, text="Fechar", command=win.destroy, bg="#ffffff", fg=TEXT, font=("Segoe UI", 10), relief="solid", borderwidth=1, padx=14, pady=5).pack(side="right", padx=(8, 0))
            try:
                win.transient(self)
                win.lift()
                win.focus_force()
            except Exception:
                pass
        except Exception:
            self._notify_info(text)

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Selecione arquivos",
            initialdir=str(self.work_folders.get("xmls", app_runtime_dir())),
            filetypes=[
                ("Documentos suportados", "*.xml *.pdf *.doc *.docx *.xls *.xlsx *.txt *.jpg *.jpeg *.png *.bmp *.tif *.tiff"),
                ("Todos", "*.*"),
            ],
            parent=self.winfo_toplevel(),
        )
        return self.cte_presenter.import_paths_async(paths, show_log=True)

    def add_folder(self):
        folder = filedialog.askdirectory(
            title="Selecione uma pasta",
            initialdir=str(self.work_folders.get("xmls", app_runtime_dir())),
            parent=self.winfo_toplevel(),
        )
        if not folder:
            return None
        return self.cte_presenter.import_paths_async([Path(folder)], show_log=True)

    def add_paths(self, paths, show_log=True):
        return self.cte_presenter.import_paths(paths, show_log=show_log)

    def status_display_text(self, status):
        st = norm_text(status)
        if not status:
            return ""
        if st.startswith("OK"):
            return "✅ " + status
        if "DIVERGENTE" in st:
            return "⚠️ " + status
        if "ANULACAO" in st:
            return "ℹ️ " + status
        if "CADASTRO" in st or "REGRA" in st or "REVIS" in st or "PARCEIRO" in st:
            return "🟠 " + status
        if "NAO" in st or "ERRO" in st or "SEM" in st:
            return "⛔ " + status
        return status

    def refresh_table(self):
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        try:
            self.tree.grid_remove()
        except Exception:
            pass

        shown = 0
        for info in self.files:
            if not self.passes_current_filter(info):
                continue
            shown += 1
            path = info.get("path", "")
            status_val = (info.get("validacao", {}) or {}).get("status", "")
            tag = ""
            status_norm = norm_text(status_val)
            if status_norm.startswith("OK"):
                tag = "ok"
            elif "DIVERGENTE" in status_norm or "NAO" in status_norm or "SEM" in status_norm or "ERRO" in status_norm:
                tag = "bad"
            elif "IGNORADO" in status_norm or "ANULACAO" in status_norm:
                tag = "info"
            elif status_val:
                tag = "warn"
            self.tree.insert(
                "",
                "end",
                iid=path if path else None,
                tags=(tag,) if tag else (),
                values=(
                    "☑" if path in self.selected_paths else "☐",
                    info.get("tipo", ""),
                    info.get("numero", ""),
                    info.get("serie", ""),
                    info.get("emitente", ""),
                    info.get("destinatario", ""),
                    (info.get("validacao", {}) or {}).get("nf", "") or get_nf_from_info(info),
                    (info.get("dest", {}) or {}).get("mun", ""),
                    (info.get("validacao", {}) or {}).get("tipo_cobranca", ""),
                    (info.get("validacao", {}) or {}).get("componente_comparado", ""),
                    money(info.get("valor", "")),
                    money((info.get("validacao", {}) or {}).get("valor_comparado", info.get("valor", ""))),
                    money((info.get("validacao", {}) or {}).get("base_frete", "")),
                    fmt_percent((info.get("validacao", {}) or {}).get("percentual", "")),
                    money((info.get("validacao", {}) or {}).get("esperado", "")),
                    money((info.get("validacao", {}) or {}).get("diferenca", "")),
                    self.status_display_text(status_val),
                    self.manual_review_label(info),
                    info.get("arquivo", ""),
                    path,
                )
            )

        try:
            self.tree.grid()
        except Exception:
            pass
        self.update_filter_options()
        self.update_filter_info_label(shown)

    def selected_infos(self):
        return [f for f in self.files if f["path"] in self.selected_paths]

    def focused_or_selected_infos(self):
        infos = self.selected_infos()
        if infos:
            return infos
        focus = self.tree.focus()
        if focus:
            path = self.tree.item(focus, "values")[-1]
            return [f for f in self.files if f["path"] == path]
        return self.files[:1]

    def remove_selected(self):
        if not self.selected_paths:
            messagebox.showinfo(APP_TITLE, "Selecione ao menos um arquivo na coluna da caixinha.")
            return

        qtd = len(self.selected_paths)
        self.files = [f for f in self.files if f["path"] not in self.selected_paths]
        self.selected_paths.clear()
        self.refresh_table()
        self.update_stats()
        self.set_status(f"{qtd} arquivo(s) removido(s).")

    def clear_list(self):
        self.files.clear()
        self.selected_paths.clear()
        self.printed_count = 0
        self.refresh_table()
        self.update_stats()
        self.set_status("Lista limpa.")

    def write_temp_html(self, infos, name="dacte_previa.html", with_button=True, auto_print=False):
        temp_dir = Path(tempfile.gettempdir()) / "central_cte_dacte"
        temp_dir.mkdir(exist_ok=True)
        html_path = temp_dir / name
        html_path.write_text(render_document(infos, with_button=with_button, auto_print=auto_print), encoding="utf-8")
        return html_path

    def preview_selected(self):
        infos = self.focused_or_selected_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Adicione ou selecione um XML primeiro.")
            return

        html_path = self.write_temp_html(infos, "dacte_previa.html")
        webbrowser.open(html_path.as_uri())
        self.set_status(f"Prévia aberta em {html_path}")

    def export_htmls(self):
        return self.cte_presenter.generate_htmls()

    def export_single_html(self):
        return self.cte_presenter.generate_single_html()

    def print_infos(self, infos):
        if not infos:
            messagebox.showinfo(APP_TITLE, "Nenhum arquivo selecionado.")
            return

        if os.name != "nt":
            messagebox.showerror(APP_TITLE, "A impressão direta está implementada apenas para Windows.")
            return

        xml_infos = [i for i in infos if Path(i["path"]).suffix.lower() == ".xml"]
        other_infos = [i for i in infos if Path(i["path"]).suffix.lower() != ".xml"]
        sent = 0
        errors = []

        try:
            if xml_infos:
                html_path = self.write_temp_html(
                    xml_infos,
                    "dacte_lote_impressao.html",
                    with_button=True,
                    auto_print=True,
                )
                open_html_for_print(html_path)
                sent += len(xml_infos)
                self.printed_count += len(xml_infos)
                self.set_status(f"XMLs abertos no navegador para impressão: {len(xml_infos)}")
                self.update_idletasks()
                time.sleep(1.0)
        except Exception as e:
            errors.append(f"XMLs: {e}")

        for info in other_infos:
            p = Path(info["path"])
            try:
                if p.suffix.lower() in SUPPORTED_DIRECT_PRINT:
                    print_file_windows(str(p))
                    sent += 1
                    self.printed_count += 1
                    self.set_status(f"Enviado para impressão: {sent}/{len(infos)}")
                    self.update_idletasks()
                    time.sleep(1.5)
                else:
                    errors.append(f"{p.name}: formato não suportado")
            except Exception as e:
                errors.append(f"{p.name}: {e}")

        self.update_stats()

        if errors:
            messagebox.showwarning(APP_TITLE, f"Abertos/enviados: {sent}\n\nErros:\n" + "\n".join(errors[:10]))
        else:
            messagebox.showinfo(APP_TITLE, f"{sent} arquivo(s) aberto(s)/enviado(s) para impressão.\n\nSe for XML/DACTE, confirme a impressão na janela do navegador.")

    def print_selected(self):
        infos = self.selected_infos()
        if not infos:
            messagebox.showinfo(APP_TITLE, "Selecione ao menos um arquivo na coluna da caixinha.")
            return
        self.print_infos(infos)

    def print_all(self):
        self.print_infos(self.files)

    def update_stats(self):
        total_files = len(self.files)
        total_cte = sum(1 for f in self.files if f.get("tipo") == "CT-e")
        selected = len(self.selected_paths)
        selected_cte = sum(1 for f in self.files if f["path"] in self.selected_paths and f.get("tipo") == "CT-e")
        total_value = sum(money_float(f.get("valor")) for f in self.files if f.get("tipo") == "CT-e")
        pending = max(total_files - self.printed_count, 0)

        divergences = 0
        divergence_value = 0.0
        for f in self.files:
            result = f.get("validacao") or {}
            st = norm_text(result.get("status", ""))
            if "DIVERGENTE" in st:
                divergences += 1
                divergence_value += abs(parse_number_br(result.get("diferenca", 0.0)))

        self.card_loaded.set_values(str(total_files), f"{total_cte} CT-e(s)")
        self.card_selected.set_values(str(selected), f"{selected_cte} CT-e(s)")
        self.card_value.set_values(money(total_value), "Total dos CT-e(s) carregados")
        self.card_print.set_values(f"{self.printed_count} / {total_files}", f"{self.printed_count} impressos • {pending} pendentes")
        if hasattr(self, "card_diff"):
            self.card_diff.set_values(str(divergences), f"R$ {money(divergence_value)}")


        self.card_loaded.set_values(str(total_files), f"{total_cte} CT-e(s)")
        self.card_selected.set_values(str(selected), f"{selected_cte} CT-e(s)")
        self.card_value.set_values(money(total_value), "Total dos CT-e(s) carregados")
        self.card_print.set_values(f"{self.printed_count} / {total_files}", f"{self.printed_count} impressos • {pending} pendentes")
