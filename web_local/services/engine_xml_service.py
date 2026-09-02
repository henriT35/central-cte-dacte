# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .xml_report_web_patch import publish_extra_comparison_fields

SERVICE_VERSION = "2.7.0 RC27.14 WEB/WINDOWS MVP13 R12.13.9"
RESULT_SCHEMA_VERSION = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raw = str(value).strip().replace("R$", "").replace("%", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return float(raw)
    except Exception:
        return None


def only_digits(value: Any) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def percentage_points(value: Any) -> float | None:
    parsed = number(value)
    if parsed is None:
        return None
    return parsed * 100.0 if -1.0 <= parsed <= 1.0 else parsed


def first_nf(info: Mapping[str, Any]) -> str:
    for document in list(info.get("docs") or []):
        if not isinstance(document, Mapping):
            continue
        candidate = str(document.get("n_doc") or document.get("numero") or "").strip()
        if candidate:
            return candidate
    return ""


def all_nfs(info: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for document in list(info.get("docs") or []):
        if not isinstance(document, Mapping):
            continue
        candidate = str(document.get("n_doc") or document.get("numero") or "").strip()
        if candidate and candidate not in result:
            result.append(candidate)
    return result


def person_name(info: Mapping[str, Any], key: str, fallback: str = "") -> str:
    value = info.get(key)
    if isinstance(value, Mapping):
        return str(value.get("nome") or value.get("xNome") or fallback).strip()
    return str(value or fallback).strip()


def destination_label(info: Mapping[str, Any]) -> str:
    # A rota comercial deve refletir o local efetivo de entrega. Quando o XML
    # informa um recebedor com município, ele prevalece sobre o fim da prestação.
    receiver = info.get("receb")
    if isinstance(receiver, Mapping):
        receiver_city = str(receiver.get("mun") or receiver.get("municipio") or "").strip()
        if receiver_city:
            return receiver_city.replace(" - ", " / ", 1)
    dest = info.get("dest")
    if isinstance(dest, Mapping):
        destination_party = str(dest.get("mun") or dest.get("municipio") or "").strip()
        if destination_party:
            return destination_party.replace(" - ", " / ", 1)
    destination = str(info.get("destino") or "").strip()
    if destination:
        parts = [part.strip() for part in destination.split("-") if part.strip()]
        if len(parts) >= 2:
            return f"{parts[0]} / {parts[1]}"
        return destination
    return ""




def _normalized_operational_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").upper())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _operational_text_from_info(info: Mapping[str, Any]) -> str:
    pieces: list[str] = []
    for key in ("obs", "obs_principal", "uso_exclusivo", "natOp", "produto", "outras_carac"):
        value = info.get(key)
        if value not in (None, ""):
            pieces.append(str(value))
    for component in list(info.get("componentes") or []):
        if isinstance(component, Mapping):
            pieces.append(str(component.get("nome") or ""))
    return _normalized_operational_text(" ".join(pieces))


def _money_br(value: Any) -> str:
    parsed = number(value)
    if parsed is None:
        return "-"
    return f"{parsed:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _normal_partner_calculation_info(info: Mapping[str, Any]) -> dict[str, Any]:
    """Cria uma fotografia neutra para descobrir o frete NORMAL do parceiro.

    A R12.13.3 usa esta fotografia somente como referência intermediária de
    cálculo. O XML original e o resultado congelado do RC26.6 são preservados.
    Campos operacionais que poderiam reclassificar o documento como reentrega
    ou outro extra são apagados, enquanto NF, rota, peso, emitente e demais
    vínculos estruturais continuam intactos.
    """
    cloned = copy.deepcopy(dict(info))
    for field in (
        "tpServ", "natOp", "obs", "obs_principal", "uso_exclusivo",
        "produto", "outras_carac", "obs_cobranca",
        "info_complementar_operacional", "observacoes_operacionais",
    ):
        if field in cloned:
            cloned[field] = ""

    components: list[dict[str, Any]] = []
    for component in list(cloned.get("componentes") or []):
        if not isinstance(component, Mapping):
            continue
        normalized_component = dict(component)
        name = _normalized_operational_text(normalized_component.get("nome") or "")
        if any(token in name for token in (
            "REENTREGA", "RE ENTREGA", "SEGUNDA ENTREGA",
            "CUSTO EXTRA", "SEPARACAO", "ESTADIA", "DEDICADO",
        )):
            normalized_component["nome"] = "FRETE VALOR"
        components.append(normalized_component)
    cloned["componentes"] = components
    return cloned


def _grauna_special_category(info: Mapping[str, Any]) -> tuple[str, str]:
    """Detecta somente a exceção contratual explícita de Atacadão.

    R12.13.5: nomes genéricos contendo SUPERMERCADO/SUPERMERCADOS não são
    evidência suficiente para aplicar os 40%. Esses clientes seguem a regra
    normal da rota (inclusive frete mínimo). A exceção de 40% continua ativa
    quando o destinatário/recebedor contém explicitamente ATACADAO.
    """
    names = " ".join(
        value for value in (
            person_name(info, "dest", str(info.get("destinatario") or "")),
            person_name(info, "receb", str(info.get("recebedor") or "")),
        ) if value
    )
    normalized = _normalized_operational_text(names)
    if re.search(r"(?:^| )ATACADAO(?: |$)", normalized):
        return "ATACADAO", names.strip()
    return "", names.strip()


def _grauna_special_percent(tables: Mapping[str, Any]) -> float | None:
    for rule in list(tables.get("extras") or []):
        if not isinstance(rule, Mapping):
            continue
        if str(rule.get("partner_id") or "").strip().upper() != "GRAUNA_TRANSPORTES":
            continue
        kind = _normalized_operational_text(rule.get("tipo_extra") or "")
        if "REDE" in kind and "ATACADAO" in kind and "VALE" in kind:
            value = number(rule.get("percent"))
            if value and value > 0:
                return value
    return None


def _grauna_tables_without_weight_rule(tables: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Retira a regra >120 kg da Graúna somente da fotografia de cálculo oficial.

    A R12.13.4 mantém a regra de peso carregada e auditável, porém ela não
    participa mais do valor/status oficial. O motor RC26.6 permanece intacto:
    criamos uma cópia rasa das tabelas e recalculamos apenas a camada web sem
    as regras de peso da Graúna.
    """
    cloned = dict(tables)
    kept: list[Any] = []
    removed: list[dict[str, Any]] = []
    for rule in list(tables.get("peso_especial") or []):
        if isinstance(rule, Mapping) and str(rule.get("partner_id") or "").strip().upper() == "GRAUNA_TRANSPORTES":
            removed.append(dict(rule))
            continue
        kept.append(rule)
    cloned["peso_especial"] = kept
    return cloned, removed


def _grauna_weight_is_candidate(validation: Mapping[str, Any], removed_rules: Iterable[Mapping[str, Any]]) -> bool:
    """Indica se a fotografia original estava sujeita à regra >120 kg."""
    weight_kg = number(validation.get("peso_base_kg")) or 0.0
    explicit = str(validation.get("regra_peso_especial") or "").strip().upper() == "SIM"
    mode = _normalized_operational_text(validation.get("modo_calculo") or validation.get("regra_comercial") or "")
    if explicit or "PESO ESPECIAL" in mode or "PESO_ESPECIAL" in str(validation.get("modo_calculo") or "").upper():
        return True
    for rule in removed_rules:
        limit = number(rule.get("peso_min_kg")) or 0.0
        if limit and weight_kg > limit:
            return True
    return False


def _grauna_shadow_weight_fields(validation: Mapping[str, Any], removed_rules: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Publica a antiga regra de peso apenas como telemetria/shadow."""
    rules = [dict(rule) for rule in removed_rules if isinstance(rule, Mapping)]
    tolerance = number(validation.get("tolerancia"))
    difference = number(validation.get("diferenca"))
    status = str(validation.get("status") or "")
    matched = bool(status.upper().startswith("OK"))
    if difference is not None and tolerance is not None:
        matched = abs(difference) <= tolerance
    return {
        "shadow_weight_active": True,
        "shadow_weight_rule": "GRAUNA_ACIMA_120KG",
        "shadow_weight_status": status,
        "shadow_weight_expected": number(validation.get("esperado")),
        "shadow_weight_difference": difference,
        "shadow_weight_percentual": number(validation.get("percentual")),
        "shadow_weight_base": number(validation.get("base_frete")),
        "shadow_weight_kg": number(validation.get("peso_base_kg")),
        "shadow_weight_match": matched,
        "shadow_weight_rules": json_safe(rules),
    }


def _grauna_weight_rate(tables: Mapping[str, Any], weight_kg: float) -> tuple[float | None, str]:
    candidates: list[tuple[float, float, str]] = []
    for rule in list(tables.get("peso_especial") or []):
        if not isinstance(rule, Mapping):
            continue
        if str(rule.get("partner_id") or "").strip().upper() != "GRAUNA_TRANSPORTES":
            continue
        limit = number(rule.get("peso_min_kg")) or 0.0
        if limit and weight_kg <= limit:
            continue
        raw = rule.get("raw") if isinstance(rule.get("raw"), Mapping) else {}
        raw_normalized = {
            re.sub(r"[^A-Z0-9]", "", _normalized_operational_text(key)): value
            for key, value in raw.items()
        }
        rate = None
        for key in ("VALORKG", "VALORPORKG", "TAXAKG", "FRETEKG"):
            if key in raw_normalized:
                rate = number(raw_normalized.get(key))
                if rate and rate > 0:
                    break
        if not rate:
            # Compatibilidade com consolidados antigos: antes da R12.13 o
            # cabeçalho Valor KG não existia no template agregado, mas a
            # própria observação da regra já guardava o valor contratual.
            match = re.search(r"R\$\s*([0-9]+(?:[.,][0-9]+)?)\s*/?\s*KG", str(rule.get("observacao") or ""), flags=re.I)
            if match:
                rate = number(match.group(1))
        if not rate:
            continue
        rule_id = str(raw_normalized.get("REGRAID") or raw.get("Regra ID") or "GRAUNA_ACIMA_120KG").strip()
        candidates.append((limit, float(rate), rule_id))
    if not candidates:
        return None, ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, rate, rule_id = candidates[0]
    return rate, rule_id

_COMMERCIAL_LOCATION_ALIASES = {
    # A denominação oficial usada pela tabela Rodotec está no singular.
    # Alguns XMLs/recebedores chegam com a variação plural.
    "ALTO ALEGRE DOS PARECIS": "ALTO ALEGRE DO PARECIS",
}


def _normalized_location(value: Any) -> str:
    """Normaliza o município do recebedor como o motor normaliza a tabela.

    Remove acentos, hífens e pontuação antes de adaptar a linha da Base SSW.
    Sem isso, ``JI-PARANÁ`` não correspondia a ``Ji-Paraná`` da planilha, pois
    a tabela era carregada como ``JI PARANA`` e o adaptador mantinha o hífen.
    """
    text = unicodedata.normalize("NFD", str(value or "").strip().upper())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    normalized = re.sub(r"\s+", " ", text).strip()
    return _COMMERCIAL_LOCATION_ALIASES.get(normalized, normalized)


def _receiver_city_uf(info: Mapping[str, Any]) -> tuple[str, str, str]:
    receiver = info.get("receb")
    if not isinstance(receiver, Mapping):
        return "", "", ""
    raw = str(receiver.get("mun") or receiver.get("municipio") or "").strip()
    if not raw:
        return "", "", ""
    city, separator, uf = raw.rpartition(" - ")
    if not separator:
        city, separator, uf = raw.rpartition("/")
    city_value = _normalized_location(city if separator else raw)
    uf_value = _normalized_location(uf)[:2] if separator else ""
    label = f"{city_value} - {uf_value}" if uf_value else city_value
    return city_value, uf_value, label


def _nf_index_keys(value: Any) -> list[str]:
    raw = str(value or "").strip()
    digits = only_digits(raw)
    keys: list[str] = []
    for candidate in (raw, digits, digits.lstrip("0")):
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys


def commercial_inputs_using_receiver(
    info: Mapping[str, Any],
    base_data: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any], dict[str, Any]]:
    """Adapta somente a entrada da validação web sem alterar o motor RC26.6.

    Quando existe endereço de recebedor, o município de entrega substitui o fim
    da prestação exclusivamente para selecionar a rota/regra comercial. O XML e
    a Base SSW originais permanecem intactos.
    """
    city, uf, receiver_label = _receiver_city_uf(info)
    if not city or not isinstance(base_data, Mapping):
        return dict(info), base_data, {}

    commercial_info = dict(info)
    destination_party = dict(info.get("dest") or {}) if isinstance(info.get("dest"), Mapping) else {}
    fiscal_destination = str(destination_party.get("mun") or info.get("destino") or "").strip()
    destination_party["mun"] = receiver_label
    destination_party["municipio"] = receiver_label
    commercial_info["dest"] = destination_party
    commercial_info["destino"] = receiver_label

    source_index = base_data.get("index")
    if not isinstance(source_index, Mapping):
        return commercial_info, base_data, {
            "city": city, "uf": uf, "label": receiver_label, "fiscal_destination": fiscal_destination, "adapted_rows": 0,
        }

    adapted_index = dict(source_index)
    adapted_rows = 0
    visited_keys: set[str] = set()
    for nf in all_nfs(info):
        for key in _nf_index_keys(nf):
            if key in visited_keys:
                continue
            rows = source_index.get(key)
            if not isinstance(rows, (list, tuple)) or not rows:
                continue
            visited_keys.add(key)
            cloned_rows: list[Any] = []
            for row in rows:
                if not isinstance(row, Mapping):
                    cloned_rows.append(row)
                    continue
                cloned = dict(row)
                cloned["destino_cidade_base_original"] = cloned.get("destino_cidade", "")
                cloned["destino_uf_base_original"] = cloned.get("destino_uf", "")
                cloned["destino_cidade"] = city
                if uf:
                    cloned["destino_uf"] = uf
                cloned["destino_fonte_comercial"] = "RECEBEDOR_XML_WEB"
                cloned_rows.append(cloned)
                adapted_rows += 1
            adapted_index[key] = cloned_rows
            break

    adapted_base = dict(base_data)
    adapted_base["index"] = adapted_index
    metadata = {
        "city": city,
        "uf": uf,
        "label": receiver_label,
        "fiscal_destination": fiscal_destination,
        "adapted_rows": adapted_rows,
        "source": "RECEBEDOR_XML_WEB",
    }
    return commercial_info, adapted_base, metadata


def annotate_receiver_route(validation: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(validation)
    if not metadata:
        return result
    result["destino_comercial"] = metadata.get("city") or ""
    result["destino_comercial_uf"] = metadata.get("uf") or ""
    result["destino_comercial_fonte"] = metadata.get("source") or "RECEBEDOR_XML_WEB"
    result["destino_fiscal_prestacao"] = metadata.get("fiscal_destination") or ""
    trace = list(result.get("trace") or [])
    trace.append(
        "Destino comercial definido pelo endereço do recebedor: "
        f"{metadata.get('label') or metadata.get('city')}. "
        "O destino/fim da prestação foi preservado apenas como informação fiscal; "
        "o motor RC26.6 não foi modificado."
    )
    result["trace"] = trace
    return result


def file_identity(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def manual_decision_key(info: Mapping[str, Any], path: Path | None = None) -> str:
    chave = only_digits(
        info.get("chave")
        or info.get("chCTe")
        or info.get("chcte")
        or info.get("access_key")
        or ""
    )
    if len(chave) >= 44:
        return f"CTE:{chave[-44:]}"
    emit = info.get("emit") if isinstance(info.get("emit"), Mapping) else {}
    cnpj = only_digits((emit or {}).get("cnpjcpf") or info.get("cnpj_emitente") or "")
    numero = only_digits(info.get("numero") or info.get("nCT") or "")
    serie = only_digits(info.get("serie") or "")
    if cnpj and numero:
        return f"CTE:{cnpj}:{serie}:{numero}"
    return f"ARQUIVO:{str(Path(path).resolve()) if path is not None else numero or 'SEM_IDENTIFICACAO'}"


def file_signature(paths: Iterable[Path]) -> str:
    parts: list[str] = []
    for path in sorted((Path(item) for item in paths), key=lambda item: str(item).lower()):
        try:
            stat = path.stat()
            parts.append(f"{path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}")
        except OSError:
            parts.append(f"{path}|ausente")
    return hashlib.sha256("\n".join(parts).encode("utf-8", errors="replace")).hexdigest()


class OfficialXmlEngineService:
    """Executa parser e validador oficiais sem depender da janela PySide6.

    A classe não implementa qualquer fórmula comercial. Ela apenas carrega as
    funções já publicadas pelo motor RC26.6 e devolve a fotografia oficial para
    a interface web.
    """

    def __init__(self, project_root: Path, upload_root: Path, state_root: Path, partner_table_root: Path | None = None):
        self.project_root = Path(project_root).resolve()
        self.upload_root = Path(upload_root).resolve()
        self.state_root = Path(state_root).resolve()
        default_partner_root = self.upload_root.parents[2] / "partner_tables"
        self.partner_table_root = Path(partner_table_root or default_partner_root).resolve()
        self.results_path = self.state_root / "xml_validation_results.json"
        self.last_run_path = self.state_root / "xml_processing_last_run.json"
        self.manual_decisions_path = self.state_root / "xml_manual_decisions.json"
        self.self_test_path = self.state_root / "engine_contract_self_test.json"
        self._lock = threading.RLock()
        self._engine: Any | None = None
        self._base_data: dict[str, Any] | None = None
        self._base_signature = ""
        self._tables: dict[str, Any] | None = None
        self._table_signature = ""
        self._result_cache: dict[str, Any] | None = None
        self._result_cache_mtime_ns = -1

    @property
    def engine_file(self) -> Path:
        return self.project_root / "engine" / "central_cte_engine_1_1_36.py"

    def readiness(self) -> dict[str, Any]:
        base_source = self.resolve_base_source(raise_on_missing=False)
        table_source = self.resolve_table_source(raise_on_missing=False)
        ready = self.engine_file.is_file() and base_source is not None and table_source is not None
        return {
            "connected": bool(ready),
            "service_version": SERVICE_VERSION,
            "engine_file": str(self.engine_file),
            "base_source": str(base_source) if base_source else "",
            "table_source": str(table_source) if table_source else "",
            "status": (
                "Serviço XML oficial disponível sem dependência da interface antiga."
                if ready
                else "Serviço XML aguardando motor, Base SSW Web ou tabela de parceiros."
            ),
            "last_run": read_json(self.last_run_path, {}),
            "self_test": read_json(self.self_test_path, {}),
        }

    def resolve_base_source(self, *, raise_on_missing: bool = True) -> Path | None:
        uploaded = self.upload_root / "bases"
        uploaded_files = sorted(uploaded.glob("*.sswweb")) if uploaded.is_dir() else []
        if uploaded_files:
            return uploaded
        project_source = self.project_root / "bases"
        if project_source.is_dir() and any(project_source.glob("*.sswweb")):
            return project_source
        if raise_on_missing:
            raise FileNotFoundError("Nenhum arquivo .sswweb foi encontrado na Base SSW Web.")
        return None

    def resolve_table_source(self, *, raise_on_missing: bool = True) -> Path | None:
        compiled = self.partner_table_root / "cadastro_tabelas_parceiros_compilada.xlsx"
        if compiled.is_file():
            return compiled
        uploaded = self.upload_root / "tabelas"
        uploaded_files = []
        if uploaded.is_dir():
            uploaded_files = sorted(
                (path for path in uploaded.iterdir() if path.is_file() and path.suffix.lower() == ".xlsx"),
                key=lambda path: path.stat().st_mtime_ns,
                reverse=True,
            )
        if uploaded_files:
            return uploaded_files[0]
        official = self.project_root / "tabelas" / "cadastro_tabelas_parceiros.xlsx"
        if official.is_file():
            return official
        if raise_on_missing:
            raise FileNotFoundError("A tabela oficial de parceiros não foi encontrada.")
        return None

    def _load_engine(self) -> Any:
        with self._lock:
            if self._engine is not None:
                return self._engine
            if not self.engine_file.is_file():
                raise FileNotFoundError(f"Motor oficial ausente: {self.engine_file}")
            engine_dir = str(self.engine_file.parent)
            if engine_dir not in sys.path:
                sys.path.insert(0, engine_dir)
            self._engine = importlib.import_module("central_cte_engine_1_1_36")
            required = ("parse_xml", "load_rodovitor_base_cached", "load_partner_tables", "validate_cte_value")
            missing = [name for name in required if not callable(getattr(self._engine, name, None))]
            if missing:
                self._engine = None
                raise RuntimeError("O motor não publicou os serviços obrigatórios: " + ", ".join(missing))
            return self._engine

    @staticmethod
    def _base_files(source: Path) -> list[Path]:
        if source.is_file():
            return [source]
        return sorted(source.glob("*.sswweb"))

    def invalidate_dependencies(self) -> None:
        """Descarta somente caches derivados de base/tabela.

        Os arquivos de origem permanecem intactos; a próxima execução recarrega
        tudo pelo motor oficial RC26.6.
        """
        with self._lock:
            self._base_data = None
            self._base_signature = ""
            self._tables = None
            self._table_signature = ""

    def validate_base_source(self, source: Path) -> dict[str, Any]:
        source = Path(source).resolve()
        files = self._base_files(source)
        if not files:
            raise ValueError("A nova Base SSW não contém arquivos .sswweb.")
        engine = self._load_engine()
        data = engine.load_rodovitor_base_cached(source, force=True)
        if not isinstance(data, dict) or not isinstance(data.get("index"), dict):
            raise ValueError("O motor RC26.6 não reconheceu a estrutura da nova Base SSW.")
        row_count = len(list(data.get("rows") or []))
        if row_count <= 0:
            raise ValueError("A nova Base SSW foi lida, mas não possui registros válidos.")
        return {"file_count": len(files), "row_count": row_count, "source": str(source)}

    def validate_table_source(self, source: Path) -> dict[str, Any]:
        source = Path(source).resolve()
        if not source.is_file() or source.suffix.lower() != ".xlsx":
            raise ValueError("A tabela de parceiros deve ser uma planilha XLSX.")
        engine = self._load_engine()
        tables = engine.load_partner_tables(source)
        if not isinstance(tables, dict):
            raise ValueError("O motor RC26.6 não reconheceu a tabela de parceiros.")
        partners = tables.get("partners") or {}
        rules = tables.get("rules") or tables.get("percent_rules") or []
        if not partners:
            raise ValueError("A tabela não possui parceiros válidos na aba PARCEIROS.")
        return {
            "partner_count": len(partners),
            "rule_count": len(rules) if hasattr(rules, "__len__") else 0,
            "source": str(source),
        }

    def _load_dependencies(self) -> tuple[Any, dict[str, Any], dict[str, Any], Path, Path]:
        engine = self._load_engine()
        base_source = self.resolve_base_source()
        table_source = self.resolve_table_source()
        assert base_source is not None and table_source is not None

        base_sig = file_signature(self._base_files(base_source))
        table_sig = file_signature([table_source])
        with self._lock:
            if self._base_data is None or self._base_signature != base_sig:
                self._base_data = engine.load_rodovitor_base_cached(base_source, force=True)
                if not isinstance(self._base_data, dict) or not isinstance(self._base_data.get("index"), dict):
                    raise RuntimeError("A Base SSW Web não retornou uma estrutura válida.")
                self._base_signature = base_sig
            if self._tables is None or self._table_signature != table_sig:
                self._tables = engine.load_partner_tables(table_source)
                if not isinstance(self._tables, dict):
                    raise RuntimeError("A tabela de parceiros não retornou uma estrutura válida.")
                self._table_signature = table_sig
            return engine, self._base_data, self._tables, base_source, table_source

    def _contract_self_test(self, engine: Any, tables: dict[str, Any]) -> dict[str, Any]:
        info = {
            "tipo": "CT-e",
            "numero": "579882",
            "serie": "2",
            "valor": "149.69",
            "vTPrest": "149.69",
            "emitente": "JSP TRANSPORTE E LOGISTICA LTDA",
            "emit": {"cnpjcpf": "14498358000109", "nome": "JSP TRANSPORTE E LOGISTICA LTDA"},
            "docs": [{"n_doc": "283763"}],
            "componentes": [{"nome": "FRETE VALOR", "valor": "149.69"}],
            "tpCTe": "NORMAL",
            "tpCTe_codigo": "0",
            "tpCTe_fonte": "XML ide/tpCTe",
        }
        row = {
            "nf": "283763",
            "cte": "001000050132",
            "chave": "",
            "tipo_base": "NORMAL",
            "valor_frete": 589.78,
            "valor_frete_planilha": 589.78,
            "valor_frete_sem_icms": 548.50,
            "valor_frete_origem": 0.0,
            "valor_mercadoria": 12268.80,
            "fonte_frete": "PLANILHA",
            "destino_cidade": "PARAUAPEBAS",
            "destino_uf": "PA",
            "origem_cidade": "GARUVA",
            "origem_uf": "SC",
            "cnpj_remetente": "",
            "cnpj_destinatario": "",
            "cnpj_pagador": "",
            "cnpj_recebedor": "",
        }
        result = engine.validate_cte_value(info, {"rows": [row], "index": {"283763": [row]}}, tables)
        passed = (
            str(result.get("status")) == "DIVERGENTE +"
            and round(float(result.get("esperado")), 2) == 147.45
            and round(float(result.get("diferenca")), 2) == 2.24
            and not result.get("repasse_embutido_status")
        )
        payload = {
            "passed": passed,
            "checked_at": now_iso(),
            "contract": "579882/JSP",
            "expected": {"status": "DIVERGENTE +", "valor_esperado": 147.45, "diferenca": 2.24},
            "observed": {
                "status": result.get("status"),
                "valor_esperado": result.get("esperado"),
                "diferenca": result.get("diferenca"),
                "repasse_embutido_status": result.get("repasse_embutido_status"),
            },
        }
        write_json_atomic(self.self_test_path, payload)
        if not passed:
            raise RuntimeError("O motor falhou no contrato sentinela 579882/JSP. O processamento foi interrompido.")
        return payload

    def _partner_name(self, result: Mapping[str, Any], info: Mapping[str, Any], tables: Mapping[str, Any]) -> str:
        partner_id = str(result.get("partner_id") or "").strip()
        partners = tables.get("partners") if isinstance(tables, Mapping) else None
        if isinstance(partners, Mapping) and partner_id:
            partner = partners.get(partner_id)
            if isinstance(partner, Mapping):
                name = str(partner.get("name") or partner.get("alias") or "").strip()
                if name:
                    return name
        return str(info.get("emitente") or person_name(info, "emit") or partner_id or "Não localizado")

    def _manual_decisions(self) -> dict[str, Any]:
        payload = read_json(self.manual_decisions_path, {})
        if not isinstance(payload, Mapping):
            return {"schema_version": 1, "updated_at": "", "decisions": {}}
        decisions = payload.get("decisions")
        return {
            "schema_version": int(payload.get("schema_version") or 1),
            "updated_at": str(payload.get("updated_at") or ""),
            "decisions": dict(decisions) if isinstance(decisions, Mapping) else {},
        }

    @staticmethod
    def _apply_partner_calculated_reentrega(
        validation: Mapping[str, Any],
        info: Mapping[str, Any],
        commercial_info: Mapping[str, Any],
        commercial_base: Mapping[str, Any],
        tables: Mapping[str, Any],
        engine: Any,
    ) -> dict[str, Any]:
        """Corrige a base da REENTREGA C Vargas sem tocar no RC26.6.

        A tabela comercial diz "Cobrar 50% da tabela". Portanto a sequência
        operacional correta é: (1) calcular o frete NORMAL do parceiro pela
        própria tabela; (2) aplicar 50% sobre esse resultado; (3) comparar com
        o XML de reentrega. O frete bruto da Rodovitor continua preservado em
        ``base_frete`` para rentabilidade e auditoria.
        """
        result = dict(validation)
        partner_id = str(result.get("partner_id") or "").strip().upper()
        charge_type = str(result.get("tipo_cobranca") or result.get("tipo_cobranca_extra") or "").strip().upper()
        if partner_id != "AC_LOG_C_VARGAS" or charge_type != "REENTREGA":
            return result

        original_status = result.get("status")
        original_expected = result.get("esperado")
        original_difference = result.get("diferenca")
        result.setdefault("engine_status", original_status)
        result.setdefault("engine_expected_value", original_expected)
        result.setdefault("engine_difference", original_difference)

        try:
            normal_info = _normal_partner_calculation_info(commercial_info)
            normal_validation = engine.validate_cte_value(normal_info, commercial_base, tables)
        except Exception as exc:
            trace = list(result.get("trace") or [])
            trace.append(f"R12.13.3: não foi possível calcular a referência NORMAL do parceiro para a reentrega: {exc}")
            result["trace"] = trace
            return result

        if not isinstance(normal_validation, Mapping):
            return result
        normal_expected = number(normal_validation.get("esperado"))
        factor = number(result.get("percentual"))
        if factor is None or factor <= 0:
            factor = 0.50
        actual = number(result.get("valor_comparado"))
        if actual is None:
            actual = number(result.get("valor_total_xml"))
        if actual is None:
            actual = number(info.get("valor"))
        tolerance = number(result.get("tolerancia"))
        if tolerance is None:
            tolerance = number(tables.get("tolerance")) or 1.0

        if normal_expected is None or normal_expected <= 0 or actual is None:
            trace = list(result.get("trace") or [])
            trace.append(
                "R12.13.3: reentrega C Vargas identificada, mas o frete NORMAL do parceiro não pôde ser calculado; "
                "resultado RC26.6 preservado para revisão."
            )
            result["trace"] = trace
            return result

        expected = float((Decimal(str(normal_expected)) * Decimal(str(factor))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        difference = round(float(actual) - expected, 2)
        if abs(difference) <= tolerance:
            calculation_status = "OK EXTRA"
        elif difference > 0:
            calculation_status = "DIVERGENTE EXTRA +"
        else:
            calculation_status = "DIVERGENTE EXTRA -"

        normal_percent = number(normal_validation.get("percentual"))
        normal_minimum = number(normal_validation.get("frete_minimo"))
        normal_rule = str(normal_validation.get("regra_comercial") or normal_validation.get("regra_extra") or normal_validation.get("modo_calculo") or "TABELA NORMAL")
        detail = str(result.get("detalhe") or "").strip()
        if detail:
            detail += "; "
        detail += (
            f"REENTREGA calculada sobre o frete normal do parceiro: R$ {_money_br(normal_expected)} × {factor * 100:.0f}% "
            f"= R$ {_money_br(expected)}; XML R$ {_money_br(actual)}"
        )

        result.update({
            "base_calculo": "PARCEIRO_CALCULADO",
            "extra_base_calculo_operacional": "PARCEIRO_CALCULADO",
            "extra_base_valor": round(normal_expected, 4),
            "partner_normal_expected": round(normal_expected, 4),
            "partner_normal_status": str(normal_validation.get("status") or ""),
            "partner_normal_percentual": normal_percent,
            "partner_normal_minimum": normal_minimum,
            "partner_normal_rule": normal_rule,
            "valor_comparado": actual,
            "esperado": expected,
            "diferenca": difference,
            "tolerancia": tolerance,
            "status": calculation_status,
            "calculation_status": calculation_status,
            "calculation_expected_value": expected,
            "calculation_difference": difference,
            "calculation_actual_value": actual,
            "detalhe": detail,
            "controle_dacte_compacto": "SIM",
            "controle_dacte_regra": "AC LOG / C VARGAS — REENTREGA",
            "controle_dacte_linha1": (
                f"Frete normal parceiro R$ {_money_br(normal_expected)} × {factor * 100:.0f}% = R$ {_money_br(expected)}"
            ),
            "controle_dacte_linha2": (
                f"Cobrado R$ {_money_br(actual)} | Diferença R$ {_money_br(difference)} | Tol. R$ {_money_br(tolerance)}"
            ),
            "controle_dacte_status": calculation_status,
        })
        trace = list(result.get("trace") or [])
        trace.append(
            "R12.13.3: REENTREGA AC Log / C Vargas recalculada sobre o frete NORMAL do parceiro, não sobre o frete bruto Rodovitor. "
            f"Referência normal R$ {normal_expected:.4f}; fator {factor:.4f}; esperado R$ {expected:.2f}; XML R$ {actual:.2f}; diferença R$ {difference:.2f}."
        )
        result["trace"] = trace
        return result

    @staticmethod
    def _apply_web_contract_adapters(
        validation: Mapping[str, Any],
        info: Mapping[str, Any],
        tables: Mapping[str, Any],
        *,
        commercial_info: Mapping[str, Any] | None = None,
        commercial_base: Mapping[str, Any] | None = None,
        engine: Any | None = None,
    ) -> dict[str, Any]:
        """Aplica contratos web sem alterar o motor congelado RC26.6.

        R12.13.4:
        - Graúna >120 kg passa a ser SOMBRA: nunca define esperado/status oficial.
        - a regra oficial volta a ser a regra normal da rota (ex.: Redenção 28%).
        - somente Atacadão continua prioritário em 40%, com autorização manual.
        - nomes genéricos de supermercado seguem a regra normal da rota/frete mínimo.

        A fotografia original do RC26.6 continua disponível em ``engine_*`` e a
        antiga regra de peso fica registrada em ``shadow_weight_*`` para QA.
        """
        original = dict(validation)
        original_status = original.get("status")
        original_expected = original.get("esperado")
        original_difference = original.get("diferenca")

        result = dict(original)
        result.setdefault("engine_status", original_status)
        result.setdefault("engine_expected_value", original_expected)
        result.setdefault("engine_difference", original_difference)
        partner_id = str(result.get("partner_id") or "").strip().upper()
        if partner_id != "GRAUNA_TRANSPORTES":
            return result

        # R12.13.4 — a regra >120 kg não participa mais da decisão operacional.
        # Recalculamos a Graúna em uma fotografia de tabelas sem o peso especial,
        # preservando o resultado original apenas como shadow/telemetria.
        official_tables, removed_weight_rules = _grauna_tables_without_weight_rule(tables)
        weight_candidate = _grauna_weight_is_candidate(original, removed_weight_rules)
        shadow_fields = _grauna_shadow_weight_fields(original, removed_weight_rules) if weight_candidate else {}

        if weight_candidate and engine is not None and commercial_base is not None:
            try:
                normal_validation = engine.validate_cte_value(
                    commercial_info if isinstance(commercial_info, Mapping) else info,
                    commercial_base,
                    official_tables,
                )
                if isinstance(normal_validation, Mapping):
                    normal_result = dict(normal_validation)
                    # Mantém metadados web já calculados antes do recálculo.
                    for key in (
                        "destino_comercial", "destino_comercial_uf", "destino_comercial_fonte",
                        "destino_fiscal_prestacao",
                    ):
                        if key in result and key not in normal_result:
                            normal_result[key] = result[key]
                    normal_result.update({
                        "engine_status": result.get("engine_status", original_status),
                        "engine_expected_value": result.get("engine_expected_value", original_expected),
                        "engine_difference": result.get("engine_difference", original_difference),
                        **shadow_fields,
                    })
                    trace = list(normal_result.get("trace") or [])
                    trace.append(
                        "R12.13.4: regra Graúna >120 kg executada somente em SHADOW; "
                        "o valor/status oficial foi recalculado sem REGRAS_PESO_ESPECIAL da Graúna."
                    )
                    if shadow_fields.get("shadow_weight_match"):
                        trace.append(
                            "R12.13.4: a antiga regra de peso coincidiu com o XML, mas essa coincidência não pode gerar OK oficial."
                        )
                    normal_result["trace"] = trace
                    result = normal_result
            except Exception as exc:
                # Segurança operacional: se o recálculo oficial falhar, nunca
                # promovemos o resultado da regra de peso para OK.
                result.update(shadow_fields)
                result.update({
                    "status": "REVISAR — REGRA >120 KG EM SOMBRA",
                    "esperado": None,
                    "diferenca": None,
                    "acao_recomendada": "Reprocessar a regra normal da rota da Graúna; a regra >120 kg não pode liberar o XML.",
                })
                trace = list(result.get("trace") or [])
                trace.append(f"R12.13.4: falha ao recalcular Graúna sem peso especial: {exc}")
                result["trace"] = trace
        elif weight_candidate:
            # Chamadas unitárias/legadas sem motor/base não têm informação
            # suficiente para reconstruir a rota. Bloqueamos o falso OK.
            result.update(shadow_fields)
            result.update({
                "status": "REVISAR — REGRA >120 KG EM SOMBRA",
                "esperado": None,
                "diferenca": None,
                "acao_recomendada": "Recalcular pela regra normal da rota da Graúna; regra >120 kg é apenas shadow.",
            })
            trace = list(result.get("trace") or [])
            trace.append(
                "R12.13.4: regra >120 kg da Graúna marcada como SHADOW; sem contexto de motor/base, nenhum OK foi emitido."
            )
            result["trace"] = trace

        # A condição especial permanece acima da regra normal da rota e também
        # acima da regra shadow de peso. R12.13.5 restringe essa exceção a
        # Atacadão explícito; supermercado genérico segue rota/frete mínimo.
        category, party_name = _grauna_special_category(info)
        if category:
            percent = _grauna_special_percent(tables) or 0.40
            base = number(result.get("base_frete"))
            if base is None:
                base = number(original.get("base_frete"))
            actual = number(result.get("valor_comparado"))
            if actual is None:
                actual = number(original.get("valor_comparado"))
            if actual is None:
                actual = number(info.get("valor"))
            expected = (base * percent) if base is not None else None
            difference = (actual - expected) if actual is not None and expected is not None else None
            result.update({
                "tipo_cobranca": "REDE_ATACADAO_VALE",
                "tipo_cobranca_extra": "REDE_ATACADAO_VALE",
                "cobranca_extra_detectada": True,
                "campo_cobranca_extra": "destinatário/recebedor",
                "texto_cobranca_extra": party_name,
                "fonte_cobranca_extra": "Proposta Graúna — condição especial 40%",
                "explicacao_classificacao": (
                    f"Nome do destinatário/recebedor indica {category.replace('_', ' ')}; "
                    "a proposta comercial prevê condição especial de 40%."
                ),
                "requires_manual_authorization": True,
                "authorization_status": "PENDENTE",
                "special_contract_percent": percent,
                "special_contract_expected": round(expected, 2) if expected is not None else None,
                "special_contract_difference": round(difference, 2) if difference is not None else None,
                "esperado": None,
                "diferenca": None,
                "status": "EXTRA — AGUARDANDO AUTORIZAÇÃO",
                "acao_recomendada": (
                    "Confirmar que o destinatário pertence à condição especial da proposta Graúna e registrar aprovação ou recusa."
                ),
                "detalhe": (
                    "Condição especial Graúna identificada por nome do destinatário/recebedor. "
                    + (
                        f"Memória técnica: R$ {_money_br(base)} × {percent * 100:.0f}% = R$ {_money_br(expected)}; "
                        f"XML R$ {_money_br(actual)}. " if expected is not None else ""
                    )
                    + "A liberação permanece manual porque a proposta não fornece catálogo oficial de CNPJs."
                ),
                "controle_dacte_compacto": "SIM",
                "controle_dacte_regra": "GRAÚNA — CONDIÇÃO ESPECIAL",
                "controle_dacte_linha1": (
                    f"Referência contratual: R$ {_money_br(base)} × {percent * 100:.0f}% = R$ {_money_br(expected)}"
                    if expected is not None else "Condição especial 40% — base indisponível"
                ),
                "controle_dacte_linha2": f"Cobrado R$ {_money_br(actual)} | aguardando autorização",
                "controle_dacte_status": "EXTRA — AGUARDANDO AUTORIZAÇÃO",
            })
            trace = list(result.get("trace") or [])
            trace.append(
                "R12.13.5: exceção Graúna 40% aplicada somente a Atacadão explícito; supermercado genérico permanece na regra normal da rota/frete mínimo."
            )
            result["trace"] = trace
            return result

        # Se o recálculo normal foi executado, publica um bloco compacto coerente
        # com a regra oficial, sem expor a regra shadow como decisão financeira.
        if weight_candidate and engine is not None and commercial_base is not None:
            official_expected = number(result.get("esperado"))
            official_actual = number(result.get("valor_comparado"))
            if official_actual is None:
                official_actual = number(info.get("valor"))
            official_difference = number(result.get("diferenca"))
            official_percent = number(result.get("percentual"))
            destination = destination_label(info) or str(result.get("destino_comercial") or "ROTA")
            result.update({
                "controle_dacte_compacto": "SIM",
                "controle_dacte_regra": f"GRAÚNA — {destination} — REGRA DA ROTA",
                "controle_dacte_linha1": (
                    f"Regra oficial {official_percent * 100:.0f}% | esperado R$ {_money_br(official_expected)}"
                    if official_percent is not None else f"Regra oficial da rota | esperado R$ {_money_br(official_expected)}"
                ),
                "controle_dacte_linha2": (
                    f"Cobrado R$ {_money_br(official_actual)} | Diferença R$ {_money_br(official_difference)} | >120 kg somente shadow"
                ),
                "controle_dacte_status": str(result.get("status") or ""),
            })
        return result

    @staticmethod
    def _apply_operational_authorization_policy(
        validation: Mapping[str, Any],
        info: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = dict(validation)
        partner_id = str(result.get("partner_id") or "").strip().upper()
        current_charge = str(
            result.get("tipo_cobranca")
            or result.get("tipo_cobranca_extra")
            or result.get("charge_type")
            or "NORMAL"
        ).strip().upper()
        text = _operational_text_from_info(info)
        charge_type = current_charge
        evidence = ""

        # Correções de classificação exclusivas da camada web. O RC26.6
        # continua intocado; o status técnico original é preservado em engine_*.
        if "ESTADIA" in text:
            charge_type, evidence = "ESTADIA", "ESTADIA"
        elif "TAXA DE DEDICADO" in text or "VEICULO DEDICADO" in text or "OPERACAO DEDICADA" in text:
            charge_type, evidence = "VEICULO_DEDICADO", "DEDICADO"
        elif current_charge in {"", "NORMAL", "NAO CALCULADO"} and (
            "SEPARACAO" in text or "CUSTO EXTRA" in text
        ):
            # "Conferente:" faz parte do texto operacional padrão de diversos CT-es
            # e não é evidência suficiente de custo extra por si só.
            charge_type, evidence = "CUSTO_EXTRA", "CUSTO EXTRA/SEPARAÇÃO"

        if charge_type != current_charge:
            result["tipo_cobranca"] = charge_type
            result["tipo_cobranca_extra"] = charge_type
            result["cobranca_extra_detectada"] = True
            result["campo_cobranca_extra"] = "obs/uso_exclusivo"
            result["texto_cobranca_extra"] = evidence
            result["fonte_cobranca_extra"] = "Camada operacional web R12.13.2"
            result["explicacao_classificacao"] = f"Indício explícito no XML: {evidence}."
            trace = list(result.get("trace") or [])
            trace.append(
                f"R12.13.2 camada web: cobrança reclassificada de {current_charge or 'NORMAL'} para {charge_type} por indício explícito no XML ({evidence})."
            )
            result["trace"] = trace

        result.setdefault("engine_status", validation.get("status"))
        result.setdefault("engine_expected_value", validation.get("esperado"))
        result.setdefault("engine_difference", validation.get("diferenca"))

        def mark_manual(*, label: str, action: str, detail: str, trace_note: str, evidence_in_xml: bool = False, preserve_calculation: bool = False) -> None:
            calculation_status = str(result.get("status") or "SEM STATUS")
            calculation_expected = result.get("esperado")
            calculation_difference = result.get("diferenca")
            calculation_actual = result.get("valor_comparado")
            if calculation_actual in (None, ""):
                calculation_actual = info.get("valor")
            result["calculation_status"] = calculation_status
            result["calculation_expected_value"] = calculation_expected
            result["calculation_difference"] = calculation_difference
            result["calculation_actual_value"] = calculation_actual
            result["requires_manual_authorization"] = True
            result["authorization_status"] = "PENDENTE"
            result["authorization_evidence_in_xml"] = evidence_in_xml
            if not preserve_calculation:
                result["esperado"] = None
                result["diferenca"] = None
            result["status"] = "EXTRA — AGUARDANDO AUTORIZAÇÃO"
            result["acao_recomendada"] = action
            result["detalhe"] = detail
            result["controle_dacte_compacto"] = "SIM"
            result["controle_dacte_regra"] = label
            if preserve_calculation and calculation_expected not in (None, ""):
                result["controle_dacte_linha1"] = (
                    f"Cálculo: {calculation_status} | esperado R$ {_money_br(calculation_expected)} | cobrado R$ {_money_br(calculation_actual)}"
                )
                result["controle_dacte_linha2"] = "Autorização operacional: PENDENTE"
            else:
                result["controle_dacte_linha1"] = f"Cobrança especial: {charge_type}"
                result["controle_dacte_linha2"] = "Cálculo técnico preservado | aguardando autorização"
            result["controle_dacte_status"] = "EXTRA — AGUARDANDO AUTORIZAÇÃO"
            trace = list(result.get("trace") or [])
            trace.append(trace_note)
            result["trace"] = trace

        # W S: qualquer cobrança extra identificada depende de autorização.
        if partner_id == "W_S_TRANSPORTES" and charge_type not in {"", "NORMAL", "NAO CALCULADO"}:
            mark_manual(
                label="W S — CUSTO EXTRA",
                action="Confirmar se o custo extra foi autorizado. Não solicitar correção apenas pela diferença técnica da tabela.",
                detail=(
                    f"Custo extra {charge_type} da W S identificado. O cálculo automático foi preservado para auditoria, "
                    "mas a liberação depende de autorização manual."
                ),
                trace_note=(
                    "Política operacional W S: custo extra classificado como aguardando autorização; "
                    f"status técnico original preservado como {result.get('engine_status') or 'SEM STATUS'}."
                ),
            )

        # C Vargas / AC Log: documentos explicitamente marcados como CUSTO EXTRA,
        # separação, conferente ou reentrega de custo extra não devem virar falsa
        # divergência da tabela normal.
        c_vargas_extra = (
            (("CUSTO EXTRA" in text or "SEPARACAO" in text) and charge_type not in {"", "NORMAL", "NAO CALCULADO"})
            or charge_type == "REENTREGA"
        )
        if partner_id == "AC_LOG_C_VARGAS" and c_vargas_extra:
            xml_authorized = "AUTORIZAD" in text
            if charge_type == "REENTREGA":
                calc_status = str(result.get("status") or "SEM STATUS")
                calc_expected = result.get("esperado")
                calc_actual = result.get("valor_comparado") if result.get("valor_comparado") not in (None, "") else info.get("valor")
                mark_manual(
                    label="AC LOG / C VARGAS — REENTREGA",
                    action="Registrar a autorização da reentrega no Central. O valor é conferido separadamente pela regra de 50% do frete normal do parceiro.",
                    detail=(
                        f"REENTREGA AC Log / C Vargas. Cálculo financeiro: {calc_status}; "
                        f"esperado R$ {_money_br(calc_expected)}; cobrado R$ {_money_br(calc_actual)}. "
                        "A autorização operacional continua obrigatória e não é confundida com a conferência do valor."
                    ),
                    trace_note=(
                        "R12.13.3 política AC Log / C Vargas: REENTREGA mantém cálculo financeiro independente e exige autorização operacional. "
                        f"Cálculo antes da autorização: {calc_status}."
                    ),
                    evidence_in_xml=xml_authorized,
                    preserve_calculation=True,
                )
            else:
                mark_manual(
                    label="AC LOG / C VARGAS — CUSTO EXTRA",
                    action=(
                        "Conferir a autorização interna indicada no XML e registrar aprovação ou recusa no Central."
                    ),
                    detail=(
                        f"Cobrança {charge_type} da AC Log / C Vargas contém indicação explícita de custo extra. "
                        "A comparação da tabela normal foi mantida apenas na auditoria técnica."
                    ),
                    trace_note=(
                        "Política operacional AC Log / C Vargas: custo extra separado da regra normal; "
                        f"status técnico original preservado como {result.get('engine_status') or 'SEM STATUS'}."
                    ),
                    evidence_in_xml=xml_authorized,
                )

        # JSP: taxa de dedicado é cobrança específica e não deve ser comparada
        # automaticamente ao percentual padrão da rota sem regra própria.
        if partner_id == "JSP" and charge_type == "VEICULO_DEDICADO":
            mark_manual(
                label="JSP — TAXA DE DEDICADO",
                action="Conferir a autorização/cotação da taxa de dedicado e registrar aprovação ou recusa.",
                detail=(
                    "Taxa de dedicado identificada explicitamente no XML da JSP. A regra percentual normal da rota "
                    "não é usada como divergência operacional para esta cobrança."
                ),
                trace_note=(
                    "Política operacional JSP: TAXA DE DEDICADO separada para autorização manual; "
                    f"status técnico original preservado como {result.get('engine_status') or 'SEM STATUS'}."
                ),
            )

        # M&M: a proposta padrão cobre 35% do frete original com mínimo de
        # R$ 70,00. Cotações especiais explicitamente descritas no XML não
        # devem virar falsa divergência; ficam separadas para autorização.
        if partner_id == "M_M_TRANSPORTES" and charge_type in {"COTACAO_AUTORIZADA", "COTACAO_ESPECIAL"}:
            mark_manual(
                label="M&M — COTAÇÃO ESPECIAL",
                action=(
                    "Conferir o e-mail/cotação interna e registrar aprovação ou recusa. "
                    "Não comparar esta cobrança pela regra padrão de 35%."
                ),
                detail=(
                    f"Cotação especial {charge_type} da M&M identificada. O cálculo padrão foi preservado "
                    "nos campos técnicos, mas a liberação depende de autorização manual."
                ),
                trace_note=(
                    "Política operacional M&M: cotação fora da tabela padrão separada para autorização manual; "
                    f"status técnico original preservado como {result.get('engine_status') or 'SEM STATUS'}."
                ),
                evidence_in_xml=charge_type == "COTACAO_AUTORIZADA",
            )
        return result

    @staticmethod
    def _apply_manual_decision(
        validation: Mapping[str, Any],
        decision: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        result = dict(validation)
        result.setdefault("automatic_status", result.get("status"))
        result.setdefault("automatic_expected_value", result.get("esperado"))
        result.setdefault("automatic_difference", result.get("diferenca"))
        if not decision:
            return result

        action = str(decision.get("decision") or "").strip().lower()
        reason = str(decision.get("reason") or "").strip()
        if action == "approved":
            if result.get("requires_manual_authorization"):
                result["status"] = "OK EXTRA AUTORIZADO"
                result["authorization_status"] = "AUTORIZADO"
            else:
                result["status"] = "OK MANUAL"
            result["revisao_manual"] = "APROVADO"
            result["acao_recomendada"] = "Baixa manual registrada. Nenhuma ação pendente para este CT-e."
        elif action == "rejected":
            result["status"] = "RECUSADO MANUAL"
            result["authorization_status"] = "RECUSADO"
            result["revisao_manual"] = "RECUSADO"
            result["acao_recomendada"] = "Tratar a recusa conforme a justificativa registrada."
        elif action == "pending":
            result["status"] = "PENDENTE MANUAL"
            result["authorization_status"] = "PENDENTE"
            result["revisao_manual"] = "PENDENTE"
            result["acao_recomendada"] = "Concluir a conferência e registrar aprovação ou recusa."
        else:
            return result

        result["observacao_manual"] = reason
        result["revisao_data"] = str(decision.get("decided_at") or "")
        result["manual_decision"] = dict(decision)
        trace = list(result.get("trace") or [])
        trace.append(
            f"Decisão manual: {action.upper()} por {decision.get('actor_name') or decision.get('actor_id') or 'usuário autorizado'}. "
            f"Motivo: {reason}"
        )
        result["trace"] = trace
        return result

    @staticmethod
    def _update_row_from_validation(row: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
        updated = dict(row)
        trace = validation.get("trace")
        diagnosis = "\n".join(str(item) for item in trace) if isinstance(trace, (list, tuple)) else str(
            trace or validation.get("detalhe") or ""
        )
        status = str(validation.get("status") or "SEM STATUS")
        updated.update({
            "status": status,
            "expected_value": number(validation.get("esperado")),
            "difference": number(validation.get("diferenca")),
            "diagnosis": diagnosis,
            "operational_reason": str(validation.get("detalhe") or ""),
            "recommended_action": str(validation.get("acao_recomendada") or validation.get("acao_financeira") or ""),
            "error": "" if status != "ERRO VALIDAÇÃO" else str(validation.get("detalhe") or "Erro de validação"),
            "automatic_status": str(validation.get("automatic_status") or status),
            "engine_status": str(validation.get("engine_status") or validation.get("automatic_status") or status),
            "engine_expected_value": number(validation.get("engine_expected_value")),
            "engine_difference": number(validation.get("engine_difference")),
            "requires_manual_authorization": bool(validation.get("requires_manual_authorization", False)),
            "authorization_status": str(validation.get("authorization_status") or ""),
            "manual_decision": json_safe(validation.get("manual_decision") or {}),
            "manual_reason": str(validation.get("observacao_manual") or ""),
            "manual_decided_at": str(validation.get("revisao_data") or ""),
            "validation": json_safe(validation),
        })
        return json_safe(updated)

    def _decision_for(self, info: Mapping[str, Any], path: Path) -> tuple[str, dict[str, Any] | None]:
        key = manual_decision_key(info, path)
        record = self._manual_decisions().get("decisions", {}).get(key)
        return key, dict(record) if isinstance(record, Mapping) else None

    def set_manual_decision(
        self,
        path: Path,
        decision: str,
        reason: str,
        *,
        actor_id: str,
        actor_name: str,
    ) -> dict[str, Any]:
        path = Path(path).resolve()
        action = str(decision or "").strip().lower()
        if action not in {"approved", "rejected", "pending", "clear"}:
            raise ValueError("Decisão manual inválida.")
        reason = str(reason or "").strip()
        if action != "clear" and len(reason) < 3:
            raise ValueError("Informe uma justificativa com pelo menos 3 caracteres.")

        with self._lock:
            data = self._results()
            by_path = data.get("by_path") if isinstance(data, Mapping) else None
            documents = data.get("documents") if isinstance(data, Mapping) else None
            if not isinstance(by_path, Mapping) or not isinstance(documents, Mapping):
                raise ValueError("Processe o CT-e antes de registrar uma decisão manual.")
            identity = by_path.get(str(path))
            row = documents.get(identity) if identity else None
            if not isinstance(row, Mapping):
                raise ValueError("A fotografia oficial deste CT-e não foi encontrada.")
            info = dict(row.get("engine_info") or {})
            key = manual_decision_key(info, path)
            payload = self._manual_decisions()
            decisions = dict(payload.get("decisions") or {})
            record: dict[str, Any] | None
            if action == "clear":
                decisions.pop(key, None)
                record = None
            else:
                record = {
                    "decision": action,
                    "reason": reason,
                    "actor_id": str(actor_id or ""),
                    "actor_name": str(actor_name or actor_id or "Usuário autorizado"),
                    "decided_at": now_iso(),
                    "decision_key": key,
                    "automatic_status": str(row.get("automatic_status") or row.get("status") or ""),
                }
                decisions[key] = record
            write_json_atomic(self.manual_decisions_path, {
                "schema_version": 1,
                "updated_at": now_iso(),
                "decisions": decisions,
            })

            base_validation = row.get("automatic_validation") or row.get("validation") or {}
            if not isinstance(base_validation, Mapping):
                base_validation = {}
            applied = self._apply_manual_decision(base_validation, record)
            updated = self._update_row_from_validation(row, applied)
            updated["automatic_validation"] = json_safe(base_validation)
            updated["decision_key"] = key
            mutable_documents = dict(documents)
            mutable_documents[str(identity)] = updated
            mutable_data = dict(data)
            mutable_data["documents"] = mutable_documents
            mutable_data["updated_at"] = now_iso()
            write_json_atomic(self.results_path, mutable_data)
            self._result_cache = mutable_data
            self._result_cache_mtime_ns = self.results_path.stat().st_mtime_ns
            self._refresh_last_run_counts(mutable_documents.values())
            return updated

    def _refresh_last_run_counts(self, rows: Iterable[Mapping[str, Any]]) -> None:
        counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get("status") or "SEM STATUS")
            counts[status] = counts.get(status, 0) + 1
        total = sum(counts.values())
        ok_count = sum(value for key, value in counts.items() if str(key).upper().startswith("OK"))
        errors = sum(value for key, value in counts.items() if "ERRO" in str(key).upper())
        last = read_json(self.last_run_path, {})
        if not isinstance(last, Mapping):
            last = {}
        updated = dict(last)
        updated.update({
            "updated_at": now_iso(),
            "total": total,
            "processed": total,
            "ok": ok_count,
            "attention": max(total - ok_count - errors, 0),
            "errors": errors,
            "counts": counts,
        })
        write_json_atomic(self.last_run_path, updated)

    def _web_row(
        self,
        path: Path,
        info: Mapping[str, Any],
        validation: Mapping[str, Any],
        tables: Mapping[str, Any],
    ) -> dict[str, Any]:
        stat = path.stat()
        trace = validation.get("trace")
        diagnosis = "\n".join(str(item) for item in trace) if isinstance(trace, (list, tuple)) else str(trace or validation.get("detalhe") or "")
        nfs = all_nfs(info)
        status = str(validation.get("status") or "SEM STATUS")
        result = {
            "identity": file_identity(path),
            "file": path.name,
            "path": str(path.resolve()),
            "source": "web_upload" if self.upload_root in path.resolve().parents else "project",
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "processed_at": now_iso(),
            "cte": str(info.get("numero") or ""),
            "numero": str(info.get("numero") or ""),
            "series": str(info.get("serie") or ""),
            "serie": str(info.get("serie") or ""),
            "partner": self._partner_name(validation, info, tables),
            "recipient": person_name(info, "dest", str(info.get("destinatario") or "Não localizado")),
            "nf": ", ".join(nfs) if nfs else str(validation.get("nf") or "Não localizado"),
            "base_nf": str(validation.get("nf") or first_nf(info) or "Não localizado"),
            "city": destination_label(info) or str(validation.get("destino_comercial") or "Não localizado"),
            "proof": ", ".join(nfs) if nfs else "Não localizado",
            "document_type": str(validation.get("tipo_fiscal") or info.get("tpCTe") or info.get("tipo") or "Não calculado"),
            "charge_type": str(validation.get("tipo_cobranca") or validation.get("tipo_cobranca_extra") or "Não calculado"),
            "compared_component": str(validation.get("componente_comparado") or "Não calculado"),
            "xml_value": number(validation.get("valor_comparado")) if number(validation.get("valor_comparado")) is not None else number(info.get("valor")),
            "expected_value": number(validation.get("esperado")),
            "difference": number(validation.get("diferenca")),
            "status": status,
            "automatic_status": str(validation.get("automatic_status") or status),
            "engine_status": str(validation.get("engine_status") or validation.get("automatic_status") or status),
            "engine_expected_value": number(validation.get("engine_expected_value")),
            "engine_difference": number(validation.get("engine_difference")),
            "requires_manual_authorization": bool(validation.get("requires_manual_authorization", False)),
            "authorization_status": str(validation.get("authorization_status") or ""),
            "manual_decision": json_safe(validation.get("manual_decision") or {}),
            "manual_reason": str(validation.get("observacao_manual") or ""),
            "manual_decided_at": str(validation.get("revisao_data") or ""),
            "diagnosis": diagnosis,
            "compact_calculation": str(validation.get("controle_dacte_compacto") or ""),
            "search_method": str(validation.get("metodo_busca") or validation.get("base_match_method") or "SSW Web por NF"),
            "partner_table": str(validation.get("partner_name") or validation.get("partner_id") or "Não localizado"),
            "applied_rule": str(validation.get("regra_comercial") or validation.get("regra_extra") or validation.get("modo_calculo") or "Não calculado"),
            "calculation_base": number(validation.get("base_frete")) if number(validation.get("base_frete")) is not None else number(validation.get("base_calculo")),
            "percentage": percentage_points(validation.get("percentual")),
            "operational_reason": str(validation.get("detalhe") or ""),
            "recommended_action": str(validation.get("acao_recomendada") or validation.get("acao_financeira") or ""),
            "error": "" if status != "ERRO VALIDAÇÃO" else str(validation.get("detalhe") or "Erro de validação"),
            "engine_info": json_safe(info),
            "validation": json_safe(validation),
        }
        return json_safe(result)

    def _non_cte_row(self, path: Path, info: Mapping[str, Any]) -> dict[str, Any]:
        stat = path.stat()
        is_error = bool(info.get("erro"))
        return {
            "identity": file_identity(path),
            "file": path.name,
            "path": str(path.resolve()),
            "source": "web_upload" if self.upload_root in path.resolve().parents else "project",
            "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "processed_at": now_iso(),
            "cte": str(info.get("numero") or ""),
            "numero": str(info.get("numero") or ""),
            "series": str(info.get("serie") or ""),
            "serie": str(info.get("serie") or ""),
            "partner": str(info.get("emitente") or "Não localizado"),
            "recipient": str(info.get("destinatario") or "Não localizado"),
            "nf": str(info.get("numero") or "Não localizado"),
            "base_nf": "Não localizado",
            "city": "Não localizado",
            "proof": str(info.get("numero") or "Não localizado"),
            "document_type": str(info.get("tipo") or "XML"),
            "charge_type": "Documento auxiliar",
            "compared_component": "Não calculado",
            "xml_value": number(info.get("valor")),
            "expected_value": None,
            "difference": None,
            "status": "Erro de leitura" if is_error else "NÃO É CT-e",
            "diagnosis": str(info.get("erro") or "Documento ignorado pela validação comercial por não ser CT-e."),
            "compact_calculation": "",
            "search_method": "Parser oficial RC26.6",
            "partner_table": "Não aplicável",
            "applied_rule": "Não aplicável",
            "calculation_base": None,
            "percentage": None,
            "operational_reason": str(info.get("erro") or "Documento sem estrutura de CT-e."),
            "recommended_action": "",
            "error": str(info.get("erro") or ""),
            "engine_info": json_safe(info),
            "validation": {
                "status": "Erro de leitura" if is_error else "NÃO É CT-e",
                "detalhe": str(info.get("erro") or "Documento sem estrutura de CT-e."),
            },
        }

    def process(
        self,
        xml_paths: Iterable[Path],
        progress: Callable[[int, int, str, str], None] | None = None,
    ) -> dict[str, Any]:
        paths = [Path(path).resolve() for path in xml_paths if Path(path).is_file() and Path(path).suffix.lower() == ".xml"]
        paths = sorted(dict.fromkeys(paths), key=lambda item: str(item).lower())
        if not paths:
            raise ValueError("Nenhum XML foi encontrado para processamento.")

        started_iso = now_iso()
        started = time.monotonic()
        engine, base_data, tables, base_source, table_source = self._load_dependencies()
        self_test = self._contract_self_test(engine, tables)
        total = len(paths)
        counts: dict[str, int] = {}
        documents: dict[str, dict[str, Any]] = {}
        by_path: dict[str, str] = {}

        for position, path in enumerate(paths, start=1):
            if progress:
                progress(position - 1, total, path.name, "Lendo XML com o parser oficial")
            try:
                info = engine.parse_xml(path)
                if not isinstance(info, Mapping):
                    raise RuntimeError("O parser oficial não retornou um documento válido.")
                if str(info.get("tipo") or "").strip().upper() == "CT-E":
                    commercial_info, commercial_base, receiver_metadata = commercial_inputs_using_receiver(info, base_data)
                    validation = engine.validate_cte_value(commercial_info, commercial_base, tables)
                    if not isinstance(validation, Mapping):
                        raise RuntimeError("O validador oficial não retornou uma estrutura válida.")
                    validation = annotate_receiver_route(validation, receiver_metadata)
                    validation = publish_extra_comparison_fields(validation, info)
                    validation = self._apply_partner_calculated_reentrega(
                        validation, info, commercial_info, commercial_base, tables, engine
                    )
                    validation = self._apply_web_contract_adapters(
                        validation, info, tables,
                        commercial_info=commercial_info,
                        commercial_base=commercial_base,
                        engine=engine,
                    )
                    validation = publish_extra_comparison_fields(validation, info)
                    validation = self._apply_operational_authorization_policy(validation, info)
                    automatic_validation = json_safe(validation)
                    decision_key, manual_decision = self._decision_for(info, path)
                    validation = self._apply_manual_decision(validation, manual_decision)
                    row = self._web_row(path, info, validation, tables)
                    row["automatic_validation"] = automatic_validation
                    row["decision_key"] = decision_key
                else:
                    row = self._non_cte_row(path, info)
            except Exception as exc:
                row = self._non_cte_row(path, {"tipo": "XML inválido", "erro": str(exc)})
                row["status"] = "ERRO VALIDAÇÃO"
                row["validation"] = {"status": "ERRO VALIDAÇÃO", "detalhe": str(exc), "trace": [str(exc)]}

            identity = str(row["identity"])
            documents[identity] = row
            by_path[str(path)] = identity
            status = str(row.get("status") or "SEM STATUS")
            counts[status] = counts.get(status, 0) + 1
            if progress:
                progress(position, total, path.name, status)

        ok_count = sum(value for key, value in counts.items() if str(key).upper().startswith("OK"))
        errors = sum(value for key, value in counts.items() if "ERRO" in str(key).upper())
        payload = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "service_version": SERVICE_VERSION,
            "updated_at": now_iso(),
            "base_source": str(base_source),
            "base_file_count": len(self._base_files(base_source)),
            "base_row_count": len(list(base_data.get("rows") or [])),
            "table_source": str(table_source),
            "self_test": self_test,
            "documents": documents,
            "by_path": by_path,
        }
        write_json_atomic(self.results_path, payload)
        self._result_cache = payload
        self._result_cache_mtime_ns = self.results_path.stat().st_mtime_ns

        summary = {
            "status": "concluido",
            "started_at": started_iso,
            "finished_at": now_iso(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "total": total,
            "processed": total,
            "ok": ok_count,
            "attention": max(total - ok_count - errors, 0),
            "errors": errors,
            "counts": counts,
            "base_source": str(base_source),
            "base_file_count": payload["base_file_count"],
            "base_row_count": payload["base_row_count"],
            "table_source": str(table_source),
            "self_test": self_test,
        }
        write_json_atomic(self.last_run_path, summary)
        return summary

    def _results(self) -> dict[str, Any]:
        try:
            mtime = self.results_path.stat().st_mtime_ns
        except OSError:
            return {}
        if self._result_cache is None or self._result_cache_mtime_ns != mtime:
            self._result_cache = read_json(self.results_path, {})
            self._result_cache_mtime_ns = mtime
        return self._result_cache if isinstance(self._result_cache, dict) else {}

    def clear_results(self) -> dict[str, Any]:
        """Remove somente a fotografia do lote XML atual.

        A Base SSW, a tabela de parceiros e o contrato sentinela permanecem
        preservados. Relatórios já exportados também não são apagados.
        """
        removed: list[str] = []
        with self._lock:
            for path in (self.results_path, self.last_run_path):
                try:
                    path.unlink()
                    removed.append(path.name)
                except FileNotFoundError:
                    pass
            self._result_cache = None
            self._result_cache_mtime_ns = -1
        return {
            "cleared_at": now_iso(),
            "removed_state_files": removed,
            "results_cleared": True,
        }

    def stored_row(self, path: Path) -> dict[str, Any] | None:
        path = Path(path).resolve()
        data = self._results()
        by_path = data.get("by_path") if isinstance(data, Mapping) else None
        documents = data.get("documents") if isinstance(data, Mapping) else None
        if not isinstance(by_path, Mapping) or not isinstance(documents, Mapping):
            return None
        identity = by_path.get(str(path))
        if not identity:
            return None
        try:
            if identity != file_identity(path):
                return None
        except OSError:
            return None
        row = documents.get(identity)
        return dict(row) if isinstance(row, Mapping) else None


__all__ = ["OfficialXmlEngineService", "SERVICE_VERSION", "file_identity", "manual_decision_key"]
