from __future__ import annotations

import functools
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, MutableMapping

from ..ui import ApplicationUIController, CTeUIController, InvoiceUIController, UIAuditWriter

BRIDGE_VERSION = "2.6.67.5"


APP_ACTIONS = {
    "add_files": "import", "add_folder": "import", "add_paths": "import",
    "validate_values": "validate", "run_validation_silent": "validate", "process_work_folder": "process",
    "clear_filter": "filter", "schedule_filter_refresh": "filter",
    "refresh_table": "refresh", "update_stats": "refresh", "update_filter_options": "refresh",
    "refresh_filter_chips": "refresh",
    "export_validation_report": "export", "export_validation_report_subset": "export",
    "export_filtered_validation_report": "export", "export_selected_validation_report": "export",
    "create_filtered_package": "export", "export_htmls": "export", "export_single_html": "export",
    "print_infos": "print", "print_selected": "print", "print_all": "print",
    "signature_pdf_action_266518": "export",
}

CTE_ACTIONS = {
    "add_files": "import", "add_folder": "import", "add_paths": "import", "add_xmls": "import",
    "add_xml_files": "import", "import_files": "import", "import_xmls": "import", "load_files": "import",
    "validate_values": "validate", "validate_ctes": "validate", "process_ctes": "process",
    "run_validation": "validate", "process_files": "process",
    "refresh_table": "refresh", "update_table": "refresh", "refresh_xml_table": "refresh",
    "atualizar_tabela": "refresh", "update_stats": "refresh", "update_cards": "refresh",
    "apply_filters": "filter", "clear_filters": "filter", "clear_status_filter": "filter",
    "export_validation_report": "export", "export_report": "export", "export_selected": "export",
    "export_filtered": "export", "export_htmls": "export", "export_single_html": "export",
    "print_selected": "print", "print_all": "print",
    "signature_pdf_action_266518": "export",
}

INVOICE_ACTIONS = {
    "add_invoices": "import", "add_invoice_files": "import", "add_faturas": "import",
    "add_invoice_docs": "import", "add_files": "import", "load_invoices": "import",
    "load_invoice_files": "import", "load_faturas": "import",
    "process_invoices": "process",
    "refresh_partner_filter": "refresh", "update_partner_filter": "refresh",
    "refresh_filters": "refresh", "update_filters": "refresh", "apply_filters": "filter",
    "refresh_table": "refresh", "refresh_invoice_list": "refresh", "refresh_faturas_list": "refresh",
    "refresh_docs": "refresh", "update_cards": "refresh", "load_details_for_selected": "refresh",
    "clear_list": "clear", "clear_invoices": "clear", "clear_faturas": "clear",
    "clear_invoice_list": "clear", "clear_all": "clear", "clear_files": "clear",
    "clear_docs": "clear", "clear_documents": "clear", "clear_faturas_list": "clear",
    "clear_invoice_docs": "clear", "reset_invoices": "clear", "limpar_lista": "clear",
    "limpar_faturas": "clear", "limpar_documentos": "clear", "remove_all_invoices": "clear",
    "export_report": "export", "export_invoice_report": "export", "exportar_relatorio": "export",
    "exportar_relatorio_faturas": "export", "export_faturas_report": "export",
    "exportar_relatorio_faturas_2663": "export", "exportar_relatorio_faturas_modular_2674": "export",
}


