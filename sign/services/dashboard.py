"""Indicadores da dashboard (Vendas, Produtos, Despesas).

Concentra toda a matemática (agregações ORM em centavos, fórmulas de meta,
janelas de data), retornando um dict pronto para o contexto da view.
"""

import calendar
from datetime import timedelta

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from ..models import Company, ExpenseInstallment, Product, Sale, SaleItem
from .money import _cents_to_reais


def dashboard_metrics(*, company=None, today=None):
    """Consolida os indicadores da dashboard (Vendas, Produtos, Despesas).

    Concentra toda a matemática (agregações ORM em centavos, fórmulas de meta,
    janelas de data) num único lugar, retornando um dict pronto para o contexto
    da view. ``company``/``today`` são injetáveis (testes); por padrão usam o
    singleton e ``timezone.localdate()``.

    A conversão centavos→reais acontece só na borda (valores retornados em reais,
    para exibição e para os gráficos). Nenhuma escrita no banco.
    """
    if company is None:
        company = Company.get_solo()
    if today is None:
        today = timezone.localdate()

    # --- Janelas de data (semana = segunda a domingo) ---
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    month_start = today.replace(day=1)
    month_end = today.replace(day=days_in_month)

    # --- Vendas: contagem + faturamento (created_at é DateTimeField) ---
    sales = Sale.objects.all()

    def sale_stats(qs):
        agg = qs.aggregate(count=Count("id"), revenue=Sum("total_cents"))
        return {
            "count": agg["count"] or 0,
            "revenue": _cents_to_reais(agg["revenue"]),
        }

    sales_metrics = {
        "today": sale_stats(sales.filter(created_at__date=today)),
        "week": sale_stats(sales.filter(created_at__date__range=(week_start, week_end))),
        "month": sale_stats(
            sales.filter(created_at__date__range=(month_start, month_end))
        ),
        "total": sale_stats(sales),
    }
    # Faturamento em centavos (semana/mês) para o cálculo de % de meta.
    week_revenue_cents = round(sales_metrics["week"]["revenue"] * 100)
    month_revenue_cents = round(sales_metrics["month"]["revenue"] * 100)

    # --- Produtos vendidos (unidades) = soma de SaleItem.quantity ---
    items = SaleItem.objects.all()

    def units_sold(qs):
        return qs.aggregate(u=Sum("quantity"))["u"] or 0

    units_metrics = {
        "today": units_sold(items.filter(sale__created_at__date=today)),
        "week": units_sold(
            items.filter(sale__created_at__date__range=(week_start, week_end))
        ),
        "month": units_sold(
            items.filter(sale__created_at__date__range=(month_start, month_end))
        ),
        "total": units_sold(items),
    }

    # --- Faturamento da semana por dia (Seg→Dom), preenchendo dias vazios ---
    week_by_day = (
        sales.filter(created_at__date__range=(week_start, week_end))
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total_cents"))
    )
    by_day_cents = {row["day"]: row["revenue"] or 0 for row in week_by_day}
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    weekly_revenue = [_cents_to_reais(by_day_cents.get(d, 0)) for d in week_days]

    # --- Faturamento do mês por dia (1→último dia), preenchendo dias vazios ---
    month_by_day = (
        sales.filter(created_at__date__range=(month_start, month_end))
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total_cents"))
    )
    month_by_day_cents = {row["day"]: row["revenue"] or 0 for row in month_by_day}
    month_days = [month_start + timedelta(days=i) for i in range(days_in_month)]
    monthly_revenue = [
        _cents_to_reais(month_by_day_cents.get(d, 0)) for d in month_days
    ]

    # --- Metas (em centavos; % com guarda para meta 0) ---
    daily_goal_cents = company.daily_sales_goal_cents
    weekly_goal_cents = company.operating_days_per_week * daily_goal_cents
    month_factor = max(
        0,
        days_in_month
        - (days_in_month % 7) * (7 - company.operating_days_per_week),
    )
    monthly_goal_cents = month_factor * daily_goal_cents

    def pct(value_cents, goal_cents):
        if not goal_cents:
            return None
        return round(value_cents / goal_cents * 100, 1)

    weekly_goal_pct = pct(week_revenue_cents, weekly_goal_cents)
    monthly_goal_pct = pct(month_revenue_cents, monthly_goal_cents)

    # --- Produtos (estoque) ---
    # Estoque baixo/zerado consideram só produtos ativos e usam o estoque
    # mínimo de cada produto (o limite da empresa é apenas o default de cadastro).
    active_products = Product.objects.filter(is_active=True)
    total_products = Product.objects.count()
    active_count = active_products.count()
    low_stock = active_products.filter(quantity__lte=F("min_stock")).count()
    zero_stock = active_products.filter(quantity=0).count()

    def share(n, base):
        return round(n / base * 100, 1) if base else 0.0

    products_metrics = {
        "total": total_products,
        "active": active_count,
        "active_pct": share(active_count, total_products),
        "low": low_stock,
        "low_pct": share(low_stock, active_count),
        "zero": zero_stock,
        "zero_pct": share(zero_stock, active_count),
    }

    # --- Despesas do mês (por saldo: pagas + não pagas = a pagar) ---
    inst = ExpenseInstallment.objects.filter(
        due_date__range=(month_start, month_end)
    )
    exp = inst.aggregate(
        due=Sum("value_cents"),
        paid=Sum("paid_value_cents"),
        recurrent=Sum("value_cents", filter=Q(expense__recurrent=True)),
        isolated=Sum("value_cents", filter=Q(expense__recurrent=False)),
    )
    exp_due_cents = exp["due"] or 0
    exp_paid_raw = exp["paid"] or 0
    exp_unpaid_cents = max(0, exp_due_cents - exp_paid_raw)
    exp_paid_cents = exp_due_cents - exp_unpaid_cents  # = min(pago, devido)

    expenses_metrics = {
        "due": _cents_to_reais(exp_due_cents),
        "unpaid": _cents_to_reais(exp_unpaid_cents),
        "paid": _cents_to_reais(exp_paid_cents),
        "recurrent": _cents_to_reais(exp["recurrent"]),
        "isolated": _cents_to_reais(exp["isolated"]),
    }

    goals = {
        "daily": _cents_to_reais(daily_goal_cents),
        "weekly": _cents_to_reais(weekly_goal_cents),
        "monthly": _cents_to_reais(monthly_goal_cents),
        "weekly_pct": weekly_goal_pct,
        "monthly_pct": monthly_goal_pct,
    }

    # Dados serializados para o Chart.js (json_script). Tudo em reais.
    chart_data = {
        "weekly": {
            "labels": ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"],
            "revenue": weekly_revenue,
            "daily_goal": _cents_to_reais(daily_goal_cents),
        },
        "monthly": {
            "labels": [str(d.day) for d in month_days],
            "revenue": monthly_revenue,
            "daily_goal": _cents_to_reais(daily_goal_cents),
        },
        "week_goal": {
            "attained": sales_metrics["week"]["revenue"],
            "goal": _cents_to_reais(weekly_goal_cents),
            "pct": weekly_goal_pct,
        },
        "month_goal": {
            "attained": sales_metrics["month"]["revenue"],
            "goal": _cents_to_reais(monthly_goal_cents),
            "pct": monthly_goal_pct,
        },
        "stock": {
            "ok": max(0, active_count - low_stock),
            "low": max(0, low_stock - zero_stock),
            "zero": zero_stock,
        },
        "expenses": {
            "paid": expenses_metrics["paid"],
            "unpaid": expenses_metrics["unpaid"],
        },
    }

    return {
        "sales": sales_metrics,
        "units": units_metrics,
        "products": products_metrics,
        "expenses": expenses_metrics,
        "goals": goals,
        "chart_data": chart_data,
    }
