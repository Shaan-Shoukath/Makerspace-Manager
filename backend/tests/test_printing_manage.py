from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.makerspaces.models import MakerspaceMembership
from apps.printing.models import FilamentSpool, PrintPrinter, PrintRequest
from tests.test_printing import (
    authenticated_client,
    make_bucket,
    make_member,
    make_print_manager,
    make_request,
    make_space,
    make_user,
)

pytestmark = pytest.mark.django_db


def printer_list_url():
    return reverse("printing:managed-printer-list")


def printer_detail_url(printer):
    return reverse("printing:managed-printer-detail", kwargs={"pk": printer.id})


def spool_list_url():
    return reverse("printing:managed-spool-list")


def spool_detail_url(spool):
    return reverse("printing:managed-spool-detail", kwargs={"pk": spool.id})


def action_url(print_request, action):
    return reverse(f"printing:managed-request-{action}", kwargs={"pk": print_request.id})


def test_managed_printer_create_success_and_validation_error():
    makerspace = make_space("manage-printer-create")
    manager = make_print_manager("manage-printer-create-manager", makerspace)
    client = authenticated_client(manager)

    response = client.post(
        printer_list_url(),
        {
            "makerspace": makerspace.id,
            "name": "Bambu A1",
            "model": "A1 Combo",
            "status": "active",
        },
        format="json",
    )

    assert response.status_code == 201
    printer = PrintPrinter.objects.get(pk=response.data["id"])
    assert printer.makerspace == makerspace
    assert printer.name == "Bambu A1"

    response = client.post(
        printer_list_url(),
        {"makerspace": makerspace.id, "name": "", "status": "active"},
        format="json",
    )

    assert response.status_code == 400
    assert "name" in response.data


def test_managed_spool_create_and_remaining_weight_adjustment():
    makerspace = make_space("manage-spool-create")
    manager = make_print_manager("manage-spool-create-manager", makerspace)
    printer = PrintPrinter.objects.create(makerspace=makerspace, name="Prusa MK4")
    client = authenticated_client(manager)

    response = client.post(
        spool_list_url(),
        {
            "makerspace": makerspace.id,
            "printer": printer.id,
            "material": "PLA",
            "color": "black",
            "brand": "Generic",
            "initial_weight_grams": "1000.00",
            "remaining_weight_grams": "900.00",
        },
        format="json",
    )

    assert response.status_code == 201
    spool = FilamentSpool.objects.get(pk=response.data["id"])
    assert spool.printer == printer
    assert spool.remaining_weight_grams == Decimal("900.00")

    response = client.patch(
        spool_detail_url(spool),
        {"remaining_weight_grams": "750.00"},
        format="json",
    )

    assert response.status_code == 200
    spool.refresh_from_db()
    assert spool.remaining_weight_grams == Decimal("750.00")

    response = client.patch(
        spool_detail_url(spool),
        {"remaining_weight_grams": "1200.00"},
        format="json",
    )

    assert response.status_code == 400
    assert "remaining_weight_grams" in response.data


def test_managed_fail_print_requires_reason_and_stores_reason():
    makerspace = make_space("manage-fail-print")
    bucket = make_bucket(makerspace)
    requester = make_user("manage-fail-requester", access_status=User.AccessStatus.ACTIVE)
    manager = make_print_manager("manage-fail-manager", makerspace)
    print_request = make_request(
        bucket,
        requester,
        status=PrintRequest.Status.PRINTING,
    )

    response = authenticated_client(manager).post(
        action_url(print_request, "fail"),
        {"reason": "Layer shift."},
        format="json",
    )

    assert response.status_code == 200
    print_request.refresh_from_db()
    assert print_request.status == PrintRequest.Status.FAILED
    assert print_request.reason == "Layer shift."


def test_managed_edit_deactivate_is_rbac_scoped_to_makerspace():
    makerspace = make_space("manage-edit-own")
    other_space = make_space("manage-edit-other")
    manager = make_print_manager("manage-edit-manager", makerspace)
    guest = make_member(
        "manage-edit-guest",
        makerspace,
        membership_role=MakerspaceMembership.Role.GUEST_ADMIN,
        role=User.Role.GUEST_ADMIN,
    )
    own_printer = PrintPrinter.objects.create(makerspace=makerspace, name="Own")
    other_printer = PrintPrinter.objects.create(makerspace=other_space, name="Other")
    own_spool = FilamentSpool.objects.create(
        makerspace=makerspace,
        printer=own_printer,
        material="PETG",
        initial_weight_grams=1000,
        remaining_weight_grams=800,
    )
    client = authenticated_client(manager)

    response = client.patch(
        printer_detail_url(own_printer),
        {"model": "MK4S", "status": "maintenance"},
        format="json",
    )
    assert response.status_code == 200
    own_printer.refresh_from_db()
    assert own_printer.model == "MK4S"
    assert own_printer.status == PrintPrinter.Status.MAINTENANCE

    response = client.patch(
        printer_detail_url(own_printer),
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 200
    own_printer.refresh_from_db()
    assert own_printer.is_active is False

    response = client.patch(
        spool_detail_url(own_spool),
        {"is_active": False},
        format="json",
    )
    assert response.status_code == 200
    own_spool.refresh_from_db()
    assert own_spool.is_active is False

    response = client.patch(
        printer_detail_url(other_printer),
        {"model": "Out of scope"},
        format="json",
    )
    assert response.status_code == 404

    response = authenticated_client(guest).patch(
        printer_detail_url(own_printer),
        {"model": "Guest update"},
        format="json",
    )
    assert response.status_code == 403
