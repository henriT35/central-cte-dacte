# -*- coding: utf-8 -*-
from __future__ import annotations

"""Correções de publicação do relatório XML exclusivas da camada web.

O motor RC26.6 e seus hashes permanecem congelados. Este módulo trabalha
somente sobre a fotografia oficial já calculada: completa campos de exibição,
trata R$ 0,01 como sentinela na rentabilidade gerencial e esclarece no painel
a diferença entre volume sob atenção e divergência financeira apurada.
"""

from html import escape
import os
from pathlib import Path
from typing import Any, Iterable, Mapping
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile


PROFITABILITY_SENTINEL_MAX = 0.01


def _number(value: Any) -> float | None:
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
    except (TypeError, ValueError):
        return None


def publish_extra_comparison_fields(
    validation: Mapping[str, Any],
    info: Mapping[str, Any],
) -> dict[str, Any]:
    """Publica campos de comparação já implícitos no status oficial de extra.

    A função não escolhe regra, não calcula valor esperado e não altera status.
    Ela apenas usa o valor total do XML e o esperado já devolvido pelo motor para
    impedir diferença vazia/R$ 0,00 em ``OK/DIVERGENTE EXTRA``.
    """

    result = dict(validation)
    status = str(result.get("status") or "").upper()
    if "EXTRA" not in status:
        return result

    actual = _number(result.get("valor_comparado"))
    if actual is None:
        actual = _number(result.get("valor_total_xml"))
    if actual is None:
        actual = _number(info.get("valor"))
    expected = _number(result.get("esperado"))

    if actual is not None:
        if result.get("valor_total_xml") in (None, ""):
            result["valor_total_xml"] = actual
        if result.get("valor_comparado") in (None, ""):
            result["valor_comparado"] = actual
        if not str(result.get("componente_comparado") or "").strip():
            result["componente_comparado"] = "VALOR TOTAL XML — COBRANÇA EXTRA"
        result["comparacao_fallback_total"] = False

    if actual is not None and expected is not None and result.get("diferenca") in (None, ""):
        result["diferenca"] = round(actual - expected, 2)

    trace = list(result.get("trace") or [])
    if actual is not None and expected is not None:
        note = (
            "Publicação web da cobrança extra: valor total XML "
            f"R$ {actual:.2f}; valor esperado oficial R$ {expected:.2f}; "
            f"diferença R$ {round(actual - expected, 2):.2f}."
        )
        if note not in trace:
            trace.append(note)
    result["trace"] = trace
    return result


