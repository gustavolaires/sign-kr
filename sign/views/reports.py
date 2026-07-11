"""Views da geração de relatórios (configuração + tela de impressão).

``report_index`` renderiza a tela de configuração (seleção de relatório +
filtros dinâmicos). ``report_render`` lê os filtros do GET, delega o cálculo à
camada de serviço (``build_report``) e renderiza a tela standalone imprimível.
"""

from django.contrib import messages
from django.shortcuts import redirect, render

from ..services import (
    REPORT_SPECS,
    _current_month_range,
    _last_12_months_range,
    _prev_month_range,
    build_report,
)
from django.core.exceptions import ValidationError
from django.utils import timezone

# Orientações de página aceitas na impressão A4 (fallback: retrato).
ORIENTATIONS = {"portrait", "landscape"}
DEFAULT_ORIENTATION = "portrait"


def _default_periods(today):
    """Datas default (YYYY-MM-DD) por janela, para o JS pré-preencher os inputs."""
    windows = {
        "prev_month": _prev_month_range(today),
        "current_month": _current_month_range(today),
        "last_12_months": _last_12_months_range(today),
    }
    return {
        kind: {"from": start.isoformat(), "to": end.isoformat()}
        for kind, (start, end) in windows.items()
    }


def report_index(request):
    """Tela de configuração: escolhe o relatório e ajusta os filtros."""
    report_meta = {
        spec["key"]: {"period": spec["period"] or "", "cutoff": spec["cutoff"] or ""}
        for spec in REPORT_SPECS
    }
    return render(
        request,
        "sign/reports/index.html",
        {
            "report_specs": REPORT_SPECS,
            "report_meta": report_meta,
            "default_periods": _default_periods(timezone.localdate()),
        },
    )


def report_render(request):
    """Tela standalone imprimível (A4) do relatório escolhido."""
    report_type = request.GET.get("type", "").strip()
    try:
        report = build_report(report_type=report_type, params=request.GET)
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return redirect("sign:report_index")

    orientation = request.GET.get("orientation", DEFAULT_ORIENTATION)
    if orientation not in ORIENTATIONS:
        orientation = DEFAULT_ORIENTATION

    # Querystring sem "orientation" — base para os links de troca de orientação.
    params = request.GET.copy()
    params.pop("orientation", None)

    context = dict(report)
    context["orientation"] = orientation
    context["base_query"] = params.urlencode()
    context["generated_at"] = timezone.localtime()
    return render(request, "sign/reports/report.html", context)
