"""Relatórios imprimíveis.

Cada relatório é essencialmente uma lista imprimível. A especificação de cada
um (``REPORT_SPECS``) descreve os filtros exibidos na tela de configuração e o
catálogo de colunas (fixas + opcionais). ``build_report`` resolve os filtros,
consulta o banco (agregações em centavos, conversão só na borda) e devolve um
contexto normalizado — ``columns`` + ``rows`` (linhas = listas de células
alinhadas às colunas) — pronto para o template genérico de impressão.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from ..models import (
    Client,
    ExpenseInstallment,
    PaymentType,
    Product,
    Sale,
    SaleItem,
    SalePayment,
)
from .money import _cents_to_reais, _parse_reais, reais_to_cents


def _report_col(key, label, type_, default=True):
    """Descritor de coluna de relatório (``type`` guia a formatação no template)."""
    return {"key": key, "label": label, "type": type_, "default": default}


# Colunas de produto reaproveitadas por "Produtos" e "Produtos mais vendidos".
_PRODUCT_COLUMNS = [
    _report_col("barcode", "Código de barras", "text"),
    _report_col("manufacturer_code", "Cód. fabricante", "text"),
    _report_col("name", "Nome", "text"),
    _report_col("manufacturer", "Fabricante", "text"),
    _report_col("quantity", "Quantidade", "int"),
    _report_col("unit_price", "Preço unitário", "money"),
    _report_col("description", "Descrição", "text", default=False),
]

REPORT_SPECS = [
    {
        "key": "products",
        "label": "Produtos",
        "period": None,
        "cutoff": False,
        "fixed_columns": [],
        "optional_columns": _PRODUCT_COLUMNS
        + [
            _report_col("unit_type", "Tipo de unidade", "text", default=False),
            _report_col("min_stock", "Estoque mínimo", "int", default=False),
            _report_col("is_active", "Ativo", "bool", default=False),
        ],
    },
    {
        "key": "best_products",
        "label": "Produtos mais vendidos",
        "period": "month_to_date",
        "cutoff": "units",
        "fixed_columns": [_report_col("units", "Unidades vendidas", "int")],
        "optional_columns": _PRODUCT_COLUMNS,
    },
    {
        "key": "sales",
        "label": "Vendas",
        "period": "month_to_date",
        "cutoff": False,
        "fixed_columns": [],
        "optional_columns": [
            _report_col("number", "Nº", "int"),
            _report_col("date", "Data", "date"),
            _report_col("client", "Cliente", "text"),
            _report_col("payments", "Forma(s) de pagamento", "text"),
            _report_col("subtotal", "Subtotal", "money"),
            _report_col("discount", "Desconto", "money"),
            _report_col("total", "Total", "money"),
            _report_col("change", "Troco", "money"),
            _report_col("obs", "Observações", "text", default=False),
        ],
    },
    {
        "key": "sales_summary",
        "label": "Vendas - Resumo",
        "period": "month_to_date",
        "cutoff": False,
        "fixed_columns": [],
        # As "colunas opcionais" aqui são as informações (linhas) do resumo —
        # a seleção reusa os checkboxes de colunas; todas marcadas por padrão.
        "optional_columns": [
            _report_col("count", "Nº de vendas", "int"),
            _report_col("units", "Produtos vendidos", "int"),
            _report_col("distinct_units", "Produtos diferentes vendidos", "int"),
            _report_col("subtotal", "Subtotal", "money"),
            _report_col("discount", "Desconto", "money"),
            _report_col("total", "Total", "money"),
            _report_col("pay_credit", "Crédito", "money"),
            _report_col("pay_debit", "Débito", "money"),
            _report_col("pay_cash", "Dinheiro", "money"),
            _report_col("pay_pix", "Pix", "money"),
            _report_col("pay_other", "Outros", "money"),
        ],
    },
    {
        "key": "sales_by_day",
        "label": "Vendas - Total por dia",
        "period": "month_to_date",
        "cutoff": False,
        "fixed_columns": [
            _report_col("day", "Dia", "date"),
            _report_col("total", "Valor total", "money"),
        ],
        "optional_columns": [],
    },
    {
        "key": "sales_by_month",
        "label": "Vendas - Total por mês",
        "period": "month_to_date",
        "cutoff": False,
        "fixed_columns": [
            _report_col("month", "Mês", "text"),
            _report_col("total", "Valor total", "money"),
        ],
        "optional_columns": [],
    },
    {
        "key": "best_clients",
        "label": "Clientes - Maiores compradores",
        "period": "month_to_date",
        "cutoff": "money",
        "fixed_columns": [_report_col("total", "Total comprado", "money")],
        "optional_columns": [
            _report_col("name", "Nome", "text"),
            _report_col("cpf_cnpj", "CPF/CNPJ", "cpf_cnpj"),
            _report_col("service_provider", "Prestador de serviço", "bool"),
            _report_col("email", "E-mail", "text"),
            _report_col("phone_primary", "Telefone principal", "phone"),
            _report_col("person_type", "Tipo de pessoa", "text", default=False),
        ],
    },
    {
        "key": "expenses",
        "label": "Despesas",
        "period": "month_to_date",
        "cutoff": False,
        "fixed_columns": [
            _report_col("name", "Despesa", "text"),
            _report_col("type", "Tipo", "text"),
            _report_col("installment_current", "Parcela", "int"),
            _report_col("installment_total", "Total de parcelas", "int"),
            _report_col("due_date", "Vencimento", "date"),
            _report_col("value", "Valor", "money"),
            _report_col("paid_value", "Valor pago", "money"),
            _report_col("paid_at", "Data de pagamento", "date"),
        ],
        "optional_columns": [],
    },
    {
        "key": "expenses_open",
        "label": "Despesas abertas",
        "period": "month_to_date",
        "cutoff": False,
        "fixed_columns": [
            _report_col("name", "Despesa", "text"),
            _report_col("type", "Tipo", "text"),
            _report_col("installment_current", "Parcela", "int"),
            _report_col("installment_total", "Total de parcelas", "int"),
            _report_col("due_date", "Vencimento", "date"),
            _report_col("value", "Valor", "money"),
        ],
        "optional_columns": [],
    },
    {
        "key": "expenses_paid",
        "label": "Despesas pagas",
        "period": "month_to_date",
        "cutoff": False,
        "fixed_columns": [
            _report_col("name", "Despesa", "text"),
            _report_col("type", "Tipo", "text"),
            _report_col("installment_current", "Parcela", "int"),
            _report_col("installment_total", "Total de parcelas", "int"),
            _report_col("due_date", "Vencimento", "date"),
            _report_col("value", "Valor", "money"),
            _report_col("paid_value", "Valor pago", "money"),
            _report_col("paid_at", "Data de pagamento", "date"),
        ],
        "optional_columns": [],
    },
]

_REPORT_SPECS_BY_KEY = {spec["key"]: spec for spec in REPORT_SPECS}

# "Vendas - Resumo": agrupamento das informações (linhas) em 3 blocos. ``total``
# indica que o grupo mostra um rodapé "Somatório" das linhas exibidas.
_SALES_SUMMARY_GROUPS = [
    {"title": "Vendas", "keys": ["count", "units", "distinct_units"], "total": False},
    {"title": "Valores", "keys": ["subtotal", "discount", "total"], "total": False},
    {
        "title": "Formas de pagamento",
        "keys": ["pay_credit", "pay_debit", "pay_cash", "pay_pix", "pay_other"],
        "total": True,
    },
]

_SALES_SUMMARY_PAYMENT_KEYS = {
    "pay_credit": PaymentType.CREDIT,
    "pay_debit": PaymentType.DEBIT,
    "pay_cash": PaymentType.CASH,
    "pay_pix": PaymentType.PIX,
    "pay_other": PaymentType.OTHER,
}


# --- Leitura de parâmetros (aceita QueryDict do request ou dict simples) ---


def _param(params, key, default=""):
    value = params.get(key, default)
    return value if value is not None else default


def _param_list(params, key):
    if hasattr(params, "getlist"):
        return params.getlist(key)
    value = params.get(key, [])
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value] if value else []


def _parse_report_date(raw):
    """Converte ``YYYY-MM-DD`` em ``date``; devolve ``None`` se vazio/ inválido."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_report_int(raw, default=0):
    try:
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default


