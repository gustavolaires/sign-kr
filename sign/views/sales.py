from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView

from ..cart import COOKIE_NAME, Cart
from ..forms import SaleForm
from ..models import PaymentType, Sale
from ..search import filter_unaccent
from ..services import compute_quote_amounts, create_sale

# Formatos de comprovante suportados (58mm térmico / A4).
RECEIPT_FORMATS = {"58mm", "a4"}
DEFAULT_RECEIPT_FORMAT = "58mm"


def _valid_format(raw):
    """Normaliza o formato do comprovante (fallback para o padrão 58mm)."""
    return raw if raw in RECEIPT_FORMATS else DEFAULT_RECEIPT_FORMAT


def _calc_items(items):
    """Itens (rótulo + subtotal em centavos) para a calculadora de desconto.

    Serializável em JSON para o ``checkout.js`` montar um slider por produto.
    """
    calc = []
    for item in items:
        product = item["product"]
        label = product.name
        if product.manufacturer_code:
            label = f"[{product.manufacturer_code}] {label}"
        calc.append(
            {
                "label": label,
                "subtotal_cents": product.unit_price_cents * item["quantity"],
            }
        )
    return calc


def _receipt_context(*, mode, op_label, doc_label, number, created_at, client,
                     items, payments, subtotal, discount, total, change,
                     has_perc_discount, perc_discount, obs, fmt,
                     discount_obs="", sale_pk=None, hidden_fields=None):
    """Empacota o contexto normalizado consumido por ``receipt.html``.

    Serve tanto o comprovante de venda (``mode="sale"``) quanto o orçamento
    (``mode="quote"``); ``items``/``payments`` são objetos com atributos neutros.
    """
    return {
        "mode": mode,
        "op_label": op_label,
        "doc_label": doc_label,
        "number": number,
        "created_at": created_at,
        "client": client,
        "items": items,
        "payments": payments,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "change": change,
        "has_perc_discount": has_perc_discount,
        "perc_discount": perc_discount,
        "obs": obs,
        "discount_obs": discount_obs,
        "fmt": fmt,
        "sale_pk": sale_pk,
        "hidden_fields": hidden_fields or [],
    }


def _parse_decimal(raw):
    """Converte texto em ``Decimal``, aceitando vírgula ou ponto; vazio = 0."""
    raw = (raw or "").strip().replace(",", ".")
    if raw == "":
        return Decimal("0")
    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ValidationError("Valor numérico inválido.")


def _collect_payments(request):
    """Monta a lista de pagamentos a partir das listas paralelas do POST.

    Ignora linhas totalmente vazias (sem forma e sem valor).
    """
    types = request.POST.getlist("payment_type")
    values = request.POST.getlist("payment_value")
    installments = request.POST.getlist("payment_installments")
    payments = []
    for i, ptype in enumerate(types):
        value = values[i] if i < len(values) else ""
        inst = installments[i] if i < len(installments) else "1"
        if not ptype and not (value or "").strip():
            continue
        payments.append(
            {"payment_type": ptype, "value": value, "installments": inst}
        )
    return payments


