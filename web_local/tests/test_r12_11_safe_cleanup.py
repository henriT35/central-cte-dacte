from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_release_version_and_engine_preserved():
    assert 'MVP13 R12.13' in _text('web_local/server.py')
    assert 'MVP13 R12.13' in _text('web_local/static/app.js')
    assert 'central-cte-dacte:r12.13' in _text('deploy/vps/compose.yaml')
    assert 'RC26.6' in _text('web_local/server.py')


def test_obsolete_desktop_page_classes_removed_but_modern_pages_remain():
    obsolete = ['DashboardPage', 'AuditPage', 'ReportsPage', 'SettingsPage']
    for rel in ('ui_modern/app_shell.py', '_internal/ui_modern/app_shell.py'):
        source = _text(rel)
        for name in obsolete:
            assert f'class {name}(' not in source
        assert 'class ModernApplicationShell(' in source
        assert 'ModernDashboardPage' in source
        assert 'ModernAuditPage' in source
        assert 'ModernReportsPage' in source
        assert 'ModernSettingsPage' in source


def test_removed_imports_from_obsolete_pages_are_not_left_behind():
    source = _text('ui_modern/app_shell.py')
    for token in (
        'QFont,', 'QAbstractItemView', 'QGridLayout', 'QTableView',
        'CurrentInvoiceAdapter', 'CurrentXmlAdapter', 'format_money_br',
        'format_percentage_br', 'status_tone', 'ColumnSpec',
        'PresentationTableModel', 'MetricCard', 'ResponsiveCardGrid',
    ):
        assert token not in source


def test_caddy_does_not_claim_udp_443_used_by_bedrock():
    compose = _text('deploy/vps/compose.yaml')
    assert '"443:443"' in compose
    assert '443:443/udp' not in compose


def test_cleanup_does_not_remove_compatibility_entrypoints():
    for rel in (
        'engine/central_cte_engine_1_1_34.py',
        'engine/central_cte_engine_1_1_35.py',
        'engine/central_cte_engine_1_1_36.py',
        'engine/legacy/central_cte_engine_2_6_65_20_2_frozen.py',
    ):
        assert (ROOT / rel).is_file(), rel
