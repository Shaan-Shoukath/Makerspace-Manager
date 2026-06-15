import uuid
from types import SimpleNamespace

from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.apiclients.throttling import ClientTierRateThrottle
from apps.checkin import client as checkin
from apps.makerspaces.lookup import get_public_makerspace
from apps.makerspaces.platform import module_enabled
from apps.printing import public_workflow
from apps.printing.models import PrintRequest, PrintRequestFile
from apps.printing.public_serializers import (
    PrintCheckinVerifyRequestSerializer,
    PrintCheckinVerifyResponseSerializer,
    PrintPresignRequestSerializer,
    PrintPresignResponseSerializer,
    PrintRequestSubmitResponseSerializer,
    PrintRequestSubmitSerializer,
    PublicPrintStatusSerializer,
)
from apps.printing.storage import (
    presigned_print_upload,
    print_object_key,
    validate_print_upload,
)


def _require_module(makerspace):
    if not module_enabled(makerspace, "printing"):
        raise ValidationError({"module": "printing is disabled for this makerspace."})


def _honeypot_filled(payload):
    try:
        value = payload.get("website", "")
    except AttributeError:
        return False
    return bool(str(value).strip())


class PrintCheckinVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "checkin_verify"

    @extend_schema(
        tags=["Public printing"],
        auth=[],
        request=PrintCheckinVerifyRequestSerializer,
        responses={200: PrintCheckinVerifyResponseSerializer},
    )
    def post(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        serializer = PrintCheckinVerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = checkin.verify(makerspace, serializer.validated_data["identifier"])
        return Response({"username": result.username, "external_id": result.external_id})


class PrintUploadPresignView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "print_request_submit"

    @extend_schema(
        tags=["Public printing"],
        auth=[],
        request=PrintPresignRequestSerializer,
        responses={201: PrintPresignResponseSerializer},
    )
    def post(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        serializer = PrintPresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = checkin.verify(makerspace, data["identifier"])
        try:
            content_type = validate_print_upload(
                data["kind"],
                data["filename"],
                data.get("content_type", ""),
            )
        except ValueError as exc:
            raise ValidationError({"file": str(exc)}) from exc

        object_key = print_object_key(makerspace.id, data["kind"])
        upload_file = PrintRequestFile.objects.create(
            makerspace=makerspace,
            kind=data["kind"],
            object_key=object_key,
            content_type=content_type,
            owner_checkin_user_id=result.external_id,
        )
        upload = presigned_print_upload(object_key, content_type)
        return Response(
            {"file_id": upload_file.id, "upload": upload},
            status=status.HTTP_201_CREATED,
        )


class PrintRequestSubmitView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "print_request_submit"

    @extend_schema(
        tags=["Public printing"],
        auth=[],
        request=PrintRequestSubmitSerializer,
        responses={201: PrintRequestSubmitResponseSerializer},
    )
    def post(self, request, makerspace_slug):
        makerspace = get_public_makerspace(makerspace_slug)
        _require_module(makerspace)
        if _honeypot_filled(request.data):
            decoy = SimpleNamespace(
                public_token=uuid.uuid4(),
                status=PrintRequest.Status.PENDING,
            )
            return Response(
                PrintRequestSubmitResponseSerializer(decoy).data,
                status=status.HTTP_201_CREATED,
            )

        serializer = PrintRequestSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = checkin.verify(makerspace, serializer.validated_data["identifier"])
        print_request = public_workflow.submit_public_print_request(
            makerspace,
            serializer.validated_data,
            result,
        )
        return Response(
            PrintRequestSubmitResponseSerializer(print_request).data,
            status=status.HTTP_201_CREATED,
        )


class PublicPrintStatusView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    throttle_classes = [ClientTierRateThrottle]
    throttle_scope = "request_status"
    serializer_class = PublicPrintStatusSerializer
    lookup_field = "public_token"
    queryset = PrintRequest.objects.all()

    @extend_schema(
        tags=["Public printing"],
        auth=[],
        responses={200: PublicPrintStatusSerializer},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
