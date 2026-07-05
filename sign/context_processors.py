"""Context processors do app ``sign``."""

from .cart import Cart
from .models import Company


def cart(request):
    """Expõe a contagem de produtos distintos no carrinho para os templates."""
    return {"cart_count": len(Cart(request))}


def company(request):
    """Expõe os dados da empresa (singleton) para todos os templates."""
    return {"company": Company.get_solo()}
