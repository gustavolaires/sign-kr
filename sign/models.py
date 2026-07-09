import hashlib
import json

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


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
    is_active = models.BooleanField("Ativo", default=True)
    min_stock = models.PositiveIntegerField("Estoque mínimo", default=0)
    nf_search_id = models.TextField(
        "IDs de busca para NF",
        blank=True,
        help_text="IDs de referência usados por fornecedores, separados por ';'.",
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


class BrazilianState(models.TextChoices):
    """Unidades federativas do Brasil (sigla armazenada e exibida)."""

    AC = "AC", "AC"
    AL = "AL", "AL"
    AP = "AP", "AP"
    AM = "AM", "AM"
    BA = "BA", "BA"
    CE = "CE", "CE"
    DF = "DF", "DF"
    ES = "ES", "ES"
    GO = "GO", "GO"
    MA = "MA", "MA"
    MT = "MT", "MT"
    MS = "MS", "MS"
    MG = "MG", "MG"
    PA = "PA", "PA"
    PB = "PB", "PB"
    PR = "PR", "PR"
    PE = "PE", "PE"
    PI = "PI", "PI"
    RJ = "RJ", "RJ"
    RN = "RN", "RN"
    RS = "RS", "RS"
    RO = "RO", "RO"
    RR = "RR", "RR"
    SC = "SC", "SC"
    SP = "SP", "SP"
    SE = "SE", "SE"
    TO = "TO", "TO"


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
    state = models.CharField(
        "Estado",
        max_length=2,
        choices=BrazilianState.choices,
        blank=True,
    )
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
    discount_obs = models.TextField("Observações do desconto", blank=True)
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


class Expense(models.Model):
    """Despesa (definição). As ocorrências/parcelas ficam em ``ExpenseInstallment``.

    Uma despesa pode ser isolada (``recurrent=False``) ou recorrente
    (``recurrent=True``), caso em que ``scheduled_for`` guarda o dia previsto de
    vencimento (1–31) e as parcelas são geradas por horizonte (próximos N meses).
    "Parcela única vs múltiplas" e "valor fixo vs variável" são resolvidos pelas
    parcelas filhas: cada uma tem seu próprio valor e vencimento.
    """

    name = models.CharField("Nome", max_length=200)
    description = models.TextField("Descrição", blank=True)
    recurrent = models.BooleanField("Recorrente", default=False)
    scheduled_for = models.PositiveSmallIntegerField(
        "Dia previsto de vencimento",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Dia do mês (1–31) usado quando a despesa é recorrente.",
    )
    created_at = models.DateTimeField("Criada em", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"
        ordering = ["-id"]

    def __str__(self):
        return self.name


class ExpenseInstallment(models.Model):
    """Parcela/ocorrência de uma despesa.

    Os valores ficam em centavos (inteiro). O ``status`` é derivado (não
    armazenado) a partir do valor pago e da data de vencimento.
    """

    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"

    STATUS_LABELS = {
        PENDING: "Pendente",
        PARTIAL: "Parcial",
        PAID: "Pago",
        OVERDUE: "Atrasado",
    }

    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="installments",
        verbose_name="Despesa",
    )
    installment_current = models.PositiveIntegerField("Parcela", default=1)
    installment_total = models.PositiveIntegerField("Total de parcelas", default=1)
    value_cents = models.PositiveIntegerField("Valor (centavos)", default=0)
    due_date = models.DateField("Data de vencimento")
    paid_value_cents = models.PositiveIntegerField("Valor pago (centavos)", default=0)
    paid_at = models.DateField("Data de pagamento", null=True, blank=True)
    created_at = models.DateTimeField("Criada em", auto_now_add=True)
    updated_at = models.DateTimeField("Atualizada em", auto_now=True)

    class Meta:
        verbose_name = "Parcela"
        verbose_name_plural = "Parcelas"
        ordering = ["due_date", "installment_current"]

    def __str__(self):
        return f"{self.installment_current}/{self.installment_total} — {self.expense.name}"

    @property
    def value(self):
        """Valor em reais (somente leitura)."""
        return self.value_cents / 100

    @property
    def paid_value(self):
        """Valor pago em reais (somente leitura)."""
        return self.paid_value_cents / 100

    @property
    def status(self):
        """Situação derivada: pago / parcial / atrasado / pendente.

        Prioridade: quitada (pago ≥ devido) > paga em parte > vencida em aberto
        > pendente. Usa a data local atual para detectar atraso.
        """
        if self.value_cents and self.paid_value_cents >= self.value_cents:
            return self.PAID
        if self.paid_value_cents > 0:
            return self.PARTIAL
        if self.due_date and self.due_date < timezone.localdate():
            return self.OVERDUE
        return self.PENDING

    @property
    def status_label(self):
        """Rótulo PT-BR da situação (para exibição)."""
        return self.STATUS_LABELS[self.status]


class RoundingType(models.TextChoices):
    """Estratégias de arredondamento de preço (usadas na precificação)."""

    CENT = "cent", "Centavo"
    CENT_10 = "cent_10", "Centavo (Múltiplo de 10)"
    REAL = "real", "Real"
    REAL_2 = "real_2", "Real (Múltiplo de 2)"
    REAL_5 = "real_5", "Real (Múltiplo de 5)"
    REAL_10 = "real_10", "Real (Múltiplo de 10)"


class Company(models.Model):
    """Dados da empresa exibidos na UI e nos comprovantes (não fiscais).

    É um *singleton*: existe sempre uma única linha (``pk=1``), editável pela
    tela de configurações. Os campos mascarados (``cnpj``, telefones,
    ``postal_code``) armazenam apenas dígitos; a formatação é aplicada na
    exibição pelos filtros de ``sign_format``.
    """

    name = models.CharField("Nome", max_length=200)
    legal_name = models.CharField("Razão social", max_length=200, blank=True)
    cnpj = models.CharField("CNPJ", max_length=18, blank=True)
    email = models.EmailField("E-mail", blank=True)
    phone_primary = models.CharField("Telefone principal", max_length=20, blank=True)
    phone_secondary = models.CharField(
        "Telefone alternativo", max_length=20, blank=True
    )
    street = models.CharField("Rua", max_length=200, blank=True)
    number = models.CharField("Número", max_length=20, blank=True)
    complement = models.CharField("Complemento", max_length=120, blank=True)
    district = models.CharField("Bairro", max_length=120, blank=True)
    city = models.CharField("Cidade", max_length=120, blank=True)
    state = models.CharField(
        "Estado",
        max_length=2,
        choices=BrazilianState.choices,
        blank=True,
    )
    postal_code = models.CharField("Código postal", max_length=12, blank=True)

    # Operação e precificação (usados na dashboard e na precificação).
    daily_sales_goal_cents = models.PositiveIntegerField(
        "Meta de venda diária (centavos)", default=0
    )
    operating_days_per_week = models.PositiveSmallIntegerField(
        "Dias de operação na semana",
        default=6,
        choices=[(i, str(i)) for i in range(0, 8)],
    )
    low_stock_threshold = models.PositiveIntegerField("Estoque baixo", default=5)
    price_multiplier = models.FloatField(
        "Fator multiplicativo de preço", default=1.0
    )
    rounding_type = models.CharField(
        "Tipo de arredondamento",
        max_length=8,
        choices=RoundingType.choices,
        default=RoundingType.CENT,
    )

    class Meta:
        verbose_name = "Empresa"
        verbose_name_plural = "Empresa"

    def __str__(self):
        return self.name

    @property
    def display_name(self):
        """Nome de exibição: razão social se preenchida, senão o nome."""
        return self.legal_name or self.name

    @property
    def daily_sales_goal(self):
        """Meta de venda diária em reais (somente leitura)."""
        return self.daily_sales_goal_cents / 100

    def save(self, *args, **kwargs):
        """Força o singleton: a empresa é sempre a linha ``pk=1``."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """Retorna a única instância da empresa, criando-a se necessário."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Supplier(models.Model):
    """Fornecedor: responsável por vender e entregar os produtos.

    Os campos mascarados (``cnpj``, telefones) armazenam apenas dígitos; a
    formatação é aplicada na exibição pelos filtros de ``sign_format``. A
    ``state_registration`` (inscrição estadual) é texto livre (pode ser
    alfanumérica ou "ISENTO"), portanto não é mascarada.
    """

    name = models.CharField("Nome", max_length=200)
    cnpj = models.CharField("CNPJ", max_length=18, blank=True)
    state_registration = models.CharField(
        "Inscrição estadual", max_length=20, blank=True
    )
    multiple_brands = models.BooleanField(
        "Trabalha com múltiplas marcas", default=True
    )
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.SET_NULL,
        related_name="suppliers",
        null=True,
        blank=True,
        verbose_name="Marca",
        help_text="Usado quando o fornecedor não trabalha com múltiplas marcas.",
    )
    email = models.EmailField("E-mail", blank=True)
    phone_primary = models.CharField("Telefone principal", max_length=20, blank=True)
    phone_secondary = models.CharField(
        "Telefone alternativo", max_length=20, blank=True
    )

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Representative(models.Model):
    """Representante (contato) de um fornecedor."""

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="representatives",
        verbose_name="Fornecedor",
    )
    name = models.CharField("Nome", max_length=200)
    email = models.EmailField("E-mail", blank=True)
    phone_primary = models.CharField("Telefone principal", max_length=20, blank=True)
    phone_secondary = models.CharField(
        "Telefone alternativo", max_length=20, blank=True
    )

    class Meta:
        verbose_name = "Representante"
        verbose_name_plural = "Representantes"
        ordering = ["name"]

    def __str__(self):
        return self.name


