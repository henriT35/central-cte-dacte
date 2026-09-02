from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from .styles import DACTE_CSS
from .overlays.complementary_information import ComplementaryInformationOverlay


class HtmlDocumentRenderer:
    """Compõe o documento HTML em lote usando páginas já renderizadas."""

    def __init__(
        self,
        page_renderer: Callable[[Mapping[str, Any]], str],
        complementary_overlay: ComplementaryInformationOverlay,
        css: str = DACTE_CSS,
    ) -> None:
        self.page_renderer = page_renderer
        self.complementary_overlay = complementary_overlay
        self.css = str(css)

    def render(
        self,
        infos: Iterable[Mapping[str, Any]],
        with_button: bool = True,
        auto_print: bool = False,
    ) -> str:
        button = '<div class="printbar"><button onclick="window.print()">Imprimir</button></div>' if with_button else ""
        auto_script = """
<script>
window.addEventListener('load', function() {
    setTimeout(function() { window.print(); }, 600);
});
</script>
""" if auto_print else ""
        pages = "\n".join(
            self.complementary_overlay.apply(info, self.page_renderer(info))
            for info in infos
        )
        return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>DACTE em Lote</title>
<style>{self.css}</style>
{auto_script}
</head>
<body>
{button}
{pages}
</body>
</html>"""
