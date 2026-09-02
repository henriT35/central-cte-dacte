from __future__ import annotations

"""Cálculo modular do controle interno de frete-peso, GRIS e pedágio."""

import math
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from collections.abc import MutableMapping
from typing import Any, Callable, Mapping, Sequence

from ..repositories.component_configuration import ComponentConfigurationService

COMPONENT_CALCULATOR_VERSION = "2.7.0-RC24"


@dataclass(frozen=True)
class ComponentCalculationDependencies:
    norm_text: Callable[[Any], str]
    parse_number_br: Callable[[Any], float]
    get_nfs_from_info: Callable[[Mapping[str, Any]], Sequence[str]]
    find_base_by_nf: Callable[..., Any]
    identify_partner: Callable[[Mapping[str, Any], Mapping[str, Any] | None], str | None]
    base_rows_have_same_route: Callable[[Sequence[Mapping[str, Any]]], bool]
    choose_partner_rule: Callable[..., Mapping[str, Any] | None]
    should_use_frete_peso: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]
    peso_base_kg_from_info: Callable[[Mapping[str, Any]], tuple[float, str]]
    format_peso_xml_debug: Callable[[Mapping[str, Any]], str]
    money: Callable[[Any], str]


class ComponentCalculationService:
    """Pós-processa a validação sem monkeypatch e preserva o contrato 2.6.31."""

    def __init__(
        self,
        dependencies: ComponentCalculationDependencies,
        configuration: ComponentConfigurationService | None = None,
    ) -> None:
        self.d = dependencies
        self.configuration = configuration or ComponentConfigurationService()

    @staticmethod
    def _round_money(value: Any) -> float:
        try:
            return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        except Exception:
            return 0.0

    @staticmethod
    def _fmt_num(value: Any, places: int = 2, thousands: bool = False) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0.0
        if abs(number - round(number)) < 1e-7:
            return str(int(round(number)))
        if thousands:
            text = f"{number:,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            text = f"{number:.{places}f}".replace(".", ",")
        return text.rstrip("0").rstrip(",") if "," in text else text

    @staticmethod
    def _fmt_money_plain(value: Any) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0.0
        return f"{number:.2f}".replace(".", ",")

    @classmethod
    def _fmt_money_rs(cls, value: Any) -> str:
        return "R$" + cls._fmt_money_plain(value)

    @staticmethod
    def _fmt_percent_short(value: Any) -> str:
        try:
            number = float(value or 0) * 100.0
        except Exception:
            number = 0.0
        text = f"{number:.4f}".replace(".", ",").rstrip("0").rstrip(",")
        return text + "%"

    def _component_value_any(
        self,
        info: Mapping[str, Any],
        aliases: Sequence[str],
    ) -> tuple[float, list[tuple[Any, float]]]:
        total = 0.0
        found: list[tuple[Any, float]] = []
        normalized_aliases = [self.d.norm_text(alias) for alias in aliases]
        for component in info.get("componentes", []) or []:
            name = self.d.norm_text(component.get("nome", ""))
            if any(alias and alias in name for alias in normalized_aliases):
                value = self.d.parse_number_br(component.get("valor", ""))
                total += value
                found.append((component.get("nome", ""), value))
        return total, found

    def _valid_base_rows(
        self,
        info: Mapping[str, Any],
        base_data: Mapping[str, Any],
        ignored_nfs: Sequence[Any] | None = None,
    ) -> list[Mapping[str, Any]]:
        ignored = {
            (re.sub(r"\D+", "", str(invoice or "")).lstrip("0") or "0")
            for invoice in (ignored_nfs or [])
        }
        rows: list[Mapping[str, Any]] = []
        for invoice in self.d.get_nfs_from_info(info):
            normalized = re.sub(r"\D+", "", str(invoice or "")).lstrip("0") or "0"
            if normalized in ignored:
                continue
            base_row, _base_status, _candidates = self.d.find_base_by_nf(base_data, invoice, info)
            if base_row:
                rows.append(base_row)
        return rows

    def apply(
        self,
        result: MutableMapping[str, Any],
        info: Mapping[str, Any],
        base_data: Mapping[str, Any] | None,
        tables: MutableMapping[str, Any] | None,
    ) -> MutableMapping[str, Any]:
        if not isinstance(result, MutableMapping):
            return result
        partner_id = result.get("partner_id") or self.d.identify_partner(info, tables)
        if not partner_id or not base_data or not tables:
            return result

        # Garante o mesmo contrato quando a guarda de repositório escolhe o
        # carregador legado como fallback.
        self.configuration.enrich_tables(tables)

        base_rows = self._valid_base_rows(info, base_data, result.get("nfs_ignoradas"))
        if not base_rows or (len(base_rows) > 1 and not self.d.base_rows_have_same_route(base_rows)):
            return result
        base_row = base_rows[0]
        weight_kg, weight_source = self.d.peso_base_kg_from_info(info)
        rule_base_row = dict(base_row)
        rule_base_row["peso_regra_kg"] = weight_kg
        rule = self.d.choose_partner_rule(partner_id, rule_base_row, tables)
        if not rule:
            return result
        rule = dict(rule)
        self.configuration.enrich_rule(rule)
        if not (rule.get("controle_dacte") or rule.get("gris_ativo") or rule.get("pedagio_ativo")):
            return result
        if not self.d.should_use_frete_peso(rule, info):
            return result

        ton_rate = rule.get("ton_rate", 0.0) or 0.0
        rate_kg = ton_rate / 1000.0 if ton_rate else 0.0
        minimum = rule.get("minimum", 0.0) or 0.0
        tolerance = tables.get("tolerance", 1.0)
        total_xml = self.d.parse_number_br(info.get("valor", ""))
        if ton_rate <= 0 or weight_kg <= 0:
            return result

        freight_raw = weight_kg * rate_kg
        freight_calculated = self._round_money(freight_raw)
        percent = float(rule.get('percent', 0.0) or 0.0)
        hybrid_c_vargas = bool(partner_id == 'AC_LOG_C_VARGAS' and percent > 0 and ton_rate > 0)
        percentage_base = 0.0
        percentage_calculated = 0.0
        if hybrid_c_vargas:
            try:
                percentage_base = float(result.get('base_frete') or base_row.get('valor_frete', 0.0) or 0.0)
            except Exception:
                percentage_base = 0.0
            percentage_calculated = self._round_money(percentage_base * percent)
            freight_final = self._round_money(max(freight_calculated, minimum, percentage_calculated))
            minimum_applied = bool(minimum and freight_final == self._round_money(minimum) and minimum > freight_calculated and minimum > percentage_calculated)
            if freight_final == percentage_calculated:
                freight_criterion = 'PERCENTUAL'
            elif freight_final == freight_calculated:
                freight_criterion = 'FRETE_PESO'
            else:
                freight_criterion = 'FRETE_MINIMO'
        else:
            minimum_applied = bool(minimum and minimum > freight_calculated)
            freight_final = self._round_money(max(freight_calculated, minimum))
            freight_criterion = 'FRETE_PESO' if not minimum_applied else 'FRETE_MINIMO'

        merchandise_value = self.d.parse_number_br(info.get("valor_carga", ""))
        if merchandise_value <= 0:
            try:
                merchandise_value = sum(float(row.get("valor_mercadoria", 0.0) or 0.0) for row in base_rows)
            except Exception:
                merchandise_value = 0.0

        calculated_components: list[dict[str, Any]] = []
        line_parts: list[str] = []
        freight_formula = (
            f"{self._fmt_num(weight_kg, places=3, thousands=True)} kg × "
            f"R${self._fmt_money_plain(rate_kg)}/kg = R${self._fmt_money_plain(freight_calculated)}"
        )
        if hybrid_c_vargas:
            line_parts.append(
                'Frete híbrido: maior entre '
                f'percentual R${self._fmt_money_plain(percentage_base)} × {self._fmt_percent_short(percent)} = R${self._fmt_money_plain(percentage_calculated)}, '
                f'frete-peso {freight_formula} e mínimo R${self._fmt_money_plain(minimum)} '
                f'→ R${self._fmt_money_plain(freight_final)} ({freight_criterion})'
            )
        elif minimum_applied:
            line_parts.append(
                f"Frete peso: {freight_formula} → mínimo R${self._fmt_money_plain(freight_final)}"
            )
        else:
            line_parts.append(f"Frete peso: {freight_formula}")

        freight_xml, freight_found = self._component_value_any(info, ["FRETE PESO"])
        if hybrid_c_vargas and not freight_found:
            freight_xml, freight_found = self._component_value_any(info, ["FRETE VALOR"])
        calculated_components.append({
            "nome": "FRETE HÍBRIDO" if hybrid_c_vargas else "FRETE PESO", "calc": freight_final,
            "xml": freight_xml, "found": freight_found,
        })

        gris_calculated = 0.0
        gris_xml, gris_found = self._component_value_any(info, ["GRIS", "GERENCIAMENTO RISCO", "RISCO"])
        gris_charged_xml = bool(gris_found) and abs(self._round_money(gris_xml)) > 0.0
        if rule.get("gris_ativo") and gris_charged_xml:
            gris_percent = rule.get("gris_percentual", 0.0) or 0.0
            gris_calculated = self._round_money(merchandise_value * gris_percent)
            calculated_components.append({
                "nome": "GRIS", "calc": gris_calculated,
                "xml": gris_xml, "found": gris_found,
            })
            line_parts.append(
                f"GRIS (mercadoria): R${self._fmt_money_plain(merchandise_value)} × "
                f"{self._fmt_percent_short(gris_percent)} = R${self._fmt_money_plain(gris_calculated)}"
            )

        toll_calculated = 0.0
        toll_quantity = 0
        toll_xml, toll_found = self._component_value_any(info, ["PEDAG", "PEDAGIO", "PEDÁGIO"])
        toll_charged_xml = bool(toll_found) and abs(self._round_money(toll_xml)) > 0.0
        if rule.get("pedagio_ativo") and toll_charged_xml:
            toll_value = rule.get("pedagio_valor", 0.0) or 0.0
            toll_fraction = rule.get("pedagio_fracao_kg", 100.0) or 100.0
            toll_quantity = int(math.ceil(weight_kg / toll_fraction)) if weight_kg > 0 and toll_fraction > 0 else 0
            toll_calculated = self._round_money(toll_quantity * toll_value)
            calculated_components.append({
                "nome": "PEDÁGIO", "calc": toll_calculated,
                "xml": toll_xml, "found": toll_found,
            })
            line_parts.append(
                f"Pedágio: {self._fmt_num(weight_kg, places=3, thousands=True)} kg ÷ "
                f"{self._fmt_num(toll_fraction, places=3, thousands=True)} kg = {toll_quantity} "
                f"{'fração' if toll_quantity == 1 else 'frações'} × "
                f"R${self._fmt_money_plain(toll_value)} = R${self._fmt_money_plain(toll_calculated)}"
            )

        expected = self._round_money(freight_final + gris_calculated + toll_calculated)
        difference = self._round_money(total_xml - expected)
        short_status = "OK" if abs(difference) <= tolerance else ("DIVERGENTE +" if difference > 0 else "DIVERGENTE -")
        rule_name = rule.get("controle_regra_nome") or "RODOTEC"
        line1 = " | ".join(line_parts)
        line2 = (
            f"Total calc.: {self._fmt_money_rs(expected)} | XML: {self._fmt_money_rs(total_xml)} | "
            f"Dif.: {self._fmt_money_rs(difference)} | {short_status}"
        )

        result["modo_calculo"] = "HIBRIDO_PERCENTUAL_FRETE_PESO_COMPONENTES" if hybrid_c_vargas else "FRETE_PESO_COMPONENTES"
        result["base_calculo"] = "MAX(PERCENTUAL,FRETE_PESO,MINIMO)+COMPONENTES" if hybrid_c_vargas else "FRETE_PESO+COMPONENTES"
        result["peso_base_kg"] = weight_kg
        result["peso_xml_fonte"] = weight_source
        result["peso_xml_todos"] = self.d.format_peso_xml_debug(info)
        result["tonelagem_taxa"] = ton_rate
        result["taxa_kg"] = rate_kg
        result["frete_peso_calculado"] = freight_calculated if hybrid_c_vargas else freight_final
        if hybrid_c_vargas:
            result["frete_percentual_calculado"] = percentage_calculated
            result["frete_peso_referencia"] = freight_calculated
            result["criterio_frete_aplicado"] = freight_criterion
            result["percentual"] = percent
            result["base_frete"] = percentage_base
        result["gris_calculado"] = gris_calculated if rule.get("gris_ativo") and gris_charged_xml else None
        result["gris_percentual"] = rule.get("gris_percentual") if rule.get("gris_ativo") and gris_charged_xml else None
        result["gris_cobrado_xml"] = bool(gris_charged_xml)
        result["pedagio_calculado"] = toll_calculated if rule.get("pedagio_ativo") and toll_charged_xml else None
        result["pedagio_qtd"] = toll_quantity if rule.get("pedagio_ativo") and toll_charged_xml else None
        result["pedagio_valor"] = rule.get("pedagio_valor") if rule.get("pedagio_ativo") and toll_charged_xml else None
        result["pedagio_fracao_kg"] = toll_fraction if rule.get("pedagio_ativo") and toll_charged_xml else None
        result["pedagio_tipo"] = "KG" if rule.get("pedagio_ativo") and toll_charged_xml else None
        result["pedagio_cobrado_xml"] = bool(toll_charged_xml)
        result["valor_total_xml"] = total_xml
        result["valor_comparado"] = total_xml
        result["componente_comparado"] = "VALOR TOTAL DO SERVIÇO"
        result["esperado"] = expected
        result["diferenca"] = difference
        result["tolerancia"] = tolerance
        result["controle_dacte_regra"] = rule_name
        result["controle_dacte_linha1"] = line1
        result["controle_dacte_linha2"] = line2
        result["controle_dacte_status"] = short_status
        result["controle_dacte_compacto"] = f"CONTROLE INTERNO - {rule_name}\n{line1}\n{line2}"
        result["componentes_calculados"] = calculated_components
        result["detalhe"] = (result.get("detalhe") or "") + (
            f"; controle interno {rule_name}: maior entre percentual, frete peso e mínimo + componentes"
            if hybrid_c_vargas else f"; controle interno {rule_name}: frete peso + componentes"
        )

        suffix = " NF PARCIAL" if result.get("validacao_parcial") else ""
        if abs(difference) <= tolerance:
            result["status"] = f"OK {rule_name}".strip() + suffix
        elif difference > 0:
            result["status"] = f"DIVERGENTE {rule_name} +".strip() + suffix
        else:
            result["status"] = f"DIVERGENTE {rule_name} -".strip() + suffix

        trace = result.setdefault("trace", [])
        trace.append(f"Controle interno {rule_name}: cálculo composto ativado pela tabela do parceiro.")
        if hybrid_c_vargas:
            trace.append(
                f"R12.13.7 AC Log / C Vargas: frete oficial = maior entre percentual (R$ {self.d.money(percentage_calculated)}), "
                f"frete-peso (R$ {self.d.money(freight_calculated)}) e mínimo (R$ {self.d.money(minimum)}); "
                f"critério vencedor {freight_criterion}, valor R$ {self.d.money(freight_final)}."
            )
        if rule.get("gris_ativo") and not gris_charged_xml:
            trace.append("GRIS cadastrado para a regra, mas não cobrado no XML; componente opcional ignorado no total esperado.")
        if rule.get("pedagio_ativo") and not toll_charged_xml:
            trace.append("Pedágio cadastrado para a regra, mas não cobrado no XML; componente opcional ignorado no total esperado.")
        trace.append(f"Linha compacta: {line1}")
        trace.append(f"Conferência total: {line2}")
        for component in calculated_components:
            component_difference = self._round_money((component.get("xml") or 0.0) - (component.get("calc") or 0.0))
            component_status = "OK" if abs(component_difference) <= tolerance else "DIVERGENTE"
            trace.append(
                f"Componente {component.get('nome')}: calculado R$ {self.d.money(component.get('calc'))}; "
                f"XML R$ {self.d.money(component.get('xml'))}; diferença R$ {self.d.money(component_difference)}; "
                f"{component_status}."
            )
        return result


__all__ = [
    "COMPONENT_CALCULATOR_VERSION",
    "ComponentCalculationDependencies",
    "ComponentCalculationService",
]
