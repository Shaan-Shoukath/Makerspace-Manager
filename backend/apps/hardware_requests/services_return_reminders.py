from django.db import transaction
from django.utils import timezone

from apps.accounts import rbac
from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest


def run_return_reminders(*, now=None, limit=200) -> dict:
    now = now or timezone.now()
    limit = max(int(limit), 1)
    # Exclude only ARCHIVED (soft-deleted) makerspaces. A superadmin-hidden space
    # (superadmin_access_enabled=False) is still fully operational for its own staff
    # and borrowers — only the global superadmin's view is blocked — so its overdue
    # loans must still trigger borrower-facing return reminders.
    excluded_makerspace_ids = rbac.archived_makerspace_ids()
    queryset = (
        HardwareRequest.objects.select_related("makerspace", "requester")
        .filter(
            status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ],
            return_due_at__lte=now,
            return_reminder_sent_at__isnull=True,
        )
        .exclude(makerspace_id__in=excluded_makerspace_ids)
        .order_by("return_due_at", "id")[:limit]
    )
    sent_count = 0
    skipped_count = 0
    for hardware_request in queryset:
        with transaction.atomic():
            claimed = HardwareRequest.objects.filter(
                pk=hardware_request.pk,
                return_reminder_sent_at__isnull=True,
            ).update(return_reminder_sent_at=now)
        if not claimed:
            continue

        try:
            sent = notifications.notify_return_due(hardware_request)
        except Exception:
            _reset_reminder_claim(hardware_request.pk, now)
            raise

        if sent:
            sent_count += 1
        else:
            _reset_reminder_claim(hardware_request.pk, now)
            skipped_count += 1

    return {"sent": sent_count, "skipped": skipped_count}


def _reset_reminder_claim(hardware_request_id, claimed_at):
    HardwareRequest.objects.filter(
        pk=hardware_request_id,
        return_reminder_sent_at=claimed_at,
    ).update(return_reminder_sent_at=None)
