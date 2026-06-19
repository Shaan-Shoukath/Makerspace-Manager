from rest_framework.permissions import BasePermission

from apps.accounts import rbac
from apps.accounts.models import User
from apps.makerspaces.origin_scope import staff_origin_scope_allows


def _active_authenticated(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.access_status == User.AccessStatus.ACTIVE
        and not getattr(user, "must_change_password", False)
    )


class CanReviewRequest(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user) or not staff_origin_scope_allows(request, view):
            return False

        return bool(
            rbac.makerspaces_for_action(user, rbac.Action.ACCEPT_REQUEST)
            or rbac.makerspaces_for_action(user, rbac.Action.REJECT_REQUEST)
        )


class CanViewHandoverQueue(BasePermission):
    """Accepted-requests (handover) queue: active staff who can issue somewhere.

    rbac.can() does not consider access_status, so a restricted/suspended staff user
    would otherwise pass a bare IsAuthenticated gate — this enforces active status too."""

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user) or not staff_origin_scope_allows(request, view):
            return False
        return bool(rbac.makerspaces_for_action(user, rbac.Action.ISSUE_REQUEST))


class CanAssignBox(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user) or not staff_origin_scope_allows(request, view):
            return False
        return bool(rbac.makerspaces_for_action(user, rbac.Action.ASSIGN_BOX))


class CanIssueRequest(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user) or not staff_origin_scope_allows(request, view):
            return False
        return bool(rbac.makerspaces_for_action(user, rbac.Action.ISSUE_REQUEST))


class CanIssueDirectLoan(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user) or not staff_origin_scope_allows(request, view):
            return False
        return bool(rbac.makerspaces_for_action(user, rbac.Action.ISSUE_DIRECT_LOAN))


class CanReturnRequest(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user) or not staff_origin_scope_allows(request, view):
            return False
        return bool(rbac.makerspaces_for_action(user, rbac.Action.RETURN_REQUEST))


class CanReturnDirectLoan(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not _active_authenticated(user):
            return False
        return bool(rbac.makerspaces_for_action(user, rbac.Action.RETURN_REQUEST))
