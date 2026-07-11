# Visão geral da arquitetura

SIGN-KR (Sistema Integrado de Gestão de Negócios — Kasa dos Reparos) é um **ERP
de pequeno porte** para controle de estoque, vendas, clientes, fornecedores e
contas a pagar, com relatórios integrados. Este documento descreve o **formato
do sistema** como um todo; as outras páginas de `arquitetura/` detalham camadas,
modelo de dados e convenções.

## Stack

| Item | Escolha |
|---|---|
| Linguagem | Python 3.13.9 |
| Framework | Django 5.2 |
| Banco | SQLite (arquivo `db.sqlite3` na raiz) |
| Frontend | Templates Django + Tailwind CSS v4 (build offline) + JS vanilla |
| Ícones | FontAwesome Free 6.7.2 (local) |
| Empacotamento alvo | **Desktop** via PyWebView + PyInstaller |

> **Desktop offline é a restrição que molda o projeto.** Como o app roda numa
> janela PyWebView (sem internet garantida), **não há CDN**: CSS, JS e fontes são
> servidos localmente. O app já abre em **janela nativa** via `python app.py`
> (PyWebView + waitress + WhiteNoise); o empacotamento final em `.exe` com
> PyInstaller é o próximo alvo (ver [Estado atual](#estado-atual-e-roadmap)).

## Organização em apps

Projeto Django padrão com **dois pacotes**:

```
sign-kr/
├── core/                 # projeto Django (configuração, não tem regra de negócio)
│   ├── settings.py       # apps, middleware, templates, banco
│   ├── urls.py           # inclui sign.urls na raiz; admin em /admin/
│   ├── wsgi.py / asgi.py
├── sign/                 # ÚNICA app de domínio — todo o negócio vive aqui
│   ├── models.py         # todas as entidades
│   ├── services/         # pacote de regras de negócio, um módulo por domínio
│   ├── forms.py          # forms + estilização + conversões reais↔centavos
│   ├── cart.py           # carrinho em cookie (sem banco)
│   ├── views/            # pacote de views, uma por área
│   ├── urls.py           # rotas (namespace "sign")
│   ├── context_processors.py  # cart_count global nos templates
│   ├── templatetags/sign_format.py  # filtros de máscara/centavos
│   ├── admin.py          # Django admin (operação/depuração)
│   ├── templates/sign/   # base.html + subpasta por área
│   ├── static/sign/      # css (input/output), js, fontawesome
│   └── migrations/
├── docs/                 # esta documentação
├── manage.py
└── tailwindcss.exe       # CLI standalone (não versionado)
```

Toda a lógica de domínio está concentrada na app **`sign`**. `core` só tem
configuração. Não há divisão em múltiplas apps por área (produtos, vendas, etc.);
a separação é feita **por arquivo/módulo** dentro de `sign` (ver
[`camadas.md`](camadas.md)).

## Arquitetura em camadas

O fluxo de uma requisição atravessa camadas com responsabilidades bem definidas:

```
  Navegador / PyWebView
        │  HTTP (form POST, ou fetch/AJAX no carrinho)
        ▼
  core/urls.py ──► sign/urls.py        (roteamento, namespace "sign")
        ▼
  sign/views/*.py                      (orquestra: lê request, chama form/service, responde)
        │              │
        │              ▼
        │        sign/forms.py         (valida entrada, estiliza widgets, converte 1 campo)
        ▼              ▼
  sign/services/*.py                   (REGRAS DE NEGÓCIO: matemática, transações atômicas)
        ▼
  sign/models.py  ◄──► db.sqlite3      (persistência; properties de exibição; status derivado)
        ▲
        │ contexto
  sign/templates/sign/*.html           (apresentação; estende base.html)
  sign/static/sign/{css,js}            (Tailwind output.css + JS vanilla)
```

**Regra de ouro de onde colocar o quê:**

- **View** — orquestração fina: parse do request, decide o template/redirect,
  trata `ValidationError`/`ProtectedError`, emite `messages`. Não contém
  matemática monetária nem escrita multi-tabela.
- **Service** (`services/`) — toda regra de negócio com **transação atômica**,
  **matemática em centavos** ou **escrita em várias tabelas** (ex.: `create_sale`,
  `create_expense`). Levanta `ValidationError` (PT-BR); a view captura.
- **Form** — validação de entrada e conversão simples de um campo (reais→centavos
  no `save()`).
- **Model** — estrutura de dados, properties de **exibição** (centavos→reais) e
  **estado derivado** (ex.: `ExpenseInstallment.status`).
- **Template/JS** — só apresentação. O JS (carrinho, checkout) é **vanilla**, faz
  cálculo ao vivo apenas para exibição; **o backend é sempre autoritativo**.

Ver [`camadas.md`](camadas.md) para o detalhamento de cada camada e
[`convencoes.md`](convencoes.md) para as regras transversais (dinheiro, idiomas,
offline, CRUD).

## Áreas funcionais

A app `sign` cobre cinco áreas, agrupadas no menu por seção:

| Seção (menu) | Área | Recurso | Fluxo |
|---|---|---|---|
| Logística | Produtos e Fabricantes | [produtos](../recursos/produtos.md) | [cadastros](../fluxos/cadastros.md) |
| Comercial | Carrinho + Vendas/Checkout | [carrinho](../recursos/carrinho.md), [vendas](../recursos/vendas.md) | [venda](../fluxos/venda.md) |
| Financeiro | Despesas (contas a pagar) | [despesas](../recursos/despesas.md) | [despesas](../fluxos/despesas.md) |
| Social | Clientes | [clientes](../recursos/clientes.md) | [cadastros](../fluxos/cadastros.md) |

## Padrões arquiteturais notáveis

- **Service layer** para regras de negócio críticas, com `@transaction.atomic`
  (vendas e despesas) — nada é gravado se uma validação falhar.
- **Snapshot imutável** nas vendas: `ProductSnapshot` replica os dados do produto
  no momento da venda (com dedup por hash), de modo que editar/excluir o produto
  não altera o histórico. Ver [`modelo-de-dados.md`](modelo-de-dados.md).
- **Estado derivado, não armazenado**: o `status` de uma parcela de despesa é
  calculado on-the-fly a partir de valor pago × vencimento.
- **Carrinho sem banco**: vive num cookie JSON, manipulado por AJAX. O servidor
  só lê para renderizar; a fonte de verdade da quantidade é o cookie, mas o
  **estoque** é revalidado no backend a cada operação e no checkout.
- **Centavos em toda parte** + conversão só na borda (ver `convencoes.md`).

## Estado atual e roadmap

- **Hoje**:
  - Abre como **app desktop** via `python app.py` — o launcher na raiz sobe o
    Django atrás do **waitress** (WSGI) numa thread local em `127.0.0.1` (porta
    livre) e aponta a janela **PyWebView** (maximizada) para ela. Os estáticos são
    servidos pelo **WhiteNoise** a partir do `STATIC_ROOT` (`collectstatic`),
    então funciona com **`DEBUG=False`** e offline. O webview usa **perfil
    persistente** (`private_mode=False, storage_path=...`) para o cookie do
    carrinho sobreviver entre execuções (ver
    [`recursos/carrinho.md`](../recursos/carrinho.md)). O `app.py` roda
    `migrate` (e `collectstatic` na 1ª execução) automaticamente no startup.
  - `DEBUG` é controlado pela env var `DJANGO_DEBUG` (default `False`; use
    `DJANGO_DEBUG=1` com `runserver` para páginas de erro no desenvolvimento).
  - SQLite; sem autenticação de usuário na UI (só o admin do Django existe).
    `TIME_ZONE=UTC`, `USE_TZ=True`.
- **Planejado / deixado para depois**:
  - Empacotamento final em `.exe` com **PyInstaller** (o launcher `app.py` e o
    serving offline já estão prontos para isso).
  - **Status/estorno** de venda (não há fluxo de cancelamento ainda).
  - **Descontos por item** (promoções) — campos já existem em `SaleItem`, sem UI.
  - **Relatórios** integrados.
