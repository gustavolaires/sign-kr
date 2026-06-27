# Modelo de dados

Entidades, relacionamentos e as decisões de integridade referencial da app
`sign`. Os models estão todos em `sign/models.py`. Para campos exaustivos de cada
entidade, ver o respectivo doc em [`recursos/`](../recursos/).

## Diagrama de entidades

```
  Manufacturer 1──┐ PROTECT
                  └──* Product *──┐ SET_NULL
                                  └──* ProductSnapshot ◄─┐ PROTECT
                                                         │
  Client 1───┐ PROTECT                                   │
             └──* Sale 1──* SaleItem *────────────────────┘
                   │
                   └──* SalePayment      (UNIQUE: sale + payment_type)

  Expense 1──* ExpenseInstallment        (CASCADE)
```

Legenda: `1──*` = um-para-muitos; a anotação é a `on_delete` da FK (do lado
"muitos" para o "um").

## Entidades por área

### Logística — estoque
- **`Manufacturer`** — fabricante (só `name`, único).
- **`Product`** — produto em estoque. FK `manufacturer` **PROTECT** (não se
  apaga fabricante com produtos). Preço em `unit_price_cents`; `quantity`
  inteira; `unit_type` (`UnitType`).

### Social — clientes
- **`Client`** — pessoa física/jurídica (`PersonType`). Campos de contato e
  endereço opcionais; documentos/telefones gravados **só com dígitos**.

### Comercial — vendas
- **`Sale`** — **documento imutável** da venda. Totais gravados em centavos
  (`subtotal_cents`/`discount_cents`/`change_cents`/`total_cents`), não
  recalculados. FK `client` **PROTECT** e **opcional** (`NULL` = venda avulsa).
- **`ProductSnapshot`** — **réplica reaproveitável** dos dados descritivos do
  produto no momento da venda (ver [Padrão snapshot](#padrão-snapshot)).
- **`SaleItem`** — linha da venda. FK `sale` **CASCADE**, `product_snapshot`
  **PROTECT**. Guarda preço e subtotal no momento da venda.
- **`SalePayment`** — forma de pagamento (`PaymentType`). **UniqueConstraint
  `(sale, payment_type)`** → no máximo um pagamento por tipo por venda.

### Financeiro — despesas
- **`Expense`** — definição da despesa (isolada ou recorrente).
- **`ExpenseInstallment`** — parcela/ocorrência. FK `expense` **CASCADE**.
  Valores em centavos; **`status` é derivado** (não armazenado).

## Estratégia de `on_delete`

A escolha de cada `on_delete` codifica uma regra de negócio:

| Relação | Política | Por quê |
|---|---|---|
| `Product.manufacturer` | **PROTECT** | Não apagar fabricante em uso. |
| `Sale.client` | **PROTECT** | Preservar a quem se vendeu (cliente é opcional, mas se existir, é protegido). |
| `SaleItem.sale` | **CASCADE** | Itens não existem sem a venda. |
| `SaleItem.product_snapshot` | **PROTECT** | O snapshot é o registro histórico — nunca some. |
| `ProductSnapshot.product` | **SET_NULL** | O produto pode ser excluído; o snapshot sobrevive (vira "produto removido"). |
| `ExpenseInstallment.expense` | **CASCADE** | Parcelas não existem sem a despesa. |

## Padrão snapshot (vendas)

`ProductSnapshot` resolve o problema de "a venda precisa lembrar como o produto
era, mesmo que ele mude ou seja excluído depois":

- **Réplica reaproveitável**: armazena nome, descrição, código de barras,
  `manufacturer_name` (**denormalizado** — texto, não FK, senão renomear o
  fabricante alteraria vendas antigas), código do fabricante e `unit_type`.
- **O preço NÃO entra no snapshot** — ele varia por venda e fica em `SaleItem`.
  Isso é o que torna o reaproveitamento eficaz.
- **Dedup por `content_hash`** (`unique`): sha256 de uma serialização canônica
  (JSON com ordem fixa) que **inclui `product_id`**. `get_or_create_for` reusa um
  snapshot idêntico em vez de criar outro; editar o produto gera um novo hash →
  novo snapshot.
- O hash é um **fingerprint de criação**; não é recalculado quando `product` vira
  `NULL` (produto excluído).

Detalhes em [`recursos/vendas.md`](../recursos/vendas.md).

## Estado derivado (despesas)

`ExpenseInstallment.status` **não é uma coluna** — é uma property calculada a
cada leitura, com prioridade: **pago** (pago ≥ devido) > **parcial** (pago > 0) >
**atrasado** (venceu em aberto, comparando com `timezone.localdate()`) >
**pendente**. `status_label` traduz para PT-BR. Consequência: o status sempre
reflete a data atual sem job de atualização. Detalhes em
[`recursos/despesas.md`](../recursos/despesas.md) e
[`fluxos/despesas.md`](../fluxos/despesas.md).

## Convenções de campo

- **Dinheiro**: sempre `PositiveIntegerField` com sufixo `_cents`; property em
  reais para exibição (ver `convencoes.md`).
- **Ordenação default** via `Meta.ordering` (ex.: `Sale`/`Expense` por `-id`;
  `Product`/`Manufacturer`/`Client` por `name`; parcelas por `due_date`).
- **Índices**: `created_at` tem `db_index=True` em `Sale` e `Expense` (uso futuro
  em relatórios).

## Migrações

Histórico em `sign/migrations/`:

| Migração | Conteúdo |
|---|---|
| `0001_initial` | `Manufacturer`, `Product` |
| `0002_alter_product_quantity` | ajuste de `quantity` |
| `0003_client` | `Client` |
| `0004_productsnapshot_sale_saleitem_salepayment` | vendas (4 tabelas) |
| `0005_expense_expenseinstallment` | despesas (pai/filho) |

Gerar/aplicar com o Python do venv (ver `convencoes.md`).
