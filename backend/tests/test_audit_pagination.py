import pytest

from apps.accounts.models import User
from apps.audit import services as audit
from tests.return_helpers import authenticated_client, make_space, make_user

pytestmark = pytest.mark.django_db


def test_audit_log_endpoint_is_paginated_and_filters_still_apply():
    actor = make_user(
        "audit-superadmin",
        role=User.Role.SUPERADMIN,
        access_status=User.AccessStatus.ACTIVE,
    )
    space = make_space("audit-page")
    other_space = make_space("audit-other")
    for _ in range(25):
        audit.record(actor, "audit.page", makerspace=space, target=space)
    audit.record(actor, "audit.other", makerspace=other_space, target=other_space)

    client = authenticated_client(actor)
    page = client.get("/api/v1/admin/audit-logs")
    filtered = client.get(
        "/api/v1/admin/audit-logs",
        {
            "makerspace": space.id,
            "action": "audit.page",
            "target_type": "makerspaces.makerspace",
            "target_id": str(space.id),
        },
    )

    assert page.status_code == 200
    assert set(page.data) == {"count", "next", "previous", "results"}
    assert page.data["count"] == 26
    assert page.data["next"]
    assert len(page.data["results"]) == 24

    assert filtered.status_code == 200
    assert filtered.data["count"] == 25
    assert filtered.data["next"]
    assert {row["makerspace"] for row in filtered.data["results"]} == {space.id}
    assert {row["action"] for row in filtered.data["results"]} == {"audit.page"}
    assert {row["target_id"] for row in filtered.data["results"]} == {str(space.id)}
