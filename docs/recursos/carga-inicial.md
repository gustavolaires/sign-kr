# Carga inicial de Produtos e Fabricantes via CSV (app `sign`)

Recurso **oculto** para importar Fabricantes e Produtos de uma base já existente a
partir de um arquivo CSV. **Não há item de menu**: o acesso é só pela URL direta
(`/products/import/`). Fluxo em duas telas: **upload** → **mapeamento de
colunas** → execução. Valores monetários seguem
[`../arquitetura/convencoes.md`](../arquitetura/convencoes.md) (reais na UI,
centavos no banco).

## Fluxo

1. **Upload** (`products/import/`, `product_import_upload`): o usuário envia um
   `.csv`. O arquivo é lido **em memória** (`request.FILES`, sem `MEDIA_ROOT`),
   decodificado (`utf-8-sig` → fallback `latin-1`) e o delimitador é detectado com
   `csv.Sniffer` (entre `, ; \t`; fallback `;`). Cabeçalhos + linhas ficam em
   **`request.session["product_import"]`** e redireciona ao mapeamento.
2. **Mapeamento** (`products/import/mapping/`, `product_import_mapping`): para cada
   **campo-alvo** (`IMPORT_PRODUCT_FIELDS`) há um `<select>` com as colunas do CSV,
   **pré-selecionado por heurística** de nome de coluna (`_guess_mapping`, casa o
   cabeçalho normalizado contra aliases). Uma prévia mostra as 1ªs linhas.
   **Nome** e **Fabricante** são obrigatórios; sem eles, re-renderiza com erro.
3. **Execução** (POST do mapeamento): monta `rows` como lista de dicts
   `{campo_alvo: valor}` e chama `import_products_csv`; limpa a sessão e renderiza
   o **resultado** (contadores + linhas puladas).

## Serviço (`sign/services/imports.py`)

- **`import_products_csv(*, rows)`** — `@transaction.atomic`. `rows` é a lista de
  dicts já resolvida pela view. Dois passos, espelhando `create_inbound_invoice`:
  1. **Fabricantes**: `Manufacturer.objects.get_or_create(name=...)` para cada nome
     distinto e não-vazio (cacheados por nome).
  2. **Produtos**: por linha — valida e **cria ou atualiza**. Casa produto existente
     por **`barcode`** (se informado), senão por **`name` (iexact) + `manufacturer`**.
     Reaproveita `reais_to_cents` e `nf_search_tokens`/`format_nf_search` (anexa
     `barcode` e `manufacturer_code` ao `nf_search_id`, como `ProductForm.save`).
- **Relatório** (dict): `manufacturers_created`, `products_created`,
  `products_updated`, `imported` (criados + atualizados), `skipped` (lista de
  `{line, reason}`), `total`.

