"""Regras de negócio do checkout de vendas.

Concentra toda a matemática monetária (em centavos, com ``Decimal``/
``ROUND_HALF_UP``) e a criação atômica da venda. As validações levantam
``ValidationError`` com mensagens em PT-BR, capturadas pela view do checkout.
"""

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import (
    Expense,
    ExpenseInstallment,
    InboundInvoice,
    InvoiceDuplicate,
    InvoiceItem,
    PaymentType,
    Product,
    ProductSnapshot,
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
