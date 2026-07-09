from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone

from .models import (
    Company,
    Expense,
    ExpenseInstallment,
    Manufacturer,
    Product,
    ProductSnapshot,
    Sale,
    SaleItem,
)
from .services import dashboard_metrics


def _make_sale(total_cents, when):
    """Cria uma venda e força ``created_at`` (contorna ``auto_now_add``)."""
    sale = Sale.objects.create(total_cents=total_cents)
    aware = timezone.make_aware(when) if timezone.is_naive(when) else when
    Sale.objects.filter(pk=sale.pk).update(created_at=aware)
    return Sale.objects.get(pk=sale.pk)


class DashboardMetricsGoalsTests(TestCase):
    """Fórmulas de meta semanal/mensal."""

    def setUp(self):
        self.company = Company.get_solo()
        self.company.daily_sales_goal_cents = 20000  # R$ 200,00/dia
        self.company.operating_days_per_week = 6
        self.company.save()

    def test_weekly_and_monthly_goal(self):
        # Julho/2026 tem 31 dias: fator mensal = 31 - (31 % 7) * (7 - 6) = 28.
        metrics = dashboard_metrics(company=self.company, today=date(2026, 7, 15))
        self.assertEqual(metrics["goals"]["weekly"], 1200.0)  # 6 * 200
        self.assertEqual(metrics["goals"]["monthly"], 5600.0)  # 28 * 200

    def test_monthly_goal_fewer_operating_days(self):
        # operating=0 → fator = 31 - (31 % 7) * 7 = 31 - 21 = 10 (nunca negativo).
        self.company.operating_days_per_week = 0
        self.company.save()
        metrics = dashboard_metrics(company=self.company, today=date(2026, 7, 15))
        self.assertEqual(metrics["goals"]["weekly"], 0.0)
        self.assertEqual(metrics["goals"]["monthly"], 2000.0)  # 10 * 200


class DashboardMetricsSalesWindowTests(TestCase):
    """Janelas de data das vendas (semana = segunda a domingo)."""

    def test_today_late_sale_stays_in_today(self):
        today = date(2026, 7, 8)  # quarta-feira
        _make_sale(10000, datetime(2026, 7, 8, 23, 0))  # hoje 23h
        _make_sale(5000, datetime(2026, 7, 1, 12, 0))  # mês atual, semana anterior
        _make_sale(9900, datetime(2026, 6, 30, 12, 0))  # mês anterior

        metrics = dashboard_metrics(company=Company.get_solo(), today=today)
        # Hoje: só a venda das 23h.
        self.assertEqual(metrics["sales"]["today"]["count"], 1)
        self.assertEqual(metrics["sales"]["today"]["revenue"], 100.0)
        # Semana (06→12 jul): só a venda de hoje.
        self.assertEqual(metrics["sales"]["week"]["count"], 1)
        # Mês (julho): as duas de julho.
        self.assertEqual(metrics["sales"]["month"]["count"], 2)
        self.assertEqual(metrics["sales"]["month"]["revenue"], 150.0)
        # Total: as três.
        self.assertEqual(metrics["sales"]["total"]["count"], 3)


class DashboardMetricsExpensesTests(TestCase):
    """Despesas do mês separadas por saldo (pagas + não pagas = a pagar)."""

    def test_paid_and_unpaid_by_balance(self):
        today = date(2026, 7, 15)
        rec = Expense.objects.create(name="Aluguel", recurrent=True)
        iso = Expense.objects.create(name="Compra", recurrent=False)
        # Recorrente do mês, quitada (100 devido, 100 pago).
        ExpenseInstallment.objects.create(
            expense=rec, value_cents=10000, paid_value_cents=10000,
            due_date=date(2026, 7, 10),
        )
        # Isolada do mês, parcial (50 devido, 20 pago).
        ExpenseInstallment.objects.create(
            expense=iso, value_cents=5000, paid_value_cents=2000,
            due_date=date(2026, 7, 20),
        )
        # Parcela fora do mês (não deve contar).
        ExpenseInstallment.objects.create(
            expense=iso, value_cents=9900, paid_value_cents=0,
            due_date=date(2026, 8, 5),
        )

        m = dashboard_metrics(company=Company.get_solo(), today=today)["expenses"]
        self.assertEqual(m["due"], 150.0)  # 100 + 50
        self.assertEqual(m["paid"], 120.0)  # 100 + 20 (por saldo)
        self.assertEqual(m["unpaid"], 30.0)  # 150 - 120
        self.assertEqual(m["paid"] + m["unpaid"], m["due"])  # invariante
        self.assertEqual(m["recurrent"], 100.0)
        self.assertEqual(m["isolated"], 50.0)


class DashboardMetricsProductsTests(TestCase):
    """Contagens de estoque e doughnut de saúde (buckets exclusivos)."""

    def test_stock_counts_and_buckets(self):
        maker = Manufacturer.objects.create(name="ACME")
        # Estoque baixo/zerado usam o min_stock do próprio produto e só ativos.
        Product.objects.create(
            name="A", manufacturer=maker, quantity=100, min_stock=10
        )  # ok
        Product.objects.create(
            name="B", manufacturer=maker, quantity=3, min_stock=5
        )  # baixo
        Product.objects.create(
            name="C", manufacturer=maker, quantity=0, min_stock=5
        )  # zerado (e baixo)
        Product.objects.create(
            name="D", manufacturer=maker, quantity=0, min_stock=5, is_active=False
        )  # inativo — não conta

        result = dashboard_metrics(
            company=Company.get_solo(), today=date(2026, 7, 15)
        )
        p = result["products"]
        self.assertEqual(p["total"], 4)  # todos os cadastrados
        self.assertEqual(p["active"], 3)
        self.assertAlmostEqual(p["active_pct"], 75.0, places=1)
        self.assertEqual(p["low"], 2)  # B e C (quantidade <= min_stock)
        self.assertEqual(p["zero"], 1)  # só C (D é inativo)
        self.assertAlmostEqual(p["low_pct"], 66.7, places=1)  # % dos ativos
        self.assertAlmostEqual(p["zero_pct"], 33.3, places=1)
        # Doughnut com buckets exclusivos (somam o total de ativos).
        stock = result["chart_data"]["stock"]
        self.assertEqual(stock, {"ok": 1, "low": 1, "zero": 1})


class DashboardMetricsGuardTests(TestCase):
    """Guardas de divisão por zero (banco vazio / meta 0)."""

    def test_empty_database(self):
        m = dashboard_metrics(company=Company.get_solo(), today=date(2026, 7, 15))
        self.assertIsNone(m["goals"]["weekly_pct"])  # meta 0
        self.assertIsNone(m["goals"]["monthly_pct"])
        self.assertEqual(m["products"]["low_pct"], 0.0)  # sem produtos
        self.assertEqual(m["expenses"]["due"], 0.0)  # sem despesas
        self.assertEqual(m["sales"]["total"]["revenue"], 0.0)
