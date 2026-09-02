from __future__ import annotations

"""Modelo canônico do relatório dinâmico de faturas RC26.6.

O módulo não relê PDF, XML, base Rodovitor ou tabela comercial. Ele recebe a
fotografia já decidida pelo motor e apenas expõe, de forma auditável, a natureza
financeira e a rentabilidade de cada CT-e. As fórmulas do XLSX consultam a
classe de bloqueio canônica antes de considerar a edição do comprovante.
"""

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..invoices.normalization import normalize_space, normalize_status, parse_money, stable_hash
from .xlsx_openxml import Formula, formula_value

SheetSpec = tuple[str, list[list[Any]], list[float]]

STATUS_OK = "OK PARA PAGAMENTO"
STATUS_FUTURE = "PAGAMENTO FUTURO"
STATUS_REVIEW = "PROBLEMA INTERNO / CONFERÊNCIA"
STATUS_EXCLUDED = "NÃO CONTABILIZADO"

FATURAS_HEADERS = (
    "Número da Fatura", "Parceiro", "CT-es Importados", "CT-es na Composição Financeira",
    "CT-es Liberados Agora", "CT-es para Pagamento Futuro", "CT-es com Problema Interno",
    "CT-es em Conferência Histórica", "CT-es Não Contabilizados",
    "Valor Total Financeiro da Fatura", "Valor a Pagar Agora",
    "Valor para Pagamento Futuro", "Valor Retido por Problema Interno",
    "Valor em Conferência Histórica", "Percentual Liberado",
    "Status de Pagamento Atual da Fatura", "Principais Pendências Atuais",
    "Ação Financeira Atual", "Consistência Financeira e Contábil",
    "Frete Base Total", "Custo Total do Parceiro", "Lucro Bruto Estimado",
    "Margem Bruta Estimada", "Rentabilidade",
)

ATTENTION_HEADERS = (
    "Fatura", "Parceiro", "CT-e", "NF", "Frete Cobrado pelo Parceiro",
    "Valor para Pagamento Futuro", "Valor Retido por Problema Interno",
    "Valor Histórico em Conferência", "Status Operacional Atual",
    "Tipo da Pendência", "Motivo Operacional Atual", "Ação Recomendada Atual",
    "Comprovante", "Mensagem Operacional",
)

# Os campos operacionais atuais são a fonte de verdade de pagamento. Os campos
# marcados como originais são apenas trilha histórica e ficam ocultos por padrão
# na visão CT_ES, permanecendo integralmente disponíveis na auditoria técnica.
CTE_HEADERS = (
    "Fatura", "Parceiro", "CT-e", "NF", "Frete Cobrado pelo Parceiro",
    "Frete Base / Receita", "Diferença da Validação",
    "Auditoria de Valor Original (histórico)", "Comprovante",
    "Código de Decisão Canônico Original", "Status Canônico Original (histórico)",
    "Classe Financeira Canônica Original", "Status Operacional Atual",
    "Valor para Pagamento Futuro", "Valor Retido por Problema Interno",
    "Valor Histórico em Conferência", "Valor Liberado Agora",
    "Consistência da Partição Financeira Atual", "Motivo Operacional Atual",
    "Ação Recomendada Atual", "Confiança Original", "Avisos Originais",
    "Lucro Bruto Estimado", "Margem Bruta Estimada", "Classificação da Margem",
    "Índice Dinâmico de Atenção",
)

# As primeiras 64 colunas preservam a fotografia técnica da decisão original.
# As colunas finais são fórmulas vivas ligadas à CT_ES e refletem qualquer edição
# válida do comprovante, frete-base ou custo no Excel.
def _invoice_status_formula(row: int) -> str:
    """Status atual da fatura: comprovante S paga, demais vão ao futuro.

    Somente problemas internos retêm valores. A coluna N é uma trilha histórica
    oculta e não recebe valores no fluxo RC26.6.
    """
    return (
        f'IF(OR($S{row}<>"COERENTE",$J{row}<=0),"{STATUS_REVIEW}",'
        f'IF(SUM($M{row}:$N{row})>0.005,"{STATUS_REVIEW}",'
        f'IF($L{row}>0.005,"{STATUS_FUTURE}","{STATUS_OK}")))'
    )

def _invoice_action_formula(row: int) -> str:
    return (
        f'IF($S{row}<>"COERENTE","Corrigir a inconsistência interna antes de liberar valores.",'
        f'IF($J{row}<=0,"Conferir a composição financeira da fatura.",'
        f'IF(ABS($K{row}-$J{row})<=0.01,"Liberar pagamento integral.",'
        f'IF(AND($K{row}>0,$L{row}>0,SUM($M{row}:$N{row})<=0.005),'
        f'"Liberar o valor atual e manter o saldo para pagamento futuro.",'
        f'IF(AND($K{row}<=0.005,$L{row}>0,SUM($M{row}:$N{row})<=0.005),'
        f'"Manter integralmente para pagamento futuro e solicitar os comprovantes.",'
        f'IF(AND($K{row}>0,SUM($M{row}:$N{row})>0),'
        f'"Liberar somente o valor apto e conferir os itens com problema interno.",'
        f'"Conferir os itens com problema interno antes de nova análise."))))))'
    )

