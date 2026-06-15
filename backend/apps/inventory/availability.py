from django.db import connection, transaction

from apps.inventory.models import InventoryProduct


class InsufficientStock(Exception):
    pass


def adjust_quantities(
    product, *, delta_available, delta_damaged, delta_lost, reason, actor
):
    """Apply signed deltas to a product's available/damaged/lost buckets, recompute
    total, record an InventoryAdjustment, and audit. Row-locked; refuses to make any
    bucket negative (raises InsufficientStock)."""
    with transaction.atomic():
        locked = InventoryProduct.objects.select_for_update().get(pk=product.pk)
        available = locked.available_quantity + delta_available
        damaged = locked.damaged_quantity + delta_damaged
        lost = locked.lost_quantity + delta_lost
        if available < 0 or damaged < 0 or lost < 0:
            raise InsufficientStock(
                "Quantity adjustment cannot make a bucket negative."
            )

        locked.available_quantity = available
        locked.damaged_quantity = damaged
        locked.lost_quantity = lost
        locked.total_quantity = (
            locked.available_quantity
            + locked.reserved_quantity
            + locked.issued_quantity
            + locked.damaged_quantity
            + locked.lost_quantity
            + locked.needs_fix_quantity
        )
        locked.save(
            update_fields=[
                "available_quantity",
                "damaged_quantity",
                "lost_quantity",
                "total_quantity",
                "updated_at",
            ]
        )

        from apps.audit import services as audit
        from apps.operations.models import InventoryAdjustment

        InventoryAdjustment.objects.create(
            makerspace=locked.makerspace,
            product=locked,
            delta_available=delta_available,
            delta_damaged=delta_damaged,
            delta_lost=delta_lost,
            reason=reason,
            created_by=actor,
        )
        audit.record(
            actor,
            "inventory.quantity_adjusted",
            makerspace=locked.makerspace,
            target=locked,
            meta={
                "delta_available": delta_available,
                "delta_damaged": delta_damaged,
                "delta_lost": delta_lost,
                "reason": reason,
            },
        )
    return locked


def issue_available(product, quantity):
    """Move `quantity` of a single product straight from available -> issued.

    The no-reservation flows (public self-checkout, admin direct handout) never go
    through accept/reserve, so they skip the reserved bucket. The caller must
    already hold a row lock on `product` (select_for_update) inside an atomic
    block; centralizing the math here keeps the never-below-zero invariant in one
    place instead of being open-coded in each workflow."""
    if not connection.in_atomic_block:
        raise RuntimeError("issue_available must be called inside transaction.atomic().")
    if product.available_quantity < quantity:
        raise InsufficientStock(
            f"Insufficient stock for product {product.pk}: "
            f"requested {quantity}, available {product.available_quantity}."
        )
    product.available_quantity -= quantity
    product.issued_quantity += quantity
    product.save(update_fields=["available_quantity", "issued_quantity", "updated_at"])


def return_to_available(product, quantity):
    """Move `quantity` of a single product back from issued -> available.

    Mirror of `issue_available` for the no-reservation return paths. Same locking
    contract as above."""
    if not connection.in_atomic_block:
        raise RuntimeError("return_to_available must be called inside transaction.atomic().")
    if product.issued_quantity < quantity:
        raise InsufficientStock(
            f"Insufficient issued stock for product {product.pk}: "
            f"returning {quantity}, issued {product.issued_quantity}."
        )
    product.issued_quantity -= quantity
    product.available_quantity += quantity
    product.save(update_fields=["issued_quantity", "available_quantity", "updated_at"])


def reserve_for_request(request):
    if not connection.in_atomic_block:
        raise RuntimeError("reserve_for_request must be called inside transaction.atomic().")

    items = list(request.items.order_by("product_id"))
    product_ids = [item.product_id for item in items]
    products = {
        product.pk: product
        for product in InventoryProduct.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
    }

    for item in items:
        quantity = item.accepted_quantity
        if quantity <= 0:
            continue

        product = products[item.product_id]
        if product.available_quantity < quantity:
            raise InsufficientStock(
                f"Insufficient stock for product {product.pk}: "
                f"requested {quantity}, available {product.available_quantity}."
            )

        product.available_quantity -= quantity
        product.reserved_quantity += quantity
        product.save(
            update_fields=[
                "available_quantity",
                "reserved_quantity",
                "updated_at",
            ]
        )


# Dispositions for units rejected as broken at handover.
REJECT_NEEDS_FIX = "needs_fix"  # park on the to-be-fixed shelf (stays in total)
REJECT_REMOVE = "remove"  # scrap it out of inventory entirely (total drops)


