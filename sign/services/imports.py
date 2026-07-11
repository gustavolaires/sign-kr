"""Importação de produtos/fabricantes via CSV (carga inicial).

A tela de mapeamento (view) e este serviço compartilham ``IMPORT_PRODUCT_FIELDS``.
Reaproveita os helpers de ``nf_search_id`` de ``invoices`` e o parsing monetário
de ``money``. Importação parcial: linhas inválidas são puladas e reportadas.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from ..models import Company, Manufacturer, Product, UnitType
from .invoices import format_nf_search, nf_search_tokens
from .money import _parse_reais, reais_to_cents

# Campos-alvo do mapeamento CSV → Product/Manufacturer: (chave, rótulo PT-BR,
# obrigatório?). A tela de mapeamento e o serviço compartilham esta lista.
IMPORT_PRODUCT_FIELDS = [
    ("name", "Nome do produto", True),
    ("manufacturer", "Fabricante (nome)", True),
    ("description", "Descrição", False),
    ("barcode", "Código de barras", False),
    ("manufacturer_code", "Código do fabricante", False),
    ("unit_price", "Preço unitário (R$)", False),
    ("quantity", "Quantidade", False),
    ("min_stock", "Estoque mínimo", False),
    ("unit_type", "Tipo de unidade", False),
]


def _parse_positive_int(value):
    """Converte texto do CSV para inteiro ≥ 0. Vazio → ``None``.

    Aceita casas decimais (``"10"``, ``"10.0"``, ``"10,0"``), arredondando.
    Levanta ``ValueError`` para texto não numérico ou negativo.
    """
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        number = Decimal(text)
    except ArithmeticError as exc:
        raise ValueError(str(exc))
    if number < 0:
        raise ValueError("valor negativo")
    return int(number.to_integral_value(rounding=ROUND_HALF_UP))


@transaction.atomic
def import_products_csv(*, rows):
    """Importa fabricantes e produtos a partir de linhas de CSV já mapeadas.

    ``rows`` é uma lista de dicts ``{campo_alvo: valor_texto}`` (a view resolve o
    mapeamento coluna→campo). Em dois passos: (1) cria os fabricantes ainda não
    cadastrados (``get_or_create`` por nome); (2) cria ou **atualiza** os produtos
    (casa por ``barcode`` quando informado, senão por ``name`` + ``manufacturer``).
    Linhas inválidas são **puladas** e registradas em ``skipped`` (importação
    parcial); as válidas são persistidas. O preço vem em reais. Devolve um
    relatório (dict) com os contadores e os motivos das linhas puladas.
    """
    default_min_stock = Company.get_solo().low_stock_threshold or 0

    # --- Passo 1: fabricantes (get_or_create por nome) ---
    manufacturers = {}  # nome → Manufacturer (cache, evita consultas repetidas)
    manufacturers_created = 0
    for row in rows:
        name = (row.get("manufacturer") or "").strip()
        if not name or name in manufacturers:
            continue
        obj, created = Manufacturer.objects.get_or_create(name=name)
        manufacturers[name] = obj
        if created:
            manufacturers_created += 1

    # --- Passo 2: produtos (cria ou atualiza) ---
    products_created = 0
    products_updated = 0
    skipped = []

    for line, row in enumerate(rows, start=1):
        name = (row.get("name") or "").strip()
        manufacturer_name = (row.get("manufacturer") or "").strip()
        if not name:
            skipped.append({"line": line, "reason": "Sem nome de produto."})
            continue
        if not manufacturer_name:
            skipped.append({"line": line, "reason": "Sem fabricante."})
            continue
        manufacturer = manufacturers[manufacturer_name]

        # Preço (reais → centavos).
        try:
            unit_price_cents = reais_to_cents(_parse_reais(row.get("unit_price")))
        except (ArithmeticError, ValueError):
            skipped.append(
                {"line": line, "reason": f"Preço inválido: {row.get('unit_price')!r}."}
            )
            continue

        # Tipo de unidade (vazio → unidade; desconhecido → pula).
        unit_type = (row.get("unit_type") or "").strip().lower()
        if unit_type and unit_type not in UnitType.values:
            skipped.append(
                {"line": line, "reason": f"Tipo de unidade inválido: {unit_type!r}."}
            )
            continue
        unit_type = unit_type or UnitType.UNID

        # Quantidade (vazio → 0) e estoque mínimo (vazio → default da empresa).
        try:
            quantity = _parse_positive_int(row.get("quantity")) or 0
        except ValueError:
            skipped.append(
                {"line": line, "reason": f"Quantidade inválida: {row.get('quantity')!r}."}
            )
            continue
        try:
            min_stock = _parse_positive_int(row.get("min_stock"))
        except ValueError:
            skipped.append(
                {"line": line, "reason": f"Estoque mínimo inválido: {row.get('min_stock')!r}."}
            )
            continue
        if min_stock is None:
            min_stock = default_min_stock

        barcode = (row.get("barcode") or "").strip()
        manufacturer_code = (row.get("manufacturer_code") or "").strip()
        description = (row.get("description") or "").strip()

        # Casa produto existente: por barcode; senão por nome + fabricante.
        existing = None
        if barcode:
            existing = Product.objects.filter(barcode=barcode).first()
        if existing is None:
            existing = Product.objects.filter(
                name__iexact=name, manufacturer=manufacturer
            ).first()

        # nf_search_id: anexa barcode e código do fabricante (como ProductForm.save).
        tokens = nf_search_tokens(existing.nf_search_id if existing else "")
        for extra in (barcode, manufacturer_code):
            if extra and extra not in tokens:
                tokens.append(extra)
        nf_search_id = format_nf_search(tokens)

        values = {
            "name": name,
            "description": description,
            "barcode": barcode,
            "manufacturer": manufacturer,
            "manufacturer_code": manufacturer_code,
            "quantity": quantity,
            "unit_type": unit_type,
            "unit_price_cents": unit_price_cents,
            "min_stock": min_stock,
            "nf_search_id": nf_search_id,
        }
        if existing is None:
            Product.objects.create(is_active=True, **values)
            products_created += 1
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.save()
            products_updated += 1

    return {
        "manufacturers_created": manufacturers_created,
        "products_created": products_created,
        "products_updated": products_updated,
        "imported": products_created + products_updated,
        "skipped": skipped,
        "total": len(rows),
    }