AUDIT_HEADERS = (
    "Fatura", "Parceiro", "Seq.", "Arquivo PDF", "CT-e PDF",
    "NF PDF Original", "NF Utilizada", "Origem NF", "Valor CT-e",
    "Peso Fatura", "Frete CTRC Origem Fatura", "Comissão Fatura",
    "Chave Fatura", "CTRC Origem PDF", "Método de Busca", "CT-e Base",
    "CTRC Base", "NF Base", "Confirmação NF", "Fatura Base Exp",
    "Fatura Base Rec", "Vínculo da Fatura", "Origem Rota",
    "Destino Rota Base", "Destino Comercial Tabela", "Fonte Destino Tabela",
    "Aviso Rota", "Tipo Documento", "DY Original", "Valor Base/Comissão",
    "Parceiro Tabela ID", "Regra Tabela ID", "Fonte Regra",
    "Base Cálculo Tabela", "Fonte Base Tabela", "Percentual Tabela",
    "Mínimo Tabela", "Valor Esperado Tabela", "Diferença Tabela",
    "Tolerância Tabela", "Status Tabela Parceiro", "Peso Usado Tabela",
    "Fonte Peso Tabela", "Modo Tabela", "Caminho Cálculo Tabela",
    "Valor XML", "Diferença XML", "Status Valor", "Origem Validação Valor",
    "Confiança Valor", "Vínculo Validação Valor", "Regra Aplicada",
    "Status Valor Legado", "Status Final Original", "Motivo Final Original",
    "Caminho do Status Original", "Avisos Originais",
    "Código de Decisão Canônico Original", "Fonte do Frete Base",
    "Fonte do Frete Cobrado", "Código de Bloqueio Canônico Original",
    "Natureza Financeira Inicial (fotografia)", "Memória da Rentabilidade Inicial",
    "Consistência Financeira Inicial",
    "Comprovante Atual", "Status Operacional Atual", "Valor a Pagar Agora Atual",
    "Valor para Pagamento Futuro Atual", "Valor Retido por Problema Interno Atual",
    "Reserva Técnica Legada Atual", "Motivo Operacional Atual",
    "Ação Recomendada Atual", "Consistência Financeira Atual",
    "Memória da Rentabilidade Atual",
)


@dataclass(frozen=True)
class InvoiceReportBuildResult:
    version: str
    sheets: list[SheetSpec]
    invoice_count: int
    item_count: int
    problem_item_count: int
    total_value: float
    payable_value: float
    future_value: float
    blocked_value: float
    fingerprint: str
    partner_count: int = 0
    consistency_issue_count: int = 0
    audit_column_count: int = len(AUDIT_HEADERS)

    def to_dict(self, *, include_sheets: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": self.version,
            "invoice_count": self.invoice_count,
            "item_count": self.item_count,
            "problem_item_count": self.problem_item_count,
            "partner_count": self.partner_count,
            "consistency_issue_count": self.consistency_issue_count,
            "audit_column_count": self.audit_column_count,
            "total_value": self.total_value,
            "payable_value": self.payable_value,
            "future_value": self.future_value,
            "blocked_value": self.blocked_value,
            "sheet_count": len(self.sheets),
            "sheet_names": [sheet[0] for sheet in self.sheets],
            "fingerprint": self.fingerprint,
        }
        if include_sheets:
            payload["sheets"] = self.sheets
        return payload


@dataclass(frozen=True)
class _CanonicalItem:
    record: Mapping[str, Any]
    invoice: str
    partner: str
    cte: str
    nf: str
    billed: float
    billed_present: bool
    billed_source: str
    freight_base: float | None
    base_source: str
    validation_difference: float
    value_status: str
    proof: str
    decision_code: str
    original_status: str
    block_class: str
    financial_status: str
    future_value: float
    blocked_value: float
    released_value: float
    reason: str
    action: str
    confidence: str
    warnings: str
    gross_profit: float | None
    margin: float | None
    margin_class: str
    consistency: str


def _money(value: Any) -> str:
    return "R$ " + f"{parse_money(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _first(record: Mapping[str, Any], *keys: str, default: Any = "-") -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def _first_present(record: Mapping[str, Any], keys: Sequence[str]) -> tuple[Any, str, bool]:
    for key in keys:
        if key in record and record.get(key) not in (None, ""):
            return record.get(key), key, True
    return None, "NÃO INFORMADO", False


def _historical_display(value: Any) -> str:
    """Mantém termos antigos restritos à AUDITORIA_TÉCNICA."""

    text = normalize_space(value or "")
    normalized = normalize_status(text)
    if any(token in normalized for token in (
        "NAO PAGAR", "NÃO PAGAR", "BLOQUEADO", "BLOQUEIO DEFINITIVO",
    )):
        return "CONSULTAR AUDITORIA TÉCNICA (HISTÓRICO)"
    return text


def _counted(record: Mapping[str, Any]) -> bool:
    value = record.get("Financeiro contabilizado", True)
    if isinstance(value, str):
        return normalize_status(value) not in {"N", "NAO", "NÃO", "FALSE", "0"}
    return bool(value)


def _decision_code(record: Mapping[str, Any]) -> str:
    raw = normalize_status(record.get("Código decisão") or record.get("Código decisão modular") or "")
    token = raw.replace(" ", "_")
    if token:
        return token
    status = normalize_status(record.get("Status final CT-e") or record.get("Status CT-e") or "")
    if status in {"OK", "OK_COMPLEMENTAR", "OK COMPLEMENTAR"}:
        return status.replace(" ", "_")
    if "SEM COMPROVANTE" in status:
        return "SEM_COMPROVANTE"
    if "FORA DA BASE" in status:
        return "FORA_DA_BASE"
    return "SEM_CODIGO"


def _proof(record: Mapping[str, Any], code: str) -> str:
    raw = normalize_status(record.get("DY") or record.get("Comprovante") or "")
    if code == "OK_COMPLEMENTAR" or "NAO EXIG" in raw or "NÃO EXIG" in raw:
        return "-"
    if raw == "S" or "COMPROVANTE OK" in raw or "DY=S" in raw:
        return "S"
    if raw == "N" or "SEM COMPROVANTE" in raw or "DY=N" in raw:
        return "N"
    if code == "SEM_COMPROVANTE":
        return "N"
    # Nunca deduz S a partir do status original. Ausente ou '-' significa que
    # o comprovante não está OK e, portanto, segue para pagamento futuro.
    return "-"


