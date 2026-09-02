from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.central_cte_modular.commercial.cte_classification import detectar_cobranca_extra
from engine.central_cte_modular.repositories.partner_table_repository import PartnerTableRepository
from web_local.services.engine_xml_service import OfficialXmlEngineService, write_json_atomic


ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "web_local" / "data" / "partner_tables" / "cadastro_tabelas_parceiros_compilada.xlsx"


def _rule(tables: dict, city: str) -> dict:
    for rule in tables.get("rules", []):
        if rule.get("partner_id") == "AC_LOG_C_VARGAS" and rule.get("destino_cidade") == city:
            return rule
    raise AssertionError(f"Regra de {city} não encontrada")


def test_c_vargas_table_publishes_frete_peso_mode_and_cnpj() -> None:
    tables = PartnerTableRepository().load(TABLE)
    assert tables["partners"]["AC_LOG_C_VARGAS"]["cnpj"] == "34059736000157"

    calcoene = _rule(tables, "CALCOENE")
    oiapoque = _rule(tables, "OIAPOQUE")
    assert calcoene["modo_calculo"] == "FRETE_PESO"
    assert oiapoque["modo_calculo"] == "FRETE_PESO"
    assert calcoene["ton_rate"] == pytest.approx(788.48)
    assert oiapoque["ton_rate"] == pytest.approx(1103.87)


def test_c_vargas_real_report_values_are_weight_times_rate_per_kg() -> None:
    assert round(111 * 1.10387, 2) == 122.53  # CT-e 48576
    assert round(1485 * 0.78848, 2) == 1170.89  # CT-e 48580


def test_tda_is_detected_as_difficulty_of_access() -> None:
    result = detectar_cobranca_extra({
        "componentes": [{"nome": "TDA", "valor": "30.81"}],
        "obs": "TAXA DE DIFICULDADE DE ACESSO (TDA)",
    })
    assert result["tipo"] == "TDA"


def test_ws_extra_becomes_authorization_pending_without_operational_difference() -> None:
    validation = {
        "partner_id": "W_S_TRANSPORTES",
        "tipo_cobranca": "REENTREGA",
        "status": "DIVERGENTE EXTRA -",
        "esperado": 117.29,
        "diferenca": -65.32,
        "trace": [],
    }
    result = OfficialXmlEngineService._apply_operational_authorization_policy(validation, {})
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["requires_manual_authorization"] is True
    assert result["authorization_status"] == "PENDENTE"
    assert result["esperado"] is None
    assert result["diferenca"] is None
    assert result["engine_status"] == "DIVERGENTE EXTRA -"
    assert result["engine_expected_value"] == pytest.approx(117.29)
    assert result["engine_difference"] == pytest.approx(-65.32)


def test_manual_approval_is_persistent_and_keeps_automatic_snapshot(tmp_path: Path) -> None:
    project = ROOT
    upload = tmp_path / "workspace" / "user" / "uploads"
    state = tmp_path / "workspace" / "user" / "state"
    upload.mkdir(parents=True)
    state.mkdir(parents=True)
    xml_path = tmp_path / "cte.xml"
    xml_path.write_text("<xml/>", encoding="utf-8")

    service = OfficialXmlEngineService(project, upload, state, project / "web_local" / "data" / "partner_tables")
    identity = service_file_identity = __import__(
        "web_local.services.engine_xml_service", fromlist=["file_identity"]
    ).file_identity(xml_path)
    automatic = {
        "partner_id": "W_S_TRANSPORTES",
        "tipo_cobranca": "TDA",
        "status": "EXTRA — AGUARDANDO AUTORIZAÇÃO",
        "automatic_status": "EXTRA — AGUARDANDO AUTORIZAÇÃO",
        "engine_status": "EXTRA REVISAR",
        "requires_manual_authorization": True,
        "authorization_status": "PENDENTE",
        "esperado": None,
        "diferenca": None,
        "trace": [],
    }
    row = {
        "identity": identity,
        "path": str(xml_path.resolve()),
        "file": xml_path.name,
        "cte": "3580172",
        "status": automatic["status"],
        "automatic_status": automatic["status"],
        "automatic_validation": automatic,
        "validation": automatic,
        "engine_info": {
            "chave": "11260715186966000132570050035801721012710290",
            "numero": "3580172",
            "serie": "5",
            "emit": {"cnpjcpf": "15186966000132"},
        },
    }
    write_json_atomic(service.results_path, {
        "schema_version": 3,
        "documents": {identity: row},
        "by_path": {str(xml_path.resolve()): identity},
    })

    approved = service.set_manual_decision(
        xml_path,
        "approved",
        "Custo autorizado pelo coordenador",
        actor_id="dev-1",
        actor_name="Desenvolvedor",
    )
    assert approved["status"] == "OK EXTRA AUTORIZADO"
    assert approved["automatic_status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert approved["authorization_status"] == "AUTORIZADO"
    assert approved["manual_reason"] == "Custo autorizado pelo coordenador"

    decisions = json.loads(service.manual_decisions_path.read_text(encoding="utf-8"))
    assert len(decisions["decisions"]) == 1

    cleared = service.set_manual_decision(
        xml_path,
        "clear",
        "",
        actor_id="dev-1",
        actor_name="Desenvolvedor",
    )
    assert cleared["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert cleared["authorization_status"] == "PENDENTE"
    assert cleared["manual_decision"] == {}


def test_ui_and_api_publish_manual_status_controls() -> None:
    server = (ROOT / "web_local" / "server.py").read_text(encoding="utf-8")
    app = (ROOT / "web_local" / "static" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web_local" / "static" / "index.html").read_text(encoding="utf-8")
    tools = (ROOT / "web_local" / "developer_tools.py").read_text(encoding="utf-8")

    assert "/api/process/xml/manual-status" in server
    assert "can_override_xml_status" in server
    assert "can_override_xml_status" in tools
    assert "Aprovar / dar baixa" in app
    assert "O cálculo automático não será apagado" in app
    assert "<th>Ação</th>" in html
