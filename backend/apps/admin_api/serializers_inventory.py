from django.utils.text import slugify
from rest_framework import serializers

from apps.inventory.models import (
    Category,
    InventoryProduct,
    PublicAvailabilityMode,
    TrackingMode,
)


class InventoryProductAdminSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = InventoryProduct
        fields = [
            "id",
            "makerspace",
            "box",
            "category",
            "name",
            "description",
            "tracking_mode",
            "total_quantity",
            "available_quantity",
            "reserved_quantity",
            "issued_quantity",
            "damaged_quantity",
            "lost_quantity",
            "needs_fix_quantity",
            "is_public",
            "public_self_checkout_enabled",
            "show_public_count",
            "public_availability_mode",
            "storage_location",
            "is_archived",
            "created_at",
            "updated_at",
        ]
        # makerspace is read-only: it is set from the URL scope on create and must
        # never be reassigned on PATCH, or a manager in one tenant could move a
        # product into another. Box scope is enforced in the view (it knows the
        # authoritative makerspace).
        # needs_fix_quantity is owned by the handover/shelf workflow (never set directly).
        read_only_fields = ["id", "makerspace", "needs_fix_quantity", "created_at", "updated_at"]

    def validate_tracking_mode(self, value):
        if value not in TrackingMode.values:
            raise serializers.ValidationError("Invalid tracking mode.")
        return value

    def validate_public_availability_mode(self, value):
        if value not in PublicAvailabilityMode.values:
            raise serializers.ValidationError("Invalid public availability mode.")
        return value


class CategoryAdminSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(required=False, allow_blank=True)
    product_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = [
            "id",
            "makerspace",
            "name",
            "slug",
            "display_order",
            "icon",
            "product_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "makerspace",
            "product_count",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        makerspace_id = self.context.get("makerspace_id") or getattr(
            self.instance, "makerspace_id", None
        )
        name = attrs.get("name", getattr(self.instance, "name", None))
        provided_slug = (attrs.get("slug") or "").strip()
        if provided_slug:
            slug = provided_slug
        elif self.instance is not None and self.instance.slug:
            # PATCH that omits slug: keep the existing (possibly custom) slug
            # instead of silently re-deriving it from the name.
            slug = self.instance.slug
        else:
            slug = slugify(name or "")
        if not slug:
            raise serializers.ValidationError(
                {"slug": "Provide a name that yields a valid slug."}
            )
        duplicate = (
            Category.objects.filter(makerspace_id=makerspace_id, slug=slug)
            .exclude(pk=getattr(self.instance, "pk", None))
            .exists()
        )
        if duplicate:
            raise serializers.ValidationError(
                {
                    "slug": "A category with this slug already exists in this makerspace."
                }
            )
        attrs["slug"] = slug
        return attrs


class InventoryQuantityAdjustmentSerializer(serializers.Serializer):
    delta_available = serializers.IntegerField(default=0)
    delta_damaged = serializers.IntegerField(default=0)
    delta_lost = serializers.IntegerField(default=0)
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate(self, attrs):
        deltas = [
            attrs.get("delta_available", 0),
            attrs.get("delta_damaged", 0),
            attrs.get("delta_lost", 0),
        ]
        if not any(deltas):
            raise serializers.ValidationError("At least one quantity delta is required.")
        return attrs
