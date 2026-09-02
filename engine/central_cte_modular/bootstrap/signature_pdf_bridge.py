from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from typing import Any, MutableMapping

from ..signing import (
    PdfBatchExporter as ModularPdfBatchExporter,
    SignatureProfile,
    SignatureProfileStore,
    cte_output_basename,
    detect_registration_box,
    find_browser,
    html_file_to_pdf,
    html_text_to_pdf,
    image_backend_status,
    inject_signature_html,
    normalize_stamp_size,
    partner_name_from_info,
    process_signature_image,
    registration_sheet_html,
    render_pdf_first_page,
    render_signed_batch_html,
    render_signed_html,
    signature_block_html,
    signature_css,
    validate_pdf_file,
)
from ..signing.audit import SignaturePdfAuditWriter
from ..signing.guarded import GuardedSignaturePdfService

BRIDGE_VERSION = "2.6.67.8"
VALID_MODES = {"modular_guarded", "shadow", "legacy"}


def _load_module(name: str, path: Path) -> Any:
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Não foi possível carregar o módulo de assinatura: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def install_signature_pdf_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    paths = services.resolve("paths")
    settings = services.resolve("settings")
    logger = services.resolve("logger")
    plugin_path = Path(paths.engine) / "assinatura_pdf_engine_2_6_65_18.py"
    if not plugin_path.exists():
        plugin_path = Path(module_globals.get("__file__", "")).resolve().parent / "assinatura_pdf_engine_2_6_65_18.py"
    if not plugin_path.exists():
        return {"version": BRIDGE_VERSION, "active": False, "reason": "plugin legado não encontrado"}

    active_plugin = _load_module("central_cte_assinatura_pdf_2_6_65_18", plugin_path)
    legacy_plugin = _load_module("central_cte_assinatura_pdf_legacy_frozen_2676", plugin_path)
    report_dir = Path(paths.reports) / "assinatura_pdf_modular"
    reporter = SignaturePdfAuditWriter(report_dir)
    force_legacy_flag = Path(paths.sessions) / "FORCAR_ASSINATURA_PDF_LEGADA.flag"

    def _true(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "sim", "yes", "on"}

    def get_mode() -> str:
        if force_legacy_flag.exists() or _true(os.environ.get("CENTRAL_CTE_FORCE_LEGACY_SIGNATURE_PDF")):
            return "legacy"
        env = str(os.environ.get("CENTRAL_CTE_SIGNATURE_PDF_MODE", "") or "").strip().lower()
        try:
            configured = str((settings.load() or {}).get("signature_pdf_mode") or "").strip().lower()
        except Exception:
            configured = ""
        raw = env or configured or "modular_guarded"
        aliases = {
            "modular": "modular_guarded", "guarded": "modular_guarded", "controlado": "modular_guarded",
            "modular_guarded": "modular_guarded", "shadow": "shadow", "sombra": "shadow",
            "legacy": "legacy", "legado": "legacy",
        }
        return aliases.get(raw, "modular_guarded")

    def set_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_MODES)}")
        values = settings.load() or {}
        values["signature_pdf_mode"] = normalized
        settings.save(values)
        return normalized

    def log(event: str, **payload: Any) -> None:
        try:
            logger.write(event, **payload)
        except Exception:
            pass

    service = GuardedSignaturePdfService(legacy_plugin, reporter, get_mode, log)
    original_legacy_exporter = legacy_plugin.PdfBatchExporter

    class GuardedPdfBatchExporter:
        """API compatível com o diálogo antigo, delegando ao serviço modular."""

        def __init__(self, runtime_dir: Path, engine: Any, store: Any):
            self.runtime_dir = Path(runtime_dir)
            self.engine = engine
            self.store = store

        def export(self, infos: list[dict[str, Any]], profile: Any, date_text: str, **kwargs: Any) -> dict[str, Any]:
            return service.export(
                self.runtime_dir,
                self.engine,
                self.store,
                original_legacy_exporter,
                infos,
                profile,
                date_text,
                **kwargs,
            )

    # A interface PySide6 histórica permanece como casca temporária. Todas as
    # operações de domínio e conversão passam a resolver estes símbolos novos.
    replacements = {
        "SignatureProfile": SignatureProfile,
        "SignatureProfileStore": SignatureProfileStore,
        "PdfBatchExporter": GuardedPdfBatchExporter,
        "registration_sheet_html": registration_sheet_html,
        "process_signature_image": service.process_signature_image,
        "detect_registration_box": detect_registration_box,
        "image_backend_status": image_backend_status,
        "render_pdf_first_page": render_pdf_first_page,
        "inject_signature_html": inject_signature_html,
        "render_signed_html": service.render_signed_html,
        "render_signed_batch_html": service.render_signed_batch_html,
        "signature_block_html": signature_block_html,
        "signature_css": signature_css,
        "normalize_stamp_size": normalize_stamp_size,
        "find_browser": find_browser,
        "html_file_to_pdf": service.html_file_to_pdf,
        "html_text_to_pdf": service.html_text_to_pdf,
        "cte_output_basename": cte_output_basename,
        "partner_name_from_info": partner_name_from_info,
        "VERSION": BRIDGE_VERSION,
    }

    patched_modules: list[str] = []
    target_path = plugin_path.resolve()
    for name, candidate in list(sys.modules.items()):
        try:
            raw_file = getattr(candidate, "__file__", "")
            if not raw_file or Path(raw_file).resolve() != target_path:
                continue
            if candidate is legacy_plugin:
                continue
            for symbol, value in replacements.items():
                setattr(candidate, symbol, value)
            patched_modules.append(name)
        except Exception:
            continue
    if not patched_modules:
        for symbol, value in replacements.items():
            setattr(active_plugin, symbol, value)
        patched_modules.append(getattr(active_plugin, "__name__", "assinatura_pdf"))

    try:
        services.register_instance("signature_pdf_service", service)
        services.register_instance("signature_pdf_audit_writer", reporter)
    except Exception:
        pass

    module_globals["MODULAR_SIGNATURE_PDF_VERSION"] = BRIDGE_VERSION
    module_globals["MODULAR_SIGNATURE_PDF_SERVICE"] = service
    module_globals["MODULAR_SIGNATURE_PDF_REPORTER"] = reporter
    module_globals["MODULAR_SIGNATURE_PDF_REPORT_DIR"] = report_dir
    module_globals["MODULAR_SIGNATURE_PDF_EMERGENCY_FLAG"] = force_legacy_flag
    module_globals["get_signature_pdf_mode"] = get_mode
    module_globals["set_signature_pdf_mode"] = set_mode
    module_globals["get_signature_pdf_audit_summary"] = reporter.snapshot
    module_globals["validate_generated_pdf"] = validate_pdf_file

    log("assinatura_pdf_modular_instalada", version=BRIDGE_VERSION, mode=get_mode(), patched_modules=patched_modules)
    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": get_mode(),
        "official": "modular_when_html_exact_and_pdf_valid",
        "fallback": "legacy_on_html_difference_or_modular_error",
        "legacy_ui_shell": True,
        "xml_originals_read_only": True,
        "patched_modules": patched_modules,
        "report_directory": str(report_dir),
        "emergency_rollback_flag": str(force_legacy_flag),
        "latest_reports": [
            str(report_dir / "ultima_auditoria_assinatura_pdf.json"),
            str(report_dir / "ultima_auditoria_assinatura_pdf.txt"),
            str(report_dir / "ultima_auditoria_assinatura_pdf.csv"),
            str(reporter.jsonl_path),
        ],
    }
