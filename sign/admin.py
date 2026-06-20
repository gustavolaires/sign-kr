from django.contrib import admin

from .models import (
    Client,
    Manufacturer,
    Product,
    ProductSnapshot,
    Sale,
    SaleItem,
    SalePayment,
)


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


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    fields = ["product_snapshot", "quantity", "unit_price_cents", "discount_cents", "total_cents"]
    readonly_fields = fields
    raw_id_fields = ["product_snapshot"]


class SalePaymentInline(admin.TabularInline):
    model = SalePayment
    extra = 0
    can_delete = False
    fields = ["payment_type", "installments", "value_cents"]
    readonly_fields = fields


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "client", "discount_cents", "total_cents"]
    list_filter = ["created_at", "has_perc_discount"]
    search_fields = ["id", "client__name"]
    date_hierarchy = "created_at"
    inlines = [SaleItemInline, SalePaymentInline]
    readonly_fields = [
        "client",
        "subtotal_cents",
        "has_perc_discount",
        "perc_discount",
        "discount_cents",
        "change_cents",
        "total_cents",
        "obs",
        "created_at",
    ]


@admin.register(ProductSnapshot)
class ProductSnapshotAdmin(admin.ModelAdmin):
    list_display = ["name", "manufacturer_name", "barcode", "unit_type", "created_at"]
    search_fields = ["name", "barcode", "manufacturer_code"]
    readonly_fields = ["content_hash", "created_at"]