def prepare_report_files(files: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for item in files:
        info = dict(item)
        validation = info.get("validacao")
        if isinstance(validation, Mapping):
            info["validacao"] = publish_extra_comparison_fields(validation, info)
        prepared.append(info)
    return prepared


def _formula_value(report_module: Any, value: Any) -> Any:
    helper = getattr(report_module, "formula_value", None)
    if callable(helper):
        return helper(value)
    return getattr(value, "cached", value)


def _detail_number(report_module: Any, value: Any) -> float:
    parsed = _number(_formula_value(report_module, value))
    return float(parsed or 0.0)


def correct_report_model(report_module: Any, model: Any) -> Any:
    """Corrige somente a camada gerencial do modelo oficial já consolidado."""

    detail_headers = list(getattr(report_module, "DETAIL_HEADERS"))
    audit_headers = list(getattr(report_module, "AUDIT_HEADERS"))
    Formula = getattr(report_module, "Formula")

    ci_partner = detail_headers.index("Parceiro")
    ci_status = detail_headers.index("Status")
    ci_difference = detail_headers.index("Diferença")
    ci_base = detail_headers.index("Frete Base / Receita")
    ci_cost = detail_headers.index("Frete Cobrado pelo Parceiro")
    ci_profit = detail_headers.index("Lucro Bruto Estimado")
    ci_margin = detail_headers.index("Margem Bruta Estimada")
    ci_class = detail_headers.index("Classificação da Margem")

    ai_base = audit_headers.index("Frete Base")
    ai_base_source = audit_headers.index("Fonte do Frete Base / Receita")
    ai_profit = audit_headers.index("Lucro Bruto Estimado")
    ai_margin = audit_headers.index("Margem Bruta Estimada")
    ai_class = audit_headers.index("Classificação da Margem")
    ai_memory = audit_headers.index("Memória da Rentabilidade")

    valid_base_count = 0
    total_base = 0.0
    total_profit = 0.0

    for offset, row in enumerate(list(model.detail_rows)):
        excel_row = 6 + offset
        raw_base = _detail_number(report_module, row[ci_base])
        sentinel = 0.0 < raw_base <= PROFITABILITY_SENTINEL_MAX
        cost = _detail_number(report_module, row[ci_cost])
        cost_present = _formula_value(report_module, row[ci_cost]) not in (None, "")

        if sentinel:
            row[ci_base] = ""
            cached_profit: Any = ""
            cached_margin: Any = ""
            cached_class = "SEM FRETE BASE" if cost_present else "SEM DADOS"

            if offset < len(model.audit_rows):
                audit = model.audit_rows[offset]
                audit[ai_base_source] = "NÃO UTILIZADO — VALOR SENTINELA R$ 0,01"
                audit[ai_profit] = ""
                audit[ai_margin] = ""
                audit[ai_class] = cached_class
                audit[ai_memory] = (
                    "Frete base sentinela R$ 0,01; tratado como não informado; "
                    f"custo do parceiro R$ {cost:.2f}; classe {cached_class}."
                )
        else:
            cached_profit = _formula_value(report_module, row[ci_profit])
            cached_margin = _formula_value(report_module, row[ci_margin])
            cached_class = str(_formula_value(report_module, row[ci_class]) or "")
            if raw_base > PROFITABILITY_SENTINEL_MAX:
                valid_base_count += 1
                total_base += raw_base
                total_profit += float(_number(cached_profit) or 0.0)

        row[ci_profit] = Formula(
            f'IF(OR($U{excel_row}="",$U{excel_row}<=\'PAINEL\'!$T$81,$V{excel_row}=""),"",$U{excel_row}-$V{excel_row})',
            cached_profit,
        )
        row[ci_margin] = Formula(
            f'IF(OR($U{excel_row}="",$U{excel_row}<=\'PAINEL\'!$T$81,$W{excel_row}=""),"",$W{excel_row}/$U{excel_row})',
            cached_margin,
        )
        row[ci_class] = Formula(
            f'IF($V{excel_row}="","SEM DADOS",IF(OR($U{excel_row}="",$U{excel_row}<=\'PAINEL\'!$T$81),"SEM FRETE BASE",IF($X{excel_row}<0,"MARGEM NEGATIVA",IF($X{excel_row}<\'PAINEL\'!$T$79,"MARGEM BAIXA",IF($X{excel_row}<\'PAINEL\'!$T$80,"MARGEM SAUDÁVEL","MARGEM ALTA")))))',
            cached_class,
        )

    metrics = dict(getattr(model, "metrics", {}) or {})
    metrics["total_base"] = round(total_base, 2)
    metrics["total_profit"] = round(total_profit, 2)
    metrics["overall_margin"] = total_profit / total_base if total_base > 0.0 else 0.0
    metrics["base_count"] = valid_base_count
    model.metrics = metrics

    for summary in list(getattr(model, "partner_summary", []) or []):
        partner = str(summary.get("partner") or "")
        matching = [
            row for row in model.detail_rows
            if str(_formula_value(report_module, row[ci_partner]) or "") == partner
        ]
        base = round(sum(_detail_number(report_module, row[ci_base]) for row in matching), 2)
        profit = round(sum(_detail_number(report_module, row[ci_profit]) for row in matching), 2)
        summary["freight_base"] = base
        summary["gross_profit"] = profit
        summary["base_count"] = sum(
            _detail_number(report_module, row[ci_base]) > PROFITABILITY_SENTINEL_MAX
            for row in matching
        )
        summary["margin"] = profit / base if base > 0.0 else None
        summary["margin_class"] = (
            "SEM FRETE BASE" if base <= 0.0
            else "MARGEM NEGATIVA" if summary["margin"] < 0.0
            else "MARGEM BAIXA" if summary["margin"] < 0.10
            else "MARGEM SAUDÁVEL" if summary["margin"] < 0.25
            else "MARGEM ALTA"
        )

    # Mantém os campos usados pelo patch OpenXML acessíveis sem recalcular regra.
    model._web_difference_column = ci_difference
    model._web_status_column = ci_status
    return model


def _column_name(index: int) -> str:
    index += 1
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Relatório XML web: estrutura inesperada em {label}; ocorrências={count}.")
    return text.replace(old, new, 1)


def patch_report_xlsx(path: Path, report_module: Any, model: Any) -> None:
    """Atualiza apenas o painel do XLSX oficial, preservando tabelas e gráficos."""

    path = Path(path)
    detail_headers = list(getattr(report_module, "DETAIL_HEADERS"))
    ci_status = detail_headers.index("Status")
    ci_difference = detail_headers.index("Diferença")
    status_letter = _column_name(ci_status)
    difference_letter = _column_name(ci_difference)
    detail_end = max(6, 5 + len(model.detail_rows))

    divergent_value = round(sum(
        abs(_detail_number(report_module, row[ci_difference]))
        for row in model.detail_rows
        if "DIVERGENTE" in str(_formula_value(report_module, row[ci_status]) or "").upper()
    ), 2)

    with ZipFile(path, "r") as source:
        entries = {name: source.read(name) for name in source.namelist()}

    panel = entries["xl/worksheets/sheet1.xml"].decode("utf-8")
    panel = _replace_once(
        panel,
        "<t>Valor sob atenção</t>",
        "<t>Volume financeiro sob atenção</t>",
        label="rótulo do volume sob atenção",
    )

    old_note = (
        '<row r="20" ht="30" customHeight="1"><c r="A20" t="inlineStr" s="21"><is><t>'
        'A rentabilidade é gerencial e não altera o status comercial; itens SEM FRETE BASE ficam fora do lucro e da margem, sem serem tratados como prejuízo.'
        '</t></is></c>'
    )
    new_note_text = (
        "Volume sob atenção é o total dos CT-es não aprovados e não representa prejuízo. "
        "Divergência apurada soma somente diferenças dos status DIVERGENTE. "
        "Rentabilidade é gerencial; frete base até R$ 0,01 é tratado como SEM FRETE BASE."
    )
    new_note = (
        '<row r="20" ht="34" customHeight="1"><c r="A20" t="inlineStr" s="21"><is><t>'
        + escape(new_note_text)
        + '</t></is></c>'
    )
    panel = _replace_once(panel, old_note, new_note, label="nota explicativa do painel")

    panel = _replace_once(
        panel,
        '<c r="P15"/>',
        '<c r="P15" t="inlineStr" s="3"><is><t>Divergência financeira apurada</t></is></c>',
        label="cartão de divergência",
    )
    formula = (
        f'SUMPRODUCT(--ISNUMBER(SEARCH(&quot;DIVERGENTE&quot;,\'DETALHAMENTO\'!${status_letter}$6:${status_letter}${detail_end})),'
        f'ABS(\'DETALHAMENTO\'!${difference_letter}$6:${difference_letter}${detail_end}))'
    )
    panel = _replace_once(
        panel,
        '<c r="P17"/>',
        f'<c r="P17" s="8"><f>{formula}</f><v>{divergent_value}</v></c>',
        label="valor do cartão de divergência",
    )

    old_row81 = (
        '<row r="81" ht="8" customHeight="1">'
        + ''.join(f'<c r="{column}81"/>' for column in "ABCDEFGHIJKLMNOPQRST")
        + '</row>'
    )
    new_row81 = (
        '<row r="81" ht="24" customHeight="1">'
        + ''.join(f'<c r="{column}81"/>' for column in "ABCDEFGHIJKLMNOPQR")
        + '<c r="S81" t="inlineStr" s="33"><is><t>Frete base sentinela até</t></is></c>'
        + '<c r="T81" s="31"><v>0.01</v></c></row>'
    )
    panel = _replace_once(panel, old_row81, new_row81, label="parâmetro sentinela")

    panel = _replace_once(
        panel,
        '<mergeCells count="28">',
        '<mergeCells count="30">',
        label="quantidade de mesclagens",
    )
    panel = _replace_once(
        panel,
        '<mergeCell ref="K17:O18"/><mergeCell ref="A20:T20"/>',
        '<mergeCell ref="K17:O18"/><mergeCell ref="P15:T16"/><mergeCell ref="P17:T18"/><mergeCell ref="A20:T20"/>',
        label="mesclagens do cartão de divergência",
    )
    panel = _replace_once(
        panel,
        '<mergeCell ref="A79:R80"/>',
        '<mergeCell ref="A79:R81"/>',
        label="mesclagem dos parâmetros",
    )
    ElementTree.fromstring(panel.encode("utf-8"))
    entries["xl/worksheets/sheet1.xml"] = panel.encode("utf-8")

    temporary = path.with_suffix(path.suffix + ".webpatch.tmp")
    try:
        temporary.unlink(missing_ok=True)
    except Exception:
        pass
    with ZipFile(temporary, "w", ZIP_DEFLATED, compresslevel=6) as target:
        for name, data in entries.items():
            target.writestr(name, data)
    with ZipFile(temporary, "r") as check:
        if check.testzip() is not None:
            raise RuntimeError("Relatório XML web ficou com uma entrada ZIP inválida após o patch.")
        ElementTree.fromstring(check.read("xl/worksheets/sheet1.xml"))
        ElementTree.fromstring(check.read("xl/worksheets/sheet3.xml"))
    os.replace(temporary, path)


__all__ = [
    "PROFITABILITY_SENTINEL_MAX",
    "correct_report_model",
    "patch_report_xlsx",
    "prepare_report_files",
    "publish_extra_comparison_fields",
]