class InboundInvoice(models.Model):
    """Nota Fiscal de Entrada (NF): recebimento de mercadorias de um fornecedor.

    Registra o cabeçalho da nota (número, datas, fornecedor e os valores
    monetários totais, digitados manualmente conforme o documento físico). As
    Faturas/Duplicatas (``InvoiceDuplicate``) e os Produtos (``InvoiceItem``)
    são filhos ``CASCADE``, gerenciados apenas dentro da NF. Todos os valores
    ficam em centavos (inteiro); cada um expõe uma ``@property`` em reais.
    """

    number = models.CharField("Número da nota", max_length=64)
    issue_date = models.DateField("Data de emissão", null=True, blank=True)
    delivery_date = models.DateField("Data de entrega", null=True, blank=True)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name="Fornecedor",
    )
    products_total_cents = models.PositiveIntegerField(
        "Valor total dos produtos (centavos)", default=0
    )
    total_cents = models.PositiveIntegerField("Valor total (centavos)", default=0)
    icms_base_cents = models.PositiveIntegerField(
        "Base de cálculo do ICMS (centavos)", default=0
    )
    icms_cents = models.PositiveIntegerField("Valor do ICMS (centavos)", default=0)
    ipi_cents = models.PositiveIntegerField("Valor do IPI (centavos)", default=0)
    taxes_total_cents = models.PositiveIntegerField(
        "Valor total dos tributos (centavos)", default=0
    )
    freight_cents = models.PositiveIntegerField("Valor do frete (centavos)", default=0)
    insurance_cents = models.PositiveIntegerField(
        "Valor do seguro (centavos)", default=0
    )
    discount_cents = models.PositiveIntegerField(
        "Valor do desconto (centavos)", default=0
    )
    other_costs_cents = models.PositiveIntegerField(
        "Outras despesas acessórias (centavos)", default=0
    )
    created_at = models.DateTimeField("Criada em", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Nota fiscal de entrada"
        verbose_name_plural = "Notas fiscais de entrada"
        ordering = ["-id"]

    def __str__(self):
        return f"NF {self.number}"

    @property
    def products_total(self):
        """Valor total dos produtos em reais (somente leitura)."""
        return self.products_total_cents / 100

    @property
    def total(self):
        """Valor total da nota em reais (somente leitura)."""
        return self.total_cents / 100

    @property
    def icms_base(self):
        """Base de cálculo do ICMS em reais (somente leitura)."""
        return self.icms_base_cents / 100

    @property
    def icms(self):
        """Valor do ICMS em reais (somente leitura)."""
        return self.icms_cents / 100

    @property
    def ipi(self):
        """Valor do IPI em reais (somente leitura)."""
        return self.ipi_cents / 100

    @property
    def taxes_total(self):
        """Valor total dos tributos em reais (somente leitura)."""
        return self.taxes_total_cents / 100

    @property
    def freight(self):
        """Valor do frete em reais (somente leitura)."""
        return self.freight_cents / 100

    @property
    def insurance(self):
        """Valor do seguro em reais (somente leitura)."""
        return self.insurance_cents / 100

    @property
    def discount(self):
        """Valor do desconto em reais (somente leitura)."""
        return self.discount_cents / 100

    @property
    def other_costs(self):
        """Outras despesas acessórias em reais (somente leitura)."""
        return self.other_costs_cents / 100


class InvoiceDuplicate(models.Model):
    """Fatura/Duplicata de uma NF de entrada (título a pagar)."""

    invoice = models.ForeignKey(
        InboundInvoice,
        on_delete=models.CASCADE,
        related_name="duplicates",
        verbose_name="Nota fiscal",
    )
    due_date = models.DateField("Vencimento")
    value_cents = models.PositiveIntegerField("Valor (centavos)", default=0)

    class Meta:
        verbose_name = "Fatura"
        verbose_name_plural = "Faturas"
        ordering = ["due_date", "id"]

    def __str__(self):
        return f"Fatura NF {self.invoice.number} — venc. {self.due_date}"

    @property
    def value(self):
        """Valor da fatura em reais (somente leitura)."""
        return self.value_cents / 100


class InvoiceItem(models.Model):
    """Produto listado numa NF de entrada.

    Reaproveita o enum ``UnitType`` dos produtos. A quantidade é ``Decimal``
    (suporta unidades fracionadas, ex.: kg/l). Os valores ficam em centavos.
    """

    invoice = models.ForeignKey(
        InboundInvoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Nota fiscal",
    )
    code = models.CharField("Código do produto", max_length=64)
    description = models.CharField("Descrição do produto", max_length=200)
    unit_type = models.CharField(
        "Tipo de unidade",
        max_length=4,
        choices=UnitType.choices,
        default=UnitType.UNID,
    )
    quantity = models.DecimalField(
        "Quantidade", max_digits=12, decimal_places=3, default=0
    )
    unit_price_cents = models.PositiveIntegerField(
        "Valor unitário (centavos)", default=0
    )
    total_cents = models.PositiveIntegerField("Valor total (centavos)", default=0)
    icms_base_cents = models.PositiveIntegerField(
        "Base de cálculo do ICMS (centavos)", default=0
    )
    icms_cents = models.PositiveIntegerField("Valor ICMS (centavos)", default=0)
    ipi_cents = models.PositiveIntegerField("Valor IPI (centavos)", default=0)

    class Meta:
        verbose_name = "Produto da nota"
        verbose_name_plural = "Produtos da nota"
        ordering = ["id"]

    def __str__(self):
        return f"{self.code} — {self.description}"

    @property
    def unit_price(self):
        """Valor unitário em reais (somente leitura)."""
        return self.unit_price_cents / 100

    @property
    def total(self):
        """Valor total do item em reais (somente leitura)."""
        return self.total_cents / 100

    @property
    def icms_base(self):
        """Base de cálculo do ICMS em reais (somente leitura)."""
        return self.icms_base_cents / 100

    @property
    def icms(self):
        """Valor do ICMS em reais (somente leitura)."""
        return self.icms_cents / 100

    @property
    def ipi(self):
        """Valor do IPI em reais (somente leitura)."""
        return self.ipi_cents / 100
