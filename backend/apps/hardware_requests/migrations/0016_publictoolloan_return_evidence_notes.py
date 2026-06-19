import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evidence", "0003_evidencephoto_purge_delete_guard"),
        ("hardware_requests", "0015_hardwarerequest_hwreq_ms_status_created_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="publictoolloan",
            name="return_evidence",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="evidence.evidencephoto",
            ),
        ),
        migrations.AddField(
            model_name="publictoolloan",
            name="return_notes",
            field=models.TextField(blank=True, default=""),
        ),
    ]