def checkout(request):
    """Tela de finalização da venda (passo seguinte ao carrinho).

    GET renderiza o resumo do carrinho + cliente/desconto/pagamentos. POST
    delega a criação ao serviço atômico ``create_sale`` e, em sucesso, limpa o
    cookie do carrinho e redireciona para o detalhe da venda.
    """
    cart = Cart(request)
    items = cart.items()
    # Totais derivados dos itens já buscados, evitando novas queries de produto.
    cart_total_cents = sum(item["total_cents"] for item in items)
    cart_total = cart_total_cents / 100

    if request.method != "POST":
        if not items:
            messages.error(request, "Seu carrinho está vazio.")
            return redirect("sign:cart_detail")
        return render(
            request,
            "sign/sales/checkout.html",
            {
                "form": SaleForm(),
                "cart_items": items,
                "calc_items": _calc_items(items),
                "cart_total": cart_total,
                "cart_total_cents": cart_total_cents,
                "payment_types": PaymentType.choices,
                "payments": [],
                "discount_mode": "value",
                "discount_amount": "",
            },
        )

    form = SaleForm(request.POST)
    discount_mode = request.POST.get("discount_mode", "value")
    discount_amount = request.POST.get("discount_amount", "")
    payments = _collect_payments(request)

    def rerender():
        return render(
            request,
            "sign/sales/checkout.html",
            {
                "form": form,
                "cart_items": items,
                "calc_items": _calc_items(items),
                "cart_total": cart_total,
                "cart_total_cents": cart_total_cents,
                "payment_types": PaymentType.choices,
                "payments": payments,
                "discount_mode": discount_mode,
                "discount_amount": discount_amount,
            },
        )

    # "Voltar" a partir do orçamento: apenas repõe o formulário preenchido.
    if request.POST.get("intent") == "edit":
        return rerender()

    if not form.is_valid():
        return rerender()

    try:
        discount_input = _parse_decimal(discount_amount)
        service_payments = [
            {
                "payment_type": p["payment_type"],
                "installments": p["installments"],
                "value": _parse_decimal(p["value"]),
            }
            for p in payments
        ]
        sale = create_sale(
            cart=cart,
            client=form.cleaned_data["client"],
            has_perc_discount=(discount_mode == "percent"),
            discount_input=discount_input,
            payments=service_payments,
            obs=form.cleaned_data["obs"],
            discount_obs=form.cleaned_data["discount_obs"],
        )
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return rerender()

    messages.success(request, f"Venda #{sale.pk} finalizada com sucesso.")
    response = redirect("sign:sale_detail", pk=sale.pk)
    response.delete_cookie(COOKIE_NAME)
    return response


class SaleListView(ListView):
    model = Sale
    template_name = "sign/sales/list.html"
    context_object_name = "sales"
    paginate_by = 50

    def get_queryset(self):
        qs = super().get_queryset().select_related("client")
        params = self.request.GET
        client = params.get("client", "").strip()
        date_from = params.get("date_from", "").strip()
        date_to = params.get("date_to", "").strip()

        if client:
            qs = filter_unaccent(qs, "client__name", client)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        return qs.order_by("-id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        filters = {
            "client": params.get("client", "").strip(),
            "date_from": params.get("date_from", "").strip(),
            "date_to": params.get("date_to", "").strip(),
        }
        ctx["filters"] = filters
        ctx["has_filters"] = any(filters.values())
        return ctx


class SaleDetailView(DetailView):
    model = Sale
    template_name = "sign/sales/detail.html"
    context_object_name = "sale"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("client")
            .prefetch_related("items__product_snapshot", "payments")
        )


def sale_receipt(request, pk):
    """Comprovante (não fiscal) da venda, imprimível em 58mm ou A4.

    O formato vem do querystring ``?format=`` (default 58mm); a impressão e o
    "salvar como PDF" usam o diálogo nativo (``window.print()``) no template.
    """
    sale = get_object_or_404(
        Sale.objects.select_related("client").prefetch_related(
            "items__product_snapshot", "payments"
        ),
        pk=pk,
    )
    items = [
        SimpleNamespace(
            barcode=si.product_snapshot.barcode,
            name=si.product_snapshot.name,
            manufacturer_code=si.product_snapshot.manufacturer_code,
            manufacturer_name=si.product_snapshot.manufacturer_name,
            unit_type=si.product_snapshot.unit_type,
            quantity=si.quantity,
            unit_price=si.unit_price,
            total=si.total,
        )
        for si in sale.items.all()
    ]
    payments = [
        SimpleNamespace(
            label=p.get_payment_type_display(),
            installments=p.installments,
            value=p.value,
        )
        for p in sale.payments.all()
    ]
    context = _receipt_context(
        mode="sale",
        op_label="Venda",
        doc_label="Comprovante",
        number=sale.pk,
        created_at=sale.created_at,
        client=sale.client,
        items=items,
        payments=payments,
        subtotal=sale.subtotal,
        discount=sale.discount,
        total=sale.total,
        change=sale.change,
        has_perc_discount=sale.has_perc_discount,
        perc_discount=sale.perc_discount,
        obs=sale.obs,
        discount_obs=sale.discount_obs,
        fmt=_valid_format(request.GET.get("format", DEFAULT_RECEIPT_FORMAT)),
        sale_pk=sale.pk,
    )
    return render(request, "sign/sales/receipt.html", context)