# --- Janelas de data (defaults por relatório) ---


def _prev_month_range(today):
    """1º ao último dia do mês anterior."""
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev


def _current_month_range(today):
    """1º ao último dia do mês corrente."""
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=1), today.replace(day=last_day)


def _last_12_months_range(today):
    """Do 1º dia do mês 11 meses atrás ao último dia do mês corrente (12 meses)."""
    year, month = today.year, today.month - 11
    while month <= 0:
        month += 12
        year -= 1
    _, last_end = _current_month_range(today)
    return date(year, month, 1), last_end


def _month_to_date_range(today):
    """Do 1º dia do mês corrente até hoje (período padrão de todos os relatórios)."""
    return today.replace(day=1), today


_PERIOD_DEFAULTS = {
    "month_to_date": _month_to_date_range,
    "prev_month": _prev_month_range,
    "current_month": _current_month_range,
    "last_12_months": _last_12_months_range,
}


def _resolve_period(spec, params, today):
    """(início, fim, rótulo) do período; aplica o default quando o input é vazio."""
    kind = spec.get("period")
    if not kind:
        return None, None, ""
    start = _parse_report_date(_param(params, "date_from"))
    end = _parse_report_date(_param(params, "date_to"))
    if not (start and end):
        start, end = _PERIOD_DEFAULTS[kind](today)
    if start > end:
        start, end = end, start
    label = f"{start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}"
    return start, end, label


