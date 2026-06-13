from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils.crypto import get_random_string
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import rbac
from apps.accounts.models import User
from apps.admin_api import bulk_import
from apps.admin_api.permissions import IsActiveStaff, IsActiveSuperAdmin, require_action
from apps.admin_api.serializers import (
    AuditLogSerializer,
    BulkImportPreviewSerializer,
    CategoryAdminSerializer,
    InventoryQuantityAdjustmentSerializer,
    InventoryProductAdminSerializer,
    MakerspaceSerializer,
    RestrictUserSerializer,
    ReturnPolicySerializer,
    StaffCreateSerializer,
    StaffMembershipSerializer,
    TenantFrontendSerializer,
    UserSerializer,
)
from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.inventory.models import Category, InventoryProduct
from apps.makerspaces.models import Makerspace, MakerspaceMembership, TenantFrontend
from apps.makerspaces.guards import require_module
from apps.openapi import BULK_IMPORT_ROWS_EXAMPLE, RESTRICT_USER_EXAMPLE
from apps.operations.models import InventoryAdjustment


@extend_schema(tags=["Admin makerspaces"], summary="List or create makerspaces")
class MakerspaceListCreateView(generics.ListCreateAPIView):
    serializer_class = MakerspaceSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = None

    def get_queryset(self):
        return rbac.scope_by_action(self.request.user, rbac.Action.VIEW_INVENTORY, Makerspace.objects.all(), field="id").order_by("name")

    def perform_create(self, serializer):
        if not (self.request.user.is_superuser or self.request.user.role == User.Role.SUPERADMIN):
            raise PermissionDenied()
        instance = serializer.save(created_by=self.request.user)
        audit.record(
            self.request.user,
            "makerspace.created",
            makerspace=instance,
            target=instance,
        )


@extend_schema(tags=["Admin makerspaces"], summary="Retrieve or update a makerspace")
class MakerspaceDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = MakerspaceSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        action = (
            rbac.Action.MANAGE_MAKERSPACE
            if self.request.method == "PATCH"
            else rbac.Action.VIEW_INVENTORY
        )
        return rbac.scope_by_action(self.request.user, action, Makerspace.objects.all(), field="id")

    def perform_update(self, serializer):
        instance = serializer.save()
        audit.record(
            self.request.user,
            "makerspace.updated",
            makerspace=instance,
            target=instance,
        )


@extend_schema(tags=["Admin makerspaces"], summary="Retrieve or update return policy")
class ReturnPolicyView(generics.RetrieveUpdateAPIView):
    serializer_class = ReturnPolicySerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_action(self.request.user, rbac.Action.ACCEPT_REQUEST, makerspace_id)
        return get_object_or_404(Makerspace, pk=makerspace_id)

    def perform_update(self, serializer):
        instance = serializer.save()
        audit.record(
            self.request.user,
            "makerspace.return_policy_updated",
            makerspace=instance,
            target=instance,
            meta={"default_loan_days": instance.default_loan_days},
        )


@extend_schema(tags=["Tenant bootstrap"], summary="List or create registered tenant frontends")
class TenantFrontendListCreateView(generics.ListCreateAPIView):
    serializer_class = TenantFrontendSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.MANAGE_MAKERSPACE, makerspace_id)
        return TenantFrontend.objects.filter(makerspace_id=makerspace_id).order_by("frontend_type", "hostname")

    def perform_create(self, serializer):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.MANAGE_MAKERSPACE, makerspace_id)
        frontend = serializer.save(makerspace_id=makerspace_id, created_by=self.request.user)
        audit.record(
            self.request.user,
            "tenant_frontend.created",
            makerspace=frontend.makerspace,
            target=frontend,
        )


