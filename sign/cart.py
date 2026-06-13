"""Carrinho de compras persistido em cookie (sem banco de dados).

O carrinho é serializado em JSON no cookie ``cart`` no formato
``{"<product_id>": <quantidade>}``. As escritas são feitas pelas views (via
``Cart.save(response)``), que validam o estoque antes de gravar.
"""

import json

from .models import Product

COOKIE_NAME = "cart"
# Persistência longa para o carrinho sobreviver ao fechar/reabrir o app.
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias, em segundos.


class Cart:
    """Encapsula leitura/escrita do carrinho no cookie da requisição."""

    def __init__(self, request):
        raw = request.COOKIES.get(COOKIE_NAME)
        cart = {}
        if raw:
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                data = {}
            if isinstance(data, dict):
                # Normaliza: chaves str, quantidades int > 0.
                for key, value in data.items():
                    try:
                        quantity = int(value)
                    except (ValueError, TypeError):
                        continue
                    if quantity > 0:
                        cart[str(key)] = quantity
        self.cart = cart

    def __len__(self):
        """Número de produtos distintos (usado no badge do header)."""
        return len(self.cart)

    def quantity_of(self, product_id):
        """Quantidade atual de um produto no carrinho (0 se ausente)."""
        return self.cart.get(str(product_id), 0)

    def add(self, product_id, quantity):
        """Soma ``quantity`` à quantidade existente do produto."""
        key = str(product_id)
        self.cart[key] = self.cart.get(key, 0) + quantity

    def set(self, product_id, quantity):
        """Define a quantidade do produto (substitui a existente)."""
        self.cart[str(product_id)] = quantity

    def remove(self, product_id):
        """Remove o produto do carrinho, se presente."""
        self.cart.pop(str(product_id), None)

    def items(self):
        """Itens do carrinho com produto, quantidade e totais (em reais).

        Faz uma única query e ignora ids cujo produto não exista mais.
        """
        products = Product.objects.select_related("manufacturer").in_bulk(
            [int(pid) for pid in self.cart.keys()]
        )
        items = []
        for pid, quantity in self.cart.items():
            product = products.get(int(pid))
            if product is None:
                continue
            total_cents = product.unit_price_cents * quantity
            items.append(
                {
                    "product": product,
                    "quantity": quantity,
                    "unit_price": product.unit_price,
                    "total_price": total_cents / 100,
                }
            )
        return items

    def total_price_cents(self):
        """Total geral do carrinho em centavos (inteiro)."""
        products = Product.objects.in_bulk(
            [int(pid) for pid in self.cart.keys()]
        )
        total = 0
        for pid, quantity in self.cart.items():
            product = products.get(int(pid))
            if product is not None:
                total += product.unit_price_cents * quantity
        return total

    def total_price(self):
        """Total geral do carrinho em reais (somente exibição)."""
        return self.total_price_cents() / 100

    def save(self, response):
        """Grava o carrinho no cookie da resposta."""
        response.set_cookie(
            COOKIE_NAME,
            json.dumps(self.cart),
            max_age=COOKIE_MAX_AGE,
            samesite="Lax",
        )
        return response
