import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
CHANGE_PASSWORD = "/api/v1/auth/change-password"


def test_setup_instance_default_superadmin_must_change_password(monkeypatch):
    monkeypatch.delenv("SETUP_SUPERADMIN_USERNAME", raising=False)
    monkeypatch.delenv("SETUP_SUPERADMIN_PASSWORD", raising=False)

    call_command("setup_instance")

    user = get_user_model().objects.get(username="superadmin")
    assert user.must_change_password is True
    assert user.check_password("super123")


def test_setup_instance_explicit_password_does_not_force_change(monkeypatch):
    monkeypatch.delenv("SETUP_SUPERADMIN_USERNAME", raising=False)
    monkeypatch.delenv("SETUP_SUPERADMIN_PASSWORD", raising=False)

    call_command(
        "setup_instance",
        username="explicit-superadmin",
        password="Explicit-Strong-123",
    )

    user = get_user_model().objects.get(username="explicit-superadmin")
    assert user.must_change_password is False
    assert user.check_password("Explicit-Strong-123")


def test_login_and_me_include_must_change_password():
    get_user_model().objects.create_user(
        username="must-change",
        email="must-change@example.com",
        password="Current-Strong-123",
        role=User.Role.SPACE_MANAGER,
        access_status=User.AccessStatus.ACTIVE,
        must_change_password=True,
    )
    client = APIClient()

    login = client.post(
        LOGIN,
        {"username": "must-change", "password": "Current-Strong-123"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    me = client.get(ME)

    assert login.status_code == 200
    assert login.data["user"]["must_change_password"] is True
    assert me.status_code == 200
    assert me.data["must_change_password"] is True


def test_change_password_validates_updates_and_audits():
    user = get_user_model().objects.create_user(
        username="password-user",
        email="password-user@example.com",
        password="Current-Strong-123",
        role=User.Role.SPACE_MANAGER,
        access_status=User.AccessStatus.ACTIVE,
        must_change_password=True,
    )
    client = APIClient()
    login = client.post(
        LOGIN,
        {"username": "password-user", "password": "Current-Strong-123"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    wrong_current = client.post(
        CHANGE_PASSWORD,
        {"current_password": "wrong", "new_password": "New-Strong-123"},
        format="json",
    )
    equal_password = client.post(
        CHANGE_PASSWORD,
        {
            "current_password": "Current-Strong-123",
            "new_password": "Current-Strong-123",
        },
        format="json",
    )
    weak_password = client.post(
        CHANGE_PASSWORD,
        {"current_password": "Current-Strong-123", "new_password": "short"},
        format="json",
    )
    changed = client.post(
        CHANGE_PASSWORD,
        {"current_password": "Current-Strong-123", "new_password": "New-Strong-123"},
        format="json",
    )

    assert wrong_current.status_code == 400
    assert "current_password" in wrong_current.data
    assert equal_password.status_code == 400
    assert "new_password" in equal_password.data
    assert weak_password.status_code == 400
    assert "new_password" in weak_password.data
    assert changed.status_code == 200
    assert changed.data == {"detail": "Password updated."}

    user.refresh_from_db()
    assert user.must_change_password is False
    assert authenticate(username="password-user", password="New-Strong-123") == user
    assert AuditLog.objects.filter(
        actor=user,
        action="user.password_changed",
        target_type="accounts.user",
        target_id=str(user.id),
    ).exists()
