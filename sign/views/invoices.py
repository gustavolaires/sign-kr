from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ..forms import InboundInvoiceForm, InvoiceDuplicateForm, InvoiceItemForm
from ..models import (
    Company,
    InboundInvoice,
    InvoiceDuplicate,
    InvoiceItem,
    Manufacturer,
    Product,
    Supplier,
    UnitType,
)
from ..services import (
    create_inbound_invoice,
    process_inbound_invoice,
    reais_to_cents,
    suggest_product_match,
    suggested_price_cents,
)


def _redirect_if_processed(request, invoice):
    """Bloqueia alterações numa NF já processada (imutável). Retorna o redirect
    para o detalhe, ou ``None`` se ainda for editável."""
    if invoice.processed:
        messages.error(
            request,
            "Esta nota fiscal já foi processada e não pode mais ser alterada.",
        )
        return redirect("sign:invoice_detail", pk=invoice.pk)
    return None


class InboundInvoiceListView(ListView):
    model = InboundInvoice
    template_name = "sign/invoices/list.html"
    context_object_name = "invoices"

    # Campos permitidos para ordenação (asc/desc).
    SORT_FIELDS = ("number", "issue_date", "delivery_date", "created_at")

    def _current_sort(self):
        """Sort validado (default: -created_at); ignora valores fora da allowlist."""
        sort = self.request.GET.get("sort", "-created_at")
        if sort.lstrip("-") not in self.SORT_FIELDS:
            return "-created_at"
        return sort

    def get_queryset(self):
        qs = super().get_queryset().select_related("supplier")
        params = self.request.GET
        number = params.get("number", "").strip()
        supplier = params.get("supplier", "").strip()
        issue_date = parse_date(params.get("issue_date", "").strip() or "")
        delivery_date = parse_date(params.get("delivery_date", "").strip() or "")

        if number:
            qs = qs.filter(number__icontains=number)
        if supplier.isdigit():
            qs = qs.filter(supplier_id=supplier)
        if issue_date:
            qs = qs.filter(issue_date=issue_date)
        if delivery_date:
            qs = qs.filter(delivery_date=delivery_date)

        return qs.order_by(self._current_sort())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        filters = {
            "number": params.get("number", "").strip(),
            "supplier": params.get("supplier", "").strip(),
            "issue_date": params.get("issue_date", "").strip(),
            "delivery_date": params.get("delivery_date", "").strip(),
        }
        current = self._current_sort()
        active = {key: value for key, value in filters.items() if value}

        # Links de ordenação por coluna (preservam os filtros e alternam asc/desc).
        sort_links = {}
        sort_state = {}
        for field in self.SORT_FIELDS:
            if current == field:
                nxt, state = "-" + field, "asc"
            elif current == "-" + field:
                nxt, state = field, "desc"
            else:
                nxt, state = field, None
            sort_links[field] = "?" + urlencode({**active, "sort": nxt})
            sort_state[field] = state

        ctx["filters"] = filters
        ctx["suppliers"] = Supplier.objects.all()
        ctx["current_sort"] = current
        ctx["sort_links"] = sort_links
        ctx["sort_state"] = sort_state
        ctx["has_filters"] = bool(active)
        return ctx


class InboundInvoiceDetailView(DetailView):
    model = InboundInvoice
    template_name = "sign/invoices/detail.html"
    context_object_name = "invoice"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["duplicates"] = self.object.duplicates.all()
        ctx["items"] = self.object.items.all()
        return ctx


def _collect_rows(post, prefix, keys):
    """Monta uma lista de dicts a partir de inputs paralelos do POST.

    ``keys`` mapeia a chave do dict → sufixo do input (``prefix`` + sufixo).
    Datas (chave ``due_date``) são parseadas para ``date`` ou ``None``.
    """
    lists = {key: post.getlist(prefix + suffix) for key, suffix in keys.items()}
    count = max((len(values) for values in lists.values()), default=0)
    rows = []
    for i in range(count):
        row = {}
        for key in keys:
            value = lists[key][i] if i < len(lists[key]) else ""
            if key == "due_date":
                value = parse_date(value) if value else None
            row[key] = value
        rows.append(row)
    return rows


