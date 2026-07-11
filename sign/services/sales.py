"""Regras de negócio do checkout de vendas.

Concentra a matemática monetária (em centavos, com ``Decimal``/
``ROUND_HALF_UP``) e a criação atômica da venda. As validações levantam
``ValidationError`` com mensagens em PT-BR, capturadas pela view do checkout.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from ..models import (
    PaymentType,
    Product,
    ProductSnapshot,
    Sale,
    SaleItem,
    SalePayment,
)
from .money import reais_to_cents


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
