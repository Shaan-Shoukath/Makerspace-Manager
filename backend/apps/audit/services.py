from django.db import models

from apps.audit.models import AuditLog


def record(actor, action, *, makerspace=None, target=None, target_type="", meta=None):
    target_id = ""
    if isinstance(target, models.Model):
        target_type = target._meta.label_lower
        target_id = str(target.pk)

    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        makerspace=makerspace,
        meta=meta or {},
    )
