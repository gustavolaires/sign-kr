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
    quantity = models.PositiveIntegerField("Quantidade", default=0)
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


class PersonType(models.TextChoices):
    """Tipo de pessoa de um cliente."""

    PF = "pf", "Pessoa Física"
    PJ = "pj", "Pessoa Jurídica"


class Client(models.Model):
    """Cliente da empresa."""

    name = models.CharField("Nome", max_length=200)
    person_type = models.CharField(
        "Tipo de pessoa",
        max_length=2,
        choices=PersonType.choices,
        default=PersonType.PF,
    )
    service_provider = models.BooleanField("Prestador de serviço", default=False)
    cpf_cnpj = models.CharField("CPF/CNPJ", max_length=18)
    birth_date = models.DateField("Data de nascimento", null=True, blank=True)
    email = models.EmailField("E-mail", blank=True)
    phone_primary = models.CharField("Telefone principal", max_length=20, blank=True)
    phone_primary_is_whatsapp = models.BooleanField(
        "Telefone principal é WhatsApp", default=False
    )
    phone_secondary = models.CharField(
        "Telefone alternativo", max_length=20, blank=True
    )
    phone_secondary_is_whatsapp = models.BooleanField(
        "Telefone alternativo é WhatsApp", default=False
    )
    street = models.CharField("Rua", max_length=200, blank=True)
    number = models.CharField("Número", max_length=20, blank=True)
    complement = models.CharField("Complemento", max_length=120, blank=True)
    district = models.CharField("Bairro", max_length=120, blank=True)
    city = models.CharField("Cidade", max_length=120, blank=True)
    postal_code = models.CharField("Código postal", max_length=12, blank=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ["name"]

    def __str__(self):
        return self.name
