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
            "raw": {"REGRAID": "GRAUNA_ACIMA_120KG"},
        }],
    }


def _snapshot(*, base: float, actual: float, percent: float, minimum: float, expected: float, weight: float = 80.0) -> dict:
    return {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "OK",
        "base_frete": base,
        "valor_comparado": actual,
        "percentual": percent,
        "frete_minimo": minimum,
        "esperado": expected,
        "diferenca": round(actual - expected, 2),
        "tolerancia": 1.0,
        "peso_base_kg": weight,
        "tipo_cobranca": "NORMAL",
        "trace": ["regra normal da rota"],
    }


def test_giro_supermercados_ourilandia_stays_route_minimum_ok() -> None:
    automatic = _snapshot(base=234.17, actual=75.0, percent=0.30, minimum=75.0, expected=75.0)
    info = {
        "dest": {"nome": "GIRO SUPERMERCADOS LTDA", "mun": "OURILANDIA DO NORTE - PA"},
        "receb": {"nome": "GIRO SUPERMERCADOS LTDA", "mun": "OURILANDIA DO NORTE - PA"},
        "valor": "75.00",
    }

    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, info, _tables())

    assert result["status"] == "OK"
    assert result["esperado"] == pytest.approx(75.0)
    assert result["diferenca"] == pytest.approx(0.0)
    assert result["percentual"] == pytest.approx(0.30)
    assert result["frete_minimo"] == pytest.approx(75.0)
    assert result.get("requires_manual_authorization") is not True
    assert result.get("tipo_cobranca_extra") != "REDE_ATACADAO_VALE"


def test_amm_supermercados_redencao_stays_28_percent_minimum_ok() -> None:
    automatic = _snapshot(base=264.62, actual=75.0, percent=0.28, minimum=75.0, expected=75.0)
    info = {
        "dest": {"nome": "A M M SUPERMERCADOS LTDA", "mun": "REDENCAO - PA"},
        "receb": {"nome": "A M M SUPERMERCADOS LTDA", "mun": "REDENCAO - PA"},
        "valor": "75.00",
        "tpCTe": "SUBSTITUICAO",
    }

    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, info, _tables())

    assert result["status"] == "OK"
    assert result["esperado"] == pytest.approx(75.0)
    assert result["diferenca"] == pytest.approx(0.0)
    assert result["percentual"] == pytest.approx(0.28)
    assert result["frete_minimo"] == pytest.approx(75.0)
    assert result.get("requires_manual_authorization") is not True
    assert result.get("authorization_status") in (None, "")


class _RouteEngine:
    def validate_cte_value(self, info, base, tables):
        assert not [
            rule for rule in tables.get("peso_especial", [])
            if str(rule.get("partner_id") or "").upper() == "GRAUNA_TRANSPORTES"
        ]
        return {
            "partner_id": "GRAUNA_TRANSPORTES",
            "status": "OK",
            "base_frete": 1000.0,
            "valor_comparado": 280.0,
            "percentual": 0.28,
            "frete_minimo": 75.0,
            "esperado": 280.0,
            "diferenca": 0.0,
            "tolerancia": 1.0,
            "peso_base_kg": 180.0,
            "tipo_cobranca": "NORMAL",
            "trace": ["Redenção 28%"],
        }


def test_supermarket_above_120kg_uses_route_not_special_40() -> None:
    original = {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "DIVERGENTE -",
        "base_frete": 1000.0,
        "valor_comparado": 280.0,
        "percentual": 0.30,
        "esperado": 300.0,
        "diferenca": -20.0,
        "tolerancia": 1.0,
        "regra_peso_especial": "SIM",
        "peso_base_kg": 180.0,
        "modo_calculo": "PESO_ESPECIAL_PERCENTUAL",
        "trace": [],
    }
    info = {
        "dest": {"nome": "CLIENTE SUPERMERCADOS LTDA", "mun": "REDENCAO - PA"},
        "receb": {"nome": "CLIENTE SUPERMERCADOS LTDA", "mun": "REDENCAO - PA"},
        "valor": "280.00",
    }

    result = OfficialXmlEngineService._apply_web_contract_adapters(
        original,
        info,
        _tables(),
        commercial_info=info,
        commercial_base={"index": {}},
        engine=_RouteEngine(),
    )

    assert result["status"] == "OK"
    assert result["esperado"] == pytest.approx(280.0)
    assert result["percentual"] == pytest.approx(0.28)
    assert result["shadow_weight_active"] is True
    assert result.get("requires_manual_authorization") is not True
    assert result.get("tipo_cobranca_extra") != "REDE_ATACADAO_VALE"


def test_atacadao_das_embalagens_keeps_40_percent_manual_authorization() -> None:
    automatic = _snapshot(base=1666.53, actual=466.62, percent=0.28, minimum=75.0, expected=466.63, weight=180.0)
    automatic.update({
        "regra_peso_especial": "SIM",
        "modo_calculo": "PESO_ESPECIAL_PERCENTUAL",
    })
    info = {
        "dest": {"nome": "ATACADAO DAS EMBALAGENS LTDA", "mun": "REDENCAO - PA"},
        "receb": {"nome": "ATACADAO DAS EMBALAGENS LTDA", "mun": "REDENCAO - PA"},
        "valor": "466.62",
    }

    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, info, _tables())

    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["tipo_cobranca_extra"] == "REDE_ATACADAO_VALE"
    assert result["special_contract_percent"] == pytest.approx(0.40)
    assert result["special_contract_expected"] == pytest.approx(666.61)
    assert result["authorization_status"] == "PENDENTE"
    assert result["requires_manual_authorization"] is True
