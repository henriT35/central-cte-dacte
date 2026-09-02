from __future__ import annotations

from pathlib import Path
from typing import Callable


class InvoicePdfTextReader:
    """Leitor isolado de texto de PDF com múltiplos backends opcionais.

    O EXE legado já possui sua própria extração. Esta classe permite que o
    módulo novo leia o arquivo por conta própria quando algum backend estiver
    empacotado. Se nenhum estiver disponível, o chamador pode fornecer um
    fallback, sem transformar a falta do backend em falha do processamento.
    """

    VERSION = "2.6.67.3"

    def read(self, file_path: str | Path, fallback: Callable[[Path], str] | None = None) -> tuple[str, str]:
        path = Path(file_path)
        errors: list[str] = []

        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if text.strip():
                return text, "pypdf"
        except Exception as exc:
            errors.append(f"pypdf={type(exc).__name__}: {exc}")

        try:
            import fitz  # type: ignore

            document = fitz.open(str(path))
            try:
                text = "\n".join(page.get_text("text") or "" for page in document)
            finally:
                document.close()
            if text.strip():
                return text, "pymupdf"
        except Exception as exc:
            errors.append(f"pymupdf={type(exc).__name__}: {exc}")

        if callable(fallback):
            try:
                text = str(fallback(path) or "")
                if text.strip():
                    return text, "fallback_legado"
            except Exception as exc:
                errors.append(f"fallback={type(exc).__name__}: {exc}")

        detail = "; ".join(errors) if errors else "nenhum backend de PDF disponível"
        raise RuntimeError(f"Não foi possível extrair texto de {path.name}: {detail}")
