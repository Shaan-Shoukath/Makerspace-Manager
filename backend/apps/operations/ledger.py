from datetime import datetime, timezone

from django.db.models import F

from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem, PublicToolLoan


def ledger_rows(makerspace_id=None):
    rows = [*_request_rows(makerspace_id), *_loan_rows(makerspace_id)]
    floor = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(rows, key=lambda row: row["since"] or floor, reverse=True)


def _request_rows(makerspace_id):
    queryset = (
        HardwareRequestItem.objects.select_related("product", "request")
        .filter(
            request__status__in=[
                HardwareRequest.Status.ISSUED,
                HardwareRequest.Status.PARTIALLY_RETURNED,
            ],
            request__public_tool_loan__isnull=True,
        )
        .annotate(
            outstanding=(
                F("issued_quantity")
                - F("returned_quantity")
                - F("damaged_quantity")
                - F("missing_quantity")
            )
        )
        .filter(outstanding__gt=0)
    )
    if makerspace_id is not None:
        queryset = queryset.filter(request__makerspace_id=makerspace_id)

    return [
        {
            "source": "request",
            "item_name": item.product.name,
            "holder": _request_holder(item.request),
            "quantity": item.outstanding,
            "since": item.request.issued_at,
            "due": item.request.return_due_at,
            "makerspace_id": item.request.makerspace_id,
            "reference_id": item.request_id,
            "status": item.request.status,
        }
        for item in queryset.order_by("-request__issued_at", "request_id", "id")
    ]


def _loan_rows(makerspace_id):
    # Every outstanding PublicToolLoan, regardless of source. This covers public
    # self-checkout AND admin direct handouts (both create a PublicToolLoan whose
    # backing HardwareRequest is excluded from _request_rows). Without this, items
    # handed out directly would be invisible in a ledger meant to show all stock OUT.
    queryset = PublicToolLoan.objects.select_related("requester").filter(
        status=PublicToolLoan.Status.CHECKED_OUT,
    )
    if makerspace_id is not None:
        queryset = queryset.filter(makerspace_id=makerspace_id)

    return [
        {
            "source": (
                "self_checkout"
                if loan.source == PublicToolLoan.Source.PUBLIC_SELF_CHECKOUT
                else "direct_handout"
            ),
            "item_name": loan.target_label,
            "holder": loan.requester.username,
            "quantity": 1,
            "since": loan.checked_out_at,
            "due": loan.due_at,
            "makerspace_id": loan.makerspace_id,
            "reference_id": loan.id,
            "status": loan.status,
        }
        for loan in queryset.order_by("-checked_out_at", "id")
    ]


def _request_holder(request):
    return (
        request.requester_username
        or request.requester_contact_email
        or request.requester_contact_phone
    )
