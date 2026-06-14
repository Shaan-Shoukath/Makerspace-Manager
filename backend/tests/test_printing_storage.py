import re

import pytest

from apps.printing.models import PrintRequestFile
from apps.printing.storage import print_object_key, validate_print_upload
from tests.test_printing import make_bucket, make_request, make_space, make_user

pytestmark = pytest.mark.django_db


def test_print_object_key_returns_expected_shape():
    key = print_object_key(42, "stl")

    assert re.fullmatch(r"print/42/stl/[0-9a-f]{32}", key)


def test_validate_print_upload_accepts_allowed_model_and_screenshot():
    assert (
        validate_print_upload("stl", "part.stl", "application/octet-stream")
        == "application/octet-stream"
    )
    assert validate_print_upload("screenshot", "shot.png", "image/png") == "image/png"


@pytest.mark.parametrize(
    ("kind", "filename", "content_type"),
    [
        ("stl", "evil.exe", "application/octet-stream"),
        ("screenshot", "x.png", "application/pdf"),
        ("bogus", "a.stl", ""),
    ],
)
def test_validate_print_upload_rejects_bad_input(kind, filename, content_type):
    with pytest.raises(ValueError):
        validate_print_upload(kind, filename, content_type)


def test_print_request_file_can_be_created_unattached():
    makerspace = make_space("printing-storage-files")
    bucket = make_bucket(makerspace)
    requester = make_user("printing-storage-requester")
    make_request(bucket, requester)

    upload = PrintRequestFile.objects.create(
        print_request=None,
        makerspace=makerspace,
        kind=PrintRequestFile.Kind.STL,
        object_key="print/1/stl/abc123",
        content_type="application/octet-stream",
        size_bytes=123,
        owner_checkin_user_id="checkin-user-1",
    )

    assert upload.print_request is None
    assert upload.attached_at is None
    assert upload.makerspace == makerspace
