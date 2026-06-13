from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERADMIN = "superadmin", "Super Admin"
        SPACE_MANAGER = "space_manager", "Space Manager"
        GUEST_ADMIN = "guest_admin", "Guest Admin"
        REQUESTER = "requester", "Requester"

    class AccessStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        RESTRICTED = "restricted", "Restricted"
        SUSPENDED = "suspended", "Suspended"

    phone = models.CharField(max_length=32, blank=True)
    external_checkin_user_id = models.CharField(max_length=128, blank=True)
    telegram_user_id = models.CharField(max_length=64, blank=True)
    must_change_password = models.BooleanField(default=False)
    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.REQUESTER,
    )
    access_status = models.CharField(
        max_length=32,
        choices=AccessStatus.choices,
        default=AccessStatus.ACTIVE,
    )
    restriction_reason = models.TextField(blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["external_checkin_user_id"],
                condition=~models.Q(external_checkin_user_id=""),
                name="uniq_external_checkin_user_id",
            ),
            models.UniqueConstraint(
                fields=["telegram_user_id"],
                condition=~models.Q(telegram_user_id=""),
                name="uniq_telegram_user_id",
            ),
        ]
