from django.db import migrations

MODULE = "procurement"


def enable_procurement(apps, schema_editor):
    # Backfill the new per-makerspace "procurement" module flag onto existing
    # makerspaces so the To-Buy feature is available by default (new makerspaces
    # get it via DEFAULT_ENABLED_MODULES). A makerspace can still disable it later.
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    for makerspace in Makerspace.objects.all():
        modules = list(makerspace.enabled_modules or [])
        if MODULE not in modules:
            modules.append(MODULE)
            makerspace.enabled_modules = modules
            makerspace.save(update_fields=["enabled_modules"])


def disable_procurement(apps, schema_editor):
    Makerspace = apps.get_model("makerspaces", "Makerspace")
    for makerspace in Makerspace.objects.all():
        modules = [m for m in (makerspace.enabled_modules or []) if m != MODULE]
        makerspace.enabled_modules = modules
        makerspace.save(update_fields=["enabled_modules"])


class Migration(migrations.Migration):
    dependencies = [
        ("makerspaces", "0010_makerspace_default_loan_days"),
    ]

    operations = [
        migrations.RunPython(enable_procurement, disable_procurement),
    ]
