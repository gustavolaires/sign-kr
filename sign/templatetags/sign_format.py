"""Filtros de formatação puramente visual (CPF/CNPJ, telefone, CEP).

Os valores são armazenados no banco apenas com dígitos; estes filtros aplicam
a máscara somente na exibição. Se o número de dígitos não bater com um formato
conhecido, o valor original é retornado sem alteração.
"""

from django import template

register = template.Library()


def _only_digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


@register.filter(name="cpf_cnpj")
def cpf_cnpj(value):
    d = _only_digits(value)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return value


@register.filter(name="phone")
def phone(value):
    d = _only_digits(value)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return value


@register.filter(name="cep")
def cep(value):
    d = _only_digits(value)
    if len(d) == 8:
        return f"{d[:5]}-{d[5:]}"
    return value


@register.filter(name="centavos")
def centavos(value):
    """Converte centavos (inteiro) em reais (para usar com ``floatformat:2``)."""
    try:
        return (value or 0) / 100
    except (TypeError, ValueError):
        return 0