@extend_schema(tags=["Tenant bootstrap"], summary="Retrieve or update registered tenant frontend")
class TenantFrontendDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = TenantFrontendSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return rbac.scope_by_action(
            self.request.user,
            rbac.Action.MANAGE_MAKERSPACE,
            TenantFrontend.objects.select_related("makerspace"),
        )

    def perform_update(self, serializer):
        frontend = serializer.save()
        audit.record(
            self.request.user,
            "tenant_frontend.updated",
            makerspace=frontend.makerspace,
            target=frontend,
        )


@extend_schema(tags=["Admin inventory"], summary="List or create inventory products")
class InventoryListCreateView(generics.ListCreateAPIView):
    serializer_class = InventoryProductAdminSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        return InventoryProduct.objects.filter(makerspace_id=makerspace_id).order_by("name")

    def perform_create(self, serializer):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.EDIT_INVENTORY, makerspace_id)
        _assert_box_in_makerspace(serializer.validated_data.get("box"), makerspace_id)
        _assert_category_in_makerspace(
            serializer.validated_data.get("category"), makerspace_id
        )
        instance = serializer.save(makerspace_id=makerspace_id)
        audit.record(
            self.request.user,
            "inventory.created",
            makerspace=instance.makerspace,
            target=instance,
        )


@extend_schema(tags=["Admin inventory"], summary="Retrieve or update inventory product")
class InventoryDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = InventoryProductAdminSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        action = (
            rbac.Action.EDIT_INVENTORY
            if self.request.method == "PATCH"
            else rbac.Action.VIEW_INVENTORY
        )
        return rbac.scope_by_action(self.request.user, action, InventoryProduct.objects.select_related("makerspace", "box"))

    def perform_update(self, serializer):
        _assert_box_in_makerspace(
            serializer.validated_data.get("box"), serializer.instance.makerspace_id
        )
        _assert_category_in_makerspace(
            serializer.validated_data.get("category"), serializer.instance.makerspace_id
        )
        instance = serializer.save()
        audit.record(
            self.request.user,
            "inventory.updated",
            makerspace=instance.makerspace,
            target=instance,
        )


class InventoryQuantityAdjustmentView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Admin inventory"],
        summary="Adjust inventory quantity buckets",
        request=InventoryQuantityAdjustmentSerializer,
        responses={200: InventoryProductAdminSerializer},
    )
    def post(self, request, pk, *args, **kwargs):
        product = get_object_or_404(
            rbac.scope_by_action(
                request.user,
                rbac.Action.VIEW_INVENTORY,
                InventoryProduct.objects.select_related("makerspace"),
            ),
            pk=pk,
        )
        require_module(product.makerspace_id, "staff_admin")
        require_action(request.user, rbac.Action.EDIT_INVENTORY, product.makerspace_id)
        serializer = InventoryQuantityAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            locked = InventoryProduct.objects.select_for_update().get(pk=product.pk)
            available = locked.available_quantity + data["delta_available"]
            damaged = locked.damaged_quantity + data["delta_damaged"]
            lost = locked.lost_quantity + data["delta_lost"]
            if available < 0 or damaged < 0 or lost < 0:
                raise ValidationError("Quantity adjustment cannot make a bucket negative.")
            locked.available_quantity = available
            locked.damaged_quantity = damaged
            locked.lost_quantity = lost
            locked.total_quantity = (
                locked.available_quantity
                + locked.reserved_quantity
                + locked.issued_quantity
                + locked.damaged_quantity
                + locked.lost_quantity
            )
            locked.save(
                update_fields=[
                    "available_quantity",
                    "damaged_quantity",
                    "lost_quantity",
                    "total_quantity",
                    "updated_at",
                ]
            )
            InventoryAdjustment.objects.create(
                makerspace=locked.makerspace,
                product=locked,
                delta_available=data["delta_available"],
                delta_damaged=data["delta_damaged"],
                delta_lost=data["delta_lost"],
                reason=data["reason"],
                created_by=request.user,
            )
            audit.record(
                request.user,
                "inventory.quantity_adjusted",
                makerspace=locked.makerspace,
                target=locked,
                meta={
                    "delta_available": data["delta_available"],
                    "delta_damaged": data["delta_damaged"],
                    "delta_lost": data["delta_lost"],
                    "reason": data["reason"],
                },
            )
        return Response(InventoryProductAdminSerializer(locked).data)


