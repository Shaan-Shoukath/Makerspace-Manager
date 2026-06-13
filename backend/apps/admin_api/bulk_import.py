import csv
import io
import json

from django.db import transaction
from django.utils.text import slugify

from apps.audit import services as audit
from apps.boxes.models import Box
from apps.inventory.models import Category, InventoryProduct, PublicAvailabilityMode, TrackingMode


REQUIRED_FIELDS = {"name", "total_quantity", "available_quantity"}
OPTIONAL_FIELDS = {
    "description",
    "tracking_mode",
    "is_public",
    "public_self_checkout_enabled",
    "show_public_count",
    "public_availability_mode",
    "storage_location",
    "category",
    "box_code",
    "reserved_quantity",
    "issued_quantity",
    "damaged_quantity",
    "lost_quantity",
}
VALID_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS


def rows_from_upload(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".json"):
        parsed = json.loads(data.decode("utf-8-sig"))
        if not isinstance(parsed, list):
            raise ValueError("JSON import must be a list of row objects.")
        return parsed
    if name.endswith(".tsv"):
        return _delimited_rows(data, "\t")
    if name.endswith(".xlsx"):
        return _xlsx_rows(data)
    return _delimited_rows(data, ",")


def _delimited_rows(data, delimiter):
    text = data.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


def _xlsx_rows(data):
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("XLSX import requires openpyxl to be installed.") from exc
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
    except Exception as exc:  # corrupt/unsupported workbook -> treat as bad input
        raise ValueError("XLSX file could not be read.") from exc
    if not rows:
        return []
    headers = [str(value or "").strip() for value in rows[0]]
    return [
        {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
        for row in rows[1:]
    ]


def preview_import(makerspace, rows, mapping):
    mapping = mapping or _default_mapping(rows)
    mapped = []
    errors = []
    existing_names = _existing_names(makerspace, rows, mapping)
    for index, row in enumerate(rows, start=2):
        normalized, row_errors = _normalize_row(makerspace, row, mapping)
        if row_errors:
            errors.append({"row": index, "errors": row_errors})
        action = "error" if row_errors else _row_action(normalized, existing_names)
        mapped.append({"row": index, "action": action, "data": normalized})
    return {
        "mapping": mapping,
        "valid": not errors,
        "errors": errors,
        "rows": mapped,
        "summary": {
            "create": sum(1 for item in mapped if item["action"] == "create"),
            "update": sum(1 for item in mapped if item["action"] == "update"),
            "errors": len(errors),
            "total": len(mapped),
        },
    }


def apply_import(actor, makerspace, rows, mapping):
    preview = preview_import(makerspace, rows, mapping)
    if not preview["valid"]:
        return {**preview, "applied": False}
    created = 0
    updated = 0
    with transaction.atomic():
        for item in preview["rows"]:
            data = item["data"]
            box = data.pop("box", None)
            category_name = data.pop("category_name", "")
            if category_name:
                category, was_category_created = _category_for_name(makerspace, category_name)
                data["category_id"] = category.id
                if was_category_created:
                    audit.record(
                        actor,
                        "category.created",
                        makerspace=makerspace,
                        target=category,
                        meta={"source": "bulk_import"},
                    )
            product, was_created = InventoryProduct.objects.update_or_create(
                makerspace=makerspace,
                name=data.pop("name"),
                defaults={**data, "box": box},
            )
            created += 1 if was_created else 0
            updated += 0 if was_created else 1
        audit.record(
            actor,
            "inventory.bulk_imported",
            makerspace=makerspace,
            target=makerspace,
            meta={"created": created, "updated": updated},
        )
    return {**preview, "applied": True, "created": created, "updated": updated}


def _default_mapping(rows):
    if not rows:
        return {}
    lower = {str(key).strip().lower(): key for key in rows[0].keys()}
    return {field: lower[field] for field in VALID_FIELDS if field in lower}


def _normalize_row(makerspace, row, mapping):
    data = {}
    errors = {}
    for field in VALID_FIELDS:
        column = mapping.get(field)
        if column:
            data[field] = row.get(column)
    for field in REQUIRED_FIELDS:
        if data.get(field) in {None, ""}:
            errors[field] = "This field is required."

    for field in [
        "total_quantity",
        "available_quantity",
        "reserved_quantity",
        "issued_quantity",
        "damaged_quantity",
        "lost_quantity",
    ]:
        if field in data:
            data[field] = _int_value(data[field], field, errors)
    data.setdefault("reserved_quantity", 0)
    data.setdefault("issued_quantity", 0)
    data.setdefault("damaged_quantity", 0)
    data.setdefault("lost_quantity", 0)

    for field in ["is_public", "public_self_checkout_enabled", "show_public_count"]:
        if field in data:
            data[field] = _bool_value(data[field])
    data.setdefault("is_public", True)
    data.setdefault("public_self_checkout_enabled", False)
    data.setdefault("show_public_count", False)
    data.setdefault("tracking_mode", TrackingMode.QUANTITY)
    data.setdefault("public_availability_mode", PublicAvailabilityMode.STATUS_ONLY)
    if data["tracking_mode"] not in TrackingMode.values:
        errors["tracking_mode"] = "Invalid tracking mode."
    if data["public_availability_mode"] not in PublicAvailabilityMode.values:
        errors["public_availability_mode"] = "Invalid public availability mode."

    total_used = sum(
        data[field]
        for field in [
            "available_quantity",
            "reserved_quantity",
            "issued_quantity",
            "damaged_quantity",
            "lost_quantity",
        ]
    )
    if "total_quantity" in data and total_used > data["total_quantity"]:
        errors["total_quantity"] = "Quantity buckets cannot exceed total quantity."

    box_code = data.pop("box_code", None)
    data["box"] = None
    if box_code:
        data["box"] = Box.objects.filter(makerspace=makerspace, code=box_code).first()
        if data["box"] is None:
            errors["box_code"] = "Box code does not exist in this makerspace."
    category_name = str(data.pop("category", "") or "").strip()
    if category_name:
        category = Category.objects.filter(makerspace=makerspace, name__iexact=category_name).first()
        data["category_name"] = category_name
        data["category_id"] = category.id if category else None
    return data, errors


def _int_value(value, field, errors):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors[field] = "Must be an integer."
        return 0
    if parsed < 0:
        errors[field] = "Must be non-negative."
    return parsed


def _bool_value(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _existing_names(makerspace, rows, mapping):
    name_column = mapping.get("name")
    if not name_column:
        return set()
    names = [row.get(name_column) for row in rows if row.get(name_column)]
    return set(
        InventoryProduct.objects.filter(
            makerspace=makerspace,
            name__in=names,
        ).values_list("name", flat=True)
    )


def _row_action(normalized, existing_names):
    name = normalized.get("name")
    if not name:
        return "error"
    return "update" if name in existing_names else "create"


def _category_for_name(makerspace, name):
    category = Category.objects.filter(makerspace=makerspace, name__iexact=name).first()
    if category:
        return category, False
    base_slug = slugify(name) or "category"
    slug = base_slug
    suffix = 2
    while Category.objects.filter(makerspace=makerspace, slug=slug).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return Category.objects.create(makerspace=makerspace, name=name, slug=slug), True
