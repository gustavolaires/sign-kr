from datetime import date, datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from django.core.exceptions import ValidationError

from .models import (
    Client,
    Company,
    Expense,
    ExpenseInstallment,
    Manufacturer,
    PaymentType,
    Product,
    ProductSnapshot,
    Sale,
    SaleItem,
    SalePayment,
    offset_to_tzinfo,
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


def _add_payment(sale, payment_type, value_cents):
    """Adiciona uma forma de pagamento a uma venda."""
    return SalePayment.objects.create(
        sale=sale, payment_type=payment_type, value_cents=value_cents
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


class DashboardMetricsSalesExtrasTests(TestCase):
    """Produtos diferentes vendidos e formas de pagamento (hoje/semana)."""

    def test_distinct_products_and_payments(self):
        today = date(2026, 7, 15)  # quarta; semana 13→19 jul
        maker = Manufacturer.objects.create(name="ACME")
        a = Product.objects.create(
            name="A", manufacturer=maker, quantity=100, unit_price_cents=1000
        )
        b = Product.objects.create(
            name="B", manufacturer=maker, quantity=100, unit_price_cents=1000
        )
        c = Product.objects.create(
            name="C", manufacturer=maker, quantity=100, unit_price_cents=1000
        )
        # Venda de hoje: A e B (2 produtos distintos).
        s_today = _make_sale(15000, datetime(2026, 7, 15, 10, 0))
        _add_item(s_today, a, 2)
        _add_item(s_today, b, 3)
        _add_payment(s_today, PaymentType.CASH, 10000)
        _add_payment(s_today, PaymentType.PIX, 5000)
        # Venda anterior na semana (segunda 13/07): C.
        s_week = _make_sale(3000, datetime(2026, 7, 13, 10, 0))
        _add_item(s_week, c, 1)
        _add_payment(s_week, PaymentType.CREDIT, 3000)

        m = dashboard_metrics(company=Company.get_solo(), today=today)
        self.assertEqual(m["distinct"]["today"], 2)  # A, B
        self.assertEqual(m["distinct"]["week"], 3)  # A, B, C

        # Doughnut de hoje: só dinheiro e pix (ordem de PaymentType.choices).
        today_pay = m["chart_data"]["payments_today"]
        self.assertEqual(
            [(p["code"], p["value"]) for p in today_pay],
            [("cash", 100.0), ("pix", 50.0)],
        )
        # Semana: crédito + dinheiro + pix.
        week_pay = {p["code"]: p["value"] for p in m["chart_data"]["payments_week"]}
        self.assertEqual(week_pay, {"credit": 30.0, "cash": 100.0, "pix": 50.0})


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
JULY = {"date_from": "2026-07-01", "date_to": "2026-07-31"}


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
        all_r = build_report(report_type="expenses", params=JULY, today=TODAY)
        self.assertEqual(len(all_r["rows"]), 2)
        types = {_report_cell_map(all_r, i)["name"]: _report_cell_map(all_r, i)["type"]
                 for i in range(len(all_r["rows"]))}
        self.assertEqual(types, {"Aluguel": "Recorrente", "Compra": "Isolada"})

        open_r = build_report(report_type="expenses_open", params=JULY, today=TODAY)
        self.assertEqual(
            [_report_cell_map(open_r, i)["name"] for i in range(len(open_r["rows"]))],
            ["Compra"],
        )

        paid_r = build_report(report_type="expenses_paid", params=JULY, today=TODAY)
        self.assertEqual(
            [_report_cell_map(paid_r, i)["name"] for i in range(len(paid_r["rows"]))],
            ["Aluguel"],
        )

    def test_all_records_ignores_period(self):
        # "Considerar todos os registros" traz também a parcela de agosto.
        report = build_report(
            report_type="expenses", params={"all_sales": "1"}, today=TODAY
        )
        self.assertEqual(len(report["rows"]), 3)
        self.assertEqual(report["period_label"], "Todos os registros")


class ReportGuardTests(TestCase):
    """Guardas do dispatcher de relatórios."""

    def test_invalid_type_raises(self):
        with self.assertRaises(ValidationError):
            build_report(report_type="nope", params={}, today=TODAY)

    def test_default_period_label_is_month_to_date(self):
        # Padrão único: 1º dia do mês atual até hoje.
        report = build_report(report_type="sales", params={}, today=TODAY)
        self.assertEqual(report["period_label"], "01/07/2026 a 15/07/2026")


class ReportSalesSummaryTests(TestCase):
    """Resumo de vendas: grupos, somatórios, seleção e "todos os registros"."""

    def _sale(self, *, subtotal, discount, total, when):
        sale = Sale.objects.create(
            subtotal_cents=subtotal, discount_cents=discount, total_cents=total
        )
        Sale.objects.filter(pk=sale.pk).update(created_at=timezone.make_aware(when))
        return Sale.objects.get(pk=sale.pk)

    def setUp(self):
        maker = Manufacturer.objects.create(name="ACME")
        self.a = Product.objects.create(
            name="Alfa", manufacturer=maker, quantity=100, unit_price_cents=1000
        )
        self.b = Product.objects.create(
            name="Beta", manufacturer=maker, quantity=100, unit_price_cents=2000
        )
        # Duas vendas no período (month_to_date: 01/07 a 15/07).
        s1 = self._sale(
            subtotal=16000, discount=1000, total=15000, when=datetime(2026, 7, 5, 12, 0)
        )
        _add_item(s1, self.a, 2)
        _add_item(s1, self.b, 3)
        _add_payment(s1, PaymentType.CASH, 15000)
        s2 = self._sale(
            subtotal=5000, discount=0, total=5000, when=datetime(2026, 7, 10, 12, 0)
        )
        _add_item(s2, self.a, 1)
        _add_payment(s2, PaymentType.PIX, 5000)
        # Venda de junho (fora do período padrão).
        s3 = self._sale(
            subtotal=99900, discount=0, total=99900, when=datetime(2026, 6, 20, 12, 0)
        )
        _add_payment(s3, PaymentType.CREDIT, 99900)

    def test_default_period_groups_and_totals(self):
        report = build_report(report_type="sales_summary", params={}, today=TODAY)
        self.assertEqual(report["title"], "Vendas - Resumo")
        groups = {g["title"]: g for g in report["groups"]}

        vendas = {r["label"]: r["value"] for r in groups["Vendas"]["rows"]}
        self.assertEqual(vendas["Nº de vendas"], 2)
        self.assertEqual(vendas["Produtos vendidos"], 6)  # 2 + 3 + 1
        self.assertEqual(vendas["Produtos diferentes vendidos"], 2)  # Alfa, Beta
        self.assertIsNone(groups["Vendas"]["total"])  # grupo sem somatório

        valores = {r["label"]: r["value"] for r in groups["Valores"]["rows"]}
        self.assertEqual(valores["Subtotal"], 210.0)
        self.assertEqual(valores["Desconto"], 10.0)
        self.assertEqual(valores["Total"], 200.0)
        self.assertIsNone(groups["Valores"]["total"])  # grupo sem somatório

        pag = {r["label"]: r["value"] for r in groups["Formas de pagamento"]["rows"]}
        self.assertEqual(pag["Dinheiro"], 150.0)
        self.assertEqual(pag["Pix"], 50.0)
        self.assertEqual(pag["Crédito"], 0.0)  # a venda de junho ficou fora
        self.assertEqual(groups["Formas de pagamento"]["total"]["value"], 200.0)

    def test_all_records_includes_everything(self):
        report = build_report(
            report_type="sales_summary", params={"all_sales": "1"}, today=TODAY
        )
        self.assertEqual(report["period_label"], "Todos os registros")
        groups = {g["title"]: g for g in report["groups"]}
        vendas = {r["label"]: r["value"] for r in groups["Vendas"]["rows"]}
        self.assertEqual(vendas["Nº de vendas"], 3)  # inclui junho
        pag = {r["label"]: r["value"] for r in groups["Formas de pagamento"]["rows"]}
        self.assertEqual(pag["Crédito"], 999.0)  # 99900 centavos

    def test_selection_drops_rows_and_empty_groups(self):
        report = build_report(
            report_type="sales_summary",
            params={"col": ["total", "pay_credit"]},
            today=TODAY,
        )
        # Grupo "Vendas" some (nenhuma informação selecionada).
        self.assertEqual([g["title"] for g in report["groups"]],
                         ["Valores", "Formas de pagamento"])
        valores = report["groups"][0]
        self.assertEqual([r["label"] for r in valores["rows"]], ["Total"])
        self.assertIsNone(valores["total"])  # grupo Valores sem somatório
        pag = report["groups"][1]
        self.assertEqual([r["label"] for r in pag["rows"]], ["Crédito"])
        self.assertEqual(pag["total"]["value"], 0.0)  # somatório do grupo pagamentos


class TimezoneConfigTests(TestCase):
    """Fuso configurável: conversão do offset e janelas seguindo a tz ativa."""

    def test_tzinfo_from_offset(self):
        self.assertEqual(
            Company(timezone="-03:00").tzinfo.utcoffset(None), timedelta(hours=-3)
        )
        self.assertEqual(
            Company(timezone="+00:00").tzinfo.utcoffset(None), timedelta(0)
        )

    def test_sale_window_follows_active_timezone(self):
        # Venda às 08/07 01:00 UTC == 07/07 22:00 em UTC-03:00.
        sale = Sale.objects.create(total_cents=10000)
        Sale.objects.filter(pk=sale.pk).update(
            created_at=datetime(2026, 7, 8, 1, 0, tzinfo=offset_to_tzinfo("+00:00"))
        )
        company = Company.get_solo()
        with timezone.override(offset_to_tzinfo("-03:00")):
            # Sob UTC-03:00, a venda cai no dia local 07/07 (não em 08/07).
            m7 = dashboard_metrics(company=company, today=date(2026, 7, 7))
            m8 = dashboard_metrics(company=company, today=date(2026, 7, 8))
        self.assertEqual(m7["sales"]["today"]["count"], 1)
        self.assertEqual(m8["sales"]["today"]["count"], 0)
        # Sob UTC, a mesma venda cai em 08/07.
        with timezone.override(offset_to_tzinfo("+00:00")):
            m8_utc = dashboard_metrics(company=company, today=date(2026, 7, 8))
        self.assertEqual(m8_utc["sales"]["today"]["count"], 1)