def _resolve_columns(spec, params):
    """Colunas efetivas: fixas + opcionais escolhidas (ou defaults se nenhuma)."""
    chosen = set(_param_list(params, "col"))
    optional = spec["optional_columns"]
    if chosen:
        selected = [c for c in optional if c["key"] in chosen]
    else:
        selected = [c for c in optional if c["default"]]
    columns = list(spec["fixed_columns"]) + selected
    return [{"key": c["key"], "label": c["label"], "type": c["type"]} for c in columns]


# --- Builders por relatório (devolvem lista de registros dict + rótulo meta) ---


def _report_products(params, today):
    products = Product.objects.select_related("manufacturer").order_by("name")
    records = [
        {
            "barcode": p.barcode,
            "manufacturer_code": p.manufacturer_code,
            "name": p.name,
            "manufacturer": p.manufacturer.name,
            "quantity": p.quantity,
            "unit_price": _cents_to_reais(p.unit_price_cents),
            "description": p.description,
            "unit_type": p.unit_type,
            "min_stock": p.min_stock,
            "is_active": p.is_active,
        }
        for p in products
    ]
    return records, ""


def _report_best_products(params, today, period):
    start, end, _ = period
    all_sales = bool(_param(params, "all_sales"))
    mode = _param(params, "cutoff_mode", "top")
    amount = _parse_report_int(_param(params, "cutoff_value"), 10)

    items = SaleItem.objects.filter(product_snapshot__product_id__isnull=False)
    if not all_sales:
        items = items.filter(sale__created_at__date__range=(start, end))
    agg = items.values("product_snapshot__product_id").annotate(
        units=Sum("quantity")
    )
    if mode == "cut":
        agg = agg.filter(units__gte=amount).order_by("-units")
        meta = f"Produtos com {amount} ou mais unidades vendidas"
    else:
        agg = agg.order_by("-units")[: amount or 0]
        meta = f"TOP {amount} produtos por unidades vendidas"

    units_by_id = {r["product_snapshot__product_id"]: r["units"] for r in agg}
    products = {
        p.id: p
        for p in Product.objects.select_related("manufacturer").filter(
            id__in=units_by_id.keys()
        )
    }
    records = []
    for pid, p in products.items():
        records.append(
            {
                "units": units_by_id.get(pid, 0),
                "barcode": p.barcode,
                "manufacturer_code": p.manufacturer_code,
                "name": p.name,
                "manufacturer": p.manufacturer.name,
                "quantity": p.quantity,
                "unit_price": _cents_to_reais(p.unit_price_cents),
                "description": p.description,
            }
        )
    records.sort(key=lambda r: r["name"].lower())
    return records, meta


def _report_sales(params, today, period):
    start, end, _ = period
    all_sales = bool(_param(params, "all_sales"))
    sales = Sale.objects.select_related("client").prefetch_related("payments")
    if not all_sales:
        sales = sales.filter(created_at__date__range=(start, end))
    sales = sales.order_by("-created_at")
    records = [
        {
            "number": s.pk,
            "date": s.created_at,
            "client": s.client.name if s.client else "",
            "payments": ", ".join(
                p.get_payment_type_display() for p in s.payments.all()
            ),
            "subtotal": _cents_to_reais(s.subtotal_cents),
            "discount": _cents_to_reais(s.discount_cents),
            "total": _cents_to_reais(s.total_cents),
            "change": _cents_to_reais(s.change_cents),
            "obs": s.obs,
        }
        for s in sales
    ]
    return records, ""


