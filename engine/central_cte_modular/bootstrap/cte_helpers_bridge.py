from __future__ import annotations

"""Publica helpers CT-e modulares no contrato histórico sem aplicar patches."""

from typing import Any, MutableMapping

from ..ui.cte.helpers import CTeHelperService, FILTER_GROUPS, HELPERS_VERSION

BRIDGE_VERSION = "2.7.0"


def install_cte_helpers_bridge(module_globals: MutableMapping[str, Any], services: Any) -> dict[str, Any]:
    service = CTeHelperService()

    def selected_or_visible(page: Any):
        return service.selected_or_visible(page)

    def status_group(status: Any) -> str:
        return service.status_group(status)

    def has_ignored(info: Any) -> bool:
        return service.has_ignored_nfs(info)

    def raw_status(info: Any) -> str:
        return service.raw_status(info)

    def matches(info: Any, filters: Any = None, ui: Any = None) -> bool:
        return service.matches_filters(info, filters, ui)

    def report_bucket(status: Any) -> str:
        return service.report_bucket(status)

    exports = {
        "_central_cte_selected_or_visible_infos_266516": selected_or_visible,
        "CENTRAL_CTE_FILTER_GROUPS_266517": FILTER_GROUPS,
        "central_cte_status_group_266517": status_group,
        "_central_cte_has_ignored_nfs_266517": has_ignored,
        "_central_cte_raw_status_266517": raw_status,
        "_central_cte_filter_info_matches_266517": matches,
        "_central_cte_report_bucket_266517": report_bucket,
        "report_bucket": report_bucket,
        "MODULAR_CTE_HELPER_SERVICE": service,
        "MODULAR_CTE_HELPERS_VERSION": HELPERS_VERSION,
    }
    module_globals.update(exports)
    try:
        services.register_instance("cte_helper_service", service, replace=True)
    except Exception:
        pass
    return {
        "version": BRIDGE_VERSION,
        "active": True,
        "mode": "direct_modular_cte_helpers",
        "service_version": HELPERS_VERSION,
        "compatibility_aliases": 7,
        "runtime_residual_required": False,
        "exports": sorted(exports),
    }


__all__ = ["BRIDGE_VERSION", "install_cte_helpers_bridge"]
