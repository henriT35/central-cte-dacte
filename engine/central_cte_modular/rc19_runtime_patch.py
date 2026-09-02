from __future__ import annotations

"""Instala as correções RC18 sem depender dos classificadores históricos."""

from dataclasses import replace
from typing import Any, MutableMapping

from .commercial.cte_classification import (
    buscar_sigla_como_token,
    detectar_cobranca_extra,
    explicar_classificacao,
    resolve_tipo_cte_oficial,
)
from .commercial.optional_components import (
    calcular_pedagio_jsp,
    calcular_pedagio_regra,
    validar_componente_opcional,
)
from .legacy_core.commercial_validation_compat import install_commercial_validation_compat
from .legacy_core.report_excel_compat import install_report_excel_compat
from .bootstrap.validation_bridge import install_validation_bridge

RC19_VERSION = "2.7.0 RC19 — Correção do Cálculo Compacto"


def _rule_pedagio_expected(namespace: Any, rule: dict[str, Any], info: dict[str, Any]):
    active = bool(rule.get("pedagio_ativo"))
    value = rule.get("valor_pedagio", 0.0) or rule.get("pedagio_valor", 0.0) or 0.0
    if not active or value <= 0:
        return 0.0, ""
    charged, _items = namespace.component_value(info, "PEDAGIO", "PEDÁGIO")
    if charged <= 0:
        return 0.0, "pedágio opcional não cobrado no XML"
    kind = namespace.norm_text(rule.get("tipo_pedagio", ""))
    fraction = rule.get("fracao_pedagio_kg", 0.0) or rule.get("pedagio_fracao_kg", 0.0) or 0.0
    if "CTE" in kind or "CONHECIMENTO" in kind or "EMISSAO" in kind:
        return value, "1 CT-e"
    if "KG" in kind or fraction > 0:
        weight, source = namespace.peso_base_kg_from_info(info)
        if weight <= 0:
            return 0.0, "PEDÁGIO SEM PESO"
        fraction = fraction or 100.0
        units = int((weight - 1e-9) // fraction) + 1
        return units * value, f"{units} fração(ões) de {fraction:g} kg ({source})"
    return value, "1 CT-e"



def _money_round(value: Any) -> float:
    """Arredonda valores monetários para centavos com critério financeiro."""

    from decimal import Decimal, ROUND_HALF_UP

    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))



def _refresh_percentage_trace(
    namespace: Any,
    result: dict[str, Any],
    trace: list[str],
    expected: float,
    difference: float,
    tolerance: float,
) -> None:
    """Mantém o diagnóstico textual com o mesmo arredondamento do resultado."""

    base = float(result.get("base_frete") or 0.0)
    percentage = float(result.get("percentual") or 0.0)
    for index, line in enumerate(trace):
        if line.startswith("Cálculo percentual:") and base > 0 and percentage > 0:
            trace[index] = (
                f"Cálculo percentual: R$ {namespace.money(base)} × "
                f"{namespace.fmt_percent(percentage)} = R$ {namespace.money(expected)}."
            )
        elif line.startswith("Valor esperado para comparação:"):
            trace[index] = (
                f"Valor esperado para comparação: R$ {namespace.money(expected)}. "
                f"Diferença: R$ {namespace.money(difference)}. "
                f"Tolerância: R$ {namespace.money(tolerance)}."
            )

def _repasse_rule_for_route(
    namespace: Any,
    rule: dict[str, Any],
    partner_id: str,
    city: str,
    state: str,
    tables: Any,
) -> tuple[str, str, dict[str, Any]]:
    """Localiza a anotação de repasse e preserva a regra que a originou."""

    selected = rule
    raw_value = str((selected.get("raw") or {}).get("REPASSE", "") or "").strip()
    if not raw_value:
        for table_rule in tables.get("rules", []) or []:
            if table_rule.get("partner_id") != partner_id:
                continue
            if table_rule.get("destino_cidade") != city or table_rule.get("destino_uf") != state:
                continue
            candidate = str((table_rule.get("raw") or {}).get("REPASSE", "") or "").strip()
            if candidate:
                selected = table_rule
                raw_value = candidate
                break
    return namespace.norm_text(raw_value), raw_value, selected


