from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Append-only audit event; database triggers are the real mutation guard."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    action = models.CharField(max_length=100)
    target_type = models.CharField(max_length=200, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    makerspace = models.ForeignKey(
        "makerspaces.Makerspace",
        null=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    meta = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["makerspace", "created_at"]),
            models.Index(fields=["action"]),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("AuditLog rows are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog rows are append-only.")

    def __str__(self):
        return f"{self.action} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
