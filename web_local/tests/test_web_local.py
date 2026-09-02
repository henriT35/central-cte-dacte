# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import json
from io import BytesIO
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("central_cte_web_server", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(server)


def xlsx_sheet_names(path: Path) -> list[str]:
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(path, "r") as archive:
        self_test = archive.testzip()
        if self_test is not None:
            raise AssertionError(f"Entrada XLSX inválida: {self_test}")
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    sheets = root.find(f"{{{namespace}}}sheets")
    if sheets is None:
        return []
    return [item.attrib.get("name", "") for item in list(sheets)]


class WebLocalTests(unittest.TestCase):
    def test_safe_filename_removes_path(self):
        self.assertEqual(server.safe_filename(r"..\pasta\arquivo.xml"), "arquivo.xml")
        self.assertEqual(server.safe_filename("arquivo<>.xml"), "arquivo_.xml")

    def test_upload_extension_contract(self):
        self.assertEqual(server.validate_upload_filename("xml", "arquivo.XML"), "arquivo.XML")
        self.assertEqual(server.validate_upload_filename("faturas", "fatura.pdf"), "fatura.pdf")
        self.assertEqual(server.validate_upload_filename("bases", "base.sswweb"), "base.sswweb")
        self.assertEqual(server.validate_upload_filename("tabelas", "parceiros.xlsx"), "parceiros.xlsx")
        with self.assertRaises(ValueError):
            server.validate_upload_filename("faturas", "fatura.exe")
        with self.assertRaises(ValueError):
            server.validate_upload_filename("xml", "sem_extensao")

    def test_parse_cte_xml_preserves_missing_commercial_values(self):
        content = """<?xml version='1.0' encoding='UTF-8'?>
        <cteProc xmlns='http://www.portalfiscal.inf.br/cte'>
          <CTe><infCte Id='CTe35260100000000000123570010000005798820000001'>
            <ide><nCT>579882</nCT><serie>1</serie><tpCTe>0</tpCTe><dhEmi>2026-07-26T10:00:00-03:00</dhEmi><xMunIni>Belém</xMunIni><UFIni>PA</UFIni><xMunFim>Ananindeua</xMunFim><UFFim>PA</UFFim></ide>
            <emit><xNome>JSP TRANSPORTES</xNome></emit>
            <dest><xNome>DESTINATÁRIO TESTE</xNome></dest>
            <vPrest><vTPrest>149.69</vTPrest></vPrest>
            <infCTeNorm><infDoc><infNFe><chave>35260100000000000123550010000012341000012345</chave></infNFe></infDoc></infCTeNorm>
          </infCte></CTe>
        </cteProc>"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cte.xml"
            path.write_text(content, encoding="utf-8")
            row = server.parse_xml_document(path)
        self.assertEqual(row["cte"], "579882")
        self.assertEqual(row["partner"], "JSP TRANSPORTES")
        self.assertAlmostEqual(row["xml_value"], 149.69)
        self.assertIsNone(row["expected_value"])
        self.assertIsNone(row["difference"])
        self.assertEqual(row["status"], "Aguardando motor")

    def test_invalid_xml_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.xml"
            path.write_text("<cte>", encoding="utf-8")
            row = server.parse_xml_document(path)
        self.assertEqual(row["document_type"], "XML inválido")
        self.assertEqual(row["status"], "Erro de leitura")
        self.assertTrue(row["error"])

    def test_partner_table_reader_reads_official_file(self):
        data = server.scan_partners()
        self.assertFalse(data["error"], data["error"])
        self.assertGreater(len(data["partners"]), 0)
        self.assertGreater(len(data["rules"]), 0)

    def test_bootstrap_contract(self):
        payload = server.build_bootstrap()
        for key in ("app", "engine", "xmls", "invoices", "partners", "partner_rules", "reports", "signatures", "settings", "qa"):
            self.assertIn(key, payload)
        self.assertTrue(payload["engine"]["connected"])
        self.assertTrue(payload["engine"]["xml_service_connected"])
        self.assertTrue(payload["engine"]["invoice_service_connected"])
        self.assertTrue(payload["engine"]["report_service_connected"])
        self.assertTrue(payload["engine"]["dacte_service_connected"])
        self.assertTrue(payload["engine"]["signature_editor_connected"])
        self.assertTrue(payload["engine"]["report_service_connected"])
        self.assertTrue(payload["engine"]["ui_is_passive"])

    def test_official_invoice_service_contract_without_ui(self):
        from services import OfficialInvoiceEngineService

        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            upload_root = temp / "uploads"
            state_root = temp / "state"
            (upload_root / "bases").mkdir(parents=True)
            service = OfficialInvoiceEngineService(server.PROJECT_ROOT, upload_root, state_root)
            result = service._contract_self_test()

        self.assertTrue(result["passed"])
        self.assertEqual(result["invoice_count"], 1)
        self.assertEqual(result["item_count"], 2)
        self.assertAlmostEqual(result["total_value"], 150.0)
        self.assertAlmostEqual(result["payable_value"], 100.0)
        self.assertAlmostEqual(result["blocked_value"], 50.0)
        self.assertEqual(result["decision_codes"].get("OK"), 1)
        self.assertEqual(result["decision_codes"].get("SEM_COMPROVANTE"), 1)

    def test_official_invoice_service_links_real_pdf_text_to_official_base(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab não está disponível para gerar o PDF de integração")

        from services import OfficialInvoiceEngineService

        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            upload_root = temp / "uploads"
            state_root = temp / "state"
            (upload_root / "bases").mkdir(parents=True)
            pdf_path = temp / "Fatura_0000336-0.pdf"
            document = canvas.Canvas(str(pdf_path))
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

            service = OfficialInvoiceEngineService(server.PROJECT_ROOT, upload_root, state_root)
            summary = service.process([pdf_path])
            rows = service.stored_rows([pdf_path])
            from services import OfficialReportService, OfficialXmlEngineService
            report_service = OfficialReportService(
                server.PROJECT_ROOT,
                upload_root,
                temp / "outputs",
                state_root,
                OfficialXmlEngineService(server.PROJECT_ROOT, upload_root, state_root),
                service,
            )
            report = report_service.generate_invoices([pdf_path])
            report_path = Path(report["path"])
            report_sheets = xlsx_sheet_names(report_path)

        self.assertEqual(summary["documents"], 1)
        self.assertEqual(summary["items"], 1)
        self.assertEqual(summary["invoices"], 1)
        self.assertAlmostEqual(summary["total_value"], 76.07)
        self.assertAlmostEqual(summary["payable_value"], 76.07)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payment_status"], "OK PAGAR")
        self.assertEqual(rows[0]["details"][0]["proof_status"], "S")
        self.assertEqual(rows[0]["details"][0]["link_mode"], "FATURA_EN_ER")
        self.assertEqual(report_sheets, ["PAINEL", "FATURAS", "ATENÇÃO", "CT_ES", "AUDITORIA_TÉCNICA"])
        self.assertAlmostEqual(report["total_value"], 76.07)
        self.assertAlmostEqual(report["payable_value"], 76.07)

    def test_official_xml_service_processes_sentinel_without_ui(self):
        from services import OfficialXmlEngineService

        content = """<?xml version='1.0' encoding='UTF-8'?>
        <cteProc xmlns='http://www.portalfiscal.inf.br/cte'><CTe>
          <infCte Id='CTe42260614498358000109570020005798821000000001'>
            <ide><nCT>579882</nCT><serie>2</serie><mod>57</mod><dhEmi>2026-06-10T10:00:00-03:00</dhEmi><tpCTe>0</tpCTe><tpServ>0</tpServ><modal>01</modal><xMunIni>GARUVA</xMunIni><UFIni>SC</UFIni><cMunIni>4205803</cMunIni><xMunFim>PARAUAPEBAS</xMunFim><UFFim>PA</UFFim><cMunFim>1505536</cMunFim></ide>
            <emit><CNPJ>14498358000109</CNPJ><xNome>JSP TRANSPORTE E LOGISTICA LTDA</xNome><enderEmit><xMun>GARUVA</xMun><UF>SC</UF></enderEmit></emit>
            <dest><CNPJ>00000000000100</CNPJ><xNome>DESTINATARIO TESTE</xNome><enderDest><xMun>PARAUAPEBAS</xMun><UF>PA</UF></enderDest></dest>
            <vPrest><vTPrest>149.69</vTPrest><vRec>149.69</vRec><Comp><xNome>FRETE VALOR</xNome><vComp>149.69</vComp></Comp></vPrest>
            <infCTeNorm><infCarga><vCarga>12268.80</vCarga><proPred>CARGA TESTE</proPred></infCarga><infDoc><infNF><mod>01</mod><serie>1</serie><nDoc>283763</nDoc><dEmi>2026-06-09</dEmi><vBC>0</vBC><vICMS>0</vICMS><vBCST>0</vBCST><vST>0</vST><vProd>12268.80</vProd><vNF>12268.80</vNF><nCFOP>5102</nCFOP><nPeso>1</nPeso></infNF></infDoc><infModal versaoModal='4.00'><rodo><RNTRC>12345678</RNTRC></rodo></infModal></infCTeNorm>
          </infCte>
        </CTe></cteProc>"""
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            upload_root = temp / "uploads"
            state_root = temp / "state"
            xml_dir = upload_root / "xml"
            (upload_root / "bases").mkdir(parents=True)
            (upload_root / "tabelas").mkdir(parents=True)
            xml_dir.mkdir(parents=True)
            xml_path = xml_dir / "sentinela_579882.xml"
            xml_path.write_text(content, encoding="utf-8")
            service = OfficialXmlEngineService(server.PROJECT_ROOT, upload_root, state_root)
            summary = service.process([xml_path])
            row = service.stored_row(xml_path)
            from services import OfficialInvoiceEngineService, OfficialReportService
            report_service = OfficialReportService(
                server.PROJECT_ROOT,
                upload_root,
                temp / "outputs",
                state_root,
                service,
                OfficialInvoiceEngineService(server.PROJECT_ROOT, upload_root, state_root),
            )
            report = report_service.generate_xml([xml_path])
            report_sheets = xlsx_sheet_names(Path(report["path"]))

        self.assertTrue(summary["self_test"]["passed"])
        self.assertEqual(summary["processed"], 1)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "DIVERGENTE +")
        self.assertAlmostEqual(row["expected_value"], 147.45)
        self.assertAlmostEqual(row["difference"], 2.24)
        self.assertAlmostEqual(row["percentage"], 25.0)
        self.assertIn("CONTROLE INTERNO - JSP", row["compact_calculation"])
        self.assertEqual(report_sheets, ["PAINEL", "ATENÇÃO", "DETALHAMENTO", "AUDITORIA_TÉCNICA"])
        self.assertEqual(report["documents"], 1)
        self.assertAlmostEqual(report["metrics"]["total_expected"], 147.45)


    def test_official_dacte_service_generates_preview_batch_and_individual_zip(self):
        from services import OfficialDacteService, OfficialXmlEngineService

        content = """<?xml version='1.0' encoding='UTF-8'?>
        <cteProc xmlns='http://www.portalfiscal.inf.br/cte'><CTe>
          <infCte Id='CTe42260614498358000109570020005798821000000001'>
            <ide><nCT>579882</nCT><serie>2</serie><mod>57</mod><dhEmi>2026-06-10T10:00:00-03:00</dhEmi><tpCTe>0</tpCTe><tpServ>0</tpServ><modal>01</modal><xMunIni>GARUVA</xMunIni><UFIni>SC</UFIni><cMunIni>4205803</cMunIni><xMunFim>PARAUAPEBAS</xMunFim><UFFim>PA</UFFim><cMunFim>1505536</cMunFim></ide>
            <emit><CNPJ>14498358000109</CNPJ><xNome>JSP TRANSPORTE E LOGISTICA LTDA</xNome><enderEmit><xMun>GARUVA</xMun><UF>SC</UF></enderEmit></emit>
            <rem><CNPJ>00000000000200</CNPJ><xNome>REMETENTE TESTE</xNome><enderReme><xMun>GARUVA</xMun><UF>SC</UF></enderReme></rem>
            <dest><CNPJ>00000000000100</CNPJ><xNome>DESTINATARIO TESTE</xNome><enderDest><xMun>PARAUAPEBAS</xMun><UF>PA</UF></enderDest></dest>
            <vPrest><vTPrest>149.69</vTPrest><vRec>149.69</vRec><Comp><xNome>FRETE VALOR</xNome><vComp>149.69</vComp></Comp></vPrest>
            <infCTeNorm><infCarga><vCarga>12268.80</vCarga><proPred>CARGA TESTE</proPred></infCarga><infDoc><infNF><mod>01</mod><serie>1</serie><nDoc>283763</nDoc><dEmi>2026-06-09</dEmi><vBC>0</vBC><vICMS>0</vICMS><vBCST>0</vBCST><vST>0</vST><vProd>12268.80</vProd><vNF>12268.80</vNF><nCFOP>5102</nCFOP><nPeso>1</nPeso></infNF></infDoc><infModal versaoModal='4.00'><rodo><RNTRC>12345678</RNTRC></rodo></infModal></infCTeNorm>
          </infCte>
        </CTe></cteProc>"""
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            upload_root = temp / "uploads"
            state_root = temp / "state"
            xml_dir = upload_root / "xml"
            xml_dir.mkdir(parents=True)
            xml_path = xml_dir / "sentinela_579882.xml"
            xml_path.write_text(content, encoding="utf-8")
            xml_service = OfficialXmlEngineService(server.PROJECT_ROOT, upload_root, state_root)
            xml_service.process([xml_path])
            dacte_service = OfficialDacteService(
                server.PROJECT_ROOT, temp / "outputs", state_root, xml_service,
            )
            preview = dacte_service.preview(xml_path, [xml_path])
            batch = dacte_service.generate([xml_path], [xml_path], mode="batch")
            individuals = dacte_service.generate([xml_path], [xml_path], mode="individuals")
            with zipfile.ZipFile(individuals["path"], "r") as archive:
                individual_names = archive.namelist()

        self.assertEqual(preview["cte"], "579882")
        self.assertGreaterEqual(preview["pages"], 1)
        self.assertTrue(preview["renderer"].startswith("HTML oficial RC26.6"))
        self.assertEqual(batch["documents"], 1)
        self.assertGreaterEqual(batch["pages"], 1)
        self.assertEqual(individuals["documents"], 1)
        self.assertEqual(len(individual_names), 1)
        self.assertTrue(individual_names[0].lower().endswith(".pdf"))


    def test_signature_service_creates_profile_and_signed_dacte_without_ui(self):
        import base64
        import binascii
        import struct
        import zlib
        from services import OfficialDacteService, OfficialSignatureService, OfficialXmlEngineService

        content = """<?xml version='1.0' encoding='UTF-8'?>
        <cteProc xmlns='http://www.portalfiscal.inf.br/cte'><CTe>
          <infCte Id='CTe42260614498358000109570020005798821000000001'>
            <ide><nCT>579882</nCT><serie>2</serie><mod>57</mod><dhEmi>2026-06-10T10:00:00-03:00</dhEmi><tpCTe>0</tpCTe><tpServ>0</tpServ><modal>01</modal><xMunIni>GARUVA</xMunIni><UFIni>SC</UFIni><cMunIni>4205803</cMunIni><xMunFim>PARAUAPEBAS</xMunFim><UFFim>PA</UFFim><cMunFim>1505536</cMunFim></ide>
            <emit><CNPJ>14498358000109</CNPJ><xNome>JSP TRANSPORTE E LOGISTICA LTDA</xNome><enderEmit><xMun>GARUVA</xMun><UF>SC</UF></enderEmit></emit>
            <rem><CNPJ>00000000000200</CNPJ><xNome>REMETENTE TESTE</xNome><enderReme><xMun>GARUVA</xMun><UF>SC</UF></enderReme></rem>
            <dest><CNPJ>00000000000100</CNPJ><xNome>DESTINATARIO TESTE</xNome><enderDest><xMun>PARAUAPEBAS</xMun><UF>PA</UF></enderDest></dest>
            <vPrest><vTPrest>149.69</vTPrest><vRec>149.69</vRec><Comp><xNome>FRETE VALOR</xNome><vComp>149.69</vComp></Comp></vPrest>
            <infCTeNorm><infCarga><vCarga>12268.80</vCarga><proPred>CARGA TESTE</proPred></infCarga><infDoc><infNF><mod>01</mod><serie>1</serie><nDoc>283763</nDoc><dEmi>2026-06-09</dEmi><vBC>0</vBC><vICMS>0</vICMS><vBCST>0</vBCST><vST>0</vST><vProd>12268.80</vProd><vNF>12268.80</vNF><nCFOP>5102</nCFOP><nPeso>1</nPeso></infNF></infDoc><infModal versaoModal='4.00'><rodo><RNTRC>12345678</RNTRC></rodo></infModal></infCTeNorm>
          </infCte>
        </CTe></cteProc>"""

        def png_chunk(name, payload):
            return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", binascii.crc32(name + payload) & 0xFFFFFFFF)

        width, height = 180, 70
        rows = []
        for y in range(height):
            row = bytearray([0])
            for x in range(width):
                line_y = 35 + int(12 * __import__("math").sin(x / 17.0))
                alpha = 255 if abs(y - line_y) <= 2 and 12 < x < 168 else 0
                row.extend((20, 35, 90, alpha))
            rows.append(bytes(row))
        png = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + png_chunk(b"IEND", b"")
        )
        data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            upload_root = temp / "uploads"
            state_root = temp / "state"
            data_root = temp / "data"
            xml_dir = upload_root / "xml"
            xml_dir.mkdir(parents=True)
            xml_path = xml_dir / "sentinela_579882.xml"
            xml_path.write_text(content, encoding="utf-8")
            xml_service = OfficialXmlEngineService(server.PROJECT_ROOT, upload_root, state_root)
            xml_service.process([xml_path])
            dacte_service = OfficialDacteService(server.PROJECT_ROOT, temp / "outputs", state_root, xml_service)
            signature_service = OfficialSignatureService(server.PROJECT_ROOT, data_root, state_root, xml_service, dacte_service)
            profile = signature_service.create_profile({
                "name": "Expedição",
                "person_name": "Responsável Teste",
                "role": "Conferência",
                "title": "REDESPACHO",
            })
            imported = signature_service.import_browser_processed({
                "profile_id": profile["id"],
                "original_name": "assinatura.png",
                "original_data_url": data_url,
                "processed_data_url": data_url,
                "threshold": 242,
            })
            updated = signature_service.update_profile(profile["id"], {
                "custom_x_mm": 116.5,
                "custom_y_mm": 256.5,
                "custom_width_mm": 84.0,
                "custom_rotation_deg": 0,
                "signature_scale_percent": 112,
                "signature_offset_x_mm": 1.5,
                "signature_offset_y_mm": -1.0,
            })
            preview = signature_service.preview(xml_path, [xml_path], profile["id"], "26/07/2026")
            batch = signature_service.generate([xml_path], [xml_path], profile["id"], "26/07/2026", mode="batch")
            individuals = signature_service.generate([xml_path], [xml_path], profile["id"], "26/07/2026", mode="individuals")
            with zipfile.ZipFile(individuals["path"], "r") as archive:
                names = archive.namelist()

        self.assertTrue(imported["profile"]["ready"])
        self.assertEqual(imported["processing"]["backend"], "Canvas do navegador")
        self.assertEqual(updated["position"], "custom")
        self.assertAlmostEqual(updated["custom_width_mm"], 84.0)
        self.assertEqual(preview["operation"], "signed-preview")
        self.assertEqual(preview["profile_name"], "Expedição")
        self.assertGreaterEqual(preview["pages"], 1)
        self.assertEqual(batch["operation"], "signed-batch")
        self.assertEqual(batch["documents"], 1)
        self.assertTrue(batch["visual_signature_only"])
        self.assertEqual(individuals["documents"], 1)
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].lower().endswith(".pdf"))


    def test_security_password_session_and_roles(self):
        from security import AuthManager

        with tempfile.TemporaryDirectory() as tmp:
            manager = AuthManager(Path(tmp) / "security")
            self.assertTrue(manager.setup_required())
            admin = manager.setup_admin("admin.teste", "Administrador Teste", "SenhaSegura123")
            self.assertEqual(admin.role, "admin")
            self.assertFalse(manager.setup_required())
            authenticated = manager.authenticate("admin.teste", "SenhaSegura123", remote_key="127.0.0.1")
            self.assertIsNotNone(authenticated)
            self.assertIsNone(manager.authenticate("admin.teste", "senha-incorreta", remote_key="127.0.0.2"))
            operator = manager.create_user("operador.01", "Operador Um", "operador", "Operador1234", actor=admin)
            self.assertEqual(operator.role, "operador")
            token, session = manager.create_session(operator)
            self.assertTrue(token)
            self.assertTrue(manager.verify_csrf(session, session["csrf"]))
            self.assertFalse(manager.verify_csrf(session, "invalido"))
            self.assertEqual(manager.get_session(token)["user"].id, operator.id)
            manager.destroy_session(token)
            self.assertIsNone(manager.get_session(token))

    def test_upload_content_validation_rejects_disguised_files(self):
        valid_xml = b"<?xml version='1.0'?><root><item>ok</item></root>"
        server.validate_upload_content("xml", valid_xml)
        with self.assertRaises(ValueError):
            server.validate_upload_content("xml", b"<root>")
        with self.assertRaises(ValueError):
            server.validate_upload_content("faturas", b"nao e pdf")
        server.validate_upload_content("faturas", b"%PDF-1.4\nobj\n%%EOF")

        official_xlsx = server.PROJECT_ROOT / "tabelas" / "cadastro_tabelas_parceiros.xlsx"
        server.validate_upload_content("tabelas", official_xlsx.read_bytes())
        with self.assertRaises(ValueError):
            server.validate_upload_content("tabelas", b"PK\x03\x04arquivo falso")

        official_base = next((server.PROJECT_ROOT / "bases").glob("*.sswweb"))
        server.validate_upload_content("bases", official_base.read_bytes())
        with self.assertRaises(ValueError):
            server.validate_upload_content("bases", b"MZ" + b"x" * 100)

    def test_workspaces_are_isolated_and_backup_is_integral(self):
        from security import AuthenticatedUser

        original_root = server.WORKSPACES_ROOT
        original_backup = server.BACKUP_ROOT
        original_cache = server.WORKSPACE_CACHE
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            try:
                server.WORKSPACES_ROOT = temp / "workspaces"
                server.BACKUP_ROOT = temp / "backups"
                server.WORKSPACE_CACHE = {}
                first = server.get_workspace("usuario-a")
                second = server.get_workspace("usuario-b")
                xml = first.upload_categories["xml"] / "privado.xml"
                xml.write_text("<?xml version='1.0'?><root/>", encoding="utf-8")
                self.assertTrue(any(row["file"] == "privado.xml" for row in server.scan_xmls(first)))
                self.assertFalse(any(row["file"] == "privado.xml" for row in server.scan_xmls(second)))

                user = AuthenticatedUser(id="usuario-a", username="usuario.a", display_name="Usuário A", role="admin")
                backup = server.create_workspace_backup(first, user)
                backup_path = Path(backup["path"])
                self.assertTrue(backup_path.is_file())
                with zipfile.ZipFile(backup_path, "r") as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertIn("workspace/uploads/xml/privado.xml", archive.namelist())
                    self.assertIn("backup_manifest.json", archive.namelist())
            finally:
                server.WORKSPACES_ROOT = original_root
                server.BACKUP_ROOT = original_backup
                server.WORKSPACE_CACHE = original_cache


    def test_clear_xml_workspace_removes_lot_and_preserves_reports_and_bases(self):
        original_root = server.WORKSPACES_ROOT
        original_backup = server.BACKUP_ROOT
        original_cache = server.WORKSPACE_CACHE
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            try:
                server.WORKSPACES_ROOT = temp / "workspaces"
                server.BACKUP_ROOT = temp / "backups"
                server.WORKSPACE_CACHE = {}
                context = server.get_workspace("clear-user")
                xml_path = context.upload_categories["xml"] / "lote.xml"
                xml_path.write_text("<?xml version='1.0'?><root/>", encoding="utf-8")
                base_path = context.upload_categories["bases"] / "base.sswweb"
                base_path.write_text("base preservada", encoding="utf-8")
                report_path = context.output_root / "relatorios" / "relatorio.xlsx"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_bytes(b"relatorio preservado")
                context.xml_service.results_path.parent.mkdir(parents=True, exist_ok=True)
                context.xml_service.results_path.write_text('{"documents": []}', encoding="utf-8")
                context.xml_service.last_run_path.write_text('{"status": "completed"}', encoding="utf-8")
                preview = context.dacte_service.preview_root / "preview.pdf"
                preview.parent.mkdir(parents=True, exist_ok=True)
                preview.write_bytes(b"%PDF-1.4\n%%EOF")

                result = server.clear_xml_workspace(context)

                self.assertEqual(result["deleted_xml_count"], 1)
                self.assertFalse(xml_path.exists())
                self.assertFalse(context.xml_service.results_path.exists())
                self.assertFalse(context.xml_service.last_run_path.exists())
                self.assertFalse(preview.exists())
                self.assertTrue(base_path.is_file())
                self.assertTrue(report_path.is_file())
                self.assertTrue(result["reports_preserved"])
                self.assertTrue(result["bases_preserved"])
            finally:
                server.WORKSPACES_ROOT = original_root
                server.BACKUP_ROOT = original_backup
                server.WORKSPACE_CACHE = original_cache

    def test_signature_pdf_import_extracts_embedded_image(self):
        try:
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab não está disponível para gerar o PDF de integração")

        import binascii
        import struct
        import zlib
        from services import OfficialSignatureService

        def png_chunk(name, payload):
            return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", binascii.crc32(name + payload) & 0xFFFFFFFF)

        width, height = 160, 60
        rows = []
        for y in range(height):
            row = bytearray([0])
            for x in range(width):
                dark = abs(y - (30 + int(8 * __import__("math").sin(x / 15.0)))) <= 2
                row.extend((15, 25, 70, 255 if dark else 0))
            rows.append(bytes(row))
        png = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + png_chunk(b"IEND", b"")
        )

        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            pdf_path = temp / "folha_assinada.pdf"
            document = canvas.Canvas(str(pdf_path))
            document.drawString(72, 790, "Folha de assinatura")
            document.drawImage(ImageReader(BytesIO(png)), 72, 680, width=240, height=90, mask="auto")
            document.save()
            service = OfficialSignatureService(server.PROJECT_ROOT, temp / "data", temp / "state", None, None)
            result = service.extract_pdf_images(pdf_path.read_bytes(), pdf_path.name)

        self.assertEqual(result["pages"], 1)
        self.assertGreaterEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertTrue(candidate["mime"].startswith("image/"))
        self.assertTrue(candidate["data_url"].startswith("data:image/"))
        self.assertGreater(candidate["size_bytes"], 20)

    def test_mvp9_interface_contains_clear_pdf_import_and_preview_controls(self):
        index = (server.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        app = (server.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        for identifier in (
            'id="clear-xml-list"',
            'id="signature-pdf-candidates"',
            'id="dacte-preview-toolbar"',
            'id="dacte-preview-zoom"',
            'id="fullscreen-dacte-preview"',
        ):
            self.assertIn(identifier, index)
        self.assertIn('/api/xml/clear', app)
        self.assertIn('/api/signatures/pdf-images', app)
        self.assertIn('toggleDactePreviewFullscreen', app)

    def test_clear_invoice_workspace_removes_lot_and_preserves_reports_and_bases(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_root = server.WORKSPACES_ROOT
            original_backup = server.BACKUP_ROOT
            original_cache = server.WORKSPACE_CACHE
            try:
                server.WORKSPACES_ROOT = Path(tmp) / "workspaces"
                server.BACKUP_ROOT = Path(tmp) / "backups"
                server.WORKSPACE_CACHE = {}
                context = server.get_workspace("invoice-clear")
                pdf = context.upload_categories["faturas"] / "fatura.pdf"
                pdf.write_bytes(b"%PDF-1.4\n%%EOF")
                base_path = context.upload_categories["bases"] / "base.sswweb"
                base_path.write_text("base preservada", encoding="utf-8")
                report_path = context.output_root / "relatorios" / "financeiro.xlsx"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_bytes(b"relatorio preservado")
                context.invoice_service.results_path.write_text('{"invoices": []}', encoding="utf-8")
                context.invoice_service.last_run_path.write_text('{"status": "concluido"}', encoding="utf-8")

                result = server.clear_invoice_workspace(context)

                self.assertEqual(result["deleted_invoice_count"], 1)
                self.assertFalse(pdf.exists())
                self.assertFalse(context.invoice_service.results_path.exists())
                self.assertFalse(context.invoice_service.last_run_path.exists())
                self.assertTrue(base_path.is_file())
                self.assertTrue(report_path.is_file())
                self.assertTrue(result["reports_preserved"])
                self.assertTrue(result["bases_preserved"])
            finally:
                server.WORKSPACES_ROOT = original_root
                server.BACKUP_ROOT = original_backup
                server.WORKSPACE_CACHE = original_cache

    def test_complementary_information_is_scoped_and_injected_into_official_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            xml_path = temp / "cte.xml"
            xml_path.write_text("<cteProc><CTe><infCte Id='CTe12345678901234567890123456789012345678901234'><ide><nCT>123</nCT><serie>1</serie></ide></infCte></CTe></cteProc>", encoding="utf-8")

            class XmlStub:
                def stored_row(self, path):
                    return {
                        "engine_info": {"tipo": "CT-E", "numero": "123", "serie": "1", "chave": "12345678901234567890123456789012345678901234"},
                        "validation": {"status": "OK"},
                    }

            from services.official_dacte_service import OfficialDacteService, COMPLEMENTARY_INFO_KEY
            service = OfficialDacteService(server.PROJECT_ROOT, temp / "outputs", temp / "state", XmlStub())
            applied = service.apply_complementary_information([xml_path], [xml_path], "  Observação de entrega.  ")
            self.assertEqual(applied["documents"], 1)
            self.assertFalse(applied["xml_fiscal_modified"])
            self.assertEqual(service.complementary_information(xml_path), "Observação de entrega.")
            infos = service._official_infos([xml_path])
            self.assertEqual(infos[0][COMPLEMENTARY_INFO_KEY], "Observação de entrega.")
            removed = service.remove_complementary_information([xml_path], [xml_path])
            self.assertGreaterEqual(removed["removed_identities"], 1)
            self.assertEqual(service.complementary_information(xml_path), "")

    def test_mvp11_interface_contains_invoice_clear_and_complementary_information(self):
        index = (server.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        app = (server.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        for identifier in (
            'id="clear-invoice-list"',
            'id="add-complementary-info"',
            'id="complementary-modal"',
            'id="complementary-text"',
        ):
            self.assertIn(identifier, index)
        self.assertIn('/api/invoices/clear', app)
        self.assertIn('/api/xml/complementary', app)
        self.assertIn('clearInvoiceList', app)
        self.assertIn('saveComplementaryInformation', app)

    def test_health_contract_reports_writable_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_root = server.WORKSPACES_ROOT
            original_cache = server.WORKSPACE_CACHE
            try:
                server.WORKSPACES_ROOT = Path(tmp) / "workspaces"
                server.WORKSPACE_CACHE = {}
                context = server.get_workspace("health-user")
                health = server.workspace_health(context)
                self.assertEqual(health["status"], "ok")
                self.assertGreater(health["disk"]["free_bytes"], 0)
                self.assertTrue(all(item["writable"] for item in health["directories"].values()))
                self.assertIn("xml", health["services"])
                self.assertIn("signatures", health["services"])
            finally:
                server.WORKSPACES_ROOT = original_root
                server.WORKSPACE_CACHE = original_cache


    def test_security_session_persists_after_manager_restart(self):
        from security import AuthManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "security"
            first = AuthManager(root)
            admin = first.setup_admin("admin.persistente", "Admin Persistente", "SenhaPersistente123")
            token, session = first.create_session(admin)
            second = AuthManager(root)
            restored = second.get_session(token)
            self.assertIsNotNone(restored)
            self.assertEqual(restored["user"].id, admin.id)
            self.assertTrue(second.verify_csrf(restored, session["csrf"]))
            second.revoke_user_sessions(admin.id)
            self.assertIsNone(first.get_session(token))

    def test_prometheus_metrics_and_readiness_contract(self):
        metrics = server.prometheus_metrics()
        self.assertIn("central_cte_uptime_seconds", metrics)
        self.assertIn("central_cte_requests_total", metrics)
        readiness = server.production_readiness()
        self.assertIn("ready", readiness)
        self.assertIn("checks", readiness)
        self.assertIn("engine", readiness["checks"])



if __name__ == "__main__":
    unittest.main()
