# -*- coding: utf-8 -*-
from __future__ import annotations

import gzip
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SERVICE_VERSION = "R12.12-postgres-shadow-v1"
DEFAULT_SCHEMA = "staging"
DEFAULT_TABLE = "stg_ssw_455_fretes"
MAX_SNAPSHOT_ROWS = 300_000
MAX_SNAPSHOT_JSON_BYTES = 180 * 1024 * 1024
IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

DB_COLUMNS = (
    "serie_numero_ctrc",
    "serie_numero_ct_e",
    "tipo_do_documento",
    "data_de_emissao",
    "data_de_autorizacao",
    "chave_ct_e",
    "cnpj_remetente",
    "cnpj_pagador",
    "cnpj_destinatario",
    "cnpj_recebedor",
    "numero_da_nota_fiscal",
    "valor_da_mercadoria",
    "valor_do_frete",
    "valor_do_frete_sem_icms",
    "cidade_de_entrega",
    "uf_de_entrega",
    "cidade_origem_da_prestacao",
    "uf_origem_da_prestacao",
    "tipo_de_baixa",
    "data_da_liquidacao",
    "frete_peso",
    "frete_valor",
    "despacho",
    "gris",
    "pedagio",
    "tda",
    "outros",
    "data_do_cancelamento",
    "motivo_do_cancelamento",
    "arquivo_origem",
    "data_carga",
)

