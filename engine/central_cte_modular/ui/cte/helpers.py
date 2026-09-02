from __future__ import annotations

"""Helpers modulares de seleção, filtro e agrupamento da página CT-e.

Este módulo substitui o último resíduo ``cte_helpers_2665``. As funções são
puras sempre que possível e não dependem do namespace do motor histórico.
Aliases com os nomes antigos são publicados por uma ponte modular apenas para
consumidores ainda existentes durante a homologação final.
"""

import unicodedata
from typing import Any, Mapping

HELPERS_VERSION = "2.7.0"

FILTER_GROUPS = (
    "Todos",
    "Não processado",
    "OK",
    "Divergente",
    "Revisão necessária",
    "Sem base ou vínculo",
    "Sem cadastro ou tabela",
    "Erro de leitura",
    "Outros",
)


def normalize_text(value: Any) -> str:
    text = str(value or "").replace("\xa0", " ").strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.upper().split())


def is_cte_info(info: Mapping[str, Any] | None) -> bool:
    if not isinstance(info, Mapping):
        return False
    kind = normalize_text(info.get("tipo") or info.get("document_type") or "")
    compact = kind.replace("-", "").replace(" ", "")
    return compact in {"CTE", "CT", "CTEOS"}


class CTeHelperService:
    version = HELPERS_VERSION
    filter_groups = FILTER_GROUPS

    @staticmethod
    def is_cte(info: Mapping[str, Any] | None) -> bool:
        return is_cte_info(info)

    def selected_or_visible(self, page: Any) -> tuple[list[dict[str, Any]], str]:
        """Retorna CT-es marcados; na ausência deles, os visíveis no filtro.

        Suporta a página Tk modular e o contrato Qt histórico usado por alguns
        consumidores de recuperação, sem importar Qt no fluxo normal.
        """

        selected: list[dict[str, Any]] = []
        selected_provider = getattr(page, "selected_infos", None)
        if callable(selected_provider):
            try:
                selected = [
                    info for info in list(selected_provider() or [])
                    if self.is_cte(info)
                ]
            except Exception:
                selected = []

        if not selected:
            try:
                table = getattr(page, "xml_table", None)
                rows: set[int] = set()
                model = table.selectionModel() if table is not None else None
                if model is not None:
                    try:
                        rows.update(index.row() for index in model.selectedRows())
                    except Exception:
                        rows.update(index.row() for index in table.selectedIndexes())
                role = 256
                try:
                    from PySide6.QtCore import Qt

                    role = getattr(
                        getattr(Qt, "ItemDataRole", Qt),
                        "UserRole",
                        getattr(Qt, "UserRole", 256),
                    )
                except Exception:
                    pass
                xml_rows = list(getattr(page, "xml_rows", []) or [])
                for row in sorted(rows):
                    item = table.item(row, 0) if table is not None else None
                    if item is None:
                        continue
                    try:
                        index = int(item.data(role))
                    except Exception:
                        continue
                    if 0 <= index < len(xml_rows) and self.is_cte(xml_rows[index]):
                        selected.append(xml_rows[index])
            except Exception:
                selected = []

        if selected:
            return selected, "marcados"

        for provider_name in ("visible_infos", "filtered_files"):
            provider = getattr(page, provider_name, None)
            if callable(provider):
                try:
                    visible = [
                        info for info in list(provider() or [])
                        if self.is_cte(info)
                    ]
                    return visible, "visíveis no filtro atual"
                except Exception:
                    pass

        source = getattr(page, "files", None)
        if source is None:
            source = getattr(page, "xml_rows", [])
        visible = [info for info in list(source or []) if self.is_cte(info)]
        return visible, "visíveis no filtro atual"

    @staticmethod
    def status_group(status: Any) -> str:
        normalized = normalize_text(str(status or "").strip())
        if not normalized or normalized in {
            "NAO VALIDADO",
            "NAO PROCESSADO",
            "AGUARDANDO",
            "PENDENTE DE PROCESSAMENTO",
        }:
            return "NÃO PROCESSADO"
        if normalized.startswith("OK"):
            return "OK"
        if "DIVERGENTE" in normalized:
            return "DIVERGENTE"

        review_tokens = (
            "REVISAR",
            "REVISAO",
            "AMBIG",
            "MULTIPLAS ROTAS",
            "MULTIPLA ROTA",
            "REGRA PENDENTE",
            "REGRA EXTRA PENDENTE",
            "REGRA SEM VALOR",
            "REGRA EXTRA SEM VALOR",
            "FRETE PESO SEM DADOS",
            "EXTRA REVISAR",
            "DADOS INSUFICIENTES",
        )
        if any(token in normalized for token in review_tokens):
            return "REVISÃO NECESSÁRIA"

        error_tokens = (
            "ERRO XML",
            "ERRO DE LEITURA",
            "ERRO AO LER",
            "NAO E CT-E",
            "NAO E CTE",
            "NF NAO LIDA",
            "XML INVALIDO",
            "XML MALFORMADO",
        )
        if any(token in normalized for token in error_tokens) or normalized.startswith("ERRO"):
            return "ERRO DE LEITURA"

        base_tokens = (
            "NF INCOMPATIVEL",
            "NF NAO ENCONTRADA",
            "NF FORA DA BASE",
            "FORA DA BASE",
            "FORA DO PERIODO",
            "FORA DA BASE / PERIODO",
            "ORIGINAL NAO ENCONTRADO",
            "BASE NAO CARREGADA",
            "SEM BASE",
            "SEM VINCULO",
            "VINCULO NAO ENCONTRADO",
        )
        if any(token in normalized for token in base_tokens):
            return "SEM BASE OU VÍNCULO"

        registration_tokens = (
            "TABELAS NAO CARREGADAS",
            "TABELA NAO CARREGADA",
            "SEM TABELA",
            "PARCEIRO SEM CADASTRO",
            "SEM PARCEIRO",
            "PARCEIRO NAO IDENTIFICADO",
            "REGRA NAO ENCONTRADA",
            "SEM REGRA",
            "CADASTRO NAO ENCONTRADO",
        )
        if any(token in normalized for token in registration_tokens):
            return "SEM CADASTRO OU TABELA"

        if (
            "BASE" in normalized
            or normalized.startswith("NF")
            or "ORIGINAL" in normalized
            or "PERIODO" in normalized
        ):
            return "SEM BASE OU VÍNCULO"
        if "PARCEIRO" in normalized or "REGRA" in normalized or "TABELA" in normalized:
            return "SEM CADASTRO OU TABELA"
        return "OUTROS"

    @staticmethod
    def has_ignored_nfs(info: Mapping[str, Any] | None) -> bool:
        result = (info or {}).get("validacao") or {}
        ignored: list[str] = []
        for key in ("nfs_ignoradas", "nfs_nao_encontradas", "nfs_incompativeis"):
            value = result.get(key)
            if isinstance(value, (list, tuple, set)):
                ignored.extend(str(item).strip() for item in value if str(item).strip())
            elif str(value or "").strip():
                ignored.append(str(value).strip())
        return bool(ignored or result.get("validacao_parcial"))

    @staticmethod
    def raw_status(info: Mapping[str, Any] | None) -> str:
        result = (info or {}).get("validacao") or {}
        status = str(result.get("status") or "").strip()
        return status or "NÃO PROCESSADO"

    def matches_filters(
        self,
        info: Mapping[str, Any] | None,
        filters: Mapping[str, Any] | None = None,
        ui: Mapping[str, Any] | None = None,
    ) -> bool:
        filters = filters or {}
        info = info or {}
        result = info.get("validacao") or {}
        ui = ui or {}

        raw_status = self.raw_status(info)
        group = str(filters.get("group") or "Todos")
        if normalize_text(group) not in {"", "TODOS"}:
            if normalize_text(self.status_group(raw_status)) != normalize_text(group):
                return False

        exact = str(filters.get("exact") or "Todos")
        if normalize_text(exact) not in {"", "TODOS"} and normalize_text(raw_status) != normalize_text(exact):
            return False

        review_mode = normalize_text(filters.get("review") or "Todos")
        reviewed = normalize_text(info.get("revisao_manual", "")) == "REVISADO"
        if review_mode == "REVISADO" and not reviewed:
            return False
        if review_mode == "NAO REVISADO" and reviewed:
            return False

        observation_mode = normalize_text(filters.get("observation") or "Todos")
        has_observation = bool(str(info.get("observacao_manual", "") or "").strip())
        if observation_mode == "COM OBSERVACAO" and not has_observation:
            return False
        if observation_mode == "SEM OBSERVACAO" and has_observation:
            return False

        ignored_mode = normalize_text(filters.get("ignored") or "Todos")
        has_ignored = self.has_ignored_nfs(info)
        if ignored_mode == "COM NFS IGNORADAS" and not has_ignored:
            return False
        if ignored_mode == "SEM NFS IGNORADAS" and has_ignored:
            return False

        text = normalize_text(filters.get("search") or "")
        nf_query = normalize_text(filters.get("nf") or "")
        partner_query = normalize_text(filters.get("partner") or "")
        city_query = normalize_text(filters.get("city") or "")
        charge = str(filters.get("charge") or "Todos")
        component = str(filters.get("component") or "Todos")

        ignored_text = " ".join(
            str(value or "")
            for key in ("nfs_ignoradas", "nfs_nao_encontradas", "nfs_incompativeis")
            for value in (
                (result.get(key) or [])
                if isinstance(result.get(key), (list, tuple, set))
                else [result.get(key)]
            )
        )
        hay_parts = [
            ui.get("numero", info.get("numero", "")),
            ui.get("serie", info.get("serie", "")),
            ui.get("emitente", info.get("emitente", "")),
            ui.get("destinatario", info.get("destinatario", "")),
            ui.get("nf", result.get("nf", "")),
            ui.get("cidade", info.get("destino", "")),
            ui.get("tipo_cob", result.get("tipo_cobranca", "")),
            ui.get("componente", result.get("componente_comparado", "")),
            raw_status,
            ui.get("arquivo", info.get("arquivo", "")),
            result.get("detalhe", ""),
            info.get("observacao_manual", ""),
            info.get("revisao_manual", ""),
            ignored_text,
        ]
        hay = normalize_text(" ".join(str(value or "") for value in hay_parts))
        if text and text not in hay:
            return False

        nf_text = normalize_text(
            " ".join(str(value or "") for value in [ui.get("nf", ""), result.get("nf", ""), ignored_text])
        )
        if nf_query and nf_query not in nf_text:
            return False

        partner_text = normalize_text(
            " ".join(
                str(value or "")
                for value in [ui.get("emitente", ""), info.get("emitente", ""), result.get("partner_id", "")]
            )
        )
        if partner_query and partner_query not in partner_text:
            return False

        city_text = normalize_text(
            " ".join(
                str(value or "")
                for value in [
                    ui.get("cidade", ""),
                    info.get("destino", ""),
                    (info.get("dest") or {}).get("mun", ""),
                ]
            )
        )
        if city_query and city_query not in city_text:
            return False

        if normalize_text(charge) not in {"", "TODOS"}:
            actual_charge = normalize_text(ui.get("tipo_cob", result.get("tipo_cobranca", "")))
            if actual_charge != normalize_text(charge):
                return False

        if normalize_text(component) not in {"", "TODOS"}:
            actual_component = normalize_text(ui.get("componente", result.get("componente_comparado", "")))
            if normalize_text(component) not in actual_component:
                return False
        return True

    def report_bucket(self, status: Any) -> str:
        group = self.status_group(status)
        return {
            "OK": "OK",
            "DIVERGENTE": "DIVERGENTES",
            "SEM BASE OU VÍNCULO": "SEM_BASE",
            "SEM CADASTRO OU TABELA": "SEM_PARCEIRO_REGRA",
            "REVISÃO NECESSÁRIA": "REVISAO_ERROS",
            "ERRO DE LEITURA": "REVISAO_ERROS",
        }.get(group, "OUTROS")

    def matches_page_status_filter(self, status: Any, selected_filter: Any) -> bool:
        current = str(selected_filter or "TODOS")
        normalized = normalize_text(status)
        if current == "TODOS":
            return True
        if current == "NÃO VALIDADO":
            return normalized in {"NAO VALIDADO", "NAO PROCESSADO"}
        if current == "OK":
            return self.status_group(status) == "OK"
        if current == "DIVERGENTES":
            return self.status_group(status) == "DIVERGENTE"
        if current == "REVISÃO":
            return self.status_group(status) == "REVISÃO NECESSÁRIA"
        if current == "SEM BASE":
            return self.status_group(status) == "SEM BASE OU VÍNCULO"
        if current == "SEM PARCEIRO/REGRA":
            return self.status_group(status) == "SEM CADASTRO OU TABELA"
        if current == "ERROS":
            return self.status_group(status) == "ERRO DE LEITURA"
        if current.startswith("STATUS: "):
            return str(status or "") == current.split(":", 1)[1].strip()
        return True


__all__ = [
    "HELPERS_VERSION",
    "FILTER_GROUPS",
    "normalize_text",
    "is_cte_info",
    "CTeHelperService",
]
