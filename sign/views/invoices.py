from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
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
    InboundInvoice,
    InvoiceDuplicate,
    InvoiceItem,
    Supplier,
    UnitType,
)
from ..services import create_inbound_invoice


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

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.pk})


class InboundInvoiceDeleteView(DeleteView):
    model = InboundInvoice
    template_name = "sign/invoices/confirm_delete.html"
    success_url = reverse_lazy("sign:invoice_list")
    context_object_name = "invoice"

    def form_valid(self, form):
        # CASCADE remove faturas e produtos vinculados.
        messages.success(self.request, "Nota fiscal excluída com sucesso.")
        return super().form_valid(form)


# --- Faturas (duplicatas) — CRUD só dentro da NF ------------------------------


class InvoiceDuplicateCreateView(SuccessMessageMixin, CreateView):
    model = InvoiceDuplicate
    form_class = InvoiceDuplicateForm
    template_name = "sign/invoices/duplicates/form.html"
    success_message = "Fatura adicionada com sucesso."

    def dispatch(self, request, *args, **kwargs):
        self.invoice = get_object_or_404(InboundInvoice, pk=kwargs["invoice_pk"])
        return super().dispatch(request, *args, **kwargs)

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
        return super().dispatch(request, *args, **kwargs)

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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invoice"] = self.object.invoice
        return ctx

    def get_success_url(self):
        return reverse("sign:invoice_detail", kwargs={"pk": self.object.invoice.pk})

    def form_valid(self, form):
        messages.success(self.request, "Produto excluído com sucesso.")
        return super().form_valid(form)