@extend_schema(tags=["Admin inventory"], summary="List or create inventory categories")
class CategoryListCreateView(generics.ListCreateAPIView):
    serializer_class = CategoryAdminSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.VIEW_INVENTORY, makerspace_id)
        return (
            Category.objects.filter(makerspace_id=makerspace_id)
            .annotate(product_count=Count("products"))
            .order_by("display_order", "name")
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["makerspace_id"] = self.kwargs["makerspace_id"]
        return context

    def perform_create(self, serializer):
        makerspace_id = self.kwargs["makerspace_id"]
        require_module(makerspace_id, "staff_admin")
        require_action(self.request.user, rbac.Action.EDIT_INVENTORY, makerspace_id)
        try:
            instance = serializer.save(makerspace_id=makerspace_id)
        except IntegrityError:
            raise ValidationError(
                {
                    "slug": "A category with this slug already exists in this makerspace."
                }
            )
        audit.record(
            self.request.user,
            "category.created",
            makerspace=instance.makerspace,
            target=instance,
        )


@extend_schema(
    tags=["Admin inventory"],
    summary="Retrieve, update, or delete inventory category",
)
class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CategoryAdminSerializer
    permission_classes = [IsActiveStaff]
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return rbac.scope_by_action(
            self.request.user,
            rbac.Action.VIEW_INVENTORY,
            Category.objects.select_related("makerspace").annotate(
                product_count=Count("products")
            ),
        )

    def get_object(self):
        category = super().get_object()
        require_module(category.makerspace_id, "staff_admin")
        return category

    def perform_update(self, serializer):
        require_action(
            self.request.user,
            rbac.Action.EDIT_INVENTORY,
            serializer.instance.makerspace_id,
        )
        try:
            instance = serializer.save()
        except IntegrityError:
            raise ValidationError(
                {
                    "slug": "A category with this slug already exists in this makerspace."
                }
            )
        audit.record(
            self.request.user,
            "category.updated",
            makerspace=instance.makerspace,
            target=instance,
        )

    def perform_destroy(self, instance):
        require_action(
            self.request.user,
            rbac.Action.EDIT_INVENTORY,
            instance.makerspace_id,
        )
        detached_product_count = instance.products.count()
        audit.record(
            self.request.user,
            "category.deleted",
            makerspace=instance.makerspace,
            target=instance,
            meta={"detached_product_count": detached_product_count},
        )
        instance.delete()


def _assert_box_in_makerspace(box, makerspace_id):
    """A product may only point at a box in its own makerspace (tenant isolation)."""
    if box is not None and box.makerspace_id != makerspace_id:
        raise ValidationError({"box": "Box belongs to a different makerspace."})


def _assert_category_in_makerspace(category, makerspace_id):
    """A product may only point at a category in its own makerspace."""
    if category is not None and category.makerspace_id != makerspace_id:
        raise ValidationError(
            {"category": "Category belongs to a different makerspace."}
        )


def _rows_from_upload(uploaded_file):
    """Parse an uploaded import file, mapping bad-input parse errors to 400.

    rows_from_upload raises ValueError (incl. JSONDecodeError/UnicodeDecodeError,
    and normalized corrupt-XLSX errors) on malformed files; without this they'd
    surface as a 500 for what is really user input."""
    try:
        return bulk_import.rows_from_upload(uploaded_file)
    except ValueError as exc:
        raise ValidationError({"file": str(exc) or "Uploaded file could not be parsed."})


class BulkImportPreviewView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Bulk import"],
        summary="Preview inventory bulk import",
        request=BulkImportPreviewSerializer,
        responses={200: OpenApiResponse(description="Import preview with row errors.")},
        examples=[BULK_IMPORT_ROWS_EXAMPLE],
    )
    def post(self, request, makerspace_id, *args, **kwargs):
        makerspace = get_object_or_404(Makerspace, pk=makerspace_id)
        require_module(makerspace, "bulk_import")
        require_action(request.user, rbac.Action.EDIT_INVENTORY, makerspace_id)
        serializer = BulkImportPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data.get("rows")
        if rows is None:
            rows = _rows_from_upload(serializer.validated_data["file"])
        return Response(
            bulk_import.preview_import(
                makerspace,
                rows,
                serializer.validated_data.get("mapping") or {},
            )
        )


