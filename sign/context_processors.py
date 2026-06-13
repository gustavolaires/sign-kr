"""Context processors do app ``sign``."""

from .cart import Cart


def cart(request):
    """Expõe a contagem de produtos distintos no carrinho para os templates."""
    return {"cart_count": len(Cart(request))}
