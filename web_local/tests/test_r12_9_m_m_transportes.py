from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from engine.central_cte_modular.commercial.commercial_engine import (
    CommercialDependencies,
    ModularCommercialEngine,
)
from engine.central_cte_modular.commercial.cte_classification import detectar_cobranca_extra
from engine.central_cte_modular.repositories.partner_table_repository import PartnerTableRepository
from web_local.services.engine_xml_service import OfficialXmlEngineService

ROOT = Path(__file__).resolve().parents[2]
TABLE_ROOT = ROOT / "web_local" / "data" / "partner_tables"
COMPILED = TABLE_ROOT / "cadastro_tabelas_parceiros_compilada.xlsx"


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.upper().split())


def _engine() -> ModularCommercialEngine:
    return ModularCommercialEngine(
        CommercialDependencies(
            norm_text=_norm,
            only_digits=lambda value: re.sub(r"\D+", "", str(value or "")),
            parse_number_br=lambda value: float(value or 0),
            normalize_nf=lambda value: re.sub(r"\D+", "", str(value or "")),
            partner_policy=lambda _partner_id: {},
        )
    )


def test_release_r12_9_is_published() -> None:
    server = (ROOT / "web_local" / "server.py").read_text(encoding="utf-8")
    app = (ROOT / "web_local" / "static" / "app.js").read_text(encoding="utf-8")
    compose = (ROOT / "deploy" / "vps" / "compose.yaml").read_text(encoding="utf-8")
    assert "MVP13 R12.13" in server
    assert "MVP13 R12.13" in app
    assert "central-cte-dacte:r12.13" in compose


def test_m_m_partner_is_published_with_cnpj_aliases_and_counts() -> None:
    tables = PartnerTableRepository().load(COMPILED)
    assert len(tables["partners"]) == 16
    assert len(tables["rules"]) == 289
    assert len(tables["regions"]) == 390
    assert len(tables["extras"]) == 104

    partner = tables["partners"]["M_M_TRANSPORTES"]
    assert partner["cnpj"] == "59339996000107"
    engine = _engine()
    assert engine.identify_partner(
        {"emitente": "M E M TRANSPORTES LTDA", "emit": {"cnpjcpf": "59.339.996/0001-07"}},
        tables,
    ) == "M_M_TRANSPORTES"
    assert engine.identify_partner({"emitente": "M&M TRANSPORTES", "emit": {}}, tables) == "M_M_TRANSPORTES"


def test_m_m_rules_match_full_official_city_names_without_fiscal_origin_restriction() -> None:
    tables = PartnerTableRepository().load(COMPILED)
    engine = _engine()
    for city in ("SAO DOMINGOS DO ARAGUAIA", "SAO GERALDO DO ARAGUAIA"):
        rule = engine.choose_partner_rule(
            "M_M_TRANSPORTES",
            {
                "origem_cidade": "CAMBORIU",
                "origem_uf": "SC",
                "destino_cidade": city,
                "destino_uf": "PA",
            },
            tables,
        )
        assert rule is not None
        assert rule["percent"] == pytest.approx(0.35)
        assert rule["minimum"] == pytest.approx(70.0)
        assert not rule.get("origem_cidade")
        assert not rule.get("origem_uf")


def test_standard_examples_close_with_35_percent_or_minimum() -> None:
    examples = [
        (267.66, 93.68),
        (921.29, 322.45),
        (327.94, 114.78),
        (180.00, 70.00),
        (242.86, 85.00),
    ]
    for base, charged in examples:
        expected = round(max(base * 0.35, 70.0), 2)
        assert expected == pytest.approx(charged, abs=0.01)


def test_m_m_special_quotes_are_separated_but_plain_cot_lais_stays_normal() -> None:
    normal = detectar_cobranca_extra({"obs": "COT. LAIS Transporte subcontratado pela Rodovitor", "componentes": []})
    authorized = detectar_cobranca_extra({"obs": "COTACAO - AUTORIZADA VIA E-MAIL (MAIARA MELO)", "componentes": []})
    special = detectar_cobranca_extra({"obs": "FRETE REF.ANDAIMES,COT. LAIS", "componentes": []})
    assert normal["tipo"] == "NORMAL"
    assert authorized["tipo"] == "COTACAO_AUTORIZADA"
    assert special["tipo"] == "COTACAO_ESPECIAL"


def test_m_m_special_quote_requires_manual_authorization_without_false_divergence() -> None:
    automatic = {
        "partner_id": "M_M_TRANSPORTES",
        "tipo_cobranca": "COTACAO_AUTORIZADA",
        "status": "DIVERGENTE +",
        "esperado": 348.50,
        "diferenca": 630.19,
        "trace": [],
    }
    result = OfficialXmlEngineService._apply_operational_authorization_policy(automatic, {})
    assert result["status"] == "EXTRA — AGUARDANDO AUTORIZAÇÃO"
    assert result["requires_manual_authorization"] is True
    assert result["authorization_status"] == "PENDENTE"
    assert result["authorization_evidence_in_xml"] is True
    assert result["esperado"] is None
    assert result["diferenca"] is None
    assert result["engine_status"] == "DIVERGENTE +"


def test_seed_and_source_files_are_included() -> None:
    expected = [
        TABLE_ROOT / "files" / "M_M_TRANSPORTES.xlsx",
        ROOT / "deploy" / "vps" / "seed" / "partner_tables" / "files" / "M_M_TRANSPORTES.xlsx",
        ROOT / "fontes" / "TABELA_M_E_M_TRANSPORTES_ROTA1_2026.pdf",
        ROOT / "_internal" / "fontes" / "TABELA_M_E_M_TRANSPORTES_ROTA1_2026.pdf",
    ]
    assert all(path.is_file() and path.stat().st_size > 0 for path in expected)
    seed_version = (ROOT / "deploy" / "vps" / "seed" / "partner_tables" / "release_seed_version.txt").read_text(encoding="utf-8")
    assert "R12.10" in seed_version
    signature = (ROOT / "deploy" / "vps" / "seed" / "partner_tables" / "compiled_signature.txt").read_text(encoding="utf-8")
    assert "M_M_TRANSPORTES.xlsx" in signature
