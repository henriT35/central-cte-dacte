"""Motor modular de faturas.

A versão 2.6.67.4 preserva a promoção iniciada na 2.6.67.3 e promove a decisão modular por fatura quando as auditorias
de entrada e decisão não apresentam divergência crítica. Qualquer fatura insegura
permanece automaticamente no legado.
"""
from .audit_report import InvoiceAuditReport
from .base_linker import InvoiceBaseLinker
from .decision_audit import InvoiceDecisionAuditEngine
from .decision_engine import InvoiceDecisionEngine
from .decision_report import InvoiceDecisionAuditReport
from .document_parser import InvoiceDocumentParser
from .input_audit import InvoiceInputAuditEngine
from .input_audit_report import InvoiceInputAuditReport
from .input_catalog import InvoiceInputCatalog
from .shadow_engine import InvoiceShadowEngine, InvoiceShadowService
from .promotion_engine import InvoicePromotionEngine
from .promotion_models import InvoicePromotionResult
from .promotion_report import InvoicePromotionReport

__all__ = [
    "InvoiceAuditReport",
    "InvoiceBaseLinker",
    "InvoiceDecisionAuditEngine",
    "InvoiceDecisionAuditReport",
    "InvoiceDecisionEngine",
    "InvoiceDocumentParser",
    "InvoiceInputAuditEngine",
    "InvoiceInputAuditReport",
    "InvoiceInputCatalog",
    "InvoiceShadowEngine",
    "InvoiceShadowService",
    "InvoicePromotionEngine",
    "InvoicePromotionResult",
    "InvoicePromotionReport",
]
