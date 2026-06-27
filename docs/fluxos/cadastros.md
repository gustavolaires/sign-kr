# Fluxo de cadastros (CRUD genérico)

Padrão de uso comum a **Produtos, Fabricantes e Clientes** (e base dos demais
cadastros): listar → criar → detalhar → editar → excluir. Documenta o percurso e
o processamento compartilhados; as particularidades de cada entidade estão em
[`recursos/`](../recursos/). Convenção de implementação em
[`../arquitetura/convencoes.md`](../arquitetura/convencoes.md#padrão-crud).

## Percurso

```
  <area>/                 Listagem  ──"Novo"──►  <area>/new/        Criar
     │  ▲                                            │
 ações│  │                                           │ salva
     ▼  │ cancelar                                   ▼
  <area>/<pk>/            Detalhe  ◄── salva ──  <area>/<pk>/edit/  Editar
     │       │                                       ▲
 "Deletar"   └──────── cancelar ─────────────────────┘
     ▼
  <area>/<pk>/delete/     Confirmação ──confirma──► volta à Listagem
```

### Regras de navegação (para onde volta)

- **Criar** salva e vai para a **listagem**.
- **Editar** salva e vai para o **detalhe** do objeto (`get_success_url` →
  `<area>_detail`); o "Cancelar" da edição também volta ao detalhe.
- **Excluir**: o "Cancelar" volta ao detalhe; **confirmar** volta à **listagem**
  (o objeto deixou de existir).
- Botões padronizados por ícone: Salvar `fa-check`, Excluir `fa-trash`,
  Cancelar `fa-xmark`, Voltar `fa-arrow-left`, Novo `fa-plus`; ações de linha
  `fa-eye`/`fa-pen-to-square`/`fa-trash`.

## Processamento por etapa

### Listagem
- CBV `ListView`. **Filtros** chegam por GET e são aplicados no `get_queryset`
  (`icontains`, selects, etc.); `get_context_data` devolve os filtros ativos para
  re-exibir o form e mostrar/ocultar o botão **Limpar**.
- **Ordenação** por coluna (quando há): validada por **allowlist** no backend;
  os links de ordenação **preservam os filtros** e os filtros preservam o `sort`.
- Use `select_related` para FKs exibidas (evita N+1, ex.:
  `ProductListView.select_related("manufacturer")`).

### Criar / Editar
- CBVs `CreateView`/`UpdateView` + `SuccessMessageMixin` (mensagem de sucesso).
- O form herda de **`StyledModelForm`** (estilo Tailwind automático).
- **Conversões na borda do backend**:
  - **Dinheiro**: campo virtual em reais → centavos no `save()` (`ProductForm`).
  - **Máscaras** (CPF/CNPJ, telefone, CEP): formatadas no front por `masks.js`,
    mas **gravadas só com dígitos** pelos `clean_<campo>` (`ClientForm`).
  Ver [`../arquitetura/convencoes.md`](../arquitetura/convencoes.md).

### Excluir e integridade referencial
- CBV `DeleteView` com confirmação.
- FKs sensíveis usam **`on_delete=PROTECT`**: tentar excluir um registro
  referenciado levanta `ProtectedError`, **capturado pela view**, que mostra
  mensagem PT-BR e redireciona (padrão de `ManufacturerDeleteView`) em vez de
  estourar erro 500.
- Entidades ainda sem dependentes (ex.: `Client` quando criado) não tratam
  `ProtectedError`; ao virarem alvo de FK, replicar o padrão. Matriz completa de
  `on_delete` em [`../arquitetura/modelo-de-dados.md`](../arquitetura/modelo-de-dados.md).

## Apresentação

- Telas em subpastas por área (`products/`, `manufacturers/`, `clients/`), todas
  estendendo `base.html`. Formulários e detalhes podem ser **seccionados** (ex.:
  Clientes em Dados básicos / Contato / Endereço), com um partial `_field.html`
  para renderizar cada campo de forma uniforme.
- Telas de form/exclusão centralizam um card; listagens usam tabela com ações em
  ícone. Shell e menu em [`navegacao.md`](navegacao.md).

## Onde diverge por entidade

| Entidade | Particularidades | Doc |
|---|---|---|
| Produtos | preço em reais↔centavos; `quantity` com `step="any"`; redireciona ao detalhe | [produtos](../recursos/produtos.md) |
| Fabricantes | só `name`; `PROTECT` por produtos vinculados | [produtos](../recursos/produtos.md) |
| Clientes | seções; máscaras CPF/CNPJ/telefone/CEP; filtros + ordenação | [clientes](../recursos/clientes.md) |
