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
    `sign/services.py` — `Decimal(value) * 100`, arredondado com `ROUND_HALF_UP`.
    A mesma fórmula está em `ProductForm.save`.
  - **centavos → reais** (ao exibir): cada model expõe uma **property somente
    leitura** sem o sufixo (ex.: `Product.unit_price = unit_price_cents / 100`);
    para centavos crus em template, use o filtro `centavos` (ver abaixo).
- **Nunca** faça aritmética monetária em float; some/multiplique sobre centavos
  inteiros e converta só na borda (exibição).

> A camada que **decide** a matemática monetária é o **service** (ou o `save()`
> do form, para conversão simples de 1 campo) — nunca a view nem o template.

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
  (`sign/services.py`), chamado pela view — não na view nem no model. Ver
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

O azul de **destaque/ação** (item ativo do menu, botões primários, link "Ver") é
o **`blue-600`** nativo do Tailwind. **Não use `indigo`** na UI.

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
