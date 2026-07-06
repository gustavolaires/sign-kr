# Notas Fiscais de Entrada (app `sign`)

Registro das **Notas Fiscais de Entrada (NF)** recebidas dos fornecedores, com
suas **Faturas/Duplicatas** e seus **Produtos**. Segue o padrão master-detail de
[`fornecedores.md`](fornecedores.md) (Fornecedor→Representantes): as faturas e os
produtos existem **apenas dentro da NF** e são criados inline no cadastro da NF
**e** editados/excluídos/adicionados depois em páginas próprias. Valores em
centavos conforme [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md).

Uma operação futura **"Processar"** (atualizar produtos e gerar despesas a partir
da NF) está prevista, mas **não** implementada — ver o fim deste doc.

## Models (`sign/models.py`)

| Model | Campos | Observações |
|---|---|---|
| `InboundInvoice` | `number`, `issue_date`, `delivery_date`, `supplier` (FK), + 10 valores `_cents` | Só `number`/`supplier` exigidos; datas e valores opcionais (default 0). |
| `InvoiceDuplicate` | `invoice` (FK), `due_date`, `value_cents` | Fatura/duplicata; `invoice` CASCADE (`related_name="duplicates"`). Só vencimento e valor. |
| `InvoiceItem` | `invoice` (FK), `code`, `description`, `unit_type`, `quantity`, `unit_price_cents`, `total_cents`, `icms_base_cents`, `icms_cents`, `ipi_cents` | Produto; `invoice` CASCADE (`related_name="items"`). |

- **`InboundInvoice.supplier`** usa **`on_delete=PROTECT`** (`related_name="invoices"`):
  excluir um fornecedor com NFs levanta `ProtectedError`, tratado no
  `SupplierDeleteView` (mensagem PT-BR, volta ao detalhe do fornecedor).
- **Valores monetários** (todos `PositiveIntegerField` sufixo `_cents`, com
  `@property` em reais para exibição): na NF — `products_total`, `total`,
  `icms_base`, `icms`, `ipi`, `taxes_total`, `freight`, `insurance`, `discount`,
  `other_costs`; nos itens — `unit_price`, `total`, `icms_base`, `icms`, `ipi`.
  Digitados manualmente (fiéis ao documento físico); **não** são calculados.
- **`InvoiceItem.unit_type`** reutiliza o enum `UnitType` dos produtos.
- **`InvoiceItem.quantity`** é `DecimalField(max_digits=12, decimal_places=3)`
  (suporta unidades fracionadas — kg/l), diferente de `Product.quantity` (inteiro).
- `Meta.ordering`: NF `["-id"]`; faturas `["due_date", "id"]`; itens `["id"]`.

## Serviço (`sign/services.py`)

- **`create_inbound_invoice(*, number, issue_date, delivery_date, supplier,
  products_total, total, icms_base, icms, ipi, taxes_total, freight, insurance,
  discount, other_costs, duplicates, items)`** — `@transaction.atomic`. Concentra a
  conversão reais→centavos (via `reais_to_cents`) e o `bulk_create` das faturas e
  produtos. `duplicates`/`items` são listas de dicts (valores em reais, `due_date`
  já como `date`); linhas vazias (fatura sem número, produto sem código) são
  ignoradas. Valida obrigatórios por linha e levanta `ValidationError` (PT-BR).
- Helper `_reais_or_zero(value)` — trata vazio/`None` como 0 centavos.

## Forms (`sign/forms.py`)

Todos herdam `StyledModelForm`; valores em reais são `DecimalField` **virtuais**
(fora de `Meta.fields`), convertidos no `save()`/no serviço. Helper `_reais_field`.

- **`InboundInvoiceForm`** — `number`, `issue_date`, `delivery_date`, `supplier` +
  os 10 campos virtuais em R$ (mapa `MONEY_FIELDS`). **Obrigatórios**: `number`,
  `supplier` e `total` (Valor total); os demais valores são opcionais (default 0).
  Datas `DateInput(type=date)`. No **update** o `save()` converte para centavos; no
  **create** quem grava é o serviço (a view não chama `super().form_valid`).
- **`InvoiceDuplicateForm`** — `due_date` + `value` (R$).
- **`InvoiceItemForm`** — `code`, `description`, `unit_type`, `quantity` +
  `unit_price`, `total`, `icms_base`, `icms`, `ipi` (R$). **Obrigatórios**: `code`,
  `description`, `unit_type`, `quantity` e `unit_price`; `total`/impostos são
  opcionais. `unit_type` exibe a sigla (mesmo ajuste do `ProductForm`); `quantity`
  com `step="any"`.

## Views (`sign/views/invoices.py`) e URLs (`sign/urls.py`)

