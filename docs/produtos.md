# Gestão de Produtos e Fabricantes (app `sign`)

Feature de CRUD completo para **Produtos** e **Fabricantes**, com interface em
Tailwind CSS. Esta documentação registra os fluxos, decisões e comportamentos
não óbvios — leia antes de alterar models, forms ou templates desta área.

## Models (`sign/models.py`)

| Model | Campos principais | Observações |
|---|---|---|
| `Manufacturer` | `name` (único) | Entidade separada; por enquanto só o nome. |
| `Product` | `name`, `description`, `barcode`, `manufacturer` (FK), `manufacturer_code`, `quantity`, `unit_type`, `unit_price_cents` | Ver detalhes abaixo. |
| `UnitType` | `TextChoices` | unid, pct, kg, g, mg, km, m, cm, mm, l, ml. |

### Preço — armazenado em centavos
- O preço é persistido em **`unit_price_cents`** (`PositiveIntegerField`), **sempre como inteiro em centavos** (ex.: R$ 12,34 → `1234`). Isso evita erros de aritmética de ponto flutuante.
- O model expõe a property **`unit_price`** (somente leitura) = `unit_price_cents / 100`, usada apenas para exibição em templates/admin.
- **Nunca** faça cálculos monetários em float; opere sobre centavos inteiros.

### Quantidade
- `quantity` é `DecimalField(max_digits=12, decimal_places=3)` para suportar unidades fracionadas (kg, g, l, etc.).

### Fabricante protegido
- `Product.manufacturer` usa `on_delete=models.PROTECT`. Excluir um fabricante com produtos vinculados levanta `ProtectedError` (tratado na view).

## Forms (`sign/forms.py`)

- `StyledModelForm` é a base que aplica as classes Tailwind (`INPUT_CLASSES`) a todos os widgets automaticamente no `__init__`. Novos forms desta área devem herdar dela.
- **`ProductForm` — conversão reais ↔ centavos (regra central):**
  - O form **não** expõe `unit_price_cents`. Em vez disso declara um campo virtual **`unit_price`** (`DecimalField`, 2 casas, label "Preço unitário (R$)") — o usuário sempre digita/vê **reais**.
  - `__init__`: ao editar, preenche `unit_price.initial` a partir de `unit_price_cents / 100`.
  - `save()`: converte reais → centavos com `Decimal` e `ROUND_HALF_UP` antes de gravar em `unit_price_cents`.
  - Toda conversão fica no backend; a UI só conhece reais.
- **Campo Quantidade**: widget `NumberInput(attrs={"step": "any"})`. Com `step="any"` as setas do input incrementam de **1 em 1** e ainda aceitam decimais. Não use `step="1"` (rejeitaria valores como 1,5 na validação HTML).

## Views (`sign/views.py`)

- Class-Based Views genéricas (`ListView`, `DetailView`, `CreateView`, `UpdateView`, `DeleteView`) para Produto e Fabricante.
- Mensagens de sucesso via `SuccessMessageMixin` (create/update) e `messages.success` manual nas exclusões.
- `ManufacturerDeleteView` captura `ProtectedError` e exibe mensagem de erro em vez de quebrar, redirecionando para a listagem.
- `ProductListView` usa `select_related("manufacturer")` para evitar N+1.
- **Redirecionamentos de Produto (navegação):**
  - `ProductUpdateView` define `get_success_url()` → ao **salvar** uma edição, vai para os **detalhes** (`sign:product_detail`), não para a listagem. (Create continua indo para a listagem.)
  - Nos templates de Produto, os botões "Cancelar" de **edição** (quando `form.instance.pk`) e de **exclusão** voltam para os **detalhes**; já a exclusão **confirmada** redireciona para a listagem (o objeto deixou de existir).

## URLs (`sign/urls.py`)

- Namespace `app_name = "sign"`. Incluído em `core/urls.py` na raiz (`path("", include("sign.urls"))`).
- **Os paths das rotas são em inglês** (`products/`, `products/new/`, `products/<pk>/edit/`, `manufacturers/`, ...). Os textos de UI são em PT-BR.
- `/` (`name="home"`) redireciona para `sign:product_list`.

## Templates (`sign/templates/sign/`)

