from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncDay, TruncHour, TruncMonth

from apps.printing.models import FilamentSpool, PrintRequest


STATUS_KEYS = {
    PrintRequest.Status.COMPLETED: "completed",
    PrintRequest.Status.FAILED: "failed",
    PrintRequest.Status.REJECTED: "rejected",
    PrintRequest.Status.PENDING: "pending",
    PrintRequest.Status.PRINTING: "printing",
    PrintRequest.Status.ACCEPTED: "accepted",
}


def build_printing_report(makerspace_id=None, *, include_makerspace=False):
    requests = PrintRequest.objects.all()
    spools = FilamentSpool.objects.all()
    if makerspace_id is not None:
        requests = requests.filter(bucket__makerspace_id=makerspace_id)
        spools = spools.filter(makerspace_id=makerspace_id)

    return {
        "totals": _totals(requests),
        "printer_hours": _printer_hours(requests, include_makerspace),
        "filament_used": _filament_used(spools, include_makerspace),
        "top_requesters": _top_requesters(requests, include_makerspace),
        "total_grams_used": _total_spool_grams_used(spools),
        "filament_estimated_by_period": {
            "by_month": _estimated_filament_by_period(requests, TruncMonth, "%Y-%m"),
            "by_day": _estimated_filament_by_period(requests, TruncDay, "%Y-%m-%d"),
            "by_hour": _estimated_filament_by_period(
                requests,
                TruncHour,
                "%Y-%m-%d %H:00",
            ),
        },
    }


def _totals(requests):
    rows = requests.values("status").annotate(count=Count("id"))
    counts = {row["status"]: row["count"] for row in rows}
    totals = {"total_requests": sum(counts.values())}
    for status, key in STATUS_KEYS.items():
        totals[key] = counts.get(status, 0)
    return totals


def _printer_hours(requests, include_makerspace):
    completed = requests.filter(
        status=PrintRequest.Status.COMPLETED,
        printer__isnull=False,
    )
    values = ["printer_id", "printer__name"]
    if include_makerspace:
        values.append("printer__makerspace_id")

    rows = (
        completed.values(*values)
        .annotate(
            completed_requests=Count("id"),
            minutes=Sum("estimated_minutes"),
        )
        .order_by("printer__makerspace_id", "printer__name", "printer_id")
    )

    data = []
    for row in rows:
        item = {
            "printer_id": row["printer_id"],
            "printer_name": row["printer__name"],
            "completed_requests": row["completed_requests"],
            "hours": round((row["minutes"] or 0) / 60, 1),
        }
        if include_makerspace:
            item["makerspace_id"] = row["printer__makerspace_id"]
        data.append(item)
    return data


def _top_requesters(requests, include_makerspace):
    # Who submits the most 3D-print jobs: request count + total quantity per requester,
    # ranked high-to-low. In aggregate mode each row is per requester+makerspace
    # (mirrors printer_hours/filament_used).
    values = ["requester_id", "requester__username"]
    if include_makerspace:
        values.append("bucket__makerspace_id")
    rows = (
        requests.values(*values)
        .annotate(request_count=Count("id"), items=Sum("quantity"))
        .order_by("-request_count", "-items")
    )
    data = []
    for row in rows:
        item = {
            "requester_id": row["requester_id"],
            "requester": row["requester__username"],
            "requests": row["request_count"],
            "items": row["items"] or 0,
        }
        if include_makerspace:
            item["makerspace_id"] = row["bucket__makerspace_id"]
        data.append(item)
    return data


def _filament_used(spools, include_makerspace):
    data = []
    for spool in spools.order_by("makerspace_id", "material", "color", "id"):
        item = {
            "spool_id": spool.id,
            "material": spool.material,
            "color": spool.color,
            "grams_used": _decimal_to_float(_spool_grams_used(spool)),
            "remaining_grams": _decimal_to_float(spool.remaining_weight_grams),
        }
        if include_makerspace:
            item["makerspace_id"] = spool.makerspace_id
        data.append(item)
    return data


def _total_spool_grams_used(spools):
    total = Decimal("0")
    for spool in spools.only(
        "initial_weight_grams",
        "remaining_weight_grams",
    ):
        total += _spool_grams_used(spool)
    return _decimal_to_float(total)


def _spool_grams_used(spool):
    return max(
        spool.initial_weight_grams - spool.remaining_weight_grams,
        Decimal("0"),
    )


def _estimated_filament_by_period(requests, trunc, period_format):
    rows = (
        requests.filter(
            status=PrintRequest.Status.COMPLETED,
            completed_at__isnull=False,
            estimated_filament_grams__isnull=False,
        )
        .annotate(period=trunc("completed_at"))
        .values("period")
        .annotate(grams=Sum("estimated_filament_grams"))
        .order_by("period")
    )
    return [
        {
            "period": row["period"].strftime(period_format),
            "grams": _decimal_to_float(row["grams"] or Decimal("0")),
        }
        for row in rows
    ]


def _decimal_to_float(value):
    return round(float(value), 2)
