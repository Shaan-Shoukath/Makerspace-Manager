from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("evidence", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
CREATE OR REPLACE FUNCTION evidence_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'append-only/immutable table: % not allowed', TG_OP;
END;
$$;

CREATE TRIGGER evidence_evidencephoto_no_update
BEFORE UPDATE ON evidence_evidencephoto
FOR EACH ROW EXECUTE FUNCTION evidence_reject_mutation();

CREATE TRIGGER evidence_evidencephoto_no_delete
BEFORE DELETE ON evidence_evidencephoto
FOR EACH ROW EXECUTE FUNCTION evidence_reject_mutation();
""",
            reverse_sql="""
DROP TRIGGER IF EXISTS evidence_evidencephoto_no_update ON evidence_evidencephoto;
DROP TRIGGER IF EXISTS evidence_evidencephoto_no_delete ON evidence_evidencephoto;
DROP FUNCTION IF EXISTS evidence_reject_mutation();
""",
        ),
    ]
