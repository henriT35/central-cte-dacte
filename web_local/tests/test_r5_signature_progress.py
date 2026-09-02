# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_signature_progress_interface_contract():
    html = (ROOT / "web_local" / "static" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web_local" / "static" / "styles.css").read_text(encoding="utf-8")
    js = (ROOT / "web_local" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'id="signature-generation-progress"' in html
    assert 'id="signature-progress-bar"' in html
    assert 'id="signature-progress-count"' in html
    assert ".signature-generation-progress" in css
    assert 'api("/api/signatures/generate-job"' in js
    assert 'api(`/api/jobs/${encodeURIComponent(job.id)}`' in js
    assert "renderSignatureGenerationProgress" in js


def test_signature_progress_server_contract():
    server = (ROOT / "web_local" / "server.py").read_text(encoding="utf-8")
    service = (ROOT / "web_local" / "services" / "official_signature_service.py").read_text(encoding="utf-8")

    assert '"signature": {}' in server
    assert 'def start_signature_job(' in server
    assert 'if parsed.path == "/api/signatures/generate-job"' in server
    assert 'if path == "/api/process/signatures/status"' in server
    assert "progress: Callable[[float, int, int, str, str], None] | None" in service
    assert 'f"Gerando PDF assinado {position} de {total}."' in service
