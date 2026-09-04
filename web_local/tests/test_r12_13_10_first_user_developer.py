# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

WEB_ROOT = Path(__file__).resolve().parents[1]
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from security import AuthManager  # noqa: E402


class R121310FirstUserDeveloperTests(unittest.TestCase):
    def test_initial_setup_creates_developer_not_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = AuthManager(Path(tmp))
            self.assertTrue(auth.setup_required())
            user = auth.setup_developer("dev.inicial", "Desenvolvedor Inicial", "SenhaSegura123")
            self.assertEqual(user.role, "desenvolvedor")
            self.assertFalse(auth.setup_required())
            self.assertTrue(auth.developer_exists())

    def test_legacy_setup_admin_alias_cannot_create_initial_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = AuthManager(Path(tmp))
            user = auth.setup_admin("compat.local", "Compatibilidade", "SenhaSegura123")
            self.assertEqual(user.role, "desenvolvedor")

    def test_frontend_and_server_use_developer_bootstrap(self):
        app_js = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")
        server_py = (WEB_ROOT / "server.py").read_text(encoding="utf-8")
        self.assertIn("Criar Desenvolvedor inicial", app_js)
        self.assertIn("Criar Desenvolvedor", app_js)
        self.assertNotIn("Criar administrador inicial", app_js)
        self.assertIn("AUTH.setup_developer", server_py)


if __name__ == "__main__":
    unittest.main()
