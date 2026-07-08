from django.views.generic import TemplateView

from .. import services


class DashboardView(TemplateView):
    """Página de indicadores (Vendas, Produtos, Despesas).

    Toda a matemática fica no serviço ``dashboard_metrics``; a view apenas
    injeta o resultado no contexto. Os dados dos gráficos são serializados no
    template via ``json_script`` para o ``dashboard.js``.
    """

    template_name = "sign/dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(services.dashboard_metrics())
        return context
