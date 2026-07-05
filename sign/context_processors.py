"""Context processors do app ``sign``."""

from django.conf import settings

from .cart import Cart


def cart(request):
    """Expõe a contagem de produtos distintos no carrinho para os templates."""
    return {"cart_count": len(Cart(request))}


def company(request):
    """Expõe os dados da empresa (settings.COMPANY) para todos os templates."""
    return {"company": settings.COMPANY}
