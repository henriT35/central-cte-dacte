from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "web_local/static/app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web_local/static/index.html").read_text(encoding="utf-8")
CSS = (ROOT / "web_local/static/styles.css").read_text(encoding="utf-8")
SERVER = (ROOT / "web_local/server.py").read_text(encoding="utf-8")
COMPOSE = (ROOT / "deploy/vps/compose.yaml").read_text(encoding="utf-8")

def test_release_version():
    assert "MVP13 R12.13" in SERVER
    assert "MVP13 R12.13" in APP
    assert "central-cte-dacte:r12.13" in COMPOSE

def test_advanced_filters_are_present():
    for element_id in [
        "signature-filter", "signature-status-filter", "signature-partner-filter",
        "signature-city-filter", "signature-result-filter", "signature-sort-filter",
        "signature-visible-count", "reset-signature-filters", "unselect-visible-dactes",
    ]:
        assert f'id="{element_id}"' in HTML
    assert "Selecionar visíveis" in HTML
    assert "Desmarcar visíveis" in HTML
    assert "Prontos para PDF" in HTML

def test_filter_logic_covers_business_fields():
    assert "refreshSignatureDynamicFilterOptions" in APP
    assert "signatureResultMatches" in APP
    assert "signatureSortCandidates" in APP
    for field in ["row.recipient", "row.nf", "row.city", "row.authorization_status", "row.applied_rule", "row.file"]:
        assert field in APP
    assert 'filter === "__authorization_pending__"' in APP
    assert 'filter === "__manual__"' in APP

def test_visible_selection_is_filter_scoped():
    assert 'filteredSignatureCandidates().filter(({ row }) => isOfficialCte(row))' in APP
    assert 'state.selectedSignature.delete(String(row.path))' in APP

def test_responsive_layout_exists():
    assert ".signature-filterbar-advanced" in CSS
    assert "grid-template-columns" in CSS