def _block_class(record: Mapping[str, Any], code: str) -> str:
    if not _counted(record):
        return "NÃO CONTABILIZADO"
    if code == "OK_COMPLEMENTAR":
        return "LIBERADO SEM COMPROVANTE"
    if code in {"OK", "SEM_COMPROVANTE", "FORA_DA_BASE"}:
        # A ausência na Base Rodovitor permanece na auditoria, mas não é um
        # bloqueio financeiro. O comprovante atual é a fonte de verdade.
        return "CONTROLADO POR COMPROVANTE"
    # Base ambígua, base não carregada e falhas estruturais continuam exigindo
    # conferência. Nenhum parceiro é bloqueado apenas por cadastro ou tabela.
    return "CONFERIR"

def _financial_status(block_class: str, proof: str) -> str:
    if block_class == STATUS_EXCLUDED:
        return STATUS_EXCLUDED
    if block_class == "LIBERADO SEM COMPROVANTE":
        return STATUS_OK
    if block_class in {"CONFERIR", "BLOQUEIO DEFINITIVO"}:
        return STATUS_REVIEW
    # Regra simples: comprovante S paga agora; N, vazio ou '-' vai para futuro.
    return STATUS_OK if proof == "S" else STATUS_FUTURE

def _freight_base(record: Mapping[str, Any]) -> tuple[float | None, str]:
    priorities = (
        "Frete CTRC Origem fatura", "Frete Base / Receita", "Frete base / receita",
        "Frete Base", "Frete base", "Receita", "Valor frete base", "Valor base",
    )
    for key in priorities:
        if key not in record or record.get(key) in (None, ""):
            continue
        value = parse_money(record.get(key))
        if value > 0.0:
            suffix = " (fallback técnico)" if key == "Valor base" else ""
            declared_source = normalize_space(record.get("Fonte frete base") or "")
            source = declared_source if key == "Frete CTRC Origem fatura" and declared_source else key
            return round(value, 2), source + suffix
    return None, "NÃO INFORMADO / ZERO"


def _margin_class(base: float | None, cost_present: bool, margin: float | None, low: float = 0.10, high: float = 0.25) -> str:
    if not cost_present:
        return "SEM DADOS"
    if base is None or base <= 0.0 or margin is None:
        return "SEM FRETE BASE"
    if margin < 0.0:
        return "MARGEM NEGATIVA"
    if margin < low:
        return "MARGEM BAIXA"
    if margin < high:
        return "MARGEM SAUDÁVEL"
    return "MARGEM ALTA"


def _canonical_item(record: Mapping[str, Any]) -> _CanonicalItem:
    billed_raw, billed_source, billed_present = _first_present(
        record, ("Valor fatura", "Frete Cobrado pelo Parceiro", "Valor CT-e", "valor")
    )
    billed = round(parse_money(billed_raw), 2)
    base, base_source = _freight_base(record)
    code = _decision_code(record)
    proof = _proof(record, code)
    block_class = _block_class(record, code)
    status = _financial_status(block_class, proof)
    amount = billed if _counted(record) else 0.0
    future = amount if status == STATUS_FUTURE else 0.0
    released = amount if status == STATUS_OK else 0.0
    blocked = amount if status == STATUS_REVIEW else 0.0
    consistency = "OK" if abs(amount - released - future - blocked) <= 0.01 else "INCONSISTENTE"
    profit = round(base - billed, 2) if base is not None and billed_present else None
    margin = (profit / base) if profit is not None and base and base > 0.0 else None
    original = normalize_space(record.get("Status final CT-e") or record.get("Status CT-e") or "REVISAR")
    return _CanonicalItem(
        record=record,
        invoice=str(record.get("Fatura") or "-"),
        partner=str(record.get("Parceiro") or "Parceiro não identificado"),
        cte=str(_first(record, "CT-e fatura", "CT-e", default="-")),
        nf=str(_first(record, "NF fatura", "NF", default="-")),
        billed=billed,
        billed_present=billed_present,
        billed_source=billed_source,
        freight_base=base,
        base_source=base_source,
        validation_difference=round(parse_money(record.get("Diferença tabela") or record.get("Diferença XML")), 2),
        value_status=str(record.get("Status valor") or "-"),
        proof=proof,
        decision_code=code,
        original_status=original,
        block_class=block_class,
        financial_status=status,
        future_value=round(future, 2),
        blocked_value=round(blocked, 2),
        released_value=round(released, 2),
        reason=str(record.get("Motivo") or "-"),
        action=str(record.get("Ação recomendada") or ("Liberar pagamento." if status == STATUS_OK else "Conferir antes de liberar.")),
        confidence=str(record.get("Confiança validação valor") or record.get("Confiança") or "-"),
        warnings=str(record.get("Avisos auditoria") or record.get("Avisos") or "-"),
        gross_profit=profit,
        margin=margin,
        margin_class=_margin_class(base, billed_present, margin),
        consistency=consistency,
    )


def _invoice_status(released: float, future: float, blocked: float, total: float, consistency: bool) -> str:
    if not consistency or total <= 0.005 or blocked > 0.005:
        return STATUS_REVIEW
    if future > 0.005:
        return STATUS_FUTURE
    return STATUS_OK

