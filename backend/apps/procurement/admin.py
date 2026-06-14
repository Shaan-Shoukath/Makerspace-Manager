from django.contrib import admin
from unfold.admin import ModelAdmin

from config.admin_access import SuperuserOnlyModelAdmin
from apps.procurement.models import ToBuyItem


@admin.register(ToBuyItem)
class ToBuyItemAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("name", "makerspace", "kind", "quantity", "status", "created_by", "created_at")
    list_filter = ("kind", "status", "makerspace")
    search_fields = ("name", "link", "makerspace__name", "makerspace__slug")
    readonly_fields = ("created_by", "created_at", "updated_at")
    fields = (
        "makerspace",
        "kind",
        "name",
        "quantity",
        "link",
        "status",
        "estimated_unit_cost",
        "created_by",
        "created_at",
        "updated_at",
    )
