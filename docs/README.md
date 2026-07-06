# Documentação do SIGN-KR

Documentação do **Sistema Integrado de Gestão de Negócios — Kasa dos Reparos**
(ERP desktop em Django 5.2 / Python 3.13, empacotado offline com PyWebView/
PyInstaller). Está organizada em **três categorias**, cada uma numa pasta:

| Pasta | Responde à pergunta | Quando ler |
|---|---|---|
| [`arquitetura/`](arquitetura/) | *Como o sistema é construído?* | Antes de mexer em estrutura, camadas, dados ou convenções globais. |
| [`fluxos/`](fluxos/) | *Como o sistema é usado e como processa?* | Para entender um percurso de ponta a ponta (venda, despesa, cadastro). |
| [`recursos/`](recursos/) | *Como esta feature funciona em detalhe?* | Antes de alterar os models/forms/views/templates de uma área. |

> **Convenções globais** (dinheiro em centavos, idiomas, build offline do
> Tailwind, padrão CRUD) ficam em
> [`arquitetura/convencoes.md`](arquitetura/convencoes.md) — fonte única. Os
> demais docs apontam para lá.

## Arquitetura

- [`visao-geral.md`](arquitetura/visao-geral.md) — stack, organização em apps,
  arquitetura em camadas, padrões notáveis, estado atual e roadmap.
- [`camadas.md`](arquitetura/camadas.md) — responsabilidade de cada camada
  (URLs, views, services, forms, models, carrinho, templates, static) e o que
  **não** colocar em cada uma.
- [`modelo-de-dados.md`](arquitetura/modelo-de-dados.md) — entidades,
  relacionamentos, estratégia de `on_delete`, padrão snapshot, estado derivado,
  migrações.
- [`convencoes.md`](arquitetura/convencoes.md) — regras transversais (idiomas,
  centavos, máscaras, CRUD, forms, offline/Tailwind/FontAwesome, ambiente).

## Fluxos

- [`navegacao.md`](fluxos/navegacao.md) — shell de UI (`base.html`), side menu
  por seção, header, mensagens/toast, mapa de rotas.
- [`venda.md`](fluxos/venda.md) — produto → carrinho (cookie/AJAX) → checkout →
  `create_sale` (atômico) → comprovante.
- [`despesas.md`](fluxos/despesas.md) — cadastro → geração de parcelas por
  horizonte → status derivado → registro de pagamento → filtros agregados.
- [`cadastros.md`](fluxos/cadastros.md) — CRUD genérico (listar/criar/detalhar/
  editar/excluir) e integridade referencial.

## Recursos (referência por feature)

- [`produtos.md`](recursos/produtos.md) — Produtos e Fabricantes.
- [`carrinho.md`](recursos/carrinho.md) — Carrinho em cookie + AJAX.
- [`clientes.md`](recursos/clientes.md) — Cadastro de Clientes (máscaras, seções).
- [`fornecedores.md`](recursos/fornecedores.md) — Fornecedores + Representantes.
- [`vendas.md`](recursos/vendas.md) — Vendas/Checkout (snapshot, pagamentos).
- [`despesas.md`](recursos/despesas.md) — Despesas/contas a pagar.

## Como manter

Ao alterar uma área, atualize **os três níveis quando fizer sentido**: o recurso
(detalhe), o fluxo (se o percurso mudou) e a arquitetura (se mudou uma camada,
relação de dados ou convenção). Mantenha as convenções globais em
`arquitetura/convencoes.md`, sem duplicá-las nos outros arquivos.