class InboundInvoiceCreateView(CreateView):
    model = InboundInvoice
    form_class = InboundInvoiceForm
    template_name = "sign/invoices/form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Siglas de unidade para o <select> das linhas de produto inline.
        ctx["unit_types"] = UnitType.values
        return ctx

    def form_valid(self, form):
        data = form.cleaned_data
        duplicates = _collect_rows(
            self.request.POST,
            "dup_",
            {
                "due_date": "due_date",
                "value": "value",
            },
        )
        items = _collect_rows(
            self.request.POST,
            "item_",
            {
                "code": "code",
                "description": "description",
                "unit_type": "unit_type",
                "quantity": "quantity",
                "unit_price": "unit_price",
                "total": "total",
                "icms_base": "icms_base",
                "icms": "icms",
                "ipi": "ipi",
            },
        )
        try:
            self.object = create_inbound_invoice(
                number=data["number"],
                issue_date=data.get("issue_date"),
                delivery_date=data.get("delivery_date"),
                supplier=data["supplier"],
                products_total=data.get("products_total"),
                total=data.get("total"),
                icms_base=data.get("icms_base"),
                icms=data.get("icms"),
                ipi=data.get("ipi"),
                taxes_total=data.get("taxes_total"),
                freight=data.get("freight"),
                insurance=data.get("insurance"),
                discount=data.get("discount"),
                other_costs=data.get("other_costs"),
                duplicates=duplicates,
                items=items,
            )
        except ValidationError as exc:
            # Mensagens (PT-BR) do serviço viram erros não-associados do form.
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Nota fiscal criada com sucesso.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.pk})


class InboundInvoiceUpdateView(SuccessMessageMixin, UpdateView):
    model = InboundInvoice
    form_class = InboundInvoiceForm
    template_name = "sign/invoices/form.html"
    success_message = "Nota fiscal atualizada com sucesso."

    def dispatch(self, request, *args, **kwargs):
        invoice = get_object_or_404(InboundInvoice, pk=kwargs["pk"])
        return _redirect_if_processed(request, invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.pk})


class InboundInvoiceDeleteView(DeleteView):
    model = InboundInvoice
    template_name = "sign/invoices/confirm_delete.html"
    success_url = reverse_lazy("sign:invoice_list")
    context_object_name = "invoice"

    def dispatch(self, request, *args, **kwargs):
        invoice = get_object_or_404(InboundInvoice, pk=kwargs["pk"])
        return _redirect_if_processed(request, invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def form_valid(self, form):
        # CASCADE remove faturas e produtos vinculados.
        messages.success(self.request, "Nota fiscal excluída com sucesso.")
        return super().form_valid(form)


def invoice_process(request, pk):
    """Tela de confirmação e execução do processamento da NF de entrada.

    GET monta as sugestões (associação item→produto + preço sugerido); POST
    coleta as decisões do usuário e delega ao serviço ``process_inbound_invoice``
    (atômico). Segue o padrão de ação POST de ``installment_pay``.
    """
    invoice = get_object_or_404(
        InboundInvoice.objects.select_related("supplier", "supplier__manufacturer"),
        pk=pk,
    )
    if invoice.processed:
        messages.error(request, "Esta nota fiscal já foi processada.")
        return redirect("sign:invoice_detail", pk=invoice.pk)

    company = Company.get_solo()
    supplier = invoice.supplier
    items = list(invoice.items.all())
    duplicates = list(invoice.duplicates.all())

    if request.method == "POST":
        decisions = []
        for item in items:
            key = str(item.pk)
            is_new = bool(request.POST.get(f"item_is_new_{key}"))
            price_raw = (request.POST.get(f"item_price_{key}") or "").strip()
            try:
                price_cents = reais_to_cents(price_raw) if price_raw else 0
            except (ArithmeticError, ValueError):
                price_cents = 0
            product = manufacturer = None
            if is_new:
                man_id = request.POST.get(f"item_manufacturer_{key}", "")
                if man_id.isdigit():
                    manufacturer = Manufacturer.objects.filter(pk=man_id).first()
            else:
                prod_id = request.POST.get(f"item_product_{key}", "")
                if prod_id.isdigit():
                    product = Product.objects.filter(pk=prod_id).first()
            decisions.append(
                {
                    "item": item,
                    "is_new": is_new,
                    "product": product,
                    "unit_price_cents": price_cents,
                    "manufacturer": manufacturer,
                }
            )
        try:
            process_inbound_invoice(invoice, decisions=decisions)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            rows = _rows_from_decisions(decisions)
        else:
            messages.success(request, "Nota fiscal processada com sucesso.")
            return redirect("sign:invoice_detail", pk=invoice.pk)
    else:
        rows = _suggestion_rows(items, supplier, company)

    context = {
        "invoice": invoice,
        "rows": rows,
        "duplicates": duplicates,
        "products": Product.objects.filter(is_active=True).order_by("name"),
        "manufacturers": Manufacturer.objects.order_by("name"),
        "company": company,
    }
    return render(request, "sign/invoices/process.html", context)


def _suggestion_rows(items, supplier, company):
    """Linhas iniciais da tela de confirmação (associação + preço sugeridos)."""
    default_manufacturer_id = supplier.manufacturer_id or None
    rows = []
    for item in items:
        product, reason = suggest_product_match(item)
        price_cents = suggested_price_cents(item, company)
        rows.append(
            {
                "item": item,
                "selected_product_id": product.pk if product else None,
                "is_new": product is None,
                "price_reais": f"{price_cents / 100:.2f}",
                "manufacturer_id": default_manufacturer_id,
                "match_reason": reason,
            }
        )
    return rows


def _rows_from_decisions(decisions):
    """Reconstrói as linhas da tela a partir das decisões (re-render após erro)."""
    rows = []
    for d in decisions:
        rows.append(
            {
                "item": d["item"],
                "selected_product_id": d["product"].pk if d["product"] else None,
                "is_new": d["is_new"],
                "price_reais": f"{(d['unit_price_cents'] or 0) / 100:.2f}",
                "manufacturer_id": (
                    d["manufacturer"].pk if d["manufacturer"] else None
                ),
                "match_reason": None,
            }
        )
    return rows


# --- Faturas (duplicatas) — CRUD só dentro da NF ------------------------------


class InvoiceDuplicateCreateView(SuccessMessageMixin, CreateView):
    model = InvoiceDuplicate
    form_class = InvoiceDuplicateForm
    template_name = "sign/invoices/duplicates/form.html"
    success_message = "Fatura adicionada com sucesso."

    def dispatch(self, request, *args, **kwargs):
        self.invoice = get_object_or_404(InboundInvoice, pk=kwargs["invoice_pk"])
        return _redirect_if_processed(request, self.invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def form_valid(self, form):
        form.instance.invoice = self.invoice
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.invoice
        return ctx

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.invoice.pk})