def issue_items(request, rejects_by_item=None):
    """Move each accepted item out of `reserved`.

    `rejects_by_item` maps HardwareRequestItem.id -> (broken, disposition) for units
    rejected as broken at handover. Broken units leave `reserved`; with disposition
    'needs_fix' they go to the needs-fix shelf (stays within total), with 'remove' they
    are scrapped (total drops). The rest of the accepted quantity is issued normally.
    """
    if not connection.in_atomic_block:
        raise RuntimeError("issue_items must be called inside transaction.atomic().")

    rejects_by_item = rejects_by_item or {}
    items = list(request.items.order_by("product_id"))
    product_ids = [item.product_id for item in items]
    products = {
        product.pk: product
        for product in InventoryProduct.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
    }

    for item in items:
        accepted = item.accepted_quantity
        if accepted <= 0:
            continue

        broken, disposition = rejects_by_item.get(item.id, (0, REJECT_NEEDS_FIX))
        broken = max(0, int(broken))
        if broken > accepted:
            raise InsufficientStock(
                f"Cannot reject {broken} as broken: only {accepted} accepted."
            )
        issued = accepted - broken

        product = products[item.product_id]
        if product.reserved_quantity < accepted:
            raise InsufficientStock(
                f"Insufficient reserved stock for product {product.pk}: "
                f"requested {accepted}, reserved {product.reserved_quantity}."
            )

        product.reserved_quantity -= accepted
        product.issued_quantity += issued
        update_fields = ["reserved_quantity", "issued_quantity", "updated_at"]
        if broken and disposition == REJECT_REMOVE:
            product.total_quantity -= broken
            update_fields.append("total_quantity")
        elif broken:
            product.needs_fix_quantity += broken
            update_fields.append("needs_fix_quantity")
        product.save(update_fields=update_fields)

        item.issued_quantity = issued
        item.needs_fix_quantity = broken
        item.save(update_fields=["issued_quantity", "needs_fix_quantity"])


def repair_from_needs_fix(product, quantity):
    """Move repaired units off the to-be-fixed shelf back into available stock."""
    if not connection.in_atomic_block:
        raise RuntimeError("repair_from_needs_fix must be called inside transaction.atomic().")
    locked = InventoryProduct.objects.select_for_update().get(pk=product.pk)
    if quantity <= 0 or locked.needs_fix_quantity < quantity:
        raise InsufficientStock(
            f"Cannot repair {quantity}: only {locked.needs_fix_quantity} on the shelf."
        )
    locked.needs_fix_quantity -= quantity
    locked.available_quantity += quantity
    locked.save(update_fields=["needs_fix_quantity", "available_quantity", "updated_at"])
    return locked


def scrap_from_needs_fix(product, quantity):
    """Remove unrepairable units from the to-be-fixed shelf and from inventory (total drops)."""
    if not connection.in_atomic_block:
        raise RuntimeError("scrap_from_needs_fix must be called inside transaction.atomic().")
    locked = InventoryProduct.objects.select_for_update().get(pk=product.pk)
    if quantity <= 0 or locked.needs_fix_quantity < quantity:
        raise InsufficientStock(
            f"Cannot scrap {quantity}: only {locked.needs_fix_quantity} on the shelf."
        )
    locked.needs_fix_quantity -= quantity
    locked.total_quantity -= quantity
    locked.save(update_fields=["needs_fix_quantity", "total_quantity", "updated_at"])
    return locked


def return_items(request, resolutions):
    if not connection.in_atomic_block:
        raise RuntimeError("return_items must be called inside transaction.atomic().")

    items = [resolution["item"] for resolution in resolutions]
    product_ids = [item.product_id for item in items]
    products = {
        product.pk: product
        for product in InventoryProduct.objects.select_for_update()
        .filter(pk__in=product_ids)
        .order_by("pk")
    }

    for resolution in resolutions:
        item = resolution["item"]
        returned = resolution["returned"]
        damaged = resolution["damaged"]
        missing = resolution["missing"]
        quantity = returned + damaged + missing
        if quantity <= 0:
            continue

        product = products[item.product_id]
        if product.issued_quantity < quantity:
            raise InsufficientStock(
                f"Insufficient issued stock for product {product.pk}: "
                f"returning {quantity}, issued {product.issued_quantity}."
            )

        product.issued_quantity -= quantity
        product.available_quantity += returned
        product.damaged_quantity += damaged
        product.lost_quantity += missing
        product.save(
            update_fields=[
                "issued_quantity",
                "available_quantity",
                "damaged_quantity",
                "lost_quantity",
                "updated_at",
            ]
        )

        item.returned_quantity += returned
        item.damaged_quantity += damaged
        item.missing_quantity += missing
        item.save(
            update_fields=[
                "returned_quantity",
                "damaged_quantity",
                "missing_quantity",
            ]
        )
