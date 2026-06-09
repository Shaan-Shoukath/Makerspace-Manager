from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
CREATE OR REPLACE FUNCTION audit_reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'append-only/immutable table: % not allowed', TG_OP;
END;
$$;

CREATE TRIGGER audit_auditlog_no_update
BEFORE UPDATE ON audit_auditlog
FOR EACH ROW EXECUTE FUNCTION audit_reject_mutation();

CREATE TRIGGER audit_auditlog_no_delete
BEFORE DELETE ON audit_auditlog
FOR EACH ROW EXECUTE FUNCTION audit_reject_mutation();
""",
            reverse_sql="""
DROP TRIGGER IF EXISTS audit_auditlog_no_update ON audit_auditlog;
DROP TRIGGER IF EXISTS audit_auditlog_no_delete ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_reject_mutation();
""",
        ),
    ]
