# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

WEB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WEB_ROOT.parent
SERVER_PATH = WEB_ROOT / "server.py"

spec = importlib.util.spec_from_file_location("central_cte_web_server_r12", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(server)


def xlsx_sheet_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path, "r") as archive:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [str(item.attrib.get("name") or "") for item in root.findall("main:sheets/main:sheet", namespace)]


class R12InvoiceReconciliationTests(unittest.TestCase):
    def _good_invoice_pdf(self, path: Path) -> None:
        try:
            from reportlab.pdfgen import canvas
        except ImportError as exc:  # pragma: no cover - ambiente sem reportlab
            self.skipTest(f"reportlab indisponível: {exc}")
        document = canvas.Canvas(str(path))
        lines = (
            "FATURA No: 0000336-0",
            "Transportador: JSP TRANSPORTE E LOGISTICA LTDA",
            "CT-e / RPS / NFS-e",
            "1 001000050465 01/01/26 000286327 1.000,00 10 0,00 76,07",
        )
        y = 800
        for line in lines:
            document.drawString(72, y, line)
            y -= 24
        document.save()

    def test_reconciles_every_pdf_and_exports_alert_sheet(self):
        from services import OfficialInvoiceEngineService, OfficialReportService, OfficialXmlEngineService

        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            upload_root = temp / "uploads"
            state_root = temp / "state"
            (upload_root / "bases").mkdir(parents=True)

            good = temp / "Fatura_0000336-0.pdf"
            duplicate = temp / "Fatura_0000336-0_copia.pdf"
            rejected = temp / "Fatura_corrompida.pdf"
            self._good_invoice_pdf(good)
            duplicate.write_bytes(good.read_bytes())
            rejected.write_bytes(b"%PDF-1.4\nconteudo quebrado")

            service = OfficialInvoiceEngineService(PROJECT_ROOT, upload_root, state_root)
            summary = service.process([good, duplicate, rejected])
            records = service.stored_file_records([good, duplicate, rejected])
            statuses = {record["file"]: record["status"] for record in records}

            report_service = OfficialReportService(
                PROJECT_ROOT,
                upload_root,
                temp / "outputs",
                state_root,
                OfficialXmlEngineService(PROJECT_ROOT, upload_root, state_root),
                service,
            )
            report = report_service.generate_invoices([good, duplicate, rejected])
            sheets = xlsx_sheet_names(Path(report["path"]))

        self.assertEqual(summary["uploaded_documents"], 3)
        self.assertEqual(summary["processed_files"], 1)
        self.assertEqual(summary["rejected_files"], 1)
        self.assertEqual(summary["duplicate_files"], 1)
        self.assertEqual(statuses[good.name], "processed")
        self.assertEqual(statuses[duplicate.name], "duplicate")
        self.assertEqual(statuses[rejected.name], "rejected")
        self.assertEqual(report["rejected_file_rows"], 2)
        self.assertIn("ARQUIVOS_REJEITADOS", sheets)

    def test_all_rejected_still_persists_name_reason_and_export(self):
        from services import OfficialInvoiceEngineService, OfficialReportService, OfficialXmlEngineService

        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            upload_root = temp / "uploads"
            state_root = temp / "state"
            (upload_root / "bases").mkdir(parents=True)
            rejected = temp / "nao_lida.pdf"
            rejected.write_bytes(b"%PDF-invalido")

            service = OfficialInvoiceEngineService(PROJECT_ROOT, upload_root, state_root)
            with self.assertRaises(RuntimeError):
                service.process([rejected])
            records = service.stored_file_records([rejected])
            summary = service.stored_summary([rejected])
            report_service = OfficialReportService(
                PROJECT_ROOT,
                upload_root,
                temp / "outputs",
                state_root,
                OfficialXmlEngineService(PROJECT_ROOT, upload_root, state_root),
                service,
            )
            report = report_service.generate_invoices([rejected])
            sheets = xlsx_sheet_names(Path(report["path"]))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["file"], rejected.name)
        self.assertEqual(records[0]["status"], "rejected")
        self.assertEqual(records[0]["code"], "PDF_READ_FAILED")
        self.assertTrue(records[0]["reason"])
        self.assertEqual(summary["uploaded_documents"], 1)
        self.assertEqual(summary["rejected_files"], 1)
        self.assertEqual(report["rejected_file_rows"], 1)
        self.assertEqual(sheets, ["ARQUIVOS_REJEITADOS"])

    def test_bootstrap_contract_includes_file_reconciliation(self):
        payload = server.build_bootstrap()
        self.assertIn("invoice_files", payload)
        self.assertIsInstance(payload["invoice_files"], list)


if __name__ == "__main__":
    unittest.main()