def _percentage_rate(namespace: Any, value: Any, *, require_percent_sign: bool = False) -> float:
    """Converte 0,015, 1,5 ou 1,5% em 0,015, recusando texto sem número."""

    import re

    if value in (None, "", False):
        return 0.0
    text = str(value).strip()
    if require_percent_sign and "%" not in text:
        return 0.0
    match = re.search(r"[-+]?\d+(?:[.,]\d+)?", text)
    if not match:
        return 0.0
    try:
        number = float(match.group(0).replace(",", "."))
    except Exception:
        return 0.0
    if number <= 0:
        return 0.0
    rate = number if number < 1 else number / 100.0
    return rate if 0 < rate < 1 else 0.0


def _explicit_repasse_rate(
    namespace: Any,
    rule: dict[str, Any],
    repasse_raw: str,
) -> tuple[float, str]:
    """Aceita gross-up somente quando a própria tabela informa percentual."""

    for key in (
        "percentual_repasse",
        "repasse_percentual",
        "aliquota_repasse",
        "percentual_imposto_gris",
    ):
        rate = _percentage_rate(namespace, rule.get(key))
        if rate:
            return rate, key

    raw = rule.get("raw") or {}
    for key in (
        "PERCENTUALREPASSE",
        "REPASSEPERCENTUAL",
        "ALIQUOTAREPASSE",
        "PERCENTUALIMPOSTOGRIS",
    ):
        rate = _percentage_rate(namespace, raw.get(key))
        if rate:
            return rate, key

    rate = _percentage_rate(namespace, repasse_raw, require_percent_sign=True)
    if rate:
        return rate, "REPASSE"
    return 0.0, ""

