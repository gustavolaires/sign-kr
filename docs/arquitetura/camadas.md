# Camadas e responsabilidades

Detalha cada camada da app `sign`: o que faz, onde fica e o que **não** deve
conter. Use como guia de "onde colocar este código". Visão de conjunto em
[`visao-geral.md`](visao-geral.md); regras transversais em
[`convencoes.md`](convencoes.md).

## Roteamento (`core/urls.py` + `sign/urls.py`)

- `core/urls.py` registra o admin em `admin/` e inclui `sign.urls` na raiz
  (`path("", include("sign.urls"))`).
- `sign/urls.py` define `app_name = "sign"` (namespace) e todas as rotas. **Paths
  em inglês**; nomes de rota no padrão `<area>_<acao>` (`product_list`,
  `sale_detail`, `expense_create`...). `/` (`name="home"`) redireciona para
  `sign:product_list`.
- Sempre referencie rotas por nome (`{% url 'sign:...' %}` / `reverse(...)`),
  nunca por path literal.

## Views (`sign/views/`)

Pacote com **um módulo por área** — `products.py`, `manufacturers.py`,
`clients.py`, `sales.py`, `cart.py`, `expenses.py` — e um `__init__.py` que
**reexporta** todas as views (com `__all__`), para `urls.py` importar de
`sign.views` de forma plana.

Responsabilidade da view: **orquestração fina**.

- A maioria são **CBVs genéricas** (`ListView`/`DetailView`/`CreateView`/
  `UpdateView`/`DeleteView`) + `SuccessMessageMixin` (ver padrão CRUD em
  `convencoes.md`).
- Operações que não casam com CBV são **FBVs**: o carrinho (`cart_add`,
  `cart_update`, `cart_remove`, `cart_detail`), o `checkout` e o `installment_pay`.
- **Listagens** concentram filtros/ordenação/agregados no `get_queryset` +
  `get_context_data` (ex.: `ExpenseListView` com `annotate`/`Count`/`Sum`;
  `SaleListView` com filtros de cliente e período). Use `select_related`/
  `prefetch_related` para evitar N+1.
- Ao precisar de regra de negócio, a view **chama um service** e **captura**
  `ValidationError` (vira `messages.error` ou `form.add_error`). Não faz
  matemática monetária nem escreve em várias tabelas diretamente.
- Padrão de navegação pós-salvar em `convencoes.md` (edição → detalhe).

> Caso especial: `ExpenseCreateView.form_valid` **não** chama `super()` — a
> `Expense` e suas parcelas são criadas inteiramente por `create_expense`, para
> não gravar uma `Expense` duplicada.

## Services (`sign/services/`)

A camada de **regras de negócio**, organizada como **pacote com um módulo por
domínio** (mesmo padrão de `sign/views/`): `money.py` (primitivos monetários
compartilhados — base), `dashboard.py`, `sales.py`, `expenses.py`, `invoices.py`
(NF de entrada + precificação), `imports.py` (carga CSV) e `reports.py`. O
`__init__.py` **reexporta** a API pública de forma plana, então
`from sign.services import ...` continua funcionando. Aqui mora tudo que é crítico:

- **Matemática monetária** em centavos (`reais_to_cents`, `Decimal`,
  `ROUND_HALF_UP`) — ver `convencoes.md`.
- **Transações atômicas** (`@transaction.atomic`): `create_sale` e
  `create_expense` validam tudo **antes** de qualquer escrita e gravam várias
  tabelas de uma vez; se algo falhar, nada é persistido.
- **Validações de negócio**, levantando `ValidationError` com mensagens **PT-BR**
  (estoque insuficiente, desconto > subtotal, pagamentos < total, dia de
  vencimento inválido, etc.).
- Funções auxiliares de calendário para despesas (`_month_with_day`,
  `_first_recurrent_due`, `_generate_installments`) e `register_payment`.

Detalhe do processamento em [`fluxos/venda.md`](../fluxos/venda.md) e
[`fluxos/despesas.md`](../fluxos/despesas.md).

## Forms (`sign/forms.py`)

- **`StyledModelForm`** é a base que injeta as classes Tailwind nos widgets.
  Todos os ModelForms herdam dela; forms simples (`forms.Form`, ex.
  `InstallmentPaymentForm`) aplicam `INPUT_CLASSES` manualmente.
- **Conversão de 1 campo**: campos monetários são `DecimalField` virtuais (em
  reais), convertidos a centavos no `save()` (`ProductForm`, `ExpenseInstallmentForm`).
- **Limpeza de máscara**: `clean_<campo>` remove pontuação antes de gravar
  (`ClientForm`).
- **Validação por modo**: `ExpenseForm.clean()` exige campos diferentes conforme
  recorrente vs isolada.
- Forms que alimentam um service expõem campos **não-model** (ex.: `value`,
  `installment_total`, `first_due_date`, `months_ahead` no `ExpenseForm`),
  consumidos pela view.

## Models (`sign/models.py`)

- Define as entidades e o **modelo de dados** (ver [`modelo-de-dados.md`](modelo-de-dados.md)).
- Contém **apenas** estrutura, properties de **exibição** (centavos→reais,
  somente leitura) e **estado derivado** (`ExpenseInstallment.status`/
  `status_label`). **Não** contém escrita multi-tabela (isso é service).
- Lógica de snapshot reaproveitável (`ProductSnapshot.compute_hash` /
  `get_or_create_for`) vive no model por ser intrínseca à entidade.
- `TextChoices` para enumerações (`UnitType`, `PersonType`, `PaymentType`).

## Carrinho (`sign/cart.py`)

Camada à parte: a classe **`Cart`** encapsula leitura/escrita/normalização do
cookie `cart` (sem banco) e o cálculo de totais (em centavos). As **views** é que
gravam (`cart.save(response)`). Ver [`recursos/carrinho.md`](../recursos/carrinho.md).

## Templates (`sign/templates/sign/`)

- **`base.html`** é o shell reutilizável (side menu navy + header + mensagens +
  badge do carrinho + toast). Todas as telas o estendem. Ver
  [`fluxos/navegacao.md`](../fluxos/navegacao.md).
- Cada área tem sua **subpasta** (`products/`, `manufacturers/`, `clients/`,
  `sales/`, `cart/`, `expenses/` — esta com `installments/` aninhada), com os
  arquivos típicos `list/detail/form/confirm_delete.html` e partials `_field.html`.
- Filtros de máscara/centavos via `{% load sign_format %}`.

## Static, context processors e template tags

- **`static/sign/css/`**: `input.css` (fonte Tailwind v4) e `output.css`
  (commitado). **`static/sign/js/`**: `cart.js`, `checkout.js`, `masks.js`
  (JS vanilla, sem framework). **`static/sign/fontawesome/`**: ícones locais.
- **`context_processors.cart`**: injeta `cart_count` (nº de produtos distintos)
  em **todos** os templates, para o badge do header. Registrado em
  `core/settings.py` → `TEMPLATES.OPTIONS.context_processors`.
- **`templatetags/sign_format.py`**: filtros `cpf_cnpj`, `phone`, `cep`
  (remontam máscara) e `centavos` (centavos→reais para usar com `floatformat:2`).

## Admin (`sign/admin.py`)

Django admin configurado para **operação/depuração** (não é a UI principal):
`Sale` é read-only com inlines de itens e pagamentos; `Expense` tem inline de
parcelas; `ProductSnapshot` expõe o `content_hash` como read-only.
