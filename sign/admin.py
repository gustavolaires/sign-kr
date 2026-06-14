from django.contrib import admin

from .models import Client, Manufacturer, Product


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "manufacturer", "quantity", "unit_type", "unit_price_cents"]
    list_filter = ["unit_type", "manufacturer"]
    search_fields = ["name", "barcode", "manufacturer_code"]


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "person_type", "cpf_cnpj", "email", "phone_primary"]
    list_filter = ["person_type"]
    search_fields = ["name", "cpf_cnpj", "email"]