def install_ui_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    paths = services.resolve("paths")
    logger = services.resolve("logger")
    settings = services.resolve("settings")
    audit_dir = Path(paths.reports) / "controladores_ui"
    audit_dir.mkdir(parents=True, exist_ok=True)
    force_legacy_flag = Path(paths.sessions) / "FORCAR_INTERFACE_LEGADA.flag"
    writer = UIAuditWriter(audit_dir)
    try:
        services.register_instance("ui_audit_writer", writer)
    except Exception:
        pass

    patched_classes: set[tuple[int, str]] = set()
    patch_lock = threading.RLock()

    def _true(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "sim", "yes", "on"}

    def ui_mode() -> str:
        if force_legacy_flag.exists() or _true(os.environ.get("CENTRAL_CTE_FORCE_LEGACY_UI")):
            return "legacy"
        env = str(os.environ.get("CENTRAL_CTE_UI_CONTROLLER_MODE", "") or "").strip().lower()
        try:
            configured = str((settings.load() or {}).get("ui_controller_mode") or "").strip().lower()
        except Exception:
            configured = ""
        raw = env or configured or "modular_guarded"
        aliases = {
            "modular": "modular_guarded", "guarded": "modular_guarded",
            "modular_guarded": "modular_guarded", "controlado": "modular_guarded",
            "shadow": "shadow", "sombra": "shadow", "legacy": "legacy", "legado": "legacy",
        }
        return aliases.get(raw, "modular_guarded")

    def log(message: str, **extra: Any) -> None:
        try:
            logger.write("controladores_ui", message=str(message), **extra)
        except Exception:
            pass

    controller_types = {
        "App": ApplicationUIController,
        "CTePage": CTeUIController,
        "FaturasPage": InvoiceUIController,
    }
    action_maps = {"App": APP_ACTIONS, "CTePage": CTE_ACTIONS, "FaturasPage": INVOICE_ACTIONS}

    def get_controller(page: Any, kind: str):
        attr = f"_modular_ui_controller_2675_{kind.lower()}"
        controller = getattr(page, attr, None)
        if controller is None:
            controller = controller_types[kind](page, writer, ui_mode, logger)
            try:
                setattr(page, attr, controller)
            except Exception:
                pass
        return controller

    def _make_wrapper(original: Any, kind: str, method_name: str, action: str):
        @functools.wraps(original)
        def wrapped(self: Any, *args: Any, **kwargs: Any):
            controller = get_controller(self, kind)
            return controller.dispatch(
                action,
                method_name,
                lambda *inner_args, **inner_kwargs: original(self, *inner_args, **inner_kwargs),
                args,
                kwargs,
            )
        wrapped._central_cte_ui_controller_2675 = True
        wrapped._central_cte_ui_original_2675 = original
        return wrapped

    def patch_class(cls: type, kind: str) -> bool:
        key = (id(cls), kind)
        with patch_lock:
            if key in patched_classes or getattr(cls, f"_controladores_ui_2675_{kind.lower()}", False):
                return True
            methods = action_maps[kind]
            wrapped_count = 0
            for method_name, action in methods.items():
                try:
                    current = getattr(cls, method_name, None)
                    if not callable(current) or getattr(current, "_central_cte_ui_controller_2675", False):
                        continue
                    setattr(cls, f"LEGACY_UI_{kind.upper()}_{method_name}_2675", current)
                    setattr(cls, method_name, _make_wrapper(current, kind, method_name, action))
                    wrapped_count += 1
                except Exception as exc:
                    log("Método de interface não instrumentado", kind=kind, method=method_name, error=str(exc))
            if not wrapped_count:
                return False
            setattr(cls, f"_controladores_ui_2675_{kind.lower()}", True)
            setattr(cls, "get_modular_ui_controller_2675", lambda self, _kind=kind: get_controller(self, _kind))
            patched_classes.add(key)
            log(
                "Classe de interface ligada ao controlador modular",
                kind=kind,
                class_module=getattr(cls, "__module__", ""),
                class_name=getattr(cls, "__name__", ""),
                methods=wrapped_count,
                mode=ui_mode(),
            )
            return True

    def _find_classes(kind: str) -> list[type]:
        found: list[type] = []
        direct = module_globals.get(kind)
        if isinstance(direct, type):
            found.append(direct)
        for exact in (True, False):
            for module in list(sys.modules.values()):
                try:
                    cls = getattr(module, kind, None)
                    if not isinstance(cls, type) or cls in found:
                        continue
                    defining = getattr(cls, "__module__", "") == getattr(module, "__name__", "")
                    if defining == exact:
                        found.append(cls)
                except Exception:
                    continue
        return found

    def scan_and_patch() -> dict[str, int]:
        counts = {"App": 0, "CTePage": 0, "FaturasPage": 0}
        for kind in counts:
            for cls in _find_classes(kind):
                if patch_class(cls, kind):
                    counts[kind] += 1
        return counts

    initial = scan_and_patch()

    module_globals.update({
        "MODULAR_UI_AUDIT_WRITER": writer,
        "MODULAR_UI_AUDIT_DIR": audit_dir,
        "MODULAR_UI_FORCE_LEGACY_FLAG": force_legacy_flag,
        "MODULAR_UI_CONTROLLER_VERSION": BRIDGE_VERSION,
        "get_ui_controller_mode": ui_mode,
        "rescan_ui_controller_bridge": scan_and_patch,
    })
    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": ui_mode(),
        "patched_classes": initial,
        "audit_dir": str(audit_dir),
        "force_legacy_flag": str(force_legacy_flag),
        "architecture": "view_delegates_to_controller_then_existing_service",
        "activation": "event_driven_by_view_and_page_coordinator",
        "polling_thread": False,
    }