class InvoiceDuplicateUpdateView(SuccessMessageMixin, UpdateView):
    model = InvoiceDuplicate
    form_class = InvoiceDuplicateForm
    template_name = "sign/invoices/duplicates/form.html"
    success_message = "Fatura atualizada com sucesso."

    def dispatch(self, request, *args, **kwargs):
        duplicate = get_object_or_404(InvoiceDuplicate, pk=kwargs["pk"])
        return _redirect_if_processed(request, duplicate.invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.object.invoice
        return ctx

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.invoice.pk})


class InvoiceDuplicateDeleteView(DeleteView):
    model = InvoiceDuplicate
    template_name = "sign/invoices/duplicates/confirm_delete.html"
    context_object_name = "duplicate"

    def dispatch(self, request, *args, **kwargs):
        duplicate = get_object_or_404(InvoiceDuplicate, pk=kwargs["pk"])
        return _redirect_if_processed(request, duplicate.invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.object.invoice
        return ctx

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.invoice.pk})

    def form_valid(self, form):
        messages.success(self.request, "Fatura excluída com sucesso.")
        return super().form_valid(form)


# --- Produtos da NF — CRUD só dentro da NF ------------------------------------


class InvoiceItemCreateView(SuccessMessageMixin, CreateView):
    model = InvoiceItem
    form_class = InvoiceItemForm
    template_name = "sign/invoices/items/form.html"
    success_message = "Produto adicionado com sucesso."

    def dispatch(self, request, *args, **kwargs):
        self.invoice = get_object_or_404(InboundInvoice, pk=kwargs["invoice_pk"])
        return _redirect_if_processed(request, self.invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def form_valid(self, form):
        form.instance.invoice = self.invoice
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.invoice
        return ctx

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.invoice.pk})


class InvoiceItemUpdateView(SuccessMessageMixin, UpdateView):
    model = InvoiceItem
    form_class = InvoiceItemForm
    template_name = "sign/invoices/items/form.html"
    success_message = "Produto atualizado com sucesso."

    def dispatch(self, request, *args, **kwargs):
        item = get_object_or_404(InvoiceItem, pk=kwargs["pk"])
        return _redirect_if_processed(request, item.invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.object.invoice
        return ctx

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.invoice.pk})


class InvoiceItemDeleteView(DeleteView):
    model = InvoiceItem
    template_name = "sign/invoices/items/confirm_delete.html"
    context_object_name = "item"

    def dispatch(self, request, *args, **kwargs):
        item = get_object_or_404(InvoiceItem, pk=kwargs["pk"])
        return _redirect_if_processed(request, item.invoice) or super().dispatch(
            request, *args, **kwargs
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.object.invoice
        return ctx

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.invoice.pk})

    def form_valid(self, form):
        messages.success(self.request, "Produto excluído com sucesso.")
        return super().form_valid(form)
