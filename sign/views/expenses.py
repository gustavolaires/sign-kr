from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, F, Min, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from ..forms import (
    ExpenseForm,
    ExpenseInstallmentForm,
    ExpenseUpdateForm,
    InstallmentPaymentForm,
)
from ..models import Expense, ExpenseInstallment
from ..search import filter_unaccent
from ..services import create_expense, register_payment, reais_to_cents


class ExpenseListView(ListView):
    model = Expense
    template_name = "sign/expenses/list.html"
    context_object_name = "expenses"

    # Campos permitidos para ordenação (asc/desc).
    SORT_FIELDS = ("name", "created_at")

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
        recurrent = params.get("recurrent", "").strip()
        status = params.get("status", "").strip()
        due_month = params.get("due_month", "").strip()

        if name:
            qs = filter_unaccent(qs, "name", name)
        if recurrent in ("0", "1"):
            qs = qs.filter(recurrent=(recurrent == "1"))

        today = timezone.localdate()
        # "Em aberto" = parcela cujo pago < devido; "vencida" = em aberto e já passou.
        open_q = Q(installments__paid_value_cents__lt=F("installments__value_cents"))
        overdue_q = open_q & Q(installments__due_date__lt=today)
        # Pago no mês corrente = parcela com data de pagamento neste mês/ano.
        paid_month_q = Q(
            installments__paid_at__year=today.year,
            installments__paid_at__month=today.month,
        )
        # A pagar no mês corrente = parcela EM ABERTO com vencimento neste mês/ano.
        due_month_q = open_q & Q(
            installments__due_date__year=today.year,
            installments__due_date__month=today.month,
        )

        # Agregados por despesa: nº de parcelas, total, pago, próximo vencimento
        # em aberto e contagens usadas para o filtro por situação.
        qs = qs.annotate(
            installments_count=Count("installments"),
            total_cents_sum=Sum("installments__value_cents"),
            paid_cents_sum=Sum("installments__paid_value_cents"),
            next_due=Min("installments__due_date", filter=open_q),
            open_count=Count("installments", filter=open_q),
            overdue_count=Count("installments", filter=overdue_q),
            paid_month_count=Count("installments", filter=paid_month_q),
            due_month_count=Count("installments", filter=due_month_q),
        )

        # Situação da despesa (derivada das parcelas):
        #   pago = sem parcelas em aberto; atrasado = tem parcela vencida;
        #   pendente = tem parcelas em aberto, mas nenhuma vencida;
        #   pago no mês = tem parcela paga no mês corrente.
        if status == "paid":
            qs = qs.filter(open_count=0)
        elif status == "paid_month":
            qs = qs.filter(paid_month_count__gt=0)
        elif status == "overdue":
            qs = qs.filter(overdue_count__gt=0)
        elif status == "pending":
            qs = qs.filter(open_count__gt=0, overdue_count=0)

        # A pagar esse mês (checkbox): tem parcela em aberto vencendo no mês corrente.
        if due_month:
            qs = qs.filter(due_month_count__gt=0)

        return qs.order_by(self._current_sort())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET
        filters = {
            "name": params.get("name", "").strip(),
            "recurrent": params.get("recurrent", "").strip(),
            "status": params.get("status", "").strip(),
            "due_month": params.get("due_month", "").strip(),
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
        ctx["status_choices"] = [
            ("paid", "Pago"),
            ("paid_month", "Pago esse mês"),
            ("pending", "Pendente"),
            ("overdue", "Atrasado"),
        ]
        ctx["current_sort"] = current
        ctx["sort_links"] = sort_links
        ctx["sort_state"] = sort_state
        ctx["has_filters"] = bool(active)
        return ctx


class ExpenseDetailView(DetailView):
    model = Expense
    template_name = "sign/expenses/detail.html"
    context_object_name = "expense"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        installments = list(self.object.installments.all())
        ctx["installments"] = installments
        ctx["total_cents"] = sum(i.value_cents for i in installments)
        ctx["paid_cents"] = sum(i.paid_value_cents for i in installments)
        return ctx


class ExpenseCreateView(CreateView):
    model = Expense
    form_class = ExpenseForm
    template_name = "sign/expenses/form.html"

    def form_valid(self, form):
        data = form.cleaned_data
        try:
            self.object = create_expense(
                name=data["name"],
                description=data["description"],
                recurrent=data["recurrent"],
                scheduled_for=data.get("scheduled_for"),
                value_cents=reais_to_cents(data["value"]),
                installment_total=data.get("installment_total"),
                first_due_date=data.get("first_due_date"),
                months_ahead=data.get("months_ahead"),
            )
        except ValidationError as exc:
            # Mensagens (PT-BR) do serviço viram erros não-associados do form.
            form.add_error(None, exc)
            return self.form_invalid(form)
        messages.success(self.request, "Despesa criada com sucesso.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("sign:expense_detail", kwargs={"pk": self.object.pk})


class ExpenseUpdateView(SuccessMessageMixin, UpdateView):
    model = Expense
    form_class = ExpenseUpdateForm
    template_name = "sign/expenses/form.html"
    success_message = "Despesa atualizada com sucesso."

    def get_success_url(self):
        return reverse("sign:expense_detail", kwargs={"pk": self.object.pk})


class ExpenseDeleteView(DeleteView):
    model = Expense
    template_name = "sign/expenses/confirm_delete.html"
    success_url = reverse_lazy("sign:expense_list")

    def form_valid(self, form):
        messages.success(self.request, "Despesa excluída com sucesso.")
        return super().form_valid(form)


class ExpenseInstallmentCreateView(SuccessMessageMixin, CreateView):
    model = ExpenseInstallment
    form_class = ExpenseInstallmentForm
    template_name = "sign/expenses/installments/form.html"
    success_message = "Parcela adicionada com sucesso."

    def dispatch(self, request, *args, **kwargs):
        self.expense = get_object_or_404(Expense, pk=kwargs["expense_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.expense = self.expense
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["expense"] = self.expense
        return ctx

    def get_success_url(self):
        return reverse("sign:expense_detail", kwargs={"pk": self.expense.pk})


class ExpenseInstallmentUpdateView(SuccessMessageMixin, UpdateView):
    model = ExpenseInstallment
    form_class = ExpenseInstallmentForm
    template_name = "sign/expenses/installments/form.html"
    success_message = "Parcela atualizada com sucesso."

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["expense"] = self.object.expense
        return ctx

    def get_success_url(self):
        return reverse("sign:expense_detail", kwargs={"pk": self.object.expense.pk})


class ExpenseInstallmentDeleteView(DeleteView):
    model = ExpenseInstallment
    template_name = "sign/expenses/installments/confirm_delete.html"
    context_object_name = "installment"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["expense"] = self.object.expense
        return ctx

    def get_success_url(self):
        return reverse("sign:expense_detail", kwargs={"pk": self.object.expense.pk})

    def form_valid(self, form):
        messages.success(self.request, "Parcela excluída com sucesso.")
        return super().form_valid(form)


def installment_pay(request, pk):
    """Registra o pagamento (valor + data) de uma parcela."""
    installment = get_object_or_404(ExpenseInstallment, pk=pk)
    if request.method == "POST":
        form = InstallmentPaymentForm(request.POST)
        if form.is_valid():
            try:
                register_payment(
                    installment,
                    paid_value_cents=reais_to_cents(form.cleaned_data["paid_value"]),
                    paid_at=form.cleaned_data["paid_at"],
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Pagamento registrado com sucesso.")
                return redirect("sign:expense_detail", pk=installment.expense.pk)
    else:
        # Pré-preenche com o valor já pago (se houver) ou o valor devido, e a
        # data já registrada ou a data de hoje — um clique para quitar.
        base_cents = installment.paid_value_cents or installment.value_cents
        form = InstallmentPaymentForm(
            initial={
                "paid_value": Decimal(base_cents) / 100,
                "paid_at": installment.paid_at or timezone.localdate(),
            }
        )
    return render(
        request,
        "sign/expenses/installments/pay.html",
        {"form": form, "installment": installment, "expense": installment.expense},
    )
