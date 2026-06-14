"""Procurement access rules, derived from the existing RBAC action matrix.

No new permission action is introduced: a makerspace admin (MANAGE_MAKERSPACE,
held by Space Manager + Superadmin) owns both streams; hardware staff
(EDIT_INVENTORY) own the hardware stream; print managers (MANAGE_PRINTING) own
the printing stream. Visibility and write authority are both keyed off these."""
from apps.accounts import rbac
from apps.procurement.models import ToBuyItem

HARDWARE = ToBuyItem.Kind.HARDWARE
PRINTING = ToBuyItem.Kind.PRINTING


def viewable_kinds(actor, makerspace_id):
    """Streams the actor may see in this makerspace (admin sees both)."""
    if rbac.can(actor, rbac.Action.MANAGE_MAKERSPACE, makerspace_id):
        return [HARDWARE, PRINTING]
    kinds = []
    if rbac.can(actor, rbac.Action.EDIT_INVENTORY, makerspace_id):
        kinds.append(HARDWARE)
    if rbac.can(actor, rbac.Action.MANAGE_PRINTING, makerspace_id):
        kinds.append(PRINTING)
    return kinds


def can_use(actor, makerspace_id):
    """True if the actor has any procurement stream in this makerspace."""
    return bool(viewable_kinds(actor, makerspace_id))


def derive_kind(actor, makerspace_id, requested=None):
    """Decide the stream for a new item from the actor's role.

    Makerspace admins / superadmin may target either stream (default hardware);
    everyone else is auto-tagged: hardware staff -> hardware, print -> printing."""
    if rbac.can(actor, rbac.Action.MANAGE_MAKERSPACE, makerspace_id):
        return requested if requested in (HARDWARE, PRINTING) else HARDWARE
    if rbac.can(actor, rbac.Action.EDIT_INVENTORY, makerspace_id):
        return HARDWARE
    return PRINTING


def can_manage_kind(actor, makerspace_id, kind):
    """True if the actor may create/edit/delete items of this stream."""
    if kind == PRINTING:
        return rbac.can(actor, rbac.Action.MANAGE_PRINTING, makerspace_id)
    return rbac.can(actor, rbac.Action.EDIT_INVENTORY, makerspace_id)
