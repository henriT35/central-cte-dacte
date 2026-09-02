from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "web_local/static/app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "web_local/static/index.html").read_text(encoding="utf-8")
STYLES = (ROOT / "web_local/static/styles.css").read_text(encoding="utf-8")
SERVER_TEXT = (ROOT / "web_local/server.py").read_text(encoding="utf-8")


def load_server_module():
    spec = importlib.util.spec_from_file_location("central_server_r1210", ROOT / "web_local/server.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_cte(key: str = "15260759339996000107570100000207021001267563", cte: str = "20702") -> bytes:
    return f'''<?xml version="1.0" encoding="utf-8"?>
<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00">
  <CTe><infCte Id="CTe{key}" versao="4.00"><ide><nCT>{cte}</nCT></ide></infCte></CTe>
  <protCTe><infProt><chCTe>{key}</chCTe></infProt></protCTe>
</cteProc>'''.encode("utf-8")


def test_r1210_version_and_invoice_icon():
    assert 'MVP13 R12.13' in SERVER_TEXT
    assert 'MVP13 R12.13' in APP_JS
    assert 'central-cte-dacte:r12.13' in (ROOT / "deploy/vps/compose.yaml").read_text(encoding="utf-8")
    assert 'icon: "alert.svg"' in APP_JS
    assert 'icon: "warning.svg"' not in APP_JS
    assert (ROOT / "web_local/static/icons/alert.svg").is_file()


def test_invoice_file_conference_is_after_invoices_and_collapsible():
    identified = INDEX.index("Faturas identificadas")
    reconciliation = INDEX.index("Conferência dos arquivos do lote")
    assert identified < reconciliation
    assert 'id="invoice-file-panel"' in INDEX
    assert 'id="toggle-invoice-file-panel"' in INDEX
    assert 'aria-controls="invoice-file-panel-content"' in INDEX
    assert 'invoice-file-panel.collapsed .invoice-file-panel-content' in STYLES
    assert 'function setInvoiceFilePanelCollapsed' in APP_JS
    assert 'syncInvoiceFilePanel(rejected, duplicates)' in APP_JS


def test_xml_filter_contains_aggregate_non_ok_and_dynamic_statuses():
    assert 'value="__not_ok__">Não OK / requer atenção' in INDEX
    assert 'value="__ok__">Somente OK' in INDEX
    assert 'value="__authorization_pending__">Aguardando autorização' in INDEX
    assert 'function refreshXmlStatusFilterOptions' in APP_JS
    assert 'Status encontrados neste lote' in APP_JS
    assert 'selectedStatus === "__not_ok__"' in APP_JS
    assert 'statusMatches = !isXmlOk(row)' in APP_JS


def test_compact_block_shows_authorization_status_and_justification_together():
    assert 'compact-authorization-summary' in APP_JS
    assert '<small>Status da autorização</small>' in APP_JS
    assert 'id="compact-authorization-justification"' in APP_JS
    assert 'Sem justificativa registrada.' in APP_JS
    assert 'xml-manual-reason' in APP_JS
    assert 'compact-authorization-summary' in STYLES


def test_duplicate_xml_detection_by_hash_and_fiscal_identity(tmp_path: Path):
    server = load_server_module()
    original = sample_cte()
    path = tmp_path / "original.xml"
    path.write_bytes(original)

    same_hash = server.find_duplicate_xml(tmp_path, original, hashlib.sha256(original).hexdigest())
    assert same_hash
    assert same_hash["file"] == "original.xml"
    assert same_hash["match"] == "sha256"

    reformatted = sample_cte().replace(b"><", b">\n<")
    same_identity = server.find_duplicate_xml(tmp_path, reformatted, hashlib.sha256(reformatted).hexdigest())
    assert same_identity
    assert same_identity["file"] == "original.xml"
    assert same_identity["match"] == "fiscal_identity"
    assert same_identity["identity"] == "15260759339996000107570100000207021001267563"


def test_upload_route_blocks_duplicate_before_destination_write():
    block = SERVER_TEXT[SERVER_TEXT.index('if parsed.path == "/api/upload"'):SERVER_TEXT.index('if parsed.path == "/api/qa"')]
    assert 'find_duplicate_xml' in block
    assert 'code="DUPLICATE_XML"' in block
    assert 'upload.duplicate_blocked' in block
    assert block.index('find_duplicate_xml') < block.index('destination.write_bytes(body)')
    assert 'XML duplicado bloqueado' in APP_JS
