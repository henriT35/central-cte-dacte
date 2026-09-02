from __future__ import annotations

import pytest

from web_local.services.engine_xml_service import OfficialXmlEngineService


def _tables() -> dict:
    return {
        "tolerance": 1.0,
        "extras": [{
            "partner_id": "GRAUNA_TRANSPORTES",
            "tipo_extra": "REDE_ATACADAO_VALE",
            "percent": 0.40,
        }],
        "peso_especial": [{
            "partner_id": "GRAUNA_TRANSPORTES",
            "peso_min_kg": 120.0,
            "percent": 0.30,
            "base_calculo": "ORIGINAL",
            "raw": {"REGRAID": "GRAUNA_ACIMA_120KG", "PERCENTUAL": "30%", "VALORKG": "0.80"},
        }],
    }


class _RouteEngine:
    def __init__(self, *, status: str = "DIVERGENTE +", actual: float = 300.0) -> None:
        self.status = status
        self.actual = actual
        self.received_tables: dict | None = None

    def validate_cte_value(self, info, base, tables):
        self.received_tables = tables
        # A fotografia oficial não pode mais receber a regra de peso da Graúna.
        assert not [
            rule for rule in tables.get("peso_especial", [])
            if str(rule.get("partner_id") or "").upper() == "GRAUNA_TRANSPORTES"
        ]
        return {
            "partner_id": "GRAUNA_TRANSPORTES",
            "status": self.status,
            "base_frete": 1000.0,
            "valor_comparado": self.actual,
            "percentual": 0.28,
            "frete_minimo": 75.0,
            "esperado": 280.0,
            "diferenca": round(self.actual - 280.0, 2),
            "tolerancia": 1.0,
            "regra_comercial": "REDENCAO_PA_28_PERCENT",
            "trace": ["regra normal Redenção 28%"],
        }


def _weight_ok_snapshot(actual: float = 300.0) -> dict:
    return {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "OK",
        "base_frete": 1000.0,
        "valor_comparado": actual,
        "percentual": 0.30,
        "frete_minimo": None,
        "esperado": 300.0,
        "diferenca": round(actual - 300.0, 2),
        "tolerancia": 1.0,
        "regra_peso_especial": "SIM",
        "peso_base_kg": 180.0,
        "modo_calculo": "PESO_ESPECIAL_PERCENTUAL",
        "regra_comercial": "REGRAS_PESO_ESPECIAL | GRAUNA_ACIMA_120KG",
        "trace": ["fotografia RC26.6 usando peso"],
    }


def test_redencao_above_120kg_uses_28_percent_and_keeps_weight_only_in_shadow() -> None:
    engine = _RouteEngine(status="DIVERGENTE +", actual=300.0)
    info = {"dest": {"mun": "REDENÇÃO - PA", "nome": "CLIENTE NORMAL"}, "valor": "300.00"}

    result = OfficialXmlEngineService._apply_web_contract_adapters(
        _weight_ok_snapshot(),
        info,
        _tables(),
        commercial_info=info,
        commercial_base={"index": {}},
        engine=engine,
    )

    assert result["percentual"] == pytest.approx(0.28)
    assert result["esperado"] == pytest.approx(280.0)
    assert result["diferenca"] == pytest.approx(20.0)
    assert result["status"] == "DIVERGENTE +"
    assert result["controle_dacte_status"] == "DIVERGENTE +"

    # O antigo 30% continua auditável, mas não pode transformar a linha em OK.
    assert result["engine_status"] == "OK"
    assert result["engine_expected_value"] == pytest.approx(300.0)
    assert result["shadow_weight_active"] is True
    assert result["shadow_weight_match"] is True
    assert result["shadow_weight_expected"] == pytest.approx(300.0)
    assert result["shadow_weight_percentual"] == pytest.approx(0.30)
    assert any("não pode gerar OK oficial" in str(item) for item in result["trace"])


def test_atacadao_40_percent_remains_priority_even_above_120kg() -> None:
    engine = _RouteEngine(status="DIVERGENTE +", actual=400.0)
    info = {"dest": {"mun": "REDENÇÃO - PA", "nome": "ATACADAO SA"}, "valor": "400.00"}

    result = OfficialXmlEngineService._apply_web_contract_adapters(
        _weight_ok_snapshot(actual=400.0),
        info,
        _tables(),
        commercial_info=info,
        commercial_base={"index": {}},
        engine=engine,
    )

    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["special_contract_percent"] == pytest.approx(0.40)
    assert result["special_contract_expected"] == pytest.approx(400.0)
    assert result["authorization_status"] == "PENDENTE"
    assert result["shadow_weight_active"] is True
    assert result["controle_dacte_status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"


def test_below_120kg_keeps_existing_route_result_without_shadow() -> None:
    automatic = {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "OK",
        "base_frete": 1000.0,
        "valor_comparado": 280.0,
        "percentual": 0.28,
        "esperado": 280.0,
        "diferenca": 0.0,
        "tolerancia": 1.0,
        "peso_base_kg": 100.0,
        "trace": [],
    }
    info = {"dest": {"mun": "REDENÇÃO - PA", "nome": "CLIENTE NORMAL"}, "valor": "280.00"}

    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, info, _tables())

    assert result["status"] == "OK"
    assert result["percentual"] == pytest.approx(0.28)
    assert result.get("shadow_weight_active") is not True
