# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from engine.central_cte_modular.commercial.compact_render_guard import (
    CompactConsistencyError,
    FinalCompactRenderGuard,
)
from engine.central_cte_modular.rendering.overlays.compact_control import CompactControlOverlay
from web_local.services.official_dacte_service import OfficialDacteService


class _FakeXmlService:
    @staticmethod
    def _apply_manual_decision(validation, decision):
        result = dict(validation)
        action = str(decision.get("decision") or "").lower()
        if action == "approved":
            result["status"] = "OK MANUAL"
            result["revisao_manual"] = "APROVADO"
        result["observacao_manual"] = str(decision.get("reason") or "")
        result["revisao_data"] = str(decision.get("decided_at") or "")
        result["manual_decision"] = dict(decision)
        return result

    @staticmethod
    def _decision_for(info, path):
        return "cte:test", {
            "decision": "approved",
            "reason": "Baixa manual autorizada pelo responsável operacional",
            "actor_name": "Desenvolvedor",
            "decided_at": "2026-09-01T14:00:00-03:00",
        }


def _manual_validation() -> dict:
    return {
        "partner_id": "PARCEIRO_TESTE",
        "status": "OK MANUAL",
        "automatic_status": "DIVERGENTE +",
        "automatic_expected_value": 100.00,
        "automatic_difference": 3.49,
        "esperado": 100.00,
        "valor_comparado": 103.49,
        "diferenca": 3.49,
        "tolerancia": 1.00,
        "revisao_manual": "APROVADO",
        "observacao_manual": "Autorizado devido a ajuste comercial documentado",
        "manual_decision": {
            "decision": "approved",
            "reason": "Autorizado devido a ajuste comercial documentado",
            "actor_name": "Desenvolvedor",
            "decided_at": "2026-09-01T13:55:00-03:00",
        },
        "trace": [],
    }


def test_manual_approval_with_3_49_difference_does_not_block_signed_pdf_guard() -> None:
    guard = FinalCompactRenderGuard()
    info = {"tipo": "CT-e", "numero": "22066", "valor": "103,49", "validacao": _manual_validation()}

    prepared = guard.prepare_infos([info], strict=True)[0]
    validation = prepared["validacao"]

    assert validation["status"] == "OK MANUAL"
    assert validation["controle_dacte_status"] == "OK MANUAL"
    assert validation["controle_dacte_inconsistente"] is False
    assert validation["controle_dacte_diferenca"] == pytest.approx(3.49, abs=0.01)
    assert "Resultado automático: DIVERGENTE +" in validation["controle_dacte_linha1"]
    assert "Dif. automática R$3,49" in validation["controle_dacte_linha2"]



def test_manual_approval_also_bypasses_guard_when_percentage_compact_is_rebuilt() -> None:
    guard = FinalCompactRenderGuard()
    validation = _manual_validation()
    validation.update({
        "componente_comparado": "FRETE VALOR",
        "base_frete": 500.00,
        "base_calculo": "ORIGINAL",
        "percentual": 0.20,
        "esperado": 100.00,
        "valor_comparado": 103.49,
    })
    info = {
        "tipo": "CT-e",
        "numero": "22066",
        "valor": "103,49",
        "componentes": [{"nome": "FRETE VALOR", "valor": "103,49"}],
        "validacao": validation,
    }

    prepared = guard.prepare_infos([info], strict=True)[0]["validacao"]
    assert prepared["controle_dacte_status"] == "OK MANUAL"
    assert prepared["controle_dacte_inconsistente"] is False
    assert prepared["controle_dacte_diferenca"] == pytest.approx(3.49, abs=0.01)
    assert "Frete valor" in prepared["controle_dacte_linha1"]
    assert "Dif. automática R$3,49" in prepared["controle_dacte_linha2"]

def test_false_automatic_ok_without_manual_approval_is_still_blocked() -> None:
    guard = FinalCompactRenderGuard()
    validation = {
        "status": "OK",
        "esperado": 100.00,
        "valor_comparado": 103.49,
        "diferenca": 3.49,
        "tolerancia": 1.00,
        "controle_dacte_regra": "TESTE",
        "controle_dacte_linha1": "Cálculo automático",
        "controle_dacte_linha2": "Diferença R$ 3,49 | Validação: OK",
        "controle_dacte_compacto": "SIM",
    }
    info = {"tipo": "CT-e", "numero": "22066", "validacao": validation}

    with pytest.raises(CompactConsistencyError):
        guard.prepare_infos([info], strict=True)


def test_manual_approval_justification_is_rendered_with_compact_block() -> None:
    guard = FinalCompactRenderGuard()
    overlay = CompactControlOverlay()
    info = {"tipo": "CT-e", "numero": "22066", "valor": "103,49", "validacao": _manual_validation()}
    prepared = guard.prepare_infos([info], strict=True)[0]

    html = overlay.build(prepared)
    assert "CONTROLE INTERNO" in html
    assert "OK MANUAL" in html
    assert "JUSTIFICATIVA DA APROVAÇÃO" in html
    assert "Autorizado devido a ajuste comercial documentado" in html
    assert "Desenvolvedor" in html
    assert "2026-09-01T13:55:00-03:00" in html


def test_dacte_hydrates_manual_decision_from_canonical_store_for_old_rows(tmp_path: Path) -> None:
    service = OfficialDacteService(tmp_path, tmp_path / "out", tmp_path / "state", _FakeXmlService())
    path = tmp_path / "cte.xml"
    path.write_text("<xml/>", encoding="utf-8")
    stored = {
        "status": "OK MANUAL",
        "manual_reason": "Baixa manual autorizada pelo responsável operacional",
        "manual_decided_at": "2026-09-01T14:00:00-03:00",
    }
    base_validation = {
        "status": "DIVERGENTE +",
        "esperado": 100.00,
        "valor_comparado": 103.49,
        "diferenca": 3.49,
        "tolerancia": 1.00,
    }

    hydrated = service._hydrate_manual_validation(stored, {"numero": "22066"}, path, base_validation)

    assert hydrated["status"] == "OK MANUAL"
    assert hydrated["revisao_manual"] == "APROVADO"
    assert hydrated["observacao_manual"] == "Baixa manual autorizada pelo responsável operacional"
    assert hydrated["manual_decision"]["decision"] == "approved"
    assert hydrated["manual_decision"]["actor_name"] == "Desenvolvedor"
