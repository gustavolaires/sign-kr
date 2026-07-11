from datetime import date, datetime

from django.test import TestCase
from django.utils import timezone

from django.core.exceptions import ValidationError

from .models import (
    Client,
    Company,
    Expense,
    ExpenseInstallment,
    Manufacturer,
    Product,
    ProductSnapshot,
    Sale,
    SaleItem,
)
from .services import build_report, dashboard_metrics


def _make_sale(total_cents, when, client=None):
    """Cria uma venda e força ``created_at`` (contorna ``auto_now_add``)."""
    sale = Sale.objects.create(total_cents=total_cents, client=client)
    aware = timezone.make_aware(when) if timezone.is_naive(when) else when
    Sale.objects.filter(pk=sale.pk).update(created_at=aware)
    return Sale.objects.get(pk=sale.pk)


def _add_item(sale, product, quantity):
    """Adiciona um item à venda usando o snapshot reaproveitável do produto."""
    snapshot = ProductSnapshot.get_or_create_for(product)
    return SaleItem.objects.create(
        sale=sale,
        product_snapshot=snapshot,
        quantity=quantity,
        unit_price_cents=product.unit_price_cents,
        total_cents=product.unit_price_cents * quantity,
    )


def _report_cell_map(report, row_index):
    """Mapa {coluna: valor} de uma linha do relatório (para asserções legíveis)."""
    return {
        col["key"]: cell["value"]
        for col, cell in zip(report["columns"], report["rows"][row_index])
    }


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


TODAY = date(2026, 7, 15)
JUNE = {"date_from": "2026-06-01", "date_to": "2026-06-30"}


class ReportProductsTests(TestCase):
    """Relatório de Produtos: ordem alfabética e colunas personalizáveis."""

    def setUp(self):
        self.maker = Manufacturer.objects.create(name="ACME")
        Product.objects.create(
            name="Zebra", manufacturer=self.maker, quantity=5, unit_price_cents=1000
        )
        Product.objects.create(
            name="Abacaxi", manufacturer=self.maker, quantity=3, unit_price_cents=250
        )

    def test_alphabetical_order_and_default_columns(self):
        report = build_report(report_type="products", params={}, today=TODAY)
        self.assertEqual(report["title"], "Produtos")
        # Ordem alfabética por nome.
        names = [_report_cell_map(report, i)["name"] for i in range(len(report["rows"]))]
        self.assertEqual(names, ["Abacaxi", "Zebra"])
        # Colunas default (sem descrição/tipo/estoque mín./ativo).
        keys = [c["key"] for c in report["columns"]]
        self.assertEqual(
            keys,
            ["barcode", "manufacturer_code", "name", "manufacturer",
             "quantity", "unit_price"],
        )
        # Preço convertido para reais.
        self.assertEqual(_report_cell_map(report, 0)["unit_price"], 2.5)

    def test_custom_columns(self):
        report = build_report(
            report_type="products",
            params={"col": ["name", "is_active"]},
            today=TODAY,
        )
        self.assertEqual([c["key"] for c in report["columns"]], ["name", "is_active"])


class ReportBestProductsTests(TestCase):
    """Ranking de produtos mais vendidos por unidades vendidas."""

    def setUp(self):
        self.maker = Manufacturer.objects.create(name="ACME")
        self.a = Product.objects.create(
            name="Alfa", manufacturer=self.maker, quantity=10, unit_price_cents=1000
        )
        self.b = Product.objects.create(
            name="Beta", manufacturer=self.maker, quantity=10, unit_price_cents=2000
        )
        # Junho (dentro do período default): A=5, B=2.
        s_june = _make_sale(0, datetime(2026, 6, 10, 12, 0))
        _add_item(s_june, self.a, 5)
        _add_item(s_june, self.b, 2)
        # Julho (fora do período): B=100.
        s_july = _make_sale(0, datetime(2026, 7, 5, 12, 0))
        _add_item(s_july, self.b, 100)

    def test_top_ranks_by_units_in_period(self):
        report = build_report(
            report_type="best_products",
            params={**JUNE, "cutoff_mode": "top", "cutoff_value": "1"},
            today=TODAY,
        )
        # TOP 1 no período de junho = Alfa (5 unidades).
        self.assertEqual(len(report["rows"]), 1)
        row = _report_cell_map(report, 0)
        self.assertEqual(row["name"], "Alfa")
        self.assertEqual(row["units"], 5)

    def test_cut_by_minimum_units(self):
        report = build_report(
            report_type="best_products",
            params={**JUNE, "cutoff_mode": "cut", "cutoff_value": "3"},
            today=TODAY,
        )
        names = [_report_cell_map(report, i)["name"] for i in range(len(report["rows"]))]
        self.assertEqual(names, ["Alfa"])  # só A tem >= 3 unidades em junho

    def test_all_sales_ignores_period(self):
        report = build_report(
            report_type="best_products",
            params={**JUNE, "all_sales": "1", "cutoff_value": "10"},
            today=TODAY,
        )
        rows = {r_map["name"]: r_map["units"] for r_map in
                (_report_cell_map(report, i) for i in range(len(report["rows"])))}
        self.assertEqual(rows, {"Alfa": 5, "Beta": 102})
        # Exibição em ordem alfabética.
        names = [_report_cell_map(report, i)["name"] for i in range(len(report["rows"]))]
        self.assertEqual(names, ["Alfa", "Beta"])


