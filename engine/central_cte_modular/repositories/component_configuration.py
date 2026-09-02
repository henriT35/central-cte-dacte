from __future__ import annotations

"""Configuração modular dos componentes comerciais exibidos no DACTE.

A lógica nasceu no hotfix 2.6.31 e agora é aplicada explicitamente tanto ao
repositório modular quanto ao resultado de qualquer fallback de tabela. Nenhum
método do motor é substituído em runtime.
"""

from collections.abc import MutableMapping
from typing import Any

from ..infrastructure.normalization import norm_text, normalize_header
from .value_parsers import (
    parse_number_br,
    parse_optional_single_money,
    parse_percent,
)

COMPONENT_CONFIGURATION_VERSION = "2.6.69.6"


class ComponentConfigurationService:
    """Normaliza GRIS, pedágio e identificação do controle interno."""

    @staticmethod
    def _yes(value: Any) -> bool:
        return norm_text(value) in {"S", "SIM", "YES", "TRUE", "1", "ATIVO", "OK"}

    @staticmethod
    def _first_raw(raw: MutableMapping[str, Any] | None, *keys: str) -> Any:
        source = raw or {}
        for key in keys:
            normalized = normalize_header(key)
            if normalized in source and str(source.get(normalized, "") or "").strip() != "":
                return source.get(normalized)
        return ""

    def enrich_rule(self, item: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        raw = item.get("raw", {}) or {}
        gris_raw = self._first_raw(raw, "GRIS Ativo", "GRIS", "Usa GRIS", "Cobrar GRIS")
        gris_percent_raw = self._first_raw(raw, "Percentual GRIS", "GRIS Percentual", "% GRIS", "Perc GRIS")
        toll_raw = self._first_raw(
            raw,
            "Pedágio Ativo", "Pedagio Ativo", "Pedágio", "Pedagio",
            "Usa Pedágio", "Usa Pedagio",
        )
        toll_value_raw = self._first_raw(
            raw,
            "Valor Pedágio", "Valor Pedagio", "Pedágio Valor", "Pedagio Valor",
            "Pedágio por Fração", "Pedagio por Fracao",
        )
        toll_fraction_raw = self._first_raw(
            raw,
            "Fração Pedágio KG", "Fracao Pedagio KG", "Fração KG", "Fracao KG",
            "Pedágio Fração KG", "Pedagio Fracao KG",
        )
        toll_type_raw = (
            self._first_raw(
                raw,
                "Tipo Pedágio", "Tipo Pedagio", "Pedágio Tipo", "Pedagio Tipo",
                "Modalidade Pedágio", "Modalidade Pedagio",
            )
            or item.get("tipo_pedagio")
            or item.get("pedagio_tipo")
            or ""
        )
        control_raw = self._first_raw(
            raw,
            "Controle DACTE", "Mostrar Controle DACTE", "Controle Interno",
            "Validação DACTE", "Validacao DACTE",
        )
        rule_label = str(self._first_raw(raw, "Nome Controle", "Regra Controle", "Nome Regra") or "").strip()

        gris_percent = parse_percent(gris_percent_raw)
        toll_value = parse_optional_single_money(toll_value_raw)
        parsed_toll_fraction = parse_number_br(toll_fraction_raw)
        normalized_toll_type = norm_text(toll_type_raw)
        compact_toll_type = normalized_toll_type.replace(" ", "").replace("-", "")
        explicit_cte = (
            compact_toll_type in {"CTE", "CTRC", "CONHECIMENTO", "EMISSAO"}
            or "POR CTE" in normalized_toll_type
            or "POR CONHECIMENTO" in normalized_toll_type
            or "POR EMISSAO" in normalized_toll_type
        )
        explicit_kg = any(
            token in normalized_toll_type
            for token in ("KG", "PESO", "FRACAO")
        )
        if explicit_cte:
            toll_type = "CTE"
            toll_fraction = 0.0
        elif explicit_kg or parsed_toll_fraction > 0:
            toll_type = "KG"
            toll_fraction = parsed_toll_fraction or 100.0
        else:
            toll_type = "CTE"
            toll_fraction = 0.0

        item["gris_ativo"] = self._yes(gris_raw) or gris_percent > 0
        item["gris_percentual"] = gris_percent
        item["pedagio_ativo"] = self._yes(toll_raw) or toll_value > 0
        item["pedagio_valor"] = toll_value
        item["pedagio_tipo"] = toll_type
        item["tipo_pedagio"] = toll_type
        item["pedagio_fracao_kg"] = toll_fraction
        item["fracao_pedagio_kg"] = toll_fraction
        item["controle_dacte"] = self._yes(control_raw) or item["gris_ativo"] or item["pedagio_ativo"]
        default_name = (
            "RODOTEC"
            if "RODOTEC" in norm_text(item.get("regiao", "") or raw.get("REGIAOBASE", ""))
            else "TABELA"
        )
        item["controle_regra_nome"] = rule_label or default_name
        return item

    def enrich_tables(self, tables: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        for item in tables.get("rules", []) or []:
            if isinstance(item, MutableMapping):
                self.enrich_rule(item)
        for item in tables.get("regions", []) or []:
            if isinstance(item, MutableMapping):
                self.enrich_rule(item)
        tables["componentes_2631"] = True
        return tables


__all__ = ["COMPONENT_CONFIGURATION_VERSION", "ComponentConfigurationService"]
