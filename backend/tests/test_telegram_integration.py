from unittest.mock import Mock
from contextlib import nullcontext
import json

import pytest
from django.test import override_settings

from apps.accounts.models import User
from apps.hardware_requests import notifications
from apps.hardware_requests.models import HardwareRequest, HardwareRequestItem
from apps.integrations.telegram import TelegramDeliveryError, send_message
from tests.return_helpers import authenticated_client, make_accepted_request, make_member, make_product, make_space

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "test-webhook-secret"
WEBHOOK_URL = "/api/v1/integrations/telegram/webhook"


@override_settings(TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_telegram_accept_callback_routes_through_workflow(monkeypatch):
    makerspace = make_space("telegram")
    admin = make_member("telegram-admin", makerspace)
    admin.telegram_user_id = "42"
    admin.save(update_fields=["telegram_user_id"])
    product = make_product(makerspace)
    hardware_request = make_accepted_request(makerspace, product, 1)
    hardware_request.status = HardwareRequest.Status.PENDING_APPROVAL
    hardware_request.save(update_fields=["status"])
    monkeypatch.setattr("apps.evidence.storage.object_exists", Mock(return_value=True))

    response = authenticated_client(admin).post(
        WEBHOOK_URL,
        {
            "callback_query": {
                "from": {"id": 42},
                "data": f"accept:{hardware_request.id}",
            }
        },
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
    )

    assert response.status_code == 200
    hardware_request.refresh_from_db()
    assert hardware_request.status == HardwareRequest.Status.ACCEPTED


@override_settings(TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_unlinked_telegram_actor_is_denied():
    response = authenticated_client(
        User.objects.create_user(
            username="placeholder",
            role=User.Role.SUPERADMIN,
            access_status=User.AccessStatus.ACTIVE,
        )
    ).post(
        WEBHOOK_URL,
        {"callback_query": {"from": {"id": 999}, "data": "accept:1"}},
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
    )

    assert response.status_code == 403


@override_settings(TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_telegram_webhook_rejects_missing_or_wrong_secret():
    # The spoofable `from.id` must never reach the workflow without a valid secret.
    response = authenticated_client(
        User.objects.create_user(
            username="placeholder",
            role=User.Role.SUPERADMIN,
            access_status=User.AccessStatus.ACTIVE,
        )
    ).post(
        WEBHOOK_URL,
        {"callback_query": {"from": {"id": 42}, "data": "accept:1"}},
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong-secret",
    )

    assert response.status_code == 403


@override_settings(TELEGRAM_WEBHOOK_SECRET=WEBHOOK_SECRET)
def test_suspended_telegram_actor_cannot_act():
    makerspace = make_space("telegram-suspended")
    admin = make_member("telegram-suspended-admin", makerspace)
    admin.telegram_user_id = "77"
    admin.access_status = User.AccessStatus.SUSPENDED
    admin.save(update_fields=["telegram_user_id", "access_status"])
    product = make_product(makerspace)
    hardware_request = make_accepted_request(makerspace, product, 1)
    hardware_request.status = HardwareRequest.Status.PENDING_APPROVAL
    hardware_request.save(update_fields=["status"])

    response = authenticated_client(admin).post(
        WEBHOOK_URL,
        {"callback_query": {"from": {"id": 77}, "data": f"accept:{hardware_request.id}"}},
        format="json",
        HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=WEBHOOK_SECRET,
    )

    assert response.status_code == 403
    hardware_request.refresh_from_db()
    assert hardware_request.status == HardwareRequest.Status.PENDING_APPROVAL


def test_suspended_user_cannot_send_telegram_test_alert():
    makerspace = make_space("telegram-test-alert")
    admin = make_member("telegram-alert-admin", makerspace)
    admin.access_status = User.AccessStatus.SUSPENDED
    admin.save(update_fields=["access_status"])

    response = authenticated_client(admin).post(
        "/api/v1/integrations/telegram/test-alert",
        {"makerspace_id": makerspace.id, "message": "hi"},
        format="json",
    )

    assert response.status_code == 403


def test_telegram_delivery_uses_decrypted_makerspace_bot_token(monkeypatch, settings):
    settings.TELEGRAM_API_URL = "https://telegram.test"
    makerspace = make_space("telegram-encrypted-token")
    makerspace.telegram_group_chat_id = "-100123"
    makerspace.set_telegram_bot_token("bot-token")
    makerspace.save(update_fields=["telegram_group_chat_id", "telegram_bot_token"])
    posted = Mock()
    posted.return_value = nullcontext(type("Response", (), {"status": 200})())
    monkeypatch.setattr("urllib.request.urlopen", posted)

    delivered = send_message(makerspace, "hello")

    assert delivered is True
    posted.assert_called_once()
    request = posted.call_args.args[0]
    assert request.full_url == "https://telegram.test/botbot-token/sendMessage"
    assert json.loads(request.data.decode()) == {
        "chat_id": "-100123",
        "text": "hello",
    }
    assert makerspace.telegram_bot_token != "bot-token"


def test_submitted_request_telegram_alert_includes_contact_and_items(monkeypatch):
    makerspace = make_space("telegram-submitted-alert")
    requester = User.objects.create_user(
        username="requester-alert",
        role=User.Role.REQUESTER,
        access_status=User.AccessStatus.ACTIVE,
    )
    product = make_product(makerspace, name="Bench Meter")
    second_product = make_product(makerspace, name="Logic Analyzer")
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        requester_contact_email="requester@example.com",
        requester_contact_phone="+15551234567",
        requested_for="Robotics workshop",
        status=HardwareRequest.Status.PENDING_APPROVAL,
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=2,
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=second_product,
        requested_quantity=3,
    )
    sent = Mock(return_value=True)
    monkeypatch.setattr(notifications, "send_message", sent)
    monkeypatch.setattr(notifications, "_send_templated_email", Mock(return_value=False))

    notifications.notify_request_submitted(hardware_request)

    text = sent.call_args.args[1]
    assert "requester@example.com" in text
    assert "+15551234567" in text
    assert "Robotics workshop" in text
    assert "Bench Meter: 2" in text
    assert "Logic Analyzer: 3" in text
    assert "parse_mode" not in sent.call_args.kwargs
    assert sent.call_args.kwargs["reply_markup"]["inline_keyboard"]


def test_submitted_request_telegram_delivery_error_is_swallowed(monkeypatch):
    makerspace = make_space("telegram-submitted-failure")
    requester = User.objects.create_user(
        username="requester-failure",
        role=User.Role.REQUESTER,
        access_status=User.AccessStatus.ACTIVE,
    )
    product = make_product(makerspace)
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        status=HardwareRequest.Status.PENDING_APPROVAL,
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
    )
    sent = Mock(side_effect=TelegramDeliveryError("delivery failed"))
    monkeypatch.setattr(notifications, "send_message", sent)
    monkeypatch.setattr(notifications, "_send_templated_email", Mock(return_value=False))

    notifications.notify_request_submitted(hardware_request)

    sent.assert_called_once()


def test_submitted_request_telegram_message_stays_within_limit(monkeypatch):
    # A long requested_for must not push the payload past Telegram's 4096-char
    # limit, or the failed send would be swallowed and the alert lost.
    makerspace = make_space("telegram-long-message")
    requester = User.objects.create_user(
        username="requester-long",
        role=User.Role.REQUESTER,
        access_status=User.AccessStatus.ACTIVE,
    )
    product = make_product(makerspace, name="Bench Meter")
    hardware_request = HardwareRequest.objects.create(
        makerspace=makerspace,
        requester=requester,
        requester_username=requester.username,
        requested_for="x" * 9000,
        status=HardwareRequest.Status.PENDING_APPROVAL,
    )
    HardwareRequestItem.objects.create(
        request=hardware_request,
        product=product,
        requested_quantity=1,
    )
    sent = Mock(return_value=True)
    monkeypatch.setattr(notifications, "send_message", sent)
    monkeypatch.setattr(notifications, "_send_templated_email", Mock(return_value=False))

    notifications.notify_request_submitted(hardware_request)

    text = sent.call_args.args[1]
    assert len(text) <= 4096
    assert sent.call_args.kwargs["reply_markup"]["inline_keyboard"]


@override_settings(TELEGRAM_WEBHOOK_SECRET="")
def test_telegram_webhook_fails_closed_when_unconfigured():
    response = authenticated_client(
        User.objects.create_user(
            username="placeholder",
            role=User.Role.SUPERADMIN,
            access_status=User.AccessStatus.ACTIVE,
        )
    ).post(
        WEBHOOK_URL,
        {"callback_query": {"from": {"id": 42}, "data": "accept:1"}},
        format="json",
    )

    assert response.status_code == 403
