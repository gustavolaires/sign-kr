"""Camada de regras de negócio da app ``sign``.

Pacote organizado com **um módulo por domínio** (dashboard, vendas, despesas,
notas fiscais, importação CSV e relatórios) sobre um módulo-base ``money`` com os
primitivos monetários compartilhados. Este ``__init__`` **reexporta** a API
pública de forma plana, para que ``from sign.services import ...`` (e o acesso por
atributo ``services.<nome>``) continue funcionando como quando era um único módulo.
"""

from .money import _cents_to_reais, _parse_reais, reais_to_cents
from .dashboard import dashboard_metrics
from .sales import compute_quote_amounts, create_sale
from .expenses import cancel_payment, create_expense, register_payment
from .invoices import (
    create_inbound_invoice,
    format_nf_search,
    nf_search_tokens,
    process_inbound_invoice,
    round_price_cents,
    suggest_product_match,
    suggested_price_cents,
)
from .imports import IMPORT_PRODUCT_FIELDS, import_products_csv
from .reports import (
    REPORT_SPECS,
    build_report,
    # Helpers de janela de data importados por nome em ``views/reports.py``.
    _current_month_range,
    _last_12_months_range,
    _month_to_date_range,
    _prev_month_range,
)

__all__ = [
    # money
    "reais_to_cents",
    # dashboard
    "dashboard_metrics",
    # sales
    "compute_quote_amounts",
    "create_sale",
    # expenses
    "create_expense",
    "register_payment",
    "cancel_payment",
    # invoices
    "create_inbound_invoice",
    "process_inbound_invoice",
    "suggest_product_match",
    "suggested_price_cents",
    "round_price_cents",
    "nf_search_tokens",
    "format_nf_search",
    # imports
    "IMPORT_PRODUCT_FIELDS",
    "import_products_csv",
    # reports
    "REPORT_SPECS",
    "build_report",
]