- **`base.html`** é o shell base reutilizável; todas as telas o estendem (`{% extends "sign/base.html" %}`). Estrutura:
  - **Side menu** fixo à esquerda (`bg-navy`, `w-64`, `id="sidebar"`), com a marca **"Kasa dos Reparos"** no topo e itens agrupados por **seções** (rótulo uppercase): **Logística → Produtos** e **Social → Fabricantes**. Os itens são só texto + ícone FontAwesome (`fa-tag`, `fa-building-user`).
  - **Item ativo**: destacado em `bg-blue-600`, detectado via `request.resolver_match.url_name` (`{% if 'product' in url_name %}` / `'manufacturer' in url_name`).
  - **Header** branco no topo com um botão `fa-bars` (`id="sidebarToggle"`) que mostra/oculta o side menu via um pequeno `<script>` no fim do `<body>` (alterna `-translate-x-full` na sidebar e `ml-64`/`ml-0` no `#content`). Há um `{% block header %}` reservado para botões futuros.
  - Mantém o bloco de mensagens e o `{% block content %}`.
- Os templates de cada recurso ficam em **subpastas próprias**, referenciadas em `template_name` das views:
  - **Produtos** (`sign/products/`): `list.html`, `detail.html`, `form.html`, `confirm_delete.html`.
  - **Fabricantes** (`sign/manufacturers/`): `list.html`, `form.html`, `confirm_delete.html`.
- **Telas de form e exclusão**: o conteúdo ocupa o espaço inteiro disponível (`flex min-h-full`); cards menores ficam centralizados. As **ações de listagem** são ícones (`fa-eye`, `fa-pen-to-square`, `fa-trash`) com `title`/`aria-label`; os **botões** usam ícones: Salvar=`fa-check`, excluir=`fa-trash`, Cancelar=`fa-xmark`, Voltar=`fa-arrow-left`. A tela de **detalhes** mostra o `dl` num card branco e os botões Editar/Deletar/Voltar abaixo.
- **Exibição da quantidade** (`products/list.html` e `products/detail.html`): `quantity` é inteiro, exibido como `{{ product.quantity }} {{ product.unit_type }}` (a sigla do tipo, não o label completo).
- Preço é exibido com `R$ {{ product.unit_price|floatformat:2 }}`.

## Tailwind CSS — build offline (importante)

A app é empacotada para desktop **offline** (PyWebView/PyInstaller), então **não** usamos CDN.

- Usa-se o **Tailwind CLI standalone v4** (binário, sem Node/npm). O binário `tailwindcss.exe` fica na raiz e **não é versionado** (está no `.gitignore`).
- Sintaxe **v4** (CSS-based, não há `tailwind.config.js`): o arquivo de entrada `sign/static/sign/css/input.css` usa `@import "tailwindcss";` + `@source "../../../templates/**/*.html";`.
- O **`output.css` é commitado** no repositório para funcionar offline no app empacotado.
- Comando de build (rodar sempre que classes mudarem nos templates):
  ```
  ./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify
  ```
- Adicionar `--watch` durante o desenvolvimento.

### Paleta de cores (tokens `@theme`)

O `input.css` define cores customizadas via `@theme`, expostas como utilitários Tailwind:

| Token | Valor | Uso |
|---|---|---|
| `navy` | `#1b2a4e` | fundo do side menu |
| `navy-hover` | `#25365e` | hover dos itens do menu |
| `canvas` | `#eef1f6` | fundo da área de conteúdo (`<body>`) |

O azul de **destaque/ação** (item ativo do menu, botões primários, link "Ver") é o **`blue-600`** nativo do Tailwind. **Não use `indigo`** — foi substituído por `blue` em toda a UI.

## Ícones — FontAwesome Free (offline)

Como o app roda offline, o **FontAwesome Free** é servido **localmente** (sem CDN):

- Assets em **`sign/static/sign/fontawesome/`** (`css/all.min.css` + `webfonts/`), **commitados** no repositório. Versão **6.7.2**.
- Linkado no `base.html` (`{% static 'sign/fontawesome/css/all.min.css' %}`) **antes** do `output.css`.
- Uso nos templates: `<i class="fa-solid fa-NOME"></i>` (apenas o estilo **solid** é usado).
- Ícones em uso: menu `fa-tag`/`fa-building-user`; header `fa-bars`; ações `fa-eye`/`fa-pen-to-square`/`fa-trash`; botões `fa-check`/`fa-xmark`/`fa-arrow-left`/`fa-plus`.
- Para **adicionar/atualizar** os assets, baixe o pacote "web" do FontAwesome Free e copie `css/all.min.css` + `webfonts/` para a pasta acima (o CSS referencia `../webfonts/`).

## Verificação rápida

```
./venv/Scripts/python.exe manage.py makemigrations
./venv/Scripts/python.exe manage.py migrate
./venv/Scripts/python.exe manage.py check
./venv/Scripts/python.exe manage.py runserver
```
Fluxo manual: criar fabricante → criar produto (digitando preço em reais) → listar →
detalhar → editar → excluir. Conferir mensagens de sucesso e o bloqueio ao excluir
fabricante com produtos vinculados.
