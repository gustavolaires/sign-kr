"""Regras de negócio do checkout de vendas.

Concentra toda a matemática monetária (em centavos, com ``Decimal``/
``ROUND_HALF_UP``) e a criação atômica da venda. As validações levantam
``ValidationError`` com mensagens em PT-BR, capturadas pela view do checkout.
"""

import calendar
import math
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import (
    Company,
    Expense,
    ExpenseInstallment,
    InboundInvoice,
    InvoiceDuplicate,
    InvoiceItem,
    PaymentType,
    Product,
    ProductSnapshot,
    RoundingType,
    Sale,
    SaleItem,
    SalePayment,
    UnitType,
)


def reais_to_cents(value):
    """Converte um ``Decimal`` em reais para centavos (inteiro), arredondando.

    Mesma fórmula usada em ``ProductForm.save`` (HALF_UP, sem float).
    """
    value = Decimal(value)
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cents_to_reais(cents):
    """Converte centavos (inteiro) para reais (float) só na borda de exibição."""
    return (cents or 0) / 100


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


def compute_quote_amounts(*, items, has_perc_discount, discount_input, payments):
    """Calcula os montantes de um orçamento (somente exibição), sem persistir.

    Espelha as fórmulas monetárias de ``create_sale`` (centavos, ``Decimal``/
    ``ROUND_HALF_UP``), mas é **lenient**: não valida estoque nem exige que os
    pagamentos cubram o total, e **nunca levanta** ``ValidationError``. Desconto
    fora de faixa é clampado; linhas de pagamento inválidas são ignoradas.

    Retorna ``(subtotal_cents, discount_cents, total_cents, change_cents,
    perc_discount, normalized_payments)``, onde ``normalized_payments`` é uma lista
    de dicts ``{"payment_type", "installments", "value_cents"}``.
    """
    subtotal_cents = 0
    for item in items:
        product = item["product"]
        quantity = max(int(item["quantity"] or 0), 0)
        subtotal_cents += product.unit_price_cents * quantity

    # Desconto (percentual clampado a 0–100, ou valor não-negativo), sem exceder o subtotal.
    perc_discount = None
    if has_perc_discount:
        perc_discount = Decimal(discount_input or 0)
        if perc_discount < 0:
            perc_discount = Decimal(0)
        elif perc_discount > 100:
            perc_discount = Decimal(100)
        discount_cents = int(
            (Decimal(subtotal_cents) * perc_discount / 100).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    else:
        discount_cents = reais_to_cents(discount_input or 0)
        if discount_cents < 0:
            discount_cents = 0
    if discount_cents > subtotal_cents:
        discount_cents = subtotal_cents

    total_cents = subtotal_cents - discount_cents

    # Pagamentos: ignora tipos inválidos/duplicados e valores não positivos.
    seen_types = set()
    normalized_payments = []
    paid_cents = 0
    for payment in payments:
        payment_type = payment.get("payment_type")
        if payment_type not in PaymentType.values or payment_type in seen_types:
            continue
        value_cents = reais_to_cents(payment.get("value") or 0)
        if value_cents <= 0:
            continue
        seen_types.add(payment_type)

        installments = 1
        if payment_type == PaymentType.CREDIT:
            try:
                installments = int(payment.get("installments") or 1)
            except (TypeError, ValueError):
                installments = 1
            if installments < 1:
                installments = 1

        normalized_payments.append(
            {
                "payment_type": payment_type,
                "installments": installments,
                "value_cents": value_cents,
            }
        )
        paid_cents += value_cents

    change_cents = max(paid_cents - total_cents, 0)
    return (
        subtotal_cents,
        discount_cents,
        total_cents,
        change_cents,
        perc_discount,
        normalized_payments,
    )


@transaction.atomic
def create_sale(*, cart, client, has_perc_discount, discount_input, payments, obs,
                discount_obs=""):
    """Cria uma venda completa a partir do carrinho, de forma atômica.

    Parâmetros:
        cart: instância de ``Cart`` (lê itens do cookie).
        client: ``Client`` ou ``None`` (venda avulsa).
        has_perc_discount: ``True`` se o desconto da venda é percentual.
        discount_input: ``Decimal`` — percentual (0–100) se ``has_perc_discount``,
            senão valor em reais. ``None``/0 quando não há desconto.
        payments: lista de dicts ``{"payment_type", "installments", "value"}``,
            com ``value`` em reais (``Decimal``).
        obs: observações (str).
        discount_obs: observações do desconto (str) — texto livre, sem cálculo.

    Revalida o estoque, baixa ``Product.quantity`` e grava Sale/SaleItem/
    SalePayment. Retorna a ``Sale`` criada. Levanta ``ValidationError`` em
    qualquer inconsistência (nada é gravado).
    """
    items = cart.items()
    if not items:
        raise ValidationError("Seu carrinho está vazio.")

    # 1) Revalida estoque item a item e calcula o subtotal (em centavos).
    subtotal_cents = 0
    for item in items:
        product = item["product"]
        quantity = item["quantity"]
        if not product.is_active:
            raise ValidationError(
                f"{product.name} está inativo e não pode ser vendido."
            )
        if quantity < 1:
            raise ValidationError(f"Quantidade inválida para {product.name}.")
        if quantity > product.quantity:
            raise ValidationError(
                f"Estoque insuficiente para {product.name}. "
                f"Disponível: {product.quantity}; solicitado: {quantity}."
            )
        subtotal_cents += product.unit_price_cents * quantity

    # 2) Desconto da venda (percentual ou valor) → centavos.
    perc_discount = None
    if has_perc_discount:
        perc_discount = Decimal(discount_input or 0)
        if perc_discount < 0 or perc_discount > 100:
            raise ValidationError("O percentual de desconto deve estar entre 0 e 100.")
        discount_cents = int(
            (Decimal(subtotal_cents) * perc_discount / 100).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
    else:
        discount_cents = reais_to_cents(discount_input or 0)
        if discount_cents < 0:
            raise ValidationError("O desconto não pode ser negativo.")

    if discount_cents > subtotal_cents:
        raise ValidationError("O desconto não pode ser maior que o subtotal.")

    total_cents = subtotal_cents - discount_cents

    # 3) Pagamentos: normaliza, valida tipos e soma (em centavos).
    seen_types = set()
    normalized_payments = []
    paid_cents = 0
    for payment in payments:
        payment_type = payment["payment_type"]
        if payment_type not in PaymentType.values:
            raise ValidationError("Forma de pagamento inválida.")
        if payment_type in seen_types:
            raise ValidationError(
                "Há mais de um pagamento com a mesma forma de pagamento."
            )
        seen_types.add(payment_type)

        value_cents = reais_to_cents(payment.get("value") or 0)
        if value_cents <= 0:
            raise ValidationError("O valor de cada pagamento deve ser maior que zero.")

        # Parcelas só fazem sentido no crédito; normaliza os demais para 1.
        installments = 1
        if payment_type == PaymentType.CREDIT:
            try:
                installments = int(payment.get("installments") or 1)
            except (TypeError, ValueError):
                installments = 1
            if installments < 1:
                installments = 1

        normalized_payments.append(
            {
                "payment_type": payment_type,
                "installments": installments,
                "value_cents": value_cents,
            }
        )
        paid_cents += value_cents

    # 4) Regra de pagamento: soma ≥ total (permite troco). Sem pagamento só se total 0.
    if total_cents > 0 and not normalized_payments:
        raise ValidationError("Informe ao menos uma forma de pagamento.")
    if paid_cents < total_cents:
        raise ValidationError(
            f"A soma dos pagamentos (R$ {paid_cents / 100:.2f}) é menor que o "
            f"total da venda (R$ {total_cents / 100:.2f})."
        )
    change_cents = paid_cents - total_cents

    # 5) Persiste tudo (atômico). Ordem dos campos da venda conforme o BD.
    sale = Sale.objects.create(
        client=client,
        subtotal_cents=subtotal_cents,
        has_perc_discount=has_perc_discount,
        perc_discount=perc_discount,
        discount_cents=discount_cents,
        discount_obs=discount_obs,
        change_cents=change_cents,
        total_cents=total_cents,
        obs=obs,
    )

    for item in items:
        product = item["product"]
        quantity = item["quantity"]
        unit_price_cents = product.unit_price_cents
        item_subtotal_cents = unit_price_cents * quantity
        snapshot = ProductSnapshot.get_or_create_for(product)
        SaleItem.objects.create(
            sale=sale,
            product_snapshot=snapshot,
            quantity=quantity,
            unit_price_cents=unit_price_cents,
            subtotal_cents=item_subtotal_cents,
            # Descontos por item ficam para o módulo de promoções (v1: zero).
            has_perc_discount=False,
            perc_discount=None,
            discount_cents=0,
            total_cents=item_subtotal_cents,
        )
        # Baixa de estoque (já validado acima nesta mesma transação).
        Product.objects.filter(pk=product.pk).update(
            quantity=F("quantity") - quantity
        )

    for payment in normalized_payments:
        SalePayment.objects.create(sale=sale, **payment)

    return sale


# --- Despesas -----------------------------------------------------------------


def _month_with_day(base, months, day):
    """Data ``base`` deslocada ``months`` meses, no ``day`` (clampado ao mês).

    Ancorar no mês-base (em vez de somar sobre a data anterior) evita o acúmulo
    de clamp: o dia 31 não "gruda" no 28 depois de passar por fevereiro.
    """
    index = base.year * 12 + (base.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _first_recurrent_due(day):
    """Próxima ocorrência do dia ``day`` em diante (este mês ou o próximo)."""
    today = timezone.localdate()
    last_day = calendar.monthrange(today.year, today.month)[1]
    this_month_due = date(today.year, today.month, min(day, last_day))
    if this_month_due >= today:
        return this_month_due
    return _month_with_day(today, 1, day)


def _generate_installments(expense, *, value_cents, count, start_date, day):
    """Cria ``count`` parcelas mensais para ``expense`` (uma por mês).

    A i-ésima parcela vence no ``day`` (clampado) do mês ``start_date`` + i.
    Retorna a lista de parcelas criadas.
    """
    installments = [
        ExpenseInstallment(
            expense=expense,
            installment_current=i + 1,
            installment_total=count,
            value_cents=value_cents,
            due_date=_month_with_day(start_date, i, day),
        )
        for i in range(count)
    ]
    return ExpenseInstallment.objects.bulk_create(installments)


@transaction.atomic
def create_expense(*, name, description, recurrent, scheduled_for, value_cents,
                   installment_total, first_due_date, months_ahead):
    """Cria uma despesa e gera suas parcelas, de forma atômica.

    Parâmetros:
        name, description: dados da definição.
        recurrent: ``True`` para despesa recorrente (mensal).
        scheduled_for: dia do mês (1–31) do vencimento — obrigatório se recorrente.
        value_cents: valor (em centavos) aplicado a cada parcela gerada.
        installment_total: nº de parcelas — usado quando NÃO recorrente.
        first_due_date: ``date`` do 1º vencimento — usado quando NÃO recorrente.
        months_ahead: nº de meses a gerar — usado quando recorrente.

    O valor é o mesmo em todas as parcelas geradas (valor fixo); valores
    variáveis são ajustados depois, editando cada parcela. Levanta
    ``ValidationError`` (em PT-BR) em qualquer inconsistência; nada é gravado.
    """
    if value_cents <= 0:
        raise ValidationError("O valor da parcela deve ser maior que zero.")

    if recurrent:
        if not scheduled_for or not (1 <= scheduled_for <= 31):
            raise ValidationError(
                "Informe um dia previsto de vencimento entre 1 e 31."
            )
        count = int(months_ahead or 0)
        if count < 1:
            raise ValidationError("O horizonte deve ser de pelo menos 1 mês.")
        start_date = _first_recurrent_due(scheduled_for)
        day = scheduled_for
    else:
        if first_due_date is None:
            raise ValidationError("Informe a data do primeiro vencimento.")
        count = int(installment_total or 0)
        if count < 1:
            raise ValidationError("O número de parcelas deve ser de pelo menos 1.")
        start_date = first_due_date
        day = first_due_date.day

    expense = Expense.objects.create(
        name=name,
        description=description,
        recurrent=recurrent,
        scheduled_for=scheduled_for if recurrent else None,
    )
    _generate_installments(
        expense, value_cents=value_cents, count=count, start_date=start_date, day=day
    )
    return expense


def register_payment(installment, *, paid_value_cents, paid_at):
    """Registra (ou limpa) o pagamento de uma parcela.

    ``paid_value_cents`` 0 com ``paid_at`` ``None`` zera o pagamento (volta a
    pendente/atrasada). O ``status`` é derivado no model.
    """
    if paid_value_cents < 0:
        raise ValidationError("O valor pago não pode ser negativo.")
    installment.paid_value_cents = paid_value_cents
    installment.paid_at = paid_at
    installment.save(update_fields=["paid_value_cents", "paid_at", "updated_at"])
    return installment


# --- Notas fiscais de entrada -------------------------------------------------


def _reais_or_zero(value):
    """Converte reais → centavos, tratando vazio/``None`` como zero."""
    if value in (None, ""):
        return 0
    return reais_to_cents(value)


@transaction.atomic
def create_inbound_invoice(*, number, issue_date, delivery_date, supplier,
                           products_total, total, icms_base, icms, ipi,
                           taxes_total, freight, insurance, discount, other_costs,
                           duplicates, items):
    """Cria uma NF de entrada com suas faturas e produtos, de forma atômica.

    Os valores do cabeçalho e os montantes de cada linha chegam **em reais** e
    são convertidos para centavos aqui (via ``reais_to_cents``, ``HALF_UP``,
    nunca float). ``duplicates``/``items`` são listas de dicts parseadas do POST;
    linhas totalmente vazias (fatura sem número, produto sem código) são
    ignoradas. Levanta ``ValidationError`` (PT-BR) em qualquer inconsistência;
    nada é gravado nesse caso.
    """
    if not (number or "").strip():
        raise ValidationError("Informe o número da nota.")
    if supplier is None:
        raise ValidationError("Selecione o fornecedor.")
    if total in (None, ""):
        raise ValidationError("Informe o valor total da nota.")

    # 1) Faturas: valida linhas preenchidas (as vazias são puladas).
    duplicate_objs = []
    for index, row in enumerate(duplicates, start=1):
        due_date = row.get("due_date")
        value_raw = row.get("value")
        # Linha vazia (sem vencimento e sem valor) é ignorada.
        if due_date is None and value_raw in (None, ""):
            continue
        if due_date is None:
            raise ValidationError(f"Informe o vencimento da fatura {index}.")
        value_cents = _reais_or_zero(value_raw)
        if value_cents <= 0:
            raise ValidationError(f"Informe um valor válido para a fatura {index}.")
        duplicate_objs.append(
            InvoiceDuplicate(due_date=due_date, value_cents=value_cents)
        )

    # 2) Produtos: valida linhas preenchidas (as vazias são puladas).
    item_objs = []
    for row in items:
        code = (row.get("code") or "").strip()
        if not code:
            continue
        description = (row.get("description") or "").strip()
        if not description:
            raise ValidationError(f"Informe a descrição do produto {code}.")
        unit_type = (row.get("unit_type") or "").strip()
        if unit_type not in UnitType.values:
            raise ValidationError(f"Tipo de unidade inválido no produto {code}.")
        try:
            quantity = Decimal(row.get("quantity") or 0)
        except (ArithmeticError, TypeError, ValueError):
            raise ValidationError(f"Quantidade inválida no produto {code}.")
        if quantity <= 0:
            raise ValidationError(f"Informe a quantidade do produto {code}.")
        unit_price_cents = _reais_or_zero(row.get("unit_price"))
        total_item_cents = _reais_or_zero(row.get("total"))  # opcional
        if unit_price_cents <= 0:
            raise ValidationError(f"Informe o valor unitário do produto {code}.")
        item_objs.append(
            InvoiceItem(
                code=code,
                description=description,
                unit_type=unit_type,
                quantity=quantity,
                unit_price_cents=unit_price_cents,
                total_cents=total_item_cents,
                icms_base_cents=_reais_or_zero(row.get("icms_base")),
                icms_cents=_reais_or_zero(row.get("icms")),
                ipi_cents=_reais_or_zero(row.get("ipi")),
            )
        )

    # 3) Persiste o cabeçalho e as linhas (atômico).
    invoice = InboundInvoice.objects.create(
        number=number.strip(),
        issue_date=issue_date,
        delivery_date=delivery_date,
        supplier=supplier,
        products_total_cents=_reais_or_zero(products_total),
        total_cents=_reais_or_zero(total),
        icms_base_cents=_reais_or_zero(icms_base),
        icms_cents=_reais_or_zero(icms),
        ipi_cents=_reais_or_zero(ipi),
        taxes_total_cents=_reais_or_zero(taxes_total),
        freight_cents=_reais_or_zero(freight),
        insurance_cents=_reais_or_zero(insurance),
        discount_cents=_reais_or_zero(discount),
        other_costs_cents=_reais_or_zero(other_costs),
    )
    for dup in duplicate_objs:
        dup.invoice = invoice
    for item in item_objs:
        item.invoice = invoice
    if duplicate_objs:
        InvoiceDuplicate.objects.bulk_create(duplicate_objs)
    if item_objs:
        InvoiceItem.objects.bulk_create(item_objs)
    return invoice


# --- Processamento de NF de entrada -------------------------------------------

# Passo (em centavos) de cada estratégia de arredondamento de preço.
_ROUNDING_STEP_CENTS = {
    RoundingType.CENT: 1,
    RoundingType.CENT_10: 10,
    RoundingType.REAL: 100,
    RoundingType.REAL_2: 200,
    RoundingType.REAL_5: 500,
    RoundingType.REAL_10: 1000,
}


def round_price_cents(cents, rounding_type):
    """Arredonda um preço (em centavos) **para cima** conforme ``rounding_type``.

    É a lógica canônica de precificação da NF: multiplica-se o custo pelo
    ``Company.price_multiplier`` e arredonda-se ao próximo múltiplo do passo
    definido em ``rounding_type`` (nunca para baixo, para preservar a margem).
    ``cents`` pode ser ``Decimal``/``float``/``int``.
    """
    step = _ROUNDING_STEP_CENTS.get(rounding_type, 1)
    value = Decimal(str(cents))
    return int(math.ceil(value / step)) * step


def suggested_price_cents(item, company):
    """Preço de venda sugerido (centavos) para um item da NF, arredondado p/ cima."""
    raw = Decimal(item.unit_price_cents) * Decimal(str(company.price_multiplier))
    return round_price_cents(raw, company.rounding_type)


def nf_search_tokens(value):
    """Tokens (não vazios) de um ``nf_search_id`` (separados por ``;``)."""
    return [tok.strip() for tok in (value or "").split(";") if tok.strip()]


def format_nf_search(tokens):
    """Serializa os tokens de ``nf_search_id`` com ``;`` **ao final de cada um**.

    Ex.: ``["ABC", "ZZZ"]`` → ``"ABC;ZZZ;"``. O ``;`` terminador deixa o campo
    pronto para a próxima inserção. Retorna ``""`` quando não há tokens.
    """
    return "".join(f"{tok};" for tok in tokens)


def suggest_product_match(item):
    """Sugere o ``Product`` já cadastrado para um ``InvoiceItem``.

    Tenta, nesta ordem: (1) ``nf_search_id`` contendo o código do item como
    token exato; (2) descrição do item igual ao ``name`` ou ``description`` do
    produto (case-insensitive). Retorna ``(product, motivo)`` ou ``(None, None)``.
    """
    code = (item.code or "").strip()
    description = (item.description or "").strip()

    # 1) nf_search_id — token exato (o __icontains é só um pré-filtro).
    if code:
        for product in Product.objects.filter(nf_search_id__icontains=code):
            if code in nf_search_tokens(product.nf_search_id):
                return product, "nf_search_id"

    # 2) Descrição do item igual ao nome ou à descrição de um produto
    #    (igualdade case-insensitive).
    if description:
        product = Product.objects.filter(
            Q(name__iexact=description) | Q(description__iexact=description)
        ).first()
        if product:
            return product, "description"

    return None, None


def _item_quantity_int(item):
    """Converte a quantidade (Decimal) do item para inteiro (estoque só é inteiro)."""
    return int(item.quantity.to_integral_value(rounding=ROUND_HALF_UP))


@transaction.atomic
def process_inbound_invoice(invoice, *, decisions):
    """Processa a NF: dá entrada no estoque/preços e gera as despesas.

    Operação **única e irreversível**. ``decisions`` é uma lista (uma por item)
    de dicts validados pela view::

        {"item": InvoiceItem, "is_new": bool, "product": Product | None,
         "unit_price_cents": int, "manufacturer": Manufacturer | None}

    Para item novo, cria um ``Product`` com os dados da nota; para item
    associado, soma o estoque (``F``), sobrescreve o preço e garante o código em
    ``nf_search_id``. As ``InvoiceDuplicate`` viram **uma** ``Expense`` da NF, com
    uma parcela por fatura (numeradas por vencimento; total = nº de faturas).
    Levanta ``ValidationError`` (PT-BR); nada é gravado nesse caso.
    """
    if invoice.processed:
        raise ValidationError("Esta nota fiscal já foi processada.")

    supplier = invoice.supplier

    for decision in decisions:
        item = decision["item"]
        code = (item.code or "").strip()
        price_cents = decision["unit_price_cents"]
        if price_cents is None or price_cents <= 0:
            raise ValidationError(
                f"Informe um preço de venda válido para o produto {code}."
            )
        quantity = _item_quantity_int(item)

        if decision["is_new"]:
            manufacturer = decision.get("manufacturer")
            if manufacturer is None:
                raise ValidationError(
                    f"Selecione o fabricante do produto novo {code}."
                )
            Product.objects.create(
                name=item.description,
                manufacturer=manufacturer,
                # Código do fabricante só faz sentido p/ fornecedor mono-marca.
                manufacturer_code=code if not supplier.multiple_brands else "",
                quantity=quantity,
                unit_type=item.unit_type,
                unit_price_cents=price_cents,
                min_stock=Company.get_solo().low_stock_threshold or 0,
                nf_search_id=format_nf_search([code] if code else []),
            )
        else:
            product = decision.get("product")
            if product is None:
                raise ValidationError(
                    f"Selecione o produto associado ao item {code}."
                )
            # Garante o código do item entre os IDs de busca para futuras NFs.
            tokens = nf_search_tokens(product.nf_search_id)
            if code and code not in tokens:
                tokens.append(code)
            Product.objects.filter(pk=product.pk).update(
                quantity=F("quantity") + quantity,
                unit_price_cents=price_cents,
                nf_search_id=format_nf_search(tokens),
            )

    # Faturas → uma única despesa por NF, com uma parcela por fatura. As parcelas
    # são numeradas por ordem de vencimento; o total de parcelas é a quantidade de
    # faturas. Não usa create_expense (que gera parcelas de valor fixo/mensais):
    # aqui cada parcela tem o valor e o vencimento da sua fatura.
    duplicates = list(invoice.duplicates.order_by("due_date", "id"))
    if duplicates:
        expense = Expense.objects.create(
            name=f"NF {invoice.number} — {supplier.name}",
            description=f"Faturas da NF {invoice.number}.",
            recurrent=False,
            scheduled_for=None,
        )
        total = len(duplicates)
        ExpenseInstallment.objects.bulk_create(
            [
                ExpenseInstallment(
                    expense=expense,
                    installment_current=index,
                    installment_total=total,
                    value_cents=duplicate.value_cents,
                    due_date=duplicate.due_date,
                )
                for index, duplicate in enumerate(duplicates, start=1)
            ]
        )

    invoice.processed = True
    invoice.processed_at = timezone.now()
    invoice.save(update_fields=["processed", "processed_at"])
    return invoice
