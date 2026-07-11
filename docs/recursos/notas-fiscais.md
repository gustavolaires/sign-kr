# Notas Fiscais de Entrada (app `sign`)

Registro das **Notas Fiscais de Entrada (NF)** recebidas dos fornecedores, com
suas **Faturas/Duplicatas** e seus **Produtos**. Segue o padrão master-detail de
[`fornecedores.md`](fornecedores.md) (Fornecedor→Representantes): as faturas e os
produtos existem **apenas dentro da NF** e são criados inline no cadastro da NF
**e** editados/excluídos/adicionados depois em páginas próprias. Valores em
centavos conforme [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md).

A operação **"Processar"** efetiva a NF (entrada de estoque, precificação dos
produtos e geração de despesas). É **única e irreversível**: depois de processada
a NF fica **imutável** (não pode ser editada, excluída nem reprocessada). Ver a
seção [Processamento](#processamento).

## Models (`sign/models.py`)

| Model | Campos | Observações |
|---|---|---|
| `InboundInvoice` | `number`, `issue_date`, `delivery_date`, `supplier` (FK), + 10 valores `_cents`, `processed`, `processed_at` | Só `number`/`supplier` exigidos; datas e valores opcionais (default 0). `processed` (bool, default `False`) + `processed_at` marcam o estado terminal. |
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
- **`round_price_cents(cents, rounding_type)`** — arredonda um preço (centavos)
  **para cima** ao passo de `RoundingType` (`cent`=1, `cent_10`=10, `real`=100,
  `real_2`=200, `real_5`=500, `real_10`=1000). É a lógica canônica de precificação.
- **`suggested_price_cents(item, company)`** — `item.unit_price_cents *
  company.price_multiplier`, arredondado por `round_price_cents`.
- **`suggest_product_match(item)`** — sugere o `Product` já cadastrado
  (retorna `(product, motivo)`), tentando em ordem: (1) token exato em
  `nf_search_id`; (2) `name`/`description` do produto == descrição do item
  (igualdade case-insensitive). `(None, None)` se nada casar. Obs.: no primeiro
  processamento o `nf_search_id` costuma estar vazio (é preenchido justamente ao
  processar/associar), então as associações iniciais tendem a vir por descrição
  ou manuais — depois disso passam a casar por `nf_search_id`.
- **`process_inbound_invoice(invoice, *, decisions)`** — `@transaction.atomic`.
  Ver [Processamento](#processamento).

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
| `invoice_process` | `invoices/<pk>/process/` | `invoice_process` (function-based; tela de confirmação + execução) |
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
>
> **Bloqueio pós-processamento**: o helper `_redirect_if_processed(request,
> invoice)` (redirect ao detalhe + `messages.error`) é chamado no `dispatch` de
> `InboundInvoiceUpdateView`/`DeleteView` e de **todas** as views de
> faturas/itens (create/update/delete). Uma NF processada é imutável.

## Templates (`sign/templates/sign/invoices/`)

- `list.html`, `detail.html`, `form.html`, `confirm_delete.html` e
  `duplicates/{form,confirm_delete}.html`, `items/{form,confirm_delete}.html` —
  estendem `base.html` e reutilizam o partial `sign/clients/_field.html`.
- **Detalhe**: seções *Dados da nota* e *Valores* + tabelas de **Faturas** e
  **Produtos** com botão "Adicionar" e ações Editar/Excluir por linha. Botão
  **Processar** (`fa-file-waveform`, `blue-600`) à esquerda do Editar quando a NF
  ainda **não** foi processada; depois de processada, os botões de ação somem, um
  badge verde **"Processada em …"** aparece e as colunas de ações ficam ocultas.
- **`process.html`** (tela de confirmação): aviso de operação permanente; um
  cartão por produto com `<select>` de produto associado, checkbox **"Produto
  novo"**, `<select>` de fabricante (só para novo) e input de **preço de venda
  sugerido** (editável); tabela de faturas → despesas. Inputs keyed por item id
  (`item_product_<id>`, `item_is_new_<id>`, `item_manufacturer_<id>`,
  `item_price_<id>`). JS **`invoice-process.js`**: alterna existente/novo e mostra
  **alerta de redução de preço** (preço < atual do produto associado).
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

- Migrações: `0011_inboundinvoice_invoiceduplicate_invoiceitem` (models) e
  `0014_inboundinvoice_processed_inboundinvoice_processed_at` (campos de estado).
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
7. Detalhe → **Processar** → conferir sugestões, confirmar; no detalhe conferir o
   badge "Processada" e que Editar/Deletar e o CRUD de itens/faturas sumiram.
   Conferir no estoque/preços dos produtos e nas despesas geradas.

## Processamento

Operação **única e irreversível** que efetiva a NF. Fluxo:

1. **Tela de confirmação** (`invoice_process`, GET): para cada `InvoiceItem`,
   `suggest_product_match` sugere um produto e `suggested_price_cents` sugere o
   preço de venda. O usuário valida/corrige na tela — pode trocar o produto
   associado, marcar **"Produto novo"** (escolhendo o fabricante) e ajustar o
   preço. Fornecedor mono-marca já vem com o fabricante pré-selecionado.
2. **Execução** (`process_inbound_invoice`, POST, `@transaction.atomic`):
   - **Produto existente**: soma o estoque (`quantity = F("quantity") + qtd`),
     **sobrescreve** `unit_price_cents` com o preço confirmado e, se o código do
     item não estiver em `nf_search_id`, **anexa** (para casar em NFs futuras).
   - **Produto novo**: cria `Product` com os dados da nota (`name`=descrição,
     `nf_search_id`=código, `manufacturer_code`=código se mono-marca,
     `min_stock`=`Company.low_stock_threshold`, preço confirmado).
   - **Faturas**: todas as `InvoiceDuplicate` da NF viram **uma** `Expense`, com
     **uma parcela por fatura** (cada uma com o valor/vencimento da fatura). As
     parcelas são numeradas por ordem de vencimento e o total de parcelas é a
     quantidade de faturas. Não usa `create_expense` (que gera parcelas de valor
     fixo/mensais).
   - Marca `processed=True` / `processed_at=now`.
3. **Preço sugerido** = `custo × Company.price_multiplier`, arredondado **para
   cima** conforme `Company.rounding_type` (`round_price_cents`).
4. Quantidade: `InvoiceItem.quantity` (Decimal) é arredondada para inteiro
   (`ROUND_HALF_UP`) porque `Product.quantity` é inteiro.

> Reprocessar levanta `ValidationError`; a UI e as views de edição/exclusão da
> NF e de seus filhos bloqueiam qualquer alteração após o processamento.
