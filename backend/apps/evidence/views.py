import logging

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts import rbac
from apps.accounts.permissions import (
    HasMakerspaceAction,
    IsStaff,
    MakerspaceScopedQuerysetMixin,
    StaffAPIView,
)
from apps.audit import services as audit
from apps.evidence.models import EvidencePhoto
from apps.evidence.serializers import (
    EvidenceGetResponseSerializer,
    EvidenceUrlRequestSerializer,
    EvidenceUrlResponseSerializer,
)
from apps.evidence.storage import (
    StorageUnavailable,
    evidence_object_key,
    object_exists,
    presigned_get_url,
    presigned_upload,
)
from apps.makerspaces.models import Makerspace

logger = logging.getLogger(__name__)


class EvidenceUploadUrlView(StaffAPIView):
    required_action = rbac.Action.UPLOAD_EVIDENCE
    permission_classes = StaffAPIView.permission_classes + [HasMakerspaceAction]

    @extend_schema(
        request=EvidenceUrlRequestSerializer,
        responses={
            201: EvidenceUrlResponseSerializer,
            400: OpenApiResponse(description="Invalid evidence upload request."),
            403: OpenApiResponse(description="Insufficient makerspace permission."),
            503: OpenApiResponse(description="Evidence storage is unavailable."),
        },
    )
    def post(self, request, *args, **kwargs):
        makerspace_id = self.kwargs["makerspace_id"]
        serializer = EvidenceUrlRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        evidence_type = serializer.validated_data["evidence_type"]
        content_type = serializer.validated_data["content_type"]
        object_key = evidence_object_key(makerspace_id, evidence_type)

        try:
            upload = presigned_upload(object_key, content_type)
        except StorageUnavailable:
            logger.warning(
                "evidence_upload_url_storage_unavailable",
                extra={"makerspace_id": makerspace_id, "evidence_type": evidence_type},
                exc_info=True,
            )
            return Response(status=503)

        with transaction.atomic():
            makerspace = get_object_or_404(Makerspace, pk=makerspace_id)
            photo = EvidencePhoto.objects.create(
                makerspace=makerspace,
                evidence_type=evidence_type,
                object_key=object_key,
                uploaded_by=request.user,
            )
            audit.record(
                request.user,
                "evidence.upload_url_issued",
                makerspace=makerspace,
                target=photo,
            )

        logger.info(
            "evidence_upload_url_issued",
            extra={
                "evidence_id": photo.pk,
                "makerspace_id": makerspace_id,
                "evidence_type": evidence_type,
            },
        )
        data = {
            "evidence_id": photo.pk,
            "upload_url": upload["url"],
            "fields": upload["fields"],
            "object_key": object_key,
        }
        return Response(EvidenceUrlResponseSerializer(data).data, status=201)


class EvidenceDetailView(MakerspaceScopedQuerysetMixin, generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsStaff]
    queryset = EvidencePhoto.objects.all()
    serializer_class = EvidenceGetResponseSerializer

    @extend_schema(
        responses={
            200: EvidenceGetResponseSerializer,
            404: OpenApiResponse(description="Evidence was not found."),
            409: OpenApiResponse(description="Evidence object has not been uploaded."),
            503: OpenApiResponse(description="Evidence storage is unavailable."),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        photo = self.get_object()

        try:
            exists = object_exists(photo.object_key)
        except StorageUnavailable:
            logger.warning(
                "evidence_head_storage_unavailable",
                extra={"evidence_id": photo.pk, "makerspace_id": photo.makerspace_id},
                exc_info=True,
            )
            return Response(status=503)
        if not exists:
            return Response(status=409)

        try:
            url = presigned_get_url(photo.object_key)
        except StorageUnavailable:
            logger.warning(
                "evidence_get_url_storage_unavailable",
                extra={"evidence_id": photo.pk, "makerspace_id": photo.makerspace_id},
                exc_info=True,
            )
            return Response(status=503)

        audit.record(
            request.user,
            "evidence.viewed",
            makerspace=photo.makerspace,
            target=photo,
        )
        return Response(
            EvidenceGetResponseSerializer(
                {"url": url, "expires_in": settings.EVIDENCE_URL_TTL_SECONDS}
            ).data
        )
