# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from engine.central_cte_modular.commercial.commercial_engine import (
    CommercialDependencies,
    ModularCommercialEngine,
)
from engine.central_cte_modular.repositories.partner_table_repository import (
    PartnerTableRepository,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLE_ROOT = PROJECT_ROOT / "web_local" / "data" / "partner_tables"
COMPILED = TABLE_ROOT / "cadastro_tabelas_parceiros_compilada.xlsx"


def _norm_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text.upper()).strip()


def _commercial_engine() -> ModularCommercialEngine:
    return ModularCommercialEngine(
        CommercialDependencies(
            norm_text=_norm_text,
            only_digits=lambda value: re.sub(r"\D+", "", str(value or "")),
            parse_number_br=lambda value: float(value or 0),
            normalize_nf=lambda value: re.sub(r"\D+", "", str(value or "")),
            partner_policy=lambda _partner_id: {},
        )
    )


def _route(city: str, state: str = "AP") -> dict[str, str]:
    return {
        "origem_cidade": "ANANINDEUA",
        "origem_uf": "PA",
        "destino_cidade": city,
        "destino_uf": state,
    }


def test_release_version_is_current() -> None:
    server = (PROJECT_ROOT / "web_local" / "server.py").read_text(encoding="utf-8")
    app_js = (PROJECT_ROOT / "web_local" / "static" / "app.js").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "deploy" / "vps" / "compose.yaml").read_text(encoding="utf-8")
    assert "MVP13 R12.13" in server
    assert "MVP13 R12.13" in app_js
    assert "central-cte-dacte:r12.13" in compose


def test_sources_and_individual_tables_are_preserved() -> None:
    expected = (
        PROJECT_ROOT / "fontes" / "TABELA_DISTRIB_AP_RODOVITOR_2026_A4.xlsx",
        PROJECT_ROOT / "fontes" / "TABELA_AC_LOG_C_VARGAS_DISTRIBUICAO_AP_2025.pdf",
        PROJECT_ROOT / "_internal" / "fontes" / "TABELA_DISTRIB_AP_RODOVITOR_2026_A4.xlsx",
        PROJECT_ROOT / "_internal" / "fontes" / "TABELA_AC_LOG_C_VARGAS_DISTRIBUICAO_AP_2025.pdf",
        TABLE_ROOT / "files" / "OPAL.xlsx",
        TABLE_ROOT / "files" / "AC_LOG_C_VARGAS.xlsx",
    )
    assert all(path.is_file() and path.stat().st_size > 0 for path in expected)


def test_compiled_table_contains_both_partners_and_expected_counts() -> None:
    tables = PartnerTableRepository().load(COMPILED)
    assert len(tables["partners"]) == 16
    assert len(tables["rules"]) == 289
    assert len(tables["regions"]) == 390
    assert len(tables["extras"]) == 104
    assert "OPAL" in tables["partners"]
    assert "AC_LOG_C_VARGAS" in tables["partners"]
    assert tables["partners"]["AC_LOG_C_VARGAS"].get("cnpj", "") == "34059736000157"


def test_partner_aliases_identify_ac_log_c_vargas_and_opal() -> None:
    tables = PartnerTableRepository().load(COMPILED)
    engine = _commercial_engine()
    for name in ("AC LOG", "C VARGAS", "AC LOG / C VARGAS"):
        assert engine.identify_partner({"emitente": name, "emit": {}}, tables) == "AC_LOG_C_VARGAS"
    assert engine.identify_partner(
        {"emitente": "", "emit": {"cnpjcpf": "34.059.736/0001-57"}},
        tables,
    ) == "AC_LOG_C_VARGAS"
    assert (
        engine.identify_partner(
            {"emitente": "OPAL - ORGANIZACAO PARAENSE EIRELI ME", "emit": {}},
            tables,
        )
        == "OPAL"
    )


def test_ac_log_exact_routes_keep_percent_minimum_frete_peso_and_gris() -> None:
    tables = PartnerTableRepository().load(COMPILED)
    engine = _commercial_engine()

    macapa = engine.choose_partner_rule("AC_LOG_C_VARGAS", _route("MACAPA"), tables)
    assert macapa is not None
    assert macapa["percent"] == 0.20
    assert macapa["minimum"] == 28.39
    assert macapa["ton_rate"] == 367.96
    assert macapa["ton_rate"] / 1000 == pytest.approx(0.36796)
    assert 315 * (macapa["ton_rate"] / 1000) == pytest.approx(115.9074)
    assert macapa["percentual_gris"] == 0.002

    oiapoque = engine.choose_partner_rule("AC_LOG_C_VARGAS", _route("OIAPOQUE"), tables)
    assert oiapoque is not None
    assert oiapoque["percent"] == 0.23
    assert oiapoque["minimum"] == 36.80
    assert oiapoque["ton_rate"] == 1103.87
    assert oiapoque["ton_rate"] / 1000 == pytest.approx(1.10387)
    assert 315 * (oiapoque["ton_rate"] / 1000) == pytest.approx(347.71905)
    assert oiapoque["percentual_gris"] == 0.002


def test_opal_exact_routes_override_generic_interior_rule() -> None:
    tables = PartnerTableRepository().load(COMPILED)
    engine = _commercial_engine()

    macapa = engine.choose_partner_rule("OPAL", _route("MACAPA"), tables)
    santana = engine.choose_partner_rule("OPAL", _route("SANTANA"), tables)
    interior = engine.choose_partner_rule("OPAL", _route("CALCOENE"), tables)
    afua = engine.choose_partner_rule("OPAL", _route("AFUA", "PA"), tables)
    chaves = engine.choose_partner_rule("OPAL", _route("CHAVES", "PA"), tables)

    assert macapa and macapa["percent"] == 0.28 and macapa["minimum"] == 90.0
    assert santana and santana["percent"] == 0.28 and santana["minimum"] == 90.0
    assert interior and interior["percent"] == 0.33 and interior["minimum"] == 120.0
    assert afua and afua["percent"] == 0.07 and afua["minimum"] == 120.0
    assert chaves and chaves["percent"] == 0.07 and chaves["minimum"] == 120.0
    assert afua["base_calculo"] == "MERCADORIA"
    assert chaves["base_calculo"] == "MERCADORIA"


def test_progressive_polo_tiers_remain_manual_extras_not_normal_rules() -> None:
    tables = PartnerTableRepository().load(COMPILED)
    ac_rules = [rule for rule in tables["rules"] if rule.get("partner_id") == "AC_LOG_C_VARGAS"]
    ac_extras = [extra for extra in tables["extras"] if extra.get("partner_id") == "AC_LOG_C_VARGAS"]

    assert len(ac_rules) == 19
    assert not any("POLO" in _norm_text(rule.get("regiao", "")) for rule in ac_rules)
    polo = [
        extra
        for extra in ac_extras
        if "POLO" in _norm_text(extra.get("tipo_extra", ""))
        or "POLO" in _norm_text(extra.get("raw", {}).get("REGRADESCRICAO", ""))
    ]
    assert len(polo) == 3
    assert all("REVISAR_AUTOMACAO" in _norm_text(extra.get("status_revisao", "")) for extra in polo)
