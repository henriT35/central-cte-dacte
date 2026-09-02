from __future__ import annotations

from pathlib import Path
from typing import Any, MutableMapping

from ..infrastructure.formatting import (
    date_br, extract_cnpjs, format_cep, format_chave, format_cnpj_cpf,
    money, money_float, only_digits, qty,
)
from ..infrastructure.normalization import norm_text, normalize_header, normalize_nf
from ..infrastructure.runtime import RuntimeEnvironment

BRIDGE_VERSION = "2.6.66.1"


def install_infrastructure_bridge(
    module_globals: MutableMapping[str, Any],
    engine_file: Path,
    services: Any,
) -> dict[str, Any]:
    """Redirects low-risk legacy helpers to modular services.

    Original call signatures are preserved, and old implementations remain
    available under LEGACY_INFRASTRUCTURE_FUNCTIONS for regression/debugging.
    """
    runtime = RuntimeEnvironment.from_engine_file(engine_file)
    logger = services.resolve("logger")
    originals = dict(module_globals.get("LEGACY_INFRASTRUCTURE_FUNCTIONS") or {})

    replacements = {
        "resource_path": runtime.resource_path,
        "app_runtime_dir": runtime.runtime_dir,
        "safe_open_folder": runtime.open_path,
        "safe_open_file": runtime.open_path,
        "ensure_work_folders": runtime.ensure_work_folders,
        "only_digits": only_digits,
        "extract_cnpjs": extract_cnpjs,
        "format_cnpj_cpf": format_cnpj_cpf,
        "format_cep": format_cep,
        "money": money,
        "money_float": money_float,
        "qty": qty,
        "date_br": date_br,
        "format_chave": format_chave,
        "norm_text": norm_text,
        "normalize_header": normalize_header,
        "normalize_nf": normalize_nf,
    }
    for name, replacement in replacements.items():
        current = module_globals.get(name)
        if callable(current) and name not in originals:
            originals[name] = current
        module_globals[name] = replacement

    def write_app_log(file_name: str, text: Any) -> None:
        logger.write_legacy(file_name, text, runtime.runtime_dir() / "logs")

    current_log = module_globals.get("write_app_log")
    if callable(current_log) and "write_app_log" not in originals:
        originals["write_app_log"] = current_log
    module_globals["write_app_log"] = write_app_log
    module_globals["LEGACY_INFRASTRUCTURE_FUNCTIONS"] = originals
    module_globals["MODULAR_INFRASTRUCTURE_VERSION"] = BRIDGE_VERSION
    module_globals["MODULAR_RUNTIME_ENVIRONMENT"] = runtime
    return {"version": BRIDGE_VERSION, "redirected": tuple(sorted((*replacements.keys(), "write_app_log")))}
