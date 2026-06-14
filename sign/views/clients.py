from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ..forms import ClientForm, _only_digits
from ..models import Client, PersonType


class ClientListView(ListView):
    model = Client
    template_name = "sign/clients/list.html"
    context_object_name = "clients"

    # Campos permitidos para ordenação (asc/desc).
    SORT_FIELDS = ("name", "cpf_cnpj")

    def _current_sort(self):
        """Sort validado (default: name asc); ignora valores fora da allowlist."""
        sort = self.request.GET.get("sort", "name")
        if sort.lstrip("-") not in self.SORT_FIELDS:
            return "name"
        return sort

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.GET
        name = params.get("name", "").strip()
        person_type = params.get("person_type", "").strip()
        cpf_cnpj = params.get("cpf_cnpj", "").strip()
        email = params.get("email", "").strip()

        if name:
            qs = qs.filter(name__icontains=name)
        if person_type:
            qs = qs.filter(person_type=person_type)
        # O CPF/CNPJ é gravado só com dígitos; busca pela parte numérica digitada.
        cpf_digits = _only_digits(cpf_cnpj)
        if cpf_digits:
            qs = qs.filter(cpf_cnpj__icontains=cpf_digits)
        if email:
            qs = qs.filter(email__icontains=email)

        return qs.order_by(self._current_sort())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        filters = {
            "name": params.get("name", "").strip(),
            "person_type": params.get("person_type", "").strip(),
            "cpf_cnpj": params.get("cpf_cnpj", "").strip(),
            "email": params.get("email", "").strip(),
        }
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
        ctx["person_type_choices"] = PersonType.choices
        ctx["current_sort"] = current
        ctx["sort_links"] = sort_links
        ctx["sort_state"] = sort_state
        ctx["has_filters"] = bool(active)
        return ctx


class ClientDetailView(DetailView):
    model = Client
    template_name = "sign/clients/detail.html"
    context_object_name = "client"


class ClientCreateView(SuccessMessageMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = "sign/clients/form.html"
    success_url = reverse_lazy("sign:client_list")
    success_message = "Cliente criado com sucesso."


class ClientUpdateView(SuccessMessageMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = "sign/clients/form.html"
    success_message = "Cliente atualizado com sucesso."

    def get_success_url(self):
        return reverse("sign:client_detail", kwargs={"pk": self.object.pk})


class ClientDeleteView(DeleteView):
    model = Client
    template_name = "sign/clients/confirm_delete.html"
    success_url = reverse_lazy("sign:client_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Cliente excluído com sucesso.")
        return response
