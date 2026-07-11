"""Carga inicial de Fabricantes e Produtos via CSV (recurso oculto).

Fluxo em duas telas: (1) upload do CSV — lido em memória, interpretado
(cabeçalhos + linhas) e guardado em ``request.session``; (2) mapeamento das
colunas do CSV para os campos-alvo e execução via ``import_products_csv``.
Não há item de menu: o acesso é só pela URL direta.
"""

import csv
import io
import unicodedata

from django.contrib import messages
from django.shortcuts import redirect, render

from ..forms import CsvImportForm
from ..services import IMPORT_PRODUCT_FIELDS, import_products_csv

# Chave da sessão onde o CSV interpretado fica entre o upload e o mapeamento.
SESSION_KEY = "product_import"

# Nº de linhas exibidas na prévia da tela de mapeamento.
PREVIEW_ROWS = 10


def _normalize(text):
    """Normaliza um cabeçalho para casar aliases: minúsculas, sem acento/espaços."""
    text = unicodedata.normalize("NFKD", (text or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


# Aliases (normalizados) por campo-alvo, para o auto-mapeamento das colunas.
_FIELD_ALIASES = {
    "name": {"nome", "produto", "nome do produto"},
    "manufacturer": {"fabricante", "marca", "fabricante (nome)"},
    "description": {"descricao", "detalhes", "observacao", "observacoes"},
    "barcode": {"codigo de barras", "ean", "cod barras", "barras", "codbarras"},
    "manufacturer_code": {
        "codigo do fabricante",
        "codigo fabricante",
        "cod fabricante",
        "referencia",
        "ref",
    },
    "unit_price": {
        "preco",
        "preco unitario",
        "valor",
        "valor unitario",
        "preco de venda",
    },
    "quantity": {"quantidade", "qtd", "qtde", "estoque"},
    "min_stock": {"estoque minimo", "minimo", "estoque min"},
    "unit_type": {"tipo de unidade", "unidade", "tipo", "un", "und"},
}


def _guess_mapping(headers):
    """Sugere ``campo → índice da coluna`` casando cabeçalhos com os aliases.

    Casamento por igualdade exata (após normalizar); cada coluna é usada por no
    máximo um campo. Campos sem correspondência recebem ``None``.
    """
    normalized = [_normalize(h) for h in headers]
    used = set()
    mapping = {}
    for key, _, _ in IMPORT_PRODUCT_FIELDS:
        aliases = _FIELD_ALIASES.get(key, set())
        mapping[key] = None
        for index, header in enumerate(normalized):
            if index in used:
                continue
            if header in aliases:
                mapping[key] = index
                used.add(index)
                break
    return mapping


def _render_mapping(request, headers, rows, selected):
    """Renderiza a tela de mapeamento com a seleção atual por campo."""
    fields = [
        {
            "key": key,
            "label": label,
            "required": required,
            "selected": selected.get(key),
        }
        for key, label, required in IMPORT_PRODUCT_FIELDS
    ]
    context = {
        "headers": list(enumerate(headers)),
        "fields": fields,
        "preview": rows[:PREVIEW_ROWS],
        "total_rows": len(rows),
    }
    return render(request, "sign/imports/mapping.html", context)


def product_import_upload(request):
    """Tela de upload do CSV. POST interpreta o arquivo e vai ao mapeamento."""
    if request.method == "POST":
        form = CsvImportForm(request.POST, request.FILES)
        if form.is_valid():
            raw = form.cleaned_data["csv_file"].read()
            text = None
            for encoding in ("utf-8-sig", "latin-1"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                messages.error(request, "Não foi possível ler o arquivo (codificação).")
                return render(request, "sign/imports/upload.html", {"form": form})

            # Detecta o delimitador (vírgula, ponto e vírgula ou tab); fallback ';'.
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ";"

            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            all_rows = [row for row in reader if any(cell.strip() for cell in row)]
            if not all_rows:
                messages.error(request, "O arquivo está vazio.")
                return render(request, "sign/imports/upload.html", {"form": form})

            request.session[SESSION_KEY] = {
                "headers": all_rows[0],
                "rows": all_rows[1:],
            }
            return redirect("sign:product_import_mapping")
    else:
        form = CsvImportForm()
    return render(request, "sign/imports/upload.html", {"form": form})


def product_import_mapping(request):
    """Tela de mapeamento das colunas + execução da importação."""
    data = request.session.get(SESSION_KEY)
    if not data:
        messages.error(request, "Envie um arquivo CSV para começar.")
        return redirect("sign:product_import_upload")

    headers = data["headers"]
    rows = data["rows"]

    if request.method == "POST":
        selected = {}
        for key, _, _ in IMPORT_PRODUCT_FIELDS:
            value = request.POST.get(f"map_{key}", "")
            selected[key] = (
                int(value) if value.isdigit() and int(value) < len(headers) else None
            )
        if selected.get("name") is None or selected.get("manufacturer") is None:
            messages.error(
                request, "Mapeie ao menos as colunas de Nome e Fabricante."
            )
            return _render_mapping(request, headers, rows, selected)

        mapped_rows = []
        for row in rows:
            mapped = {}
            for key, index in selected.items():
                mapped[key] = row[index] if index is not None and index < len(row) else ""
            mapped_rows.append(mapped)

        report = import_products_csv(rows=mapped_rows)
        del request.session[SESSION_KEY]
        messages.success(request, "Importação concluída.")
        return render(request, "sign/imports/result.html", {"report": report})

    return _render_mapping(request, headers, rows, _guess_mapping(headers))
