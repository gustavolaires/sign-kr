from decimal import Decimal, ROUND_HALF_UP

from django import forms

from .models import Client, Manufacturer, Product

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
