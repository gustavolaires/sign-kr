# Cadastro de Clientes (app `sign`)

Feature de CRUD completo para **Clientes**, com interface em Tailwind CSS. Segue
exatamente as convenções de Produtos/Fabricantes (ver [`produtos.md`](produtos.md)).
Esta documentação registra os campos, decisões e comportamentos não óbvios — leia
antes de alterar o model, form ou templates desta área.

## Models (`sign/models.py`)

| Model | Campos principais | Observações |
|---|---|---|
| `PersonType` | `TextChoices` | `pf` → "Pessoa Física", `pj` → "Pessoa Jurídica". |
| `Client` | `name`, `person_type`, `service_provider`, `cpf_cnpj`, `birth_date`, `email`, `phone_primary`, `phone_primary_is_whatsapp`, `phone_secondary`, `phone_secondary_is_whatsapp`, `street`, `number`, `complement`, `district`, `city`, `postal_code` | Ver detalhes abaixo. |

### Campos obrigatórios x opcionais
- **Obrigatórios** (sem `blank`): `name`, `person_type` (default `PF`), `cpf_cnpj`.
- **Opcionais**: todos os demais usam `blank=True`. Apenas `birth_date` (`DateField`) tem
  também `null=True`, pois data vazia precisa ser `NULL` no banco.
- **Tipo de pessoa**: `TextChoices` (`PersonType`), mesmo padrão de `UnitType`; renderizado
  como `<select>`. Na exibição use `{{ client.get_person_type_display }}`.
- **WhatsApp**: `phone_primary_is_whatsapp` / `phone_secondary_is_whatsapp` são
  `BooleanField(default=False)`.
- **Prestador de serviço**: `service_provider` é `BooleanField(default=False)`. Exibido na
  listagem (coluna "Serviço", ícone `fa-wrench`) e no detalhe/form (Dados básicos).
- **Sem valores monetários**: não há campos `_cents` neste cadastro.

## Forms (`sign/forms.py`)

- `ClientForm` herda de `StyledModelForm` — as classes Tailwind (`INPUT_CLASSES`) são
  aplicadas automaticamente; `CheckboxInput` é pulado (os dois campos de WhatsApp ficam
  como checkbox nativo).
- `fields` é uma **lista explícita** na ordem da UI.
- Único ajuste de widget: `birth_date` usa `DateInput(attrs={"type": "date"}, format="%Y-%m-%d")`
  para o date picker nativo do HTML5 e para preencher corretamente o valor na edição
  (o `input_formats` padrão do Django já aceita `%Y-%m-%d`).

## Views (`sign/views/clients.py`)

- Class-Based Views genéricas: `ListView`, `DetailView`, `CreateView`, `UpdateView`,
  `DeleteView` — espelham `products.py`.
- Mensagens de sucesso via `SuccessMessageMixin` (create/update) e `messages.success`
  manual na exclusão.
- `ClientUpdateView` define `get_success_url()` → ao **salvar** uma edição vai para os
  **detalhes** (`sign:client_detail`); create vai para a listagem.
- Não há tratamento de `ProtectedError`: nenhum model aponta para `Client` ainda. Se no
  futuro Cliente virar FK de vendas, replicar o padrão de `ManufacturerDeleteView`.
- Views exportadas em `sign/views/__init__.py`.

## URLs (`sign/urls.py`)

- Namespace `app_name = "sign"`. **Paths em inglês**: `clients/`, `clients/new/`,
  `clients/<pk>/`, `clients/<pk>/edit/`, `clients/<pk>/delete/`.
- Names: `client_list`, `client_create`, `client_detail`, `client_update`, `client_delete`.

## Templates (`sign/templates/sign/clients/`)

- `list.html`, `detail.html`, `form.html`, `confirm_delete.html` — estendem `base.html`.
- **Listagem**: colunas Nome, Serviço, Tipo de pessoa, CPF/CNPJ, E-mail, Telefone principal +
  ações (`fa-eye`, `fa-pen-to-square`, `fa-trash`). Detalhes:
  - **Serviço** (logo após o Nome): mostra o ícone `fa-solid fa-wrench` quando
    `service_provider` é verdadeiro; em branco caso contrário.
  - **Tipo de pessoa** aparece como **sigla maiúscula** (`{{ client.person_type|upper }}` →
    `PF`/`PJ`).
  - **Telefone principal**: mostra o ícone `fa-brands fa-whatsapp` (verde) ao lado do número
    quando `phone_primary_is_whatsapp` está marcado.
  - **Campos não preenchidos** (e-mail, telefone) ficam **em branco** (sem `—`).
  - **Filtros** (form GET acima da tabela): Nome (`icontains`), Tipo de pessoa (`select`
    PF/PJ), CPF/CNPJ (busca pelos dígitos digitados, ignorando máscara) e E-mail
    (`icontains`). Botão **Limpar** aparece quando há filtro ativo.
  - **Painel recolhível**: o form de filtros **inicia sempre visível** ao carregar a tela.
    Um botão **Filtros** (`fa-filter`, à esquerda do "Novo cliente") alterna a visibilidade
    via um pequeno script inline (toggle da classe `hidden` + `aria-expanded`).
  - **Ordenação**: cabeçalhos **Nome** e **CPF/CNPJ** são clicáveis e alternam asc/desc
    (ícone `fa-sort`/`fa-sort-up`/`fa-sort-down`). O `sort` é validado por allowlist no
    backend (`ClientListView.SORT_FIELDS`); os links de ordenação preservam os filtros
    ativos e os filtros preservam o `sort` (campo hidden).
