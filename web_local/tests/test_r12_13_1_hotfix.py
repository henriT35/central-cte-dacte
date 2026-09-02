from __future__ import annotations

from pathlib import Path

import pytest

from engine.central_cte_modular.repositories.partner_table_repository import PartnerTableRepository
from web_local.services.engine_xml_service import OfficialXmlEngineService


ROOT = Path(__file__).resolve().parents[2]


def _grauna_tables() -> dict:
    return {
        "tolerance": 1.0,
        "peso_especial": [{
            "partner_id": "GRAUNA_TRANSPORTES",
            "peso_min_kg": 120.0,
            "percent": 0.30,
            "minimum": 0.0,
            "base_calculo": "ORIGINAL",
            "raw": {"REGRAID": "GRAUNA_ACIMA_120KG", "PERCENTUAL": "30%", "VALORKG": "0.80"},
        }],
        "extras": [],
    }


def test_c_vargas_generic_conferente_is_not_cost_extra() -> None:
    automatic = {
        "partner_id": "AC_LOG_C_VARGAS",
        "tipo_cobranca": "NORMAL",
        "status": "OK AC LOG / C VARGAS",
        "esperado": 148.97,
        "diferenca": 0.0,
        "trace": [],
    }
    info = {
        "outras_carac": "TABELA: COMBINADA CO1384 - ROTA: MCPP/MCPP - TARIF: 001 - TIPO MERCAD: DIVERSOS. Conferente: EDIELSON MELO DE SOUZA"
    }
    result = OfficialXmlEngineService._apply_operational_authorization_policy(automatic, info)
    assert result["tipo_cobranca"] == "NORMAL"
    assert result["status"] == "OK AC LOG / C VARGAS"
    assert result.get("requires_manual_authorization") is not True


def test_c_vargas_separacao_remains_manual_extra() -> None:
    automatic = {
        "partner_id": "AC_LOG_C_VARGAS",
        "tipo_cobranca": "NORMAL",
        "status": "DIVERGENTE AC LOG / C VARGAS -",
        "esperado": 839.13,
        "diferenca": -624.13,
        "trace": [],
    }
    info = {
        "obs": "SEPARACAO E CONFERENTE NF 129751",
        "outras_carac": "TABELA: INFORMADO - TIPO MERCAD: CUSTO EXTRA. Conferente: ADRIANE",
    }
    result = OfficialXmlEngineService._apply_operational_authorization_policy(automatic, info)
    assert result["tipo_cobranca"] == "CUSTO_EXTRA"
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["engine_status"] == "DIVERGENTE AC LOG / C VARGAS -"


def test_grauna_weight_rule_without_route_context_never_emits_false_ok() -> None:
    automatic = {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "OK",
        "regra_peso_especial": "SIM",
        "peso_base_kg": 297.0,
        "valor_comparado": 241.37,
        "base_frete": 804.55,
        "esperado": 241.37,
        "diferenca": 0.0,
        "percentual": 0.30,
        "trace": [],
    }
    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, {"valor": "241.37"}, _grauna_tables())
    assert result["status"] == "REVISAR — REGRA >120 KG EM SOMBRA"
    assert result["esperado"] is None
    assert result["diferenca"] is None
    assert result["shadow_weight_active"] is True
    assert result["shadow_weight_match"] is True
    assert result["shadow_weight_percentual"] == pytest.approx(0.30)
    assert result["engine_status"] == "OK"
    assert any("SHADOW" in str(item) for item in result.get("trace", []))


def test_grauna_partner_file_declares_30_percent_above_120kg() -> None:
    source = ROOT / "web_local/data/partner_tables/files/GRAUNA_TRANSPORTES.xlsx"
    tables = PartnerTableRepository().load(source)
    rules = [
        rule for rule in tables.get("peso_especial", [])
        if str(rule.get("partner_id") or "").upper() == "GRAUNA_TRANSPORTES"
        and abs(float(rule.get("peso_min_kg") or 0) - 120.0) < 1e-6
    ]
    assert rules
    rule = rules[0]
    assert float(rule.get("percent") or 0) == pytest.approx(0.30)
    assert str(rule.get("base_calculo") or "").upper() == "ORIGINAL"
    assert "30%" in str(rule.get("observacao") or "")
    assert "0,80/kg" in str(rule.get("observacao") or "")


def test_grauna_atacadao_remains_manual_40_percent_priority() -> None:
    automatic = {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "OK",
        "regra_peso_especial": "SIM",
        "peso_base_kg": 300.0,
        "base_frete": 1000.0,
        "valor_comparado": 400.0,
        "esperado": 300.0,
        "diferenca": 100.0,
        "trace": [],
    }
    tables = _grauna_tables()
    tables["extras"] = [{
        "partner_id": "GRAUNA_TRANSPORTES",
        "tipo_extra": "REDE ATACADAO VALE",
        "percent": 0.40,
    }]
    info = {"destinatario": "ATACADAO SA", "valor": "400.00"}
    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, info, tables)
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["special_contract_percent"] == pytest.approx(0.40)
    assert result["special_contract_expected"] == pytest.approx(400.0)