def _report_sales_summary(params, today, period):
    """Valores agregados do resumo de vendas (um dict key→valor já em reais/int)."""
    start, end, _ = period
    all_sales = bool(_param(params, "all_sales"))

    sales = Sale.objects.all()
    items = SaleItem.objects.all()
    payments = SalePayment.objects.all()
    if not all_sales:
        sales = sales.filter(created_at__date__range=(start, end))
        items = items.filter(sale__created_at__date__range=(start, end))
        payments = payments.filter(sale__created_at__date__range=(start, end))

    agg = sales.aggregate(
        count=Count("id"),
        subtotal=Sum("subtotal_cents"),
        discount=Sum("discount_cents"),
        total=Sum("total_cents"),
    )
    units = items.aggregate(u=Sum("quantity"))["u"] or 0
    distinct_units = (
        items.filter(product_snapshot__product__isnull=False).aggregate(
            d=Count("product_snapshot__product", distinct=True)
        )["d"]
        or 0
    )
    pay_by_type = {
        row["payment_type"]: row["v"] or 0
        for row in payments.values("payment_type").annotate(v=Sum("value_cents"))
    }

    values = {
        "count": agg["count"] or 0,
        "units": units,
        "distinct_units": distinct_units,
        "subtotal": _cents_to_reais(agg["subtotal"]),
        "discount": _cents_to_reais(agg["discount"]),
        "total": _cents_to_reais(agg["total"]),
    }
    for key, code in _SALES_SUMMARY_PAYMENT_KEYS.items():
        values[key] = _cents_to_reais(pay_by_type.get(code, 0))
    return values


def _build_sales_summary_groups(spec, params, values):
    """Monta os grupos (linhas Indicador/Valor + somatórios) do resumo de vendas.

    As linhas exibidas são as informações selecionadas (checkboxes ``col``; se
    nenhuma, os defaults do spec). Grupos sem itens selecionados são omitidos.
    """
    labels = {c["key"]: c["label"] for c in spec["optional_columns"]}
    types = {c["key"]: c["type"] for c in spec["optional_columns"]}

    chosen = set(_param_list(params, "col"))
    if not chosen:
        chosen = {c["key"] for c in spec["optional_columns"] if c["default"]}

    groups = []
    for group in _SALES_SUMMARY_GROUPS:
        keys = [k for k in group["keys"] if k in chosen]
        if not keys:
            continue
        rows = [
            {
                "label": labels[k],
                "value": values[k],
                "type": types[k],
                "strong": k == "total",  # destaca a linha "Total" em negrito
            }
            for k in keys
        ]
        total = None
        if group["total"]:
            total = {
                "label": "Somatório",
                "value": sum(values[k] for k in keys),
                "type": "money",
            }
        groups.append({"title": group["title"], "rows": rows, "total": total})
    return groups


def _report_sales_by_day(params, today, period):
    start, end, _ = period
    all_sales = bool(_param(params, "all_sales"))
    sales = Sale.objects.all()
    if not all_sales:
        sales = sales.filter(created_at__date__range=(start, end))
    rows = (
        sales.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("total_cents"))
        .order_by("day")
    )
    records = [
        {"day": r["day"], "total": _cents_to_reais(r["total"])} for r in rows
    ]
    return records, ""


def _report_sales_by_month(params, today, period):
    start, end, _ = period
    all_sales = bool(_param(params, "all_sales"))
    sales = Sale.objects.all()
    if not all_sales:
        sales = sales.filter(created_at__date__range=(start, end))
    rows = (
        sales.annotate(m=TruncMonth("created_at"))
        .values("m")
        .annotate(total=Sum("total_cents"))
    )
    total_by_key = {(r["m"].year, r["m"].month): r["total"] or 0 for r in rows}
    # Sem período (todos os registros): itera do mês mais antigo ao mais recente
    # com venda; sem vendas, devolve vazio.
    if all_sales:
        if not total_by_key:
            return [], ""
        (start_year, start_month) = min(total_by_key)
        (end_year, end_month) = max(total_by_key)
    else:
        start_year, start_month = start.year, start.month
        end_year, end_month = end.year, end.month
    records = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        cents = total_by_key.get((year, month), 0)
        records.append(
            {"month": f"{month:02d}/{year}", "total": _cents_to_reais(cents)}
        )
        month += 1
        if month > 12:
            month = 1
            year += 1
    return records, ""


