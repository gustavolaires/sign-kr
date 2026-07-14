"""Janelas de data para filtro de ``DateTimeField`` pelo índice.

No SQLite (banco da app desktop), filtrar ``created_at__date`` sobre um
``DateTimeField`` traduz para ``django_datetime_cast_date(created_at, …)`` — uma
função Python registrada, chamada **linha a linha**, que envolve a coluna e
**anula o índice** de ``created_at``. Filtrar por um intervalo half-open de
``datetime`` (``created_at__gte`` / ``created_at__lt``) é uma comparação direta
que usa o índice e não invoca callback por linha.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone


def created_at_range(start_date, end_date):
    """Intervalo half-open ``[início, fim)`` cobrindo os dias ``start_date`` a
    ``end_date`` (ambos inclusive), como ``datetime`` *aware*.

    Equivale a ``created_at__date`` entre ``start_date`` e ``end_date`` (mesma
    semântica sob ``USE_TZ=True``), mas filtrável por ``created_at__gte=início``
    **e** ``created_at__lt=fim``. ``make_aware`` usa a tz corrente (``TIME_ZONE``);
    ``00:00`` nunca é ambíguo/inexistente em UTC (sem DST).
    """
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(
        datetime.combine(end_date + timedelta(days=1), time.min)
    )
    return start_dt, end_dt
