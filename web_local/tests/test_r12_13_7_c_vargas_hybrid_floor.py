# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
import pytest
from engine import central_cte_engine_1_1_36 as engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPILED = PROJECT_ROOT / "web_local" / "data" / "partner_tables" / "cadastro_tabelas_parceiros_compilada.xlsx"

# Matriz real do relatório relatorio_validacao_xml_RC26_6_WEB_20260831_170324.xlsx.
# Todos os 33 CT-es AC LOG / C VARGAS devem conferir pela regra comercial
# híbrida: maior entre percentual da rota, frete-peso e frete mínimo.
CASES = [
    ('50186', 'SANTANA', 434.9, 150.0, 86.98),
    ('50187', 'MACAPA', 1103.71, 379.3, 220.74),
    ('50188', 'SANTANA', 1390.33, 503.0, 278.07),
    ('50189', 'MACAPA', 1558.26, 515.1, 311.65),
    ('50190', 'MACAPA', 914.68, 231.6, 182.94),
    ('50191', 'MACAPA', 1078.0, 328.8, 215.6),
    ('50192', 'MACAPA', 1226.73, 420.0, 245.35),
    ('50193', 'MACAPA', 540.0, 177.0, 108.0),
    ('50194', 'MACAPA', 760.0, 268.61, 152.0),
    ('50195', 'SANTANA', 395.64, 159.6, 79.13),
    ('50196', 'SANTANA', 329.24, 17.64, 65.85),
    ('50197', 'SANTANA', 477.44, 135.0, 95.49),
    ('50198', 'MACAPA', 330.59, 102.0, 66.12),
    ('50199', 'MACAPA', 6230.14, 2375.426, 1246.03),
    ('50200', 'MACAPA', 543.06, 183.0, 108.61),
    ('50201', 'MACAPA', 316.44, 84.0, 63.29),
    ('50202', 'MACAPA', 442.74, 244.0, 89.78),
    ('50203', 'MACAPA', 503.11, 231.0, 100.62),
    ('50204', 'MACAPA', 2446.31, 1222.0, 489.26),
    ('50205', 'MACAPA', 976.7, 475.2, 195.34),
    ('50206', 'MACAPA', 1397.21, 419.13, 279.44),
    ('50207', 'MACAPA', 489.9, 213.0, 97.98),
    ('50208', 'MACAPA', 351.9, 49.928, 70.38),
    ('50209', 'MACAPA', 887.95, 263.79, 177.59),
    ('50211', 'MACAPA', 1825.7, 674.37, 365.14),
    ('50212', 'SANTANA', 1898.4, 890.46, 379.68),
    ('50213', 'MACAPA', 4990.0, 2173.0, 998.0),
    ('50214', 'SANTANA', 582.16, 195.3, 116.43),
    ('50215', 'MACAPA', 289.81, 126.0, 57.96),
    ('50216', 'LARANJAL DO JARI', 2706.98, 960.0, 807.4),
    ('50217', 'MACAPA', 833.12, 192.22, 166.62),
    ('50218', 'MACAPA', 286.12, 53.88, 57.22),
    ('50219', 'MACAPA', 390.06, 35.88, 78.01)
]

TABLES = engine.load_partner_tables(COMPILED)

def _validate(cte: str, city: str, base_freight: float, weight_kg: float, xml_value: float):
    nf = f"9{cte}"
    base_row = {
        "nf": nf,
        "tipo_base": "NORMAL",
        "tipo_doc": "NORMAL",
        "valor_frete": base_freight,
        "valor_frete_planilha": base_freight,
        "origem_cidade": "ANANINDEUA",
        "origem_uf": "PA",
        "destino_cidade": city,
        "destino_uf": "AP",
        "fonte_frete": "PLANILHA",
    }
    info = {
        "tipo": "CT-e",
        "numero": cte,
        "serie": "1",
        "valor": str(xml_value).replace(".", ","),
        "emitente": "C VARGAS LOGISTICA EIRELI",
        "emit": {"cnpjcpf": "34.059.736/0001-57"},
        "docs": [{"n_doc": nf}],
        "peso_base": str(weight_kg).replace(".", ","),
        "componentes": [{"nome": "FRETE VALOR", "valor": str(xml_value).replace(".", ",")}],
    }
    return engine.validate_cte_value(info, {"index": {nf: [base_row]}}, TABLES)

@pytest.mark.parametrize("cte,city,base_freight,weight_kg,xml_value", CASES)
def test_real_report_matrix_uses_hybrid_floor(cte, city, base_freight, weight_kg, xml_value):
    result = _validate(cte, city, base_freight, weight_kg, xml_value)
    assert result["status"] == "OK AC LOG / C VARGAS", (cte, result.get("status"), result.get("trace"))
    assert result["modo_calculo"] == "HIBRIDO_PERCENTUAL_FRETE_PESO_COMPONENTES"
    assert result["esperado"] == pytest.approx(xml_value, abs=0.01)
    assert abs(float(result["diferenca"])) <= 0.01
    assert result["criterio_frete_aplicado"] in {"PERCENTUAL", "FRETE_PESO", "FRETE_MINIMO"}

def test_percentage_can_win_over_frete_peso():
    result = _validate("50186", "SANTANA", 434.90, 150.0, 86.98)
    assert result["criterio_frete_aplicado"] == "PERCENTUAL"
    assert result["frete_percentual_calculado"] == pytest.approx(86.98, abs=0.01)
    assert result["frete_peso_referencia"] == pytest.approx(55.19, abs=0.01)

def test_frete_peso_can_win_over_percentage():
    result = _validate("50202", "MACAPA", 442.74, 244.0, 89.78)
    assert result["criterio_frete_aplicado"] == "FRETE_PESO"
    assert result["frete_percentual_calculado"] == pytest.approx(88.55, abs=0.01)
    assert result["frete_peso_referencia"] == pytest.approx(89.78, abs=0.01)

def test_minimum_can_win_over_both():
    result = _validate("59999", "MACAPA", 100.0, 10.0, 28.39)
    assert result["status"] == "OK AC LOG / C VARGAS"
    assert result["criterio_frete_aplicado"] == "FRETE_MINIMO"
    assert result["esperado"] == pytest.approx(28.39, abs=0.01)

def test_atacadao_name_does_not_override_c_vargas_commercial_rule():
    result = _validate("50203", "MACAPA", 503.11, 231.0, 100.62)
    assert result["status"] == "OK AC LOG / C VARGAS"
    assert result["criterio_frete_aplicado"] == "PERCENTUAL"
    assert result["esperado"] == pytest.approx(100.62, abs=0.01)
