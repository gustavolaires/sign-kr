# Vendas / Checkout (app `sign`)

Finalização de venda no passo **seguinte ao carrinho**. Esta documentação
registra os models, a matemática monetária e as decisões não óbvias — leia antes
de alterar o checkout ou os relatórios de vendas.

## Visão geral do fluxo

1. Carrinho (cookie, ver [`docs/carrinho.md`](carrinho.md)) → botão **"Finalizar
   compra"** (abaixo da lista de itens) leva a `sign:checkout`.
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
  `change_cents` (troco), `total_cents`, `obs`, `created_at`. `client` é
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

## Matemática e regras (`sign/services.py`)

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
- **Tailwind**: ao mudar classes nos templates, rebuild do `output.css` (app
  offline, sem CDN — ver
  [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md#tailwind-css-build)):
  `./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify`.

## Decisões deixadas para depois

- Sem campo de **status** na venda (não há fluxo de cancelamento/estorno ainda).
- **Descontos por item** (promoções) — campos já existem em `SaleItem`, sem UI.
