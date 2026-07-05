# Fluxo de navegação e shell de UI

Como o usuário se move pelo sistema e como o "esqueleto" visual
(`sign/templates/sign/base.html`) é montado. Toda tela estende esse shell.

## Shell base (`base.html`)

Estrutura fixa herdada por todas as páginas:

```
┌────────────┬──────────────────────────────────────────────┐
│            │  header: [☰ toggle]  ...  [⚙ config] [🛒 (n)] │
│  SIDE MENU ├──────────────────────────────────────────────┤
│  (navy)    │  main:                                         │
│            │    {mensagens flash}                           │
│  Comercial │    {% block content %}                         │
│   Fabric.  │                                                │
│   Produtos │                                                │
│   Vendas   │                                                │
│  Financeiro│                                                │
│   Despesas │                                                │
│  Social    │                                                │
│   Clientes │                                                │
└────────────┴──────────────────────────────────────────────┘
                                          [toast verde]  ◄ feedback do carrinho
```

Blocos sobrescrevíveis: `{% block title %}` (default `SIGN-KR`),
`{% block header %}` (área para botões da tela) e `{% block content %}`.

## Side menu — seções

O menu lateral (`bg-navy`, largura `w-64`) agrupa os itens por **seção** (rótulo
uppercase), espelhando as áreas funcionais do sistema:

| Seção | Item | Ícone | Rota |
|---|---|---|---|
| **Comercial** | Produtos | `fa-tag` | `sign:product_list` |
| | Vendas | `fa-receipt` | `sign:sale_list` |
| **Financeiro** | Despesas | `fa-money-bill-wave` | `sign:expense_list` |
| **Social** | Clientes | `fa-users` | `sign:client_list` |

> **Fabricantes** não fica no side menu — é acessado pelo **dropdown do header**
> (ver seção Header).

As seções e os itens dentro de cada seção seguem **ordem alfabética**.

No topo, a marca (`{{ company.display_name }}` — razão social se preenchida, senão o
nome; vinda do modelo `Company` singleton via context processor) linka para a lista de
produtos.

### Item ativo

O item da seção atual é destacado em **`bg-blue-600`**. A detecção é por
`request.resolver_match.url_name` (capturado num `{% with url_name=... %}`):

- `{% if 'product' in url_name %}` → Produtos
- `{% if 'sale' in url_name or url_name == 'checkout' %}` → Vendas (inclui o checkout)
- `{% if 'expense' in url_name or 'installment' in url_name %}` → Despesas (inclui parcelas)
- `{% if 'client' in url_name %}` → Clientes

> Ao adicionar uma rota nova, garanta que o `url_name` "case" com o `if` da seção
> certa (e não colida com outra — ex.: `client` não casa `manufacturer`).

## Header

Barra branca no topo da área de conteúdo, com:

- **Toggle do menu** (`#sidebarToggle`, `fa-bars`): um `<script>` no fim do
  `<body>` alterna `-translate-x-full` na sidebar e `ml-64`/`ml-0` no `#content`
  (mostra/oculta o menu com transição).
- **`{% block header %}`**: ponto de extensão para botões específicos da tela.
- **Dropdown de configurações** (`#settingsToggle`, `fa-gear`, alinhado à direita):
  abre um **dropdown** (vanilla JS — alterna `hidden`, fecha em clique-fora e `Escape`,
  abre para a esquerda com `right-0`) com os itens **Fabricantes** (`fa-industry`,
  `sign:manufacturer_list`) e **Configurações** (`fa-gears`, `sign:company_settings`).
- **Carrinho** (`fa-cart-shopping`, alinhado à direita): leva a
  `sign:cart_detail`. Tem um **badge** (`#cart-count`) com o nº de produtos
  distintos, vindo do context processor `cart_count` (global em todo template);
  fica **oculto quando 0**.

## Mensagens (flash) e toast

- **Mensagens flash** do Django são renderizadas no topo do `main`: borda/fundo
  **vermelho** para `error`, **verde** para os demais. É o canal padrão de
  feedback de create/update/delete e de erros de validação.
- **Toast** (`#cart-toast`, canto inferior direito): feedback rápido e sem reload
  das ações do carrinho, controlado pelo `cart.js`.

## Mapa de navegação (rotas)

```
/                      → redireciona p/ sign:product_list

Produtos     products/ · products/new/ · products/<pk>/ · .../edit/ · .../delete/
Fabricantes  manufacturers/ · .../new/ · .../<pk>/edit/ · .../<pk>/delete/
Clientes     clients/ · clients/new/ · clients/<pk>/ · .../edit/ · .../delete/
Carrinho     cart/ · cart/add/ · cart/update/ · cart/remove/     (add/update/remove = AJAX POST)
Vendas       sales/checkout/ · sales/ · sales/<pk>/
Despesas     expenses/ · expenses/new/ · expenses/<pk>/ · .../edit/ · .../delete/
Parcelas     expenses/<expense_pk>/installments/new/
             installments/<pk>/edit/ · .../delete/ · .../pay/
Configurações settings/company/     (singleton, editável no dropdown do header)
```

Padrões de navegação CRUD (para onde cada salvar/cancelar volta) em
[`cadastros.md`](cadastros.md) e em
[`../arquitetura/convencoes.md`](../arquitetura/convencoes.md).
