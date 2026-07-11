"""Primitivos monetários compartilhados do pacote de services.

Concentra a conversão reais ↔ centavos (com ``Decimal``/``ROUND_HALF_UP``,
nunca float) e o parsing de texto em reais. É o módulo-base: não depende de
nenhum outro módulo do pacote.
"""

from decimal import Decimal, ROUND_HALF_UP


def reais_to_cents(value):
    """Converte um ``Decimal`` em reais para centavos (inteiro), arredondando.

    Mesma fórmula usada em ``ProductForm.save`` (HALF_UP, sem float).
    """
    value = Decimal(value)
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cents_to_reais(cents):
    """Converte centavos (inteiro) para reais (float) só na borda de exibição."""
    return (cents or 0) / 100


def _parse_reais(value):
    """Converte um preço em reais (texto do CSV) para ``Decimal``.

    Aceita vírgula ou ponto decimal, separador de milhar e o símbolo ``R$``
    (ex.: ``"1.234,56"``, ``"1234.56"``, ``"R$ 12,34"``). Vazio → ``0``.
    Levanta ``ValueError`` se não for um número reconhecível.
    """
    text = (value or "").strip().replace("R$", "").replace(" ", "")
    if not text:
        return Decimal("0")
    if "," in text:
        # Formato brasileiro: '.' é separador de milhar, ',' é o decimal.
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except ArithmeticError as exc:
        raise ValueError(str(exc))
