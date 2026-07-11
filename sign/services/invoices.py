"""Notas fiscais de entrada: criação, precificação e processamento.

Cobre a criação atômica da NF (cabeçalho + faturas + produtos, valores em reais
convertidos para centavos aqui), a precificação sugerida (arredondamento para
cima, para preservar margem), o casamento com produtos já cadastrados e o
processamento (entrada de estoque/preços + geração das despesas). Também expõe
os helpers de ``nf_search_id`` (``nf_search_tokens``/``format_nf_search``),
reusados pela importação via CSV.
"""

import math
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from ..models import (
    Company,
    Expense,
    ExpenseInstallment,
    InboundInvoice,
    InvoiceDuplicate,
    InvoiceItem,
    Product,
    RoundingType,
    UnitType,
)
from .money import reais_to_cents


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
    RoundingType.CENT_50: 50,
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
    # Estoque mínimo default (empresa) resolvido uma única vez, fora do loop.
    default_min_stock = Company.get_solo().low_stock_threshold or 0

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
                min_stock=default_min_stock,
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
