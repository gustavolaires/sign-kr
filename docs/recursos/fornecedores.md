# Fornecedores (app `sign`)

Cadastro de **Fornecedores** (quem vende/entrega os produtos) com uma sub-lista
de **Representantes** (contatos). CRUD em Tailwind seguindo as convenções de
Clientes/Empresa (ver [`clientes.md`](clientes.md)); a parte nova é a relação
**um-para-muitos** Fornecedor→Representantes, com duas formas de manejo
combinadas (ver abaixo). Leia antes de alterar os models, forms ou templates
desta área.

## Models (`sign/models.py`)

| Model | Campos | Observações |
|---|---|---|
| `Supplier` | `name`, `cnpj`, `state_registration`, `multiple_brands`, `manufacturer`, `email`, `phone_primary`, `phone_secondary` | Só `name` é obrigatório; os demais usam `blank=True`. |
| `Representative` | `supplier` (FK), `name`, `email`, `phone_primary`, `phone_secondary` | `supplier` é FK `CASCADE` (`related_name="representatives"`); só `name` é obrigatório. |

- **CNPJ / telefones**: gravados **só com dígitos** (máscara apenas visual);
  mesmo padrão de `Client`/`Company`.
- **Inscrição estadual** (`state_registration`): **texto livre** (pode ser
  alfanumérica ou "ISENTO") — **sem** máscara e **sem** `clean_`.
- **Múltiplas marcas** (`multiple_brands`): `BooleanField(default=True)`. Quando
  **falso**, o fornecedor trabalha com uma marca específica, indicada em
  `manufacturer` (FK opcional para `Manufacturer`, `on_delete=SET_NULL`,
  `related_name="suppliers"`). No form, o `<select>` de marca só aparece com o
  checkbox desmarcado (toggle via `<script>`); o `SupplierForm.clean()` zera a
  marca quando `multiple_brands` é verdadeiro.
- `Meta.ordering = ["name"]` nos dois models.
- Nada referencia `Supplier` com `PROTECT` (não há `ProtectedError` a tratar);
  excluir o fornecedor remove os representantes por CASCADE.

## Forms (`sign/forms.py`)

- **`SupplierForm`** (`StyledModelForm`) — campos `name`, `cnpj`,
  `state_registration`, `email`, `phone_primary`, `phone_secondary`. `cnpj`/
  telefones usam `data-mask` (`cpf-cnpj`/`phone`) + `clean_*` com `_only_digits`
  (espelha `CompanyForm`). `state_registration` não tem máscara nem `clean_`.
- **`RepresentativeForm`** (`StyledModelForm`) — `name`, `email`,
  `phone_primary`, `phone_secondary`; telefones com `data-mask="phone"` +
  `clean_*`.

## Manejo dos representantes (duas formas combinadas)

- **Criação: inline no form do fornecedor.** O `form.html` (apenas quando
  **não** há `form.instance.pk`) mostra uma seção **Representantes** com linhas
  dinâmicas (`<template id="representative-row-template">` clonado por
  `static/sign/js/suppliers.js`; botão "Adicionar representante"). Os inputs têm
  **nomes paralelos** (`rep_name`, `rep_email`, `rep_phone_primary`,
  `rep_phone_secondary`) — padrão dos pagamentos do checkout
  (`Sale`→`SalePayment`). O `SupplierCreateView.form_valid` salva o fornecedor,
  lê as listas via `request.POST.getlist(...)`, **ignora linhas sem nome** e faz
  `Representative.objects.bulk_create(...)`.
- **Edição/Exclusão/Adição posterior: páginas separadas.** A partir da tela de
  **detalhes** do fornecedor, cada representante é adicionado/editado/excluído em
  sua própria página (`RepresentativeCreateView`/`UpdateView`/`DeleteView`) —
  padrão Despesas→Parcelas (`ExpenseInstallment*View`). O `Create` usa `dispatch`
  para carregar o fornecedor pai por `supplier_pk` e seta `form.instance.supplier`;
  todas redirecionam de volta para `supplier_detail`. O form de **edição** do
  fornecedor **não** mostra linhas de representante.

