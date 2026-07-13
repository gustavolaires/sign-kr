# Fluxo de despesas (contas a pagar)

Percurso de uma despesa: cadastro → **geração das parcelas** → acompanhamento por
status → **registro de pagamento**. Ênfase no processamento (geração por horizonte
e status derivado). Referência da feature:
[`recursos/despesas.md`](../recursos/despesas.md).

## Modelo mental

Uma **`Expense`** (definição) tem várias **`ExpenseInstallment`** (parcelas/
ocorrências) — pai/filho, espelhando `Sale`/`SaleItem`. As três características do
negócio se combinam nas parcelas filhas:

- **isolada** (`recurrent=False`) ou **recorrente** (`recurrent=True`, mensal);
- **parcela única** ou **múltiplas** → N parcelas;
- **valor fixo** (todas iguais) ou **variável** (edita cada parcela depois).

## Visão de ponta a ponta

```
  expenses/new/  (ExpenseForm: definição + parâmetros de geração)
        │  POST → create_expense(...)  @transaction.atomic
        ▼
  Expense  +  N ExpenseInstallment   (geradas por horizonte, valor fixo)
        ▼  expenses/<pk>/
  Detalhe: tabela de parcelas com badge de status (derivado)
        ├── editar parcela (valor variável)  → installments/<pk>/edit/
        ├── adicionar parcela manual         → expenses/<pk>/installments/new/
        ├── registrar pagamento              → installments/<pk>/pay/
        └── cancelar pagamento (se paga)     → installments/<pk>/cancel-payment/
```

## 1. Cadastro → geração das parcelas (`create_expense`)

O `ExpenseForm` reúne a definição (`name`, `description`, `recurrent`,
`scheduled_for`) **e** parâmetros de geração que **não pertencem ao model**
(`value` em R$, `installment_total`, `first_due_date`, `months_ahead`). O
`clean()` exige campos diferentes conforme o modo. A view
(`ExpenseCreateView.form_valid`) chama o service — e **não** chama `super()`,
para não criar uma `Expense` duplicada.

**`create_expense`** (`sign/services/expenses.py`, `@transaction.atomic`) gera as parcelas
**por horizonte** no momento do cadastro — **não há job em background** (o app é
desktop PyWebView):

- **Recorrente**: exige `scheduled_for` (dia 1–31) e `months_ahead`. Começa na
  próxima ocorrência do dia (`_first_recurrent_due`) e gera `months_ahead`
  parcelas mensais.
- **Isolada**: exige `first_due_date` e `installment_total`. Gera
  `installment_total` parcelas mensais a partir do 1º vencimento.
- O **valor é o mesmo em todas** (valor fixo); valores variáveis são ajustados
  depois, editando cada parcela. `value_cents` vem de `reais_to_cents`.

### Aritmética de datas (clamp ancorado)

`_month_with_day(base, months, day)` soma meses **ancorando no mês-base** e
**clampa o dia** ao último dia do mês (`calendar.monthrange`). Ancorar no mês-base
(em vez de somar sobre a data anterior) evita **acúmulo de clamp**: o dia 31 não
"gruda" no 28 depois de passar por fevereiro. Ex.: dia 31, jan→fev vira 28, mas
fev→mar volta a 31.

Mais parcelas podem ser adicionadas manualmente depois
(`ExpenseInstallmentCreateView`).

## 2. Status derivado (sem job)

O `status` de cada parcela **não é armazenado** — é calculado a cada leitura
(`ExpenseInstallment.status`), com prioridade:

1. **Pago** — `paid_value_cents ≥ value_cents` (e devido > 0);
2. **Parcial** — pago > 0, mas menor que o devido;
3. **Atrasado** — em aberto e `due_date < timezone.localdate()`;
4. **Pendente** — em aberto e ainda não venceu.

`status_label` traduz para PT-BR. Consequência: o "atrasado" aparece sozinho
quando a data chega, sem nenhuma rotina de atualização. No `detail.html` o badge
é colorido (pago=green, parcial=amber, atrasado=red, pendente=gray).

## 3. Registrar pagamento (`installment_pay` + `register_payment`)

- `installment_pay` (FBV) abre `InstallmentPaymentForm` **pré-preenchido** com o
  valor já pago (ou o devido) e a data já registrada (ou hoje) — um clique para
  quitar.
- `register_payment` grava `paid_value_cents` + `paid_at` (`update_fields`).
  Pagar o total → "Pago"; pagar parte → "Parcial"; gravar 0/sem data → volta a
  pendente/atrasada. O status reavalia sozinho (derivado).
- **Cancelar pagamento** (`installment_cancel_payment` + `cancel_payment`): só
  para parcelas **pagas**. Página de confirmação (GET) → POST zera
  `paid_value_cents`/`paid_at`, revertendo a parcela para em aberto. No
  `detail.html`, o botão de pagar fica desabilitado em parcelas pagas e o de
  cancelar pagamento aparece só nelas.

## 4. Listagem — filtros, situação agregada e ordenação

`ExpenseListView` faz o trabalho pesado no `get_queryset` com `annotate`:

- **Agregados por despesa**: nº de parcelas, total, pago e próximo vencimento em
  aberto (`Min(..., filter=open_q)`).
- **Situação da despesa** (derivada das parcelas, via contagens condicionais):
  **pago** (sem parcelas em aberto), **atrasado** (tem parcela vencida em aberto),
  **pendente** (em aberto mas nada vencido), **pago esse mês** (parcela paga no
  mês corrente). Filtro extra **"a pagar esse mês"** = parcela em aberto vencendo
  no mês corrente.
- **Ordenação** por `name`/`created_at` validada por allowlist (`SORT_FIELDS`);
  os links preservam os filtros ativos (e vice-versa).

> "Em aberto" = `paid_value_cents < value_cents`. Os filtros operam em **centavos**
> diretamente no banco — sem materializar a property `status` (que é Python).

## Exclusão

Excluir a `Expense` remove as parcelas em **CASCADE**. Ver matriz de `on_delete`
em [`../arquitetura/modelo-de-dados.md`](../arquitetura/modelo-de-dados.md).
