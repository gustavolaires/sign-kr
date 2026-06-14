# CLAUDE.md

## Escopo do Projeto

Aplicação de gestão de negócios (ERP) para controle de estoque, vendas, clientes e fornecedores, além de fornecer relatórios integrados. A aplicação é construída com Django 5.2 e Python 3.13.9 e aplicada em Desktops através do PyWebView e PyInstaller.

## Documentação detalhada (`docs/`)

Observações específicas de recursos e fluxos ficam na pasta [`docs/`](docs/).
Consulte e mantenha esses documentos ao alterar as áreas correspondentes:

- [`docs/produtos.md`](docs/produtos.md) — Gestão de Produtos e Fabricantes (app `sign`): models, forms, views, URLs, templates e build do Tailwind.
- [`docs/carrinho.md`](docs/carrinho.md) — Carrinho de compras (app `sign`): armazenamento em cookie, fluxo AJAX/fetch + CSRF, validação de estoque no backend, UI (modal, badge, tela do carrinho) e nota sobre persistência no PyWebView.
- [`docs/clientes.md`](docs/clientes.md) — Cadastro de Clientes (app `sign`): model `Client` + `PersonType`, campos obrigatórios/opcionais, form, views, URLs, templates e item de menu (Social).

## Convenções e aprendizados importantes

- **Idiomas**: identificadores de código em inglês; `verbose_name`, labels e textos de UI em **PT-BR**. Os **paths das rotas também são em inglês** (ex.: `products/`, `manufacturers/`).
- **Valores monetários**: armazenados **em centavos como inteiro** (`PositiveIntegerField`, sufixo `_cents`). A UI trabalha em reais; a conversão reais ↔ centavos (com `Decimal`/`ROUND_HALF_UP`) é feita **no backend** (camada de form), nunca em float.
- **Tailwind CSS**: a app roda **offline** (PyWebView/PyInstaller), portanto **sem CDN**. Usa-se o **Tailwind CLI standalone v4** (binário não versionado, no `.gitignore`); sintaxe CSS-based em `sign/static/sign/css/input.css`; o `output.css` é **commitado**. Rebuild após mudar classes nos templates (ver `docs/produtos.md`).
- **Paleta de cores**: tokens customizados via `@theme` no `input.css` (`navy`, `navy-hover`, `canvas`); o azul de destaque/ação é o `blue-600` nativo (compatível com o side menu). **Não use `indigo`** na UI.
- **Ícones**: **FontAwesome Free** instalado **localmente** (offline, sem CDN) em `sign/static/sign/fontawesome/` — assets **commitados**. Use `<i class="fa-solid fa-...">`. Ver `docs/produtos.md`.
- **Templates**: existe um `base.html` reutilizável por app (`sign/templates/sign/base.html`) que os demais estendem — ele provê o shell de **side menu (navy) + header**. Use-o como base para novas telas.
- **Forms**: herde de `StyledModelForm` (`sign/forms.py`) para aplicar a estilização Tailwind automaticamente aos widgets.
- **CRUD**: padrão com Class-Based Views genéricas + `SuccessMessageMixin`; FKs sensíveis usam `on_delete=PROTECT` e as views tratam `ProtectedError`.
- **Ambiente**: o Python do venv fica em `./venv/Scripts/python.exe`; comandos `manage.py` devem usá-lo.