Ver as regras exatas em [Regras internas de processamento](#regras-internas-de-processamento).

## Regras internas de processamento

Toda a lógica fica no serviço `import_products_csv` (`@transaction.atomic`), num
único percurso em **dois passos**. `rows` já vem resolvido pela view (dicts
`{campo_alvo: valor_texto}`), então o serviço **não** conhece colunas/CSV.

### Passo 1 — Fabricantes
Percorre **todas** as linhas e coleta os nomes de fabricante distintos e
não-vazios (`strip`), fazendo `Manufacturer.objects.get_or_create(name=...)`.
Os objetos ficam num cache `nome → Manufacturer` (evita consultas repetidas no
passo 2). `manufacturers_created` conta só os efetivamente criados.

> **Nota:** um fabricante é criado a partir de **qualquer** linha que traga um
> nome de fabricante — inclusive linhas cujo produto será pulado no passo 2 (ex.:
> linha sem nome de produto). Isso reflete a intenção de "criar os fabricantes
> identificados no CSV", mas pode gerar um fabricante sem produtos.

### Passo 2 — Produtos (cria ou atualiza)
Percorre as linhas numeradas a partir de **1** (o nº aparece no `skipped`). Para
cada linha, na ordem, com **short-circuit** — o **primeiro** problema pula a linha
(registra `{line, reason}` em `skipped`) e passa à próxima; nada trava o lote:

| Ordem | Campo | Regra | Vazio | Inválido |
|---|---|---|---|---|
| 1 | `name` | obrigatório (`strip`) | **pula** ("Sem nome de produto.") | — |
| 2 | `manufacturer` | obrigatório; resolvido pelo cache do passo 1 | **pula** ("Sem fabricante.") | — |
| 3 | `unit_price` | reais → centavos via `_parse_reais` + `reais_to_cents` | `0` | **pula** ("Preço inválido: …") |
| 4 | `unit_type` | precisa estar em `UnitType.values` (minúsculas) | `unid` (default) | **pula** ("Tipo de unidade inválido: …") |
| 5 | `quantity` | inteiro ≥ 0 via `_parse_positive_int` | `0` | **pula** ("Quantidade inválida: …") |
| 6 | `min_stock` | inteiro ≥ 0 via `_parse_positive_int` | `Company.low_stock_threshold` | **pula** ("Estoque mínimo inválido: …") |

- **Preço** (`_parse_reais`): aceita vírgula **ou** ponto decimal, separador de
  milhar e `R$` (`"1.234,56"`, `"1234.56"`, `"R$ 12,34"`); se houver `,`, trata `.`
  como milhar. Convertido a centavos com `reais_to_cents` (`Decimal`/`ROUND_HALF_UP`,
  nunca float).
- **Inteiros** (`_parse_positive_int`): aceitam casas decimais (`"10"`, `"10.0"`,
  `"10,0"`), arredondando `ROUND_HALF_UP`; negativo é inválido.

#### Casamento (cria vs. atualiza)
Casa um produto já existente **nesta ordem**:
1. por **`barcode`** — se a linha trouxer código de barras (`Product.filter(barcode=…)`);
2. senão por **`name` (iexact) + `manufacturer`**.

Achou → **atualiza** todos os campos abaixo no produto existente (mantém o mesmo
registro, `is_active` **não** é tocado). Não achou → **cria** um `Product` novo com
`is_active=True`. Campos gravados (criação e atualização): `name`, `description`,
`barcode`, `manufacturer`, `manufacturer_code`, `quantity`, `unit_type`,
`unit_price_cents`, `min_stock`, `nf_search_id`.

> **Idempotência:** reimportar o mesmo CSV **atualiza** (não duplica), desde que o
> critério de casamento se mantenha (mesmo `barcode`, ou mesmo `name`+`manufacturer`).
> Como não há `unique` em `Product`, o casamento é 100% lógico da aplicação.

#### `nf_search_id`
Reproduz o `ProductForm.save`: parte dos tokens atuais (`nf_search_tokens` — vazio
na criação) e **anexa** `barcode` e `manufacturer_code` quando preenchidos e ainda
ausentes, reserializando com `format_nf_search` (cada token seguido de `;`). Assim
os produtos importados já casam em NFs de entrada futuras (`suggest_product_match`).

### Atomicidade
Tudo roda numa transação (`@transaction.atomic`). Linhas puladas **não** revertem o
lote (são apenas ignoradas); a transação só é desfeita se ocorrer um erro
**inesperado** (não previsto pelas validações acima), caso em que nada é gravado.

## Form (`sign/forms.py`)

- **`CsvImportForm(forms.Form)`** — `csv_file` (`FileField`). Estiliza os widgets
  manualmente **pulando `FileInput`** (o padrão de input distorceria o seletor de
  arquivo). `clean_csv_file` valida extensão `.csv` e tamanho (máx. 5 MB).

## Views (`sign/views/imports.py`) e URLs (`sign/urls.py`)

Function-based (multi-step com sessão), reexportadas em `sign/views/__init__.py`.
Rotas: `product_import_upload` (`products/import/`) e `product_import_mapping`
(`products/import/mapping/`). Como os nomes contêm `product`, o menu realça
"Produtos" — **aceitável**, pois não há link visível para a tela.

## Templates (`sign/templates/sign/imports/`)

`upload.html` (form `multipart/form-data`), `mapping.html` (selects de mapeamento +
prévia em tabela) e `result.html` (cartões de contadores + tabela de linhas
puladas). Estendem `base.html`; paleta/ícones padrão (`fa-upload`, `fa-check`).

## Verificação rápida

1. `./venv/Scripts/python.exe manage.py check`.
2. Acessar **`/products/import/`** direto pela URL (confirmar ausência no menu).
3. Enviar um CSV com colunas `Nome;Fabricante;Preço;Quantidade;Código de barras;Tipo`
   contendo linhas válidas (fabricante novo e existente), inválidas (sem fabricante;
   preço/tipo inválidos) e uma que casa com produto existente (para exercitar o
   **update**). Conferir o auto-mapeamento, importar e validar o relatório e os
   registros em Produtos/Fabricantes (preço em centavos, `nf_search_id`, sem
   duplicar ao reimportar). Testar CSV com `;` e com `,` (detecção de delimitador).
