from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit import services as audit
from apps.inventory.models import InventoryAsset, InventoryProduct
from apps.operations.models import InventoryAdjustment, StocktakeLine, StocktakeSession
from apps.operations.services_shared import _container


def create_stocktake(actor, makerspace, data):
    container = _container(data.get("container_id"), makerspace.id)
    stocktake = StocktakeSession.objects.create(
        makerspace=makerspace,
        container=container,
        started_by=actor,
        notes=data.get("notes", ""),
    )
    audit.record(actor, "stocktake.created", makerspace=makerspace, target=stocktake)
    return stocktake


def add_stocktake_line(actor, stocktake, data):
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        if locked.status not in {StocktakeSession.Status.DRAFT, StocktakeSession.Status.COUNTING}:
            raise ValidationError("Cannot add count lines after stocktake is completed.")
        product = None
        asset = None
        expected = 0
        if data.get("asset_id"):
            asset = InventoryAsset.objects.get(pk=data["asset_id"], makerspace=locked.makerspace)
            expected = 1 if asset.status == InventoryAsset.Status.AVAILABLE else 0
        else:
            product = InventoryProduct.objects.get(pk=data["product_id"], makerspace=locked.makerspace)
            expected = product.available_quantity
        container = _container(data.get("container_id"), locked.makerspace_id)
        counted = data["counted_quantity"]
        line = StocktakeLine.objects.create(
            stocktake=locked,
            product=product,
            asset=asset,
            container=container,
            expected_quantity=expected,
            counted_quantity=counted,
            variance_quantity=counted - expected,
            condition=data.get("condition") or StocktakeLine.Condition.AVAILABLE,
            notes=data.get("notes", ""),
        )
        audit.record(actor, "stocktake.line_counted", makerspace=locked.makerspace, target=locked, meta={"line_id": line.id})
        return line


def complete_stocktake(actor, stocktake):
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        if locked.status != StocktakeSession.Status.COUNTING:
            raise ValidationError("Only counting stocktakes can be completed.")
        locked.status = StocktakeSession.Status.COMPLETED
        locked.completed_at = timezone.now()
        locked.save(update_fields=["status", "completed_at"])
        audit.record(actor, "stocktake.completed", makerspace=locked.makerspace, target=locked)
        return locked


def approve_stocktake(actor, stocktake):
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        if locked.status != StocktakeSession.Status.COMPLETED:
            raise ValidationError("Only completed stocktakes can be approved.")
        locked.status = StocktakeSession.Status.APPROVED
        locked.approved_by = actor
        locked.approved_at = timezone.now()
        locked.save(update_fields=["status", "approved_by", "approved_at"])
        audit.record(actor, "stocktake.approved", makerspace=locked.makerspace, target=locked)
        return locked


def apply_stocktake_adjustments(actor, stocktake):
    if stocktake.status != StocktakeSession.Status.APPROVED:
        raise ValidationError("Only approved stocktakes can be applied.")
    with transaction.atomic():
        locked = StocktakeSession.objects.select_for_update().get(pk=stocktake.pk)
        for line in locked.lines.select_related("product", "asset"):
            if line.variance_quantity == 0:
                continue
            if line.asset_id:
                _apply_asset_line(line)
            else:
                _apply_product_line(line)
            InventoryAdjustment.objects.create(
                makerspace=locked.makerspace,
                stocktake=locked,
                product=line.product,
                asset=line.asset,
                delta_available=line.variance_quantity if line.condition == StocktakeLine.Condition.AVAILABLE else 0,
                delta_damaged=line.variance_quantity if line.condition == StocktakeLine.Condition.DAMAGED else 0,
                delta_lost=line.variance_quantity if line.condition == StocktakeLine.Condition.LOST else 0,
                reason=f"Stocktake #{locked.id}: {line.notes}".strip(),
                created_by=actor,
            )
        locked.status = StocktakeSession.Status.APPLIED
        locked.save(update_fields=["status"])
        audit.record(actor, "stocktake.adjustments_applied", makerspace=locked.makerspace, target=locked)
        return locked


def _apply_product_line(line):
    product = InventoryProduct.objects.select_for_update().get(pk=line.product_id)
    if line.condition == StocktakeLine.Condition.AVAILABLE:
        new_available = product.available_quantity + line.variance_quantity
        if new_available < 0:
            raise ValidationError("Stocktake adjustment would make available stock negative.")
        product.available_quantity = new_available
    elif line.condition == StocktakeLine.Condition.DAMAGED:
        product.damaged_quantity = max(0, product.damaged_quantity + line.variance_quantity)
    elif line.condition == StocktakeLine.Condition.LOST:
        product.lost_quantity = max(0, product.lost_quantity + line.variance_quantity)
    product.total_quantity = (
        product.available_quantity
        + product.reserved_quantity
        + product.issued_quantity
        + product.damaged_quantity
        + product.lost_quantity
        + product.needs_fix_quantity
    )
    product.save()


def _apply_asset_line(line):
    asset = InventoryAsset.objects.select_for_update().get(pk=line.asset_id)
    if line.counted_quantity == 0:
        asset.status = InventoryAsset.Status.LOST
    elif line.condition == StocktakeLine.Condition.DAMAGED:
        asset.status = InventoryAsset.Status.DAMAGED
    else:
        asset.status = InventoryAsset.Status.AVAILABLE
    asset.save(update_fields=["status", "updated_at"])