class ReportSalesTests(TestCase):
    """Relatório de Vendas: janela de data e lista de formas de pagamento."""

    def test_period_window_and_payments(self):
        from .models import SalePayment

        s = _make_sale(15000, datetime(2026, 6, 30, 23, 0))
        SalePayment.objects.create(sale=s, payment_type="pix", value_cents=5000)
        SalePayment.objects.create(sale=s, payment_type="cash", value_cents=10000)
        _make_sale(9900, datetime(2026, 7, 1, 12, 0))  # fora do período de junho

        report = build_report(report_type="sales", params=JUNE, today=TODAY)
        self.assertEqual(len(report["rows"]), 1)
        row = _report_cell_map(report, 0)
        self.assertEqual(row["total"], 150.0)
        # Formas de pagamento juntadas com rótulo PT-BR.
        self.assertIn("Pix", row["payments"])
        self.assertIn("Dinheiro", row["payments"])


class ReportSalesByPeriodTests(TestCase):
    """Totais por dia (só dias com venda) e por mês (preenche zeros)."""

    def test_by_day_only_days_with_sales(self):
        _make_sale(10000, datetime(2026, 6, 3, 12, 0))
        _make_sale(5000, datetime(2026, 6, 3, 15, 0))
        _make_sale(2000, datetime(2026, 6, 20, 9, 0))
        report = build_report(report_type="sales_by_day", params=JUNE, today=TODAY)
        self.assertEqual(len(report["rows"]), 2)  # só 03 e 20 de junho
        self.assertEqual(_report_cell_map(report, 0)["total"], 150.0)  # 100 + 50

    def test_by_month_fills_gaps(self):
        _make_sale(10000, datetime(2026, 5, 10, 12, 0))
        _make_sale(30000, datetime(2026, 7, 10, 12, 0))
        report = build_report(
            report_type="sales_by_month",
            params={"date_from": "2026-05-01", "date_to": "2026-07-31"},
            today=TODAY,
        )
        rows = [_report_cell_map(report, i) for i in range(len(report["rows"]))]
        self.assertEqual([r["month"] for r in rows], ["05/2026", "06/2026", "07/2026"])
        self.assertEqual([r["total"] for r in rows], [100.0, 0.0, 300.0])


class ReportBestClientsTests(TestCase):
    """Ranking de clientes por valor comprado (ignora venda avulsa)."""

    def setUp(self):
        self.c1 = Client.objects.create(name="Ana", cpf_cnpj="1")
        self.c2 = Client.objects.create(name="Bruno", cpf_cnpj="2")
        _make_sale(10000, datetime(2026, 6, 5, 12, 0), client=self.c1)
        _make_sale(20000, datetime(2026, 6, 6, 12, 0), client=self.c1)  # C1 total 300
        _make_sale(50000, datetime(2026, 6, 7, 12, 0), client=self.c2)  # C2 total 500
        _make_sale(99900, datetime(2026, 6, 8, 12, 0))  # avulsa: ignorada

    def test_top_sums_per_client_ignoring_avulsa(self):
        report = build_report(
            report_type="best_clients",
            params={**JUNE, "cutoff_mode": "top", "cutoff_value": "10"},
            today=TODAY,
        )
        rows = {r["name"]: r["total"] for r in
                (_report_cell_map(report, i) for i in range(len(report["rows"])))}
        self.assertEqual(rows, {"Ana": 300.0, "Bruno": 500.0})

    def test_cut_by_minimum_value(self):
        report = build_report(
            report_type="best_clients",
            params={**JUNE, "cutoff_mode": "cut", "cutoff_value": "400"},
            today=TODAY,
        )
        names = [_report_cell_map(report, i)["name"] for i in range(len(report["rows"]))]
        self.assertEqual(names, ["Bruno"])  # só C2 (R$ 500) >= R$ 400,00


class ReportExpensesTests(TestCase):
    """Despesas: filtro aberto/pago no ORM e mapeamento de tipo."""

    def setUp(self):
        self.rec = Expense.objects.create(name="Aluguel", recurrent=True)
        self.iso = Expense.objects.create(name="Compra", recurrent=False)
        # Quitada (pago >= devido).
        ExpenseInstallment.objects.create(
            expense=self.rec, value_cents=10000, paid_value_cents=10000,
            due_date=date(2026, 7, 10),
        )
        # Aberta (parcial).
        ExpenseInstallment.objects.create(
            expense=self.iso, value_cents=5000, paid_value_cents=2000,
            due_date=date(2026, 7, 20),
        )
        # Fora do mês (não conta).
        ExpenseInstallment.objects.create(
            expense=self.iso, value_cents=9900, paid_value_cents=0,
            due_date=date(2026, 8, 5),
        )

    def test_all_open_paid_and_type_mapping(self):
        all_r = build_report(report_type="expenses", params={}, today=TODAY)
        self.assertEqual(len(all_r["rows"]), 2)
        types = {_report_cell_map(all_r, i)["name"]: _report_cell_map(all_r, i)["type"]
                 for i in range(len(all_r["rows"]))}
        self.assertEqual(types, {"Aluguel": "Recorrente", "Compra": "Isolada"})

        open_r = build_report(report_type="expenses_open", params={}, today=TODAY)
        self.assertEqual(
            [_report_cell_map(open_r, i)["name"] for i in range(len(open_r["rows"]))],
            ["Compra"],
        )

        paid_r = build_report(report_type="expenses_paid", params={}, today=TODAY)
        self.assertEqual(
            [_report_cell_map(paid_r, i)["name"] for i in range(len(paid_r["rows"]))],
            ["Aluguel"],
        )


class ReportGuardTests(TestCase):
    """Guardas do dispatcher de relatórios."""

    def test_invalid_type_raises(self):
        with self.assertRaises(ValidationError):
            build_report(report_type="nope", params={}, today=TODAY)

    def test_default_period_label_is_previous_month(self):
        report = build_report(report_type="sales", params={}, today=TODAY)
        self.assertEqual(report["period_label"], "01/06/2026 a 30/06/2026")
