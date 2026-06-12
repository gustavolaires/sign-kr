from django.db import models


class Manufacturer(models.Model):
    """Fabricante de produtos."""

    name = models.CharField("Nome", max_length=120, unique=True)

    class Meta:
        verbose_name = "Fabricante"
        verbose_name_plural = "Fabricantes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UnitType(models.TextChoices):
    """Tipos de unidade de medida de um produto."""

    UNID = "unid", "Unidade"
    PCT = "pct", "Pacote"
    KG = "kg", "Quilograma"
    G = "g", "Grama"
    MG = "mg", "Miligrama"
    KM = "km", "Quilômetro"
    M = "m", "Metro"
    CM = "cm", "Centímetro"
    MM = "mm", "Milímetro"
    L = "l", "Litro"
    ML = "ml", "Mililitro"


class Product(models.Model):
    """Produto gerenciado no estoque."""

    name = models.CharField("Nome", max_length=200)
    description = models.TextField("Descrição", blank=True)
    barcode = models.CharField("Código de barras", max_length=64, blank=True)
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="Fabricante",
    )
    manufacturer_code = models.CharField(
        "Código do fabricante", max_length=64, blank=True
    )
    quantity = models.DecimalField(
        "Quantidade", max_digits=12, decimal_places=3, default=0
    )
    unit_type = models.CharField(
        "Tipo de unidade",
        max_length=4,
        choices=UnitType.choices,
        default=UnitType.UNID,
    )
    unit_price_cents = models.PositiveIntegerField(
        "Preço unitário (centavos)", default=0
    )

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def unit_price(self):
        """Preço unitário em reais (somente leitura), derivado dos centavos."""
        return self.unit_price_cents / 100
