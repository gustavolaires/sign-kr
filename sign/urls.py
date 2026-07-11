from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "sign"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="sign:product_list"), name="home"),
    # Dashboard
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    # Relatórios
    path("reports/", views.report_index, name="report_index"),
    path("reports/render/", views.report_render, name="report_render"),
    # Produtos
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/new/", views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/toggle-active/", views.ProductToggleActiveView.as_view(), name="product_toggle_active"),
    path("products/<int:pk>/delete/", views.ProductDeleteView.as_view(), name="product_delete"),
    # Importação (carga inicial — oculto, sem item de menu; acesso só via URL)
    path("products/import/", views.product_import_upload, name="product_import_upload"),
    path("products/import/mapping/", views.product_import_mapping, name="product_import_mapping"),
    # Carrinho
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
    # Vendas
    path("sales/checkout/", views.checkout, name="checkout"),
    path("sales/quote/", views.sale_quote, name="sale_quote"),
    path("sales/", views.SaleListView.as_view(), name="sale_list"),
    path("sales/<int:pk>/", views.SaleDetailView.as_view(), name="sale_detail"),
    path("sales/<int:pk>/receipt/", views.sale_receipt, name="sale_receipt"),
    # Clientes
    path("clients/", views.ClientListView.as_view(), name="client_list"),
    path("clients/new/", views.ClientCreateView.as_view(), name="client_create"),
    path("clients/<int:pk>/", views.ClientDetailView.as_view(), name="client_detail"),
    path("clients/<int:pk>/edit/", views.ClientUpdateView.as_view(), name="client_update"),
    path("clients/<int:pk>/delete/", views.ClientDeleteView.as_view(), name="client_delete"),
    # Fornecedores
    path("suppliers/", views.SupplierListView.as_view(), name="supplier_list"),
    path("suppliers/new/", views.SupplierCreateView.as_view(), name="supplier_create"),
    path("suppliers/<int:pk>/", views.SupplierDetailView.as_view(), name="supplier_detail"),
    path("suppliers/<int:pk>/edit/", views.SupplierUpdateView.as_view(), name="supplier_update"),
    path("suppliers/<int:pk>/delete/", views.SupplierDeleteView.as_view(), name="supplier_delete"),
    # Representantes
    path("suppliers/<int:supplier_pk>/representatives/new/", views.RepresentativeCreateView.as_view(), name="representative_create"),
    path("representatives/<int:pk>/edit/", views.RepresentativeUpdateView.as_view(), name="representative_update"),
    path("representatives/<int:pk>/delete/", views.RepresentativeDeleteView.as_view(), name="representative_delete"),
    # Despesas
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/new/", views.ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/", views.ExpenseDetailView.as_view(), name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_update"),
    path("expenses/<int:pk>/delete/", views.ExpenseDeleteView.as_view(), name="expense_delete"),
    # Parcelas de despesa
    path("expenses/<int:expense_pk>/installments/new/", views.ExpenseInstallmentCreateView.as_view(), name="installment_create"),
    path("installments/<int:pk>/edit/", views.ExpenseInstallmentUpdateView.as_view(), name="installment_update"),
    path("installments/<int:pk>/delete/", views.ExpenseInstallmentDeleteView.as_view(), name="installment_delete"),
    path("installments/<int:pk>/pay/", views.installment_pay, name="installment_pay"),
    # Notas fiscais de entrada
    path("invoices/", views.InboundInvoiceListView.as_view(), name="invoice_list"),
    path("invoices/new/", views.InboundInvoiceCreateView.as_view(), name="invoice_create"),
    path("invoices/<int:pk>/", views.InboundInvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/edit/", views.InboundInvoiceUpdateView.as_view(), name="invoice_update"),
    path("invoices/<int:pk>/delete/", views.InboundInvoiceDeleteView.as_view(), name="invoice_delete"),
    path("invoices/<int:pk>/process/", views.invoice_process, name="invoice_process"),
    # Faturas da nota fiscal
    path("invoices/<int:invoice_pk>/duplicates/new/", views.InvoiceDuplicateCreateView.as_view(), name="invoice_duplicate_create"),
    path("duplicates/<int:pk>/edit/", views.InvoiceDuplicateUpdateView.as_view(), name="invoice_duplicate_update"),
    path("duplicates/<int:pk>/delete/", views.InvoiceDuplicateDeleteView.as_view(), name="invoice_duplicate_delete"),
    # Produtos da nota fiscal
    path("invoices/<int:invoice_pk>/items/new/", views.InvoiceItemCreateView.as_view(), name="invoice_item_create"),
    path("items/<int:pk>/edit/", views.InvoiceItemUpdateView.as_view(), name="invoice_item_update"),
    path("items/<int:pk>/delete/", views.InvoiceItemDeleteView.as_view(), name="invoice_item_delete"),
    # Configurações
    path("settings/company/", views.CompanySettingsView.as_view(), name="company_settings"),
    # Fabricantes
    path("manufacturers/", views.ManufacturerListView.as_view(), name="manufacturer_list"),
    path("manufacturers/new/", views.ManufacturerCreateView.as_view(), name="manufacturer_create"),
    path("manufacturers/<int:pk>/edit/", views.ManufacturerUpdateView.as_view(), name="manufacturer_update"),
    path("manufacturers/<int:pk>/delete/", views.ManufacturerDeleteView.as_view(), name="manufacturer_delete"),
]