def _enrich_result(namespace: Any, result: dict[str, Any], info: dict[str, Any], base_data: Any, tables: Any) -> dict[str, Any]:
    trace = result.setdefault("trace", [])
    classification = explicar_classificacao(info)
    result.update({
        "tipo_fiscal_oficial": classification["tipo_fiscal"],
        "tipo_fiscal": classification["tipo_fiscal"],
        "codigo_tpcte": classification["codigo_tpcte"],
        "fonte_tipo_fiscal": classification["fonte_tipo_fiscal"],
        "gatilho_tipo_fiscal": classification["gatilho_tipo_fiscal"],
        "tipo_cobranca_extra": classification["tipo_extra"],
        "campo_tipo_extra": classification["campo_tipo_extra"],
        "gatilho_tipo_extra": classification["gatilho_tipo_extra"],
        "fonte_tipo_extra": classification["fonte_tipo_extra"],
        "fonte_classificacao": classification["fonte_tipo_extra"],
        "gatilho_classificacao": classification["gatilho_tipo_extra"],
        "explicacao_classificacao": classification["mensagem_extra"],
        "tipo_operacional_compat": classification["tipo_operacional"],
        "tipo_cobranca": classification["tipo_extra"],
    })
    trace.append(
        f"Tipo fiscal oficial: {classification['tipo_fiscal']} "
        f"({classification['gatilho_tipo_fiscal']}; fonte {classification['fonte_tipo_fiscal']})."
    )
    extra_detail = classification["mensagem_extra"]
    if classification["campo_tipo_extra"]:
        extra_detail += f"; campo {classification['campo_tipo_extra']}; gatilho {classification['gatilho_tipo_extra']}"
    trace.append(f"Cobrança extra: {extra_detail}.")

    charged_components: list[str] = []
    for component in info.get("componentes", []) or []:
        value = namespace.parse_number_br((component or {}).get("valor", ""))
        if value > 0:
            name = str((component or {}).get("nome", "") or "COMPONENTE").strip()
            charged_components.append(f"{name}: R$ {namespace.money(value)}")
    result["componentes_cobrados_xml"] = "; ".join(charged_components) or "NENHUM COMPONENTE POSITIVO"
    result["componentes_opcionais_ignorados"] = ""
    result["destino_comercial"] = ""
    result["regra_comercial"] = ""

    if not base_data or not tables:
        return result
    nfs = namespace.get_nfs_from_info(info)
    if not nfs:
        return result
    pid = result.get("partner_id") or namespace.identify_partner(info, tables)
    if not pid:
        return result
    policy = namespace.xml_validation_partner_policy(pid)
    actual_xml_value = namespace.parse_number_br(info.get("valor", ""))
    base_row = None
    for one_nf in nfs:
        row, _status, _candidates = namespace.find_base_by_nf(
            base_data,
            one_nf,
            info,
            preferred_type=(
                "COMPLEMENTAR"
                if classification["tipo_fiscal"] == "COMPLEMENTAR"
                and policy.get("aceitar_complementar_exato_base")
                else ""
            ),
            actual_value=actual_xml_value,
            tolerance=tables.get("tolerance", 1.0),
            allow_substitute=bool(policy.get("aceitar_substituto_com_vinculo_forte")),
            require_compatibility=len(nfs) > 1,
        )
        if row:
            base_row = row
            break
    if not base_row:
        return result

    city = str(base_row.get("destino_cidade", "") or "").strip()
    state = str(base_row.get("destino_uf", "") or "").strip()
    result["destino_comercial"] = f"{city}/{state}".strip("/")
    weight_kg, _weight_source = namespace.peso_base_kg_from_info(info)
    rule_base_row = dict(base_row)
    rule_base_row["peso_regra_kg"] = weight_kg
    rule = namespace.choose_partner_rule(pid, rule_base_row, tables)
    if not rule:
        return result
    rule_id = str(rule.get("regra_id", "") or "").strip()
    source = str(rule.get("source", "") or "").strip()
    region = str(rule.get("regiao", "") or "").strip()
    result["regra_comercial"] = " | ".join(part for part in (rule_id, source, region) if part)

    ignored: list[str] = []
    toll_actual, _toll_items = namespace.component_value(info, "PEDAGIO", "PEDÁGIO")
    gris_actual, _gris_items = namespace.component_value(info, "GRIS")
    repasse_text, repasse_raw, repasse_rule = _repasse_rule_for_route(
        namespace, rule, pid, city, state, tables
    )
    expected_core = float(result.get("esperado") or 0.0)
    actual_core = float(result.get("valor_comparado") or 0.0)
    tolerance = float(tables.get("tolerance", 1.0) or 1.0)
    repasse_rate, repasse_rate_source = _explicit_repasse_rate(
        namespace, repasse_rule, repasse_raw
    )

    # "IMPOSTO/GRIS" sem percentual é apenas uma observação comercial. O
    # valor cobrado no próprio XML não pode provar circularmente um gross-up.
    # O ajuste só é permitido quando a tabela informa uma alíquota numérica.
    if (
        pid == "JSP"
        and ("IMPOSTO" in repasse_text or "GRIS" in repasse_text)
        and classification["tipo_extra"] == "NORMAL"
        and toll_actual <= 0
        and gris_actual <= 0
        and repasse_rate > 0
        and str(result.get("status", "")).startswith("DIVERGENTE")
        and expected_core > 0
    ):
        pure_expected = _money_round(expected_core)
        pure_difference = _money_round(actual_core - pure_expected)
        _refresh_percentage_trace(
            namespace, result, trace, pure_expected, pure_difference, tolerance
        )
        embedded_repasse = _money_round(expected_core / (1.0 - repasse_rate))
        if abs(actual_core - embedded_repasse) <= tolerance:
            difference = _money_round(actual_core - embedded_repasse)
            prior_status = str(result.get("status", ""))
            result.update({
                "esperado": embedded_repasse,
                "diferenca": difference,
                "status": "OK FRETE MÍNIMO" if "FRETE MÍNIMO" in prior_status else "OK",
                "repasse_embutido_status": (
                    f"IMPOSTO/GRIS {namespace.fmt_percent(repasse_rate)} "
                    "CONFIRMADO POR ALÍQUOTA EXPLÍCITA"
                ),
                "repasse_embutido_esperado": embedded_repasse,
                "repasse_embutido_percentual": repasse_rate,
                "repasse_embutido_fonte": repasse_rate_source,
            })
            trace.append(
                f"Repasse IMPOSTO/GRIS com alíquota explícita ({repasse_rate_source}): "
                f"R$ {namespace.money(_money_round(expected_core))} ÷ "
                f"{namespace.fmt_percent(1.0 - repasse_rate)} = "
                f"R$ {namespace.money(embedded_repasse)}; FRETE VALOR XML "
                f"R$ {namespace.money(actual_core)}; diferença R$ {namespace.money(difference)}."
            )
    elif (
        pid == "JSP"
        and ("IMPOSTO" in repasse_text or "GRIS" in repasse_text)
        and classification["tipo_extra"] == "NORMAL"
        and toll_actual <= 0
        and gris_actual <= 0
        and repasse_rate <= 0
    ):
        expected_rounded = _money_round(expected_core)
        difference = _money_round(actual_core - expected_rounded)
        _refresh_percentage_trace(
            namespace, result, trace, expected_rounded, difference, tolerance
        )
        result.update({
            "esperado": expected_rounded,
            "diferenca": difference,
            "repasse_informativo_status": "IGNORADO SEM PERCENTUAL EXPLÍCITO",
            "repasse_informativo_texto": repasse_raw,
        })
        result.pop("repasse_embutido_status", None)
        result.pop("repasse_embutido_esperado", None)
        trace.append(
            "Repasse IMPOSTO/GRIS não incorporado ao valor esperado: a tabela "
            "não informa percentual numérico. Mantida a comparação contratual "
            f"de R$ {namespace.money(expected_rounded)} contra R$ "
            f"{namespace.money(actual_core)}, diferença R$ {namespace.money(difference)}."
        )
    if rule.get("pedagio_ativo") and toll_actual <= 0:
        ignored.append("PEDÁGIO")
    if rule.get("gris_ativo") and gris_actual <= 0:
        ignored.append("GRIS")
    result["componentes_opcionais_ignorados"] = "; ".join(ignored)

    weight, weight_source = namespace.peso_base_kg_from_info(info)
    toll_audit = calcular_pedagio_regra(
        rule,
        toll_actual,
        peso_kg=weight,
        tolerancia=tolerance,
    )
    result.update({
        "pedagio_componente_cobrado": toll_actual,
        "pedagio_componente_esperado": toll_audit.get("esperado", 0.0),
        "pedagio_componente_diferenca": toll_audit.get("diferenca", 0.0),
        "pedagio_componente_status": toll_audit.get("status", ""),
        "pedagio_componente_detalhe": toll_audit.get("detalhe", ""),
        "pedagio_componente_tipo": toll_audit.get("tipo", ""),
        "pedagio_componente_quantidade": toll_audit.get("quantidade", 0),
        "pedagio_componente_fracao_kg": toll_audit.get("fracao_kg", 0.0),
        "pedagio_componente_peso_kg": toll_audit.get("peso_kg", weight),
        "pedagio_componente_peso_fonte": weight_source,
        "pedagio_componente_revisar": bool(toll_audit.get("revisar")),
    })
    # Campos visuais comuns para que o bloco compacto e o relatório usem a
    # mesma conta efetivamente auditada, inclusive para Rodotec.
    result.setdefault("peso_base_kg", weight)
    result.setdefault("pedagio_qtd", toll_audit.get("quantidade", 0))
    result.setdefault("pedagio_valor", toll_audit.get("configurado", 0.0))
    result.setdefault("pedagio_fracao_kg", toll_audit.get("fracao_kg", 0.0))
    result.setdefault("pedagio_tipo", toll_audit.get("tipo", ""))
    trace.append(
        f"Auditoria separada do pedágio: XML R$ {namespace.money(toll_actual)}; "
        f"esperado quando cobrado R$ {namespace.money(toll_audit.get('esperado', 0.0))}; "
        f"{toll_audit.get('status', '')}; {toll_audit.get('detalhe', '')}."
    )
    if (
        pid == "JSP"
        and toll_actual > 0
        and str(toll_audit.get("status", "")).startswith("DIVERGENTE")
        and str(result.get("status", "")).startswith("OK")
    ):
        difference = float(toll_audit.get("diferenca", 0.0) or 0.0)
        result["status"] = "DIVERGENTE PEDÁGIO +" if difference > 0 else "DIVERGENTE PEDÁGIO -"
        result["diferenca"] = difference
        result["detalhe"] = (str(result.get("detalhe", "")) + "; pedágio JSP divergente").strip("; ")
    return result


