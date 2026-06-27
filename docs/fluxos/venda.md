# Fluxo de venda (carrinho → checkout → comprovante)

Percurso completo de uma venda, da escolha do produto ao comprovante, com ênfase
no **processamento** que acontece no backend. Referência das features:
[`recursos/carrinho.md`](../recursos/carrinho.md) e
[`recursos/vendas.md`](../recursos/vendas.md).

## Visão de ponta a ponta

```
  Lista de produtos
        │  clica 🛒 no produto → modal → quantidade
        ▼  POST AJAX cart/add  (valida estoque, grava cookie)
  Carrinho (cookie JSON)  ◄── atualizar/remover (AJAX, sem reload)
        │  "Finalizar compra"
        ▼  GET sales/checkout/
  Checkout  (resumo read-only + cliente + desconto + pagamentos + obs)
        │  POST sales/checkout/
        ▼  create_sale(...)  @transaction.atomic
  Sale + SaleItem(+Snapshot) + SalePayment   ·   baixa de estoque   ·   limpa cookie
        ▼  redirect
  Comprovante  sales/<pk>/   (read-only)        Histórico: sales/
```

## 1. Adicionar ao carrinho (AJAX, sem banco)

- Na lista de produtos, cada item tem um botão `fa-cart-plus` que abre um **modal
  único** para escolher a quantidade (produtos com estoque 0 ficam desabilitados).
- O JS `cart.js` faz `fetch` POST para `cart/add` com header `X-CSRFToken`
  (token exposto em `<meta name="csrf-token">` no `base.html`).
- **Processamento no backend** (`sign/views/cart.py`): valida quantidade inteira
  ≥ 1 e que `quantidade_no_carrinho + nova ≤ estoque`; em sucesso soma no cookie
  via `Cart.add` e responde `JsonResponse` com o novo `cart_count` e totais
  (formatados a partir de centavos). O badge e o toast atualizam sem reload.
- O carrinho vive **só no cookie** `cart` (`{"<product_id>": <qtd>}`), com
  `max_age` de 30 dias. O servidor lê para renderizar; o estoque é a verdade
  autoritativa e é **revalidado** a cada operação. Detalhes e nota sobre
  persistência no PyWebView em [`recursos/carrinho.md`](../recursos/carrinho.md).

## 2. Checkout — GET (montar a tela)

`checkout` (FBV em `sign/views/sales.py`):

- Se o carrinho estiver **vazio**, redireciona ao carrinho com mensagem de erro.
- Renderiza `sales/checkout.html` com: resumo **read-only** dos itens, total
  (em reais e centavos), `SaleForm` (cliente opcional + observações), seletor de
  **desconto** (% ou R$) e linhas de **pagamento** dinâmicas.
- `checkout.js` recalcula subtotal/desconto/total/pago/troco **ao vivo, só para
  exibição** (parcelas só aparecem no crédito; bloqueia duplo-submit). **O
  backend é autoritativo.**

## 3. Checkout — POST → `create_sale` (processamento atômico)

A view parseia desconto e a lista de pagamentos (listas paralelas do POST,
`_collect_payments`), converte os valores com `_parse_decimal` (aceita vírgula ou
ponto) e delega a **`sign.services.create_sale`**, que roda em
`@transaction.atomic` e valida **tudo antes de qualquer escrita**:

1. **Carrinho vazio** → erro.
2. **Revalida o estoque** item a item contra `Product.quantity` atual (a verdade
   pode ter mudado desde que o item entrou no carrinho).
3. `subtotal_cents = Σ unit_price_cents × quantidade`.
4. **Desconto da venda**: percentual (0–100) → `subtotal × %`; ou valor em reais.
   Valida `0 ≤ desconto ≤ subtotal`. `total_cents = subtotal − desconto`.
5. **Pagamentos**: cada tipo válido e único (constraint no BD reforça);
   parcelas só no crédito (demais normalizados para 1); cada valor > 0. A soma
   deve ser **≥ total** (permite troco) → `change_cents = soma − total`. Sem
   pagamento só quando `total == 0`.
6. **Persiste** (na transação): cria `Sale` → para cada item, `SaleItem` com
   `ProductSnapshot.get_or_create_for` (reusa snapshot idêntico) e **baixa o
   estoque** via `F("quantity") - qtd` → cria os `SalePayment`.

Toda a matemática é em **centavos** com `Decimal`/`ROUND_HALF_UP` (`reais_to_cents`),
**nunca float** — ver [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md).
Qualquer inconsistência levanta `ValidationError` (PT-BR) e **nada é gravado**.

## 4. Sucesso e erro

- **Sucesso**: a view emite `messages.success`, **redireciona** ao comprovante
  (`sales/<pk>/`) e **apaga o cookie do carrinho** (`response.delete_cookie`).
- **Erro**: a view captura o `ValidationError`, transforma cada mensagem em
  `messages.error` e **re-renderiza** o checkout preservando o que o usuário
  digitou (cliente, desconto, pagamentos, obs).

## 5. Comprovante e histórico

- **Comprovante** (`SaleDetailView`, read-only): usa `select_related("client")`
  + `prefetch_related("items__product_snapshot", "payments")`.
- **Histórico** (`SaleListView`): filtros por nome de cliente e período
  (`created_at__date`), paginado.

## Por que a venda é imutável

Os totais ficam **gravados** (não recalculados) e os itens apontam para
**snapshots**, de modo que editar/excluir um produto, ou mudar regras de preço
depois, **não altera vendas passadas**. Não há fluxo de cancelamento/estorno
ainda (ver roadmap em [`../arquitetura/visao-geral.md`](../arquitetura/visao-geral.md)).
Detalhe do padrão snapshot em
[`../arquitetura/modelo-de-dados.md`](../arquitetura/modelo-de-dados.md).
