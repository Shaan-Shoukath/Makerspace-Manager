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
        # Send FIRST, mark sent only after a successful delivery. A pre-send claim
        # (timestamp set before the email goes out) is unsafe: if the process is
        # killed or times out mid-send, the row stays flagged-as-sent and the
        # borrower is never reminded again. Send-then-mark is fail-safe — the worst
        # case under concurrent runs is a duplicate reminder, never a silent skip.
        if not notifications.notify_return_due(hardware_request):
            skipped_count += 1
            continue
        with transaction.atomic():
            # Conditional update is the concurrency guard: only the first runner to
            # win the still-null row counts the send, so two concurrent runs can't
            # double-count even if both managed to send the email.
            sent_count += HardwareRequest.objects.filter(
                pk=hardware_request.pk,
                return_reminder_sent_at__isnull=True,
            ).update(return_reminder_sent_at=now)

    return {"sent": sent_count, "skipped": skipped_count}
