from __future__ import annotations

"""Pós-processador modular do controle compacto exibido no DACTE.

Este serviço preserva o contrato visual/passivo consolidado na versão 2.6.47
sem substituir ``validate_cte_value`` ou ``render_dacte_page`` em runtime.
"""

import math
import re
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable

from ..infrastructure.normalization import normalize_header
from ..repositories.component_configuration import ComponentConfigurationService
from ..repositories.value_parsers import parse_percent

COMPACT_CONTROL_SERVICE_VERSION = "2.7.0-RC24"


@dataclass(frozen=True)
class CompactControlDependencies:
    norm_text: Callable[[Any], str]
    parse_number_br: Callable[[Any], float]
    get_nfs_from_info: Callable[[Mapping[str, Any]], Sequence[str]]
    find_base_by_nf: Callable[..., Any]
    identify_partner: Callable[[Mapping[str, Any], Mapping[str, Any] | None], str | None]
    base_rows_have_same_route: Callable[[Sequence[Mapping[str, Any]]], bool]
    choose_partner_rule: Callable[..., Mapping[str, Any] | None]
    rule_matches_location: Callable[..., Any]
    sum_base_for_rule: Callable[..., Any]
    peso_base_kg_from_info: Callable[[Mapping[str, Any]], tuple[float, str]]
    money: Callable[[Any], str]


