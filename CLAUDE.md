# CLAUDE.md

## Escopo do Projeto

Aplicação de gestão de negócios (ERP) para controle de estoque, vendas, clientes e fornecedores, além de fornecer relatórios integrados. A aplicação é construída com Django 5.2 e Python 3.13.9 e aplicada em Desktops através do PyWebView e PyInstaller.

## Documentação detalhada (`docs/`)

A documentação está organizada em **três categorias**, cada uma numa pasta.
Índice geral e instruções de manutenção em [`docs/README.md`](docs/README.md).
Consulte e mantenha esses documentos ao alterar as áreas correspondentes.

**Arquitetura** ([`docs/arquitetura/`](docs/arquitetura/)) — como o sistema é construído:
- [`visao-geral.md`](docs/arquitetura/visao-geral.md) — stack, organização em apps, arquitetura em camadas, padrões e roadmap.
- [`camadas.md`](docs/arquitetura/camadas.md) — responsabilidade de cada camada (URLs, views, services, forms, models, carrinho, templates, static) e o que **não** colocar em cada uma.
- [`modelo-de-dados.md`](docs/arquitetura/modelo-de-dados.md) — entidades, relacionamentos, `on_delete`, padrão snapshot, estado derivado, migrações.
- [`convencoes.md`](docs/arquitetura/convencoes.md) — **fonte única** das convenções transversais (idiomas, centavos, máscaras, CRUD, forms, offline/Tailwind/FontAwesome, ambiente).

**Fluxos** ([`docs/fluxos/`](docs/fluxos/)) — como o sistema é usado e processa:
- [`navegacao.md`](docs/fluxos/navegacao.md) — shell de UI (`base.html`), side menu por seção, header, mensagens/toast, mapa de rotas.
- [`venda.md`](docs/fluxos/venda.md) — produto → carrinho (cookie/AJAX) → checkout → `create_sale` (atômico) → comprovante.
- [`despesas.md`](docs/fluxos/despesas.md) — cadastro → geração de parcelas por horizonte → status derivado → pagamento → filtros agregados.
- [`cadastros.md`](docs/fluxos/cadastros.md) — CRUD genérico (listar/criar/detalhar/editar/excluir) e integridade referencial.

**Recursos** ([`docs/recursos/`](docs/recursos/)) — referência detalhada por feature:
- [`produtos.md`](docs/recursos/produtos.md) — Produtos e Fabricantes: models, forms, views, URLs, templates.
- [`carrinho.md`](docs/recursos/carrinho.md) — Carrinho em cookie, fluxo AJAX/fetch + CSRF, validação de estoque, UI e nota sobre PyWebView.
- [`clientes.md`](docs/recursos/clientes.md) — Cadastro de Clientes: model `Client` + `PersonType`, máscaras, seções, filtros.
- [`fornecedores.md`](docs/recursos/fornecedores.md) — Fornecedores + Representantes: models `Supplier`/`Representative`, criação inline vs páginas separadas, máscaras.
- [`vendas.md`](docs/recursos/vendas.md) — Vendas/Checkout: `Sale`/`ProductSnapshot`/`SaleItem`/`SalePayment`, serviço `create_sale`, telas e `checkout.js`.
- [`despesas.md`](docs/recursos/despesas.md) — Despesas: `Expense`/`ExpenseInstallment` (status derivado), `create_expense`/`register_payment`, CRUD + parcelas.
- [`notas-fiscais.md`](docs/recursos/notas-fiscais.md) — NF de Entrada: `InboundInvoice`/`InvoiceDuplicate`/`InvoiceItem`, serviço `create_inbound_invoice`, faturas/produtos inline e páginas separadas.

## Convenções e aprendizados importantes

> Resumo rápido. A referência completa e canônica destas convenções está em
> [`docs/arquitetura/convencoes.md`](docs/arquitetura/convencoes.md).

- **Idiomas**: identificadores de código em inglês; `verbose_name`, labels e textos de UI em **PT-BR**. Os **paths das rotas também são em inglês** (ex.: `products/`, `manufacturers/`).
- **Valores monetários**: armazenados **em centavos como inteiro** (`PositiveIntegerField`, sufixo `_cents`). A UI trabalha em reais; a conversão reais ↔ centavos (com `Decimal`/`ROUND_HALF_UP`) é feita **no backend** (camada de form), nunca em float.
- **Tailwind CSS**: a app roda **offline** (PyWebView/PyInstaller), portanto **sem CDN**. Usa-se o **Tailwind CLI standalone v4** (binário não versionado, no `.gitignore`); sintaxe CSS-based em `sign/static/sign/css/input.css`; o `output.css` é **commitado**. Rebuild após mudar classes nos templates (ver `docs/produtos.md`).
- **Paleta de cores**: tokens customizados via `@theme` no `input.css` (`navy`, `navy-hover`, `canvas`); o azul de destaque/ação é o `blue-600` nativo (compatível com o side menu). **Não use `indigo`** na UI.
- **Ícones**: **FontAwesome Free** instalado **localmente** (offline, sem CDN) em `sign/static/sign/fontawesome/` — assets **commitados**. Use `<i class="fa-solid fa-...">`. Ver `docs/produtos.md`.
- **Templates**: existe um `base.html` reutilizável por app (`sign/templates/sign/base.html`) que os demais estendem — ele provê o shell de **side menu (navy) + header**. Use-o como base para novas telas.
- **Forms**: herde de `StyledModelForm` (`sign/forms.py`) para aplicar a estilização Tailwind automaticamente aos widgets.
- **CRUD**: padrão com Class-Based Views genéricas + `SuccessMessageMixin`; FKs sensíveis usam `on_delete=PROTECT` e as views tratam `ProtectedError`.
- **Ambiente**: o Python do venv fica em `./venv/Scripts/python.exe`; comandos `manage.py` devem usá-lo.
