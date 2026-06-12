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
    # Fabricantes
    path("manufacturers/", views.ManufacturerListView.as_view(), name="manufacturer_list"),
    path("manufacturers/new/", views.ManufacturerCreateView.as_view(), name="manufacturer_create"),
    path("manufacturers/<int:pk>/edit/", views.ManufacturerUpdateView.as_view(), name="manufacturer_update"),
    path("manufacturers/<int:pk>/delete/", views.ManufacturerDeleteView.as_view(), name="manufacturer_delete"),
]
