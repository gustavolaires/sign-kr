from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import ManufacturerForm, ProductForm
from .models import Manufacturer, Product


# --- Produtos ---------------------------------------------------------------


class ProductListView(ListView):
    model = Product
    template_name = "sign/products/list.html"
    context_object_name = "products"

    def get_queryset(self):
        return Product.objects.select_related("manufacturer")


class ProductDetailView(DetailView):
    model = Product
    template_name = "sign/products/detail.html"
    context_object_name = "product"


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


# --- Fabricantes ------------------------------------------------------------


class ManufacturerListView(ListView):
    model = Manufacturer
    template_name = "sign/manufacturers/list.html"
    context_object_name = "manufacturers"


class ManufacturerCreateView(SuccessMessageMixin, CreateView):
    model = Manufacturer
    form_class = ManufacturerForm
    template_name = "sign/manufacturers/form.html"
    success_url = reverse_lazy("sign:manufacturer_list")
    success_message = "Fabricante criado com sucesso."


class ManufacturerUpdateView(SuccessMessageMixin, UpdateView):
    model = Manufacturer
    form_class = ManufacturerForm
    template_name = "sign/manufacturers/form.html"
    success_url = reverse_lazy("sign:manufacturer_list")
    success_message = "Fabricante atualizado com sucesso."


class ManufacturerDeleteView(DeleteView):
    model = Manufacturer
    template_name = "sign/manufacturers/confirm_delete.html"
    success_url = reverse_lazy("sign:manufacturer_list")

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                "Não é possível excluir: há produtos vinculados a este fabricante.",
            )
            return redirect("sign:manufacturer_list")
        messages.success(self.request, "Fabricante excluído com sucesso.")
        return response
