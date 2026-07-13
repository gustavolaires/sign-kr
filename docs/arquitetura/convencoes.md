# Convenções transversais

Regras que valem para **todo** o código do projeto, independentemente da área.
Esta é a **fonte única** dessas convenções — os docs de recurso e de fluxo
apenas apontam para cá. Leia antes de criar qualquer model, form, view ou tela.

## Idiomas

- **Identificadores de código** (models, campos, funções, variáveis, nomes de
  rota, arquivos) → **inglês**.
- **Textos voltados ao usuário** (`verbose_name`, `label`, `help_text`, mensagens,
  conteúdo de template) → **PT-BR**.
- **Paths das URLs** → **inglês** (ex.: `products/`, `manufacturers/`,
  `expenses/<pk>/edit/`). Só a UI é PT-BR; a rota não.

## Valores monetários — centavos inteiros

Regra central do projeto, motivada por evitar erros de ponto flutuante:

- Todo valor monetário é **persistido em centavos**, como inteiro
  (`PositiveIntegerField`), com o sufixo **`_cents`** no nome do campo
  (ex.: `unit_price_cents`, `total_cents`, `value_cents`).
- A **UI trabalha em reais**: o usuário sempre digita e vê reais.
- A **conversão reais ↔ centavos acontece no backend**, nunca em float:
  - **reais → centavos** (ao gravar): helper `reais_to_cents` em
    `sign/services/money.py` — `Decimal(value) * 100`, arredondado com `ROUND_HALF_UP`.
    A mesma fórmula está em `ProductForm.save`.
  - **centavos → reais** (ao exibir): cada model expõe uma **property somente
    leitura** sem o sufixo (ex.: `Product.unit_price = unit_price_cents / 100`);
    para centavos crus em template, use o filtro `centavos` (ver abaixo).
- **Nunca** faça aritmética monetária em float; some/multiplique sobre centavos
  inteiros e converta só na borda (exibição).

> A camada que **decide** a matemática monetária é o **service** (ou o `save()`
> do form, para conversão simples de 1 campo) — nunca a view nem o template.

### Precificação (multiplicador + arredondamento)

