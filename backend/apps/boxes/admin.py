import segno
from django.contrib import admin
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin

from apps.boxes.models import Box, BoxScan, QrCode, QrScanEvent
from apps.boxes.qr_render import render_qr_label_svg
from config.admin_access import SuperuserOnlyModelAdmin


@admin.register(Box)
class BoxAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("label", "makerspace", "parent", "code", "is_active", "updated_at")
    list_filter = ("makerspace", "is_active")
    search_fields = ("label", "code", "location")
    autocomplete_fields = ("makerspace", "parent")
    readonly_fields = ("code", "qr_preview", "created_at", "updated_at")

    def qr_preview(self, obj):
        if not obj or not obj.pk:
            return "(save first to generate the QR)"
        return mark_safe(segno.make(obj.code).svg_inline(scale=4))

    qr_preview.short_description = "QR tag"


@admin.register(QrCode)
class QrCodeAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("payload", "makerspace", "target_type", "target_id", "status", "updated_at")
    list_filter = ("makerspace", "target_type", "status")
    search_fields = ("payload",)
    readonly_fields = ("payload", "qr_preview", "created_at", "updated_at", "revoked_at")

    def qr_preview(self, obj):
        if not obj or not obj.pk:
            return "(no QR)"
        return mark_safe(render_qr_label_svg(obj.payload))

    qr_preview.short_description = "QR preview"


@admin.register(QrScanEvent)
class QrScanEventAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("qr_code", "makerspace", "context", "actor", "created_at")
    list_filter = ("makerspace", "context")
    search_fields = ("qr_code__payload",)
    readonly_fields = ("qr_code", "makerspace", "request", "actor", "context", "created_at")


@admin.register(BoxScan)
class BoxScanAdmin(SuperuserOnlyModelAdmin, ModelAdmin):
    list_display = ("box", "box_qr", "makerspace", "context", "scanned_by", "created_at")
    list_filter = ("makerspace", "context")
    search_fields = (
        "box__label",
        "box__code",
        "actor__username",
        "actor__email",
        "request__requester_username",
    )
    readonly_fields = ("makerspace", "box", "request", "actor", "context", "created_at")
    fields = readonly_fields
    ordering = ("-created_at",)

    @admin.display(description="QR", ordering="box__code")
    def box_qr(self, obj):
        return obj.box.code if obj.box_id else "-"

    @admin.display(description="Scanned by", ordering="actor")
    def scanned_by(self, obj):
        return obj.actor

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
