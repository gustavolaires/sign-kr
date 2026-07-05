from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse
from django.views.generic import UpdateView

from ..forms import CompanyForm
from ..models import Company


class CompanySettingsView(SuccessMessageMixin, UpdateView):
    """Edição dos dados da empresa (singleton, sem ``pk`` na URL)."""

    form_class = CompanyForm
    template_name = "sign/company/form.html"
    success_message = "Configurações da empresa salvas com sucesso."

    def get_object(self, queryset=None):
        return Company.get_solo()

    def get_success_url(self):
        return reverse("sign:company_settings")
