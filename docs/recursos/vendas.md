# Vendas / Checkout (app `sign`)

Finalização de venda no passo **seguinte ao carrinho**. Esta documentação
registra os models, a matemática monetária e as decisões não óbvias — leia antes
de alterar o checkout ou os relatórios de vendas.

## Visão geral do fluxo

1. Carrinho (cookie, ver [`docs/carrinho.md`](carrinho.md)) → botão **"Finalizar"**
   (abaixo da lista de itens) leva a `sign:checkout`.
2. `checkout` (GET) renderiza o resumo do carrinho (somente leitura) + cliente
   (opcional) + desconto + pagamentos + observações.
3. `checkout` (POST) delega à camada de serviço `sign.services.create_sale`, que
   cria tudo de forma **atômica**, baixa o estoque e limpa o cookie do carrinho.
4. Redireciona para `sign:sale_detail` (comprovante read-only). Histórico em
   `sign:sale_list` (menu **Comercial → Vendas**).

## Models (`sign/models.py`)

- **`Sale`** — documento imutável da venda. Campos monetários em **centavos**
  (`PositiveIntegerField`, sufixo `_cents`). Ordem dos campos: `client`,
  `subtotal_cents`, `has_perc_discount`, `perc_discount`, `discount_cents`,
  `discount_obs` (observações do desconto, texto livre — preenchido pela
  calculadora, ver UI), `change_cents` (troco), `total_cents`, `obs`,
  `created_at`. `client` é
  `PROTECT` + opcional (venda avulsa = `NULL`). `Meta.ordering = ["-id"]`;
  `created_at` tem `db_index=True` (relatórios). Propriedades em reais:
  `subtotal`, `discount`, `change`, `total`.
- **`ProductSnapshot`** — **réplica reaproveitável** dos dados descritivos do
  produto no momento da venda. O **preço NÃO entra no snapshot** (varia por venda,
  fica em `SaleItem`), o que torna o reaproveitamento eficaz.
  - `manufacturer_name` é **denormalizado** (texto), não FK — senão renomear o
    fabricante alteraria vendas antigas.
  - `content_hash` (`unique`): sha256 de uma **serialização canônica** (JSON com
    ordem fixa) de `[product_id, name, description, barcode, manufacturer_name,
    manufacturer_code, unit_type]`. Inclui `product_id` ⇒ **dedup por produto**.
  - `compute_hash(...)` + `get_or_create_for(product)`: reaproveita um snapshot
    idêntico (mesmo hash) em vez de criar um novo. Vendas do mesmo produto
    inalterado compartilham **uma** linha; editar o produto gera um novo snapshot.
  - `product` é `SET_NULL`: o produto pode ser excluído sem perder o histórico. O
    hash é um **fingerprint de criação** — não é recalculado quando `product` vira
    `NULL`.
- **`SaleItem`** — linha da venda. FK `sale` (`CASCADE`) e `product_snapshot`
  (`PROTECT` — snapshot nunca é apagado). Guarda `quantity`, `unit_price_cents`
  (preço no momento da venda), `subtotal_cents`, `total_cents`. Campos de desconto
  por item (`has_perc_discount`/`perc_discount`/`discount_cents`) existem mas são
  **0 na v1** — serão preenchidos pelo módulo de promoções.
- **`SalePayment`** — forma de pagamento. `PaymentType`: `credit`/`debit`/`cash`/
  `pix`/`other`. `installments` só faz sentido no crédito (normalizado para 1 nos
  demais). `UniqueConstraint(sale, payment_type)` ⇒ **no máximo 1 pagamento por
  tipo por venda**.

## Matemática e regras (`sign/services/sales.py`)

Toda a conversão reais↔centavos usa `Decimal` + `ROUND_HALF_UP` (helper
`reais_to_cents`, mesma fórmula de `ProductForm.save`) — **nunca float**.
`create_sale(...)` roda em `transaction.atomic()` e levanta `ValidationError`
(PT-BR) antes de qualquer escrita:

1. Carrinho vazio → erro.
2. **Revalida o estoque** item a item contra `Product.quantity` atual.
3. `subtotal_cents = Σ unit_price_cents × quantidade`.
4. Desconto da venda: percentual (0–100) → `subtotal × % `; ou valor em reais.
   Validado `0 ≤ desconto ≤ subtotal`. `total_cents = subtotal − desconto`.
5. **Pagamentos**: soma deve ser **≥ total** (permite troco);
   `change_cents = soma − total`. Sem pagamento só quando `total == 0`. Tipo
   duplicado é bloqueado (além da constraint do BD).
6. Cria `Sale` → `SaleItem` (com `ProductSnapshot.get_or_create_for`) → baixa
   `Product.quantity` via `F("quantity") - qty` → cria `SalePayment`.

A view (`sign/views/sales.py`, `checkout`) parseia cliente/desconto/pagamentos do
POST, chama o serviço e, em sucesso, **limpa o cookie do carrinho**
(`response.delete_cookie`). Em erro, re-renderiza preservando os valores.

> Excluir um cliente com vendas é bloqueado (`PROTECT`); `ClientDeleteView` trata
> o `ProtectedError` com mensagem PT-BR.

## UI

- Telas em `sign/templates/sign/sales/`: `checkout.html`, `list.html`,
  `detail.html`. Estendem o `base.html` (side menu navy + header).