def _quote_hidden_fields(post):
    """Pares (nome, valor) do POST do checkout para re-postar do orçamento.

    Expande campos multivalorados (``payment_*``) e descarta o CSRF e os campos
    de controle do próprio orçamento (``format``/``intent``).
    """
    skip = {"csrfmiddlewaretoken", "format", "intent"}
    fields = []
    for key in post:
        if key in skip:
            continue
        for value in post.getlist(key):
            fields.append((key, value))
    return fields


def sale_quote(request):
    """Orçamento: mesmo comprovante, montado a partir dos dados do checkout.

    Recebe o POST do formulário de checkout e monta a pré-visualização
    imprimível **sem persistir nada** (cálculo lenient em
    ``compute_quote_amounts``). Difere do comprovante de venda apenas no rótulo
    da operação (``Orçamento``). Trocar formato / voltar re-postam os dados.
    """
    if request.method != "POST":
        return redirect("sign:cart_detail")

    cart = Cart(request)
    cart_items = cart.items()
    if not cart_items:
        messages.error(request, "Seu carrinho está vazio.")
        return redirect("sign:cart_detail")

    form = SaleForm(request.POST)
    client = form.cleaned_data.get("client") if form.is_valid() else None
    obs = request.POST.get("obs", "")
    discount_obs = request.POST.get("discount_obs", "")
    discount_mode = request.POST.get("discount_mode", "value")
    has_perc_discount = discount_mode == "percent"
    try:
        discount_input = _parse_decimal(request.POST.get("discount_amount", ""))
    except ValidationError:
        discount_input = Decimal("0")

    service_payments = []
    for p in _collect_payments(request):
        try:
            value = _parse_decimal(p["value"])
        except ValidationError:
            value = Decimal("0")
        service_payments.append(
            {
                "payment_type": p["payment_type"],
                "installments": p["installments"],
                "value": value,
            }
        )

    (subtotal_cents, discount_cents, total_cents, change_cents, perc_discount,
     normalized_payments) = compute_quote_amounts(
        items=cart_items,
        has_perc_discount=has_perc_discount,
        discount_input=discount_input,
        payments=service_payments,
    )

    items = [
        SimpleNamespace(
            barcode=item["product"].barcode,
            name=item["product"].name,
            manufacturer_code=item["product"].manufacturer_code,
            manufacturer_name=item["product"].manufacturer.name,
            unit_type=item["product"].unit_type,
            quantity=item["quantity"],
            unit_price=item["unit_price"],
            total=item["total_price"],
        )
        for item in cart_items
    ]
    payments = [
        SimpleNamespace(
            label=PaymentType(p["payment_type"]).label,
            installments=p["installments"],
            value=p["value_cents"] / 100,
        )
        for p in normalized_payments
    ]

    context = _receipt_context(
        mode="quote",
        op_label="Orçamento",
        doc_label="Orçamento",
        number=None,
        created_at=timezone.now(),
        client=client,
        items=items,
        payments=payments,
        subtotal=subtotal_cents / 100,
        discount=discount_cents / 100,
        total=total_cents / 100,
        change=change_cents / 100,
        has_perc_discount=has_perc_discount,
        perc_discount=perc_discount,
        obs=obs,
        discount_obs=discount_obs,
        fmt=_valid_format(request.POST.get("format", DEFAULT_RECEIPT_FORMAT)),
        hidden_fields=_quote_hidden_fields(request.POST),
    )
    return render(request, "sign/sales/receipt.html", context)
