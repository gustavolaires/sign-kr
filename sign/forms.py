from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.utils import timezone

from .models import (
    Client,
    Company,
    Expense,
    ExpenseInstallment,
    InboundInvoice,
    InvoiceDuplicate,
    InvoiceItem,
    Manufacturer,
    Product,
    Representative,
    Sale,
    Supplier,
)
from .services import reais_to_cents

# Classe base aplicada aos inputs para padronizar o estilo Tailwind.
INPUT_CLASSES = (
    "w-full rounded-lg border border-gray-300 px-3 py-2 text-gray-900 "
    "shadow-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 "
    "focus:outline-none"
)


class StyledModelForm(forms.ModelForm):
    """ModelForm que aplica classes Tailwind a todos os widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                continue
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {INPUT_CLASSES}".strip()


class ProductForm(StyledModelForm):
    # Campo exibido/digitado em reais; convertido de/para centavos no backend.
    unit_price = forms.DecimalField(
        label="Preço unitário (R$)",
        max_digits=12,
        decimal_places=2,
        min_value=0,
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "description",
            "barcode",
            "manufacturer",
            "manufacturer_code",
            "quantity",
            "unit_type",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "quantity": forms.NumberInput(attrs={"step": "1", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No <select> de tipo de unidade, exibe a sigla (valor) em vez do
        # nome completo; o blank inicial, se houver, é preservado.
        self.fields["unit_type"].choices = [
            (value, value if value else label)
            for value, label in self.fields["unit_type"].choices
        ]
        # Ao editar, preenche o campo em reais a partir dos centavos armazenados.
        if self.instance and self.instance.pk:
            self.fields["unit_price"].initial = (
                Decimal(self.instance.unit_price_cents) / 100
            )

    def save(self, commit=True):
        product = super().save(commit=False)
        reais = self.cleaned_data["unit_price"]
        product.unit_price_cents = int(
            (reais * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        if commit:
            product.save()
        return product


class ManufacturerForm(StyledModelForm):
    class Meta:
        model = Manufacturer
        fields = ["name"]


class SaleForm(StyledModelForm):
    """Campos simples da venda (cliente e observações).

    Desconto e pagamentos são dinâmicos e ficam fora do form; são parseados do
    POST e validados na camada de serviço (``sign.services.create_sale``).
    """

    class Meta:
        model = Sale
        fields = ["client", "obs", "discount_obs"]
        widgets = {
            "obs": forms.Textarea(attrs={"rows": 3}),
            "discount_obs": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Cliente é opcional (venda avulsa); rótulo do option vazio em PT-BR.
        self.fields["client"].required = False
        self.fields["client"].empty_label = "Sem cliente (venda avulsa)"


def _only_digits(value):
    """Mantém apenas os dígitos de uma string (descarta a formatação visual)."""
    return "".join(ch for ch in (value or "") if ch.isdigit())


class ClientForm(StyledModelForm):
    class Meta:
        model = Client
        fields = [
            "name",
            "person_type",
            "service_provider",
            "cpf_cnpj",
            "birth_date",
            "email",
            "phone_primary",
            "phone_primary_is_whatsapp",
            "phone_secondary",
            "phone_secondary_is_whatsapp",
            "street",
            "number",
            "complement",
            "district",
            "city",
            "state",
            "postal_code",
        ]
        widgets = {
            # Date picker nativo do HTML5; formato fixo para preencher o valor na edição.
            "birth_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            # Máscaras aplicadas só visualmente no front (ver static/sign/js/masks.js).
            # O `clean_*` correspondente grava apenas os dígitos no banco.
            "cpf_cnpj": forms.TextInput(
                attrs={"data-mask": "cpf-cnpj", "inputmode": "numeric", "maxlength": "18"}
            ),
            "phone_primary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
            "phone_secondary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
            "postal_code": forms.TextInput(
                attrs={"data-mask": "cep", "inputmode": "numeric", "maxlength": "9"}
            ),
        }

    # Grava sem formatação: tira a máscara e persiste apenas os dígitos.
    def clean_cpf_cnpj(self):
        return _only_digits(self.cleaned_data.get("cpf_cnpj"))

    def clean_phone_primary(self):
        return _only_digits(self.cleaned_data.get("phone_primary"))

    def clean_phone_secondary(self):
        return _only_digits(self.cleaned_data.get("phone_secondary"))

    def clean_postal_code(self):
        return _only_digits(self.cleaned_data.get("postal_code"))


class CompanyForm(StyledModelForm):
    class Meta:
        model = Company
        fields = [
            "name",
            "legal_name",
            "cnpj",
            "email",
            "phone_primary",
            "phone_secondary",
            "street",
            "number",
            "complement",
            "district",
            "city",
            "state",
            "postal_code",
        ]
        widgets = {
            # Máscaras aplicadas só visualmente no front (ver static/sign/js/masks.js).
            # O `clean_*` correspondente grava apenas os dígitos no banco.
            "cnpj": forms.TextInput(
                attrs={"data-mask": "cpf-cnpj", "inputmode": "numeric", "maxlength": "18"}
            ),
            "phone_primary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
            "phone_secondary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
            "postal_code": forms.TextInput(
                attrs={"data-mask": "cep", "inputmode": "numeric", "maxlength": "9"}
            ),
        }

    # Grava sem formatação: tira a máscara e persiste apenas os dígitos.
    def clean_cnpj(self):
        return _only_digits(self.cleaned_data.get("cnpj"))

    def clean_phone_primary(self):
        return _only_digits(self.cleaned_data.get("phone_primary"))

    def clean_phone_secondary(self):
        return _only_digits(self.cleaned_data.get("phone_secondary"))

    def clean_postal_code(self):
        return _only_digits(self.cleaned_data.get("postal_code"))


class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = [
            "name",
            "cnpj",
            "state_registration",
            "multiple_brands",
            "manufacturer",
            "email",
            "phone_primary",
            "phone_secondary",
        ]
        widgets = {
            # Máscaras aplicadas só visualmente no front (ver static/sign/js/masks.js).
            # O `clean_*` correspondente grava apenas os dígitos no banco.
            # `state_registration` é texto livre (pode ser "ISENTO"), sem máscara.
            "cnpj": forms.TextInput(
                attrs={"data-mask": "cpf-cnpj", "inputmode": "numeric", "maxlength": "18"}
            ),
            "phone_primary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
            "phone_secondary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["manufacturer"].empty_label = "Selecione uma marca"

    # Grava sem formatação: tira a máscara e persiste apenas os dígitos.
    def clean_cnpj(self):
        return _only_digits(self.cleaned_data.get("cnpj"))

    def clean_phone_primary(self):
        return _only_digits(self.cleaned_data.get("phone_primary"))

    def clean_phone_secondary(self):
        return _only_digits(self.cleaned_data.get("phone_secondary"))

    def clean(self):
        cleaned = super().clean()
        # Se trabalha com múltiplas marcas, a marca específica não se aplica.
        if cleaned.get("multiple_brands"):
            cleaned["manufacturer"] = None
        return cleaned


class RepresentativeForm(StyledModelForm):
    class Meta:
        model = Representative
        fields = ["name", "email", "phone_primary", "phone_secondary"]
        widgets = {
            "phone_primary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
            "phone_secondary": forms.TextInput(
                attrs={"data-mask": "phone", "inputmode": "numeric", "maxlength": "15"}
            ),
        }

    def clean_phone_primary(self):
        return _only_digits(self.cleaned_data.get("phone_primary"))

    def clean_phone_secondary(self):
        return _only_digits(self.cleaned_data.get("phone_secondary"))


class ExpenseForm(StyledModelForm):
    """Cadastro de despesa: definição + parâmetros de geração das parcelas.

    Os campos de geração (``value``, ``installment_total``, ``first_due_date``,
    ``months_ahead``) não pertencem ao model; são consumidos pela view via
    ``services.create_expense``. A validação por modo (recorrente vs isolada)
    fica no ``clean()``.
    """

    value = forms.DecimalField(
        label="Valor da parcela (R$)", max_digits=12, decimal_places=2, min_value=0
    )
    installment_total = forms.IntegerField(
        label="Número de parcelas", min_value=1, initial=1, required=False
    )
    first_due_date = forms.DateField(
        label="Data do 1º vencimento",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    months_ahead = forms.IntegerField(
        label="Gerar parcelas (meses)", min_value=1, initial=12, required=False
    )

    class Meta:
        model = Expense
        fields = ["name", "description", "recurrent", "scheduled_for"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "scheduled_for": forms.NumberInput(
                attrs={"min": "1", "max": "31", "step": "1"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 1º vencimento já vem preenchido com a data de hoje.
        self.fields["first_due_date"].initial = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("recurrent"):
            if not cleaned.get("scheduled_for"):
                self.add_error(
                    "scheduled_for", "Obrigatório para despesa recorrente."
                )
            if not cleaned.get("months_ahead"):
                self.add_error("months_ahead", "Informe o horizonte em meses.")
        else:
            if not cleaned.get("first_due_date"):
                self.add_error(
                    "first_due_date", "Informe a data do primeiro vencimento."
                )
            if not cleaned.get("installment_total"):
                self.add_error(
                    "installment_total", "Informe o número de parcelas."
                )
        return cleaned


class ExpenseUpdateForm(StyledModelForm):
    """Edição apenas da definição da despesa (as parcelas são editadas à parte)."""

    class Meta:
        model = Expense
        fields = ["name", "description", "recurrent", "scheduled_for"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "scheduled_for": forms.NumberInput(
                attrs={"min": "1", "max": "31", "step": "1"}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("recurrent") and not cleaned.get("scheduled_for"):
            self.add_error("scheduled_for", "Obrigatório para despesa recorrente.")
        return cleaned


class ExpenseInstallmentForm(StyledModelForm):
    """Edição/criação de uma parcela isolada (valor variável e vencimento)."""

    value = forms.DecimalField(
        label="Valor (R$)", max_digits=12, decimal_places=2, min_value=0
    )

    class Meta:
        model = ExpenseInstallment
        fields = ["installment_current", "installment_total", "due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["value"].initial = Decimal(self.instance.value_cents) / 100

    def save(self, commit=True):
        installment = super().save(commit=False)
        installment.value_cents = reais_to_cents(self.cleaned_data["value"])
        if commit:
            installment.save()
        return installment


class InstallmentPaymentForm(forms.Form):
    """Registro de pagamento de uma parcela (valor pago + data)."""

    paid_value = forms.DecimalField(
        label="Valor pago (R$)", max_digits=12, decimal_places=2, min_value=0
    )
    paid_at = forms.DateField(
        label="Data de pagamento",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Form simples (não-ModelForm): aplica a estilização Tailwind manualmente.
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {INPUT_CLASSES}".strip()


def _reais_field(label, required=False):
    """DecimalField em reais (2 casas), usado nos forms como campo virtual."""
    return forms.DecimalField(
        label=label,
        max_digits=12,
        decimal_places=2,
        min_value=0,
        required=required,
    )


class InboundInvoiceForm(StyledModelForm):
    """Cabeçalho da NF de entrada. Os valores em reais são campos virtuais.

    No **create**, a persistência (com faturas/produtos inline) é feita pela
    view via ``services.create_inbound_invoice``; no **update**, o ``save()``
    converte os reais para centavos e grava o cabeçalho.
    """

    # Mapa campo-virtual (reais) → campo do model (centavos).
    MONEY_FIELDS = {
        "products_total": "products_total_cents",
        "total": "total_cents",
        "icms_base": "icms_base_cents",
        "icms": "icms_cents",
        "ipi": "ipi_cents",
        "taxes_total": "taxes_total_cents",
        "freight": "freight_cents",
        "insurance": "insurance_cents",
        "discount": "discount_cents",
        "other_costs": "other_costs_cents",
    }

    products_total = _reais_field("Valor total dos produtos (R$)")
    total = _reais_field("Valor total (R$)", required=True)
    icms_base = _reais_field("Base de cálculo do ICMS (R$)")
    icms = _reais_field("Valor do ICMS (R$)")
    ipi = _reais_field("Valor do IPI (R$)")
    taxes_total = _reais_field("Valor total dos tributos (R$)")
    freight = _reais_field("Valor do frete (R$)")
    insurance = _reais_field("Valor do seguro (R$)")
    discount = _reais_field("Valor do desconto (R$)")
    other_costs = _reais_field("Outras despesas acessórias (R$)")

    class Meta:
        model = InboundInvoice
        fields = ["number", "issue_date", "delivery_date", "supplier"]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "delivery_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].empty_label = "Selecione o fornecedor"
        # Ao editar, preenche os campos em reais a partir dos centavos gravados.
        if self.instance and self.instance.pk:
            for reais_field, cents_field in self.MONEY_FIELDS.items():
                self.fields[reais_field].initial = (
                    Decimal(getattr(self.instance, cents_field)) / 100
                )

    def save(self, commit=True):
        invoice = super().save(commit=False)
        for reais_field, cents_field in self.MONEY_FIELDS.items():
            setattr(
                invoice,
                cents_field,
                reais_to_cents(self.cleaned_data.get(reais_field) or 0),
            )
        if commit:
            invoice.save()
        return invoice


class InvoiceDuplicateForm(StyledModelForm):
    """Criação/edição de uma fatura (duplicata) de NF, em página separada."""

    value = forms.DecimalField(
        label="Valor da fatura (R$)", max_digits=12, decimal_places=2, min_value=0
    )

    class Meta:
        model = InvoiceDuplicate
        fields = ["due_date"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["value"].initial = Decimal(self.instance.value_cents) / 100

    def save(self, commit=True):
        duplicate = super().save(commit=False)
        duplicate.value_cents = reais_to_cents(self.cleaned_data["value"])
        if commit:
            duplicate.save()
        return duplicate


class InvoiceItemForm(StyledModelForm):
    """Criação/edição de um produto de NF, em página separada."""

    MONEY_FIELDS = {
        "unit_price": "unit_price_cents",
        "total": "total_cents",
        "icms_base": "icms_base_cents",
        "icms": "icms_cents",
        "ipi": "ipi_cents",
    }

    unit_price = _reais_field("Valor unitário (R$)", required=True)
    total = _reais_field("Valor total (R$)")
    icms_base = _reais_field("Base de cálculo do ICMS (R$)")
    icms = _reais_field("Valor ICMS (R$)")
    ipi = _reais_field("Valor IPI (R$)")

    class Meta:
        model = InvoiceItem
        fields = ["code", "description", "unit_type", "quantity"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"step": "any", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exibe a sigla (valor) no <select> de tipo de unidade, como no ProductForm.
        self.fields["unit_type"].choices = [
            (value, value if value else label)
            for value, label in self.fields["unit_type"].choices
        ]
        if self.instance and self.instance.pk:
            for reais_field, cents_field in self.MONEY_FIELDS.items():
                self.fields[reais_field].initial = (
                    Decimal(getattr(self.instance, cents_field)) / 100
                )

    def save(self, commit=True):
        item = super().save(commit=False)
        for reais_field, cents_field in self.MONEY_FIELDS.items():
            setattr(
                item,
                cents_field,
                reais_to_cents(self.cleaned_data.get(reais_field) or 0),
            )
        if commit:
            item.save()
        return item