CBVs genéricas + `SuccessMessageMixin`. Paths em inglês; **todos os `name` contêm
`invoice`** (o realce do menu usa `'invoice' in url_name`). Views exportadas em
`sign/views/__init__.py`.

| Nome de rota | Path | View |
|---|---|---|
| `invoice_list` | `invoices/` | `InboundInvoiceListView` (filtros número/fornecedor/data de emissão/data de recebimento + ordenação; colunas incluem Recebimento) |
| `invoice_create` | `invoices/new/` | `InboundInvoiceCreateView` (cria faturas/produtos inline via `create_inbound_invoice`) |
| `invoice_detail` | `invoices/<pk>/` | `InboundInvoiceDetailView` (cabeçalho + tabelas de faturas e produtos) |
| `invoice_update` | `invoices/<pk>/edit/` | `InboundInvoiceUpdateView` (só cabeçalho) |
| `invoice_delete` | `invoices/<pk>/delete/` | `InboundInvoiceDeleteView` (CASCADE remove filhos) |
| `invoice_duplicate_create` | `invoices/<invoice_pk>/duplicates/new/` | `InvoiceDuplicateCreateView` |
| `invoice_duplicate_update` | `duplicates/<pk>/edit/` | `InvoiceDuplicateUpdateView` |
| `invoice_duplicate_delete` | `duplicates/<pk>/delete/` | `InvoiceDuplicateDeleteView` |
| `invoice_item_create` | `invoices/<invoice_pk>/items/new/` | `InvoiceItemCreateView` |
| `invoice_item_update` | `items/<pk>/edit/` | `InvoiceItemUpdateView` |
| `invoice_item_delete` | `items/<pk>/delete/` | `InvoiceItemDeleteView` |

> `InboundInvoiceCreateView.form_valid` **não** chama `super()`; usa o helper
> `_collect_rows` para montar as listas `dup_*`/`item_*` do POST e delega a
> `create_inbound_invoice`. Erros do serviço viram `non_field_errors`. O create
> injeta `unit_types` no contexto (siglas para o `<select>` das linhas inline).
> As sub-views (duplicata/item) espelham `Representative*View`: create aninhado
> pega o pai por `invoice_pk` no `dispatch`; todas voltam para `invoice_detail`.

## Templates (`sign/templates/sign/invoices/`)

- `list.html`, `detail.html`, `form.html`, `confirm_delete.html` e
  `duplicates/{form,confirm_delete}.html`, `items/{form,confirm_delete}.html` —
  estendem `base.html` e reutilizam o partial `sign/clients/_field.html`.
- **Detalhe**: seções *Dados da nota* e *Valores* + tabelas de **Faturas** e
  **Produtos** com botão "Adicionar" e ações Editar/Excluir por linha.
- **Form**: seções do cabeçalho + (**só na criação**) seções **Faturas** e
  **Produtos** com `<template>` de linha clonável (`duplicate-row-template`,
  `item-row-template`). O JS **`sign/static/sign/js/invoices.js`** liga os dois
  repetidores (adicionar/remover linha); os inputs paralelos são
  `dup_due_date/dup_value` e
  `item_code/item_description/item_unit_type/item_quantity/item_unit_price/item_total/item_icms_base/item_icms/item_ipi`.

## Menu

Item **NF Entrada** (`fa-solid fa-dolly`) na seção **Financeiro** do `base.html`
(após Despesas); ativo quando `'invoice' in url_name`.

## Admin (`sign/admin.py`)

`InboundInvoiceAdmin` com `InvoiceDuplicateInline` e `InvoiceItemInline`
(`TabularInline`).

## Build / migrações

- Migração: `0011_inboundinvoice_invoiceduplicate_invoiceitem`.
- Rebuild Tailwind após mexer em classes:
  `./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify`.

## Verificação rápida

1. `./venv/Scripts/python.exe manage.py check`.
2. Menu **Comercial → NF Entrada → Nova nota fiscal**: criar com fornecedor,
   datas e valores (em reais), **adicionando 2 faturas e 2 produtos inline**
   (conferir os valores no detalhe; linhas sem número/código são ignoradas).
3. Detalhe → adicionar 3ª fatura e 3º produto (páginas separadas), editar um e
   excluir outro de cada.
4. Editar a NF (só cabeçalho) → volta ao detalhe.
5. Excluir a NF → faturas e produtos somem (CASCADE).
6. Tentar excluir o **Fornecedor** vinculado → mensagem PT-BR de bloqueio
   (`ProtectedError`), sem quebrar.

## Fora de escopo (follow-up)

Operação **"Processar"**: atualizar produtos (preço/estoque, `F("quantity") + qtd`)
e gerar despesas a partir das faturas, num serviço `@transaction.atomic` em
`sign/services.py` reusando `create_expense`/`reais_to_cents`.
