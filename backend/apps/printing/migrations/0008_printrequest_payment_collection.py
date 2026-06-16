from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("printing", "0007_printrequest_filament_grams_used_and_reprint_of"),
    ]

    operations = [
        migrations.AlterField(
            model_name="printrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("accepted", "Accepted"),
                    ("printing", "Printing"),
                    ("completed", "Completed"),
                    ("collected", "Collected"),
                    ("rejected", "Rejected"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="pending",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="printrequest",
            name="price",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=8,
                validators=[MinValueValidator(0)],
            ),
        ),
        migrations.AddField(
            model_name="printrequest",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("none", "None"),
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                ],
                db_index=True,
                default="none",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="printrequest",
            name="paid_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="printrequest",
            name="collected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="printrequest",
            name="collected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="collected_print_requests",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
