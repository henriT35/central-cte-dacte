from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from web_local import server
from web_local.developer_tools import DeveloperTools


class R10QaImagesProgressPartnersTests(unittest.TestCase):
    def test_ws_transportes_regions_are_visible_as_partner_rules(self):
        data = server.scan_partners(server.DEFAULT_WORKSPACE)
        partner_ids = {row.get("partner_id") for row in data.get("partners", [])}
        self.assertIn("W_S_TRANSPORTES", partner_ids)
        rules = [row for row in data.get("rules", []) if row.get("partner_id") == "W_S_TRANSPORTES"]
        self.assertGreater(len(rules), 20)
        self.assertTrue(any(row.get("source_sheet") == "REGIOES" for row in rules))
        self.assertTrue(any(row.get("destination", "").startswith("Ji-Paraná") for row in rules))

    def test_qa_bundle_contains_json_and_real_attachment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            security = root / "data" / "security"
            tools = DeveloperTools(root, security)
            qa_path = root / "data" / "qa" / "qa_notes.json"
            attachment = tools.qa_attachment_root / "ATT-abc123.png"
            attachment.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test-image")
            notes = [{
                "id": "QA-1",
                "title": "Com imagem",
                "attachment": {"id": "ATT-abc123", "name": "evidencia.png", "mime": "image/png"},
            }]
            qa_path.write_text(json.dumps(notes), encoding="utf-8")
            bundle = tools.export_qa_bundle(SimpleNamespace(qa_path=qa_path))
            with zipfile.ZipFile(bundle) as archive:
                self.assertIn("central_cte_qa.json", archive.namelist())
                self.assertIn("attachments/ATT-abc123.png", archive.namelist())
                exported = json.loads(archive.read("central_cte_qa.json"))
            self.assertEqual(exported[0]["attachment"]["export_path"], "attachments/ATT-abc123.png")
            self.assertTrue(exported[0]["attachment"]["included_in_export"])

    def test_clear_qa_also_clears_legacy_workspace_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            security = root / "data" / "security"
            tools = DeveloperTools(root, security)
            qa_path = root / "data" / "qa" / "qa_notes.json"
            qa_path.write_text(json.dumps([{"id": "QA-OLD"}]), encoding="utf-8")
            legacy = root / "data" / "workspaces" / "user1" / "state" / "qa_notes.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps([{"id": "QA-OLD"}]), encoding="utf-8")
            result = tools.clear_qa(SimpleNamespace(qa_path=qa_path))
            self.assertEqual(json.loads(qa_path.read_text(encoding="utf-8")), [])
            self.assertEqual(json.loads(legacy.read_text(encoding="utf-8")), [])
            self.assertEqual(result["legacy_rows_cleared"], 1)
            marker = json.loads((qa_path.parent / "last_clear.json").read_text(encoding="utf-8"))
            self.assertIn("QA-OLD", marker["deleted_ids"])

    def test_xml_task_progress_and_qa_zip_button_exist(self):
        html = (server.STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        js = (server.STATIC_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="xml-task-progress"', html)
        self.assertIn("Exportar ZIP com imagens", html)
        self.assertIn("updateXmlTaskProgress", js)
        self.assertIn("/api/developer/qa/export", js)


if __name__ == "__main__":
    unittest.main()
