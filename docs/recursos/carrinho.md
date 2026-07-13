# Carrinho de Compras (app `sign`)

Carrinho de compras **persistido em cookie** (sem banco), com UI **sem reload**
via AJAX (`fetch`). Esta documentação registra os fluxos e decisões não óbvias —
leia antes de alterar o carrinho.

## Armazenamento — cookie (sem banco)

- O carrinho vive no cookie **`cart`** como JSON: `{ "<product_id>": <quantidade> }`.
- Helper central: **`sign/cart.py`** (classe `Cart`).
  - `__init__(request)`: lê e **normaliza** o cookie (chaves `str`, quantidades
    `int > 0`; ignora valores inválidos). Em JSON corrompido, assume `{}`.
  - `add` (soma à existente), `set` (substitui), `remove`, `quantity_of`.
  - `__len__`: nº de **produtos distintos** (usado no badge).
  - `items()`: resolve os produtos em **uma** query (`Product.objects.in_bulk`),
    ignorando ids cujo produto não exista mais; devolve `product`, `quantity`,
    `unit_price` (reais) e `total_price` (reais).
  - `total_price_cents()`/`total_price()`: total em **centavos** (inteiro) e em
    reais — cálculo monetário sempre sobre centavos, **nunca em float** (convenção
    do projeto; ver [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md#valores-monetários--centavos-inteiros)).
  - `save(response)`: grava o cookie com `max_age = 30 dias` e `samesite="Lax"`.
- **As escritas são feitas pelas views**, que validam e chamam `cart.save(response)`
  na resposta JSON. O cookie é a fonte de verdade; o servidor só o lê para
  renderizar (badge e tela inicial do carrinho).

## Fluxo AJAX (sem reload)

- **Endpoints** (`sign/views/cart.py`, registrados em `sign/urls.py`):
  - `cart_detail` (GET) → `sign/cart/detail.html` (render inicial do servidor).
  - `cart_add` (POST, JSON) → soma a quantidade; valida estoque.
  - `cart_update` (POST, JSON) → define a quantidade; valida estoque.
  - `cart_remove` (POST, JSON) → remove o item.
- Os endpoints de escrita retornam `JsonResponse` (`{"ok": true, "cart_count", ...}`
  ou `{"ok": false, "error": "<msg PT-BR>"}` com `status=400`) e gravam o cookie.
  Valores monetários nos JSON são **formatados no backend** a partir de centavos
  (`_format_cents` → `"12.34"`), para o JS apenas exibir.
- **CSRF**: o `base.html` expõe `<meta name="csrf-token" content="{{ csrf_token }}">`
  (referenciar `csrf_token` garante o cookie `csrftoken`). O JS (`cart.js`) envia o
  header `X-CSRFToken` em cada `fetch`.
- **JS** (`sign/static/sign/js/cart.js`, primeiro arquivo JS do projeto): helper
  `postCart(url, data)`; controla o modal de adicionar (tela de produtos) e as
  ações de atualizar/remover (tela do carrinho), atualizando badge, subtotais,
  total e linhas **sem recarregar**. Linkado no `base.html` via
  `<script src="{% static 'sign/js/cart.js' %}" defer>`.

## UI

- **Listagem de produtos** (`sign/templates/sign/products/list.html`): cada linha
  tem um botão `fa-cart-plus` (`.cart-add-btn`, com `data-id`/`data-name`/`data-max`)
  que abre um **modal único** (`#cart-modal`) para escolher a quantidade. O modal
  também exibe, a partir dos `data-*` do botão, informações do produto: fabricante,
  código do fabricante, código de barras e quantidade disponível (campos opcionais
  vazios aparecem como "—"). Produtos **sem estoque** (`quantity == 0`) exibem o
  ícone desabilitado (cinza).
- **Header** (`base.html`): botão `fa-cart-shopping` → `cart_detail`, com **badge**
  (`#cart-count`) mostrando o nº de produtos distintos; oculto quando 0.
- **Tela do carrinho** (`sign/templates/sign/cart/detail.html`): tabela com input
  de quantidade (`min=1`/`max=estoque`) + botão atualizar (`fa-check`), subtotal,
  remover (`fa-trash`), total geral e estado vazio. O contêiner `#cart-app` carrega
  as URLs de update/remove em `data-*`.
  - **Colunas de código condicionais**: as colunas "Cód. barras" e "Cód." (código do
    fabricante) só aparecem quando `company.sales_show_barcode` /
    `company.sales_show_manufacturer_code` estão ativas (config da empresa — ver
    [`vendas.md`](vendas.md#personalização-de-exibição)). O `tfoot` "Total geral" tem
    `colspan` **variável** (`7`/`6`/`5`) que acompanha quantas dessas duas colunas
    estão visíveis — ao mexer nas colunas do carrinho, ajuste também esse `colspan`.

## Validações (no backend — fonte de verdade)

- Quantidade deve ser **inteira ≥ 1** (nada negativo/zero).
- O total resultante **não pode ultrapassar o estoque** (`product.quantity`):
  - `cart_add`: valida `quantidade_no_carrinho + nova <= estoque`.
  - `cart_update`: valida `nova <= estoque`.
- Os atributos `min`/`max` nos inputs são **apenas auxílio visual**; a validação
  autoritativa é no backend.

## Build do Tailwind

Novas classes (modal, badge) exigem rebuild do `output.css` (committado, app
offline) — ver
[`../arquitetura/convencoes.md`](../arquitetura/convencoes.md#tailwind-css-build):

```
./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify
```

## Nota — PyWebView (persistência do cookie)

O carrinho deve **persistir ao fechar/reabrir** o app, o que depende do cookie
sobreviver entre execuções. O launcher desktop **`app.py`** (raiz) já resolve
isso: inicia o webview com **perfil persistente** —
`webview.start(private_mode=False, storage_path=<%LOCALAPPDATA%\SIGN-KR\webview>)`.
Sem esse par (`private_mode=False` + `storage_path`), o webview roda em modo
privado e descarta o cookie `cart` a cada fechamento, quebrando a persistência do
carrinho. Ao mexer no launcher, **não remova** essa configuração.

## Verificação rápida

```
./venv/Scripts/python.exe manage.py check
./venv/Scripts/python.exe manage.py runserver
```
Fluxo: listar produtos → adicionar via modal (badge atualiza sem reload) →
tentar quantidade > estoque (erro no modal) → abrir carrinho → atualizar/remover
(subtotal/total/badge sem reload) → re-adicionar produto (quantidade soma) →
fechar/reabrir o navegador (carrinho persiste).
