from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Mapping
import json
import re
import unicodedata

from .cte_parser import parse_xml_modular

SHADOW_VERSION = "2.6.66.5"

CORE_FIELDS = (
    "tipo", "numero", "serie", "chave", "emitente", "destinatario", "valor",
    "data", "data_br", "modelo", "natOp", "cfop", "origem", "destino",
    "vTPrest", "vRec", "produto", "outras_carac", "valor_carga",
    "peso_bruto", "peso_base", "peso_aferido", "cubagem", "volumes", "rntrc",
)

CTE_FIELDS = (
    "componentes", "docs", "obs", "obs_principal", "uso_exclusivo",
    "emit", "rem", "dest", "exped", "receb", "toma", "prot", "seguro", "imposto",
    "modal", "tpCTe", "tpServ", "toma_txt", "forma_pagamento",
)

CRITICAL_FIELDS = frozenset({
    "tipo", "numero", "serie", "chave", "emitente", "destinatario", "valor",
    "modelo", "cfop", "origem", "destino", "vTPrest", "vRec", "valor_carga",
    "peso_bruto", "peso_base", "peso_aferido", "cubagem", "volumes", "rntrc",
    "componentes", "docs", "emit", "rem", "dest", "exped", "receb", "toma",
})

INFORMATIVE_FIELDS = frozenset({
    "data", "data_br", "natOp", "produto", "outras_carac", "obs", "obs_principal",
    "uso_exclusivo", "prot", "seguro", "imposto", "modal", "tpCTe", "tpServ",
    "toma_txt", "forma_pagamento",
})

NUMERIC_FIELDS = frozenset({
    "valor", "vTPrest", "vRec", "valor_carga", "peso_bruto", "peso_base",
    "peso_aferido", "cubagem", "base", "aliq", "red", "st", "qCarga",
})

DIGIT_FIELDS = frozenset({
    "chave", "cnpj", "cnpjcpf", "cpf", "cep", "rntrc", "nProt", "apolice",
    "averbacao",
})

INTEGER_TEXT_FIELDS = frozenset({"numero", "serie", "n_doc"})


@dataclass
class ShadowComparison:
    path: str
    equal: bool
    status: str
    differences: dict[str, dict[str, Any]] = field(default_factory=dict)
    legacy_error: str = ""
    modular_error: str = ""
    legacy_summary: dict[str, Any] = field(default_factory=dict)
    modular_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def critical_count(self) -> int:
        return sum(1 for item in self.differences.values() if item.get("severity") == "CRÍTICA")

    @property
    def informative_count(self) -> int:
        return sum(1 for item in self.differences.values() if item.get("severity") == "INFORMATIVA")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SHADOW_VERSION,
            "path": self.path,
            "equal": self.equal,
            "status": self.status,
            "critical_count": self.critical_count,
            "informative_count": self.informative_count,
            "differences": self.differences,
            "legacy_error": self.legacy_error,
            "modular_error": self.modular_error,
            "legacy_summary": self.legacy_summary,
            "modular_summary": self.modular_summary,
        }