def _report_best_clients(params, today, period):
    start, end, _ = period
    all_sales = bool(_param(params, "all_sales"))
    mode = _param(params, "cutoff_mode", "top")

    sales = Sale.objects.exclude(client__isnull=True)
    if not all_sales:
        sales = sales.filter(created_at__date__range=(start, end))
    agg = sales.values("client").annotate(total=Sum("total_cents"))
    if mode == "cut":
        try:
            amount_reais = _parse_reais(_param(params, "cutoff_value"))
        except ValueError:
            amount_reais = Decimal("0")
        cutoff_cents = reais_to_cents(amount_reais)
        agg = agg.filter(total__gte=cutoff_cents).order_by("-total")
        meta = f"Clientes com R$ {cutoff_cents / 100:.2f} ou mais em compras"
    else:
        amount = _parse_report_int(_param(params, "cutoff_value"), 10)
        agg = agg.order_by("-total")[: amount or 0]
        meta = f"TOP {amount} clientes por valor comprado"

    total_by_id = {r["client"]: r["total"] for r in agg}
    clients = {c.id: c for c in Client.objects.filter(id__in=total_by_id.keys())}
    records = [
        {
            "total": _cents_to_reais(total_by_id[cid]),
            "name": c.name,
            "cpf_cnpj": c.cpf_cnpj,
            "service_provider": c.service_provider,
            "email": c.email,
            "phone_primary": c.phone_primary,
            "person_type": c.get_person_type_display(),
        }
        for cid, c in clients.items()
    ]
    records.sort(key=lambda r: r["name"].lower())
    return records, meta


def _report_expenses(params, today, period, *, mode):
    start, end, _ = period
    all_sales = bool(_param(params, "all_sales"))
    installments = ExpenseInstallment.objects.select_related("expense")
    if not all_sales:
        installments = installments.filter(due_date__range=(start, end))
    if mode == "open":
        installments = installments.filter(
            paid_value_cents__lt=F("value_cents")
        )
    elif mode == "paid":
        installments = installments.filter(
            value_cents__gt=0, paid_value_cents__gte=F("value_cents")
        )
    installments = installments.order_by("due_date", "installment_current")
    records = [
        {
            "name": i.expense.name,
            "type": "Recorrente" if i.expense.recurrent else "Isolada",
            "installment_current": i.installment_current,
            "installment_total": i.installment_total,
            "due_date": i.due_date,
            "value": _cents_to_reais(i.value_cents),
            "paid_value": _cents_to_reais(i.paid_value_cents),
            "paid_at": i.paid_at,
        }
        for i in installments
    ]
    return records, ""


def build_report(*, report_type, params, today=None):
    """Monta um relatório imprimível a partir do tipo e dos filtros do GET.

    Devolve um dict normalizado (``title``, ``period_label``, ``meta_label``,
    ``columns`` e ``rows``) — ``rows`` são listas de células ``{type, value}``
    alinhadas a ``columns``, para renderização genérica no template. Levanta
    ``ValidationError`` (PT-BR) para um tipo desconhecido.
    """
    if today is None:
        today = timezone.localdate()
    spec = _REPORT_SPECS_BY_KEY.get(report_type)
    if spec is None:
        raise ValidationError("Tipo de relatório inválido.")

    period = _resolve_period(spec, params, today)
    all_sales = bool(_param(params, "all_sales"))

    # Rótulo do período: "Todos os registros" quando o filtro de data é ignorado.
    if spec.get("period") and all_sales:
        period_label = "Todos os registros"
    else:
        period_label = period[2]

    # "Vendas - Resumo": layout vertical agrupado (grupos em vez de columns/rows).
    if report_type == "sales_summary":
        values = _report_sales_summary(params, today, period)
        return {
            "title": spec["label"],
            "period_label": period_label,
            "meta_label": "",
            "groups": _build_sales_summary_groups(spec, params, values),
        }

    columns = _resolve_columns(spec, params)

    if report_type == "products":
        records, meta = _report_products(params, today)
    elif report_type == "best_products":
        records, meta = _report_best_products(params, today, period)
    elif report_type == "sales":
        records, meta = _report_sales(params, today, period)
    elif report_type == "sales_by_day":
        records, meta = _report_sales_by_day(params, today, period)
    elif report_type == "sales_by_month":
        records, meta = _report_sales_by_month(params, today, period)
    elif report_type == "best_clients":
        records, meta = _report_best_clients(params, today, period)
    elif report_type == "expenses":
        records, meta = _report_expenses(params, today, period, mode="all")
    elif report_type == "expenses_open":
        records, meta = _report_expenses(params, today, period, mode="open")
    else:  # expenses_paid
        records, meta = _report_expenses(params, today, period, mode="paid")

    rows = [
        [{"type": c["type"], "value": rec.get(c["key"])} for c in columns]
        for rec in records
    ]
    return {
        "title": spec["label"],
        "period_label": period_label,
        "meta_label": meta,
        "columns": columns,
        "rows": rows,
    }
