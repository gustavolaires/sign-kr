from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from ..cart import Cart
from ..models import Product


def _format_cents(cents):
    """Formata centavos (inteiro) como reais no estilo ``12.34`` (sem float)."""
    return f"{cents // 100}.{cents % 100:02d}"


def _parse_request(request):
    """Lê ``product_id``/``quantity`` do POST e o produto correspondente.

    Retorna ``(product, quantity, error)``; ``error`` é uma mensagem PT-BR
    quando a entrada é inválida (produto inexistente ou quantidade não inteira).
    """
    product_id = request.POST.get("product_id")
    try:
        quantity = int(request.POST.get("quantity", ""))
    except (ValueError, TypeError):
        return None, None, "Quantidade inválida."

    product = Product.objects.filter(pk=product_id).first()
    if product is None:
        return None, None, "Produto não encontrado."
    return product, quantity, None


def cart_detail(request):
    """Renderiza a tela do carrinho (estado inicial lido do cookie)."""
    cart = Cart(request)
    return render(
        request,
        "sign/cart/detail.html",
        {"cart_items": cart.items(), "cart_total": cart.total_price()},
    )


@require_POST
def cart_add(request):
    """Adiciona (soma) um produto ao carrinho, validando o estoque."""
    cart = Cart(request)
    product, quantity, error = _parse_request(request)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)
    if not product.is_active:
        return JsonResponse(
            {"ok": False, "error": "Produto inativo não pode ser vendido."},
            status=400,
        )
    if quantity < 1:
        return JsonResponse(
            {"ok": False, "error": "Informe uma quantidade maior que zero."},
            status=400,
        )

    new_total = cart.quantity_of(product.pk) + quantity
    if new_total > product.quantity:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    f"Quantidade indisponível. Estoque: {product.quantity}; "
                    f"já no carrinho: {cart.quantity_of(product.pk)}."
                ),
            },
            status=400,
        )

    cart.add(product.pk, quantity)
    response = JsonResponse({"ok": True, "cart_count": len(cart)})
    return cart.save(response)


@require_POST
def cart_update(request):
    """Define a quantidade de um item do carrinho, validando o estoque."""
    cart = Cart(request)
    product, quantity, error = _parse_request(request)
    if error:
        return JsonResponse({"ok": False, "error": error}, status=400)
    if quantity < 1:
        return JsonResponse(
            {"ok": False, "error": "Informe uma quantidade maior que zero."},
            status=400,
        )
    if quantity > product.quantity:
        return JsonResponse(
            {
                "ok": False,
                "error": f"Quantidade indisponível. Estoque: {product.quantity}.",
            },
            status=400,
        )

    cart.set(product.pk, quantity)
    item_total_cents = product.unit_price_cents * quantity
    response = JsonResponse(
        {
            "ok": True,
            "cart_count": len(cart),
            "item_total": _format_cents(item_total_cents),
            "grand_total": _format_cents(cart.total_price_cents()),
        }
    )
    return cart.save(response)


@require_POST
def cart_remove(request):
    """Remove um item do carrinho."""
    cart = Cart(request)
    cart.remove(request.POST.get("product_id"))
    response = JsonResponse(
        {
            "ok": True,
            "cart_count": len(cart),
            "grand_total": _format_cents(cart.total_price_cents()),
        }
    )
    return cart.save(response)
