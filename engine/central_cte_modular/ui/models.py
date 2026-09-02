from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def _safe_len(value: Any) -> int:
    try:
        return len(value or [])
    except Exception:
        return 0


def _table_rows(page: Any) -> int:
    for name in (
        "invoice_table", "table", "tree", "xml_table", "cte_table",
        "faturas_table", "details_table", "detail_table",
    ):
        table = getattr(page, name, None)
        if table is None:
            continue
        try:
            row_count = getattr(table, "rowCount", None)
            if callable(row_count):
                return int(row_count())
        except Exception:
            pass
        try:
            children = getattr(table, "get_children", None)
            if callable(children):
                return len(children())
        except Exception:
            pass
    return 0


def _selected_count(page: Any) -> int:
    for name in ("selected_paths", "selected_files", "selected_items"):
        value = getattr(page, name, None)
        if value is not None:
            count = _safe_len(value)
            if count:
                return count
    for name in ("invoice_table", "table", "tree", "xml_table"):
        table = getattr(page, name, None)
        if table is None:
            continue
        try:
            selection = getattr(table, "selection", None)
            if callable(selection):
                return len(selection())
        except Exception:
            pass
        try:
            selection_model = getattr(table, "selectionModel", None)
            if callable(selection_model):
                model = selection_model()
                rows = getattr(model, "selectedRows", None)
                if callable(rows):
                    return len(rows())
        except Exception:
            pass
    return 0


@dataclass(frozen=True)
class UIStateSnapshot:
    files_count: int = 0
    invoice_docs_count: int = 0
    invoice_rows_count: int = 0
    invoice_details_count: int = 0
    selected_count: int = 0
    table_rows: int = 0
    status_text: str = ""

    @classmethod
    def capture(cls, page: Any) -> "UIStateSnapshot":
        status = ""
        for name in ("status_text", "last_status", "status_message"):
            try:
                value = getattr(page, name, "")
                if value:
                    status = str(value)
                    break
            except Exception:
                pass
        return cls(
            files_count=_safe_len(getattr(page, "files", None)),
            invoice_docs_count=_safe_len(getattr(page, "invoice_docs", None)),
            invoice_rows_count=_safe_len(getattr(page, "invoice_rows", None)),
            invoice_details_count=_safe_len(getattr(page, "invoice_detail_records", None)),
            selected_count=_selected_count(page),
            table_rows=_table_rows(page),
            status_text=status[:500],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UIActionAudit:
    version: str
    timestamp: str
    controller: str
    page_class: str
    page_module: str
    action: str
    method: str
    mode: str
    classification: str
    elapsed_ms: float
    before: UIStateSnapshot
    after: UIStateSnapshot
    result_type: str = ""
    error: str = ""
    official_source: str = ""
    thread_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        version: str,
        controller: str,
        page: Any,
        action: str,
        method: str,
        mode: str,
        classification: str,
        elapsed_ms: float,
        before: UIStateSnapshot,
        after: UIStateSnapshot,
        result: Any = None,
        error: str = "",
        official_source: str = "",
        thread_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "UIActionAudit":
        return cls(
            version=version,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            controller=controller,
            page_class=type(page).__name__,
            page_module=getattr(type(page), "__module__", ""),
            action=action,
            method=method,
            mode=mode,
            classification=classification,
            elapsed_ms=round(float(elapsed_ms), 3),
            before=before,
            after=after,
            result_type=type(result).__name__ if result is not None else "NoneType",
            error=str(error or ""),
            official_source=str(official_source or ""),
            thread_name=str(thread_name or ""),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["before"] = self.before.to_dict()
        payload["after"] = self.after.to_dict()
        return payload
