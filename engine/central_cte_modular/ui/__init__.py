"""Controladores, presenters e vistas modulares independentes de patches."""

from .audit import UIAuditWriter
from .controllers import (
    CONTROLLER_VERSION,
    ApplicationUIController,
    BaseUIController,
    CTeUIController,
    InvoiceUIController,
)
from .cte import (
    AUDIT_VERSION as CTE_PRESENTER_AUDIT_VERSION,
    PRESENTER_VERSION as CTE_PRESENTER_VERSION,
    SERVICES_VERSION as CTE_PAGE_SERVICES_VERSION,
    CTePagePresenter,
    CTePageServices,
    CTePresenterAuditWriter,
)
from .invoices import (
    AUDIT_VERSION as INVOICE_PRESENTER_AUDIT_VERSION,
    PRESENTER_VERSION as INVOICE_PRESENTER_VERSION,
    SERVICES_VERSION as INVOICE_PAGE_SERVICES_VERSION,
    InvoicePagePresenter,
    InvoicePageServices,
    InvoicePresenterAuditWriter,
)
from .models import UIActionAudit, UIStateSnapshot
from .views import (
    VIEW_FACTORY_VERSION,
    ModularViewFactory,
    ViewFactoryState,
)

__all__ = [
    "CONTROLLER_VERSION",
    "ApplicationUIController",
    "BaseUIController",
    "CTeUIController",
    "InvoiceUIController",
    "UIActionAudit",
    "UIAuditWriter",
    "UIStateSnapshot",
    "CTE_PRESENTER_AUDIT_VERSION",
    "CTE_PRESENTER_VERSION",
    "CTE_PAGE_SERVICES_VERSION",
    "CTePagePresenter",
    "CTePageServices",
    "CTePresenterAuditWriter",
    "INVOICE_PRESENTER_AUDIT_VERSION",
    "INVOICE_PRESENTER_VERSION",
    "INVOICE_PAGE_SERVICES_VERSION",
    "InvoicePagePresenter",
    "InvoicePageServices",
    "InvoicePresenterAuditWriter",
    "VIEW_FACTORY_VERSION",
    "ModularViewFactory",
    "ViewFactoryState",
]
