# Dashboard (app `sign`)

Página de indicadores consolidados (Vendas, Produtos, Despesas). Toda a
matemática fica no serviço `dashboard_metrics`; a view apenas injeta o resultado
no contexto e o template desenha KPIs + gráficos (Chart.js). Leia antes de
alterar os indicadores ou adicionar gráficos. Valores em centavos conforme
[`../arquitetura/convencoes.md`](../arquitetura/convencoes.md).

## Configuração (campos em `Company`)

A dashboard depende de campos do singleton `Company` (`sign/models.py`), editáveis
na tela de **Configurações** (seção *Operação e precificação*):

- `daily_sales_goal_cents` — meta de venda diária (centavos; property `daily_sales_goal`
  em reais). No `CompanyForm` é um `DecimalField` **virtual** (`daily_sales_goal`, em R$),
  convertido com `reais_to_cents` no `save()`.
- `operating_days_per_week` — dias de operação na semana (select 0–7).
- `low_stock_threshold` — valor **default** do estoque mínimo (`min_stock`) de novos
  produtos (inteiro). A dashboard **não** usa mais este campo: o "estoque baixo" é
  calculado pelo `min_stock` de cada produto.
- `price_multiplier` (`FloatField`) e `rounding_type` (`RoundingType` TextChoices:
  Centavo / Centavo múltiplo de 10 / Real / Real múltiplo de 2/5/10) — **não** usados
  pela dashboard; são preparação para a precificação (feature futura).

## Serviço (`sign/services.py`)

`dashboard_metrics(*, company=None, today=None)` — sem escrita no banco. `company`/
`today` são **injetáveis** (testes); por padrão usam `Company.get_solo()` e
`timezone.localdate()`. Retorna um dict com `sales`, `units`, `products`, `expenses`,
`goals` e `chart_data` (este último serializado para o JS).

Regras não óbvias:

- **Janelas de data**: semana = **segunda a domingo** (`today - weekday()` … +6);
  mês via `calendar.monthrange`. `Sale.created_at` é `DateTimeField` → filtra-se por
  `created_at__date` (e `TruncDate` para o agrupamento por dia), respeitando
  `timezone.localdate()`.
- **Vendas**: por período (hoje/semana/mês/geral) contam-se `Count("id")` e soma-se
  `Sum("total_cents")`. Produtos vendidos = `Sum(SaleItem.quantity)` nos mesmos períodos.
- **Faturamento por dia**: duas séries com `TruncDate`, preenchendo dias sem venda
  com 0 — `weekly` (7 dias, Seg→Dom) e `monthly` (todos os dias do mês, rótulos
  `"1".."31"`). Ambas expostas em `chart_data` com `labels`/`revenue`/`daily_goal`.
- **Metas**: semanal = `operating_days_per_week * daily_goal`; mensal =
  `max(0, dias_mês - (dias_mês % 7) * (7 - operating_days_per_week)) * daily_goal`
  (fórmula **aproximada**, assume múltiplos de 7; `max(0, …)` é guarda defensiva).
  `%` atingido tem **guarda para meta 0** (retorna `None` → UI mostra "—").
- **Produtos**: `total` = `count()` (todos os cadastrados); `active` = ativos
  (`is_active=True`) e `active_pct` sobre o total. **Estoque baixo/zerado consideram
  só os ativos** e usam o **`min_stock` de cada produto** (não mais o
  `low_stock_threshold` da empresa — que virou só o default de cadastro): baixo =
  ativos com `quantity__lte=F("min_stock")` (**inclui zerados**); zerado = ativos com
  `quantity=0`. `low_pct`/`zero_pct` são **sobre os ativos** (label "% dos ativos";
  guarda p/ base 0). O doughnut "saúde do estoque" usa **buckets exclusivos** (ok /
  baixo / zerado) que somam o total de **ativos**: `ok = active - low`,
  `low` do doughnut = `low - zero`.
