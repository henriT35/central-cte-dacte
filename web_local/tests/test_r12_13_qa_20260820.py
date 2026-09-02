from __future__ import annotations

from pathlib import Path

import pytest

from engine.central_cte_modular.rendering.overlays.compact_control import CompactControlOverlay
from web_local.services.engine_xml_service import OfficialXmlEngineService

ROOT = Path(__file__).resolve().parents[2]


def test_release_r1213_is_published_without_changing_engine_contract() -> None:
    server = (ROOT / "web_local/server.py").read_text(encoding="utf-8")
    app = (ROOT / "web_local/static/app.js").read_text(encoding="utf-8")
    compose = (ROOT / "deploy/vps/compose.yaml").read_text(encoding="utf-8")
    assert "MVP13 R12.13" in server
    assert "MVP13 R12.13" in app
    assert "central-cte-dacte:r12.13" in compose
    assert 'ENGINE_VERSION = "RC26.6"' in server


def test_ws_estadia_is_separated_for_manual_authorization() -> None:
    automatic = {
        "partner_id": "W_S_TRANSPORTES",
        "tipo_cobranca": "NORMAL",
        "status": "DIVERGENTE -",
        "esperado": 599.85,
        "diferenca": -249.85,
        "trace": [],
    }
    info = {"obs": "CTRC emitido para cobrança de custo de ESTADIA de veículo"}
    result = OfficialXmlEngineService._apply_operational_authorization_policy(automatic, info)
    assert result["tipo_cobranca"] == "ESTADIA"
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["requires_manual_authorization"] is True
    assert result["engine_status"] == "DIVERGENTE -"
    assert result["esperado"] is None
    assert result["diferenca"] is None


def test_c_vargas_cost_extra_does_not_publish_false_table_divergence() -> None:
    automatic = {
        "partner_id": "AC_LOG_C_VARGAS",
        "tipo_cobranca": "NORMAL",
        "status": "DIVERGENTE +",
        "esperado": 1210.55,
        "diferenca": 1090.55,
        "trace": [],
    }
    info = {
        "obs": "SEPARACAO DE NF AUTORIZADO POR BIANCA",
        "uso_exclusivo": "TIPO MERCAD: CUSTO EXTRA. Conferente: ADRIANE",
    }
    result = OfficialXmlEngineService._apply_operational_authorization_policy(automatic, info)
    assert result["tipo_cobranca"] == "CUSTO_EXTRA"
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["authorization_evidence_in_xml"] is True
    assert result["engine_status"] == "DIVERGENTE +"


def test_jsp_taxa_dedicado_is_manual_special_charge() -> None:
    automatic = {
        "partner_id": "JSP",
        "tipo_cobranca": "NORMAL",
        "status": "DIVERGENTE +",
        "esperado": 111.61,
        "diferenca": 98.39,
        "trace": [],
    }
    info = {"obs": "CTE COMPLEMENTAR REF A TAXA DE DEDICADO DA NF 368417"}
    result = OfficialXmlEngineService._apply_operational_authorization_policy(automatic, info)
    assert result["tipo_cobranca"] == "VEICULO_DEDICADO"
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["engine_expected_value"] == pytest.approx(111.61)
    assert result["engine_difference"] == pytest.approx(98.39)


def _grauna_tables() -> dict:
    return {
        "tolerance": 1.0,
        "extras": [
            {
                "partner_id": "GRAUNA_TRANSPORTES",
                "tipo_extra": "REDE_ATACADAO_VALE",
                "percent": 0.40,
            }
        ],
        "peso_especial": [
            {
                "partner_id": "GRAUNA_TRANSPORTES",
                "peso_min_kg": 120.0,
                "percent": 0.30,
                "minimum": 0.0,
                "base_calculo": "ORIGINAL",
                "observacao": "Operacional homologado: acima de 120 kg = 30%; proposta original registra R$ 0,80/kg.",
                "raw": {"REGRAID": "GRAUNA_ACIMA_120KG", "PERCENTUAL": "30%", "VALORKG": "0.80"},
            }
        ],
    }


def test_grauna_atacadao_uses_special_contract_memory_and_manual_gate() -> None:
    automatic = {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "DIVERGENTE +",
        "base_frete": 449.37,
        "valor_comparado": 179.75,
        "esperado": 125.8236,
        "diferenca": 53.93,
        "trace": [],
    }
    info = {"dest": {"nome": "ATACADAO SA"}, "valor": "179.75"}
    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, info, _grauna_tables())
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["special_contract_percent"] == pytest.approx(0.40)
    assert result["special_contract_expected"] == pytest.approx(179.75, abs=0.01)
    assert result["engine_status"] == "DIVERGENTE +"
    assert result["esperado"] is None
    assert result["diferenca"] is None


def test_grauna_weight_rule_is_shadow_and_cannot_define_official_ok() -> None:
    automatic = {
        "partner_id": "GRAUNA_TRANSPORTES",
        "status": "OK",
        "regra_peso_especial": "SIM",
        "peso_base_kg": 297.0,
        "valor_comparado": 241.37,
        "base_frete": 804.55,
        "percentual": 0.30,
        "esperado": 241.37,
        "diferenca": 0.0,
        "trace": [],
    }
    result = OfficialXmlEngineService._apply_web_contract_adapters(automatic, {"valor": "241.37"}, _grauna_tables())
    assert result["status"] == "REVISAR — REGRA >120 KG EM SOMBRA"
    assert result["esperado"] is None
    assert result["diferenca"] is None
    assert result["shadow_weight_active"] is True
    assert result["shadow_weight_match"] is True
    assert result["shadow_weight_expected"] == pytest.approx(241.37)
    assert result["engine_status"] == "OK"


def test_qa_1787247518979_manual_approval_reason_is_inside_compact_pdf_block() -> None:
    overlay = CompactControlOverlay()
    html = overlay.build({
        "validacao": {
            "controle_dacte_compacto": "SIM",
            "controle_dacte_regra": "AUTORIZAÇÃO",
            "controle_dacte_linha1": "Cobrança especial",
            "controle_dacte_linha2": "Aprovada manualmente",
            "controle_dacte_status": "OK EXTRA AUTORIZADO",
            "revisao_manual": "APROVADO",
            "observacao_manual": "Autorizado por e-mail <financeiro>",
            "manual_decision": {
                "decision": "approved",
                "actor_name": "Desenvolvedor",
                "decided_at": "2026-08-20T14:00:00-03:00",
            },
        }
    })
    assert "JUSTIFICATIVA DA APROVAÇÃO" in html
    assert "Autorizado por e-mail &lt;financeiro&gt;" in html
    assert "<financeiro>" not in html


def test_grauna_partner_file_keeps_value_kg_reference_and_operational_percent() -> None:
    table = ROOT / "web_local/data/partner_tables/files/GRAUNA_TRANSPORTES.xlsx"
    seed = ROOT / "deploy/vps/seed/partner_tables/files/GRAUNA_TRANSPORTES.xlsx"
    assert table.is_file() and seed.is_file()
    developer_tools = (ROOT / "web_local/developer_tools.py").read_text(encoding="utf-8")
    assert '"VALORKG"' in developer_tools
    assert '"Valor KG"' in developer_tools
    from engine.central_cte_modular.repositories.partner_table_repository import PartnerTableRepository
    tables = PartnerTableRepository().load(table)
    rule = next(row for row in tables["peso_especial"] if row.get("partner_id") == "GRAUNA_TRANSPORTES")
    assert rule["percent"] == pytest.approx(0.30)
    assert "R$ 0,80/kg" in rule["observacao"]