def _audit_base_row(item: _CanonicalItem) -> list[Any]:
    record = item.record
    return [
        item.invoice, item.partner, record.get("Sequência item") or "-",
        Path(str(record.get("Arquivo fatura") or "")).name if record.get("Arquivo fatura") else "-",
        item.cte, record.get("NF PDF original") or "-", item.nf, record.get("Origem NF") or "-",
        item.billed, record.get("Peso fatura") or 0.0, record.get("Frete CTRC Origem fatura") or 0.0,
        record.get("Comissão fatura") or 0.0, record.get("Fatura chave") or "-",
        record.get("CTRC Origem fatura") or "-", record.get("Método de busca") or record.get("Match base") or "-",
        record.get("CT-e base") or "-", record.get("CTRC base") or "-", record.get("NF base") or "-",
        record.get("Confirmação NF") or "-", record.get("Fatura Base Exp") or "-",
        record.get("Fatura Base Rec") or "-", record.get("Vínculo fatura") or "-",
        normalize_space(f"{record.get('Origem cidade base') or ''}/{record.get('Origem UF base') or ''}") or "-",
        normalize_space(f"{record.get('Destino cidade base') or ''}/{record.get('Destino UF base') or ''}") or "-",
        record.get("Destino comercial tabela") or "-", record.get("Fonte destino tabela") or "-",
        record.get("Aviso rota tabela") or "-", record.get("Tipo documento base") or "-",
        record.get("DY") or record.get("Comprovante") or "-", record.get("Valor base") or 0.0,
        record.get("Parceiro tabela ID") or "-", record.get("Regra tabela ID") or "-",
        record.get("Fonte regra tabela") or "-", record.get("Base cálculo tabela") or 0.0,
        record.get("Fonte base tabela") or "-", record.get("Percentual tabela") or 0.0,
        record.get("Mínimo tabela") or 0.0, record.get("Valor esperado tabela") or 0.0,
        record.get("Diferença tabela") or 0.0, record.get("Tolerância tabela") or 0.0,
        record.get("Status tabela parceiro") or "-", record.get("Peso usado tabela") or 0.0,
        record.get("Fonte peso tabela") or "-", record.get("Modo tabela") or "-",
        record.get("Caminho cálculo tabela") or "-", record.get("Valor XML") or 0.0,
        record.get("Diferença XML") or 0.0, record.get("Status valor") or "-",
        record.get("Origem validação valor") or "-", record.get("Confiança validação valor") or "-",
        record.get("Vínculo validação valor") or "-", record.get("Regra aplicada valor") or "-",
        record.get("Status valor legado") or "-", item.original_status, item.reason,
        record.get("Caminho do status") or "-", record.get("Avisos auditoria") or "-",
    ]


def _audit_row(item: _CanonicalItem) -> list[Any]:
    if item.freight_base is None or item.margin is None:
        memory = f"Frete base/receita não informado; custo do parceiro {_money(item.billed)}; classe {item.margin_class}."
    else:
        memory = (
            f"Frete base {_money(item.freight_base)} - custo parceiro {_money(item.billed)} = "
            f"lucro bruto {_money(item.gross_profit or 0.0)}; margem {item.margin:.2%}; classe {item.margin_class}."
        )
    return _audit_base_row(item) + [
        item.decision_code, item.base_source, item.billed_source, item.block_class,
        item.financial_status, memory, item.consistency,
    ]


def _formula_fingerprint_value(value: Any) -> Any:
    if isinstance(value, Formula):
        return {"formula": value.expression, "cached": value.cached}
    return round(value, 6) if isinstance(value, float) else value


def _fingerprint_sheets(sheets: Sequence[SheetSpec]) -> str:
    payload = []
    for name, rows, widths in sheets:
        payload.append([
            name,
            [[_formula_fingerprint_value(value) for value in row] for row in rows],
            [round(float(width), 3) for width in widths],
        ])
    return stable_hash(payload)