class CompactControlService:
    """Monta as linhas compactas sem alterar a decisão comercial principal."""

    compact_keys = (
        "controle_dacte_regra",
        "controle_dacte_linha1",
        "controle_dacte_linha2",
        "controle_dacte_status",
        "controle_dacte_compacto",
    )

    def __init__(
        self,
        dependencies: CompactControlDependencies,
        configuration: ComponentConfigurationService | None = None,
    ) -> None:
        self.d = dependencies
        self.configuration = configuration or ComponentConfigurationService()

    @staticmethod
    def _digits(value: Any) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    def _round(value: Any) -> float:
        try:
            return round(float(value or 0.0) + 1e-9, 2)
        except Exception:
            return 0.0

    def _money(self, value: Any) -> str:
        try:
            return self.d.money(value)
        except Exception:
            return f"{float(value or 0):.2f}".replace(".", ",")

    def _money_rs(self, value: Any) -> str:
        return "R$" + self._money(value)

    @staticmethod
    def _num(value: Any) -> str:
        try:
            number = float(value)
        except Exception:
            return str(value)
        if abs(number - int(number)) < 0.0001:
            return str(int(number))
        return (f"{number:.3f}".rstrip("0").rstrip(".")).replace(".", ",")

    @staticmethod
    def _weight(value: Any) -> str:
        try:
            number = float(value or 0.0)
        except Exception:
            number = 0.0
        places = 0 if abs(number - round(number)) < 0.0001 else 3
        text = f"{number:,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return text.rstrip("0").rstrip(",") if "," in text else text

    def _base_description(self, value: Any) -> str:
        text = self.d.norm_text(value or "")
        if "SEM ICMS" in text or "SEM_ICMS" in str(value or "").upper():
            return "base sem ICMS"
        if "ORIGINAL" in text or "BRUTO" in text:
            return "base original"
        return "base usada"

    @staticmethod
    def _percent(value: Any) -> str:
        try:
            number = float(value or 0.0) * 100.0
        except Exception:
            number = 0.0
        if abs(number - int(number)) < 0.0001:
            return f"{int(number)}%"
        return (f"{number:.4f}".rstrip("0").rstrip(".")).replace(".", ",") + "%"

    @staticmethod
    def _first_raw(raw: Mapping[str, Any] | None, *names: str) -> Any:
        source = raw or {}
        for name in names:
            key = normalize_header(name)
            if key in source and str(source.get(key) or "").strip() != "":
                return source.get(key)
            if name in source and str(source.get(name) or "").strip() != "":
                return source.get(name)
        return ""

    def _yes(self, value: Any) -> bool:
        return self.d.norm_text(value) in {"S", "SIM", "YES", "Y", "TRUE", "1", "ATIVO", "OK"}

    def _toll_type(self, *values: Any) -> str:
        text = self.d.norm_text(" ".join(str(value or "") for value in values))
        if not text:
            return ""
        if any(token in text for token in ("CTE", "CT E", "CT-E", "CTRC", "CONHECIMENTO", "EMISSAO")):
            return "CTE"
        if any(token in text for token in ("100", "KG", "PESO", "FRACAO", "TON")):
            return "KG"
        return ""

    def _component_value(
        self,
        info: Mapping[str, Any],
        keywords: Sequence[str],
        exclude: Sequence[str] = (),
    ) -> tuple[float, list[tuple[Any, float]]]:
        total = 0.0
        found: list[tuple[Any, float]] = []
        normalized_keywords = [self.d.norm_text(item) for item in keywords if str(item or "").strip()]
        normalized_exclusions = [self.d.norm_text(item) for item in exclude if str(item or "").strip()]
        for component in info.get("componentes", []) or []:
            name = self.d.norm_text(component.get("nome", ""))
            if normalized_keywords and not any(token in name for token in normalized_keywords):
                continue
            if normalized_exclusions and any(token in name for token in normalized_exclusions):
                continue
            value = self.d.parse_number_br(component.get("valor", ""))
            total += value
            found.append((component.get("nome", ""), value))
        return total, found

    def _freight_component(self, info: Mapping[str, Any]) -> tuple[float, list[tuple[Any, float]], str]:
        for keywords, label in ((["FRETE PESO"], "FRETE PESO"), (["FRETE VALOR"], "FRETE VALOR")):
            value, found = self._component_value(info, keywords)
            if found and abs(self._round(value)) > 0:
                return value, found, label
        value, found = self._component_value(
            info,
            ["FRETE"],
            exclude=["GRIS", "RISCO", "PEDAG", "PEDÁG", "ICMS", "TAXA"],
        )
        if found and abs(self._round(value)) > 0:
            return value, found, "FRETE"
        return 0.0, [], "FRETE"

    def _status_short(self, result: Mapping[str, Any]) -> str:
        status = self.d.norm_text(result.get("status") or "")
        if "OK" in status and "DIVERG" not in status and "REGRA" not in status and "NAO" not in status:
            return "OK"
        if "DIVERG" in status:
            return "DIVERGENTE"
        if any(token in status for token in ("PEND", "REVIS", "AMBIG", "MULT")):
            return "REVISAR"
        return str(result.get("status") or "PENDENTE")

    def _calculation_type_from_result(
        self,
        result: Mapping[str, Any],
        configured_type: Any,
        freight_label: str,
    ) -> str:
        """Resolve o modo visual a partir da decisão comercial já concluída.

        A tabela pode possuir simultaneamente percentual, tarifa por tonelada e
        mínimo. O bloco compacto não deve escolher novamente a regra apenas pela
        presença de ``ton_rate``. O componente efetivamente comparado e o modo
        publicado pelo validador são a fonte de verdade.
        """

        component = self.d.norm_text(result.get("componente_comparado") or freight_label or "")
        mode = self.d.norm_text(result.get("modo_calculo") or "")

        if "HIBRIDO" in mode or ("PERCENT" in mode and "FRETE PESO" in mode):
            return "HIBRIDO"
        if "FRETE PESO" in component or any(
            token in mode for token in ("FRETE PESO", "KG TON", "KG_TON")
        ):
            return "KG_TON"
        if "FRETE VALOR" in component:
            return "PERCENTUAL"
        if any(token in mode for token in ("PERCENT", "FRETE VALOR")):
            return "PERCENTUAL"
        if any(token in mode for token in ("FIXO", "MINIMO", "MÍNIMO")):
            return "FIXO_MINIMO"
        return str(configured_type or "SEM_BLOCO")

    def _valid_base_rows(
        self,
        info: Mapping[str, Any],
        base_data: Mapping[str, Any],
        ignored_nfs: Sequence[Any] | None,
    ) -> list[Mapping[str, Any]]:
        ignored = {self._digits(nf).lstrip("0") or "0" for nf in (ignored_nfs or [])}
        rows: list[Mapping[str, Any]] = []
        for invoice in self.d.get_nfs_from_info(info):
            key = self._digits(invoice).lstrip("0") or "0"
            if key in ignored:
                continue
            try:
                base_row, _base_status, _candidates = self.d.find_base_by_nf(base_data, invoice, info)
            except Exception:
                continue
            if base_row:
                rows.append(base_row)
        return rows

    def _find_related_rule(
        self,
        partner_id: str,
        base_row: Mapping[str, Any],
        tables: Mapping[str, Any],
        current_rule: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        candidates: list[tuple[Any, Mapping[str, Any]]] = []
        current_region = current_rule.get("regiao", "")
        for rule in tables.get("rules", []) or []:
            if rule.get("partner_id") != partner_id:
                continue
            try:
                score = self.d.rule_matches_location(rule, base_row)
            except Exception:
                score = None
            if score is not None:
                candidates.append((score + 20, rule))
            elif current_region and rule.get("regiao") == current_region:
                candidates.append((30, rule))
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (item[0], item[1].get("percent", 0), item[1].get("minimum", 0)),
            reverse=True,
        )
        return candidates[0][1]

    def _extra_configuration(self, partner_id: str, tables: Mapping[str, Any]) -> dict[str, Any]:
        config = {
            "gris_ativo": False,
            "gris_percentual": 0.0,
            "pedagio_ativo": False,
            "pedagio_valor": 0.0,
            "pedagio_tipo": "",
            "pedagio_fracao_kg": 0.0,
        }
        for extra in tables.get("extras", []) or []:
            if extra.get("partner_id") != partner_id:
                continue
            extra_type = self.d.norm_text(extra.get("tipo_extra", ""))
            base = self.d.norm_text(extra.get("base_calculo", ""))
            observation = self.d.norm_text(
                (extra.get("raw") or {}).get("OBSERVACAO", "") or extra.get("observacao", "")
            )
            if "GRIS" in extra_type:
                percentage = extra.get("percent", 0.0) or parse_percent(
                    self._first_raw(extra.get("raw") or {}, "Percentual", "PERCENTUAL")
                )
                if percentage:
                    config["gris_ativo"] = True
                    config["gris_percentual"] = percentage
            if "PEDAG" in extra_type:
                value = extra.get("valor_fixo", 0.0) or self.d.parse_number_br(
                    self._first_raw(extra.get("raw") or {}, "Valor", "VALOR", "Taxa", "TAXA")
                )
                if value:
                    config["pedagio_ativo"] = True
                    config["pedagio_valor"] = value
                    config["pedagio_tipo"] = self._toll_type(base, observation, extra_type) or "CTE"
                    if config["pedagio_tipo"] == "KG":
                        config["pedagio_fracao_kg"] = 100.0
        return config

    def _configuration(
        self,
        rule: Mapping[str, Any],
        partner_id: str,
        base_row: Mapping[str, Any],
        tables: MutableMapping[str, Any],
    ) -> dict[str, Any]:
        config = dict(rule or {})
        self.configuration.enrich_rule(config)
        raw = config.get("raw") or {}
        related = self._find_related_rule(partner_id, base_row, tables, config)
        related_raw = (related or {}).get("raw") or {}

        calculation_type = (
            self._first_raw(
                raw,
                "Tipo Cálculo Compacto", "Tipo Calculo Compacto",
                "Controle Tipo Cálculo", "Controle Tipo Calculo",
                "Modo Cálculo Compacto", "Modo Calculo Compacto",
            )
            or self._first_raw(
                related_raw,
                "Tipo Cálculo Compacto", "Tipo Calculo Compacto",
                "Controle Tipo Cálculo", "Controle Tipo Calculo",
                "Modo Cálculo Compacto", "Modo Calculo Compacto",
            )
        )
        normalized_type = self.d.norm_text(calculation_type)
        ton_rate = config.get("ton_rate", 0.0) or self.d.parse_number_br(
            self._first_raw(
                raw,
                "Tonelagem Mínima (R$/Ton)", "TONELAGEMMINIMARTON",
                "Tonelagem", "R$/Ton", "Valor Ton",
            )
        )
        if not normalized_type:
            if ton_rate:
                normalized_type = "KG_TON"
            elif config.get("percent", 0.0) or config.get("minimum", 0.0):
                normalized_type = "PERCENTUAL"
            else:
                normalized_type = "SEM_BLOCO"
        if "SEM" in normalized_type and "BLOCO" in normalized_type:
            normalized_type = "SEM_BLOCO"
        elif "KG" in normalized_type or "TON" in normalized_type:
            normalized_type = "KG_TON"
        elif "FIXO" in normalized_type or "MINIMO" in normalized_type:
            normalized_type = "FIXO_MINIMO"
        elif "PERCENT" in normalized_type or "%" in normalized_type:
            normalized_type = "PERCENTUAL"

        extras = self._extra_configuration(partner_id, tables)
        if not config.get("gris_ativo") and extras.get("gris_ativo"):
            config["gris_ativo"] = True
            config["gris_percentual"] = extras.get("gris_percentual", 0.0)
        if not config.get("gris_percentual") and extras.get("gris_percentual"):
            config["gris_percentual"] = extras.get("gris_percentual", 0.0)

        toll_type_raw = (
            self._first_raw(raw, "Tipo Pedágio", "Tipo Pedagio", "PEDAGIO TIPO", "TIPOPEDAGIO")
            or self._first_raw(related_raw, "Tipo Pedágio", "Tipo Pedagio", "PEDAGIO TIPO", "TIPOPEDAGIO")
        )
        toll_value_raw = (
            self._first_raw(raw, "Valor Pedágio", "Valor Pedagio", "Pedágio Valor", "Pedagio Valor")
            or self._first_raw(related_raw, "Valor Pedágio", "Valor Pedagio", "Pedágio Valor", "Pedagio Valor")
        )
        toll_fraction_raw = (
            self._first_raw(
                raw,
                "Fração Pedágio KG", "Fracao Pedagio KG", "Fração KG", "Fracao KG",
                "Pedágio Fração KG", "Pedagio Fracao KG",
            )
            or self._first_raw(
                related_raw,
                "Fração Pedágio KG", "Fracao Pedagio KG", "Fração KG", "Fracao KG",
                "Pedágio Fração KG", "Pedagio Fracao KG",
            )
        )
        old_toll = self._first_raw(raw, "Pedágio", "Pedagio", "PEDAGIO") or self._first_raw(
            related_raw, "Pedágio", "Pedagio", "PEDAGIO"
        )
        toll_value = (
            config.get("pedagio_valor", 0.0)
            or self.d.parse_number_br(toll_value_raw)
            or self.d.parse_number_br(old_toll)
            or extras.get("pedagio_valor", 0.0)
        )
        toll_type = self._toll_type(
            toll_type_raw,
            old_toll,
            self._first_raw(raw, "Base Cálculo", "Base Calculo"),
            self._first_raw(related_raw, "Base Cálculo", "Base Calculo"),
        ) or extras.get("pedagio_tipo", "")
        toll_fraction = (
            config.get("pedagio_fracao_kg", 0.0)
            or self.d.parse_number_br(toll_fraction_raw)
            or extras.get("pedagio_fracao_kg", 0.0)
        )
        if toll_value and toll_value > 0:
            config["pedagio_ativo"] = True
            config["pedagio_valor"] = toll_value
        if toll_type:
            config["pedagio_tipo"] = toll_type
        elif config.get("pedagio_ativo"):
            config["pedagio_tipo"] = "KG" if toll_fraction else "CTE"
        config["pedagio_fracao_kg"] = (toll_fraction or 100.0) if config.get("pedagio_tipo") == "KG" else (toll_fraction or 0.0)

        config["ton_rate"] = ton_rate
        config["controle_tipo_calculo"] = normalized_type
        config["controle_dacte"] = bool(config.get("controle_dacte")) or normalized_type in {"KG_TON", "PERCENTUAL"}
        if not config.get("controle_regra_nome"):
            config["controle_regra_nome"] = partner_id or "CONTROLE"
        return config

    def clear(self, result: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        for key in self.compact_keys:
            result.pop(key, None)
        return result

    def apply(
        self,
        result: MutableMapping[str, Any],
        info: Mapping[str, Any],
        base_data: Mapping[str, Any] | None,
        tables: MutableMapping[str, Any] | None,
    ) -> MutableMapping[str, Any]:
        if not isinstance(result, MutableMapping) or not isinstance(info, Mapping) or info.get("tipo") != "CT-e":
            return result
        self.clear(result)
        partner_id = result.get("partner_id") or self.d.identify_partner(info, tables)
        if not partner_id or not tables:
            return result
        if not base_data:
            result.setdefault("trace", []).append("Controle compacto modular não aplicado: base ausente.")
            return result

        base_rows = self._valid_base_rows(info, base_data, result.get("nfs_ignoradas"))
        if not base_rows:
            result.setdefault("trace", []).append("Controle compacto modular não aplicado: NF/base não localizada.")
            return result
        if len(base_rows) > 1 and not self.d.base_rows_have_same_route(base_rows):
            result.setdefault("trace", []).append("Controle compacto modular não aplicado: múltiplas rotas na base.")
            return result

        base_row = base_rows[0]
        weight_kg, _weight_source = self.d.peso_base_kg_from_info(info)
        rule_base_row = dict(base_row)
        rule_base_row["peso_regra_kg"] = weight_kg
        rule = self.d.choose_partner_rule(partner_id, rule_base_row, tables)
        if not rule:
            result.setdefault("trace", []).append("Controle compacto modular não aplicado: regra do parceiro não encontrada.")
            return result
        config = self._configuration(rule, str(partner_id), base_row, tables)
        if not config.get("controle_dacte"):
            return result

        total_xml = self.d.parse_number_br(info.get("valor", ""))
        tolerance = tables.get("tolerance", 1.0)
        parts: list[str] = []
        component_reference_total = 0.0
        merchandise_value = self.d.parse_number_br(info.get("valor_carga", ""))
        if merchandise_value <= 0:
            try:
                merchandise_value = sum(float(row.get("valor_mercadoria", 0.0) or 0.0) for row in base_rows)
            except Exception:
                merchandise_value = 0.0

        freight_xml, freight_found, freight_label = self._freight_component(info)
        freight_xml = self._round(freight_xml)
        calculation_type = self._calculation_type_from_result(
            result, config.get("controle_tipo_calculo", "SEM_BLOCO"), freight_label
        )
        compared_value = result.get("valor_comparado")
        compared_component = self.d.norm_text(result.get("componente_comparado") or "")
        if (
            calculation_type == "PERCENTUAL"
            and "FRETE VALOR" in compared_component
            and compared_value is not None
        ):
            freight_xml = self._round(compared_value)
            freight_found = [("FRETE VALOR", freight_xml)]
            freight_label = "FRETE VALOR"
        gris_probe, _ = self._component_value(info, ["GRIS", "GERENCIAMENTO RISCO", "RISCO"])
        toll_probe, _ = self._component_value(info, ["PEDAG", "PEDÁGIO", "PEDAGIO"])
        if not freight_found and total_xml:
            estimated = self._round(total_xml - self._round(gris_probe) - self._round(toll_probe))
            if estimated > 0:
                freight_xml = estimated
                freight_found = [("FRETE ESTIMADO", estimated)]
                freight_label = "FRETE"

        freight_reference: float | None = None
        if calculation_type == "HIBRIDO":
            ton_rate = config.get("ton_rate", 0.0) or 0.0
            rate_kg = ton_rate / 1000.0 if ton_rate else 0.0
            minimum = config.get("minimum", 0.0) or 0.0
            percentage = float(result.get("percentual") or config.get("percent", 0.0) or 0.0)
            calculation_base = float(result.get("base_frete") or base_row.get("valor_frete", 0.0) or 0.0)
            percent_ref = self._round(calculation_base * percentage)
            weight_ref = self._round(weight_kg * rate_kg) if weight_kg > 0 and rate_kg > 0 else 0.0
            freight_reference = self._round(max(percent_ref, weight_ref, minimum))
            criterion = str(result.get("criterio_frete_aplicado") or ("PERCENTUAL" if freight_reference == percent_ref else ("FRETE_PESO" if freight_reference == weight_ref else "FRETE_MINIMO")))
            label = (
                f"Frete híbrido: percentual R${self._money(calculation_base)} × {self._percent(percentage)} = R${self._money(percent_ref)} | "
                f"peso {self._weight(weight_kg)} kg × R${self._money(rate_kg)}/kg = R${self._money(weight_ref)} | "
                f"mínimo R${self._money(minimum)} → R${self._money(freight_reference)} ({criterion})"
            )
            if freight_found and abs(self._round(freight_xml - freight_reference)) > tolerance:
                label += f" (XML R${self._money(freight_xml)})"
            component_reference_total += freight_reference
            parts.append(label)
        elif calculation_type == "KG_TON":
            ton_rate = config.get("ton_rate", 0.0) or 0.0
            rate_kg = ton_rate / 1000.0 if ton_rate else 0.0
            minimum = config.get("minimum", 0.0) or 0.0
            if weight_kg > 0 and rate_kg > 0:
                gross = self._round(weight_kg * rate_kg)
                freight_reference = self._round(max(gross, minimum))
                formula = (
                    f"{self._weight(weight_kg)} kg × R${self._money(rate_kg)}/kg = "
                    f"R${self._money(gross)}"
                )
                if minimum and minimum > gross:
                    label = f"Frete peso: {formula} → mínimo R${self._money(freight_reference)}"
                else:
                    label = f"Frete peso: {formula}"
                if freight_found and abs(self._round(freight_xml - freight_reference)) > tolerance:
                    label = label.replace("Frete peso:", "Frete peso ref.:", 1)
                    label += f" (XML R${self._money(freight_xml)})"
                component_reference_total += freight_reference
                parts.append(label)
        elif calculation_type in {"PERCENTUAL", "FIXO_MINIMO"}:
            base_calculation = config.get("base_calculo", "ORIGINAL")
            result_base = result.get("base_frete")
            if result_base is not None:
                calculation_base = float(result_base or 0.0)
            else:
                try:
                    calculation_base, _sources = self.d.sum_base_for_rule(base_rows, base_calculation)
                except Exception:
                    calculation_base = base_row.get("valor_frete", 0.0) or 0.0
            percentage = float(result.get("percentual") or config.get("percent", 0.0) or 0.0)
            minimum = config.get("minimum", 0.0) or 0.0
            published_expected = result.get("esperado")
            label = ""
            if percentage > 0:
                gross = self._round(calculation_base * percentage)
                calculated_reference = self._round(max(gross, minimum))
                freight_reference = (
                    self._round(published_expected)
                    if published_expected is not None and float(published_expected or 0.0) > 0
                    else calculated_reference
                )
                prefix = "Frete valor" if "FRETE VALOR" in compared_component else "Frete"
                base_label = self._base_description(base_calculation)
                formula = f"R${self._money(calculation_base)} × {self._percent(percentage)}"
                if minimum and minimum > gross and abs(freight_reference - minimum) <= tolerance:
                    label = (
                        f"{prefix} ({base_label}): {formula} = R${self._money(gross)} "
                        f"→ mínimo R${self._money(freight_reference)}"
                    )
                elif abs(freight_reference - gross) > 0.01:
                    adjustment = "repasse" if result.get("repasse_embutido_status") else "ajuste"
                    label = (
                        f"{prefix} ({base_label}): {formula} = R${self._money(gross)} "
                        f"→ {adjustment} R${self._money(freight_reference)}"
                    )
                else:
                    label = (
                        f"{prefix} ({base_label}): {formula} = R${self._money(freight_reference)}"
                    )
            elif minimum > 0:
                freight_reference = self._round(
                    published_expected if published_expected is not None else minimum
                )
                label = f"Frete mín.: {self._money(freight_reference)}"
            if label and freight_reference is not None:
                if freight_found and abs(self._round(freight_xml - freight_reference)) > tolerance:
                    label = label.replace("Frete valor (", "Frete valor ref. (", 1)
                    label = label.replace("Frete (", "Frete ref. (", 1)
                    label += f" (XML R${self._money(freight_xml)})"
                component_reference_total += freight_reference
                parts.append(label)
        elif freight_found:
            parts.append(f"{freight_label}: XML {self._money(freight_xml)}")
            component_reference_total += freight_xml

        if not any(str(part).startswith(("Frete", "FRETE")) for part in parts) and freight_found:
            parts.append(f"{freight_label}: XML {self._money(freight_xml)}")
            component_reference_total += freight_xml

        gris_xml, gris_found = self._component_value(info, ["GRIS", "GERENCIAMENTO RISCO", "RISCO"])
        gris_xml = self._round(gris_xml)
        if gris_found and abs(gris_xml) > 0:
            if config.get("gris_ativo") and (config.get("gris_percentual", 0.0) or 0.0) and merchandise_value:
                percentage = config.get("gris_percentual", 0.0) or 0.0
                reference = self._round(merchandise_value * percentage)
                if abs(self._round(gris_xml - reference)) <= tolerance:
                    parts.append(
                        f"GRIS (mercadoria): R${self._money(merchandise_value)} × {self._percent(percentage)} = R${self._money(reference)}"
                    )
                else:
                    parts.append(
                        f"GRIS ref. (mercadoria): R${self._money(merchandise_value)} × {self._percent(percentage)} = "
                        f"R${self._money(reference)} (XML R${self._money(gris_xml)})"
                    )
                component_reference_total += reference
            else:
                parts.append(f"GRIS: XML {self._money(gris_xml)}")
                component_reference_total += gris_xml

        toll_xml, toll_found = self._component_value(info, ["PEDAG", "PEDÁGIO", "PEDAGIO"])
        toll_xml = self._round(toll_xml)
        if toll_found and abs(toll_xml) > 0:
            toll_value = config.get("pedagio_valor", 0.0) or 0.0
            toll_type = config.get("pedagio_tipo", "")
            if config.get("pedagio_ativo") and toll_value > 0:
                if toll_type == "KG":
                    fraction = config.get("pedagio_fracao_kg", 100.0) or 100.0
                    quantity = int(math.ceil(weight_kg / fraction)) if weight_kg > 0 and fraction > 0 else 0
                else:
                    quantity = 1
                reference = self._round(quantity * toll_value)
                if toll_type == "KG":
                    fraction = config.get("pedagio_fracao_kg", 100.0) or 100.0
                    label = (
                        f"Pedágio: {self._weight(weight_kg)} kg ÷ {self._weight(fraction)} kg = "
                        f"{quantity} {'fração' if quantity == 1 else 'frações'} × R${self._money(toll_value)} = R${self._money(reference)}"
                    )
                else:
                    label = f"Pedágio: 1 CT-e × R${self._money(toll_value)} = R${self._money(reference)}"
                if abs(self._round(toll_xml - reference)) > tolerance:
                    label = label.replace("Pedágio:", "Pedágio ref.:", 1) + f" (XML R${self._money(toll_xml)})"
                parts.append(label)
                component_reference_total += reference
            else:
                parts.append(f"Pedágio: XML {self._money(toll_xml)}")
                component_reference_total += toll_xml

        if not parts:
            return result
        component_reference_total = self._round(component_reference_total)
        visual_difference = self._round(total_xml - component_reference_total)
        short_status = self._status_short(result)
        compact_inconsistent = bool(short_status == "OK" and abs(visual_difference) > tolerance)
        if compact_inconsistent:
            short_status = "REVISAR BLOCO"
        rule_name = config.get("controle_regra_nome") or partner_id or "CONTROLE"
        line1 = " | ".join(parts)
        line2 = (
            f"Total comp.: {self._money_rs(component_reference_total)} | XML: {self._money_rs(total_xml)} | "
            f"Dif. comp.: {self._money_rs(visual_difference)} | Validação: {short_status}"
        )
        result.update(
            {
                "controle_dacte_regra": rule_name,
                "controle_dacte_linha1": line1,
                "controle_dacte_linha2": line2,
                "controle_dacte_status": short_status,
                "controle_dacte_compacto": f"CONTROLE INTERNO - {rule_name}\n{line1}\n{line2}",
                "controle_dacte_diferenca": visual_difference,
                "controle_dacte_total_referencia": component_reference_total,
                "controle_dacte_total_xml": total_xml,
                "controle_dacte_versao": COMPACT_CONTROL_SERVICE_VERSION,
                "controle_dacte_origem": "RESULTADO FINAL VALIDADO",
                "controle_dacte_inconsistente": compact_inconsistent,
            }
        )
        result.setdefault("trace", []).append(
            "Controle compacto modular 2.7.0-RC24 aplicado: único, passivo e com diferença calculada pelo valor de referência."
        )
        return result


__all__ = [
    "COMPACT_CONTROL_SERVICE_VERSION",
    "CompactControlDependencies",
    "CompactControlService",
]
