from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.evidence.models import EvidencePhoto


@admin.register(EvidencePhoto)
class EvidencePhotoAdmin(ModelAdmin):
    list_display = (
        "id",
        "makerspace",
        "evidence_type",
        "object_key",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("evidence_type", "makerspace", "created_at")
    search_fields = (
        "object_key",
        "uploaded_by__username",
        "uploaded_by__email",
        "makerspace__name",
        "makerspace__slug",
    )
    readonly_fields = (
        "makerspace",
        "evidence_type",
        "object_key",
        "uploaded_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj)
