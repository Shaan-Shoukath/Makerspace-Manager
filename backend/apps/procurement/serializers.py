from rest_framework import serializers

from apps.procurement.models import ToBuyItem


class ToBuyItemSerializer(serializers.ModelSerializer):
    # kind is decided server-side from the actor's role (see access.derive_kind),
    # never written from the request body — so it is read-only here.
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        default=None,
    )

    class Meta:
        model = ToBuyItem
        fields = [
            "id",
            "makerspace",
            "kind",
            "name",
            "quantity",
            "link",
            "status",
            "estimated_unit_cost",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "makerspace",
            "kind",
            "created_by",
            "created_by_username",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def validate_estimated_unit_cost(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Estimated unit cost cannot be negative.")
        return value
