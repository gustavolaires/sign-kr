from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    UpdateView,
)

from ..forms import ManufacturerForm
from ..models import Manufacturer


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
