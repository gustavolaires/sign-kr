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

## URLs (`sign/urls.py`)

- Namespace `app_name = "sign"`. Incluído em `core/urls.py` na raiz (`path("", include("sign.urls"))`).
- **Os paths das rotas são em inglês** (`products/`, `products/new/`, `products/<pk>/edit/`, `manufacturers/`, ...). Os textos de UI são em PT-BR.
- `/` (`name="home"`) redireciona para `sign:product_list`.

## Templates (`sign/templates/sign/`)

- **`base.html`** é o template base reutilizável (navbar + bloco de mensagens + `{% block content %}`); todas as telas o estendem.
- **Exibição da quantidade na listagem** (`product_list.html`): quando `unit_type` é `unid` ou `pct`, usa `floatformat:"0"` (sem casas decimais, ex.: `100`); para as demais unidades usa `floatformat:"-3"` (até 3 casas, removendo zeros à direita, ex.: `1.5`).
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
