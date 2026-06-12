from django.contrib import admin

from .models import Manufacturer, Product


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "manufacturer", "quantity", "unit_type", "unit_price_cents"]
    list_filter = ["unit_type", "manufacturer"]
    search_fields = ["name", "barcode", "manufacturer_code"]
