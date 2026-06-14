from urllib.parse import urlencode

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

    # Campos permitidos para ordenação (asc/desc).
    SORT_FIELDS = ("name",)

    def _current_sort(self):
        """Sort validado (default: name asc); ignora valores fora da allowlist."""
        sort = self.request.GET.get("sort", "name")
        if sort.lstrip("-") not in self.SORT_FIELDS:
            return "name"
        return sort

    def get_queryset(self):
        qs = super().get_queryset()
        name = self.request.GET.get("name", "").strip()
        if name:
            qs = qs.filter(name__icontains=name)
        return qs.order_by(self._current_sort())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        filters = {"name": self.request.GET.get("name", "").strip()}
        current = self._current_sort()
        active = {key: value for key, value in filters.items() if value}

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