class BulkImportApplyView(APIView):
    permission_classes = [IsActiveStaff]

    @extend_schema(
        tags=["Bulk import"],
        summary="Apply inventory bulk import",
        request=BulkImportPreviewSerializer,
        responses={200: OpenApiResponse(description="Import application result.")},
        examples=[BULK_IMPORT_ROWS_EXAMPLE],
    )
    def post(self, request, makerspace_id, *args, **kwargs):
        makerspace = get_object_or_404(Makerspace, pk=makerspace_id)
        require_module(makerspace, "bulk_import")
        require_action(request.user, rbac.Action.EDIT_INVENTORY, makerspace_id)
        serializer = BulkImportPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rows = serializer.validated_data.get("rows")
        if rows is None:
            rows = _rows_from_upload(serializer.validated_data["file"])
        result = bulk_import.apply_import(
            request.user,
            makerspace,
            rows,
            serializer.validated_data.get("mapping") or {},
        )
        return Response(result, status=status.HTTP_200_OK)


@extend_schema(tags=["Admin users"], summary="List or create staff memberships")
class StaffListCreateView(generics.ListCreateAPIView):
    serializer_class = StaffMembershipSerializer
    permission_classes = [IsActiveStaff]

    def get_queryset(self):
        target_role = self.kwargs["role"]
        scope = rbac.makerspaces_for_action(self.request.user, rbac.Action.MANAGE_STAFF)
        queryset = MakerspaceMembership.objects.select_related("user", "makerspace").filter(
            role=target_role
        )
        if scope is rbac.ALL:
            return queryset.order_by("user__username")
        if target_role in (
            MakerspaceMembership.Role.PRINT_MANAGER,
            MakerspaceMembership.Role.INVENTORY_MANAGER,
        ):
            manage_scope = rbac.makerspaces_for_action(
                self.request.user,
                rbac.Action.MANAGE_MAKERSPACE,
            )
            if manage_scope is rbac.ALL:
                return queryset.order_by("user__username")
            return queryset.filter(makerspace_id__in=manage_scope).order_by(
                "user__username"
            )
        return queryset.none()

    def create(self, request, *args, **kwargs):
        serializer = StaffCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        target_role = self.kwargs["role"]
        if data["role"] != target_role:
            raise ValidationError({"role": "Role does not match endpoint."})
        if not _can_create_staff_role(request.user, target_role, data["makerspace_id"]):
            raise PermissionDenied()
        # A superadmin can target any makerspace_id, including a nonexistent one. Validate
        # before writing: otherwise get_or_create commits the user, then the membership FK
        # fails -> 500 and an orphaned staff account. Wrap both writes in one transaction so
        # a membership failure rolls back the user creation too.
        if not Makerspace.objects.filter(pk=data["makerspace_id"]).exists():
            raise ValidationError({"makerspace_id": "Makerspace does not exist."})
        with transaction.atomic():
            user, created = User.objects.get_or_create(
                username=data["username"],
                defaults={
                    "email": data.get("email", ""),
                    "first_name": data.get("first_name", ""),
                    "last_name": data.get("last_name", ""),
                    "role": _global_role_for_membership(target_role),
                    "password": make_password(data.get("password") or get_random_string(32)),
                },
            )
            membership, _ = MakerspaceMembership.objects.update_or_create(
                user=user,
                makerspace_id=data["makerspace_id"],
                defaults={"role": target_role},
            )
        audit.record(
            request.user,
            "staff.created" if created else "staff.membership_updated",
            makerspace=membership.makerspace,
            target=user,
            meta={"membership_role": target_role},
        )
        return Response(StaffMembershipSerializer(membership).data, status=201)