- `checkout.js` (`sign/static/sign/js/`, padrão vanilla de `cart.js`): linhas de
  pagamento dinâmicas, alternância desconto %/R$, parcelas só no crédito,
  recálculo ao vivo de subtotal/desconto/total/pago/troco (**só exibição** — o
  backend é autoritativo) e bloqueio de duplo-submit.
- **Calculadora de desconto** (modal `#discount-calc-modal`, aberto pelo ícone
  `fa-calculator` no card "Desconto"): _range sliders_ (0–100%) num toggle
  segmentado **Valor total** (um slider sobre o total) / **Por produto** (um
  slider por item, sobre o subtotal de cada um). "Aplicar" resolve o desconto em
  **R$ (valor)** no campo existente e escreve um resumo no campo **Observações do
  desconto** (`discount_obs`). Os subtotais por produto chegam ao JS via
  `{{ calc_items|json_script:"calc-items-data" }}` (helper `_calc_items` na view).
  É **só exibição**: a venda continua gravando **um** desconto agregado em
  `discount_cents`; os campos de desconto por item de `SaleItem` seguem 0.
  `discount_obs` é impresso no comprovante e no orçamento (`receipt.html`).
- **Tailwind**: ao mudar classes nos templates, rebuild do `output.css` (app
  offline, sem CDN — ver
  [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md#tailwind-css-build)):
  `./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify`.

## Comprovante (não fiscal)

Documento de **garantia/troca**, sem valor fiscal. A tela de detalhe tem o botão
**"Comprovante"** → `sign:sale_receipt` (`sales/<pk>/receipt/`,
view `sale_receipt` em `sign/views/sales.py`).

- **Dois formatos**, alternáveis pelo querystring `?format=`: `58mm` (papel térmico,
  **padrão**) e `a4` (folha larga). Valor inválido cai no default 58mm.
- Template **standalone** `sign/templates/sign/sales/receipt.html` — **não** estende
  `base.html`; tem CSS próprio embutido (com `@page` por formato) e **não depende do
  Tailwind** (não exige rebuild do `output.css`).
- O template consome um **contexto normalizado** (`items`, `payments`, `op_label`,
  `number`, `created_at`, `subtotal`/`discount`/`total`/`change`, `client`, `obs`,
  `mode`) montado pelo helper `_receipt_context` — não acessa mais o objeto `Sale`
  diretamente. Isso permite reusá-lo também para o **orçamento** (ver abaixo).
- Impressão via **diálogo nativo** (`window.print()`) — 100% offline, coerente com o
  PyWebView; a barra de ações some no `@media print`. Salvar em PDF é feito escolhendo
  esse destino no próprio diálogo (não dá para pré-selecioná-lo por JS, então não há
  botão separado).
- **Venda avulsa** (sem cliente): os campos do cliente são renderizados **em branco**.
- **Dados da empresa**: modelo `Company` (singleton, `pk=1`), exposto a todos os
  templates pelo context processor `sign.context_processors.company` (também alimenta o
  nome no side menu do `base.html`). Editável pela UI no dropdown do header
  (`sign:company_settings`). Campos mascarados (CNPJ, telefones, CEP) guardam só dígitos.

## Orçamento (a partir do checkout)

Mesmo comprovante, montado a partir dos dados **ainda não salvos** da tela de
`Finalização` (checkout) — usado como **orçamento**. Botão **"Orçamento"** (ícone
`fa-scroll`) no rodapé do checkout: submete o próprio formulário (mesma aba, via
`formaction`) a `sign:sale_quote` (`sales/quote/`, só POST).

- Reusa o `receipt.html` (mesmo contexto normalizado). Única diferença de conteúdo:
  `op_label = "Orçamento"` (título no 58mm, Natureza da operação no A4). **Sem número**
  (não há `Sale` persistida).
- **Nada é gravado**. Os montantes vêm de `services.compute_quote_amounts` — versão
  **lenient** das fórmulas de `create_sale`: não valida estoque nem exige pagamento ≥
  total, clampa desconto e ignora linhas de pagamento inválidas (nunca levanta
  `ValidationError`). `create_sale` permanece o caminho autoritativo da venda real.
- **Sem perder dados**: o orçamento carrega os campos do checkout como `<input hidden>`
  (`_quote_hidden_fields`); trocar formato re-posta a `sale_quote` e o botão **"Voltar"**
  re-posta ao `checkout` com `intent=edit`, que apenas re-renderiza o formulário
  preenchido (reusa o `rerender()`), sem finalizar a venda.

## Decisões deixadas para depois

- Sem campo de **status** na venda (não há fluxo de cancelamento/estorno ainda).
- **Descontos por item** (promoções) — campos já existem em `SaleItem`, sem UI.
- **Gerar PDF determinístico do comprovante** — hoje o PDF depende do usuário
  escolher esse destino no diálogo de impressão. Melhoria: gerar o PDF no backend
  (WeasyPrint ou xhtml2pdf) e, por ser app desktop, salvá-lo via **diálogo nativo
  "Salvar como" do PyWebView** (`window.create_file_dialog(SAVE_DIALOG, ...)`),
  deixando o usuário escolher a pasta. Requer ponte JS↔Python (`window.pywebview.api`,
  só funciona empacotado, não no navegador de dev) e atenção ao empacotamento
  PyInstaller (WeasyPrint tem dependências nativas GTK/Pango/Cairo; `xhtml2pdf` é
  Python puro, porém com CSS mais limitado).
