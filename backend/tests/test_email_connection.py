from unittest.mock import patch

import pytest

from apps.integrations.email import makerspace_mail_connection
from apps.makerspaces.models import Makerspace

pytestmark = pytest.mark.django_db


def _connection_kwargs(space):
    # Assert the flags email.py passes to get_connection (independent of the test
    # mail backend, which doesn't expose use_ssl/use_tls).
    with patch("apps.integrations.email.get_connection") as get_connection:
        makerspace_mail_connection(space)
    return get_connection.call_args.kwargs


def test_implicit_ssl_disables_starttls():
    # use_ssl (465) and use_tls (587 STARTTLS) are mutually exclusive; when both
    # flags are set, SSL wins and STARTTLS is turned off.
    space = Makerspace.objects.create(
        name="smtp-ssl",
        slug="smtp-ssl",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_use_tls=True,
        smtp_use_ssl=True,
    )
    kwargs = _connection_kwargs(space)
    assert kwargs["use_ssl"] is True
    assert kwargs["use_tls"] is False


def test_starttls_used_when_ssl_off():
    space = Makerspace.objects.create(
        name="smtp-tls",
        slug="smtp-tls",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_use_tls=True,
        smtp_use_ssl=False,
    )
    kwargs = _connection_kwargs(space)
    assert kwargs["use_ssl"] is False
    assert kwargs["use_tls"] is True


def test_no_smtp_host_returns_no_connection():
    space = Makerspace.objects.create(name="smtp-none", slug="smtp-none")
    connection, from_email = makerspace_mail_connection(space)
    assert connection is None
