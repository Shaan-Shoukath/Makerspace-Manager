from uuid import uuid4

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.printing.models import PrintRequest, PrintRequestFile
from tests.test_printing import make_bucket, make_space

pytestmark = pytest.mark.django_db


def enable_printing(makerspace):
    makerspace.enabled_modules = ["printing"]
    makerspace.save(update_fields=["enabled_modules"])


def public_client():
    return APIClient()


def submit_url(makerspace):
    return reverse(
        "printing:public-request-submit",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def presign_url(makerspace):
    return reverse(
        "printing:public-upload-presign",
        kwargs={"makerspace_slug": makerspace.slug},
    )


def status_url(public_token):
    return reverse(
        "printing:public-request-status",
        kwargs={"public_token": str(public_token)},
    )


def mock_upload(monkeypatch):
    monkeypatch.setattr(
        "apps.printing.public_views.presigned_print_upload",
        lambda object_key, content_type: {
            "url": "http://minio/printing",
            "fields": {"key": object_key, "Content-Type": content_type},
        },
    )


def test_public_submit_creates_pending_request():
    makerspace = make_space("public-print-submit")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)

    response = public_client().post(
        submit_url(makerspace),
        {"identifier": "u@e.com", "bucket_id": bucket.id, "title": "Bracket"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["public_token"]
    assert response.data["status"] == PrintRequest.Status.PENDING
    created = PrintRequest.objects.get()
    assert created.requester.external_checkin_user_id == "u@e.com"


def test_honeypot_returns_decoy_and_creates_nothing():
    makerspace = make_space("public-print-honeypot")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    before = PrintRequest.objects.count()

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "X",
            "website": "bot",
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["status"] == PrintRequest.Status.PENDING
    assert PrintRequest.objects.count() == before


def test_module_off_blocks_submit():
    makerspace = make_space("public-print-off")
    makerspace.enabled_modules = ["public_inventory"]
    makerspace.save(update_fields=["enabled_modules"])
    bucket = make_bucket(makerspace)

    response = public_client().post(
        submit_url(makerspace),
        {"identifier": "u@e.com", "bucket_id": bucket.id, "title": "Bracket"},
        format="json",
    )

    assert response.status_code == 400


def test_status_lookup_by_token_hides_pii():
    makerspace = make_space("public-print-status")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    client = public_client()
    client.post(
        submit_url(makerspace),
        {"identifier": "u@e.com", "bucket_id": bucket.id, "title": "Bracket"},
        format="json",
    )
    print_request = PrintRequest.objects.get()

    response = client.get(status_url(print_request.public_token))

    assert response.status_code == 200
    assert set(response.data.keys()) == {
        "public_token",
        "status",
        "title",
        "created_at",
        "accepted_at",
        "started_at",
        "completed_at",
    }


def test_status_unknown_token_404():
    response = public_client().get(status_url(uuid4()))

    assert response.status_code == 404


def test_presign_rejects_bad_mime_and_accepts_good(monkeypatch):
    makerspace = make_space("public-print-presign")
    enable_printing(makerspace)
    mock_upload(monkeypatch)
    client = public_client()

    response = client.post(
        presign_url(makerspace),
        {
            "identifier": "u@e.com",
            "kind": "screenshot",
            "filename": "x.png",
            "content_type": "application/pdf",
        },
        format="json",
    )
    assert response.status_code == 400

    response = client.post(
        presign_url(makerspace),
        {
            "identifier": "u@e.com",
            "kind": "stl",
            "filename": "p.stl",
            "content_type": "application/octet-stream",
        },
        format="json",
    )
    assert response.status_code == 201
    assert "file_id" in response.data
    assert "upload" in response.data


def test_submit_rejects_foreign_file_id(monkeypatch):
    makerspace = make_space("public-print-foreign-file")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    upload = PrintRequestFile.objects.create(
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key=f"print/{makerspace.id}/stl/foreign",
        content_type="application/octet-stream",
        owner_checkin_user_id="other",
    )
    monkeypatch.setattr("apps.printing.public_workflow.print_object_size", lambda key: 10)
    before = PrintRequest.objects.count()

    response = public_client().post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "Bracket",
            "file_ids": [upload.id],
        },
        format="json",
    )

    assert response.status_code == 400
    assert PrintRequest.objects.count() == before


def test_submit_attaches_owned_file(monkeypatch):
    makerspace = make_space("public-print-owned-file")
    enable_printing(makerspace)
    bucket = make_bucket(makerspace)
    mock_upload(monkeypatch)
    client = public_client()
    response = client.post(
        presign_url(makerspace),
        {
            "identifier": "u@e.com",
            "kind": "stl",
            "filename": "p.stl",
            "content_type": "application/octet-stream",
        },
        format="json",
    )
    file_id = response.data["file_id"]
    monkeypatch.setattr("apps.printing.public_workflow.print_object_size", lambda key: 123)

    response = client.post(
        submit_url(makerspace),
        {
            "identifier": "u@e.com",
            "bucket_id": bucket.id,
            "title": "Bracket",
            "file_ids": [file_id],
        },
        format="json",
    )

    assert response.status_code == 201
    upload = PrintRequestFile.objects.get(pk=file_id)
    assert upload.attached_at is not None
    assert upload.print_request is not None
    assert upload.size_bytes == 123
