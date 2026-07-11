# Despesas (app `sign`)

Gestão de despesas (contas a pagar): cadastro, listagem, edição, exclusão e
registro de pagamento. Modelagem **pai/filho** (espelha `Sale`/`SaleItem`):
uma `Expense` (definição) tem várias `ExpenseInstallment` (parcelas/ocorrências).
Leia antes de alterar a área financeira.

## Visão geral

Uma despesa pode ser:

- **isolada** (`recurrent=False`) ou **recorrente** (`recurrent=True`, mensal);
- de **parcela única** ou **múltiplas parcelas** → N parcelas filhas;
- de **valor fixo** ou **variável** → cada parcela tem seu próprio `value_cents`
  (valor fixo = todas iguais; variável = editar parcelas individualmente).

As parcelas são geradas **por horizonte** no cadastro (sem processo em background,
pois o app roda em PyWebView desktop): a recorrente gera as próximas N ocorrências
no dia previsto; a isolada gera `installment_total` parcelas mensais a partir do
1º vencimento. Mais parcelas podem ser adicionadas depois manualmente.

## Models (`sign/models.py`)

- **`Expense`** — definição. Campos: `name`, `description`, `recurrent`,
  `scheduled_for` (dia 1–31, validado, usado só quando recorrente), `created_at`
  (`db_index=True`). `Meta.ordering = ["-id"]`.
- **`ExpenseInstallment`** — parcela/ocorrência. `expense` FK `CASCADE`
  (`related_name="installments"`). Campos: `installment_current`,
  `installment_total`, `value_cents`, `due_date` (`DateField`), `paid_value_cents`,
  `paid_at`, `created_at` (`auto_now_add`), `updated_at` (`auto_now`).
  `Meta.ordering = ["due_date", "installment_current"]`.
  - Valores monetários em **centavos**; propriedades em reais: `value`, `paid_value`.
  - **`status`** (property derivada, não armazenada; usa `timezone.localdate()`):
    `paid` (pago ≥ devido) > `partial` (pago > 0) > `overdue` (venceu em aberto) >
    `pending`. `status_label` traduz para PT-BR (Pago/Parcial/Atrasado/Pendente).

## Serviço (`sign/services/expenses.py`)

Toda a geração e matemática fica na camada de serviço. Reusa `reais_to_cents`.

- **`create_expense(*, name, description, recurrent, scheduled_for, value_cents,
  installment_total, first_due_date, months_ahead)`** — `@transaction.atomic`.
  Valida por modo (recorrente exige `scheduled_for`+`months_ahead`; isolada exige
  `first_due_date`+`installment_total`), cria a `Expense` e gera as parcelas.
  `value_cents` é o mesmo em todas (valor fixo). Levanta `ValidationError` (PT-BR).
- **`_generate_installments(expense, *, value_cents, count, start_date, day)`** —
  `bulk_create` de `count` parcelas mensais.
- **`_month_with_day(base, months, day)`** — soma meses **ancorando no mês-base**
  e **clampando o dia** ao último dia do mês (`calendar.monthrange`). Ancorar no
  mês-base (em vez de somar sobre a data anterior) evita acúmulo de clamp (dia 31
  não "gruda" no 28 após fevereiro).
- **`_first_recurrent_due(day)`** — próxima ocorrência do dia em diante (este mês
  ou o próximo).
- **`register_payment(installment, *, paid_value_cents, paid_at)`** — grava/limpa
  o pagamento (`update_fields`).

## Forms (`sign/forms.py`)

Todos herdam de `StyledModelForm` (exceto o de pagamento, que aplica `INPUT_CLASSES`
manualmente por ser `forms.Form`).

- **`ExpenseForm`** (cadastro) — definição + campos **não-model** de geração
  (`value` R$, `installment_total`, `first_due_date`, `months_ahead`), consumidos
  pela view via `create_expense`. `clean()` valida por modo.
- **`ExpenseUpdateForm`** (edição) — só a definição (name/description/recurrent/
  scheduled_for); as parcelas são editadas à parte.
- **`ExpenseInstallmentForm`** — edição/criação de 1 parcela (valor R$, vencimento,
  nº parcela/total); converte reais→centavos no `save()`.
- **`InstallmentPaymentForm`** — `paid_value` (R$) + `paid_at`.

## Views (`sign/views/expenses.py`) e URLs (`sign/urls.py`)

CBVs genéricas + `SuccessMessageMixin` (padrão `clients.py`). Paths em inglês.

| Nome de rota | Path | View |
|---|---|---|
| `expense_list` | `expenses/` | `ExpenseListView` (filtros nome/tipo, ordenação, agregados: nº parcelas, total, pago, próx. venc.) |
| `expense_create` | `expenses/new/` | `ExpenseCreateView` (chama `create_expense` no `form_valid`) |
| `expense_detail` | `expenses/<pk>/` | `ExpenseDetailView` (definição + tabela de parcelas com badge de status) |
| `expense_update` | `expenses/<pk>/edit/` | `ExpenseUpdateView` |
| `expense_delete` | `expenses/<pk>/delete/` | `ExpenseDeleteView` (CASCADE remove parcelas) |
| `installment_create` | `expenses/<expense_pk>/installments/new/` | `ExpenseInstallmentCreateView` |
| `installment_update` | `installments/<pk>/edit/` | `ExpenseInstallmentUpdateView` |
| `installment_delete` | `installments/<pk>/delete/` | `ExpenseInstallmentDeleteView` |
| `installment_pay` | `installments/<pk>/pay/` | `installment_pay` (FBV) |

> `ExpenseCreateView.form_valid` **não** chama `super()` (evita criar uma `Expense`
> duplicada); a criação é toda do serviço. Erros do serviço viram
> `non_field_errors` do form.

## Templates (`sign/templates/sign/expenses/`)

- `list.html`, `form.html`, `detail.html`, `confirm_delete.html`, `_field.html`
  (partial de campo, checkbox inline vs label) e `installments/{form,pay,confirm_delete}.html`.
- `form.html` alterna os blocos **Parcelamento** (isolada) e **Recorrência** via
  `<script>` no `change` do checkbox `#id_recurrent`.
- Badge de status no `detail.html` (cores condicionais): pago=green, parcial=amber,
  atrasado=red, pendente=gray.
- Valores em centavos (agregados/`due`) usam o filtro **`centavos`** de
  `sign_format` (`{{ x|centavos|floatformat:2 }}`); properties em reais usam
  `floatformat:2` direto.

## Menu

Item **Despesas** (`fa-money-bill-wave`) na nova seção **Financeiro** do
`base.html`; ativo quando `'expense' in url_name or 'installment' in url_name`.

## Build / migrações

- Migração: `0005_expense_expenseinstallment`.
- Rebuild Tailwind após mexer em classes (ver
  [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md#tailwind-css-build)):
  `./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify`.

## Verificação rápida

1. `./venv/Scripts/python.exe manage.py check`.
2. Criar despesa **isolada** (3 parcelas, R$ 100, 1º venc.) → detail mostra 3
   parcelas mensais, total R$ 300.
3. Editar uma parcela com outro valor → total/status atualizam (valor variável).
4. Criar **recorrente** (dia 10, 12 meses) → 12 parcelas no dia 10 (conferir clamp
   em meses curtos).
5. Registrar pagamento parcial → "Parcial"; pagamento total → "Pago"; parcela
   vencida em aberto → "Atrasado".
6. Excluir a despesa remove as parcelas (CASCADE).
