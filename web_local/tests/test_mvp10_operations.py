# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("central_cte_web_server_mvp10", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(server)


class Mvp10OperationsTests(unittest.TestCase):
    def test_interrupted_job_is_marked_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = SimpleNamespace(user_id="recovery-test", state_root=Path(tmp))
            journal = context.state_root / "jobs_journal.json"
            journal.write_text(json.dumps({
                "jobs": [{
                    "id": "XML-INTERRUPTED",
                    "kind": "xml",
                    "workspace_id": context.user_id,
                    "state": "running",
                    "created_at": "2026-07-27T00:00:00-03:00",
                    "updated_at": "2026-07-27T00:01:00-03:00",
                }]
            }), encoding="utf-8")
            with server.JOB_LOCK:
                server.JOBS.pop("XML-INTERRUPTED", None)
                server.RECOVERED_WORKSPACES.discard(context.user_id)
            server.ensure_job_recovery(context)
            jobs = server.recoverable_jobs(context)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["state"], "interrupted")
        self.assertTrue(jobs[0]["recoverable"])

    def test_engine_execution_serializes_two_operations(self):
        events: list[str] = []
        context = SimpleNamespace(user_id="lock-test")

        def worker(name: str, delay: float) -> None:
            with server.engine_execution(name, context):
                events.append(f"start:{name}")
                time.sleep(delay)
                events.append(f"end:{name}")

        first = threading.Thread(target=worker, args=("A", 0.08))
        second = threading.Thread(target=worker, args=("B", 0.01))
        first.start()
        time.sleep(0.01)
        second.start()
        first.join(2)
        second.join(2)
        self.assertEqual(events, ["start:A", "end:A", "start:B", "end:B"])
        self.assertFalse(server.engine_state_snapshot()["active"])

    def test_backup_can_be_restored_with_emergency_copy(self):
        from security import AuthenticatedUser

        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            old_workspaces = server.WORKSPACES_ROOT
            old_backups = server.BACKUP_ROOT
            old_cache = server.WORKSPACE_CACHE
            old_recovered = server.RECOVERED_WORKSPACES
            try:
                server.WORKSPACES_ROOT = temp / "workspaces"
                server.BACKUP_ROOT = temp / "backups"
                server.WORKSPACE_CACHE = {}
                server.RECOVERED_WORKSPACES = set()
                server.WORKSPACES_ROOT.mkdir(parents=True)
                server.BACKUP_ROOT.mkdir(parents=True)
                user = AuthenticatedUser("restore-user", "restore", "Restore", "admin")
                context = server.get_workspace(user.id)
                marker = context.state_root / "marker.txt"
                marker.write_text("versão original", encoding="utf-8")
                backup = server.create_workspace_backup(context, user)
                marker.write_text("versão alterada", encoding="utf-8")
                result = server.restore_workspace_backup(context, user, Path(backup["path"]).read_bytes(), Path(backup["path"]).name)
                restored = server.get_workspace(user.id)
                restored_value = (restored.state_root / "marker.txt").read_text(encoding="utf-8")
            finally:
                server.WORKSPACES_ROOT = old_workspaces
                server.BACKUP_ROOT = old_backups
                server.WORKSPACE_CACHE = old_cache
                server.RECOVERED_WORKSPACES = old_recovered
        self.assertEqual(restored_value, "versão original")
        self.assertGreaterEqual(result["files"], 1)
        self.assertTrue(result["emergency_backup"]["sha256"])

    def test_vector_pdf_is_rasterized_for_signature_crop(self):
        try:
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab indisponível")
        from services import OfficialSignatureService

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "assinatura_vetorial.pdf"
            document = canvas.Canvas(str(pdf))
            document.setFont("Helvetica", 18)
            document.drawString(100, 700, "ASSINATURA VETORIAL DE TESTE")
            document.line(100, 680, 420, 680)
            document.save()
            service = OfficialSignatureService(server.PROJECT_ROOT, Path(tmp) / "data", Path(tmp) / "state", None, None)
            result = service.extract_pdf_images(pdf.read_bytes(), pdf.name)
        self.assertGreaterEqual(result["full_page_candidates"], 1)
        self.assertTrue(result["raster_backend"])
        self.assertEqual(result["candidates"][0]["source"], "rendered_page")
        self.assertTrue(result["candidates"][0]["data_url"].startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
