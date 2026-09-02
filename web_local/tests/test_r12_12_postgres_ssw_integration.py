from __future__ import annotations

import gzip
import json
from pathlib import Path

from web_local.services.ssw_postgres_service import SswPostgresService, normalize_db_row


def sample_raw(**overrides):
    row = {
        "serie_numero_ctrc": "BNU036301-4",
        "serie_numero_ct_e": "1000035934",
        "tipo_do_documento": "NORMAL",
        "data_de_emissao": "2026-01-27T00:00:00",
        "data_de_autorizacao": "2026-01-28T00:00:00",
        "chave_ct_e": "42260108408736000881570010000359341000188081",
        "cnpj_remetente": "08.408.736/0001-05",
        "cnpj_pagador": "08.408.736/0001-05",
        "cnpj_destinatario": "24.118.660/0002-10",
        "cnpj_recebedor": "24.118.660/0002-10",
        "numero_da_nota_fiscal": "000434493",
        "valor_da_mercadoria": "4.153,24",
        "valor_do_frete": "366,65",
        "valor_do_frete_sem_icms": "340,98",
        "cidade_de_entrega": "SANTAREM",
        "uf_de_entrega": "PA",
        "cidade_origem_da_prestacao": "BRUSQUE",
        "uf_origem_da_prestacao": "SC",
        "tipo_de_baixa": "LIQUIDADO",
        "data_da_liquidacao": "2026-02-20T00:00:00",
        "frete_peso": 299.56,
        "frete_valor": 8.31,
        "despacho": 15,
        "gris": 8.31,
        "pedagio": 9.80,
        "tda": 0,
        "outros": 0,
        "data_do_cancelamento": None,
        "motivo_do_cancelamento": None,
        "arquivo_origem": "455-012026.xls",
        "data_carga": "2026-08-18T15:17:36",
    }
    row.update(overrides)
    return row


def test_normalize_db_row_contract():
    row = normalize_db_row(sample_raw())
    assert row["nf"] == "434493"
    assert row["cte"] == "1000035934"
    assert len(row["chave"]) == 44
    assert row["valor_frete"] == 366.65
    assert row["valor_frete_sem_icms"] == 340.98
    assert row["cnpj_remetente"] == "08408736000105"
    assert row["arquivo_origem"] == "455-012026.xls"


def test_bridge_token_and_snapshot_roundtrip(tmp_path: Path):
    service = SswPostgresService(tmp_path)
    token = service.rotate_bridge_token()
    assert token.startswith("cte_")
    assert service.verify_bridge_token(token)
    assert not service.verify_bridge_token(token + "x")

    meta = service.publish_snapshot({
        "source": "staging.stg_ssw_455_fretes",
        "transport": "bridge",
        "generated_at": "2026-08-18T16:00:00-03:00",
        "rows": [sample_raw()],
    })
    assert meta["row_count"] == 1
    assert meta["arquivo_origem_count"] == 1
    assert meta["official_base_unchanged"] is True
    status = service.public_status()
    assert status["mode"] == "sombra"
    assert status["read_only"] is True
    assert status["snapshot"]["row_count"] == 1


def test_bridge_gzip_decode(tmp_path: Path):
    service = SswPostgresService(tmp_path)
    payload = {"source": "staging.stg_ssw_455_fretes", "rows": [sample_raw()]}
    body = gzip.compress(json.dumps(payload).encode("utf-8"))
    decoded = service.decode_bridge_payload(body, "gzip")
    assert decoded["source"] == "staging.stg_ssw_455_fretes"
    assert len(decoded["rows"]) == 1


def test_compare_is_shadow_only(tmp_path: Path):
    service = SswPostgresService(tmp_path)
    service.publish_snapshot({"source": "staging.stg_ssw_455_fretes", "rows": [sample_raw()]})
    pg = normalize_db_row(sample_raw())
    base = {
        "nf": pg["nf"],
        "cte": pg["cte"],
        "chave": pg["chave"],
        "valor_frete": 366.65,
    }
    result = service.compare_with_base_rows([base])
    assert result["matched"] == 1
    assert result["freight_equal"] == 1
    assert result["freight_compatibility_percent"] == 100.0
    assert result["promotion_allowed"] is False
