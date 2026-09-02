from __future__ import annotations

"""Guarda final do cálculo compacto antes de HTML, assinatura e PDF.

A validação comercial é a fonte de verdade. Sessões ou fotografias antigas
podem carregar um bloco compacto criado antes dos últimos enriquecimentos.
Este serviço reconstrói o bloco a partir do resultado final e impede que um
status ``OK`` seja impresso junto de uma diferença visual acima da tolerância.
"""

import re
import unicodedata
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

COMPACT_RENDER_GUARD_VERSION = "2.7.0-RC25.1-R12.13.9"


class CompactConsistencyError(RuntimeError):
    """Indica que um documento ainda possui bloco compacto incompatível."""


@dataclass(frozen=True)
class CompactGuardAudit:
    cte: str
    repaired: bool
    inconsistent: bool
    difference: float
    reason: str


class FinalCompactRenderGuard:
    """Reconstrói o bloco visual usando exclusivamente o resultado validado."""

    _diff_pattern = re.compile(
        r"Dif(?:erença|\.\s*comp\.|\.?)\s*:?\s*R\$\s*([+-]?[\d\.]+(?:,\d+)?)",
        flags=re.I,
    )

    @staticmethod
    def _norm(value: Any) -> str:
        text = unicodedata.normalize("NFD", str(value or ""))
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", text).strip().upper()

    @staticmethod
    def _parse(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value or "").strip().replace("R$", "").replace(" ", "")
        if not text:
            return 0.0
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return float(text)
        except Exception:
            return 0.0

    @staticmethod
    def _round(value: Any) -> float:
        try:
            return round(float(value or 0.0) + 1e-9, 2)
        except Exception:
            return 0.0

    @staticmethod
    def _money(value: Any) -> str:
        number = FinalCompactRenderGuard._round(value)
        return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    @staticmethod
    def _percent(value: Any) -> str:
        try:
            number = float(value or 0.0) * 100.0
        except Exception:
            number = 0.0
        if abs(number - round(number)) < 1e-8:
            return f"{int(round(number))}%"
        return f"{number:.4f}".rstrip("0").rstrip(".").replace(".", ",") + "%"

    @staticmethod
    def _weight(value: Any) -> str:
        number = FinalCompactRenderGuard._parse(value)
        places = 0 if abs(number - round(number)) < 0.0001 else 3
        text = f"{number:,.{places}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return text.rstrip("0").rstrip(",") if "," in text else text

    def _base_description(self, validation: Mapping[str, Any]) -> str:
        text = self._norm(validation.get("base_calculo") or "")
        if "SEM ICMS" in text or "SEM_ICMS" in str(validation.get("base_calculo") or "").upper():
            return "base sem ICMS"
        if "ORIGINAL" in text or "BRUTO" in text:
            return "base original"
        return "base usada"

    def _component_sum(self, info: Mapping[str, Any], aliases: tuple[str, ...]) -> float:
        aliases_norm = tuple(self._norm(alias) for alias in aliases)
        total = 0.0
        for component in info.get("componentes", []) or []:
            name = self._norm((component or {}).get("nome", ""))
            if any(alias in name for alias in aliases_norm):
                total += self._parse((component or {}).get("valor", ""))
        return self._round(total)

    def _total_components(self, info: Mapping[str, Any]) -> float:
        total = 0.0
        for component in info.get("componentes", []) or []:
            total += self._parse((component or {}).get("valor", ""))
        return self._round(total)

    def _manual_approved(self, validation: Mapping[str, Any]) -> bool:
        manual = validation.get("manual_decision")
        action = ""
        if isinstance(manual, Mapping):
            action = self._norm(manual.get("decision") or "")
        review = self._norm(validation.get("revisao_manual") or "")
        status = self._norm(validation.get("status") or "")
        persisted = self._norm(validation.get("status_final_persistido") or "")
        return bool(
            validation.get("baixa_manual_aplicada")
            or action == "APPROVED"
            or review == "APROVADO"
            or status.startswith("OK MANUAL")
            or status.startswith("OK EXTRA AUTORIZADO")
            or persisted.startswith("OK MANUAL")
            or persisted.startswith("OK EXTRA AUTORIZADO")
        )

    def _status_short(self, validation: Mapping[str, Any], difference: float, tolerance: float) -> str:
        status = self._norm(validation.get("status") or "")
        if self._manual_approved(validation):
            return "OK EXTRA AUTORIZADO" if "EXTRA" in status else "OK MANUAL"
        if status.startswith("OK"):
            return "OK" if abs(difference) <= tolerance else "REVISAR BLOCO"
        if "DIVERG" in status:
            return "DIVERGENTE"
        if any(token in status for token in ("REVIS", "PEND", "REGRA", "BASE", "AMBIG")):
            return "REVISAR"
        return str(validation.get("status") or "PENDENTE")

    def _ensure_manual_compact(
        self,
        validation: MutableMapping[str, Any],
        *,
        difference: float,
    ) -> None:
        """Garante um bloco auditável para toda baixa manual aprovada.

        A aprovação manual não apaga o cálculo automático. Para evitar que
        fotografias antigas reaproveitem um bloco incompleto, o fallback
        manual é reconstruído de forma determinística e carrega a justificativa
        em campos próprios usados também pelo PDF assinado.
        """
        if not self._manual_approved(validation):
            return

        automatic_status = str(
            validation.get("automatic_status")
            or validation.get("engine_status")
            or "RESULTADO AUTOMÁTICO"
        ).strip()
        expected = self._parse(
            validation.get("automatic_expected_value")
            if validation.get("automatic_expected_value") not in (None, "")
            else validation.get("esperado")
        )
        compared = self._parse(validation.get("valor_comparado"))
        if compared <= 0:
            compared = self._parse(validation.get("valor_total_xml"))
        tolerance = self._parse(validation.get("tolerancia")) or 1.0
        rule = str(
            validation.get("controle_dacte_regra")
            or validation.get("partner_name")
            or validation.get("partner_id")
            or "BAIXA MANUAL"
        ).strip()

        # Quando não existe fórmula compacta reconstruível, não reutiliza
        # texto antigo: imprime a fotografia automática que motivou a baixa.
        if not str(validation.get("controle_dacte_origem") or "").startswith("RESULTADO FINAL VALIDADO"):
            pieces = [f"Resultado automático: {automatic_status}"]
            if expected > 0:
                pieces.append(f"Esperado R${self._money(expected)}")
            if compared > 0:
                pieces.append(f"Cobrado R${self._money(compared)}")
            validation["controle_dacte_linha1"] = " | ".join(pieces)

        final_short = "OK EXTRA AUTORIZADO" if "EXTRA" in self._norm(validation.get("status")) else "OK MANUAL"
        validation["controle_dacte_linha2"] = (
            f"Dif. automática R${self._money(difference)} | Tol. R${self._money(tolerance)} | "
            f"Validação: {final_short}"
        )
        validation["controle_dacte_regra"] = rule
        validation["controle_dacte_status"] = final_short
        validation["controle_dacte_compacto"] = (
            f"CONTROLE INTERNO - {rule}\n"
            f"{validation.get('controle_dacte_linha1') or ''}\n"
            f"{validation.get('controle_dacte_linha2') or ''}"
        )
        validation["controle_dacte_diferenca"] = self._round(difference)
        validation["controle_dacte_inconsistente"] = False
        validation["controle_dacte_versao"] = COMPACT_RENDER_GUARD_VERSION
        validation["controle_dacte_origem"] = "BAIXA MANUAL + RESULTADO AUTOMÁTICO PRESERVADO"
        validation["baixa_manual_aplicada"] = True

        manual = validation.get("manual_decision")
        reason = str(validation.get("observacao_manual") or validation.get("controle_dacte_justificativa") or "").strip()
        actor = str(validation.get("controle_dacte_responsavel_manual") or "").strip()
        decided_at = str(validation.get("revisao_data") or validation.get("controle_dacte_data_manual") or "").strip()
        if isinstance(manual, Mapping):
            reason = reason or str(manual.get("reason") or "").strip()
            actor = actor or str(manual.get("actor_name") or manual.get("actor_id") or "").strip()
            decided_at = decided_at or str(manual.get("decided_at") or "").strip()
        validation["controle_dacte_justificativa"] = reason
        validation["controle_dacte_responsavel_manual"] = actor
        validation["controle_dacte_data_manual"] = decided_at

    def _extract_existing_difference(self, validation: Mapping[str, Any]) -> float | None:
        line = str(validation.get("controle_dacte_linha2") or "")
        match = self._diff_pattern.search(line)
        if not match:
            return None
        return self._parse(match.group(1))

    def _build_percentage_compact(
        self,
        info: Mapping[str, Any],
        validation: MutableMapping[str, Any],
    ) -> tuple[bool, float, str]:
        component = self._norm(validation.get("componente_comparado") or "")
        if "FRETE VALOR" not in component:
            return False, 0.0, "componente final não é FRETE VALOR"

        base = self._parse(validation.get("base_frete"))
        percentage = self._parse(validation.get("percentual"))
        expected = self._parse(validation.get("esperado"))
        compared = self._parse(validation.get("valor_comparado"))
        if base <= 0 or percentage <= 0 or expected <= 0:
            return False, 0.0, "campos finais insuficientes para percentual"

        gross = self._round(base * percentage)
        status = self._norm(validation.get("status") or "")
        if expected > gross + 0.01:
            if "MINIMO" in status:
                freight_label = (
                    f"Frete valor ({self._base_description(validation)}): R${self._money(base)} × {self._percent(percentage)} = "
                    f"R${self._money(gross)} → mínimo R${self._money(expected)}"
                )
            elif validation.get("repasse_embutido_status"):
                freight_label = (
                    f"Frete valor ({self._base_description(validation)}): R${self._money(base)} × {self._percent(percentage)} = "
                    f"R${self._money(gross)} → repasse R${self._money(expected)}"
                )
            else:
                freight_label = (
                    f"Frete valor ({self._base_description(validation)}): R${self._money(base)} × {self._percent(percentage)} = "
                    f"R${self._money(gross)} → ajuste R${self._money(expected)}"
                )
        else:
            freight_label = (
                f"Frete valor ({self._base_description(validation)}): R${self._money(base)} × {self._percent(percentage)} = "
                f"R${self._money(expected)}"
            )

        tolerance = self._parse(validation.get("tolerancia")) or 1.0
        if compared > 0 and abs(self._round(compared - expected)) > tolerance:
            freight_label = freight_label.replace("Frete valor (", "Frete valor ref. (", 1)
            freight_label += f" (XML R${self._money(compared)})"

        gris_xml = self._component_sum(info, ("GRIS", "GERENCIAMENTO RISCO", "RISCO"))
        toll_xml = self._component_sum(info, ("PEDAGIO", "PEDÁGIO", "PEDAG"))
        freight_xml = compared or self._component_sum(info, ("FRETE VALOR",))
        all_components = self._total_components(info)

        gris_reference = self._parse(validation.get("gris_calculado"))
        if gris_reference <= 0 and gris_xml > 0:
            gris_reference = gris_xml
        toll_reference = self._parse(validation.get("pedagio_calculado"))
        if toll_reference <= 0 and toll_xml > 0:
            toll_reference = toll_xml

        parts = [freight_label]
        if gris_xml > 0:
            merchandise = self._parse(info.get("valor_carga"))
            gris_percentage = self._parse(validation.get("gris_percentual"))
            if merchandise > 0 and gris_percentage > 0:
                parts.append(
                    f"GRIS (mercadoria): R${self._money(merchandise)} × {self._percent(gris_percentage)} = "
                    f"R${self._money(gris_reference)}"
                )
            else:
                parts.append(f"GRIS: XML {self._money(gris_xml)}")
        if toll_xml > 0:
            quantity = int(self._parse(validation.get("pedagio_qtd")))
            toll_value = self._parse(validation.get("pedagio_valor"))
            if quantity > 0 and toll_value > 0:
                fraction = self._parse(
                    validation.get("pedagio_fracao_kg")
                    or validation.get("pedagio_componente_fracao_kg")
                )
                weight = self._parse(
                    validation.get("peso_base_kg")
                    or validation.get("pedagio_componente_peso_kg")
                )
                kind = self._norm(
                    validation.get("pedagio_tipo")
                    or validation.get("pedagio_componente_tipo")
                )
                if ("KG" in kind or fraction > 0) and fraction > 0:
                    if weight > 0:
                        parts.append(
                            f"Pedágio: {self._weight(weight)} kg ÷ {self._weight(fraction)} kg = "
                            f"{quantity} {'fração' if quantity == 1 else 'frações'} × "
                            f"R${self._money(toll_value)} = R${self._money(toll_reference)}"
                        )
                    else:
                        parts.append(
                            f"Pedágio: {quantity} {'fração' if quantity == 1 else 'frações'} de {self._weight(fraction)} kg × "
                            f"R${self._money(toll_value)} = R${self._money(toll_reference)}"
                        )
                else:
                    parts.append(
                        f"Pedágio: 1 CT-e × R${self._money(toll_value)} = R${self._money(toll_reference)}"
                    )
            else:
                parts.append(f"Pedágio: XML R${self._money(toll_xml)}")

        known_xml = self._round(freight_xml + gris_xml + toll_xml)
        other_xml = self._round(all_components - known_xml)
        if other_xml > 0.01:
            parts.append(f"Outros comp.: XML {self._money(other_xml)}")

        reference_total = self._round(expected + gris_reference + toll_reference + max(other_xml, 0.0))
        total_xml = self._parse(info.get("valor") or info.get("vTPrest"))
        if total_xml <= 0:
            total_xml = all_components
        total_xml = self._round(total_xml)
        difference = self._round(total_xml - reference_total)
        short_status = self._status_short(validation, difference, tolerance)
        rule_name = str(validation.get("controle_dacte_regra") or validation.get("partner_id") or "CONTROLE")
        line1 = " | ".join(parts)
        line2 = (
            f"Total comp.: R${self._money(reference_total)} | XML: R${self._money(total_xml)} | "
            f"Dif. comp.: R${self._money(difference)} | Validação: {short_status}"
        )
        validation.update(
            {
                "controle_dacte_regra": rule_name,
                "controle_dacte_linha1": line1,
                "controle_dacte_linha2": line2,
                "controle_dacte_status": short_status,
                "controle_dacte_compacto": f"CONTROLE INTERNO - {rule_name}\n{line1}\n{line2}",
                "controle_dacte_diferenca": difference,
                "controle_dacte_total_referencia": reference_total,
                "controle_dacte_total_xml": total_xml,
                "controle_dacte_versao": COMPACT_RENDER_GUARD_VERSION,
                "controle_dacte_origem": "RESULTADO FINAL VALIDADO",
                "controle_dacte_inconsistente": bool(short_status == "REVISAR BLOCO"),
            }
        )
        return True, difference, "compacto percentual reconstruído pelo resultado final"

    def repair_validation(
        self,
        info: Mapping[str, Any],
        validation: MutableMapping[str, Any],
    ) -> CompactGuardAudit:
        cte = str(info.get("numero") or info.get("chave") or "SEM NÚMERO")
        tolerance = self._parse(validation.get("tolerancia")) or 1.0
        rebuilt, difference, reason = self._build_percentage_compact(info, validation)

        if not rebuilt:
            existing_difference = self._extract_existing_difference(validation)
            if existing_difference is not None:
                difference = self._round(existing_difference)
            else:
                published_difference = validation.get("automatic_difference")
                if published_difference in (None, ""):
                    published_difference = validation.get("diferenca")
                difference = self._round(published_difference)
            final_status = self._norm(validation.get("status") or "")
            manual_approved = self._manual_approved(validation)
            inconsistent = bool(
                final_status.startswith("OK")
                and abs(difference) > tolerance
                and not manual_approved
            )
            if manual_approved:
                self._ensure_manual_compact(validation, difference=difference)
                reason = (
                    "baixa manual aprovada; divergência automática preservada para auditoria sem bloquear o PDF"
                )
            elif inconsistent:
                line2 = str(validation.get("controle_dacte_linha2") or "")
                if line2:
                    line2 = re.sub(
                        r"Validação\s*:\s*[^|]+$",
                        "Validação: REVISAR BLOCO",
                        line2,
                        flags=re.I,
                    )
                    validation["controle_dacte_linha2"] = line2
                    rule = str(validation.get("controle_dacte_regra") or "CONTROLE")
                    line1 = str(validation.get("controle_dacte_linha1") or "")
                    validation["controle_dacte_compacto"] = (
                        f"CONTROLE INTERNO - {rule}\n{line1}\n{line2}"
                    )
                validation["controle_dacte_status"] = "REVISAR BLOCO"
                validation["controle_dacte_inconsistente"] = True
                validation["controle_dacte_versao"] = COMPACT_RENDER_GUARD_VERSION
                validation["controle_dacte_origem"] = "GUARDA FINAL"
                reason = "OK bloqueado porque a diferença visual excede a tolerância"
            return CompactGuardAudit(cte, bool(manual_approved), inconsistent, difference, reason)

        if self._manual_approved(validation):
            self._ensure_manual_compact(validation, difference=difference)
            return CompactGuardAudit(
                cte,
                True,
                False,
                difference,
                "compacto reconstruído e baixa manual aprovada preservada",
            )

        inconsistent = bool(validation.get("controle_dacte_inconsistente"))
        return CompactGuardAudit(cte, True, inconsistent, difference, reason)

    def prepare_info(self, info: Mapping[str, Any]) -> tuple[dict[str, Any], CompactGuardAudit | None]:
        prepared = dict(info)
        validation_source = info.get("validacao")
        if not isinstance(validation_source, Mapping):
            return prepared, None
        validation = dict(validation_source)
        prepared["validacao"] = validation
        audit = self.repair_validation(prepared, validation)
        trace = validation.setdefault("trace", [])
        if isinstance(trace, list):
            marker = (
                f"Guarda final do compacto {COMPACT_RENDER_GUARD_VERSION}: "
                f"{audit.reason}; diferença R$ {self._money(audit.difference)}."
            )
            if marker not in trace:
                trace.append(marker)
        return prepared, audit

    def prepare_infos(
        self,
        infos: Iterable[Mapping[str, Any]],
        *,
        strict: bool = True,
    ) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        inconsistencies: list[CompactGuardAudit] = []
        for info in infos:
            one, audit = self.prepare_info(info)
            prepared.append(one)
            if audit is not None and audit.inconsistent:
                inconsistencies.append(audit)
        if strict and inconsistencies:
            details = ", ".join(
                f"CT-e {item.cte} (dif. R$ {self._money(item.difference)})"
                for item in inconsistencies[:12]
            )
            if len(inconsistencies) > 12:
                details += f" e mais {len(inconsistencies) - 12}"
            raise CompactConsistencyError(
                "Geração bloqueada: o cálculo compacto ainda diverge do status final. " + details
            )
        return prepared


__all__ = [
    "COMPACT_RENDER_GUARD_VERSION",
    "CompactConsistencyError",
    "CompactGuardAudit",
    "FinalCompactRenderGuard",
]
