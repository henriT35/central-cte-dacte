"""Assinatura visual e geração de PDF extraídas do motor monolítico.

O XML fiscal é sempre somente leitura. O pacote trabalha sobre HTML/PDF e
possui auditoria e fallback para a implementação histórica.
"""
from .common import VERSION, cte_output_basename, partner_name_from_info
from .models import SignatureProfile
from .profiles import SignatureProfileStore, registration_sheet_html
from .image_processing import process_signature_image, detect_registration_box, image_backend_status, render_pdf_first_page
from .html_signer import (STAMP_SIZE_LABELS, inject_signature_html, normalize_stamp_size, render_signed_html, render_signed_batch_html, signature_block_html, signature_css)
from .pdf_converter import find_browser, html_file_to_pdf, html_text_to_pdf, validate_pdf_file
from .exporter import PdfBatchExporter

__all__ = [
    "VERSION", "SignatureProfile", "SignatureProfileStore", "PdfBatchExporter",
    "registration_sheet_html", "process_signature_image", "detect_registration_box",
    "image_backend_status", "render_pdf_first_page", "inject_signature_html",
    "render_signed_html", "render_signed_batch_html", "signature_block_html",
    "signature_css", "normalize_stamp_size", "STAMP_SIZE_LABELS", "find_browser",
    "html_file_to_pdf", "html_text_to_pdf", "validate_pdf_file",
    "cte_output_basename", "partner_name_from_info",
]
