from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "web_local" / "static" / "app.js").read_text(encoding="utf-8")
STYLES = (ROOT / "web_local" / "static" / "styles.css").read_text(encoding="utf-8")
SERVER = (ROOT / "web_local" / "server.py").read_text(encoding="utf-8")


def test_invoice_file_table_uses_existing_size_formatter():
    assert "formatFileSize(" not in APP_JS
    assert "formatBytes(row.size_bytes || 0)" in APP_JS
    assert "function formatBytes(" in APP_JS


def test_admin_users_card_cannot_overlap_neighbor_cards():
    assert ".admin-users-card { grid-column: 1 / -1;" in STYLES
    assert ".admin-users-card .admin-user-row { grid-template-columns: minmax(0, 1fr)" in STYLES
    assert "overflow: hidden" in STYLES


def test_release_identifies_hotfix_version_or_newer():
    server_match = re.search(r"MVP13 R12\.(\d+)", SERVER)
    app_match = re.search(r"MVP13 R12\.(\d+)", APP_JS)
    assert server_match and int(server_match.group(1)) >= 1
    assert app_match and int(app_match.group(1)) >= 1
