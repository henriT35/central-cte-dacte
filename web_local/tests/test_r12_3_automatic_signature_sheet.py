# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from web_local.services.official_signature_service import OfficialSignatureService


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _registration_sheet(path: Path, *, signed: bool) -> None:
    document = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    document.setFont("Helvetica-Bold", 18)
    document.drawCentredString(width / 2, height - 70, "CADASTRO DE ASSINATURA - CENTRAL CT-e")
    document.setLineWidth(2)
    document.rect(70, 377, 455, 175)
    if signed:
        document.setStrokeColorRGB(0.04, 0.08, 0.45)
        document.setLineWidth(5)
        document.bezier(145, 420, 180, 515, 225, 405, 265, 490)
        document.bezier(265, 490, 310, 535, 335, 410, 405, 475)
    document.save()


def _service(root: Path) -> OfficialSignatureService:
    return OfficialSignatureService(PROJECT_ROOT, root / "data", root / "state", None, None)


def test_signed_registration_sheet_is_read_automatically() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = root / "folha_assinada.pdf"
        _registration_sheet(pdf, signed=True)
        result = _service(root).extract_pdf_images(pdf.read_bytes(), pdf.name)

    automatic = result.get("automatic_signature")
    assert result["automatic_read"] is True
    assert automatic
    assert automatic["source"] == "registration_sheet_auto"
    assert "quadro" in automatic["detection"].lower()
    assert automatic["processed_data_url"].startswith("data:image/png;base64,")
    assert len(base64.b64decode(automatic["processed_data_url"].split(",", 1)[1])) > 100
    assert result["candidates"] == []


def test_blank_registration_sheet_is_not_accepted_as_signature() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = root / "folha_em_branco.pdf"
        _registration_sheet(pdf, signed=False)
        result = _service(root).extract_pdf_images(pdf.read_bytes(), pdf.name)

    assert result["automatic_read"] is False
    assert result["automatic_signature"] is None
    assert result["candidates"]
    assert result["candidates"][0]["source"] == "rendered_page"


def test_vps_image_installs_poppler_fallback() -> None:
    dockerfile = (PROJECT_ROOT / "deploy" / "vps" / "Dockerfile").read_text(encoding="utf-8")
    image_processing = (PROJECT_ROOT / "engine" / "central_cte_modular" / "signing" / "image_processing.py").read_text(encoding="utf-8")
    app = (PROJECT_ROOT / "web_local" / "static" / "app.js").read_text(encoding="utf-8")

    assert "poppler-utils" in dockerfile
    assert 'shutil.which("pdftoppm")' in image_processing
    assert "Assinatura lida automaticamente" in app
    assert "automatic_signature" in app


def test_first_page_renderer_uses_poppler_when_python_pdf_backends_are_missing(monkeypatch) -> None:
    from engine.central_cte_modular.signing import image_processing

    real_import = image_processing.importlib.import_module

    def blocked_import(name: str, *args, **kwargs):
        if name in {"pypdfium2", "fitz"}:
            raise ImportError(f"{name} bloqueado no teste")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(image_processing.importlib, "import_module", blocked_import)
    monkeypatch.setattr(image_processing, "_qt_load_qimage", lambda _path: (_ for _ in ()).throw(RuntimeError("Qt bloqueado no teste")))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pdf = root / "pagina.pdf"
        _registration_sheet(pdf, signed=True)
        image = image_processing.render_pdf_first_page(pdf)

    assert image.width > 500
    assert image.height > 700
