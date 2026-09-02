from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from ..domain.cte_models import CargoData, CteDocument, InvoiceReference, Party


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    text = str(value or "0").strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        return Decimal(text or "0")
    except InvalidOperation:
        return Decimal("0")


def _party(value: Any) -> Party:
    data = _mapping(value)
    return Party(
        name=_first(data.get("nome"), data.get("name"), data.get("xNome")),
        tax_id=_first(data.get("cnpj"), data.get("cpf"), data.get("cnpj_cpf"), data.get("tax_id")),
        state_registration=_first(data.get("ie"), data.get("inscricao_estadual")),
        city=_first(data.get("municipio"), data.get("cidade"), data.get("city")),
        state=_first(data.get("uf"), data.get("state")),
        address=_first(data.get("endereco"), data.get("logradouro"), data.get("address")),
        postal_code=_first(data.get("cep"), data.get("postal_code")),
        phone=_first(data.get("fone"), data.get("telefone"), data.get("phone")),
    )


class LegacyInfoAdapter:
    """Converts legacy dictionaries to typed models without mutating input."""

    def to_document(self, info: Mapping[str, Any]) -> CteDocument:
        if not isinstance(info, Mapping):
            raise TypeError("O CT-e legado precisa ser um mapeamento.")
        invoice_values = info.get("nfs") or info.get("notas") or info.get("invoices") or []
        invoices: list[InvoiceReference] = []
        if isinstance(invoice_values, (str, int)):
            invoice_values = [invoice_values]
        if isinstance(invoice_values, (list, tuple, set)):
            for item in invoice_values:
                if isinstance(item, Mapping):
                    number = _first(item.get("numero"), item.get("nf"), item.get("number"))
                    key = _first(item.get("chave"), item.get("key"))
                else:
                    number, key = str(item or "").strip(), ""
                if number or key:
                    invoices.append(InvoiceReference(number=number, access_key=key))

        cargo_raw = _mapping(info.get("carga") or info.get("cargo"))
        source = _first(info.get("source_path"), info.get("arquivo"), info.get("path"))
        return CteDocument(
            number=_first(info.get("numero"), info.get("cte"), info.get("number")),
            series=_first(info.get("serie"), info.get("series")),
            access_key=_first(info.get("chave"), info.get("chave_acesso"), info.get("access_key")),
            issuer=_party(info.get("emit") or info.get("emitente")),
            sender=_party(info.get("rem") or info.get("remetente")),
            recipient=_party(info.get("dest") or info.get("destinatario")),
            dispatcher=_party(info.get("exped") or info.get("expedidor")),
            receiver=_party(info.get("receb") or info.get("recebedor")),
            payer=_party(info.get("toma") or info.get("tomador")),
            invoices=tuple(invoices),
            cargo=CargoData(
                gross_weight_kg=_decimal(cargo_raw.get("peso_bruto") or info.get("peso_bruto")),
                calculation_weight_kg=_decimal(cargo_raw.get("peso_base") or info.get("peso_base")),
                volume_m3=_decimal(cargo_raw.get("cubagem") or info.get("cubagem")),
                goods_value=_decimal(cargo_raw.get("valor_mercadoria") or info.get("valor_mercadoria")),
                description=_first(cargo_raw.get("produto"), info.get("produto_predominante")),
            ),
            service_value=_decimal(info.get("valor_total") or info.get("valor_servico") or info.get("vPrest")),
            source_path=Path(source) if source else None,
            raw_metadata=dict(info),
        )
