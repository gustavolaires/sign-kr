from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ..forms import ProductForm
from ..models import Product


class ProductListView(ListView):
    model = Product
    template_name = "sign/products/list.html"
    context_object_name = "products"

    # Campos permitidos para ordenação (asc/desc) e a expressão real de ordenação.
    SORT_FIELDS = ("name", "barcode", "manufacturer")
    SORT_EXPRESSIONS = {
        "name": "name",
        "barcode": "barcode",
        "manufacturer": "manufacturer__name",
    }

    def _current_sort(self):
        """Sort validado (default: name asc); ignora valores fora da allowlist."""
        sort = self.request.GET.get("sort", "name")
        if sort.lstrip("-") not in self.SORT_FIELDS:
            return "name"
        return sort

    def _order_by(self, sort):
        """Traduz a chave de sort para a expressão de ordenação do ORM."""
        key = sort.lstrip("-")
        prefix = "-" if sort.startswith("-") else ""
        return prefix + self.SORT_EXPRESSIONS[key]

    # Filtro de status: padrão mostra só os ativos; valores fora da allowlist
    # caem no padrão "active".
    STATUS_CHOICES = ("active", "inactive", "all")

    def _current_status(self):
        status = self.request.GET.get("status", "active").strip()
        return status if status in self.STATUS_CHOICES else "active"

    def get_queryset(self):
        qs = Product.objects.select_related("manufacturer")
        params = self.request.GET
        name = params.get("name", "").strip()
        barcode = params.get("barcode", "").strip()
        manufacturer = params.get("manufacturer", "").strip()
        manufacturer_code = params.get("manufacturer_code", "").strip()
        status = self._current_status()

        if name:
            qs = qs.filter(name__icontains=name)
        if barcode:
            qs = qs.filter(barcode__icontains=barcode)
        if manufacturer:
            qs = qs.filter(manufacturer__name__icontains=manufacturer)
        if manufacturer_code:
            qs = qs.filter(manufacturer_code__icontains=manufacturer_code)
        if status == "active":
            qs = qs.filter(is_active=True)
        elif status == "inactive":
            qs = qs.filter(is_active=False)

        return qs.order_by(self._order_by(self._current_sort()))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        status = self._current_status()
        filters = {
            "name": params.get("name", "").strip(),
            "barcode": params.get("barcode", "").strip(),
            "manufacturer": params.get("manufacturer", "").strip(),
            "manufacturer_code": params.get("manufacturer_code", "").strip(),
            "status": status,
        }
        current = self._current_sort()
        # Filtros de texto vazios são omitidos da query string; o status só é
        # preservado quando difere do padrão ("active").
        active = {
            key: value
            for key, value in filters.items()
            if key != "status" and value
        }
        if status != "active":
            active["status"] = status

        # Links de ordenação por coluna (preservam os filtros ativos e alternam asc/desc).
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
        ctx["current_sort"] = current
        ctx["sort_links"] = sort_links
        ctx["sort_state"] = sort_state
        ctx["has_filters"] = bool(active)
        return ctx


class ProductDetailView(DetailView):
    model = Product
    template_name = "sign/products/detail.html"
    context_object_name = "product"


class ProductToggleActiveView(View):
    """Alterna o status ativo/inativo do produto (POST) e volta ao detalhe."""

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        product.is_active = not product.is_active
        product.save(update_fields=["is_active"])
        messages.success(
            request,
            "Produto ativado." if product.is_active else "Produto desativado.",
        )
        return redirect("sign:product_detail", pk=pk)


class ProductCreateView(SuccessMessageMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "sign/products/form.html"
    success_url = reverse_lazy("sign:product_list")
    success_message = "Produto criado com sucesso."


class ProductUpdateView(SuccessMessageMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = "sign/products/form.html"
    success_message = "Produto atualizado com sucesso."

    def get_success_url(self):
        return reverse("sign:product_detail", kwargs={"pk": self.object.pk})


class ProductDeleteView(DeleteView):
    model = Product
    template_name = "sign/products/confirm_delete.html"
    success_url = reverse_lazy("sign:product_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Produto excluído com sucesso.")
        return response
