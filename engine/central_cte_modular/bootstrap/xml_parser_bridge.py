from __future__ import annotations

from pathlib import Path
from typing import Any, MutableMapping
import os

from ..xml.audit_batch import ParserBatchAudit
from ..xml.cte_parser import PARSER_VERSION, ModularXmlParser, parse_xml_modular
from ..xml.promotion import (
    GuardedModularParser,
    MODE_LEGACY_SHADOW,
    MODE_MODULAR_FAST,
    MODE_MODULAR_GUARDED,
    ParserPromotionReport,
    VALID_MODES,
)
from ..xml.shadow_parser import ParserShadowComparator
from ..xml.shadow_report import ParserShadowReport
from ..xml.import_service import XML_IMPORT_SERVICE_VERSION, XmlImportService
from ..xml.batch_processor import FastXmlBatchProcessor
from ..xml.batch_report import XmlImportBatchReporter
from ..xml.cache import XmlParseCache

BRIDGE_VERSION = "2.7.0-rc17"


def install_xml_parser_shadow(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    legacy = module_globals.get("LEGACY_PARSE_XML") or module_globals.get("parse_xml")
    if not callable(legacy):
        return {"version": BRIDGE_VERSION, "active": False, "reason": "parse_xml legado não encontrado"}

    paths = services.resolve("paths")
    report_dir = paths.reports / "parser_xml_sombra"
    reporter = ParserShadowReport(report_dir)
    promotion_reporter = ParserPromotionReport(report_dir)
    logger = services.resolve("logger")
    try:
        settings = services.resolve("settings")
    except Exception:
        settings = None
    memory_settings: dict[str, Any] = {}
    sessions_dir = Path(getattr(paths, "sessions", Path(paths.reports).parent / "sessoes"))
    emergency_flag = sessions_dir / "FORCAR_PARSER_LEGADO.flag"

    def log_difference(text: str) -> None:
        try:
            logger.write("parser_xml_shadow", message=str(text))
        except Exception:
            pass

    def get_mode() -> str:
        env_mode = str(os.environ.get("CENTRAL_CTE_XML_PARSER_MODE", "") or "").strip().lower()
        if env_mode in VALID_MODES:
            return env_mode
        if emergency_flag.exists():
            return MODE_LEGACY_SHADOW
        try:
            source = settings.load() if settings is not None else memory_settings
            configured = str(source.get("xml_parser_mode", "") or "").strip().lower()
            if configured in VALID_MODES:
                return configured
        except Exception:
            pass
        return MODE_MODULAR_FAST

    def set_mode(mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in VALID_MODES:
            raise ValueError(f"Modo inválido: {mode}. Use {sorted(VALID_MODES)}")
        if settings is None:
            memory_settings["xml_parser_mode"] = normalized
        else:
            values = settings.load()
            values["xml_parser_mode"] = normalized
            settings.save(values)
        return normalized

    comparator = ParserShadowComparator(
        legacy,
        log_difference,
        modular_parser=parse_xml_modular,
        on_result=reporter.record,
    )
    guarded = GuardedModularParser(
        legacy,
        parse_xml_modular,
        comparator,
        promotion_reporter,
        get_mode,
        log_difference,
    )
    promoted_parser = guarded.build_parser()
    batch_auditor = ParserBatchAudit(comparator, reporter)

    cache_root = Path(getattr(paths, "cache", Path(paths.reports).parent / "cache"))
    xml_cache = XmlParseCache(
        cache_root / "xml_parse_cache.db",
        parser_version=PARSER_VERSION,
    )
    fast_batch_processor = FastXmlBatchProcessor(
        xml_cache,
        mode_resolver=get_mode,
        max_workers=4,
        parallel_threshold=100,
    )
    batch_reporter = XmlImportBatchReporter(Path(paths.reports) / "importacao_xml")
    # A função oficial continua compatível com chamadas unitárias e também
    # publica o contrato de lote usado pelo XmlImportService.
    setattr(promoted_parser, "parse_many", fast_batch_processor.parse_many)
    setattr(promoted_parser, "_central_cte_xml_cache", xml_cache)
    setattr(promoted_parser, "_central_cte_batch_processor", fast_batch_processor)
    xml_import_service = XmlImportService(
        promoted_parser,
        batch_processor=fast_batch_processor,
        batch_reporter=batch_reporter,
    )
    try:
        services.register_instance("xml_import", xml_import_service, replace=True)
    except Exception:
        pass

    module_globals["LEGACY_PARSE_XML"] = legacy
    module_globals["MODULAR_XML_PARSER"] = ModularXmlParser()
    module_globals["PARSER_SHADOW_COMPARATOR"] = comparator
    module_globals["PARSER_SHADOW_REPORTER"] = reporter
    module_globals["PARSER_SHADOW_BATCH_AUDITOR"] = batch_auditor
    module_globals["PARSER_SHADOW_REPORT_DIR"] = report_dir
    module_globals["PARSER_PROMOTION_CONTROLLER"] = guarded
    module_globals["PARSER_PROMOTION_REPORTER"] = promotion_reporter
    module_globals["PARSER_LEGACY_EMERGENCY_FLAG"] = emergency_flag
    module_globals["parse_xml_modular"] = parse_xml_modular
    module_globals["compare_xml_parsers"] = comparator.compare
    module_globals["compare_xml_parsers_with_legacy"] = comparator.compare_with_legacy
    module_globals["compare_xml_parser_results"] = comparator.compare_results
    module_globals["audit_xml_paths"] = batch_auditor.run
    module_globals["audit_xml_folder"] = lambda folder, recursive=True: batch_auditor.run(folder, recursive=recursive)
    module_globals["get_parser_shadow_summary"] = reporter.snapshot
    module_globals["get_parser_audit_consolidated_summary"] = reporter.consolidated_snapshot
    module_globals["rebuild_parser_audit_reports"] = reporter.rebuild_consolidated
    module_globals["get_xml_parser_mode"] = get_mode
    module_globals["set_xml_parser_mode"] = set_mode
    module_globals["get_parser_promotion_summary"] = promotion_reporter.snapshot
    module_globals["parse_xml"] = promoted_parser
    module_globals["MODULAR_XML_PARSER_VERSION"] = BRIDGE_VERSION
    module_globals["XML_IMPORT_SERVICE"] = xml_import_service
    module_globals["XML_IMPORT_SERVICE_VERSION"] = XML_IMPORT_SERVICE_VERSION
    module_globals["XML_PARSE_CACHE"] = xml_cache
    module_globals["XML_FAST_BATCH_PROCESSOR"] = fast_batch_processor
    module_globals["XML_IMPORT_BATCH_REPORTER"] = batch_reporter
    module_globals["clear_xml_parse_cache"] = xml_cache.clear

    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": get_mode(),
        "official": "modular_fast_by_default",
        "fallback": "guarded_or_legacy_modes_available_for_homologation",
        "legacy_calls_per_xml": 0 if get_mode() == MODE_MODULAR_FAST else 1,
        "modular_calls_per_xml": 1,
        "cache_backend": xml_cache.backend,
        "cache_path": str(xml_cache.path if xml_cache.backend == "sqlite" else xml_cache._json_path),
        "parallel_workers": fast_batch_processor.max_workers,
        "parallel_threshold": fast_batch_processor.parallel_threshold,
        "parallel_min_bytes": fast_batch_processor.parallel_min_bytes,
        "parallel_min_files": fast_batch_processor.parallel_min_files,
        "batch_report_directory": str(batch_reporter.directory),
        "report_directory": str(report_dir),
        "session_id": reporter.session_id,
        "promotion_session_id": promotion_reporter.session_id,
        "emergency_rollback_flag": str(emergency_flag),
        "xml_import": "direct_modular_service",
        "xml_import_version": XML_IMPORT_SERVICE_VERSION,
        "latest_reports": [
            str(report_dir / "ultima_auditoria.html"),
            str(report_dir / "ultima_auditoria.json"),
            str(report_dir / "ultima_auditoria.txt"),
            str(reporter.jsonl_path),
            str(report_dir / "ultima_promocao_parser.json"),
            str(report_dir / "ultima_promocao_parser.txt"),
            str(report_dir / "ultima_promocao_parser.csv"),
            str(promotion_reporter.jsonl_path),
        ],
        "consolidated_reports": [
            str(report_dir / "auditoria_consolidada.html"),
            str(report_dir / "auditoria_consolidada.json"),
            str(report_dir / "auditoria_consolidada.txt"),
            str(report_dir / "divergencias.csv"),
            str(report_dir / "divergencias_criticas.json"),
            str(report_dir / "divergencias_informativas.json"),
            str(report_dir / "xmls_iguais.json"),
        ],
    }
