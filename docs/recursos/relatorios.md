# Relatórios (app `sign`)

Geração de **relatórios imprimíveis em A4** — listas cruas dos dados para análise
offline e conferência em papel. Complementa a [Dashboard](dashboard.md) (que
consolida indicadores em gráficos). Toda a consulta/agregação fica na camada de
serviço; as views são finas. Valores em centavos conforme
[`../arquitetura/convencoes.md`](../arquitetura/convencoes.md).

## Visão geral do fluxo

1. **Tela de configuração** (`reports/`, `report_index`): estende `base.html`.
   Um `<select name="type">` lista os relatórios; ao trocar, um `<script>` inline
   mostra/oculta os blocos de **filtro** (período / corte) e o bloco de **colunas**
   do relatório escolhido, pré-preenchendo as datas com o default daquele relatório.
2. **Tela de impressão** (`reports/render/`, `report_render`): template
   **standalone** `sign/reports/report.html` (**não** estende `base.html`; CSS
   embutido, no molde de [`sales/receipt.html`](vendas.md#comprovante-não-fiscal)).
   Renderiza a tabela + cabeçalho (empresa, título, período, data de geração) e
   uma **toolbar** (só na tela) com **Imprimir** (`window.print()`), toggle
   **Retrato/Paisagem** (`?orientation=`) e **Voltar**. O `<form>` da configuração
   tem `target="_blank"`, então o relatório abre em nova aba.

## Serviço (`sign/services.py`)

- **`REPORT_SPECS`** — lista ordenada que descreve cada relatório para a UI e para
  o builder: `key`, `label` (PT-BR), `period` (janela default: `prev_month` /
  `current_month` / `last_12_months` / `None`), `cutoff` (`units` / `money` /
  `False`), `fixed_columns` e `optional_columns`. Cada coluna é um dict
  `{key, label, type, default}` criado por `_report_col`, com `type ∈ {text, int,
  money, date, bool, cpf_cnpj, phone}` (guia a formatação no template).
- **`build_report(*, report_type, params, today=None)`** — dispatcher. Valida o
  tipo (`ValidationError` PT-BR se desconhecido), resolve período/colunas, chama o
  helper específico e devolve o **contexto normalizado**:
  `{title, period_label, meta_label, columns, rows}`. `rows` é uma **lista de
  linhas**, cada linha uma **lista de células `{type, value}` alinhadas a
  `columns`** — o template renderiza genericamente, sem lookup dinâmico por chave.
  Dinheiro em `value` vem em **reais** (`_cents_to_reais`); datas como `date`.
  `params` aceita `QueryDict` (do request) **ou** `dict` simples (testes), via os
  helpers `_param`/`_param_list`.
- **Colunas** (`_resolve_columns`): `fixed_columns` + as opcionais escolhidas
  (`col` no GET, `getlist`); se nenhuma marcada, usa as `default`. Na tela de
  configuração, os checkboxes de blocos ocultos são **desabilitados** por JS para
  não vazarem no GET (chaves colidem entre relatórios).
- **Janela de data** (`_resolve_period` + `_prev_month_range` /
  `_current_month_range` / `_last_12_months_range`, todos com `calendar.monthrange`):
  quando `date_from`/`date_to` vêm vazios, aplica o default do relatório. O período
  efetivamente usado é impresso no cabeçalho.
- **Helpers por relatório**: `_report_products`, `_report_best_products`,
  `_report_sales`, `_report_sales_by_day`, `_report_sales_by_month`,
  `_report_best_clients`, `_report_expenses(mode)`. Reusam as agregações do
  `dashboard_metrics` (`Sum`/`Count`/`Q(filter=…)`/`TruncDate`/`TruncMonth`/`F`) e
  `reais_to_cents`/`_parse_reais` para o corte em reais.

## Catálogo de relatórios

| `type` | Filtros | Conteúdo | Notas |
|---|---|---|---|
| `products` | — | Colunas personalizáveis (default: cód. barras, cód. fabricante, nome, fabricante, quantidade, preço). Opcionais: descrição, tipo unidade, estoque mín., ativo. | Todos os produtos, ordem alfabética. |
| `best_products` | corte (TOP N / mín. unidades) + período (ou "todas as vendas") | Fixa: **unidades vendidas**; + colunas de produto personalizáveis. | Rankeia por Σ `SaleItem.quantity`; exibe alfabético. Vendas de produtos **excluídos** (snapshot sem `product`) não entram. |
| `sales` | período (default: mês anterior) | Personalizável (default: nº, data, cliente, forma(s) de pagamento, subtotal, desconto, total, troco). Opcional: observações. | `Sale` no período, ordem `-created_at`. Formas de pagamento = `get_payment_type_display()` juntadas. |
| `sales_by_day` | período (default: mês anterior) | Fixa: dia, valor total. | Só dias **com** venda (`TruncDate`). |
| `sales_by_month` | período (default: últimos 12 meses) | Fixa: mês (mm/aaaa), valor total. | `TruncMonth`; meses sem venda preenchidos com 0. |
| `best_clients` | corte (TOP N / valor mín. em R$) + período (ou "todas as vendas") | Fixa: **total comprado**; personalizável (default: nome, CPF/CNPJ, prestador de serviço, e-mail, telefone principal). Opcional: tipo de pessoa. | Σ `Sale.total_cents` por cliente; ignora venda avulsa; exibe alfabético. |
| `expenses` | período (default: mês atual) | Fixa: despesa, tipo, parcela, total parcelas, vencimento, valor, valor pago, data pagamento. | Parcelas com `due_date` no período. |
| `expenses_open` | período (default: mês atual) | Fixa: despesa, tipo, parcela, total, vencimento, valor. | Parcelas em aberto (`paid_value_cents < value_cents`). |
| `expenses_paid` | período (default: mês atual) | Fixa: despesa, tipo, parcela, total, vencimento, valor, valor pago, data pagamento. | Parcelas quitadas (`value_cents > 0` e `paid_value_cents >= value_cents`). |

> **"Tipo da despesa"** = mapeamento do booleano `Expense.recurrent` para
> **"Recorrente" / "Isolada"** (o model não tem campo de categoria). A situação
> aberta/paga é replicada **no ORM** (não a property Python `status`), com o mesmo
> critério do `open_q` em `sign/views/expenses.py`.

## Views (`sign/views/reports.py`) e URLs (`sign/urls.py`)

Function-based (reexportadas em `sign/views/__init__.py`). Ambos os `name` contêm
`report` (realce do menu via `'report' in url_name`).

| Nome de rota | Path | View |
|---|---|---|
| `report_index` | `reports/` | `report_index` (config: `REPORT_SPECS` + defaults de data p/ o JS) |
| `report_render` | `reports/render/` | `report_render` (chama `build_report`; erro → `messages.error` + redirect a `report_index`) |

## Templates (`sign/templates/sign/reports/`)

- `index.html` (estende `base.html`): `<select>` + blocos `#filter-period`,
  `#filter-cutoff` e `.columns-block` (um por relatório personalizável), com
  `json_script` (`report-meta`, `period-defaults`) alimentando o `<script>` que
  alterna visibilidade/`disabled`.
- `report.html` (standalone): `@page { size: A4 <orientation> }`,
  `@media print` oculta a `.toolbar`. Renderização **genérica** — `<thead>` itera
  `columns`; `<tbody>` itera `rows` formatando cada célula por `cell.type`
  (`money` → `R$ …|floatformat:2`; `date` → `d/m/Y`; `bool` → Sim/Não;
  `cpf_cnpj`/`phone` → filtros de `sign_format`). Colunas `money`/`int` alinhadas à
  direita. Dados da empresa via context processor `company`.

## Menu

Novo subgrupo **Análise** no topo do `base.html` (`sign/templates/sign/base.html`),
agrupando **Dashboard** (`fa-chart-column`) e **Relatórios** (`fa-file-lines`,
ativo quando `'report' in url_name`). Antes, Dashboard era um item solto.

## Build

- Rebuild do Tailwind após mexer nas classes da tela de **configuração**
  (a de impressão tem CSS próprio):
  `./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify`.
- **Sem migração** — não há novos models.

## Testes (`sign/tests.py`)

Classes `Report*Tests` (estilo `DashboardMetrics*Tests`, `today` injetado): ordem
alfabética + colunas custom (Produtos); ranking por unidades / corte / "todas as
vendas" (mais vendidos); janela de data + lista de pagamentos (Vendas); só dias com
venda / preenche zeros por mês; Σ por cliente ignorando avulsa + corte por valor
(melhores clientes); aberto/pago no ORM + mapa Recorrente/Isolada (despesas); tipo
inválido levanta `ValidationError`; rótulo de período default.

## Verificação rápida

1. `./venv/Scripts/python.exe manage.py test sign` e `manage.py check`.
2. Rebuild Tailwind (acima) e `manage.py runserver`.
3. Menu **Análise → Relatórios**: para cada tipo, conferir que só os filtros/colunas
   daquele relatório aparecem, **Gerar** (abre nova aba) → validar título, período,
   colunas escolhidas, valores em R$ e datas `d/m/aaaa`, o toggle Retrato/Paisagem e
   o botão **Imprimir** (diálogo nativo → A4).
