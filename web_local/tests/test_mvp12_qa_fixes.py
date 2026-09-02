# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

WEB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WEB_ROOT.parent
SERVER_PATH = WEB_ROOT / "server.py"

spec = importlib.util.spec_from_file_location("central_cte_web_server_mvp12", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(server)

from developer_tools import DeveloperTools  # noqa: E402
from security import AuthManager, AuthenticatedUser  # noqa: E402
from services.engine_xml_service import destination_label, commercial_inputs_using_receiver, annotate_receiver_route  # noqa: E402
from services.xml_report_web_patch import publish_extra_comparison_fields  # noqa: E402


class FakeXmlService:
    def __init__(self, partner_source: Path | None = None):
        self.partner_source = partner_source
        self.invalidated = 0
        self.cleared = 0

    def validate_base_source(self, source: Path):
        files = list(Path(source).glob("*.sswweb"))
        return {"file_count": len(files), "row_count": len(files) * 10}

    def invalidate_dependencies(self):
        self.invalidated += 1

    def clear_results(self):
        self.cleared += 1
        return {"cleared": True}

    def validate_table_source(self, source: Path):
        return {"partner_count": 3, "rule_count": 7, "source": str(source)}

    def resolve_table_source(self, *, raise_on_missing=True):
        if self.partner_source and self.partner_source.is_file():
            return self.partner_source
        if raise_on_missing:
            raise FileNotFoundError("Tabela ausente")
        return None


class FakeInvoiceService:
    def __init__(self):
        self.cleared = 0

    def clear_results(self):
        self.cleared += 1
        return {"cleared": True}


class Mvp12QaFixesTests(unittest.TestCase):
    def test_first_developer_is_created_only_once_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = AuthManager(Path(tmp))
            # setup inicial continua sendo administrador, sem credencial padrão
            auth.setup_admin("admin.local", "Administrador", "SenhaSegura123")
            developer = auth.create_first_developer_local("dev.local", "Desenvolvedor", "OutraSenha123")
            self.assertEqual(developer.role, "desenvolvedor")
            self.assertTrue(auth.developer_exists())
            with self.assertRaises(PermissionError):
                auth.create_first_developer_local("dev.2", "Outro", "MaisUmaSenha123")

    def test_only_developer_can_create_another_developer(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth = AuthManager(Path(tmp))
            admin = auth.setup_admin("admin.local", "Administrador", "SenhaSegura123")
            with self.assertRaises(PermissionError):
                auth.create_user("dev.invalido", "Dev", "desenvolvedor", "OutraSenha123", actor=admin)
            dev = auth.create_first_developer_local("dev.local", "Desenvolvedor", "OutraSenha123")
            second = auth.create_user("dev.2", "Segundo Dev", "desenvolvedor", "MaisUmaSenha123", actor=dev)
            self.assertEqual(second.role, "desenvolvedor")

    def test_capabilities_keep_technical_functions_developer_only_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tools = DeveloperTools(PROJECT_ROOT, Path(tmp))
            admin = AuthenticatedUser("a", "admin", "Admin", "admin")
            dev = AuthenticatedUser("d", "dev", "Dev", "desenvolvedor")
            operator = AuthenticatedUser("o", "op", "Op", "operador")
            self.assertFalse(tools.capabilities(admin)["can_manage_partner_tables"])
            self.assertFalse(tools.capabilities(admin)["can_view_technical_reports"])
            self.assertFalse(tools.capabilities(operator)["can_view_qa"])
            self.assertTrue(tools.capabilities(dev)["can_manage_partner_tables"])
            self.assertTrue(tools.capabilities(dev)["can_clear_qa"])
            self.assertTrue(tools.capabilities(dev)["can_view_technical_reports"])

    def test_complete_base_import_replaces_previous_set_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uploads = root / "uploads"
            state = root / "state"
            base_dir = uploads / "bases"
            base_dir.mkdir(parents=True)
            (base_dir / "antiga.sswweb").write_text("A;B;C\n1;2;3\n", encoding="latin-1")
            xml = FakeXmlService()
            invoice = FakeInvoiceService()
            context = SimpleNamespace(
                upload_categories={"bases": base_dir, "tabelas": uploads / "tabelas"},
                state_root=state,
                xml_service=xml,
                invoice_service=invoice,
                qa_path=root / "qa.json",
            )
            tools = DeveloperTools(PROJECT_ROOT, root / "security")
            batch = "base_12345678"
            tools.stage_base_file(context, batch, "parte_1.sswweb", b"NF;FRETE;DESTINO\n1;10;A\n")
            tools.stage_base_file(context, batch, "parte_2.sswweb", b"NF;FRETE;DESTINO\n2;20;B\n")
            result = tools.commit_base_batch(context, batch, expected_count=2)
            self.assertEqual({p.name for p in base_dir.glob("*.sswweb")}, {"parte_1.sswweb", "parte_2.sswweb"})
            self.assertEqual(result["active_file_count"], 2)
            self.assertTrue(result["requires_reprocessing"])
            self.assertEqual(xml.invalidated, 1)
            self.assertEqual(xml.cleared, 1)
            self.assertEqual(invoice.cleared, 1)

    def test_partner_table_can_be_exported_and_replaced_only_after_validation(self):
        official = PROJECT_ROOT / "tabelas" / "cadastro_tabelas_parceiros.xlsx"
        self.assertTrue(official.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uploads = root / "uploads"
            table_dir = uploads / "tabelas"
            state = root / "state"
            xml = FakeXmlService(official)
            context = SimpleNamespace(
                upload_categories={"bases": uploads / "bases", "tabelas": table_dir},
                state_root=state,
                xml_service=xml,
                invoice_service=FakeInvoiceService(),
                qa_path=root / "qa.json",
            )
            tools = DeveloperTools(PROJECT_ROOT, root / "security")
            self.assertEqual(tools.active_partner_table(context), official.resolve())
            result = tools.replace_partner_table(context, official.read_bytes(), "modelo_editado.xlsx")
            active = table_dir / "cadastro_tabelas_parceiros.xlsx"
            self.assertTrue(active.is_file())
            self.assertEqual(result["partners"], 3)
            self.assertEqual(result["rules"], 7)
            xml.partner_source = active
            self.assertEqual(tools.active_partner_table(context), active.resolve())

    def test_clear_qa_archives_before_emptying_notebook(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qa_path = root / "qa.json"
            qa_path.write_text(json.dumps([{"id": "QA-1"}, {"id": "QA-2"}]), encoding="utf-8")
            context = SimpleNamespace(qa_path=qa_path, state_root=root / "state")
            tools = DeveloperTools(PROJECT_ROOT, root / "security")
            result = tools.clear_qa(context)
            self.assertEqual(result["deleted"], 2)
            self.assertEqual(json.loads(qa_path.read_text(encoding="utf-8")), [])
            self.assertTrue(Path(result["archive_path"]).is_file())

    def test_standard_report_list_does_not_mix_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "relatorios").mkdir()
            (root / "logs").mkdir()
            (root / "saida_html").mkdir()
            (root / "relatorios" / "relatorio_oficial.xlsx").write_bytes(b"xlsx")
            (root / "logs" / "engine.log").write_text("log", encoding="utf-8")
            output = root / "workspace" / "outputs"
            state = root / "workspace" / "state"
            (output / "relatorios").mkdir(parents=True)
            (output / "dacte").mkdir(parents=True)
            state.mkdir(parents=True)
            (state / "snapshot.json").write_text("{}", encoding="utf-8")
            context = SimpleNamespace(output_root=output, state_root=state)
            original_root = server.PROJECT_ROOT
            try:
                server.PROJECT_ROOT = root
                standard = server.scan_reports(context, include_technical=False)
                technical = server.scan_reports(context, include_technical=True)
            finally:
                server.PROJECT_ROOT = original_root
            self.assertEqual([row["name"] for row in standard], ["relatorio_oficial.xlsx"])
            self.assertIn("engine.log", {row["name"] for row in technical})
            self.assertIn("snapshot.json", {row["name"] for row in technical})

    def test_receiver_address_precedes_end_of_provision(self):
        info = {
            "destino": "MANICORE / AM",
            "dest": {"mun": "MANICORE - AM"},
            "receb": {"mun": "SANTO ANTONIO DO MATUPI - AM"},
        }
        self.assertEqual(destination_label(info), "SANTO ANTONIO DO MATUPI / AM")
        base_row = {"destino_cidade": "MANICORE", "destino_uf": "AM", "valor_frete": 100.0}
        commercial_info, commercial_base, metadata = commercial_inputs_using_receiver(
            {**info, "docs": [{"n_doc": "3572627"}]},
            {"index": {"3572627": [base_row]}, "rows": [base_row]},
        )
        self.assertEqual(commercial_info["dest"]["mun"], "SANTO ANTONIO DO MATUPI - AM")
        self.assertEqual(commercial_base["index"]["3572627"][0]["destino_cidade"], "SANTO ANTONIO DO MATUPI")
        self.assertEqual(base_row["destino_cidade"], "MANICORE")
        annotated = annotate_receiver_route({"trace": []}, metadata)
        self.assertEqual(annotated["destino_comercial_fonte"], "RECEBEDOR_XML_WEB")
        self.assertIn("recebedor", annotated["trace"][-1].lower())

    def test_receiver_route_normalization_matches_partner_table_keys(self):
        cases = (
            ("JI-PARANÁ - RO", "JI PARANA", "RO"),
            ("GUAJARÁ-MIRIM - RO", "GUAJARA MIRIM", "RO"),
            ("TOMÉ-AÇU - PA", "TOME ACU", "PA"),
            ("ALTO ALEGRE DOS PARECIS - RO", "ALTO ALEGRE DO PARECIS", "RO"),
        )
        for receiver, expected_city, expected_uf in cases:
            with self.subTest(receiver=receiver):
                source_row = {"destino_cidade": "OUTRO MUNICIPIO", "destino_uf": expected_uf}
                _, adapted_base, metadata = commercial_inputs_using_receiver(
                    {"receb": {"mun": receiver}, "docs": [{"n_doc": "1"}]},
                    {"index": {"1": [source_row]}, "rows": [source_row]},
                )
                adapted = adapted_base["index"]["1"][0]
                self.assertEqual(adapted["destino_cidade"], expected_city)
                self.assertEqual(adapted["destino_uf"], expected_uf)
                self.assertEqual(metadata["city"], expected_city)

    def test_extra_comparison_fields_are_published_without_changing_status(self):
        validation = {
            "status": "DIVERGENTE EXTRA +",
            "esperado": 200.00,
            "diferenca": None,
            "valor_comparado": None,
            "componente_comparado": "",
            "trace": [],
        }
        published = publish_extra_comparison_fields(validation, {"valor": "517,98"})
        self.assertEqual(published["status"], "DIVERGENTE EXTRA +")
        self.assertEqual(published["valor_total_xml"], 517.98)
        self.assertEqual(published["valor_comparado"], 517.98)
        self.assertEqual(published["componente_comparado"], "VALOR TOTAL XML — COBRANÇA EXTRA")
        self.assertEqual(published["diferenca"], 317.98)
        self.assertIn("Publicação web", published["trace"][-1])

    def test_pdf_signature_requires_manual_crop_and_never_auto_applies_full_page(self):
        script = (WEB_ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Recorte obrigatório", script)
        self.assertIn("openSignatureCrop", script)
        self.assertIn("applySignatureCrop", script)
        self.assertNotIn("if (candidates.length === 1) {\n      await saveProcessedSignature", script)
        page = (WEB_ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="signature-crop-modal"', page)
        self.assertIn("A folha inteira nunca será aplicada ao DACTE", page)


if __name__ == "__main__":
    unittest.main()