class InvoiceReportBuilder:
    """Gera cinco visões a partir da mesma estrutura canônica por CT-e."""

    VERSION = "2.7.0-RC26.6"
    LOW_MARGIN = 0.10
    HIGH_MARGIN = 0.25

    def build(self, page: Any, only_problem_invoices: bool = False) -> InvoiceReportBuildResult:
        raw_records = [
            dict(row) for row in list(getattr(page, "invoice_detail_records", []) or [])
            if isinstance(row, Mapping)
        ]
        items = [_canonical_item(record) for record in raw_records]

        order: list[str] = []
        partner_hint: dict[str, str] = {}
        snapshot = getattr(page, "_last_decision_snapshot", None)
        for summary in tuple(getattr(snapshot, "invoices", ()) or ()):
            invoice = str(getattr(summary, "invoice_number", "") or "")
            if invoice and invoice not in order:
                order.append(invoice)
            partner_hint[invoice] = str(getattr(summary, "partner", "") or "")
        for row in list(getattr(page, "invoice_rows", []) or []):
            if not isinstance(row, (list, tuple)) or not row:
                continue
            invoice = str(row[0] or "")
            if invoice and invoice not in order:
                order.append(invoice)
            if len(row) > 1:
                partner_hint[invoice] = str(row[1] or "")
        for item in items:
            if item.invoice not in order:
                order.append(item.invoice)
            partner_hint[item.invoice] = item.partner

        grouped: dict[str, list[_CanonicalItem]] = defaultdict(list)
        for item in items:
            grouped[item.invoice].append(item)
        if only_problem_invoices:
            problem_invoices = {
                invoice for invoice, invoice_items in grouped.items()
                if any(item.financial_status not in {STATUS_OK, STATUS_EXCLUDED} for item in invoice_items)
            }
            order = [invoice for invoice in order if invoice in problem_invoices]
            items = [item for item in items if item.invoice in problem_invoices]
            grouped = defaultdict(list)
            for item in items:
                grouped[item.invoice].append(item)

        cte_rows: list[list[Any]] = [list(CTE_HEADERS)]
        attention_rank = 0
        for index, item in enumerate(items):
            excel_row = 6 + index
            if item.financial_status not in {STATUS_OK, STATUS_EXCLUDED}:
                attention_rank += 1
                initial_attention_rank: int | str = attention_rank
            else:
                initial_attention_rank = ""
            counted_amount = item.billed if item.block_class != "NÃO CONTABILIZADO" else 0.0
            situation_formula = (
                f'IF($L{excel_row}="{STATUS_EXCLUDED}","{STATUS_EXCLUDED}",'
                f'IF($L{excel_row}="CONFERIR","{STATUS_REVIEW}",'
                f'IF($L{excel_row}="LIBERADO SEM COMPROVANTE","{STATUS_OK}",'
                f'IF($I{excel_row}="S","{STATUS_OK}","{STATUS_FUTURE}"))))'
            )
            reason_formula = (
                f'IF($M{excel_row}="{STATUS_EXCLUDED}","Item fora da composição financeira.",'
                f'IF($M{excel_row}="{STATUS_OK}",IF($L{excel_row}="LIBERADO SEM COMPROVANTE",'
                f'"Regra canônica libera o documento sem exigência de comprovante.",'
                f'"Comprovante S; observações de base permanecem somente na auditoria."),'
                f'IF($M{excel_row}="{STATUS_FUTURE}",IF($J{excel_row}="FORA_DA_BASE","Comprovante diferente de S; ausência na base é informativa e o CT-e aguarda pagamento futuro.","Comprovante diferente de S: CT-e retirado do pagamento atual e mantido para pagamento futuro."),'
                f'IF($M{excel_row}="{STATUS_REVIEW}","Problema interno: conferência obrigatória. Código: "&$J{excel_row},'
                f'"Revisar situação financeira."))))'
            )
            action_formula = (
                f'IF($M{excel_row}="{STATUS_EXCLUDED}","Desconsiderar da composição financeira.",'
                f'IF($M{excel_row}="{STATUS_OK}","Liberar pagamento deste CT-e.",'
                f'IF($M{excel_row}="{STATUS_FUTURE}","Manter para pagamento futuro até o comprovante voltar para S.",'
                f'IF($M{excel_row}="{STATUS_REVIEW}","Reter somente este CT-e por problema interno e corrigir antes do pagamento.",'
                f'"Revisar manualmente."))))'
            )
            margin_formula = f'IF(OR($L{excel_row}="{STATUS_EXCLUDED}",$F{excel_row}="",$F{excel_row}<=0),"",$W{excel_row}/$F{excel_row})'
            class_formula = (
                f'IF($L{excel_row}="{STATUS_EXCLUDED}","{STATUS_EXCLUDED}",'
                f'IF($E{excel_row}="","SEM DADOS",IF(OR($F{excel_row}="",$F{excel_row}<=0),"SEM FRETE BASE",'
                f"IF($X{excel_row}<0,\"MARGEM NEGATIVA\",IF($X{excel_row}<'PAINEL'!$T$91,\"MARGEM BAIXA\","
                f"IF($X{excel_row}<'PAINEL'!$T$92,\"MARGEM SAUDÁVEL\",\"MARGEM ALTA\"))))))"
            )
            cte_rows.append([
                item.invoice, item.partner, item.cte, item.nf,
                item.billed if item.billed_present else None, item.freight_base,
                item.validation_difference, item.value_status, item.proof,
                item.decision_code, _historical_display(item.original_status), item.block_class,
                Formula(situation_formula, item.financial_status),
                Formula(f'IF($M{excel_row}="{STATUS_FUTURE}",$E{excel_row},0)', item.future_value),
                Formula(f'IF($M{excel_row}="{STATUS_REVIEW}",$E{excel_row},0)', item.billed if item.financial_status == STATUS_REVIEW else 0.0),
                Formula("0", 0.0),
                Formula(f'IF($M{excel_row}="{STATUS_OK}",$E{excel_row},0)', item.released_value),
                Formula(
                    f'IF(ABS(IF($L{excel_row}="{STATUS_EXCLUDED}",0,N($E{excel_row}))-SUM($N{excel_row}:$Q{excel_row}))<=0.01,'
                    f'"PARTIÇÃO COERENTE","INCONSISTENTE")',
                    "PARTIÇÃO COERENTE" if item.consistency == "OK" else "INCONSISTENTE",
                ),
                Formula(reason_formula, item.reason), Formula(action_formula, item.action),
                item.confidence, item.warnings,
                Formula(
                    f'IF($L{excel_row}="{STATUS_EXCLUDED}","",IF(OR($E{excel_row}="",$F{excel_row}="",$F{excel_row}<=0),"",$F{excel_row}-$E{excel_row}))',
                    item.gross_profit if item.block_class != STATUS_EXCLUDED and item.gross_profit is not None else "",
                ),
                Formula(margin_formula, item.margin if item.block_class != STATUS_EXCLUDED and item.margin is not None else ""),
                Formula(class_formula, STATUS_EXCLUDED if item.block_class == STATUS_EXCLUDED else item.margin_class),
                Formula(
                    f'IF(OR($M{excel_row}="{STATUS_OK}",$M{excel_row}="{STATUS_EXCLUDED}"),"",'
                    f'COUNTIFS($M$6:$M{excel_row},"<>{STATUS_OK}",$M$6:$M{excel_row},"<>{STATUS_EXCLUDED}"))',
                    initial_attention_rank,
                ),
            ])
            current_review = item.billed if item.financial_status == STATUS_REVIEW else 0.0
            current_blocked = 0.0
            if abs(counted_amount - item.released_value - item.future_value - current_review - current_blocked) > 0.01:
                raise ValueError(f"Inconsistência financeira no CT-e {item.cte} da fatura {item.invoice}.")

        cte_end = max(6, 5 + len(items))
        faturas_rows: list[list[Any]] = [list(FATURAS_HEADERS)]
        consistency_issue_count = 0
        invoice_initial: dict[str, dict[str, Any]] = {}
        for index, invoice in enumerate(order):
            invoice_items = grouped.get(invoice, [])
            partner = partner_hint.get(invoice) or (invoice_items[0].partner if invoice_items else "Parceiro não identificado")
            imported_count = len(invoice_items)
            financial_count = sum(item.block_class != STATUS_EXCLUDED for item in invoice_items)
            noncounted_count = imported_count - financial_count
            released_count = sum(item.financial_status == STATUS_OK for item in invoice_items)
            future_count = sum(item.financial_status == STATUS_FUTURE for item in invoice_items)
            review_count = sum(item.financial_status == STATUS_REVIEW for item in invoice_items)
            definitive_count = 0
            total = round(sum(item.billed for item in invoice_items if item.block_class != STATUS_EXCLUDED), 2)
            released = round(sum(item.released_value for item in invoice_items), 2)
            future = round(sum(item.future_value for item in invoice_items), 2)
            review = round(sum(item.billed for item in invoice_items if item.financial_status == STATUS_REVIEW), 2)
            definitive = 0.0
            base_total = round(sum(item.freight_base or 0.0 for item in invoice_items if item.block_class != STATUS_EXCLUDED), 2)
            cost_total = total
            profitability_items = [item for item in invoice_items if item.block_class != STATUS_EXCLUDED and item.gross_profit is not None]
            profit = round(sum(item.gross_profit or 0.0 for item in profitability_items), 2) if profitability_items else None
            margin = profit / base_total if profit is not None and base_total > 0 else None
            margin_class = _margin_class(base_total if base_total > 0 else None, bool(profitability_items), margin)
            consistent_values = abs(total - released - future - review - definitive) <= 0.01
            consistent_counts = imported_count == financial_count + noncounted_count and financial_count == released_count + future_count + review_count + definitive_count
            consistent = consistent_values and consistent_counts
            if not consistent:
                consistency_issue_count += 1
            internal = round(review + definitive, 2)
            status = _invoice_status(released, future, internal, total, consistent)
            row = 6 + index
            a_range = f"'CT_ES'!$A$6:$A${cte_end}"
            m_range = f"'CT_ES'!$M$6:$M${cte_end}"
            l_range = f"'CT_ES'!$L$6:$L${cte_end}"
            invoice_initial[invoice] = {
                "status": status, "total": total, "released": released, "future": future,
                "review": review, "blocked": definitive, "base": base_total, "cost": cost_total,
                "profit": profit, "margin": margin, "margin_class": margin_class,
            }
            pending_types = sum(value > 0.005 for value in (future, review + definitive))
            pendencies = (
                STATUS_OK if pending_types == 0
                else STATUS_FUTURE if future > 0.005 and review <= 0.005 and definitive <= 0.005
                else STATUS_REVIEW if (review + definitive) > 0.005 and future <= 0.005
                else f"{STATUS_FUTURE} + {STATUS_REVIEW}"
            )
            action = (
                "Liberar pagamento integral." if status == STATUS_OK
                else (
                    "Liberar o valor atual e manter o saldo para pagamento futuro."
                    if released > 0.005
                    else "Manter integralmente para pagamento futuro e solicitar os comprovantes."
                ) if status == STATUS_FUTURE
                else (
                    "Liberar somente o valor apto; manter o saldo futuro separado e conferir os itens com problema interno."
                    if released > 0.005 and future > 0.005
                    else "Liberar somente o valor apto e conferir os itens com problema interno."
                    if released > 0.005
                    else "Conferir os itens com problema interno antes de nova análise."
                )
            )
            faturas_rows.append([
                invoice, partner,
                Formula(f'COUNTIF({a_range},$A{row})', imported_count),
                Formula(f'COUNTIFS({a_range},$A{row},{l_range},"<>{STATUS_EXCLUDED}")', financial_count),
                Formula(f'COUNTIFS({a_range},$A{row},{m_range},"{STATUS_OK}")', released_count),
                Formula(f'COUNTIFS({a_range},$A{row},{m_range},"{STATUS_FUTURE}")', future_count),
                Formula(f'COUNTIFS({a_range},$A{row},{m_range},"{STATUS_REVIEW}")', review_count),
                Formula("0", definitive_count),
                Formula(f'COUNTIFS({a_range},$A{row},{m_range},"{STATUS_EXCLUDED}")', noncounted_count),
                Formula(f"SUMIFS('CT_ES'!$E$6:$E${cte_end},{a_range},$A{row},{l_range},\"<>{STATUS_EXCLUDED}\")", total),
                Formula(f"SUMIF({a_range},$A{row},'CT_ES'!$Q$6:$Q${cte_end})", released),
                Formula(f"SUMIF({a_range},$A{row},'CT_ES'!$N$6:$N${cte_end})", future),
                Formula(f"SUMIF({a_range},$A{row},'CT_ES'!$O$6:$O${cte_end})", review),
                Formula(f"SUMIF({a_range},$A{row},'CT_ES'!$P$6:$P${cte_end})", definitive),
                Formula(f'IF($J{row}>0,$K{row}/$J{row},0)', released / total if total else 0.0),
                Formula(_invoice_status_formula(row), status),
                Formula(
                    f'IF(AND($L{row}=0,$M{row}=0,$N{row}=0),"{STATUS_OK}",'
                    f'IF(AND($L{row}>0,$M{row}=0,$N{row}=0),"{STATUS_FUTURE}",'
                    f'IF(AND($L{row}=0,SUM($M{row}:$N{row})>0),"{STATUS_REVIEW}",'
                    f'"{STATUS_FUTURE} + {STATUS_REVIEW}")))',
                    pendencies,
                ),
                Formula(_invoice_action_formula(row), action),
                Formula(
                    f'IF(AND(ABS($J{row}-SUM($K{row}:$N{row}))<=0.01,$C{row}=$D{row}+$I{row},$D{row}=SUM($E{row}:$H{row})),"COERENTE","INCONSISTENTE")',
                    "COERENTE" if consistent else "INCONSISTENTE",
                ),
                Formula(f"SUMIFS('CT_ES'!$F$6:$F${cte_end},{a_range},$A{row},{l_range},\"<>{STATUS_EXCLUDED}\")", base_total),
                Formula(f"SUMIFS('CT_ES'!$E$6:$E${cte_end},{a_range},$A{row},{l_range},\"<>{STATUS_EXCLUDED}\")", cost_total),
                Formula(f"IF($T{row}>0,SUMIFS('CT_ES'!$W$6:$W${cte_end},{a_range},$A{row},{l_range},\"<>{STATUS_EXCLUDED}\"),\"\")", profit if profit is not None else ""),
                Formula(f'IF($T{row}>0,$V{row}/$T{row},"")', margin if margin is not None else ""),
                Formula(
                    f"IF($T{row}<=0,\"SEM FRETE BASE\",IF($W{row}<0,\"MARGEM NEGATIVA\",IF($W{row}<'PAINEL'!$T$91,\"MARGEM BAIXA\",IF($W{row}<'PAINEL'!$T$92,\"MARGEM SAUDÁVEL\",\"MARGEM ALTA\"))))",
                    margin_class,
                ),
            ])

        attention_rows: list[list[Any]] = [list(ATTENTION_HEADERS)]
        visible_items = [
            item for item in items
            if item.financial_status not in {STATUS_OK, STATUS_EXCLUDED}
        ]
        for index, _item in enumerate(items):
            row = 6 + index
            item = visible_items[index] if index < len(visible_items) else None
            position = f"MATCH(ROWS($A$6:$A{row}),'CT_ES'!$Z$6:$Z$%d,0)" % cte_end
            kind = (
                STATUS_FUTURE if item and item.financial_status == STATUS_FUTURE
                else STATUS_REVIEW
            ) if item else ""
            message = (
                f"Manter o CT-e {item.cte} da fatura {item.invoice} para pagamento futuro e solicitar o comprovante."
                if item and item.financial_status == STATUS_FUTURE
                else f"Reter o CT-e {item.cte} por problema interno antes do pagamento." if item else ""
            )

            def linked(column: str, cached: Any) -> Formula:
                return Formula(
                    f"IFERROR(INDEX('CT_ES'!${column}$6:${column}${cte_end},{position}),\"\")",
                    cached if item is not None else "",
                )

            attention_rows.append([
                linked("A", item.invoice if item else ""), linked("B", item.partner if item else ""),
                linked("C", item.cte if item else ""), linked("D", item.nf if item else ""),
                linked("E", item.billed if item else ""), linked("N", item.future_value if item else ""),
                linked("O", item.billed if item and item.financial_status == STATUS_REVIEW else ""),
                linked("P", ""),
                linked("M", item.financial_status if item else ""),
                Formula(
                    f'IF($A{row}="","",IF($I{row}="{STATUS_FUTURE}","{STATUS_FUTURE}",'
                    f'"{STATUS_REVIEW}"))',
                    kind,
                ),
                linked("S", item.reason if item else ""), linked("T", item.action if item else ""),
                linked("I", item.proof if item else ""),
                Formula(
                    f'IF($A{row}="","",IF($I{row}="{STATUS_FUTURE}",'
                    f'"Manter o CT-e "&$C{row}&" da fatura "&$A{row}&" para pagamento futuro e solicitar o comprovante.",'
                    f'"Reter o CT-e "&$C{row}&" por problema interno antes do pagamento."))',
                    message,
                ),
            ])

        audit_rows: list[list[Any]] = [list(AUDIT_HEADERS)]
        for index, item in enumerate(items):
            row = 6 + index
            original = _audit_row(item)
            current_memory_cached = (
                f"Frete base/receita não informado; custo do parceiro {_money(item.billed)}; classe {item.margin_class}."
                if item.freight_base is None or item.margin is None
                else f"Frete base {_money(item.freight_base)} - custo parceiro {_money(item.billed)} = lucro bruto {_money(item.gross_profit or 0.0)}; margem {item.margin:.2%}; classe {item.margin_class}."
            )
            live = [
                Formula(f"'CT_ES'!$I{row}", item.proof),
                Formula(f"'CT_ES'!$M{row}", item.financial_status),
                Formula(f"'CT_ES'!$Q{row}", item.released_value),
                Formula(f"'CT_ES'!$N{row}", item.future_value),
                Formula(f"'CT_ES'!$O{row}", item.billed if item.financial_status == STATUS_REVIEW else 0.0),
                Formula(f"'CT_ES'!$P{row}", 0.0),
                Formula(f"'CT_ES'!$S{row}", item.reason),
                Formula(f"'CT_ES'!$T{row}", item.action),
                Formula(f"'CT_ES'!$R{row}", "PARTIÇÃO COERENTE" if item.consistency == "OK" else "INCONSISTENTE"),
                Formula(
                    f"IF(OR('CT_ES'!$F{row}=\"\",'CT_ES'!$F{row}<=0),"
                    f"\"Frete base/receita não informado; rentabilidade não se aplica; classe \"&'CT_ES'!$Y{row}&\".\","
                    f"\"Frete base, custo, lucro e margem seguem as colunas técnicas atuais; classe \"&'CT_ES'!$Y{row}&\".\")",
                    current_memory_cached,
                ),
            ]
            audit_rows.append(original + live)
        if any(len(row) != len(AUDIT_HEADERS) for row in audit_rows):
            raise ValueError("A auditoria de faturas não preservou as colunas técnicas e gerenciais da RC26.")

        total_value = round(sum(item.billed for item in items if item.block_class != STATUS_EXCLUDED), 2)
        payable_value = round(sum(item.released_value for item in items), 2)
        future_value = round(sum(item.future_value for item in items), 2)
        blocked_value = round(sum(item.billed for item in items if item.financial_status == STATUS_REVIEW), 2)
        base_total = round(sum(item.freight_base or 0.0 for item in items), 2)
        profit_total = round(sum(item.gross_profit or 0.0 for item in items if item.gross_profit is not None), 2)
        margin_total = profit_total / base_total if base_total > 0.0 else 0.0
        partners = {item.partner for item in items if item.partner}
        statuses = [invoice_initial[invoice]["status"] for invoice in order if invoice in invoice_initial]
        panel_rows = [
            ["Indicador", "Valor", "Observação"],
            ["Total de faturas", len(order), "Uma linha por fatura na aba FATURAS."],
            ["Total de CT-es", len(items), "Uma linha por CT-e na aba CT_ES."],
            ["Parceiros processados", len(partners), "Parceiros distintos no lote."],
            ["Faturas OK para pagamento", sum(status == STATUS_OK for status in statuses), "Situação dinâmica da fatura."],
            ["Faturas com pagamento futuro", sum("FUTURO" in status for status in statuses), "Comprovantes N; não é prejuízo."],
            ["Faturas com problema interno", sum("PROBLEMA INTERNO" in status for status in statuses), "Somente itens com falha interna ficam retidos."],
            ["Valor total faturado", total_value, "Custo cobrado pelos parceiros."],
            ["Valor a pagar agora", payable_value, "Liberado pela situação atual."],
            ["Valor para pagamento futuro", future_value, "Comprovante pendente; poderá ser liberado depois."],
            ["Valor retido por problema interno", blocked_value, "Retenção técnica, separada dos comprovantes pendentes."],
            ["Frete base / receita", base_total, "Base informada para estimativa gerencial."],
            ["Lucro bruto estimado", profit_total, "Antes de impostos, despesas e custos internos."],
            ["Margem bruta estimada", margin_total, "Lucro bruto dividido pelo frete base."],
            ["Consistência interna", consistency_issue_count, "Esperado: zero."],
        ]

        sheets: list[SheetSpec] = [
            ("PAINEL", panel_rows, [34, 22, 88]),
            ("FATURAS", faturas_rows, [18, 32, 13, 16, 14, 16, 17, 0.0, 16, 18, 17, 18, 20, 0.0, 16, 31, 25, 52, 22, 18, 18, 18, 16, 22]),
            ("ATENÇÃO", attention_rows, [17, 32, 16, 16, 18, 18, 20, 0.0, 26, 24, 58, 50, 15, 75]),
            ("CT_ES", cte_rows, [17, 32, 16, 16, 18, 18, 17, 0.0, 14, 0.0, 0.0, 0.0, 26, 18, 20, 0.0, 18, 22, 58, 50, 0.0, 0.0, 18, 16, 24, 0.0]),
            ("AUDITORIA_TÉCNICA", audit_rows, [16, 32, 8, 44, 16, 18, 16, 22, 14, 14, 18, 16, 16, 20, 25, 16, 16, 16, 20, 18, 18, 30, 22, 22, 26, 26, 44, 22, 8, 16, 20, 24, 20, 18, 28, 14, 14, 18, 16, 16, 30, 16, 26, 24, 70, 14, 14, 26, 26, 20, 28, 26, 24, 22, 54, 70, 58, 26, 28, 28, 28, 28, 72, 22, 14, 26, 18, 18, 18, 20, 58, 50, 22, 78]),
        ]
        return InvoiceReportBuildResult(
            version=self.VERSION,
            sheets=sheets,
            invoice_count=len(order),
            item_count=len(items),
            problem_item_count=sum(item.financial_status not in {STATUS_OK, STATUS_EXCLUDED} for item in items),
            total_value=total_value,
            payable_value=payable_value,
            future_value=future_value,
            blocked_value=blocked_value,
            partner_count=len(partners),
            consistency_issue_count=consistency_issue_count,
            audit_column_count=len(AUDIT_HEADERS),
            fingerprint=_fingerprint_sheets(sheets),
        )


def normalize_sheets(value: Iterable[Any]) -> list[Any]:
    """Normaliza o contrato para auditoria determinística, inclusive fórmulas."""
    normalized: list[Any] = []
    for sheet in list(value or []):
        try:
            name, rows, widths = sheet
        except Exception:
            normalized.append([str(sheet)])
            continue
        normalized.append([
            str(name),
            [[_formula_fingerprint_value(cell) for cell in list(row or [])] for row in list(rows or [])],
            [round(float(width), 3) for width in list(widths or [])],
        ])
    return normalized


__all__ = [
    "AUDIT_HEADERS", "ATTENTION_HEADERS", "CTE_HEADERS", "FATURAS_HEADERS",
    "InvoiceReportBuildResult", "InvoiceReportBuilder", "SheetSpec", "normalize_sheets",
]
