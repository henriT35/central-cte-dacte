from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web_local"

import sys
for candidate in (str(WEB), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from developer_tools import DeveloperTools  # noqa: E402
from services.engine_xml_service import OfficialXmlEngineService  # noqa: E402


def _context(data_root: Path):
    workspace = data_root / "workspaces" / "test"
    upload_root = workspace / "uploads"
    state_root = workspace / "state"
    categories = {
        "xml": upload_root / "xml",
        "faturas": upload_root / "faturas",
        "bases": upload_root / "bases",
        "tabelas": upload_root / "tabelas",
    }
    for path in (upload_root, state_root, *categories.values()):
        path.mkdir(parents=True, exist_ok=True)
    xml_service = OfficialXmlEngineService(ROOT, upload_root, state_root, data_root / "partner_tables")
    return SimpleNamespace(upload_categories=categories, xml_service=xml_service)


def test_partner_catalog_rebuilds_when_grauna_file_is_added() -> None:
    source_files = ROOT / "web_local" / "data" / "partner_tables" / "files"
    grauna = source_files / "GRAUNA_TRANSPORTES.xlsx"
    assert grauna.is_file()

    with tempfile.TemporaryDirectory() as tmp:
        data_root = Path(tmp) / "data"
        security_root = data_root / "security"
        files_root = data_root / "partner_tables" / "files"
        files_root.mkdir(parents=True, exist_ok=True)
        security_root.mkdir(parents=True, exist_ok=True)

        for source in source_files.glob("*.xlsx"):
            if source.name != grauna.name:
                shutil.copy2(source, files_root / source.name)

        tools = DeveloperTools(ROOT, security_root)
        context = _context(data_root)
        before = tools.ensure_partner_files(context)
        assert before["file_count"] == 16
        assert before["partners"] == 16

        shutil.copy2(grauna, files_root / grauna.name)
        after = tools.ensure_partner_files(context)
        assert after["file_count"] == 17
        assert after["partners"] == 17
        assert after["rules"] >= before["rules"]

        signature = (data_root / "partner_tables" / "compiled_signature.txt").read_text(encoding="utf-8")
        assert "GRAUNA_TRANSPORTES.xlsx" in signature


def test_server_syncs_catalog_for_all_users_and_before_xml_processing() -> None:
    source = (WEB / "server.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "RC27.14 WEB/WINDOWS MVP13 R12.13.9"' in source
    assert "DEVELOPER_TOOLS.ensure_partner_files(context)" in source
    block = source[source.index("def _run_xml_job"):source.index("def start_xml_job")]
    assert "DEVELOPER_TOOLS.ensure_partner_files(context)" in block
