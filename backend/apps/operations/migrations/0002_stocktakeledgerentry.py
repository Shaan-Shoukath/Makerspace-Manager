import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0008_remove_inventoryproduct_qty_sum_within_total_and_more"),
        ("makerspaces", "0014_makerspace_archived_at_makerspace_archived_by"),
        ("operations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StocktakeLedgerEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bucket", models.CharField(choices=[("available", "Available"), ("damaged", "Damaged"), ("lost", "Lost")], max_length=20)),
                ("delta", models.IntegerField()),
                ("old_asset_status", models.CharField(blank=True, max_length=20)),
                ("new_asset_status", models.CharField(blank=True, max_length=20)),
                ("reason", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("asset", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="inventory.inventoryasset")),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("line", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ledger_entries", to="operations.stocktakeline")),
                ("makerspace", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stocktake_ledger_entries", to="makerspaces.makerspace")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+", to="inventory.inventoryproduct")),
                ("stocktake", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ledger_entries", to="operations.stocktakesession")),
            ],
        ),
        migrations.AddConstraint(
            model_name="stocktakeledgerentry",
            constraint=models.UniqueConstraint(fields=("stocktake", "line", "bucket"), name="uniq_stocktake_ledger_line_bucket"),
        ),
        migrations.AddIndex(
            model_name="stocktakeledgerentry",
            index=models.Index(fields=["makerspace", "created_at"], name="operations__makersp_777e0c_idx"),
        ),
        migrations.AddIndex(
            model_name="stocktakeledgerentry",
            index=models.Index(fields=["stocktake", "line"], name="operations__stockta_ad58fa_idx"),
        ),
    ]
