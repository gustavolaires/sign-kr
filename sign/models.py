import hashlib
import json

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


class PaymentType(models.TextChoices):
    """Formas de pagamento de uma venda."""

    CREDIT = "credit", "Crédito"
    DEBIT = "debit", "Débito"
    CASH = "cash", "Dinheiro"
    PIX = "pix", "Pix"
    OTHER = "other", "Outros"


class Sale(models.Model):
    """Venda finalizada no checkout.

    Os valores monetários ficam em centavos (inteiro). A venda é um documento
    imutável: os totais são gravados (não recalculados sob demanda) para manter
    o histórico consistente mesmo que produtos/regras mudem depois.
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
        verbose_name="Cliente",
    )
    subtotal_cents = models.PositiveIntegerField("Subtotal (centavos)", default=0)
    has_perc_discount = models.BooleanField("Desconto percentual", default=False)
    perc_discount = models.DecimalField(
        "Percentual de desconto",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    discount_cents = models.PositiveIntegerField("Desconto (centavos)", default=0)
    change_cents = models.PositiveIntegerField("Troco (centavos)", default=0)
    total_cents = models.PositiveIntegerField("Total (centavos)", default=0)
    obs = models.TextField("Observações", blank=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Venda"
        verbose_name_plural = "Vendas"
        ordering = ["-id"]

    def __str__(self):
        return f"Venda #{self.pk}"

    @property
    def subtotal(self):
        """Subtotal em reais (somente leitura)."""
        return self.subtotal_cents / 100

    @property
    def discount(self):
        """Desconto em reais (somente leitura)."""
        return self.discount_cents / 100

    @property
    def change(self):
        """Troco em reais (somente leitura)."""
        return self.change_cents / 100

    @property
    def total(self):
        """Total em reais (somente leitura)."""
        return self.total_cents / 100


class ProductSnapshot(models.Model):
    """Réplica dos dados descritivos de um produto no momento da venda.

    Funciona como cópia de segurança: o produto pode ser editado ou excluído
    depois sem alterar as vendas antigas. Snapshots idênticos são reaproveitados
    (dedup por ``content_hash``) para evitar crescimento desnecessário da tabela.
    O preço NÃO faz parte do snapshot (ele varia por venda e fica em ``SaleItem``),
    o que torna o reaproveitamento eficaz.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name="snapshots",
        null=True,
        blank=True,
        verbose_name="Produto",
    )
    name = models.CharField("Nome", max_length=200)
    description = models.TextField("Descrição", blank=True)
    barcode = models.CharField("Código de barras", max_length=64, blank=True)
    manufacturer_name = models.CharField("Fabricante", max_length=120)
    manufacturer_code = models.CharField(
        "Código do fabricante", max_length=64, blank=True
    )
    unit_type = models.CharField(
        "Tipo de unidade", max_length=4, choices=UnitType.choices
    )
    content_hash = models.CharField("Hash do conteúdo", max_length=64, unique=True)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Snapshot de produto"
        verbose_name_plural = "Snapshots de produto"
        ordering = ["-id"]

    def __str__(self):
        return self.name

    @staticmethod
    def compute_hash(*, product_id, name, description, barcode, manufacturer_name,
                     manufacturer_code, unit_type):
        """Fingerprint canônico (sha256) dos campos do snapshot.

        Inclui ``product_id`` ⇒ dedup por produto. Serialização canônica
        (JSON com ordem fixa) evita ambiguidade entre campos concatenados.
        """
        payload = json.dumps(
            [
                product_id,
                name,
                description,
                barcode,
                manufacturer_name,
                manufacturer_code,
                unit_type,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def get_or_create_for(cls, product):
        """Retorna o snapshot do produto, criando-o só se ainda não existir.

        Reaproveita um snapshot idêntico já existente (mesmo hash). O hash é um
        fingerprint do momento da criação; se o produto for excluído depois
        (``product`` vira NULL), o hash não é recalculado.
        """
        fields = {
            "product_id": product.pk,
            "name": product.name,
            "description": product.description,
            "barcode": product.barcode,
            "manufacturer_name": product.manufacturer.name,
            "manufacturer_code": product.manufacturer_code,
            "unit_type": product.unit_type,
        }
        content_hash = cls.compute_hash(**fields)
        snapshot, _ = cls.objects.get_or_create(
            content_hash=content_hash, defaults=fields
        )
        return snapshot


class SaleItem(models.Model):
    """Item (linha) de uma venda, ligado a um snapshot reaproveitável."""

    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="items", verbose_name="Venda"
    )
    product_snapshot = models.ForeignKey(
        ProductSnapshot,
        on_delete=models.PROTECT,
        related_name="sale_items",
        verbose_name="Snapshot do produto",
    )
    quantity = models.PositiveIntegerField("Quantidade", default=0)
    unit_price_cents = models.PositiveIntegerField("Preço unitário (centavos)", default=0)
    subtotal_cents = models.PositiveIntegerField("Subtotal (centavos)", default=0)
    has_perc_discount = models.BooleanField("Desconto percentual", default=False)
    perc_discount = models.DecimalField(
        "Percentual de desconto",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    discount_cents = models.PositiveIntegerField("Desconto (centavos)", default=0)
    total_cents = models.PositiveIntegerField("Total (centavos)", default=0)
    created_at = models.DateTimeField("Criado em", auto_now_add=True)

    class Meta:
        verbose_name = "Item da venda"
        verbose_name_plural = "Itens da venda"
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity}x {self.product_snapshot.name}"

    @property
    def unit_price(self):
        """Preço unitário em reais (somente leitura)."""
        return self.unit_price_cents / 100

    @property
    def subtotal(self):
        """Subtotal em reais (somente leitura)."""
        return self.subtotal_cents / 100

    @property
    def total(self):
        """Total em reais (somente leitura)."""
        return self.total_cents / 100


class SalePayment(models.Model):
    """Forma de pagamento de uma venda (até uma por tipo por venda)."""

    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="payments", verbose_name="Venda"
    )
    payment_type = models.CharField(
        "Forma de pagamento", max_length=8, choices=PaymentType.choices
    )
    installments = models.PositiveIntegerField("Parcelas", default=1)
    value_cents = models.PositiveIntegerField("Valor (centavos)", default=0)

    class Meta:
        verbose_name = "Pagamento"
        verbose_name_plural = "Pagamentos"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["sale", "payment_type"], name="uniq_sale_payment_type"
            )
        ]

    def __str__(self):
        return f"{self.get_payment_type_display()}: {self.value_cents} centavos"

    @property
    def value(self):
        """Valor em reais (somente leitura)."""
        return self.value_cents / 100
