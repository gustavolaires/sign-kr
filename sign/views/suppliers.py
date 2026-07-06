from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ..forms import RepresentativeForm, SupplierForm, _only_digits
from ..models import Manufacturer, Representative, Supplier


class SupplierListView(ListView):
    model = Supplier
    template_name = "sign/suppliers/list.html"
    context_object_name = "suppliers"

    # Campos permitidos para ordenação (asc/desc).
    SORT_FIELDS = ("name", "cnpj")

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
        cnpj = params.get("cnpj", "").strip()
        email = params.get("email", "").strip()
        manufacturer = params.get("manufacturer", "").strip()

        if name:
            qs = qs.filter(name__icontains=name)
        # O CNPJ é gravado só com dígitos; busca pela parte numérica digitada.
        cnpj_digits = _only_digits(cnpj)
        if cnpj_digits:
            qs = qs.filter(cnpj__icontains=cnpj_digits)
        if email:
            qs = qs.filter(email__icontains=email)
        if manufacturer.isdigit():
            qs = qs.filter(manufacturer_id=manufacturer)

        return qs.order_by(self._current_sort())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        filters = {
            "name": params.get("name", "").strip(),
            "cnpj": params.get("cnpj", "").strip(),
            "email": params.get("email", "").strip(),
            "manufacturer": params.get("manufacturer", "").strip(),
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
        ctx["manufacturers"] = Manufacturer.objects.all()
        ctx["current_sort"] = current
        ctx["sort_links"] = sort_links
        ctx["sort_state"] = sort_state
        ctx["has_filters"] = bool(active)
        return ctx


class SupplierDetailView(DetailView):
    model = Supplier
    template_name = "sign/suppliers/detail.html"
    context_object_name = "supplier"


class SupplierCreateView(SuccessMessageMixin, CreateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "sign/suppliers/form.html"
    success_url = reverse_lazy("sign:supplier_list")
    success_message = "Fornecedor criado com sucesso."

    def form_valid(self, form):
        # Salva o fornecedor e, em seguida, cria os representantes preenchidos
        # inline (linhas dinâmicas parseadas do POST — padrão de _collect_payments).
        response = super().form_valid(form)
        names = self.request.POST.getlist("rep_name")
        emails = self.request.POST.getlist("rep_email")
        phones1 = self.request.POST.getlist("rep_phone_primary")
        phones2 = self.request.POST.getlist("rep_phone_secondary")

        reps = []
        for name, email, phone1, phone2 in zip(names, emails, phones1, phones2):
            # Ignora linhas sem nome (vazias/incompletas).
            if not name.strip():
                continue
            reps.append(
                Representative(
                    supplier=self.object,
                    name=name.strip(),
                    email=email.strip(),
                    phone_primary=_only_digits(phone1),
                    phone_secondary=_only_digits(phone2),
                )
            )
        if reps:
            Representative.objects.bulk_create(reps)
        return response


class SupplierUpdateView(SuccessMessageMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "sign/suppliers/form.html"
    success_message = "Fornecedor atualizado com sucesso."

    def get_success_url(self):
        return reverse("sign:supplier_detail", kwargs={"pk": self.object.pk})


class SupplierDeleteView(DeleteView):
    model = Supplier
    template_name = "sign/suppliers/confirm_delete.html"
    success_url = reverse_lazy("sign:supplier_list")
    context_object_name = "supplier"

    def form_valid(self, form):
        # CASCADE remove os representantes vinculados.
        messages.success(self.request, "Fornecedor excluído com sucesso.")
        return super().form_valid(form)


class RepresentativeCreateView(SuccessMessageMixin, CreateView):
    model = Representative
    form_class = RepresentativeForm
    template_name = "sign/suppliers/representatives/form.html"
    success_message = "Representante adicionado com sucesso."

    def dispatch(self, request, *args, **kwargs):
        self.supplier = get_object_or_404(Supplier, pk=kwargs["supplier_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.supplier = self.supplier
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["supplier"] = self.supplier
        return ctx

    def get_success_url(self):
        return reverse("sign:supplier_detail", kwargs={"pk": self.supplier.pk})


class RepresentativeUpdateView(SuccessMessageMixin, UpdateView):
    model = Representative
    form_class = RepresentativeForm
    template_name = "sign/suppliers/representatives/form.html"
    success_message = "Representante atualizado com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["supplier"] = self.object.supplier
        return ctx

    def get_success_url(self):
        return reverse("sign:supplier_detail", kwargs={"pk": self.object.supplier.pk})


class RepresentativeDeleteView(DeleteView):
    model = Representative
    template_name = "sign/suppliers/representatives/confirm_delete.html"
    context_object_name = "representative"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["supplier"] = self.object.supplier
        return ctx

    def get_success_url(self):
        return reverse("sign:supplier_detail", kwargs={"pk": self.object.supplier.pk})

    def form_valid(self, form):
        messages.success(self.request, "Representante excluído com sucesso.")
        return super().form_valid(form)
