# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from engine.central_cte_modular.commercial.compact_render_guard import FinalCompactRenderGuard
from engine.central_cte_modular.rendering.overlays.compact_control import CompactControlOverlay
from web_local.services.official_dacte_service import OfficialDacteService


class _OldRowXmlService:
    @staticmethod
    def _decision_for(info, path):
        # Simula uma fotografia antiga em que o JSON canônico não é mais
        # encontrado, mas a própria linha persistida registra a baixa manual.
        return "cte:old", None

    @staticmethod
    def _apply_manual_decision(validation, decision):
        result = dict(validation)
        if str(decision.get("decision") or "").lower() == "approved":
            result["status"] = "OK MANUAL"
            result["revisao_manual"] = "APROVADO"
        result["observacao_manual"] = str(decision.get("reason") or "")
        result["revisao_data"] = str(decision.get("decided_at") or "")
        result["manual_decision"] = dict(decision)
        return result


def _base_validation() -> dict:
    return {
        "status": "DIVERGENTE +",
        "automatic_status": "DIVERGENTE +",
        "automatic_expected_value": 100.0,
        "automatic_difference": 3.49,
        "esperado": 100.0,
        "valor_comparado": 103.49,
        "diferenca": 3.49,
        "tolerancia": 1.0,
        "partner_id": "PARCEIRO_TESTE",
        "trace": [],
    }


def test_old_persisted_ok_manual_is_recovered_without_canonical_decision(tmp_path: Path) -> None:
    service = OfficialDacteService(tmp_path, tmp_path / "out", tmp_path / "state", _OldRowXmlService())
    xml = tmp_path / "cte22066.xml"
    xml.write_text("<xml/>", encoding="utf-8")
    stored = {
        "status": "OK MANUAL",
        "manual_reason": "Aprovado manualmente pelo responsável após conferência",
        "manual_decided_at": "2026-09-01T15:10:00-03:00",
    }

    hydrated = service._hydrate_manual_validation(stored, {"numero": "22066"}, xml, _base_validation())
    prepared = service._prepare_manual_compact_for_render(
        {"numero": "22066", "tipo": "CT-e", "valor": "103,49"}, hydrated, include_compact=True
    )

    assert prepared["status"] == "OK MANUAL"
    assert prepared["baixa_manual_aplicada"] is True
    assert prepared["controle_dacte_status"] == "OK MANUAL"
    assert prepared["controle_dacte_inconsistente"] is False
    assert prepared["controle_dacte_justificativa"] == "Aprovado manualmente pelo responsável após conferência"


def test_signed_render_double_guard_does_not_reblock_manual_cte() -> None:
    guard = FinalCompactRenderGuard()
    validation = _base_validation()
    validation.update({
        "status": "OK MANUAL",
        "status_final_persistido": "OK MANUAL",
        "baixa_manual_aplicada": True,
        "revisao_manual": "APROVADO",
        "observacao_manual": "Baixa manual documentada",
        "controle_dacte_justificativa": "Baixa manual documentada",
    })
    info = {"numero": "22066", "tipo": "CT-e", "valor": "103,49", "validacao": validation}

    # Primeiro preparo feito pelo serviço DACTE e segundo preparo feito pelo
    # render_document chamado novamente pelo fluxo de assinatura.
    first = guard.prepare_infos([info], strict=True)[0]
    second = guard.prepare_infos([first], strict=True)[0]

    final = second["validacao"]
    assert final["controle_dacte_status"] == "OK MANUAL"
    assert final["controle_dacte_inconsistente"] is False
    assert final["controle_dacte_diferenca"] == 3.49


def test_manual_compact_always_renders_justification_section() -> None:
    guard = FinalCompactRenderGuard()
    overlay = CompactControlOverlay()
    validation = _base_validation()
    validation.update({
        "status": "OK MANUAL",
        "baixa_manual_aplicada": True,
        "status_final_persistido": "OK MANUAL",
        "revisao_manual": "APROVADO",
        "controle_dacte_justificativa": "Conferido e liberado manualmente",
        "controle_dacte_responsavel_manual": "Operador Teste",
        "controle_dacte_data_manual": "2026-09-01T15:20:00-03:00",
    })
    info = {"numero": "22066", "tipo": "CT-e", "valor": "103,49", "validacao": validation}
    prepared = guard.prepare_infos([info], strict=True)[0]
    html = overlay.build(prepared)

    assert "CONTROLE INTERNO" in html
    assert "OK MANUAL" in html
    assert "JUSTIFICATIVA DA APROVAÇÃO" in html
    assert "Conferido e liberado manualmente" in html
    assert "Operador Teste" in html


def test_local_launcher_restarts_stale_version() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / "00_INICIAR_LOCAL_ONLINE.ps1").read_text(encoding="utf-8-sig")
    assert '$ExpectedVersion = "RC27.14 WEB/WINDOWS MVP13 R12.13.9"' in script
    assert "Reiniciando servidor antigo" in script
    assert "OwningProcess" in script
