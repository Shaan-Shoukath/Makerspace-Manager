from rest_framework import serializers

from apps.admin_api import bulk_import


class BulkImportPreviewSerializer(serializers.Serializer):
    file = serializers.FileField(required=False)
    rows = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=False,
        max_length=bulk_import.MAX_IMPORT_ROWS,
    )
    mapping = serializers.DictField(child=serializers.CharField(), required=False)

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("rows"):
            raise serializers.ValidationError("Provide either file or rows.")
        uploaded_file = attrs.get("file")
        if uploaded_file and uploaded_file.size > bulk_import.MAX_IMPORT_UPLOAD_BYTES:
            raise serializers.ValidationError(
                {
                    "file": (
                        "Import file must be "
                        f"{bulk_import.MAX_IMPORT_UPLOAD_BYTES} bytes or smaller."
                    )
                }
            )
        return attrs