A precificação a partir de um custo usa dois campos de `Company`:
`price_multiplier` (fator) e `rounding_type` (`RoundingType`). A lógica canônica
é **`round_price_cents(cents, rounding_type)`** em `sign/services/invoices.py`: arredonda
o preço **sempre para cima** ao próximo múltiplo do passo do tipo (`cent`=1,
`cent_10`=10, `real`=100, `real_2`=200, `real_5`=500, `real_10`=1000 centavos),
usando `Decimal`/`math.ceil` (nunca float). O preço sugerido de um produto é
`custo × price_multiplier` passado por essa função — hoje consumido pelo
processamento de NF de entrada (ver
[`recursos/notas-fiscais.md`](../recursos/notas-fiscais.md#processamento)).

## Formatação visual (CPF/CNPJ, telefone, CEP)

Mesma filosofia do dinheiro: **o banco guarda só os dígitos**; a máscara é
**apenas visual**, aplicada em três pontos:

- **Ao digitar (front)**: widgets recebem `data-mask` + `inputmode="numeric"`;
  `sign/static/sign/js/masks.js` formata enquanto o usuário digita.
- **Ao gravar (back)**: os `clean_<campo>` do form removem tudo que não é dígito
  (`_only_digits`).
- **Ao exibir**: os filtros de template em `sign/templatetags/sign_format.py`
  (`cpf_cnpj`, `phone`, `cep`) remontam a máscara a partir dos dígitos; se o
  número de dígitos não casa com um formato conhecido, devolvem o valor original.

Não há validação de dígito verificador — apenas máscara. Detalhes em
[`recursos/clientes.md`](../recursos/clientes.md).

## Busca textual — insensível a caixa **e a acentos**

Filtros de listagem por campos de texto (nome de produto/fabricante, cliente na
venda, nome de despesa etc.) **não usam `__icontains` direto**. O SQLite (banco
da app desktop) só dobra maiúsculas de caracteres ASCII, então "joão" não casaria
com "JOÃO" nem "ação" com "AÇÃO".

- **`sign/search.py`** define `filter_unaccent(queryset, field, term)` — normaliza
  o campo (no banco) e o termo (no Python) removendo acentos e passando a
  minúsculas antes de comparar com `__contains`.
- A normalização usa a função SQLite determinística **`unaccent_lower`**,
  registrada em cada conexão por `SignConfig.ready` (`sign/apps.py`); o ORM a
  acessa via a expressão `UnaccentLower`.
- **Ao adicionar um filtro de texto**, use `filter_unaccent(qs, "campo", termo)`
  em vez de `qs.filter(campo__icontains=termo)`. Campos que não são nomes (código
  de barras, código do fabricante) podem seguir com `__icontains`.

## Padrão CRUD

- **Class-Based Views genéricas** (`ListView`, `DetailView`, `CreateView`,
  `UpdateView`, `DeleteView`) para cada entidade.
- Mensagens de sucesso via **`SuccessMessageMixin`** (create/update) e
  `messages.success` manual nas exclusões.
- FKs sensíveis usam **`on_delete=PROTECT`**; as Delete views capturam
  `ProtectedError` e exibem mensagem PT-BR em vez de quebrar (ver
  `ManufacturerDeleteView`).
- Convenção de navegação: ao **salvar uma edição**, `get_success_url()` leva ao
  **detalhe** do objeto; o **create** leva à **listagem**.
- Regras de negócio com escrita multi-tabela ou matemática ficam num **service**
  (`sign/services/`), chamado pela view — não na view nem no model. Ver
  [`camadas.md`](camadas.md).

## Forms

- Herde de **`StyledModelForm`** (`sign/forms.py`): ela aplica as classes Tailwind
  (`INPUT_CLASSES`) a todos os widgets no `__init__` (pulando `CheckboxInput`).
- Forms que **não** são `ModelForm` (ex.: `InstallmentPaymentForm`) aplicam
  `INPUT_CLASSES` manualmente.
- Campos em reais são declarados como `DecimalField` **virtuais** (fora do
  `Meta.fields`) e convertidos para centavos no `save()`/na view.
- **Forms seccionados** (ex.: Clientes, Despesas) agrupam campos em `<section>` com
  um `<h2>` de cabeçalho. O cabeçalho é uma faixa de largura total (alinhada às
  bordas dos campos) com fundo e borda **`navy`** e fonte **branca**:
  `rounded-lg border border-navy bg-navy px-3 py-2 text-sm font-semibold uppercase tracking-wide text-white`.
- **Barra de ações do form** (ex.: `installments/pay.html`, `invoices/process.html`):
  alinhada à **direita** (`flex justify-end gap-3`), com a **ação primária
  primeiro (à esquerda)** e o **Cancelar depois (à direita)**. A ação primária é
  um `<button type="submit">` (`bg-blue-600 ... hover:bg-blue-700`, ou `bg-green-600`
  para "pagar") e o Cancelar é um `<a>` de contorno
  (`border border-gray-300 bg-white ... hover:bg-gray-50`, ícone `fa-xmark`) para o
  detalhe/lista de origem.

## Telas de detalhe

Layout padrão das telas `detail.html` (Produtos, Clientes, Despesas). Replicar ao
criar novas telas de detalhe.

- **Cabeçalho da página**: título (`<h1>`) à esquerda e **apenas** o botão
  **Voltar** à direita (`border border-gray-300 ... hover:bg-gray-50`, ícone
  `fa-arrow-left`). Ações de edição/exclusão **não** ficam aqui.
- **Card de informações** (fundo branco, `rounded-xl border border-gray-200 bg-white
  p-6 shadow-sm`). Dentro dele, na ordem:
  1. **Linha de ações**, alinhada à **direita** e **colada** no primeiro título
     (sem espaçamento): `<div class="flex justify-end gap-3 text-sm">` com
     - **Editar** — `inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 font-medium text-white shadow hover:bg-amber-600` (ícone `fa-pen-to-square`);
     - **Deletar** — igual, mas `bg-red-600 hover:bg-red-700` (ícone `fa-trash`).
  2. As **informações em `<section>`** (cada uma com `<h2>` de cabeçalho —
     `mb-3 text-sm font-semibold uppercase tracking-wide text-gray-700` — e um `dl`
     em grade). Mesmo quando há um só grupo, use uma `<section>` com título
     (ex.: Produtos → **Definição**).
- **Espaçamento**: o card **não** usa `gap-6` (senão empurraria o primeiro título
  para longe dos botões). Em vez disso, as `<section>` ficam num **wrapper**
  `flex flex-col gap-6` — isso preserva o espaço **entre** as seções e mantém os
  botões colados no primeiro título. Com uma única seção, o wrapper é dispensável.
- Dados exibidos em `dl` de grade: `grid grid-cols-1 gap-px overflow-hidden
  rounded-xl border border-gray-200 bg-gray-200 sm:grid-cols-2`, cada item num
  `div.bg-white px-4 py-3` com `dt` (rótulo) + `dd` (valor).

## App offline — Tailwind, paleta e ícones

O app é empacotado para **desktop offline** (PyWebView/PyInstaller — ver
[`visao-geral.md`](visao-geral.md)), portanto **nada de CDN**: todo CSS, JS e
fonte é servido localmente e versionado quando necessário.

### Tailwind CSS (build)

- Usa-se o **Tailwind CLI standalone v4** (binário, sem Node/npm). O binário
  `tailwindcss.exe` fica na raiz e **não é versionado** (está no `.gitignore`).
- Sintaxe **v4 CSS-based** (sem `tailwind.config.js`): o arquivo de entrada
  `sign/static/sign/css/input.css` usa `@import "tailwindcss";` +
  `@source "../../../templates/**/*.html";`.
- O **`output.css` é commitado** (para o app empacotado funcionar offline).
- **Rebuild sempre que classes mudarem nos templates**:
  ```
  ./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify
  ```
  Adicione `--watch` durante o desenvolvimento.

### Paleta de cores (tokens `@theme`)

Cores customizadas definidas via `@theme` no `input.css`:

| Token | Valor | Uso |
|---|---|---|
| `navy` | `#1b2a4e` | fundo do side menu; fundo/borda dos cabeçalhos de seção nos forms |
| `navy-hover` | `#25365e` | hover dos itens do menu |
| `canvas` | `#eef1f6` | fundo da área de conteúdo (`<body>`) |
| `header` | `#4b5769` | fundo da barra de header (cinza escuro dessaturado, derivado do `navy`) |
| `header-hover` | `#59657a` | hover dos botões (toggle, carrinho, config) no header |

O azul de **destaque/ação** (item ativo do menu, botões primários, link "Ver") é
o **`blue-600`** nativo do Tailwind. **Não use `indigo`** na UI.

Cores semânticas dos botões de ação (nativas do Tailwind): **Editar** → `amber-500`
(hover `amber-600`); **Deletar/excluir** → `red-600` (hover `red-700`); **primário/
confirmar** → `blue-600` (hover `blue-700`).

### Ícones — FontAwesome Free (local)

- Assets em **`sign/static/sign/fontawesome/`** (`css/all.min.css` + `webfonts/`),
  **commitados**. Versão **6.7.2**.
- Linkado no `base.html` **antes** do `output.css`.
- Uso: `<i class="fa-solid fa-NOME"></i>` (estilo **solid**; exceção: `fa-brands
  fa-whatsapp`). Para atualizar, baixe o pacote "web" do FontAwesome Free e copie
  `css/all.min.css` + `webfonts/`.

## Ambiente e comandos

- O Python do venv fica em **`./venv/Scripts/python.exe`**; todo comando
  `manage.py` deve usá-lo.
- Verificação rápida padrão:
  ```
  ./venv/Scripts/python.exe manage.py makemigrations
  ./venv/Scripts/python.exe manage.py migrate
  ./venv/Scripts/python.exe manage.py check
  ./venv/Scripts/python.exe manage.py runserver
  ```