## Máscaras em linhas dinâmicas (`sign/static/sign/js/masks.js`)

O `masks.js` expõe `window.bindMasks(root)` e liga os handlers a cada
`[data-mask]` dentro de `root` (marcando `dataset.maskBound` para não religar).
No load roda `bindMasks(document)`; o `suppliers.js` chama `window.bindMasks(row)`
após clonar cada linha nova, para a máscara de telefone funcionar nelas.

## Views (`sign/views/suppliers.py`) e URLs (`sign/urls.py`)

CBVs genéricas + `SuccessMessageMixin` (padrão `clients.py`). Paths em inglês.

| Nome de rota | Path | View |
|---|---|---|
| `supplier_list` | `suppliers/` | `SupplierListView` (filtros Nome/CNPJ/E-mail + ordenação Nome/CNPJ) |
| `supplier_create` | `suppliers/new/` | `SupplierCreateView` (cria reps inline no `form_valid`) |
| `supplier_detail` | `suppliers/<pk>/` | `SupplierDetailView` (dados + tabela de representantes) |
| `supplier_update` | `suppliers/<pk>/edit/` | `SupplierUpdateView` |
| `supplier_delete` | `suppliers/<pk>/delete/` | `SupplierDeleteView` (CASCADE remove reps) |
| `representative_create` | `suppliers/<supplier_pk>/representatives/new/` | `RepresentativeCreateView` |
| `representative_update` | `representatives/<pk>/edit/` | `RepresentativeUpdateView` |
| `representative_delete` | `representatives/<pk>/delete/` | `RepresentativeDeleteView` |

Views exportadas em `sign/views/__init__.py`.

## Templates (`sign/templates/sign/suppliers/`)

- `list.html`, `detail.html`, `form.html`, `confirm_delete.html` e
  `representatives/{form,confirm_delete}.html` — estendem `base.html`.
- **Listagem**: colunas Nome, CNPJ (`|cpf_cnpj`), E-mail, Telefone principal
  (`|phone`) + ações; filtros recolhíveis (Nome/CNPJ/E-mail) e ordenação
  clicável (Nome/CNPJ), idêntica à de Clientes.
- **Form**: seções **Dados básicos** (Nome, CNPJ, Inscrição estadual) e
  **Contato** (E-mail, telefones) via `{% include "sign/clients/_field.html" %}`
  (reutiliza o partial de campo dos Clientes — **não** há `_field.html` próprio).
  Só na criação: a seção **Representantes** com as linhas dinâmicas.
- **Detalhes**: seções Dados básicos e Contato + tabela de representantes com
  ações Editar/Excluir e botão "Adicionar representante".

## Menu

Item **Fornecedores** (`fa-solid fa-building-user`) no grupo **Social** do
`base.html` (após Clientes); ativo quando `'supplier' in url_name or
'representative' in url_name`.

## Admin (`sign/admin.py`)

`SupplierAdmin` (`list_display`/`search_fields` no estilo `ClientAdmin`) com
`RepresentativeInline` (`TabularInline`).

## Build / migrações

- Migração: `0009_supplier_representative`.
- Rebuild Tailwind após mexer em classes:
  `./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify`.

## Verificação rápida

1. `./venv/Scripts/python.exe manage.py check`.
2. Menu **Social → Fornecedores → Novo fornecedor** → criar só com Nome.
3. Criar outro completo (CNPJ, Inscrição estadual "ISENTO", e-mail, telefones)
   **adicionando 2 representantes inline** (conferir máscara nas linhas novas).
4. Listar → conferir filtros e ordenação; CNPJ com máscara.
5. Detalhe → adicionar 3º representante (página separada), editar um e excluir
   outro.
6. Editar o fornecedor (sem linhas de representante) → volta ao detalhe.
7. Excluir o fornecedor → representantes somem (CASCADE).