def install_rc19_runtime(target_globals: MutableMapping[str, Any], bootstrap_state: Any) -> dict[str, Any]:
    """Instala as correções RC18 e reinstala a ponte de validação na ordem correta.

    Na RC18, a ponte de validação era criada antes de os fallbacks comerciais
    materializarem ``detect_partner_manual_extra``, ``rule_pedagio_expected`` e
    ``validate_rodotec_components_fallback``. A instalação falhava de forma
    silenciosa e o controle compacto nunca era aplicado. A RC19 carrega as
    dependências primeiro, publica o classificador corrigido e só então instala
    o orquestrador modular com os overlays de cálculo compacto/componentes.
    """

    namespace = bootstrap_state.compatibility_module
    services = bootstrap_state.services
    engine_namespace = services.resolve("engine_namespace")

    # Materializa os blocos legados mínimos antes de instalar a validação. Eles
    # continuam sendo apenas adaptadores de compatibilidade; o fluxo oficial
    # permanece no orquestrador modular.
    lazy_registry = getattr(namespace, "CENTRAL_CTE_LEGACY_LAZY_REGISTRY", None)
    if lazy_registry is not None:
        lazy_registry.ensure("commercial_validation", trigger="rc19_compact_startup")
        lazy_registry.ensure("report_excel", trigger="rc19_compact_startup")
    else:
        install_commercial_validation_compat(namespace.__dict__)
        install_report_excel_compat(namespace.__dict__)

    # Preserva a função legada pura para permitir reinstalação idempotente da
    # ponte. Sem isso, uma segunda instalação poderia envolver o próprio guard.
    raw_legacy_validate = engine_namespace.get("RC19_LEGACY_VALIDATE_CTE_VALUE")
    if not callable(raw_legacy_validate):
        raw_legacy_validate = engine_namespace.get("validate_cte_value")
        if not callable(raw_legacy_validate):
            raise RuntimeError("validate_cte_value legado não foi materializado")
        engine_namespace["RC19_LEGACY_VALIDATE_CTE_VALUE"] = raw_legacy_validate

    def detect_charge_type(info: dict[str, Any]) -> str:
        return explicar_classificacao(info)["tipo_operacional"]

    def rule_pedagio_expected(rule: dict[str, Any], info: dict[str, Any]):
        return _rule_pedagio_expected(namespace, rule, info)

    # Publica as correções RC18 antes de reinstalar o bridge, para que o novo
    # orquestrador capture as funções certas já na criação das dependências.
    namespace.buscar_sigla_como_token = buscar_sigla_como_token
    namespace.resolve_tipo_cte_oficial = resolve_tipo_cte_oficial
    namespace.detectar_cobranca_extra = detectar_cobranca_extra
    namespace.explicar_classificacao = explicar_classificacao
    namespace.detect_partner_charge_type = detect_charge_type
    namespace.rule_pedagio_expected = rule_pedagio_expected
    namespace.validar_componente_opcional = validar_componente_opcional
    namespace.calcular_pedagio_jsp = calcular_pedagio_jsp
    namespace.calcular_pedagio_regra = calcular_pedagio_regra

    engine_namespace["MODULAR_COMMERCIAL_DETECT_PARTNER_CHARGE_TYPE"] = detect_charge_type
    engine_namespace["detect_partner_charge_type"] = detect_charge_type
    engine_namespace["rule_pedagio_expected"] = rule_pedagio_expected
    engine_namespace["buscar_sigla_como_token"] = buscar_sigla_como_token
    engine_namespace["resolve_tipo_cte_oficial"] = resolve_tipo_cte_oficial
    engine_namespace["detectar_cobranca_extra"] = detectar_cobranca_extra
    engine_namespace["explicar_classificacao"] = explicar_classificacao
    engine_namespace["validar_componente_opcional"] = validar_componente_opcional
    engine_namespace["calcular_pedagio_jsp"] = calcular_pedagio_jsp
    engine_namespace["calcular_pedagio_regra"] = calcular_pedagio_regra

    # Restaura a função-base e instala novamente a ponte. O uso do
    # EngineNamespace é obrigatório porque várias dependências comerciais estão
    # no RuntimeRegistry, e não no __dict__ do módulo de compatibilidade.
    engine_namespace["validate_cte_value"] = raw_legacy_validate
    validation_state = install_validation_bridge(engine_namespace, services)
    if not validation_state.get("active"):
        reason = validation_state.get("reason", "motivo não informado")
        raise RuntimeError(f"ponte de validação RC19 não pôde ser ativada: {reason}")

    try:
        engine_namespace.register_state("MODULAR_VALIDATION_STATE", validation_state, publish=True)
    except Exception:
        bootstrap_state.runtime.register_state("MODULAR_VALIDATION_STATE", validation_state)
        namespace.MODULAR_VALIDATION_STATE = validation_state

    orchestrator = engine_namespace.get("MODULAR_CTE_VALUE_ORCHESTRATOR")
    if orchestrator is not None and hasattr(orchestrator, "d"):
        orchestrator.d = replace(
            orchestrator.d,
            detect_partner_charge_type=detect_charge_type,
            rule_pedagio_expected=rule_pedagio_expected,
        )

    guarded_validate = engine_namespace.get("validate_cte_value")
    if not callable(guarded_validate):
        raise RuntimeError("guard modular de validação não foi publicado")

    def validate_cte_value(info: dict[str, Any], base_data: Any, tables: Any):
        validated = guarded_validate(info, base_data, tables)
        return _enrich_result(namespace, validated, info, base_data, tables)

    engine_namespace["validate_cte_value"] = validate_cte_value
    namespace.validate_cte_value = validate_cte_value
    namespace.APP_VERSION = RC19_VERSION

    compact_control = engine_namespace.get("MODULAR_COMPACT_CONTROL")
    component_control = engine_namespace.get("MODULAR_COMPONENT_CALCULATION")
    validation_guard = engine_namespace.get("MODULAR_VALIDATION_GUARD")
    if compact_control is None or component_control is None or validation_guard is None:
        raise RuntimeError(
            "ponte ativa, mas serviços de controle compacto/componentes não foram registrados"
        )

    target_globals.update({
        "APP_VERSION": RC19_VERSION,
        "validate_cte_value": validate_cte_value,
        "detect_partner_charge_type": detect_charge_type,
        "buscar_sigla_como_token": buscar_sigla_como_token,
        "resolve_tipo_cte_oficial": resolve_tipo_cte_oficial,
        "detectar_cobranca_extra": detectar_cobranca_extra,
        "explicar_classificacao": explicar_classificacao,
        "validar_componente_opcional": validar_componente_opcional,
        "calcular_pedagio_jsp": calcular_pedagio_jsp,
        "calcular_pedagio_regra": calcular_pedagio_regra,
        "MODULAR_VALIDATION_STATE": validation_state,
        "MODULAR_COMPACT_CONTROL": compact_control,
        "MODULAR_COMPONENT_CALCULATION": component_control,
        "MODULAR_VALIDATION_GUARD": validation_guard,
        "RC19_RUNTIME_PATCH": True,
    })

    return {
        "version": RC19_VERSION,
        "active": True,
        "classification": "tpCTe oficial + extra em campos confiáveis",
        "optional_components": "ausentes não entram no valor esperado",
        "validation_bridge_reinstalled": True,
        "validation_bridge_active": True,
        "compact_control_active": True,
        "component_control_active": True,
        "validation_state": dict(validation_state),
    }


__all__ = ["RC19_VERSION", "install_rc19_runtime"]
