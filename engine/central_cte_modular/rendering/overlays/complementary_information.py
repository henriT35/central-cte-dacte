from __future__ import annotations

from html import escape
import re
from typing import Any, Callable, Mapping


class ComplementaryInformationOverlay:
    """Insere informação complementar somente no HTML de impressão."""

    def __init__(
        self,
        get_information: Callable[[Mapping[str, Any]], str],
        is_cte: Callable[[Mapping[str, Any]], bool],
    ) -> None:
        self._get_information = get_information
        self._is_cte = is_cte

    def apply(self, info: Mapping[str, Any], html: str) -> str:
        value_html = str(html or "")
        try:
            value_html = re.sub(
                r'\s*<div[^>]*data-central-complementar="1"[^>]*>.*?</div>\s*',
                "\n",
                value_html,
                flags=re.S | re.I,
            )
            information = str(self._get_information(info) or "")
            if not information or not self._is_cte(info):
                return value_html
            body = escape(information).replace("\n", "<br>")
            block = (
                '<div class="informacao-complementar-cte" data-central-complementar="1" '
                'style="border:1px solid #111;border-top:0;padding:3px 5px;'
                'font-size:7.4px;line-height:1.22;font-family:Arial,sans-serif;'
                'background:#fffdf2;overflow-wrap:anywhere;">'
                f'<b>INFORMAÇÃO COMPLEMENTAR</b><br>{body}</div>'
            )

            compact = re.search(
                r'<div class="controle-rodotec[^"]*"[^>]*>.*?</div>',
                value_html,
                flags=re.S | re.I,
            )
            if compact:
                return value_html[: compact.end()] + "\n    " + block + value_html[compact.end() :]

            marker = re.search(
                r'(?P<indent>[ \t]*)<div class="section-title">INFORMAÇÕES RELATIVAS AO IMPOSTO</div>',
                value_html,
                flags=re.I,
            )
            if marker:
                indent = marker.group("indent") or "    "
                return value_html[: marker.start()] + indent + block + "\n\n" + value_html[marker.start() :]
            return value_html + "\n" + block
        except Exception:
            return value_html
