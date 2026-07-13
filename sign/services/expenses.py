"""Despesas: geração de parcelas e registro de pagamento.

Trabalha com valores já em centavos (recebidos da camada de form), portanto não
depende dos helpers monetários. As validações levantam ``ValidationError`` em
PT-BR e a criação da despesa é atômica.
"""

import calendar
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import Expense, ExpenseInstallment


def _month_with_day(base, months, day):
    """Data ``base`` deslocada ``months`` meses, no ``day`` (clampado ao mês).

    Ancorar no mês-base (em vez de somar sobre a data anterior) evita o acúmulo
    de clamp: o dia 31 não "gruda" no 28 depois de passar por fevereiro.
    """
    index = base.year * 12 + (base.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def _first_recurrent_due(day):
    """Próxima ocorrência do dia ``day`` em diante (este mês ou o próximo)."""
    today = timezone.localdate()
    last_day = calendar.monthrange(today.year, today.month)[1]
    this_month_due = date(today.year, today.month, min(day, last_day))
    if this_month_due >= today:
        return this_month_due
    return _month_with_day(today, 1, day)


def _generate_installments(expense, *, value_cents, count, start_date, day):
    """Cria ``count`` parcelas mensais para ``expense`` (uma por mês).

    A i-ésima parcela vence no ``day`` (clampado) do mês ``start_date`` + i.
    Retorna a lista de parcelas criadas.
    """
    installments = [
        ExpenseInstallment(
            expense=expense,
            installment_current=i + 1,
            installment_total=count,
            value_cents=value_cents,
            due_date=_month_with_day(start_date, i, day),
        )
        for i in range(count)
    ]
    return ExpenseInstallment.objects.bulk_create(installments)


@transaction.atomic
def create_expense(*, name, description, recurrent, scheduled_for, value_cents,
                   installment_total, first_due_date, months_ahead):
    """Cria uma despesa e gera suas parcelas, de forma atômica.

    Parâmetros:
        name, description: dados da definição.
        recurrent: ``True`` para despesa recorrente (mensal).
        scheduled_for: dia do mês (1–31) do vencimento — obrigatório se recorrente.
        value_cents: valor (em centavos) aplicado a cada parcela gerada.
        installment_total: nº de parcelas — usado quando NÃO recorrente.
        first_due_date: ``date`` do 1º vencimento — usado quando NÃO recorrente.
        months_ahead: nº de meses a gerar — usado quando recorrente.

    O valor é o mesmo em todas as parcelas geradas (valor fixo); valores
    variáveis são ajustados depois, editando cada parcela. Levanta
    ``ValidationError`` (em PT-BR) em qualquer inconsistência; nada é gravado.
    """
    if value_cents <= 0:
        raise ValidationError("O valor da parcela deve ser maior que zero.")

    if recurrent:
        if not scheduled_for or not (1 <= scheduled_for <= 31):
            raise ValidationError(
                "Informe um dia previsto de vencimento entre 1 e 31."
            )
        count = int(months_ahead or 0)
        if count < 1:
            raise ValidationError("O horizonte deve ser de pelo menos 1 mês.")
        start_date = _first_recurrent_due(scheduled_for)
        day = scheduled_for
    else:
        if first_due_date is None:
            raise ValidationError("Informe a data do primeiro vencimento.")
        count = int(installment_total or 0)
        if count < 1:
            raise ValidationError("O número de parcelas deve ser de pelo menos 1.")
        start_date = first_due_date
        day = first_due_date.day

    expense = Expense.objects.create(
        name=name,
        description=description,
        recurrent=recurrent,
        scheduled_for=scheduled_for if recurrent else None,
    )
    _generate_installments(
        expense, value_cents=value_cents, count=count, start_date=start_date, day=day
    )
    return expense


def register_payment(installment, *, paid_value_cents, paid_at):
    """Registra (ou limpa) o pagamento de uma parcela.

    ``paid_value_cents`` 0 com ``paid_at`` ``None`` zera o pagamento (volta a
    pendente/atrasada). O ``status`` é derivado no model.
    """
    if paid_value_cents < 0:
        raise ValidationError("O valor pago não pode ser negativo.")
    installment.paid_value_cents = paid_value_cents
    installment.paid_at = paid_at
    installment.save(update_fields=["paid_value_cents", "paid_at", "updated_at"])
    return installment


def cancel_payment(installment):
    """Cancela o pagamento de uma parcela paga, revertendo-a para em aberto.

    Zera o valor pago e a data de pagamento; o ``status`` derivado volta a
    pendente/atrasada. Só é permitido para parcelas quitadas (``PAID``).
    """
    if installment.status != ExpenseInstallment.PAID:
        raise ValidationError(
            "Só é possível cancelar o pagamento de parcelas pagas."
        )
    installment.paid_value_cents = 0
    installment.paid_at = None
    installment.save(update_fields=["paid_value_cents", "paid_at", "updated_at"])
    return installment
