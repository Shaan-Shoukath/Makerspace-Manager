import uuid

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from apps.evidence.storage import _client, _public_client, StorageUnavailable, object_exists


SCREENSHOT_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


def print_object_key(makerspace_id, kind):
    return f"print/{makerspace_id}/{kind}/{uuid.uuid4().hex}"


def _extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def validate_print_upload(kind, filename, content_type):
    content_type = content_type or ""
    ext = _extension(filename)

    if kind not in {"stl", "screenshot"}:
        raise ValueError("Invalid print upload kind.")

    if kind == "stl":
        if ext not in settings.PRINT_ALLOWED_MODEL_EXT:
            raise ValueError("Unsupported model file extension.")
        if content_type not in settings.PRINT_ALLOWED_MODEL_MIME:
            raise ValueError("Unsupported model file content type.")
        return content_type or "application/octet-stream"

    if ext not in settings.PRINT_ALLOWED_SCREENSHOT_EXT:
        raise ValueError("Unsupported screenshot file extension.")
    if content_type not in settings.PRINT_ALLOWED_SCREENSHOT_MIME:
        raise ValueError("Unsupported screenshot file content type.")
    if SCREENSHOT_MIME_BY_EXT.get(ext) != content_type:
        raise ValueError("Screenshot extension and content type do not match.")
    return content_type


def presigned_print_upload(object_key, content_type):
    try:
        return _public_client().generate_presigned_post(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=object_key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, settings.PRINT_UPLOAD_MAX_BYTES],
            ],
            ExpiresIn=settings.PRINT_URL_TTL_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def print_get_url(object_key):
    try:
        return _public_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_STORAGE_BUCKET_NAME, "Key": object_key},
            ExpiresIn=settings.PRINT_URL_TTL_SECONDS,
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageUnavailable from exc


def print_object_size(object_key):
    if not object_exists(object_key):
        return None

    try:
        response = _client().head_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=object_key,
        )
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = exc.response.get("Error", {}).get("Code")
        if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise StorageUnavailable from exc
    except BotoCoreError as exc:
        raise StorageUnavailable from exc

    return int(response["ContentLength"])
