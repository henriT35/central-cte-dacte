# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WEB_LOCAL_ROOT = Path(__file__).resolve().parents[1]
if str(WEB_LOCAL_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_LOCAL_ROOT))

from security import AuthManager


class R11UserManagementTests(unittest.TestCase):
    def make_auth(self, root: Path):
        auth = AuthManager(root)
        admin = auth.setup_admin("admin.local", "Administrador", "SenhaAdmin123")
        developer = auth.create_first_developer_local("dev.local", "Desenvolvedor", "SenhaDev1234")
        operator = auth.create_user("operador.local", "Operador", "operador", "SenhaOperador123", actor=admin)
        return auth, admin, developer, operator

    def test_only_developer_resets_third_party_password_and_revokes_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth, admin, developer, operator = self.make_auth(Path(tmp))
            token, _ = auth.create_session(operator)
            self.assertIsNotNone(auth.get_session(token))

            with self.assertRaises(PermissionError):
                auth.reset_password(operator.id, "NovaSenha1234", actor=admin)

            updated = auth.reset_password(
                operator.id,
                "NovaSenha1234",
                actor=developer,
                must_change_password=True,
            )
            self.assertEqual(updated.id, operator.id)
            self.assertIsNone(auth.get_session(token))
            self.assertTrue(auth.requires_password_change(operator.id))
            self.assertIsNone(auth.authenticate("operador.local", "SenhaOperador123", remote_key="old-password"))
            self.assertIsNotNone(auth.authenticate("operador.local", "NovaSenha1234", remote_key="new-password"))

    def test_temporary_password_is_generated_and_not_saved_in_public_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth, _admin, developer, operator = self.make_auth(Path(tmp))
            result = auth.create_temporary_password(operator.id, actor=developer, must_change_password=True)
            password = result["temporary_password"]
            self.assertGreaterEqual(len(password), 12)
            self.assertTrue(any(char.isalpha() for char in password))
            self.assertTrue(any(char.isdigit() for char in password))
            self.assertIsNotNone(auth.authenticate(operator.username, password, remote_key="temporary"))
            listing = auth.list_users(actor=developer)
            listed = next(item for item in listing if item["id"] == operator.id)
            self.assertTrue(listed["must_change_password"])
            self.assertNotIn("password", listed)
            self.assertNotIn("temporary_password", listed)
            self.assertTrue(listed["password_reset_at"])
            self.assertEqual(listed["password_reset_by"], developer.id)

    def test_user_changes_own_password_and_clears_mandatory_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth, _admin, developer, operator = self.make_auth(Path(tmp))
            auth.reset_password(operator.id, "Temporaria123", actor=developer, must_change_password=True)
            logged = auth.authenticate(operator.username, "Temporaria123", remote_key="forced-login")
            self.assertIsNotNone(logged)
            changed = auth.change_own_password(
                operator.id,
                "Temporaria123",
                "MinhaSenhaNova456",
                actor=logged,
            )
            self.assertEqual(changed.id, operator.id)
            self.assertFalse(auth.requires_password_change(operator.id))
            self.assertIsNone(auth.authenticate(operator.username, "Temporaria123", remote_key="old-temp"))
            self.assertIsNotNone(auth.authenticate(operator.username, "MinhaSenhaNova456", remote_key="new-own"))

    def test_developer_can_edit_username_with_uniqueness_and_session_revocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth, admin, developer, operator = self.make_auth(Path(tmp))
            second = auth.create_user("consulta.local", "Consulta", "consulta", "SenhaConsulta123", actor=admin)
            token, _ = auth.create_session(operator)

            updated = auth.update_user(
                operator.id,
                username="operador.editado",
                display_name="Operador Editado",
                role="operador",
                active=True,
                actor=developer,
            )
            self.assertEqual(updated.username, "operador.editado")
            self.assertIsNone(auth.get_session(token))
            self.assertIsNone(auth.authenticate("operador.local", "SenhaOperador123", remote_key="old-user"))
            self.assertIsNotNone(auth.authenticate("operador.editado", "SenhaOperador123", remote_key="new-user"))

            with self.assertRaises(ValueError):
                auth.update_user(
                    second.id,
                    username="operador.editado",
                    display_name="Consulta",
                    role="consulta",
                    active=True,
                    actor=developer,
                )

    def test_listing_reports_active_sessions_and_password_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth, _admin, developer, operator = self.make_auth(Path(tmp))
            auth.create_session(operator)
            auth.create_session(operator)
            listed = next(item for item in auth.list_users(actor=developer) if item["id"] == operator.id)
            self.assertEqual(listed["active_sessions"], 2)
            self.assertTrue(listed["password_changed_at"])
            self.assertIn("updated_at", listed)

            result = auth.revoke_sessions_managed(operator.id, actor=developer)
            self.assertTrue(result["revoked"])
            listed = next(item for item in auth.list_users(actor=developer) if item["id"] == operator.id)
            self.assertEqual(listed["active_sessions"], 0)

    def test_new_user_can_be_forced_to_change_initial_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            auth = AuthManager(root)
            admin = auth.setup_admin("admin.local", "Administrador", "SenhaAdmin123")
            developer = auth.create_first_developer_local("dev.local", "Desenvolvedor", "SenhaDev1234")
            created = auth.create_user(
                "novo.local",
                "Novo Usuário",
                "operador",
                "SenhaInicial123",
                actor=developer,
                must_change_password=True,
            )
            self.assertTrue(auth.requires_password_change(created.id))

    def test_frontend_and_server_expose_r11_password_management_contracts(self):
        web_root = Path(__file__).resolve().parents[1]
        html = (web_root / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (web_root / "static" / "app.js").read_text(encoding="utf-8")
        server = (web_root / "server.py").read_text(encoding="utf-8")
        for token in (
            "generate-temporary-password",
            "reset-user-password",
            "revoke-user-sessions",
            "own-password-form",
            "must_change_password",
        ):
            self.assertIn(token, html + javascript + server)
        self.assertIn("/api/auth/password/change", server)
        self.assertIn("PASSWORD_CHANGE_REQUIRED", server)



if __name__ == "__main__":
    unittest.main()
