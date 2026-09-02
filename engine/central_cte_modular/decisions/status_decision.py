from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata
from typing import Any, Iterable, Mapping


class DecisionFamily(str, Enum):
    NOT_VALIDATED = "NAO_VALIDADO"
    OK = "OK"
    DIVERGENT = "DIVERGENTE"
    REVIEW = "REVISAO"
    NO_BASE = "SEM_BASE"
    NO_RULE = "SEM_PARCEIRO_REGRA"
    ERROR = "ERRO"
    INFORMATIONAL = "INFORMATIVO"
    OTHER = "OUTROS"


class PaymentDisposition(str, Enum):
    PAY = "PAGAR"
    REVIEW = "CONFERIR"
    INFORMATIONAL = "INFORMATIVO"


@dataclass(frozen=True)
class StatusDecision:
    raw_status: str
    normalized_status: str
    family: DecisionFamily
    disposition: PaymentDisposition
    tags: tuple[str, ...]
    report_bucket: str
    color_key: str

    def has(self, tag: str) -> bool:
        return str(tag or "").strip().lower() in self.tags

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_status": self.raw_status,
            "normalized_status": self.normalized_status,
            "family": self.family.value,
            "disposition": self.disposition.value,
            "tags": list(self.tags),
            "report_bucket": self.report_bucket,
            "color_key": self.color_key,
        }


