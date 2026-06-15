from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.audit import services as audit
from apps.hardware_requests.workflow_utils import get_or_create_requester
from apps.printing.models import PrintBucket, PrintRequest, PrintRequestFile
from apps.printing.storage import print_object_size


def submit_public_print_request(makerspace, data, result):
    with transaction.atomic():
        requester = get_or_create_requester(result.external_id)
        if requester.access_status != User.AccessStatus.ACTIVE:
            raise PermissionDenied("Requester is not active.")

        bucket = PrintBucket.objects.filter(
            pk=data["bucket_id"],
            makerspace=makerspace,
            is_active=True,
        ).first()
        if bucket is None:
            raise ValidationError({"bucket_id": "Invalid or inactive bucket."})

        request = PrintRequest.objects.create(
            bucket=bucket,
            requester=requester,
            title=data["title"],
            description=data.get("description", ""),
            project_brief=data.get("project_brief", ""),
            preferred_settings=data.get("preferred_settings", ""),
            material=data.get("material", ""),
            color=data.get("color", ""),
            quantity=data.get("quantity", 1),
            source_link=data.get("source_link", ""),
            contact_email=data.get("contact_email", "").strip(),
            contact_phone=data.get("contact_phone", "").strip(),
            status=PrintRequest.Status.PENDING,
        )

        file_ids = data.get("file_ids") or []
        if file_ids:
            locked = list(
                PrintRequestFile.objects.select_for_update().filter(
                    id__in=file_ids,
                    owner_checkin_user_id=result.external_id,
                    makerspace=makerspace,
                    attached_at__isnull=True,
                )
            )
            if len(locked) != len(set(file_ids)):
                raise ValidationError(
                    {
                        "file_ids": (
                            "One or more uploads are invalid, already used, or not yours."
                        )
                    }
                )

            now = timezone.now()
            for upload in locked:
                size = print_object_size(upload.object_key)
                if size is None:
                    raise ValidationError(
                        {"file_ids": "An uploaded file was not found in storage."}
                    )
                if size > settings.PRINT_UPLOAD_MAX_BYTES:
                    raise ValidationError(
                        {"file_ids": "An uploaded file exceeds the size limit."}
                    )
                upload.print_request = request
                upload.attached_at = now
                upload.size_bytes = size
                upload.save(
                    update_fields=["print_request", "attached_at", "size_bytes"]
                )

        audit.record(requester, "print.submitted", makerspace=makerspace, target=request)
        return request
