from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import User


def user_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_superuser": user.is_superuser,
        "must_change_password": user.must_change_password,
        "makerspaces": [
            {"id": m.makerspace_id, "slug": m.makerspace.slug, "role": m.role}
            for m in user.makerspace_memberships.select_related("makerspace")
        ],
    }


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)  # raises AuthenticationFailed on bad creds/inactive
        if self.user.access_status != User.AccessStatus.ACTIVE:
            raise AuthenticationFailed("Account access is restricted.", code="access_denied")
        data["user"] = user_payload(self.user)
        return data