def _collapse(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _decimal_text(value: Any) -> str:
    raw = _collapse(str(value or ""))
    if not raw:
        return ""
    cleaned = raw.replace("R$", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return raw.casefold()
    normalized = format(number.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _integer_text(value: Any) -> str:
    digits = _digits(value)
    if not digits:
        return _collapse(str(value or "")).casefold()
    try:
        return str(int(digits))
    except Exception:
        return digits


def _field_name(path: str) -> str:
    token = path.rsplit(".", 1)[-1]
    token = re.sub(r"\[\d+\]$", "", token)
    return token


def _normalize_scalar(path: str, value: Any) -> Any:
    name = _field_name(path)
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return _decimal_text(value)
    if name in DIGIT_FIELDS:
        return _digits(value)
    if name in INTEGER_TEXT_FIELDS:
        return _integer_text(value)
    if name in NUMERIC_FIELDS or name.lower().startswith(("vcomp", "valor_")):
        return _decimal_text(value)
    return _collapse(str(value)).casefold()


def normalize_value(path: str, value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): normalize_value(f"{path}.{key}" if path else str(key), item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        normalized = [normalize_value(f"{path}[{index}]", item) for index, item in enumerate(value)]
        root = path.split(".", 1)[0].split("[", 1)[0]
        if root in {"docs", "componentes"}:
            normalized.sort(key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
        return normalized
    return _normalize_scalar(path, value)


def _severity(field_name: str) -> str:
    if field_name in CRITICAL_FIELDS or field_name.startswith("__erro"):
        return "CRÍTICA"
    if field_name in INFORMATIVE_FIELDS:
        return "INFORMATIVA"
    return "INFORMATIVA"


def _summary(info: Mapping[str, Any] | None) -> dict[str, Any]:
    data = info if isinstance(info, Mapping) else {}
    return {
        "tipo": data.get("tipo", ""),
        "numero": data.get("numero", ""),
        "serie": data.get("serie", ""),
        "chave": data.get("chave", ""),
        "emitente": data.get("emitente", ""),
        "destinatario": data.get("destinatario", ""),
        "valor": data.get("valor", data.get("vTPrest", "")),
    }


class ParserShadowComparator:
    """Compara o parser legado com o modular sem alterar o retorno oficial.

    O método ``build_audited_parser`` cria um invólucro que chama o parser legado
    exatamente uma vez, utiliza o resultado já obtido para a comparação e devolve
    o mesmo objeto ao programa. Falhas da auditoria nunca interrompem a importação.
    """

    def __init__(
        self,
        legacy_parser: Callable[[Path], dict[str, Any]],
        logger: Callable[[str], None] | None = None,
        *,
        modular_parser: Callable[[Path], dict[str, Any]] = parse_xml_modular,
        on_result: Callable[[ShadowComparison], Any] | None = None,
    ):
        if not callable(legacy_parser):
            raise TypeError("O parser legado precisa ser chamável.")
        if not callable(modular_parser):
            raise TypeError("O parser modular precisa ser chamável.")
        self.legacy_parser = legacy_parser
        self.modular_parser = modular_parser
        self.logger = logger
        self.on_result = on_result

    def compare(self, path: Path | str) -> ShadowComparison:
        path = Path(path)
        try:
            legacy = self.legacy_parser(path)
            legacy_error = ""
        except Exception as exc:
            legacy, legacy_error = {}, f"{type(exc).__name__}: {exc}"
        return self.compare_with_legacy(path, legacy, legacy_error=legacy_error)

    def compare_with_legacy(
        self,
        path: Path | str,
        legacy_result: Mapping[str, Any] | None,
        *,
        legacy_error: str = "",
    ) -> ShadowComparison:
        path = Path(path)
        try:
            modular = self.modular_parser(path)
            modular_error = ""
        except Exception as exc:
            modular, modular_error = {}, f"{type(exc).__name__}: {exc}"
        return self.compare_results(
            path,
            legacy_result,
            modular,
            legacy_error=legacy_error,
            modular_error=modular_error,
        )

    def compare_results(
        self,
        path: Path | str,
        legacy_result: Mapping[str, Any] | None,
        modular_result: Mapping[str, Any] | None,
        *,
        legacy_error: str = "",
        modular_error: str = "",
    ) -> ShadowComparison:
        """Compara resultados já calculados sem reler o XML.

        Este método é a peça que permite a promoção controlada: o modular e o
        legado são executados uma vez cada, comparados e então a ponte decide qual
        dicionário será devolvido ao restante do programa.
        """
        path = Path(path)
        legacy = dict(legacy_result or {})
        modular = dict(modular_result or {})

        differences: dict[str, dict[str, Any]] = {}
        keys = set(CORE_FIELDS)
        if legacy.get("tipo") == "CT-e" or modular.get("tipo") == "CT-e":
            keys.update(CTE_FIELDS)

        for key in sorted(keys):
            legacy_raw = legacy.get(key)
            modular_raw = modular.get(key)
            legacy_normalized = normalize_value(key, legacy_raw)
            modular_normalized = normalize_value(key, modular_raw)
            if legacy_normalized != modular_normalized:
                differences[key] = {
                    "severity": _severity(key),
                    "legacy": legacy_raw,
                    "modular": modular_raw,
                    "legacy_normalized": legacy_normalized,
                    "modular_normalized": modular_normalized,
                }

        if legacy_error:
            differences["__erro_legado__"] = {
                "severity": "CRÍTICA",
                "legacy": legacy_error,
                "modular": modular_error,
                "legacy_normalized": _collapse(legacy_error).casefold(),
                "modular_normalized": _collapse(modular_error).casefold(),
            }
        if modular_error:
            differences["__erro_modular__"] = {
                "severity": "CRÍTICA",
                "legacy": legacy_error,
                "modular": modular_error,
                "legacy_normalized": _collapse(legacy_error).casefold(),
                "modular_normalized": _collapse(modular_error).casefold(),
            }

        has_critical = any(item.get("severity") == "CRÍTICA" for item in differences.values())
        status = "CRÍTICA" if has_critical else "INFORMATIVA" if differences else "IGUAL"
        result = ShadowComparison(
            path=str(path),
            equal=not differences,
            status=status,
            differences=differences,
            legacy_error=legacy_error,
            modular_error=modular_error,
            legacy_summary=_summary(legacy),
            modular_summary=_summary(modular),
        )
        self._notify(result)
        return result

    def build_audited_parser(self) -> Callable[[Path | str], dict[str, Any]]:
        legacy_parser = self.legacy_parser

        @wraps(legacy_parser)
        def audited(path: Path | str) -> dict[str, Any]:
            path_obj = Path(path)
            try:
                legacy_result = legacy_parser(path_obj)
            except Exception as exc:
                try:
                    self.compare_with_legacy(
                        path_obj,
                        {},
                        legacy_error=f"{type(exc).__name__}: {exc}",
                    )
                except Exception:
                    pass
                raise
            try:
                self.compare_with_legacy(path_obj, legacy_result)
            except Exception as exc:
                self._log(f"Falha isolada na auditoria de {path_obj}: {type(exc).__name__}: {exc}")
            return legacy_result

        audited.__name__ = getattr(legacy_parser, "__name__", "parse_xml")
        audited.__doc__ = getattr(legacy_parser, "__doc__", None)
        setattr(audited, "_central_cte_shadow_version", SHADOW_VERSION)
        setattr(audited, "_central_cte_legacy_parser", legacy_parser)
        return audited

    def _notify(self, result: ShadowComparison) -> None:
        if self.on_result is not None:
            try:
                self.on_result(result)
            except Exception as exc:
                self._log(f"Falha ao gravar auditoria: {type(exc).__name__}: {exc}")
        if not result.equal:
            self._log(json.dumps(result.to_dict(), ensure_ascii=False, default=str))

    def _log(self, text: str) -> None:
        if self.logger is None:
            return
        try:
            self.logger(str(text))
        except Exception:
            pass