- **Despesas do mês** (`ExpenseInstallment` por `due_date` no mês) — separadas **por
  saldo**: `paid = min(Σpago, Σdevido)`, `unpaid = max(0, Σdevido − Σpago)`, de modo
  que `paid + unpaid = due`. Recorrentes/isoladas via `Q(expense__recurrent=…)`.
  (Status derivado de `ExpenseInstallment` é Python-level; não é usado no ORM aqui.)

## View / rota / menu

- **View** `DashboardView(TemplateView)` (`sign/views/dashboard.py`), exportada em
  `sign/views/__init__.py`. `template_name = "sign/dashboard/index.html"`; o
  `get_context_data` faz `context.update(dashboard_metrics())`.
- **Rota** `sign:dashboard` → `dashboard/` (`sign/urls.py`).
- **Menu**: primeiro item da seção **Análise** do `base.html` (ícone
  `fa-chart-column`, ao lado de **Relatórios**); ativo quando
  `url_name == 'dashboard'`. Ver [`relatorios.md`](relatorios.md).

## Template e gráficos (`sign/templates/sign/dashboard/`)

- `index.html` estende `base.html`: três `<section>` (Vendas/Produtos/Despesas) num
  wrapper `flex flex-col gap-10` (respiro entre grupos), com grades de cartões KPI
  (partials `_sale_card.html` = nº + R$, `_num_card.html`, `_money_card.html`) e
  `<canvas>` para os gráficos. O `_money_card.html` aceita um `col_class` opcional — em
  Despesas o card **"Totais do mês"** usa `sm:col-span-2` (largura total), e os quatro
  demais (Pendentes/Pagas, Recorrentes/Isoladas) alinham em 2×2 abaixo dele.
- Dados dos gráficos passam ao JS via `{{ chart_data|json_script:"dashboard-data" }}`
  (padrão do `checkout.html`).
- **Chart.js v4 (UMD) vendorizado** em `sign/static/sign/js/vendor/chart.umd.min.js`
  (**commitado**, offline — primeira lib JS de terceiros do projeto, segue o precedente
  do FontAwesome). `dashboard.js` instancia: dois combos de faturamento por dia
  (função reutilizável `salesByDayChart`, chamada para `chart-weekly` e
  `chart-monthly` — barras de faturamento + linha tracejada de meta diária, com %
  no tooltip), dois medidores doughnut (meta semanal/mensal, `cutout:'75%'`, %
  renderizado em **HTML** no centro — sem plugin datalabels) e dois doughnuts
  (saúde do estoque; situação das despesas).
- **Layout da seção Vendas** (grade `lg:grid-cols-2`, 2×2): linha 1 = "Vendas da
  semana por dia" + "Meta semanal"; linha 2 = "Vendas do mês por dia" + "Meta mensal".
- **Paleta triádica pop-art** (azul/amarelo/vermelho; definida no topo do `dashboard.js`):
  azul `#155AF0` (Ok / Pagas / faturamento / atingido), amarelo-ouro `#F6B717`
  (estoque baixo / pendentes / linha de meta), vermelho `#E42D28` (estoque zerado),
  `gray-200` `#e5e7eb` (trilho dos medidores); arcos com anel branco de 2px.

## Build / migrações

- Migração: `0012_company_daily_sales_goal_cents_and_more`.
- Rebuild Tailwind após mexer em classes:
  `./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify`.

## Testes (`sign/tests.py`)

`DashboardMetrics*Tests` cobrem `dashboard_metrics`: fórmulas de meta (incl. poucos
dias de operação), janela de data (venda de hoje 23h não vaza), despesas por saldo
(invariante pagas+não pagas=a pagar), buckets de estoque e guardas de zero.

## Verificação rápida

1. `./venv/Scripts/python.exe manage.py migrate && manage.py check && manage.py test sign`.
2. **Configurações** → preencher Meta diária (R$), Dias de operação, Estoque baixo →
   salvar e reabrir (meta reexibida em reais).
3. Menu → **Dashboard**: KPIs de vendas (nº + R$) e produtos vendidos conferem; combo
   semanal com linha de meta; medidores com % coerente; doughnuts de estoque e despesas
   somando o total. Confirmar que o Chart.js local carrega sem rede.
