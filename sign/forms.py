from decimal import Decimal, ROUND_HALF_UP

from django import forms

from .models import Manufacturer, Product

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
