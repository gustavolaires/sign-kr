from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "sign"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="sign:product_list"), name="home"),
    # Produtos
    path("products/", views.ProductListView.as_view(), name="product_list"),
    path("products/new/", views.ProductCreateView.as_view(), name="product_create"),
    path("products/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("products/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_update"),
    path("products/<int:pk>/delete/", views.ProductDeleteView.as_view(), name="product_delete"),
    # Carrinho
    path("cart/", views.cart_detail, name="cart_detail"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
    # Vendas
    path("sales/checkout/", views.checkout, name="checkout"),
    path("sales/", views.SaleListView.as_view(), name="sale_list"),
    path("sales/<int:pk>/", views.SaleDetailView.as_view(), name="sale_detail"),
    path("sales/<int:pk>/receipt/", views.sale_receipt, name="sale_receipt"),
    # Clientes
    path("clients/", views.ClientListView.as_view(), name="client_list"),
    path("clients/new/", views.ClientCreateView.as_view(), name="client_create"),
    path("clients/<int:pk>/", views.ClientDetailView.as_view(), name="client_detail"),
    path("clients/<int:pk>/edit/", views.ClientUpdateView.as_view(), name="client_update"),
    path("clients/<int:pk>/delete/", views.ClientDeleteView.as_view(), name="client_delete"),
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
    # Fabricantes
    path("manufacturers/", views.ManufacturerListView.as_view(), name="manufacturer_list"),
    path("manufacturers/new/", views.ManufacturerCreateView.as_view(), name="manufacturer_create"),
    path("manufacturers/<int:pk>/edit/", views.ManufacturerUpdateView.as_view(), name="manufacturer_update"),
    path("manufacturers/<int:pk>/delete/", views.ManufacturerDeleteView.as_view(), name="manufacturer_delete"),
]
