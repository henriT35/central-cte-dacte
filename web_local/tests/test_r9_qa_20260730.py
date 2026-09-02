from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from web_local import server
from web_local.developer_tools import DeveloperTools
from web_local.services.official_dacte_service import OfficialDacteService


class R9Qa20260730Tests(unittest.TestCase):
    def test_security_and_user_management_are_developer_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = DeveloperTools(Path(tmp), Path(tmp) / "security")
            admin = SimpleNamespace(role="admin")
            developer = SimpleNamespace(role="desenvolvedor")
            admin_caps = tools.capabilities(admin)
            developer_caps = tools.capabilities(developer)
            self.assertFalse(admin_caps["can_manage_users"])
            self.assertFalse(admin_caps["can_view_security_readiness"])
            self.assertFalse(admin_caps["can_manage_backups"])
            self.assertTrue(developer_caps["can_manage_users"])
            self.assertTrue(developer_caps["can_view_security_readiness"])
            self.assertTrue(developer_caps["can_manage_backups"])

    def test_partner_percentage_accepts_excel_fraction_and_percent_text(self):
        self.assertEqual(server.percentage_number(0.25), 25.0)
        self.assertEqual(server.percentage_number("25%"), 25.0)
        self.assertEqual(server.percentage_number("12,5%"), 12.5)
        self.assertEqual(server.percentage_number("0,18"), 18.0)

    def test_compact_block_can_be_removed_without_changing_other_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml = root / "cte.xml"
            xml.write_text("<xml/>", encoding="utf-8")
            stored = {
                "engine_info": {"tipo": "CT-E", "numero": "123"},
                "validation": {
                    "controle_dacte_compacto": "bloco",
                    "controle_dacte_regra": "regra",
                    "status": "OK",
                    "valor_esperado": 100.0,
                },
            }
            service = OfficialDacteService(root, root / "out", root / "state", SimpleNamespace(stored_row=lambda _path: stored))
            info = service._official_infos([xml], include_compact=False)[0]
            self.assertNotIn("controle_dacte_compacto", info["validacao"])
            self.assertNotIn("controle_dacte_regra", info["validacao"])
            self.assertEqual(info["validacao"]["status"], "OK")
            self.assertEqual(info["validacao"]["valor_esperado"], 100.0)

    def test_qa_image_attachment_is_validated_and_saved(self):
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZlZsAAAAASUVORK5CYII=")
        with tempfile.TemporaryDirectory() as tmp:
            original = server.GLOBAL_QA_ATTACHMENT_ROOT
            try:
                server.GLOBAL_QA_ATTACHMENT_ROOT = Path(tmp)
                payload = {
                    "name": "evidencia.png",
                    "data_url": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
                }
                result = server.save_qa_attachment(payload, "QA-TESTE")
            finally:
                server.GLOBAL_QA_ATTACHMENT_ROOT = original
            self.assertEqual(result["name"], "evidencia.png")
            self.assertEqual(result["mime"], "image/png")
            self.assertTrue((Path(tmp) / f"{result['id']}.png").is_file())

    def test_frontend_contains_all_r9_contracts(self):
        root = Path(__file__).resolve().parents[2]
        html = (root / "web_local" / "static" / "index.html").read_text(encoding="utf-8")
        js = (root / "web_local" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('id="add-base"', html)
        self.assertNotIn('id="base-input"', html)
        self.assertIn('id="signature-filter"', html)
        self.assertIn('id="signature-include-compact"', html)
        self.assertIn('id="dacte-generation-progress"', html)
        self.assertIn('id="qa-attachment"', html)
        self.assertIn('data-audit-index', js)
        self.assertNotIn('data-source-index', js)
        self.assertIn('/api/dacte/generate-job', js)


if __name__ == "__main__":
    unittest.main()
