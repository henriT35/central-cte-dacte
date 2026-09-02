from __future__ import annotations

import pytest

from web_local.services.engine_xml_service import OfficialXmlEngineService


class _FakeEngine:
    def __init__(self, expected_normal: float):
        self.expected_normal = expected_normal
        self.last_info = None

    def validate_cte_value(self, info, base, tables):
        self.last_info = info
        assert "REENTREGA" not in str(info.get("obs") or "").upper()
        assert "REENTREGA" not in str(info.get("obs_principal") or "").upper()
        return {
            "status": "DIVERGENTE -",
            "partner_id": "AC_LOG_C_VARGAS",
            "tipo_cobranca": "NORMAL",
            "percentual": 0.20,
            "frete_minimo": 28.39,
            "esperado": self.expected_normal,
            "diferenca": -605.27,
            "trace": [],
        }


def _validation(*, base: float, xml: float, old_expected: float) -> dict:
    return {
        "partner_id": "AC_LOG_C_VARGAS",
        "tipo_cobranca": "REENTREGA",
        "status": "DIVERGENTE EXTRA -",
        "base_frete": base,
        "base_calculo": "ORIGINAL",
        "percentual": 0.50,
        "frete_minimo": 0.0,
        "valor_comparado": xml,
        "valor_total_xml": xml,
        "esperado": old_expected,
        "diferenca": xml - old_expected,
        "tolerancia": 1.0,
        "regra_extra": "REENTREGA",
        "trace": [],
    }


def test_c_vargas_48888_reentrega_uses_partner_normal_freight() -> None:
    engine = _FakeEngine(1210.548)
    result = OfficialXmlEngineService._apply_partner_calculated_reentrega(
        _validation(base=6052.74, xml=605.27, old_expected=3026.37),
        {"valor": "605.27", "obs": "REENTREGA AUTORIZADO BIANCA"},
        {"valor": "605.27", "obs": "REENTREGA AUTORIZADO BIANCA", "obs_principal": "REENTREGA", "componentes": []},
        {"rows": []},
        {"tolerance": 1.0},
        engine,
    )
    assert result["base_frete"] == pytest.approx(6052.74)  # receita Rodovitor preservada
    assert result["base_calculo"] == "PARCEIRO_CALCULADO"
    assert result["partner_normal_expected"] == pytest.approx(1210.548)
    assert result["esperado"] == pytest.approx(605.27)
    assert result["diferenca"] == pytest.approx(0.0)
    assert result["status"] == "OK EXTRA"
    assert result["engine_expected_value"] == pytest.approx(3026.37)


def test_c_vargas_49536_reentrega_1400_becomes_140() -> None:
    engine = _FakeEngine(280.0)
    result = OfficialXmlEngineService._apply_partner_calculated_reentrega(
        _validation(base=1400.0, xml=140.0, old_expected=700.0),
        {"valor": "140.00", "obs": "REENTREGA DE NF 3758"},
        {"valor": "140.00", "obs": "REENTREGA DE NF 3758", "produto": "CUSTO EXTRA", "componentes": []},
        {"rows": []},
        {"tolerance": 1.0},
        engine,
    )
    assert result["partner_normal_expected"] == pytest.approx(280.0)
    assert result["esperado"] == pytest.approx(140.0)
    assert result["diferenca"] == pytest.approx(0.0)
    assert result["status"] == "OK EXTRA"


def test_reentrega_value_ok_still_requires_operational_authorization() -> None:
    calculated = {
        "partner_id": "AC_LOG_C_VARGAS",
        "tipo_cobranca": "REENTREGA",
        "status": "OK EXTRA",
        "base_frete": 6052.74,
        "base_calculo": "PARCEIRO_CALCULADO",
        "valor_comparado": 605.27,
        "esperado": 605.27,
        "diferenca": 0.0,
        "tolerancia": 1.0,
        "trace": [],
    }
    result = OfficialXmlEngineService._apply_operational_authorization_policy(
        calculated,
        {"valor": "605.27", "obs": "REENTREGA AUTORIZADO BIANCA"},
    )
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["requires_manual_authorization"] is True
    assert result["authorization_status"] == "PENDENTE"
    assert result["authorization_evidence_in_xml"] is True
    assert result["calculation_status"] == "OK EXTRA"
    assert result["calculation_expected_value"] == pytest.approx(605.27)
    assert result["calculation_difference"] == pytest.approx(0.0)
    assert result["esperado"] == pytest.approx(605.27)
    assert result["diferenca"] == pytest.approx(0.0)
    assert "Autorização operacional: PENDENTE" in result["controle_dacte_linha2"]


def test_non_reentrega_partner_is_unchanged() -> None:
    original = {
        "partner_id": "AC_LOG_C_VARGAS",
        "tipo_cobranca": "NORMAL",
        "status": "OK AC LOG / C VARGAS",
        "base_frete": 1000.0,
        "esperado": 200.0,
        "diferenca": 0.0,
    }
    result = OfficialXmlEngineService._apply_partner_calculated_reentrega(
        original, {}, {}, {}, {}, _FakeEngine(200.0)
    )
    assert result == original
