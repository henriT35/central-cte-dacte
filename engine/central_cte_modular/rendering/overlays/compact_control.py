from __future__ import annotations

from html import escape
import re
import unicodedata
from typing import Any, Mapping


class CompactControlOverlay:
    """Renderiza o cálculo compacto uma única vez antes do bloco de imposto."""

    marker = '    <div class="section-title">INFORMAÇÕES RELATIVAS AO IMPOSTO</div>'
    block_pattern = re.compile(
        r'\s*<div class="controle-rodotec[^"\\]*(?: [^"\\]*)?">.*?</div>\s*',
        flags=re.S,
    )

    @staticmethod
    def _normalize(value: Any) -> str:
        text = unicodedata.normalize("NFD", str(value or ""))
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", text).strip().upper()

    def build(self, info: Mapping[str, Any]) -> str:
        try:
            result = dict(info.get("validacao") or {})
            if not str(result.get("controle_dacte_compacto") or "").strip():
                return ""
            rule = escape(str(result.get("controle_dacte_regra") or "CONTROLE"))
            line1 = escape(str(result.get("controle_dacte_linha1") or ""))
            line2 = escape(str(result.get("controle_dacte_linha2") or ""))
            status = self._normalize(result.get("controle_dacte_status") or result.get("status") or "")
            css_class = "ok" if "OK" in status and "DIVERG" not in status else "bad"

            # QA-1787247518979: quando houver baixa/aprovação manual, a
            # justificativa deve viajar junto do bloco compacto no DACTE/PDF.
            # O texto é escapado porque vem de entrada do usuário.
            manual = result.get("manual_decision")
            manual_action = ""
            manual_actor = str(result.get("controle_dacte_responsavel_manual") or "").strip()
            manual_date = str(result.get("controle_dacte_data_manual") or result.get("revisao_data") or "").strip()
            if isinstance(manual, Mapping):
                manual_action = self._normalize(manual.get("decision") or "")
                manual_actor = manual_actor or str(manual.get("actor_name") or manual.get("actor_id") or "").strip()
                manual_date = manual_date or str(manual.get("decided_at") or "").strip()
            review = self._normalize(result.get("revisao_manual") or "")
            persisted = self._normalize(result.get("status_final_persistido") or "")
            reason_raw = str(
                result.get("controle_dacte_justificativa")
                or result.get("observacao_manual")
                or ((manual or {}).get("reason") if isinstance(manual, Mapping) else "")
                or ""
            ).strip()
            approved = (
                bool(result.get("baixa_manual_aplicada"))
                or manual_action == "APPROVED"
                or review == "APROVADO"
                or status.startswith("OK MANUAL")
                or status.startswith("OK EXTRA AUTORIZADO")
                or persisted.startswith("OK MANUAL")
                or persisted.startswith("OK EXTRA AUTORIZADO")
            )
            manual_html = ""
            if approved:
                reason = escape(reason_raw or "Não registrada na fotografia disponível")
                meta_parts = [part for part in (manual_actor, manual_date) if part]
                meta = escape(" • ".join(meta_parts))
                manual_html = f'<br><b>JUSTIFICATIVA DA APROVAÇÃO:</b> {reason}'
                if meta:
                    manual_html += f'<br><small>{meta}</small>'

            return (
                f'<div class="controle-rodotec {css_class}">'
                f'<b>CONTROLE INTERNO - {rule}</b><br>{line1}<br>{line2}{manual_html}</div>'
            )
        except Exception:
            return ""

    def apply(self, info: Mapping[str, Any], html: str) -> str:
        value = str(html or "")
        try:
            value = self.block_pattern.sub("\n", value)
            block = self.build(info)
            if not block:
                return value
            if self.marker in value:
                return value.replace(self.marker, f"    {block}\n\n{self.marker}", 1)
            return value + "\n" + block
        except Exception:
            return value
