"""Middlewares do app ``sign``."""

from django.utils import timezone

from .models import Company


class ActiveTimezoneMiddleware:
    """Ativa, por requisição, o fuso configurado na empresa (singleton).

    Os dados continuam gravados em UTC (``USE_TZ=True``); ativar o fuso faz
    ``timezone.localdate()``, as janelas do dashboard/relatórios (via
    ``created_at_range``), o cálculo de atraso das parcelas e a exibição de
    datetimes nos templates refletirem o horário local configurado.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        company = Company.get_solo()
        # Reaproveitado pelo context processor ``company`` (evita 2ª consulta).
        request.company = company
        timezone.activate(company.tzinfo)
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
