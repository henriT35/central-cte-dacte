from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class CommercialDependencies:
    norm_text: Callable[[Any], str]
    only_digits: Callable[[Any], str]
    parse_number_br: Callable[[Any], float]
    normalize_nf: Callable[[Any], str]
    partner_policy: Callable[[Any], Mapping[str, Any]]


class ModularCommercialEngine:
    """Núcleo comercial puro extraído do motor legado.

    Nesta etapa o orquestrador geral de validação ainda é legado. Estas funções
    cuidam da identificação do parceiro, classificação da cobrança, escolha da
    rota/regra e componentes matemáticos. Cada função é promovida somente quando
    o guardião comprova equivalência exata com a implementação congelada.
    """

    VERSION = "2.7.0-rc17"

    def __init__(self, dependencies: CommercialDependencies) -> None:
        self.d = dependencies

    def identify_partner(self, info: Mapping[str, Any], tables: Mapping[str, Any] | None) -> str | None:
        if not tables:
            return None
        emit = info.get("emit", {}) or {}
        cnpj = self.d.only_digits(emit.get("cnpjcpf", ""))
        if cnpj and cnpj in tables.get("cnpj_to_id", {}):
            return tables["cnpj_to_id"][cnpj]
        name = self.d.norm_text(info.get("emitente", ""))
        if name:
            aliases = list(tables.get("aliases", []))
            for alias, partner_id in aliases:
                if alias and alias == name:
                    return partner_id
            partial: list[str] = []
            for alias, partner_id in aliases:
                if alias and (alias in name or name in alias) and partner_id not in partial:
                    partial.append(partner_id)
            if len(partial) == 1:
                return partial[0]
        return None

    def detect_partner_charge_type(self, info: Mapping[str, Any]) -> str:
        pieces = [info.get("tpCTe", ""), info.get("tpServ", ""), info.get("natOp", ""), info.get("cfop", ""), info.get("obs", ""), info.get("produto", ""), info.get("outras_carac", "")]
        for component in info.get("componentes", []) or []:
            pieces.append(component.get("nome", ""))
        text = self.d.norm_text(" ".join(str(value or "") for value in pieces))
        if "COTACAO" in text and "AUTORIZ" in text: return "COTACAO_AUTORIZADA"
        if "FRETE REF" in text and ("COT" in text.split() or "COTACAO" in text): return "COTACAO_ESPECIAL"
        if "ANUL" in text: return "ANULACAO"
        if "SUBSTIT" in text: return "SUBSTITUICAO"
        if "TABELA ANTIGA" in text or "FRETE ANTIGO" in text: return "TABELA_ANTIGA"
        if "REEMBOLSO" in text and "DESCARG" in text: return "REEMBOLSO_DESCARGA"
        if "CAPATAZIA" in text: return "CAPATAZIA"
        if "TEMPO EXCEDIDO" in text or "PERMANENCIA EXCEDIDA" in text or "CUSTO EXTRA 5" in text or "5 HORAS" in text: return "TEMPO_EXCEDIDO"
        if "DIFICULDADE DE ACESSO" in text or "TDA" in text.split(): return "TDA"
        if "TDE" in text or "DIFICULDADE DE ENTREGA" in text: return "TDE"
        if any(token in text for token in ("REENTREGA", "REEENTREGA", "RE ENTREGA", "2 ENTREGA", "SEGUNDA ENTREGA")): return "REENTREGA"
        if "DEVOLUCAO" in text or "RETORNO DE MERCADORIA" in text: return "DEVOLUCAO"
        if "COMPLEMENT" in text or "COMPL" in text: return "COMPLEMENTAR"
        return "NORMAL"

    def extra_matches_charge_type(self, extra: Mapping[str, Any], charge_type: str) -> bool:
        extra_type = self.d.norm_text(extra.get("tipo_extra", ""))
        charge = self.d.norm_text(charge_type)
        if not extra_type or charge == "NORMAL": return False
        # TDA não pode usar correspondência por substring: "TDA" aparece dentro
        # de palavras como "ESTADIA" e selecionaria uma regra financeira errada.
        if charge == "TDA":
            return extra_type == "TDA" or "DIFICULDADE ACESSO" in extra_type
        if charge in extra_type or extra_type in charge: return True
        aliases = {
            "COMPLEMENTAR": ["COMPLEMENTO", "COMPLEMENTAR", "COMPL", "DIFERENCA", "AJUSTE"],
            "DEVOLUCAO": ["DEVOLUCAO", "RETORNO"], "REENTREGA": ["REENTREGA", "RE ENTREGA", "2 ENTREGA", "SEGUNDA ENTREGA"],
            "ANULACAO": ["ANULACAO", "ANUL"], "SUBSTITUICAO": ["SUBSTITUICAO", "SUBSTIT"],
            "REEMBOLSO_DESCARGA": ["REEMBOLSO DESCARGA", "DESCARGA", "TPD DESCARGAS"], "CAPATAZIA": ["CAPATAZIA"],
            "TDA": ["TDA", "DIFICULDADE ACESSO"], "TDE": ["TDE", "DIFICULDADE ENTREGA"], "TEMPO_EXCEDIDO": ["TEMPO EXCEDIDO", "PERMANENCIA", "ESTADIA"],
            "TABELA_ANTIGA": ["TABELA ANTIGA", "HISTORICA", "FRETE ANTIGO"], "VEICULO_DEDICADO": ["VEICULO DEDICADO", "OPERACAO DEDICADA", "COLETA PALETES"],
            "COTACAO_AUTORIZADA": ["COTACAO AUTORIZADA", "COTACAO_AUTORIZADA"],
            "COTACAO_ESPECIAL": ["COTACAO ESPECIAL", "COTACAO_ESPECIAL", "FRETE REF"],
        }
        return any(alias in extra_type for alias in aliases.get(charge, []))

    def _extra_condition_matches(self, extra: Mapping[str, Any], base_row: Mapping[str, Any] | None = None) -> bool:
        condition = self.d.norm_text(extra.get("condicao", ""))
        if not condition: return True
        row = base_row or {}
        def loc(value: Any) -> str:
            import re
            return re.sub(r"[^A-Z0-9]+", " ", self.d.norm_text(value)).strip()
        city, state = loc(row.get("destino_cidade", "")), self.d.norm_text(row.get("destino_uf", ""))
        import re
        for raw_clause in re.split(r"[;|]", condition):
            clause = raw_clause.strip()
            if not clause: continue
            if clause.startswith("DESTINO!="):
                if city == loc(clause.split("!=", 1)[1].split("/", 1)[0]): return False
            elif clause.startswith("DESTINO="):
                wanted = clause.split("=", 1)[1].strip().split("/", 1)
                if loc(wanted[0]) != city: return False
                if len(wanted) > 1 and self.d.norm_text(wanted[1]) != state: return False
            elif clause.startswith("UF=") and self.d.norm_text(clause.split("=", 1)[1]) != state:
                return False
        return True

    def choose_extra_rule(self, partner_id: str, charge_type: str, tables: Mapping[str, Any] | None, base_row: Mapping[str, Any] | None = None) -> Mapping[str, Any] | None:
        if not partner_id or not tables or charge_type == "NORMAL": return None
        inheritance = {"MILAYDE_LOBATO": "FENIX", "EUNUQUES_LOPES": "EM", "MB_SERVICOS_LOG": "MB_AMAZONIA"}
        accepted = [partner_id] + ([inheritance[partner_id]] if partner_id in inheritance else [])
        candidates = []
        for extra in tables.get("extras", []) or []:
            owner = extra.get("partner_id")
            if owner not in accepted or not self.extra_matches_charge_type(extra, charge_type) or not self._extra_condition_matches(extra, base_row): continue
            score = 20 if owner == partner_id else 10
            score += 4 if extra.get("condicao") else 0
            score += 2 if extra.get("percent") else 0
            score += 2 if extra.get("valor_fixo") else 0
            score += 1 if extra.get("minimum") else 0
            selected = dict(extra)
            if owner != partner_id:
                selected.update({"inherited_from": owner, "partner_id_original": owner, "partner_id": partner_id})
            candidates.append((score, selected))
        if not candidates: return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def calculate_extra_expected(base_freight: float, extra_rule: Mapping[str, Any]) -> float:
        percent = extra_rule.get("percent", 0.0) or 0.0
        fixed = extra_rule.get("valor_fixo", 0.0) or 0.0
        minimum = extra_rule.get("minimum", 0.0) or 0.0
        values: list[float] = []
        if percent > 0:
            values.append(base_freight * percent)
        if fixed > 0:
            values.append(fixed)
        expected = max(values) if values else 0.0
        if minimum > expected:
            expected = minimum
        return expected

    def get_nfs_from_info(self, info: Mapping[str, Any]) -> list[str]:
        invoices: list[str] = []
        seen: set[str] = set()
        for document in info.get("docs", []) or []:
            invoice = self.d.normalize_nf(document.get("n_doc", ""))
            if invoice and invoice not in seen:
                seen.add(invoice)
                invoices.append(invoice)
        return invoices

    def get_nf_from_info(self, info: Mapping[str, Any]) -> str:
        invoices = self.get_nfs_from_info(info)
        return invoices[0] if invoices else ""

    def is_generic_destination(self, name: Any) -> bool:
        normalized = self.d.norm_text(name)
        terms = ["INTERIOR", "INTERIORES", "REGIAO", "REGIÃO", "POLO", "OUTROS", "DIVERSOS", "CLIENTE"]
        return any(term in normalized for term in terms)

    def rule_matches_location(self, rule: Mapping[str, Any], base_row: Mapping[str, Any] | None) -> int | None:
        destination_city = base_row.get("destino_cidade", "") if base_row else ""
        destination_state = base_row.get("destino_uf", "") if base_row else ""
        origin_city = base_row.get("origem_cidade", "") if base_row else ""
        origin_state = base_row.get("origem_uf", "") if base_row else ""
        score = 0
        if rule.get("destino_cidade"):
            if rule["destino_cidade"] == destination_city:
                score += 60
            elif self.is_generic_destination(rule["destino_cidade"]) and (
                not rule.get("destino_uf") or rule.get("destino_uf") == destination_state
            ):
                score += 12
            else:
                return None
        if rule.get("destino_uf"):
            if rule["destino_uf"] == destination_state:
                score += 18
            else:
                return None
        if rule.get("origem_cidade"):
            if rule["origem_cidade"] == origin_city:
                score += 25
            else:
                return None
        if rule.get("origem_uf"):
            if rule["origem_uf"] == origin_state:
                score += 10
            else:
                return None
        if rule.get("regiao"):
            score += 2
        if rule.get("percent"):
            score += 1
        return score

    def rule_matches_weight(self, rule: Mapping[str, Any], base_row: Mapping[str, Any] | None) -> bool:
        lower = float(rule.get("peso_min_kg", 0.0) or 0.0)
        upper = float(rule.get("peso_max_kg", 0.0) or 0.0)
        if lower <= 0 and upper <= 0:
            return True
        if not base_row:
            return False
        weight = float(base_row.get("peso_regra_kg", 0.0) or base_row.get("peso_kg", 0.0) or 0.0)
        if weight <= 0:
            return False
        if lower > 0:
            if rule.get("peso_min_inclusivo", True):
                if weight < lower:
                    return False
            elif weight <= lower:
                return False
        if upper > 0:
            if rule.get("peso_max_inclusivo", True):
                if weight > upper:
                    return False
            elif weight >= upper:
                return False
        return True

    def choose_partner_rule(
        self,
        partner_id: str,
        base_row: Mapping[str, Any] | None,
        tables: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if not partner_id or not tables or not base_row:
            return None
        rules = [rule for rule in tables.get("rules", []) if rule.get("partner_id") == partner_id]
        scored: list[tuple[float, Mapping[str, Any]]] = []
        for rule in rules:
            if not self.rule_matches_weight(rule, base_row):
                continue
            score = self.rule_matches_location(rule, base_row)
            if score is not None:
                scored.append((score, rule))

        destination_city = base_row.get("destino_cidade", "")
        destination_state = base_row.get("destino_uf", "")
        origin_city = base_row.get("origem_cidade", "")
        origin_state = base_row.get("origem_uf", "")
        matching_regions = []
        for region in tables.get("regions", []):
            if region.get("partner_id") != partner_id:
                continue
            if region.get("cidade") and region.get("cidade") != destination_city:
                continue
            if region.get("uf") and region.get("uf") != destination_state:
                continue
            if not self.rule_matches_weight(region, base_row):
                continue
            matching_regions.append(region)

        for region in matching_regions:
            region_name = region.get("regiao", "")
            for rule in rules:
                if region_name and rule.get("regiao") == region_name and self.rule_matches_weight(rule, base_row):
                    scored.append((45, rule))
            if region.get("percent") or region.get("minimum"):
                score = 80 if region.get("cidade") == destination_city and region.get("uf") == destination_state else 60
                scored.append((score, {
                    "partner_id": partner_id,
                    "origem_cidade": origin_city,
                    "origem_uf": origin_state,
                    "destino_cidade": destination_city,
                    "destino_uf": destination_state,
                    "regiao": region_name,
                    "percent": region.get("percent", 0.0),
                    "minimum": region.get("minimum", 0.0),
                    "ton_rate": region.get("ton_rate", 0.0),
                    "modo_calculo": region.get("modo_calculo", ""),
                    "base_calculo": self.normalize_base_calculo(region.get("base_calculo", "ORIGINAL")),
                    "inclui_complementar": "NAO",
                    "status_revisao": region.get("status_revisao", ""),
                    "gris_ativo": region.get("gris_ativo", False),
                    "percentual_gris": region.get("percentual_gris", 0.0) or region.get("gris_percentual", 0.0),
                    "pedagio_ativo": region.get("pedagio_ativo", False),
                    "valor_pedagio": region.get("valor_pedagio", 0.0) or region.get("pedagio_valor", 0.0),
                    "fracao_pedagio_kg": region.get("fracao_pedagio_kg", 0.0) or region.get("pedagio_fracao_kg", 0.0),
                    "tipo_pedagio": region.get("tipo_pedagio", ""),
                    "raw": region.get("raw", {}),
                    "tipo_trecho": region.get("tipo_trecho", ""),
                    "peso_min_kg": region.get("peso_min_kg", 0.0),
                    "peso_max_kg": region.get("peso_max_kg", 0.0),
                    "peso_min_inclusivo": region.get("peso_min_inclusivo", True),
                    "peso_max_inclusivo": region.get("peso_max_inclusivo", True),
                    "source": "REGIOES",
                }))

        policy = self.d.partner_policy(partner_id)
        if (
            not scored
            and policy.get("fallback_regional_interior_ap")
            and destination_state == "AP"
            and destination_city not in {"MACAPA", "SANTANA"}
        ):
            templates: list[Mapping[str, Any]] = []
            for rule in rules:
                if (
                    "MB INTERIORES" in self.d.norm_text(rule.get("regiao", ""))
                    and (rule.get("percent") or rule.get("minimum"))
                    and self.rule_matches_weight(rule, base_row)
                ):
                    templates.append(rule)
            for region in tables.get("regions", []):
                if region.get("partner_id") != partner_id:
                    continue
                if "MB INTERIORES" not in self.d.norm_text(region.get("regiao", "")):
                    continue
                if not (region.get("percent") or region.get("minimum")):
                    continue
                if not self.rule_matches_weight(region, base_row):
                    continue
                templates.append({
                    "partner_id": partner_id,
                    "origem_cidade": origin_city,
                    "origem_uf": origin_state,
                    "destino_cidade": destination_city,
                    "destino_uf": destination_state,
                    "regiao": region.get("regiao", "MB INTERIORES-AP"),
                    "percent": region.get("percent", 0.0),
                    "minimum": region.get("minimum", 0.0),
                    "ton_rate": region.get("ton_rate", 0.0),
                    "modo_calculo": region.get("modo_calculo", ""),
                    "base_calculo": self.normalize_base_calculo(region.get("base_calculo", "ORIGINAL")),
                    "inclui_complementar": "NAO",
                    "status_revisao": region.get("status_revisao", ""),
                    "gris_ativo": region.get("gris_ativo", False),
                    "percentual_gris": region.get("percentual_gris", 0.0) or region.get("gris_percentual", 0.0),
                    "pedagio_ativo": region.get("pedagio_ativo", False),
                    "valor_pedagio": region.get("valor_pedagio", 0.0) or region.get("pedagio_valor", 0.0),
                    "fracao_pedagio_kg": region.get("fracao_pedagio_kg", 0.0) or region.get("pedagio_fracao_kg", 0.0),
                    "tipo_pedagio": region.get("tipo_pedagio", ""),
                    "raw": region.get("raw", {}),
                    "tipo_trecho": region.get("tipo_trecho", ""),
                    "peso_min_kg": region.get("peso_min_kg", 0.0),
                    "peso_max_kg": region.get("peso_max_kg", 0.0),
                    "peso_min_inclusivo": region.get("peso_min_inclusivo", True),
                    "peso_max_inclusivo": region.get("peso_max_inclusivo", True),
                    "source": "REGIOES_FALLBACK_INTERIOR_AP",
                })
            if templates:
                template = dict(templates[0])
                template.update({
                    "origem_cidade": origin_city,
                    "origem_uf": origin_state,
                    "destino_cidade": destination_city,
                    "destino_uf": destination_state,
                    "source": "REGIOES_FALLBACK_INTERIOR_AP",
                })
                scored.append((55, template))

        if not scored:
            return None
        scored.sort(
            key=lambda item: (
                item[0],
                1 if (item[1].get("peso_min_kg") or item[1].get("peso_max_kg")) else 0,
                -float(item[1].get("peso_min_kg", 0.0) or 0.0),
                item[1].get("percent", 0),
                item[1].get("minimum", 0),
            ),
            reverse=True,
        )
        return scored[0][1]

    def special_weight_city_match(self, rule_city: Any, destination_city: Any) -> int | None:
        rule_normalized = self.d.norm_text(rule_city)
        destination_normalized = self.d.norm_text(destination_city)
        if not rule_normalized:
            return 10
        if rule_normalized == destination_normalized:
            return 100
        if rule_normalized in {"DIVERSOS", "DEMAIS", "DEMAIS CIDADES", "DEMAIS CIDADES TO", "INTERIOR", "INTERIORES"}:
            return 50
        if rule_normalized and destination_normalized and (
            rule_normalized in destination_normalized or destination_normalized in rule_normalized
        ):
            return 70
        return None

    def choose_weight_special_rule(
        self,
        partner_id: str,
        base_row: Mapping[str, Any] | None,
        tables: Mapping[str, Any] | None,
        weight_kg: float,
    ) -> Mapping[str, Any] | None:
        if not partner_id or not base_row or not tables or not weight_kg:
            return None
        destination_city = self.d.norm_text(base_row.get("destino_cidade", ""))
        destination_state = self.d.norm_text(base_row.get("destino_uf", ""))
        origin_city = self.d.norm_text(base_row.get("origem_cidade", ""))
        origin_state = self.d.norm_text(base_row.get("origem_uf", ""))
        scored: list[tuple[float, Mapping[str, Any]]] = []
        for rule in tables.get("peso_especial", []) or []:
            if rule.get("partner_id") != partner_id:
                continue
            limit = rule.get("peso_min_kg", 0.0) or 0.0
            if limit and weight_kg <= limit:
                continue
            rule_state = self.d.norm_text(rule.get("destino_uf", ""))
            if rule_state and rule_state != destination_state:
                continue
            city_score = self.special_weight_city_match(rule.get("destino_cidade", ""), destination_city)
            if city_score is None:
                continue
            score = city_score + (20 if rule_state and rule_state == destination_state else 0) + (limit / 100000.0)
            scored.append((score, rule))
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1].get("percent", 0.0)), reverse=True)
        selected = dict(scored[0][1])
        selected.update({
            "origem_cidade": origin_city,
            "origem_uf": origin_state,
            "destino_cidade": destination_city,
            "destino_uf": destination_state,
            "ton_rate": 0.0,
            "inclui_complementar": "NAO",
        })
        return selected

    def normalize_base_calculo(self, value: Any) -> str:
        text = self.d.norm_text(value or "ORIGINAL")
        if not text: return "ORIGINAL"
        text = text.replace("-", " ").replace("_", " ")
        if ("SEM" in text and "ICMS" in text) or ("FRETE" in text and "SEMICMS" in text): return "SEM_ICMS"
        if "MERCADORIA" in text or "VALOR CARGA" in text or "VALOR DA CARGA" in text: return "MERCADORIA"
        if "ORIGEM" in text: return "ORIGEM"
        return "ORIGINAL"

    def base_value_for_rule(self, row: Mapping[str, Any], base_calculo: Any) -> tuple[float, str]:
        calculation = self.normalize_base_calculo(base_calculo)
        if calculation == "SEM_ICMS":
            value = row.get("valor_frete_sem_icms", 0.0) or 0.0
            return (value, "SEM_ICMS") if value > 0 else (row.get("valor_frete", 0.0) or 0.0, "SEM_ICMS_INDISPONIVEL_USOU_ORIGINAL")
        if calculation == "MERCADORIA":
            value = row.get("valor_mercadoria", 0.0) or 0.0
            return (value, "MERCADORIA") if value > 0 else (0.0, "MERCADORIA_INDISPONIVEL")
        if calculation == "ORIGEM":
            value = row.get("valor_frete_origem", 0.0) or 0.0
            return (value, "ORIGEM") if value > 0 else (row.get("valor_frete", 0.0) or 0.0, "ORIGEM_INDISPONIVEL_USOU_ORIGINAL")
        value = row.get("valor_frete_planilha", 0.0) or 0.0
        return (value, "ORIGINAL") if value > 0 else (row.get("valor_frete", 0.0) or 0.0, "ORIGINAL_FALLBACK_LEGADO")

    def sum_base_for_rule(self, rows: Sequence[Mapping[str, Any]], base_calculo: Any) -> tuple[float, list[str]]:
        total = 0.0
        sources: list[str] = []
        for row in rows:
            value, source = self.base_value_for_rule(row, base_calculo)
            total += value
            if source not in sources:
                sources.append(source)
        return total, sources

    def component_value(self, info: Mapping[str, Any], *name_parts: Any) -> tuple[float, list[tuple[Any, float]]]:
        wanted = [self.d.norm_text(part) for part in name_parts if str(part or "").strip()]
        total = 0.0
        found: list[tuple[Any, float]] = []
        for component in info.get("componentes", []) or []:
            name = self.d.norm_text(component.get("nome", ""))
            if wanted and not any(part in name for part in wanted):
                continue
            value = self.d.parse_number_br(component.get("valor", ""))
            total += value
            found.append((component.get("nome", ""), value))
        return total, found

    def total_components_value(self, info: Mapping[str, Any]) -> float:
        return sum(self.d.parse_number_br(component.get("valor", "")) for component in info.get("componentes", []) or [])

    def non_frete_peso_components_value(self, info: Mapping[str, Any]) -> tuple[float, list[tuple[Any, float]]]:
        total = 0.0
        found: list[tuple[Any, float]] = []
        for component in info.get("componentes", []) or []:
            normalized_name = self.d.norm_text(component.get("nome", ""))
            value = self.d.parse_number_br(component.get("valor", ""))
            if "FRETE" in normalized_name and "PESO" in normalized_name:
                continue
            total += value
            if value:
                found.append((component.get("nome", ""), value))
        return total, found

    def peso_base_kg_from_info(self, info: Mapping[str, Any]) -> tuple[float, str]:
        for key in ("peso_base", "peso_aferido", "peso_bruto"):
            value = self.d.parse_number_br(info.get(key, ""))
            if value > 0:
                return value, key
        return 0.0, ""

    def should_use_frete_peso(self, rule: Mapping[str, Any], info: Mapping[str, Any]) -> bool:
        ton_rate = rule.get("ton_rate", 0.0) or 0.0
        mode = self.d.norm_text(rule.get("modo_calculo", ""))
        freight_weight_xml, _ = self.component_value(info, "FRETE PESO")
        if "FRETE" in mode and "PESO" in mode:
            return True
        if ("PESO" in mode or "TON" in mode or "KG" in mode) and ton_rate > 0:
            return True
        return ton_rate > 0 and freight_weight_xml > 0

    def component_values_by_keywords(self, info: Mapping[str, Any], keywords: Sequence[Any]) -> tuple[float, list[tuple[Any, float]]]:
        total = 0.0
        found: list[tuple[Any, float]] = []
        normalized_keywords = [self.d.norm_text(keyword) for keyword in keywords if str(keyword or "").strip()]
        for component in info.get("componentes", []) or []:
            name = self.d.norm_text(component.get("nome", ""))
            if all(keyword in name for keyword in normalized_keywords):
                value = self.d.parse_number_br(component.get("valor", ""))
                total += value
                found.append((component.get("nome", ""), value))
        return total, found

    def comparison_value_from_xml(self, info: Mapping[str, Any], mode: str = "FRETE_VALOR") -> tuple[Any, ...]:
        normalized_mode = self.d.norm_text(mode)
        total_xml = self.d.parse_number_br(info.get("valor", ""))
        if "PESO" in normalized_mode:
            value, found = self.component_values_by_keywords(info, ["FRETE", "PESO"])
            if found:
                return value, "FRETE PESO", False, found, total_xml
            return total_xml, "VALOR TOTAL DO SERVIÇO (fallback)", True, [], total_xml
        value, found = self.component_values_by_keywords(info, ["FRETE", "VALOR"])
        if found:
            return value, "FRETE VALOR", False, found, total_xml
        value, found = self.component_values_by_keywords(info, ["FRETE", "PESO"])
        if found:
            return value, "FRETE PESO (fallback)", False, found, total_xml
        return total_xml, "VALOR TOTAL DO SERVIÇO (fallback)", True, [], total_xml