def normalize_status(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^A-Z0-9+\-/ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class StatusDecisionEngine:
    """Classificador único de status de validação.

    O texto original continua intacto. O motor gera uma família principal e
    etiquetas cumulativas, permitindo que tela, filtros, cards e relatórios
    usem a mesma decisão sem repetir buscas frágeis por palavras.
    """

    FILTER_ALIASES = {
        "TODOS": "all",
        "NAO VALIDADO": "not_validated",
        "OK": "ok",
        "DIVERGENTES": "divergent",
        "REVISAO": "review",
        "SEM BASE": "no_base",
        "SEM PARCEIRO/REGRA": "no_rule",
        "ERROS": "error",
        "REVISADO": "manual_review",
        "COM OBSERVACAO": "manual_observation",
    }

    def classify(self, status: Any) -> StatusDecision:
        raw = str(status or "").strip() or "NÃO VALIDADO"
        normalized = normalize_status(raw)
        tags: set[str] = set()

        if normalized in {"", "NAO VALIDADO", "PENDENTE"}:
            tags.add("not_validated")
        if normalized.startswith("OK"):
            tags.add("ok")
        if "DIVERGENTE" in normalized:
            tags.add("divergent")

        if any(token in normalized for token in (
            "REVISAR", "REVISAO", "AMBIG", "MULTIPLAS", "PENDENTE",
            "SEM VALOR", "SEM DADOS", "CONFERIR",
        )):
            tags.add("review")

        if any(token in normalized for token in (
            "NF NAO ENCONTRADA", "NF FORA DA BASE", "ORIGINAL NAO ENCONTRADO",
            "BASE NAO CARREGADA", "NF INCOMPATIVEL", "NF AMBIGUA",
            "MULTIPLAS ROTAS",
        )):
            tags.add("no_base")

        if any(token in normalized for token in (
            "PARCEIRO", "REGRA", "TABELAS NAO CARREGADAS",
        )):
            tags.add("no_rule")

        if any(token in normalized for token in (
            "ERRO", "NF NAO LIDA", "NAO E CT-E",
        )):
            tags.add("error")

        if any(token in normalized for token in (
            "IGNORADO", "ANULACAO", "NAO E CT-E",
        )):
            tags.add("informational")

        # Família principal. Estados informativos têm precedência para impedir
        # que anulações entrem como cobrança normal apenas porque começam em OK.
        if "not_validated" in tags:
            family = DecisionFamily.NOT_VALIDATED
        elif "informational" in tags:
            family = DecisionFamily.INFORMATIONAL
        elif "error" in tags:
            family = DecisionFamily.ERROR
        elif "divergent" in tags:
            family = DecisionFamily.DIVERGENT
        elif "ok" in tags:
            family = DecisionFamily.OK
        elif "no_base" in tags:
            family = DecisionFamily.NO_BASE
        elif "review" in tags and "EXTRA" in normalized:
            family = DecisionFamily.REVIEW
        elif "no_rule" in tags:
            family = DecisionFamily.NO_RULE
        elif "review" in tags:
            family = DecisionFamily.REVIEW
        else:
            family = DecisionFamily.OTHER

        if family is DecisionFamily.OK:
            disposition = PaymentDisposition.PAY
        elif family is DecisionFamily.INFORMATIONAL:
            disposition = PaymentDisposition.INFORMATIONAL
        else:
            disposition = PaymentDisposition.REVIEW

        bucket_map = {
            DecisionFamily.OK: "OK",
            DecisionFamily.DIVERGENT: "DIVERGENTES",
            DecisionFamily.NO_BASE: "SEM_BASE",
            DecisionFamily.NO_RULE: "SEM_PARCEIRO_REGRA",
            DecisionFamily.REVIEW: "REVISAO_ERROS",
            DecisionFamily.ERROR: "REVISAO_ERROS",
            DecisionFamily.NOT_VALIDATED: "REVISAO_ERROS",
            DecisionFamily.INFORMATIONAL: "OUTROS",
            DecisionFamily.OTHER: "OUTROS",
        }
        color_map = {
            DecisionFamily.OK: "green",
            DecisionFamily.DIVERGENT: "red",
            DecisionFamily.REVIEW: "yellow",
            DecisionFamily.NO_BASE: "gray",
            DecisionFamily.NO_RULE: "orange",
            DecisionFamily.ERROR: "red",
            DecisionFamily.NOT_VALIDATED: "gray",
            DecisionFamily.INFORMATIONAL: "gray",
            DecisionFamily.OTHER: "gray",
        }

        return StatusDecision(
            raw_status=raw,
            normalized_status=normalized,
            family=family,
            disposition=disposition,
            tags=tuple(sorted(tags)),
            report_bucket=bucket_map[family],
            color_key=color_map[family],
        )

    def matches_filter(self, status: Any, selected_filter: Any) -> bool:
        selected_raw = str(selected_filter or "TODOS").strip()
        selected = normalize_status(selected_raw)
        if selected_raw.upper().startswith("STATUS: "):
            expected = selected_raw.split(":", 1)[1].strip()
            return str(status or "").strip() == expected

        alias = self.FILTER_ALIASES.get(selected)
        if alias in {None, "all", "manual_review", "manual_observation"}:
            return True

        decision = self.classify(status)
        if alias == "not_validated":
            return decision.family is DecisionFamily.NOT_VALIDATED
        if alias == "ok":
            return decision.family is DecisionFamily.OK
        if alias == "divergent":
            return decision.family is DecisionFamily.DIVERGENT
        return decision.has(alias)

    def decorate_result(self, result: Mapping[str, Any] | None) -> dict[str, Any]:
        output = dict(result or {})
        decision = self.classify(output.get("status"))
        output["status_family"] = decision.family.value
        output["status_disposition"] = decision.disposition.value
        output["status_tags"] = list(decision.tags)
        output["status_report_bucket"] = decision.report_bucket
        output["status_color_key"] = decision.color_key
        return output

    def summarize_counts(self, counts: Mapping[str, int] | None) -> dict[str, int]:
        summary = {
            "total": 0,
            "ok": 0,
            "divergent": 0,
            "review": 0,
            "no_base": 0,
            "no_rule": 0,
            "error": 0,
            "informational": 0,
            "not_validated": 0,
            "other": 0,
        }
        family_keys = {
            DecisionFamily.OK: "ok",
            DecisionFamily.DIVERGENT: "divergent",
            DecisionFamily.REVIEW: "review",
            DecisionFamily.NO_BASE: "no_base",
            DecisionFamily.NO_RULE: "no_rule",
            DecisionFamily.ERROR: "error",
            DecisionFamily.INFORMATIONAL: "informational",
            DecisionFamily.NOT_VALIDATED: "not_validated",
            DecisionFamily.OTHER: "other",
        }
        review_total = 0
        for status, quantity in (counts or {}).items():
            try:
                qty = int(quantity or 0)
            except Exception:
                qty = 0
            decision = self.classify(status)
            summary["total"] += qty
            summary[family_keys[decision.family]] += qty
            if any(decision.has(tag) for tag in ("review", "no_base", "no_rule", "error", "not_validated")):
                review_total += qty
        summary["review_total"] = review_total
        return summary

    def count_divergences(self, rows: Iterable[Mapping[str, Any]]) -> tuple[int, float]:
        quantity = 0
        total_difference = 0.0
        for row in rows:
            result = row.get("validacao") or {}
            decision = self.classify(result.get("status"))
            if decision.family is not DecisionFamily.DIVERGENT:
                continue
            quantity += 1
            try:
                total_difference += abs(float(result.get("diferenca") or 0.0))
            except Exception:
                try:
                    text = str(result.get("diferenca") or "0").replace(".", "").replace(",", ".")
                    total_difference += abs(float(text))
                except Exception:
                    pass
        return quantity, total_difference
