from .cart import (
    cart_add,
    cart_detail,
    cart_remove,
    cart_update,
)
from .clients import (
    ClientCreateView,
    ClientDeleteView,
    ClientDetailView,
    ClientListView,
    ClientUpdateView,
)
from .expenses import (
    ExpenseCreateView,
    ExpenseDeleteView,
    ExpenseDetailView,
    ExpenseInstallmentCreateView,
    ExpenseInstallmentDeleteView,
    ExpenseInstallmentUpdateView,
    ExpenseListView,
    ExpenseUpdateView,
    installment_pay,
)
from .manufacturers import (
    ManufacturerCreateView,
    ManufacturerDeleteView,
    ManufacturerListView,
    ManufacturerUpdateView,
)
from .products import (
    ProductCreateView,
    ProductDeleteView,
    ProductDetailView,
    ProductListView,
    ProductUpdateView,
)
from .sales import (
    SaleDetailView,
    SaleListView,
    checkout,
    sale_receipt,
)

__all__ = [
    "cart_add",
    "cart_detail",
    "cart_remove",
    "cart_update",
    "ClientCreateView",
    "ClientDeleteView",
    "ClientDetailView",
    "ClientListView",
    "ClientUpdateView",
    "ExpenseCreateView",
    "ExpenseDeleteView",
    "ExpenseDetailView",
    "ExpenseInstallmentCreateView",
    "ExpenseInstallmentDeleteView",
    "ExpenseInstallmentUpdateView",
    "ExpenseListView",
    "ExpenseUpdateView",
    "installment_pay",
    "ManufacturerCreateView",
    "ManufacturerDeleteView",
    "ManufacturerListView",
    "ManufacturerUpdateView",
    "ProductCreateView",
    "ProductDeleteView",
    "ProductDetailView",
    "ProductListView",
    "ProductUpdateView",
    "checkout",
    "sale_receipt",
    "SaleDetailView",
    "SaleListView",
]
