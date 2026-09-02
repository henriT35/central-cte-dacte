# -*- coding: utf-8 -*-
"""Janela principal modular 2.7.0.

A ``App`` agora é somente a casca de navegação. As responsabilidades de CT-e e
faturas vivem em ``CTePage`` e ``FaturasPage`` e são publicadas pela fábrica de
vistas como classes independentes.
"""
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        screen_width = max(int(self.winfo_screenwidth() or 1366), 1024)
        screen_height = max(int(self.winfo_screenheight() or 768), 640)
        initial_width = min(1680, max(1100, screen_width - 32))
        initial_height = min(940, max(640, screen_height - 72))
        self.geometry(f"{initial_width}x{initial_height}")
        self.minsize(min(1120, max(980, screen_width - 80)), min(680, max(620, screen_height - 110)))
        self.configure(bg=BG)
        self.images = {}
        try:
            self.images["app_icon"] = photo_asset("app_icon")
            self.iconphoto(True, self.images["app_icon"])
        except Exception:
            pass
        self.create_widgets()
        if os.name == "nt":
            self.after(80, lambda: self.state("zoomed"))

    def create_widgets(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        try:
            style.configure("Central.TNotebook", background=BG, borderwidth=0)
            style.configure("Central.TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=(22, 10))
        except Exception:
            pass
        self.page_tabs = ttk.Notebook(self, style="Central.TNotebook")
        self.page_tabs.pack(fill="both", expand=True)
        self.cte_page = CTePage(self.page_tabs, app=self)
        self.faturas_page = FaturasPage(self.page_tabs, app=self)
        self.page_tabs.add(self.cte_page, text="  CT-e / DACTE  ")
        self.page_tabs.add(self.faturas_page, text="  Faturas de Parceiros  ")
        self.page_tabs.select(self.cte_page)
        return self.page_tabs

    def setup_styles(self):
        return self.cte_page.setup_styles()

    def show_cte_page(self):
        self.page_tabs.select(self.cte_page)
        return self.cte_page

    def show_faturas_page(self):
        self.page_tabs.select(self.faturas_page)
        return self.faturas_page

    def __getattr__(self, name):
        namespace = object.__getattribute__(self, "__dict__")
        for page_name in ("cte_page", "faturas_page"):
            page = namespace.get(page_name)
            if page is not None:
                try:
                    return getattr(page, name)
                except AttributeError:
                    pass
        raise AttributeError(name)

    def create_header(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_header')(*args, **kwargs)

    def create_toolbar(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_toolbar')(*args, **kwargs)

    def create_validation_bar(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_validation_bar')(*args, **kwargs)

    def update_validation_status(self, *args, **kwargs):
        return getattr(self.cte_page, 'update_validation_status')(*args, **kwargs)

    def open_work_folder(self, *args, **kwargs):
        return getattr(self.cte_page, 'open_work_folder')(*args, **kwargs)

    def open_reports_folder(self, *args, **kwargs):
        return getattr(self.cte_page, 'open_reports_folder')(*args, **kwargs)

    def find_default_base_file(self, *args, **kwargs):
        return getattr(self.cte_page, 'find_default_base_file')(*args, **kwargs)

    def find_default_partner_tables_file(self, *args, **kwargs):
        return getattr(self.cte_page, 'find_default_partner_tables_file')(*args, **kwargs)

    def auto_load_default_files(self, *args, **kwargs):
        return getattr(self.cte_page, 'auto_load_default_files')(*args, **kwargs)

    def mini_button(self, *args, **kwargs):
        return getattr(self.cte_page, 'mini_button')(*args, **kwargs)

    def labeled_entry(self, *args, **kwargs):
        return getattr(self.cte_page, 'labeled_entry')(*args, **kwargs)

    def labeled_combo(self, *args, **kwargs):
        return getattr(self.cte_page, 'labeled_combo')(*args, **kwargs)

    def create_filter_bar(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_filter_bar')(*args, **kwargs)

    def schedule_filter_refresh(self, *args, **kwargs):
        return getattr(self.cte_page, 'schedule_filter_refresh')(*args, **kwargs)

    def clear_filter(self, *args, **kwargs):
        return getattr(self.cte_page, 'clear_filter')(*args, **kwargs)

    def filter_token(self, *args, **kwargs):
        return getattr(self.cte_page, 'filter_token')(*args, **kwargs)

    def filter_value_is_empty(self, *args, **kwargs):
        return getattr(self.cte_page, 'filter_value_is_empty')(*args, **kwargs)

    def info_filter_text(self, *args, **kwargs):
        return getattr(self.cte_page, 'info_filter_text')(*args, **kwargs)

    def get_filter_nf_text(self, *args, **kwargs):
        return getattr(self.cte_page, 'get_filter_nf_text')(*args, **kwargs)

    def get_filter_partner_text(self, *args, **kwargs):
        return getattr(self.cte_page, 'get_filter_partner_text')(*args, **kwargs)

    def get_filter_city_text(self, *args, **kwargs):
        return getattr(self.cte_page, 'get_filter_city_text')(*args, **kwargs)

    def get_filter_component_text(self, *args, **kwargs):
        return getattr(self.cte_page, 'get_filter_component_text')(*args, **kwargs)

    def current_filter_summary(self, *args, **kwargs):
        return getattr(self.cte_page, 'current_filter_summary')(*args, **kwargs)

    def update_filter_info_label(self, *args, **kwargs):
        return getattr(self.cte_page, 'update_filter_info_label')(*args, **kwargs)

    def refresh_filter_chips(self, *args, **kwargs):
        return getattr(self.cte_page, 'refresh_filter_chips')(*args, **kwargs)

    def validation_status_of(self, *args, **kwargs):
        return getattr(self.cte_page, 'validation_status_of')(*args, **kwargs)

    def filter_values(self, *args, **kwargs):
        return getattr(self.cte_page, 'filter_values')(*args, **kwargs)

    def distinct_filter_values(self, *args, **kwargs):
        return getattr(self.cte_page, 'distinct_filter_values')(*args, **kwargs)

    def update_filter_options(self, *args, **kwargs):
        return getattr(self.cte_page, 'update_filter_options')(*args, **kwargs)

    def status_matches_current_filter(self, *args, **kwargs):
        return getattr(self.cte_page, 'status_matches_current_filter')(*args, **kwargs)

    def passes_current_filter(self, *args, **kwargs):
        return getattr(self.cte_page, 'passes_current_filter')(*args, **kwargs)

    def filtered_files(self, *args, **kwargs):
        return getattr(self.cte_page, 'filtered_files')(*args, **kwargs)

    def create_table(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_table')(*args, **kwargs)

    def create_cards(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_cards')(*args, **kwargs)

    def create_status(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_status')(*args, **kwargs)

    def set_status(self, *args, **kwargs):
        return getattr(self.cte_page, 'set_status')(*args, **kwargs)

    def on_tree_click(self, *args, **kwargs):
        return getattr(self.cte_page, 'on_tree_click')(*args, **kwargs)

    def toggle_all(self, *args, **kwargs):
        return getattr(self.cte_page, 'toggle_all')(*args, **kwargs)

    def _load_base_from_path(self, *args, **kwargs):
        return getattr(self.cte_page, '_load_base_from_path')(*args, **kwargs)

    def _load_partner_tables_from_path(self, *args, **kwargs):
        return getattr(self.cte_page, '_load_partner_tables_from_path')(*args, **kwargs)

    def audit_weight_action(self, *args, **kwargs):
        return getattr(self.cte_page, 'audit_weight_action')(*args, **kwargs)

    def audit_base_action(self, *args, **kwargs):
        return getattr(self.cte_page, 'audit_base_action')(*args, **kwargs)

    def audit_partner_tables_action(self, *args, **kwargs):
        return getattr(self.cte_page, 'audit_partner_tables_action')(*args, **kwargs)

    def session_default_name(self, *args, **kwargs):
        return getattr(self.cte_page, 'session_default_name')(*args, **kwargs)

    def build_session_payload(self, *args, **kwargs):
        return getattr(self.cte_page, 'build_session_payload')(*args, **kwargs)

    def save_session_file(self, *args, **kwargs):
        return getattr(self.cte_page, 'save_session_file')(*args, **kwargs)

    def load_session_file(self, *args, **kwargs):
        return getattr(self.cte_page, 'load_session_file')(*args, **kwargs)

    def run_validation_silent(self, *args, **kwargs):
        return getattr(self.cte_page, 'run_validation_silent')(*args, **kwargs)

    def process_work_folder(self, *args, **kwargs):
        return getattr(self.cte_page, 'process_work_folder')(*args, **kwargs)

    def open_table_registration_dialog(self, *args, **kwargs):
        return getattr(self.cte_page, 'open_table_registration_dialog')(*args, **kwargs)

    def load_base_file(self, *args, **kwargs):
        return getattr(self.cte_page, 'load_base_file')(*args, **kwargs)

    def load_partner_tables_file(self, *args, **kwargs):
        return getattr(self.cte_page, 'load_partner_tables_file')(*args, **kwargs)

    def validate_values(self, *args, **kwargs):
        return getattr(self.cte_page, 'validate_values')(*args, **kwargs)

    def validation_summary_text(self, *args, **kwargs):
        return getattr(self.cte_page, 'validation_summary_text')(*args, **kwargs)

    def manual_review_label(self, *args, **kwargs):
        return getattr(self.cte_page, 'manual_review_label')(*args, **kwargs)

    def ensure_base_frete_for_info(self, *args, **kwargs):
        return getattr(self.cte_page, 'ensure_base_frete_for_info')(*args, **kwargs)

    def apply_manual_percentage(self, *args, **kwargs):
        return getattr(self.cte_page, 'apply_manual_percentage')(*args, **kwargs)

    def manual_target_infos(self, *args, **kwargs):
        return getattr(self.cte_page, 'manual_target_infos')(*args, **kwargs)

    def mark_selected_reviewed(self, *args, **kwargs):
        return getattr(self.cte_page, 'mark_selected_reviewed')(*args, **kwargs)

    def clear_manual_review(self, *args, **kwargs):
        return getattr(self.cte_page, 'clear_manual_review')(*args, **kwargs)

    def set_manual_observation(self, *args, **kwargs):
        return getattr(self.cte_page, 'set_manual_observation')(*args, **kwargs)

    def show_validation_summary(self, *args, **kwargs):
        return getattr(self.cte_page, 'show_validation_summary')(*args, **kwargs)

    def write_validation_log(self, *args, **kwargs):
        return getattr(self.cte_page, 'write_validation_log')(*args, **kwargs)

    def show_validation_details(self, *args, **kwargs):
        return getattr(self.cte_page, 'show_validation_details')(*args, **kwargs)

    def _sanitize_report_label(self, *args, **kwargs):
        return getattr(self.cte_page, '_sanitize_report_label')(*args, **kwargs)

    def export_validation_report_subset(self, *args, **kwargs):
        return getattr(self.cte_page, 'export_validation_report_subset')(*args, **kwargs)

    def export_filtered_validation_report(self, *args, **kwargs):
        return getattr(self.cte_page, 'export_filtered_validation_report')(*args, **kwargs)

    def export_selected_validation_report(self, *args, **kwargs):
        return getattr(self.cte_page, 'export_selected_validation_report')(*args, **kwargs)

    def open_last_validation_log(self, *args, **kwargs):
        return getattr(self.cte_page, 'open_last_validation_log')(*args, **kwargs)

    def unique_destination_path(self, *args, **kwargs):
        return getattr(self.cte_page, 'unique_destination_path')(*args, **kwargs)

    def create_filtered_package(self, *args, **kwargs):
        return getattr(self.cte_page, 'create_filtered_package')(*args, **kwargs)

    def export_validation_report(self, *args, **kwargs):
        return getattr(self.cte_page, 'export_validation_report')(*args, **kwargs)

    def open_validation_detail_window(self, *args, **kwargs):
        return getattr(self.cte_page, 'open_validation_detail_window')(*args, **kwargs)

    def _import_norm_path_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_import_norm_path_2640')(*args, **kwargs)

    def _import_digits_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_import_digits_2640')(*args, **kwargs)

    def _import_sha1_file_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_import_sha1_file_2640')(*args, **kwargs)

    def _import_xml_key_from_file_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_import_xml_key_from_file_2640')(*args, **kwargs)

    def _import_info_path_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_import_info_path_2640')(*args, **kwargs)

    def _import_info_key_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_import_info_key_2640')(*args, **kwargs)

    def _import_key_label_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_import_key_label_2640')(*args, **kwargs)

    def _clean_loaded_files_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_clean_loaded_files_2640')(*args, **kwargs)

    def _build_xml_import_log_text_2640(self, *args, **kwargs):
        return getattr(self.cte_page, '_build_xml_import_log_text_2640')(*args, **kwargs)

    def show_xml_import_log_2640(self, *args, **kwargs):
        return getattr(self.cte_page, 'show_xml_import_log_2640')(*args, **kwargs)

    def add_files(self, *args, **kwargs):
        return getattr(self.cte_page, 'add_files')(*args, **kwargs)

    def add_folder(self, *args, **kwargs):
        return getattr(self.cte_page, 'add_folder')(*args, **kwargs)

    def add_paths(self, *args, **kwargs):
        return getattr(self.cte_page, 'add_paths')(*args, **kwargs)

    def status_display_text(self, *args, **kwargs):
        return getattr(self.cte_page, 'status_display_text')(*args, **kwargs)

    def refresh_table(self, *args, **kwargs):
        return getattr(self.cte_page, 'refresh_table')(*args, **kwargs)

    def selected_infos(self, *args, **kwargs):
        return getattr(self.cte_page, 'selected_infos')(*args, **kwargs)

    def focused_or_selected_infos(self, *args, **kwargs):
        return getattr(self.cte_page, 'focused_or_selected_infos')(*args, **kwargs)

    def remove_selected(self, *args, **kwargs):
        return getattr(self.cte_page, 'remove_selected')(*args, **kwargs)

    def clear_list(self, *args, **kwargs):
        return getattr(self.cte_page, 'clear_list')(*args, **kwargs)

    def write_temp_html(self, *args, **kwargs):
        return getattr(self.cte_page, 'write_temp_html')(*args, **kwargs)

    def preview_selected(self, *args, **kwargs):
        return getattr(self.cte_page, 'preview_selected')(*args, **kwargs)

    def export_htmls(self, *args, **kwargs):
        return getattr(self.cte_page, 'export_htmls')(*args, **kwargs)

    def export_single_html(self, *args, **kwargs):
        return getattr(self.cte_page, 'export_single_html')(*args, **kwargs)

    def print_infos(self, *args, **kwargs):
        return getattr(self.cte_page, 'print_infos')(*args, **kwargs)

    def print_selected(self, *args, **kwargs):
        return getattr(self.cte_page, 'print_selected')(*args, **kwargs)

    def print_all(self, *args, **kwargs):
        return getattr(self.cte_page, 'print_all')(*args, **kwargs)

    def update_stats(self, *args, **kwargs):
        return getattr(self.cte_page, 'update_stats')(*args, **kwargs)


__all__ = ["App"]