- **Form**: organizado nas mesmas **3 seções** da tela de detalhes — **Dados básicos**
  (Nome, Tipo de pessoa, Prestador de serviço, CPF/CNPJ, Data de nascimento), **Contato**
  (E-mail, Telefone principal + flag WhatsApp, Telefone alternativo + flag WhatsApp) e
  **Endereço** (Rua, Número, Complemento, Bairro, Cidade, Código postal). Cada campo é
  renderizado pelo partial **`sign/clients/_field.html`** (`{% include ... with field=form.X %}`),
  que trata `checkbox` (input + label lado a lado) e os demais campos (label acima).
- **Detalhes**: organizado em **3 seções** (cada uma com seu `<h2>` + `dl` em grid 2
  colunas):
  - **Dados básicos**: Tipo de pessoa, Prestador de serviço (`yesno:"Sim,Não"`), CPF/CNPJ,
    Data de nascimento.
  - **Contato**: E-mail, Telefone principal, Telefone alternativo (telefones mostram o ícone
    `fa-brands fa-whatsapp` verde quando a flag de WhatsApp correspondente está marcada).
  - **Endereço**: Rua, Número, Complemento, Bairro, Cidade, Código postal.
- **Side menu** (`base.html`): item **Clientes** na seção **Social** (acima de Fabricantes),
  ícone `fa-users`, ativo via `{% if 'client' in url_name %}` (não colide com "manufacturer").

## Formatação de CPF/CNPJ, telefones e CEP (apenas visual)

Regra central: **o banco guarda só dígitos** (sem máscara); a formatação é **apenas
visual**, aplicada em dois lugares:

- **Ao digitar (front)**: os widgets de `cpf_cnpj`, `phone_primary`, `phone_secondary` e
  `postal_code` recebem `data-mask` (`cpf-cnpj` / `phone` / `cep`) + `inputmode="numeric"`
  no `ClientForm.Meta.widgets`. O script `sign/static/sign/js/masks.js` (incluído ao final
  do `form.html`) formata o valor enquanto o usuário digita e também reformata o valor
  pré-preenchido na edição. CPF/CNPJ alterna a máscara pelo nº de dígitos (≤11 = CPF
  `000.000.000-00`; ≥12 = CNPJ `00.000.000/0000-00`); telefone alterna fixo
  `(00) 0000-0000` / celular `(00) 00000-0000`; CEP `00000-000`.
- **Ao gravar (back)**: os métodos `clean_cpf_cnpj/phone_primary/phone_secondary/postal_code`
  do `ClientForm` removem tudo que não é dígito (`_only_digits`) antes de salvar. Assim, o
  banco nunca recebe pontuação.
- **Ao exibir (listas/detalhe)**: os filtros de template em `sign/templatetags/sign_format.py`
  (`cpf_cnpj`, `phone`, `cep`) remontam a máscara a partir dos dígitos. Se o nº de dígitos
  não bate com um formato conhecido, retornam o valor original sem alterar. Uso:
  `{% load sign_format %}` + `{{ client.cpf_cnpj|cpf_cnpj }}`, `{{ client.phone_primary|phone }}`,
  `{{ client.postal_code|cep }}`.

Não há validação de dígitos verificadores nem obrigatoriedade de formato — apenas máscara.

## Build do Tailwind

Mesma regra das outras áreas — rebuild do `output.css` após mudar classes nos templates
(ver [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md#tailwind-css-build)):
```
./tailwindcss.exe -i sign/static/sign/css/input.css -o sign/static/sign/css/output.css --minify
```

## Verificação rápida

```
./venv/Scripts/python.exe manage.py makemigrations
./venv/Scripts/python.exe manage.py migrate
./venv/Scripts/python.exe manage.py check
./venv/Scripts/python.exe manage.py runserver
```
Fluxo manual: menu **Social → Clientes** → criar cliente só com os obrigatórios (Nome,
Tipo de pessoa, CPF/CNPJ) → criar outro com todos os campos (data, e-mail, telefones +
flags WhatsApp, endereço) → listar → detalhar (data em `dd/mm/aaaa`, WhatsApp visível) →
editar (data pré-preenchida) → excluir. Conferir as mensagens de sucesso.
