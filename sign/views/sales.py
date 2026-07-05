from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView

from ..cart import COOKIE_NAME, Cart
from ..forms import SaleForm
from ..models import PaymentType, Sale
from ..services import create_sale

# Formatos de comprovante suportados (58mm térmico / A4).
RECEIPT_FORMATS = {"58mm", "a4"}
DEFAULT_RECEIPT_FORMAT = "58mm"


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
                "cart_total": cart.total_price(),
                "cart_total_cents": cart.total_price_cents(),
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
                "cart_total": cart.total_price(),
                "cart_total_cents": cart.total_price_cents(),
                "payment_types": PaymentType.choices,
                "payments": payments,
                "discount_mode": discount_mode,
                "discount_amount": discount_amount,
            },
        )

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
            qs = qs.filter(client__name__icontains=client)
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
    fmt = request.GET.get("format", DEFAULT_RECEIPT_FORMAT)
    if fmt not in RECEIPT_FORMATS:
        fmt = DEFAULT_RECEIPT_FORMAT
    return render(request, "sign/sales/receipt.html", {"sale": sale, "fmt": fmt})
