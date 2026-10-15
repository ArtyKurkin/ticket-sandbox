"""PostgreSQL protects audit rows even against QuerySet/raw SQL bypasses.

TRUNCATE remains available for Django test flush/privileged maintenance.
SQLite development relies on insert-only models and guarded querysets.
"""
from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION achievements_reject_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Achievement audit rows are append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in ("achievements_achievementevent", "achievements_achievementoperation"):
        schema_editor.execute(f"""CREATE TRIGGER achievements_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION achievements_reject_audit_mutation();""")
    schema_editor.execute("""
        CREATE FUNCTION achievements_protect_source() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'Achievement source facts cannot be deleted';
            END IF;
            IF ROW(OLD.provider, OLD.external_id, OLD.schema_version, OLD.user_id,
                   OLD.context, OLD.payload, OLD.created_at)
               IS DISTINCT FROM
               ROW(NEW.provider, NEW.external_id, NEW.schema_version, NEW.user_id,
                   NEW.context, NEW.payload, NEW.created_at) THEN
                RAISE EXCEPTION 'Achievement source facts are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER achievements_source_fact_guard BEFORE UPDATE OR DELETE
        ON achievements_achievementsourceevent FOR EACH ROW
        EXECUTE FUNCTION achievements_protect_source();
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("achievements_achievementevent", "achievements_achievementoperation"):
        schema_editor.execute(f"DROP TRIGGER achievements_append_only ON {table}")
    schema_editor.execute("DROP TRIGGER achievements_source_fact_guard ON achievements_achievementsourceevent")
    schema_editor.execute("DROP FUNCTION achievements_protect_source()")
    schema_editor.execute("DROP FUNCTION achievements_reject_audit_mutation()")


class Migration(migrations.Migration):
    dependencies = [("achievements", "0003_catalog_v1")]
    operations = [migrations.RunPython(install, uninstall)]
