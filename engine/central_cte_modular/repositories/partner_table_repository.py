from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from ..infrastructure.formatting import extract_cnpjs
from ..infrastructure.normalization import norm_location, norm_text
from .component_configuration import ComponentConfigurationService
from .value_parsers import (
    normalize_base_calculo,
    parse_number_br,
    parse_optional_single_money,
    parse_percent,
    rows_to_dicts,
)
from .xlsx_reader import StandardLibraryXlsxReader


def _weight_band_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Converte descrições como '08 a 15 toneladas' em limites estruturados."""
    explicit_min = parse_number_br(
        row.get("PESOMINIMOKG", "") or row.get("PESOINICIALKG", "") or row.get("PESODEKG", "")
    )
    explicit_max = parse_number_br(
        row.get("PESOMAXIMOKG", "") or row.get("PESOFINALKG", "") or row.get("PESOATEKG", "")
    )
    if explicit_min or explicit_max:
        return {
            "peso_min_kg": explicit_min,
            "peso_max_kg": explicit_max,
            "peso_min_inclusivo": True,
            "peso_max_inclusivo": True,
        }

    text = norm_text(row.get("TIPOTRECHO", "") or row.get("FAIXAPESO", "") or row.get("OBSERVACAO", ""))
    range_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:A|ATE|-)\s*(\d+(?:[.,]\d+)?)\s*TON", text)
    if range_match:
        lower = parse_number_br(range_match.group(1)) * 1000.0
        upper = parse_number_br(range_match.group(2)) * 1000.0
        return {
            "peso_min_kg": lower,
            "peso_max_kg": upper,
            "peso_min_inclusivo": True,
            "peso_max_inclusivo": True,
        }
    above_match = re.search(r"ACIMA\s+DE\s+(\d+(?:[.,]\d+)?)\s*TON", text)
    if above_match:
        return {
            "peso_min_kg": parse_number_br(above_match.group(1)) * 1000.0,
            "peso_max_kg": 0.0,
            "peso_min_inclusivo": False,
            "peso_max_inclusivo": True,
        }
    return {
        "peso_min_kg": 0.0,
        "peso_max_kg": 0.0,
        "peso_min_inclusivo": True,
        "peso_max_inclusivo": True,
    }


class PartnerTableRepository:
    """Lê e normaliza o cadastro operacional das tabelas de parceiros."""

    def __init__(
        self,
        reader: StandardLibraryXlsxReader | None = None,
        component_configuration: ComponentConfigurationService | None = None,
    ) -> None:
        self.reader = reader or StandardLibraryXlsxReader()
        self.component_configuration = component_configuration or ComponentConfigurationService()

    def _add_component_configuration(self, item: dict[str, Any]) -> None:
        self.component_configuration.enrich_rule(item)

    def enrich_weight_bands(self, tables: dict[str, Any]) -> dict[str, Any]:
        """Aplica faixas de peso tanto ao carregador modular quanto ao legado.

        O guardião de repositório exige igualdade estrutural. Por isso a mesma
        normalização precisa ocorrer depois de qualquer carregador escolhido.
        """
        rules = list(tables.get("rules", []) or [])
        metadata: dict[tuple[str, str, str, float, float], dict[str, Any]] = {}
        for rule in rules:
            band = _weight_band_from_row(dict(rule.get("raw", {}) or {}))
            for key, value in band.items():
                rule[key] = value
            raw = dict(rule.get("raw", {}) or {})
            rule["tipo_trecho"] = str(raw.get("TIPOTRECHO", "") or rule.get("tipo_trecho", "") or "").strip()
            if not (rule.get("peso_min_kg") or rule.get("peso_max_kg")):
                continue
            lookup = (
                str(rule.get("partner_id") or ""),
                str(rule.get("regiao") or ""),
                str(rule.get("destino_cidade") or ""),
                round(float(rule.get("percent") or 0.0), 8),
                round(float(rule.get("minimum") or 0.0), 2),
            )
            metadata[lookup] = {
                "tipo_trecho": rule.get("tipo_trecho", ""),
                "peso_min_kg": rule.get("peso_min_kg", 0.0),
                "peso_max_kg": rule.get("peso_max_kg", 0.0),
                "peso_min_inclusivo": rule.get("peso_min_inclusivo", True),
                "peso_max_inclusivo": rule.get("peso_max_inclusivo", True),
            }
        for region in list(tables.get("regions", []) or []):
            lookup = (
                str(region.get("partner_id") or ""),
                str(region.get("regiao") or ""),
                str(region.get("cidade") or ""),
                round(float(region.get("percent") or 0.0), 8),
                round(float(region.get("minimum") or 0.0), 2),
            )
            region.update(metadata.get(lookup, {
                "tipo_trecho": str(region.get("tipo_trecho", "") or ""),
                "peso_min_kg": float(region.get("peso_min_kg", 0.0) or 0.0),
                "peso_max_kg": float(region.get("peso_max_kg", 0.0) or 0.0),
                "peso_min_inclusivo": bool(region.get("peso_min_inclusivo", True)),
                "peso_max_inclusivo": bool(region.get("peso_max_inclusivo", True)),
            }))
        tables["rules"] = rules
        return tables

    def load(self, file_path: str | Path) -> dict[str, Any]:
        path = Path(file_path)
        partners_rows, _ = rows_to_dicts(self.reader.read_sheet(path, "PARCEIROS"))
        rules_rows, _ = rows_to_dicts(self.reader.read_sheet(path, "REGRAS_PERCENTUAL"))
        config_rows, _ = rows_to_dicts(self.reader.try_read_sheet(path, "CONFIG_PROGRAMA"))
        regions_rows, _ = rows_to_dicts(self.reader.try_read_sheet(path, "REGIOES"))
        extras_rows, _ = rows_to_dicts(self.reader.try_read_sheet(path, "REGRAS_EXTRAS"))
        aliases_rows, _ = rows_to_dicts(self.reader.try_read_sheet(path, "ALIAS_PARCEIROS"))
        special_rows, _ = rows_to_dicts(self.reader.try_read_sheet(path, "REGRAS_PESO_ESPECIAL"))

        partners: dict[str, dict[str, Any]] = {}
        cnpj_to_id: dict[str, str] = {}
        aliases: list[tuple[str, str]] = []
        for row in partners_rows:
            partner_id = str(row.get("PARCEIROID", "")).strip()
            if not partner_id:
                continue
            name = str(row.get("NOMEPARCEIRO", "")).strip()
            alias = str(row.get("NOMENOXMLALIASPRINCIPAL", "")).strip()
            cnpjs: list[str] = []
            for key in ("CNPJ", "CNPJ2", "CNPJ3", "CNPJALTERNATIVO", "CNPJALTERNATIVO2", "CNPJSECUNDARIO", "CNPJSALTERNATIVOS", "OUTROSCNPJS"):
                for cnpj in extract_cnpjs(row.get(key, "")):
                    if cnpj not in cnpjs:
                        cnpjs.append(cnpj)
            existing = partners.get(partner_id)
            if existing:
                if name and not existing.get("name"):
                    existing["name"] = name
                if alias and not existing.get("alias"):
                    existing["alias"] = alias
                for cnpj in cnpjs:
                    if cnpj not in existing.setdefault("cnpjs", []):
                        existing["cnpjs"].append(cnpj)
                if existing.get("cnpjs"):
                    existing["cnpj"] = existing["cnpjs"][0]
            else:
                partners[partner_id] = {"id": partner_id, "name": name, "cnpj": cnpjs[0] if cnpjs else "", "cnpjs": cnpjs, "alias": alias}
            for cnpj in cnpjs:
                cnpj_to_id[cnpj] = partner_id
            for candidate_name in (name, alias):
                if candidate_name:
                    aliases.append((norm_text(candidate_name), partner_id))

        for row in aliases_rows:
            partner_id = str(row.get("PARCEIROID", "") or row.get("IDPARCEIRO", "")).strip()
            alias_name = str(row.get("NOMENOXML", "") or row.get("NOMEALIAS", "") or row.get("ALIAS", "") or row.get("NOMENOXMLALIASPRINCIPAL", "")).strip()
            if partner_id and alias_name:
                aliases.append((norm_text(alias_name), partner_id))

        rules: list[dict[str, Any]] = []
        for row in rules_rows:
            partner_id = str(row.get("PARCEIROID", "")).strip()
            if not partner_id:
                continue
            rules.append({
                "partner_id": partner_id,
                "regra_id": str(row.get("REGRAID", "") or "").strip(),
                "origem_cidade": norm_location(row.get("ORIGEMCIDADE", "")),
                "origem_uf": norm_text(row.get("ORIGEMUF", "")),
                "destino_cidade": norm_location(row.get("DESTINOCIDADE", "")),
                "destino_uf": norm_text(row.get("DESTINOUF", "")),
                "regiao": norm_text(row.get("REGIAOBASE", "")),
                "percent": parse_percent(row.get("PERCENTUAL", "")),
                "minimum": parse_number_br(row.get("FRETEMINIMO", "")),
                "ton_rate": parse_number_br(
                    row.get("TONELAGEMMINIMARTON", "")
                    or row.get("TONELAGEMMINIMA", "")
                    or row.get("TONELAGEM", "")
                    or row.get("RSTON", "")
                    or row.get("VALORTON", "")
                ),
                "modo_calculo": norm_text(
                    row.get("MODOCALCULO", "")
                    or row.get("TIPOCALCULO", "")
                    or row.get("FORMACALCULO", "")
                    or (row.get("TIPOCALCULOCOMPACTO", "") if partner_id == "AC_LOG_C_VARGAS" else "")
                    or (row.get("MODOCALCULOCOMPACTO", "") if partner_id == "AC_LOG_C_VARGAS" else "")
                ),
                "base_calculo": normalize_base_calculo(row.get("BASECALCULO", "ORIGINAL")),
                "inclui_complementar": norm_text(row.get("INCLUICOMPLEMENTAR", "NAO")),
                "status_revisao": norm_text(row.get("STATUSREVISAO", "")),
                "gris_ativo": norm_text(row.get("GRISATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
                "percentual_gris": parse_percent(row.get("PERCENTUALGRIS", "")),
                "pedagio_ativo": norm_text(row.get("PEDAGIOATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
                "valor_pedagio": parse_number_br(row.get("VALORPEDAGIO", "") or row.get("PEDAGIO", "")),
                "fracao_pedagio_kg": parse_number_br(row.get("FRACAOPEDAGIOKG", "")),
                "tipo_pedagio": norm_text(row.get("TIPOPEDAGIO", "")),
                "tipo_trecho": str(row.get("TIPOTRECHO", "") or "").strip(),
                **_weight_band_from_row(row),
                "raw": row,
                "source": "REGRAS_PERCENTUAL",
            })

        weight_metadata: dict[tuple[str, str, str, float, float], dict[str, Any]] = {}
        for rule in rules:
            if not (rule.get("peso_min_kg") or rule.get("peso_max_kg")):
                continue
            key = (
                str(rule.get("partner_id") or ""),
                str(rule.get("regiao") or ""),
                str(rule.get("destino_cidade") or ""),
                round(float(rule.get("percent") or 0.0), 8),
                round(float(rule.get("minimum") or 0.0), 2),
            )
            weight_metadata[key] = {
                "tipo_trecho": rule.get("tipo_trecho", ""),
                "peso_min_kg": rule.get("peso_min_kg", 0.0),
                "peso_max_kg": rule.get("peso_max_kg", 0.0),
                "peso_min_inclusivo": rule.get("peso_min_inclusivo", True),
                "peso_max_inclusivo": rule.get("peso_max_inclusivo", True),
            }

        regions: list[dict[str, Any]] = []
        for row in regions_rows:
            partner_id = str(row.get("PARCEIROID", "")).strip()
            if not partner_id:
                continue
            region_name = norm_text(row.get("REGIAOBASE", ""))
            city = norm_location(row.get("CIDADE", ""))
            percent = parse_percent(row.get("PERCENTUALDEFAULT", ""))
            minimum = parse_number_br(row.get("FRETEMINIMODEFAULT", ""))
            metadata = weight_metadata.get((partner_id, region_name, city, round(percent, 8), round(minimum, 2)), {})
            regions.append({
                "partner_id": partner_id,
                "regra_id": str(row.get("REGRAID", "") or row.get("REGIAOID", "") or "").strip(),
                "regiao": region_name,
                "cidade": city,
                "uf": norm_text(row.get("UF", "")),
                "percent": percent,
                "minimum": minimum,
                "tipo_trecho": metadata.get("tipo_trecho", ""),
                "peso_min_kg": metadata.get("peso_min_kg", 0.0),
                "peso_max_kg": metadata.get("peso_max_kg", 0.0),
                "peso_min_inclusivo": metadata.get("peso_min_inclusivo", True),
                "peso_max_inclusivo": metadata.get("peso_max_inclusivo", True),
                "ton_rate": parse_number_br(row.get("TONELAGEMMINIMARTON", "") or row.get("TONELAGEMMINIMA", "") or row.get("TONELAGEM", "") or row.get("RSTON", "") or row.get("VALORTON", "")),
                "modo_calculo": norm_text(
                    row.get("MODOCALCULO", "")
                    or row.get("TIPOCALCULO", "")
                    or row.get("FORMACALCULO", "")
                    or (row.get("TIPOCALCULOCOMPACTO", "") if partner_id == "AC_LOG_C_VARGAS" else "")
                    or (row.get("MODOCALCULOCOMPACTO", "") if partner_id == "AC_LOG_C_VARGAS" else "")
                ),
                "base_calculo": normalize_base_calculo(row.get("BASECALCULO", "ORIGINAL")),
                "status_revisao": norm_text(row.get("STATUSREVISAO", "")),
                "gris_ativo": norm_text(row.get("GRISATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
                "percentual_gris": parse_percent(row.get("PERCENTUALGRIS", "")),
                "pedagio_ativo": norm_text(row.get("PEDAGIOATIVO", "")) in {"SIM", "S", "1", "TRUE", "ATIVO"},
                "valor_pedagio": parse_number_br(row.get("VALORPEDAGIO", "")),
                "fracao_pedagio_kg": parse_number_br(row.get("FRACAOPEDAGIOKG", "")),
                "tipo_pedagio": norm_text(row.get("TIPOPEDAGIO", "")),
                "raw": row,
            })

        extras: list[dict[str, Any]] = []
        for row in extras_rows:
            partner_id = str(row.get("PARCEIROID", "") or row.get("IDPARCEIRO", "")).strip()
            if not partner_id:
                continue
            extras.append({
                "partner_id": partner_id,
                "tipo_extra": norm_text(row.get("TIPOEXTRA", "") or row.get("TIPO", "") or row.get("EVENTO", "") or row.get("REGRA", "") or row.get("DESCRICAO", "")),
                "percent": parse_percent(row.get("PERCENTUAL", "") or row.get("PERCENTUALSOBREFRETE", "") or row.get("VALORPERCENTUAL", "")),
                "valor_fixo": parse_optional_single_money(row.get("VALORFIXO", "") or row.get("VALOR", "") or row.get("TAXA", "")),
                "minimum": parse_optional_single_money(row.get("FRETEMINIMO", "") or row.get("VALORMINIMO", "") or row.get("MINIMO", "")),
                "base_calculo": normalize_base_calculo(row.get("BASECALCULO", "FRETE_ORIGEM")),
                "condicao": str(row.get("CONDICAO", "") or "").strip(),
                "status_revisao": norm_text(row.get("STATUSREVISAO", "")),
                "observacao": str(row.get("OBSERVACAO", "") or row.get("OBS", "") or row.get("DESCRICAO", "")).strip(),
                "raw": row,
                "source": "REGRAS_EXTRAS",
            })

        special_weight: list[dict[str, Any]] = []
        for row in special_rows:
            partner_id = str(row.get("PARCEIROID", "") or row.get("IDPARCEIRO", "")).strip()
            if not partner_id:
                continue
            special_weight.append({
                "partner_id": partner_id,
                "destino_cidade": norm_location(row.get("DESTINOCIDADE", "") or row.get("CIDADE", "")),
                "destino_uf": norm_text(row.get("DESTINOUF", "") or row.get("UF", "")),
                "regiao": norm_text(row.get("REGIAOBASE", "") or row.get("REGIAO", "")),
                "peso_min_kg": parse_number_br(row.get("PESOMINIMOKG", "") or row.get("PESOLIMITEKG", "") or row.get("PESOACIMADEKG", "") or row.get("LIMITEKG", "")),
                "percent": parse_percent(row.get("PERCENTUAL", "") or row.get("PERCENTUALSOBREFRETE", "") or row.get("VALORPERCENTUAL", "")),
                "minimum": parse_number_br(row.get("FRETEMINIMO", "") or row.get("VALORMINIMO", "") or row.get("MINIMO", "")),
                "base_calculo": normalize_base_calculo(row.get("BASECALCULO", "ORIGEM")),
                "modo_calculo": norm_text(row.get("MODOCALCULO", "") or row.get("TIPOCALCULO", "") or "PESO_ESPECIAL"),
                "status_revisao": norm_text(row.get("STATUSREVISAO", "")),
                "observacao": str(row.get("OBSERVACAO", "") or row.get("OBS", "") or "").strip(),
                "raw": row,
                "source": "REGRAS_PESO_ESPECIAL",
            })

        tolerance = 1.0
        for row in config_rows:
            key = norm_text(row.get("CHAVE", ""))
            if "TOLER" in key and "PERCENT" not in key:
                tolerance = parse_number_br(row.get("VALOR", "1")) or 1.0
        tables = {
            "path": str(path),
            "partners": partners,
            "cnpj_to_id": cnpj_to_id,
            "aliases": aliases,
            "rules": rules,
            "regions": regions,
            "extras": extras,
            "peso_especial": special_weight,
            "tolerance": tolerance,
        }
        tables = self.enrich_weight_bands(tables)
        return dict(self.component_configuration.enrich_tables(tables))