def _global_role_for_membership(target_role):
    if target_role == MakerspaceMembership.Role.SPACE_MANAGER:
        return User.Role.SPACE_MANAGER
    if target_role == MakerspaceMembership.Role.GUEST_ADMIN:
        return User.Role.GUEST_ADMIN
    if target_role == MakerspaceMembership.Role.INVENTORY_MANAGER:
        return User.Role.REQUESTER
    return User.Role.REQUESTER


def _can_create_staff_role(user, target_role, makerspace_id):
    if user.is_superuser or user.role == User.Role.SUPERADMIN:
        return True
    if target_role not in (
        MakerspaceMembership.Role.PRINT_MANAGER,
        MakerspaceMembership.Role.INVENTORY_MANAGER,
    ):
        return False
    return rbac.can(user, rbac.Action.MANAGE_MAKERSPACE, makerspace_id)


class RestrictUserView(APIView):
    permission_classes = [IsActiveSuperAdmin]

    @extend_schema(
        tags=["Admin users"],
        summary="Restrict or suspend a user",
        request=RestrictUserSerializer,
        responses={200: UserSerializer},
        examples=[RESTRICT_USER_EXAMPLE],
    )
    def post(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        serializer = RestrictUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.access_status = serializer.validated_data["status"]
        user.restriction_reason = serializer.validated_data["reason"]
        user.save(update_fields=["access_status", "restriction_reason"])
        audit.record(
            request.user,
            "user.access_restricted",
            target=user,
            meta={"status": user.access_status, "reason": user.restriction_reason},
        )
        return Response(UserSerializer(user).data)


class RestoreUserAccessView(APIView):
    permission_classes = [IsActiveSuperAdmin]

    @extend_schema(tags=["Admin users"], summary="Restore user access", request=None, responses={200: UserSerializer})
    def post(self, request, pk, *args, **kwargs):
        user = get_object_or_404(User, pk=pk)
        user.access_status = User.AccessStatus.ACTIVE
        user.restriction_reason = ""
        user.save(update_fields=["access_status", "restriction_reason"])
        audit.record(request.user, "user.access_restored", target=user)
        return Response(UserSerializer(user).data)


class AuditLogPagination(PageNumberPagination):
    page_size = 24


@extend_schema(tags=["Admin users"], summary="List audit log entries", parameters=[
    OpenApiParameter("makerspace", int, OpenApiParameter.QUERY), OpenApiParameter("action", str, OpenApiParameter.QUERY),
    OpenApiParameter("target_type", str, OpenApiParameter.QUERY), OpenApiParameter("target_id", str, OpenApiParameter.QUERY),
])
class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsActiveStaff]
    pagination_class = AuditLogPagination

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor", "makerspace").order_by("-created_at")
        queryset = rbac.scope_by_action(self.request.user, rbac.Action.VIEW_AUDIT, queryset)
        makerspace_id = self.request.query_params.get("makerspace")
        action = self.request.query_params.get("action")
        target_type, target_id = (
            self.request.query_params.get("target_type"),
            self.request.query_params.get("target_id"),
        )
        filters = {}
        if makerspace_id:
            filters["makerspace_id"] = makerspace_id
        if action:
            filters["action"] = action
        if target_type:
            filters["target_type"] = target_type
        if target_id:
            filters["target_id"] = target_id
        if filters:
            queryset = queryset.filter(**filters)
        return queryset
