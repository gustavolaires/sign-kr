"""Busca textual insensível a maiúsculas/minúsculas **e a acentos**.

O SQLite (banco da app desktop) só dobra maiúsculas de caracteres ASCII no
``LIKE``/``icontains``: "jose" casa com "JOSE", mas "joão" não casa com "JOÃO"
nem "AÇÃO" com "ação". Para nomes em PT-BR isso faz os filtros parecerem
sensíveis a maiúsculas.

Registramos uma função SQLite determinística ``unaccent_lower`` (ver
``SignConfig.ready``) que remove acentos e passa para minúsculas; o
:class:`UnaccentLower` expõe essa função ao ORM. :func:`filter_unaccent`
aplica a normalização nos dois lados da comparação.
"""

import unicodedata

from django.db.models import Func, TextField


def unaccent_lower(value):
    """Remove acentos e converte para minúsculas (usado no Python e no SQLite)."""
    if value is None:
        return None
    decomposed = unicodedata.normalize("NFKD", str(value))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()


class UnaccentLower(Func):
    """Aplica ``unaccent_lower`` a uma expressão do ORM (backend SQLite)."""

    function = "unaccent_lower"
    arity = 1
    output_field = TextField()


def filter_unaccent(queryset, field, term):
    """Filtra ``queryset`` por ``field`` contendo ``term``, ignorando caixa e acentos.

    Normaliza o campo (no banco) e o termo (no Python) antes de comparar, de modo
    que "JOÃO" case com "joão" e "ação" com "AÇÃO".
    """
    normalized = f"{field}__unaccented"
    return queryset.annotate(**{normalized: UnaccentLower(field)}).filter(
        **{f"{normalized}__contains": unaccent_lower(term)}
    )