SNAPSHOT_FIELDS = (
    "nf",
    "cte",
    "ctrc",
    "chave",
    "tipo_doc",
    "valor_frete",
    "valor_frete_sem_icms",
    "valor_mercadoria",
    "destino_cidade",
    "destino_uf",
    "origem_cidade",
    "origem_uf",
    "cnpj_remetente",
    "cnpj_destinatario",
    "cnpj_pagador",
    "cnpj_recebedor",
    "tipo_baixa",
    "data_emissao",
    "data_autorizacao",
    "data_liquidacao",
    "data_cancelamento",
    "motivo_cancelamento",
    "frete_peso",
    "frete_valor",
    "despacho",
    "gris",
    "pedagio",
    "tda",
    "outros",
    "arquivo_origem",
    "data_carga",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _text(value: Any, max_len: int = 300) -> str:
    value = str(value or "").replace("\x00", "").strip()
    return value[:max_len]


def _number(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip().replace("R$", "").replace(" ", "")
    if not raw:
        return 0.0
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _date(value: Any) -> str:
    if value in (None, ""):
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return _text(value, 40)


def _normal_nf(value: Any) -> str:
    digits = _digits(value)
    if digits:
        # O RC26.6 normaliza NFs numericamente; retirar zeros à esquerda preserva a chave lógica.
        return digits.lstrip("0") or "0"
    return _text(value, 80).upper()


def normalize_db_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "nf": _normal_nf(row.get("numero_da_nota_fiscal") if "numero_da_nota_fiscal" in row else row.get("nf")),
        "cte": _text(row.get("serie_numero_ct_e") if "serie_numero_ct_e" in row else row.get("cte"), 80),
        "ctrc": _text(row.get("serie_numero_ctrc") if "serie_numero_ctrc" in row else row.get("ctrc"), 80),
        "chave": _digits(row.get("chave_ct_e") if "chave_ct_e" in row else row.get("chave"))[:44],
        "tipo_doc": _text(row.get("tipo_do_documento") if "tipo_do_documento" in row else row.get("tipo_doc"), 120),
        "valor_frete": _number(row.get("valor_do_frete") if "valor_do_frete" in row else row.get("valor_frete")),
        "valor_frete_sem_icms": _number(row.get("valor_do_frete_sem_icms") if "valor_do_frete_sem_icms" in row else row.get("valor_frete_sem_icms")),
        "valor_mercadoria": _number(row.get("valor_da_mercadoria") if "valor_da_mercadoria" in row else row.get("valor_mercadoria")),
        "destino_cidade": _text(row.get("cidade_de_entrega") if "cidade_de_entrega" in row else row.get("destino_cidade"), 160),
        "destino_uf": _text(row.get("uf_de_entrega") if "uf_de_entrega" in row else row.get("destino_uf"), 8).upper(),
        "origem_cidade": _text(row.get("cidade_origem_da_prestacao") if "cidade_origem_da_prestacao" in row else row.get("origem_cidade"), 160),
        "origem_uf": _text(row.get("uf_origem_da_prestacao") if "uf_origem_da_prestacao" in row else row.get("origem_uf"), 8).upper(),
        "cnpj_remetente": _digits(row.get("cnpj_remetente"))[:14],
        "cnpj_destinatario": _digits(row.get("cnpj_destinatario"))[:14],
        "cnpj_pagador": _digits(row.get("cnpj_pagador"))[:14],
        "cnpj_recebedor": _digits(row.get("cnpj_recebedor"))[:14],
        "tipo_baixa": _text(row.get("tipo_de_baixa") if "tipo_de_baixa" in row else row.get("tipo_baixa"), 100),
        "data_emissao": _date(row.get("data_de_emissao") if "data_de_emissao" in row else row.get("data_emissao")),
        "data_autorizacao": _date(row.get("data_de_autorizacao") if "data_de_autorizacao" in row else row.get("data_autorizacao")),
        "data_liquidacao": _date(row.get("data_da_liquidacao") if "data_da_liquidacao" in row else row.get("data_liquidacao")),
        "data_cancelamento": _date(row.get("data_do_cancelamento") if "data_do_cancelamento" in row else row.get("data_cancelamento")),
        "motivo_cancelamento": _text(row.get("motivo_do_cancelamento") if "motivo_do_cancelamento" in row else row.get("motivo_cancelamento"), 600),
        "frete_peso": _number(row.get("frete_peso")),
        "frete_valor": _number(row.get("frete_valor")),
        "despacho": _number(row.get("despacho")),
        "gris": _number(row.get("gris")),
        "pedagio": _number(row.get("pedagio")),
        "tda": _number(row.get("tda")),
        "outros": _number(row.get("outros")),
        "arquivo_origem": _text(row.get("arquivo_origem"), 180),
        "data_carga": _date(row.get("data_carga")),
    }


def _fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        encoded = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


class SswPostgresService:
    """Integração sombra com o PostgreSQL do SSW.

    R12.12 deliberadamente NÃO substitui a Base SSW oficial. O serviço aceita
    um snapshot lido em modo somente leitura (ponte da LAN ou conexão direta),
    guarda uma fotografia validada e permite compará-la com a Base .sswweb.
    """

    def __init__(self, data_root: Path) -> None:
        self.root = Path(data_root).resolve() / "integrations" / "ssw_postgres"
        self.root.mkdir(parents=True, exist_ok=True)
        self.snapshot_path = self.root / "snapshot.json.gz"
        self.meta_path = self.root / "snapshot_meta.json"
        self.auth_path = self.root / "bridge_auth.json"
        self.direct_status_path = self.root / "direct_status.json"
        self._lock = threading.RLock()

    @staticmethod
    def direct_config() -> dict[str, Any]:
        schema = str(os.environ.get("CENTRAL_CTE_SSW_PG_SCHEMA") or DEFAULT_SCHEMA).strip().lower()
        table = str(os.environ.get("CENTRAL_CTE_SSW_PG_TABLE") or DEFAULT_TABLE).strip().lower()
        if not IDENTIFIER_RE.fullmatch(schema) or not IDENTIFIER_RE.fullmatch(table):
            schema, table = DEFAULT_SCHEMA, DEFAULT_TABLE
        return {
            "enabled": str(os.environ.get("CENTRAL_CTE_SSW_PG_DIRECT_ENABLED") or "0").strip().lower() in {"1", "true", "yes", "on"},
            "host": str(os.environ.get("CENTRAL_CTE_SSW_PG_HOST") or "").strip(),
            "port": int(os.environ.get("CENTRAL_CTE_SSW_PG_PORT") or 5432),
            "dbname": str(os.environ.get("CENTRAL_CTE_SSW_PG_DBNAME") or "").strip(),
            "user": str(os.environ.get("CENTRAL_CTE_SSW_PG_USER") or "").strip(),
            "password": str(os.environ.get("CENTRAL_CTE_SSW_PG_PASSWORD") or ""),
            "sslmode": str(os.environ.get("CENTRAL_CTE_SSW_PG_SSLMODE") or "prefer").strip(),
            "schema": schema,
            "table": table,
            "connect_timeout": max(2, min(30, int(os.environ.get("CENTRAL_CTE_SSW_PG_CONNECT_TIMEOUT") or 6))),
        }

    def public_status(self) -> dict[str, Any]:
        config = self.direct_config()
        meta = self._read_json(self.meta_path, {})
        auth = self._read_json(self.auth_path, {})
        direct = self._read_json(self.direct_status_path, {})
        return {
            "service_version": SERVICE_VERSION,
            "mode": "sombra",
            "read_only": True,
            "promotes_to_official_base": False,
            "source": f"{config['schema']}.{config['table']}",
            "direct": {
                "enabled": bool(config["enabled"]),
                "configured": bool(config["host"] and config["dbname"] and config["user"]),
                "host": config["host"],
                "port": config["port"],
                "dbname": config["dbname"],
                "user": config["user"],
                "sslmode": config["sslmode"],
                "last_test": direct,
            },
            "bridge": {
                "token_configured": bool(auth.get("token_sha256")),
                "token_rotated_at": str(auth.get("rotated_at") or ""),
            },
            "snapshot": meta if isinstance(meta, dict) else {},
            "message": "Integração PostgreSQL em modo sombra: consulta/snapshot somente leitura; a Base SSW .sswweb continua oficial.",
        }

    def rotate_bridge_token(self) -> str:
        token = "cte_" + secrets.token_urlsafe(40)
        payload = {
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "rotated_at": now_iso(),
        }
        self._write_json_atomic(self.auth_path, payload)
        return token

    def verify_bridge_token(self, token: str) -> bool:
        auth = self._read_json(self.auth_path, {})
        expected = str(auth.get("token_sha256") or "")
        if not expected or not token:
            return False
        actual = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return hmac.compare_digest(expected, actual)

    @staticmethod
    def _read_json(path: Path, fallback: Any) -> Any:
        try:
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return fallback

    @staticmethod
    def _write_json_atomic(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temp.replace(path)

    def _connect(self):
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except Exception as exc:
            raise RuntimeError("Driver PostgreSQL indisponível. Instale psycopg 3 no contêiner.") from exc
        config = self.direct_config()
        if not config["enabled"]:
            raise RuntimeError("Conexão PostgreSQL direta está desativada. Use a ponte local ou habilite CENTRAL_CTE_SSW_PG_DIRECT_ENABLED=1.")
        missing = [name for name in ("host", "dbname", "user", "password") if not config.get(name)]
        if missing:
            raise RuntimeError("Configuração PostgreSQL direta incompleta: " + ", ".join(missing))
        conn = psycopg.connect(
            host=config["host"],
            port=config["port"],
            dbname=config["dbname"],
            user=config["user"],
            password=config["password"],
            sslmode=config["sslmode"],
            connect_timeout=config["connect_timeout"],
            options="-c default_transaction_read_only=on -c statement_timeout=120000",
            row_factory=dict_row,
        )
        conn.autocommit = False
        return conn

    def test_direct(self) -> dict[str, Any]:
        started = datetime.now(timezone.utc)
        config = self.direct_config()
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SHOW transaction_read_only")
                    read_only = str(cur.fetchone().get("transaction_read_only") or "").lower()
                    cur.execute("SELECT current_database() AS database, current_user AS username, version() AS version")
                    info = cur.fetchone()
                    qualified = f"{config['schema']}.{config['table']}"
                    cur.execute(f"SELECT COUNT(*) AS total, MIN(data_de_emissao) AS primeira_emissao, MAX(data_de_emissao) AS ultima_emissao, MAX(data_carga) AS ultima_carga, COUNT(DISTINCT arquivo_origem) AS arquivos_origem FROM {qualified}")
                    stats = cur.fetchone()
                conn.rollback()
            result = {
                "ok": True,
                "checked_at": now_iso(),
                "latency_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1),
                "transaction_read_only": read_only,
                "database": _text(info.get("database"), 120),
                "username": _text(info.get("username"), 120),
                "server_version": _text(info.get("version"), 300),
                "table": qualified,
                "stats": {key: (_date(value) if "emissao" in key or "carga" in key else value) for key, value in dict(stats).items()},
            }
        except Exception as exc:
            result = {
                "ok": False,
                "checked_at": now_iso(),
                "latency_ms": round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 1),
                "error": _text(exc, 800),
            }
        self._write_json_atomic(self.direct_status_path, result)
        return result

    def sync_direct(self, *, max_rows: int = MAX_SNAPSHOT_ROWS) -> dict[str, Any]:
        config = self.direct_config()
        qualified = f"{config['schema']}.{config['table']}"
        max_rows = max(1, min(MAX_SNAPSHOT_ROWS, int(max_rows)))
        columns = ", ".join(DB_COLUMNS)
        rows: list[dict[str, Any]] = []
        with self._connect() as conn:
            with conn.cursor(name="central_cte_ssw_shadow") as cur:
                cur.itersize = 5000
                cur.execute(f"SELECT {columns} FROM {qualified} ORDER BY data_de_emissao, serie_numero_ctrc LIMIT %s", (max_rows,))
                for raw in cur:
                    rows.append(normalize_db_row(raw))
                    if len(rows) >= MAX_SNAPSHOT_ROWS:
                        break
            conn.rollback()
        return self.publish_snapshot({
            "source": qualified,
            "transport": "direct",
            "generated_at": now_iso(),
            "rows": rows,
        })

    @staticmethod
    def decode_bridge_payload(body: bytes, content_encoding: str = "") -> dict[str, Any]:
        if str(content_encoding or "").lower().strip() == "gzip":
            with gzip.GzipFile(fileobj=io.BytesIO(body), mode="rb") as stream:
                raw = stream.read(MAX_SNAPSHOT_JSON_BYTES + 1)
            if len(raw) > MAX_SNAPSHOT_JSON_BYTES:
                raise ValueError("Snapshot PostgreSQL descompactado ultrapassa 180 MB.")
        else:
            raw = body
            if len(raw) > MAX_SNAPSHOT_JSON_BYTES:
                raise ValueError("Snapshot PostgreSQL ultrapassa 180 MB.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Snapshot PostgreSQL não contém JSON UTF-8 válido.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Snapshot PostgreSQL precisa ser um objeto JSON.")
        return payload

    def publish_snapshot(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list):
            raise ValueError("Snapshot PostgreSQL sem lista de registros.")
        if not raw_rows:
            raise ValueError("Snapshot PostgreSQL vazio; publicação recusada.")
        if len(raw_rows) > MAX_SNAPSHOT_ROWS:
            raise ValueError(f"Snapshot PostgreSQL excede {MAX_SNAPSHOT_ROWS} registros.")
        rows: list[dict[str, Any]] = []
        invalid_without_nf = 0
        for raw in raw_rows:
            if not isinstance(raw, Mapping):
                continue
            row = normalize_db_row(raw)
            if not row["nf"]:
                invalid_without_nf += 1
                continue
            rows.append(row)
        if not rows:
            raise ValueError("Snapshot PostgreSQL não possui NFs válidas.")
        source = _text(payload.get("source") or f"{DEFAULT_SCHEMA}.{DEFAULT_TABLE}", 160)
        expected_source = f"{DEFAULT_SCHEMA}.{DEFAULT_TABLE}"
        configured = self.direct_config()
        configured_source = f"{configured['schema']}.{configured['table']}"
        if source not in {expected_source, configured_source}:
            raise ValueError("Fonte PostgreSQL não autorizada para esta integração.")
        arquivos = sorted({row["arquivo_origem"] for row in rows if row["arquivo_origem"]})
        cargas = [row["data_carga"] for row in rows if row["data_carga"]]
        emissoes = [row["data_emissao"] for row in rows if row["data_emissao"]]
        cancelled = sum(1 for row in rows if row["data_cancelamento"] or "CANCEL" in row["tipo_baixa"].upper())
        subc = sum(1 for row in rows if "SUBC" in row["tipo_doc"].upper())
        fingerprint = _fingerprint(rows)
        snapshot = {
            "schema_version": "central-cte-ssw-postgres-shadow-v1",
            "source": source,
            "transport": _text(payload.get("transport") or "bridge", 30),
            "generated_at": _date(payload.get("generated_at")) or now_iso(),
            "received_at": now_iso(),
            "rows": rows,
        }
        encoded = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        if len(encoded) > MAX_SNAPSHOT_JSON_BYTES:
            raise ValueError("Snapshot PostgreSQL normalizado ultrapassa 180 MB.")
        meta = {
            "available": True,
            "source": source,
            "transport": snapshot["transport"],
            "generated_at": snapshot["generated_at"],
            "received_at": snapshot["received_at"],
            "row_count": len(rows),
            "skipped_without_nf": invalid_without_nf,
            "arquivo_origem_count": len(arquivos),
            "arquivo_origem_sample": arquivos[-12:],
            "first_emission": min(emissoes) if emissoes else "",
            "last_emission": max(emissoes) if emissoes else "",
            "last_data_carga": max(cargas) if cargas else "",
            "cancelled_count": cancelled,
            "subc_count": subc,
            "fingerprint_sha256": fingerprint,
            "official_base_unchanged": True,
            "compatibility_warning": (
                "A tabela 455 de fretes não publica os campos de CT-e/CTRC origem usados pelo RC26.6 em alguns SUBC; por isso R12.12 mantém este snapshot em modo sombra."
                if subc else "Snapshot em modo sombra; promoção automática à Base SSW permanece desativada."
            ),
        }
        with self._lock:
            temp = self.snapshot_path.with_suffix(".json.gz.tmp")
            with gzip.open(temp, "wb", compresslevel=6) as stream:
                stream.write(encoded)
            temp.replace(self.snapshot_path)
            self._write_json_atomic(self.meta_path, meta)
        return meta

    def load_snapshot(self) -> dict[str, Any]:
        with self._lock:
            if not self.snapshot_path.is_file():
                raise FileNotFoundError("Nenhum snapshot PostgreSQL foi recebido ainda.")
            try:
                with gzip.open(self.snapshot_path, "rt", encoding="utf-8") as stream:
                    data = json.load(stream)
            except Exception as exc:
                raise ValueError("O snapshot PostgreSQL salvo está corrompido.") from exc
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            raise ValueError("O snapshot PostgreSQL salvo não contém registros.")
        return data

    def compare_with_base_rows(self, base_rows: list[Mapping[str, Any]], *, max_differences: int = 200) -> dict[str, Any]:
        snapshot = self.load_snapshot()
        pg_rows = snapshot.get("rows") or []
        base_by_key: dict[str, list[Mapping[str, Any]]] = {}
        for row in base_rows:
            chave = _digits(row.get("chave"))[:44]
            nf = _normal_nf(row.get("nf"))
            cte = _digits(row.get("cte"))
            key = f"K:{chave}" if len(chave) == 44 else f"N:{nf}|C:{cte}"
            base_by_key.setdefault(key, []).append(row)
        matched = 0
        freight_equal = 0
        freight_different = 0
        missing_in_base = 0
        differences: list[dict[str, Any]] = []
        seen_base_keys: set[str] = set()
        for row in pg_rows:
            chave = _digits(row.get("chave"))[:44]
            nf = _normal_nf(row.get("nf"))
            cte = _digits(row.get("cte"))
            keys = []
            if len(chave) == 44:
                keys.append(f"K:{chave}")
            keys.append(f"N:{nf}|C:{cte}")
            candidates: list[Mapping[str, Any]] = []
            found_key = ""
            for key in keys:
                if base_by_key.get(key):
                    candidates = base_by_key[key]
                    found_key = key
                    break
            if not candidates:
                missing_in_base += 1
                if len(differences) < max_differences:
                    differences.append({"status": "ausente_base_ssw", "nf": nf, "cte": row.get("cte"), "chave": chave, "frete_postgres": row.get("valor_frete")})
                continue
            seen_base_keys.add(found_key)
            matched += 1
            pg_frete = round(_number(row.get("valor_frete")), 2)
            candidate = min(candidates, key=lambda item: abs(round(_number(item.get("valor_frete")), 2) - pg_frete))
            base_frete = round(_number(candidate.get("valor_frete")), 2)
            if abs(pg_frete - base_frete) <= 0.01:
                freight_equal += 1
            else:
                freight_different += 1
                if len(differences) < max_differences:
                    differences.append({"status": "frete_divergente", "nf": nf, "cte": row.get("cte"), "chave": chave, "frete_postgres": pg_frete, "frete_base_ssw": base_frete})
        base_unmatched = max(0, len(base_by_key) - len(seen_base_keys))
        comparable = max(1, matched)
        return {
            "compared_at": now_iso(),
            "postgres_rows": len(pg_rows),
            "base_rows": len(base_rows),
            "matched": matched,
            "missing_in_base_ssw": missing_in_base,
            "base_keys_without_postgres_match": base_unmatched,
            "freight_equal": freight_equal,
            "freight_different": freight_different,
            "freight_compatibility_percent": round((freight_equal / comparable) * 100.0, 2),
            "differences": differences,
            "differences_truncated": (missing_in_base + freight_different) > len(differences),
            "promotion_allowed": False,
            "message": "Comparação em sombra concluída. Nenhuma fonte oficial foi substituída.",
        }
