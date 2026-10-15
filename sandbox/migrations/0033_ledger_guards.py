from django.db import migrations
from django.db.models import Max
from django.conf import settings
from django.utils import timezone

TABLES = [
    "sandboxledgerboundary",
    "sandboxprogrammanifest",
    "sandboxattemptcoverage",
    "sandboxevidencegap",
    "technicalcheckexecution",
    "technicalcheckexecutionevent",
    "sandboxenvironmentevent",
    "sandboxanswersubmission",
    "sandboxanswerreviewevent",
]


def install(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    ceiling = (
        apps.get_model(app_label, model_name)
        .objects.using(schema_editor.connection.alias)
        .aggregate(n=Max("pk"))["n"]
        or 0
    )
    apps.get_model("sandbox", "SandboxLedgerBoundary").objects.using(
        schema_editor.connection.alias
    ).create(
        pk=1, enabled_at=timezone.now(), version=1, initial_user_id_ceiling=ceiling
    )
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE FUNCTION sandbox_ledger_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Sandbox ledger is append-only'; END; $$ LANGUAGE plpgsql;"
    )
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER sandbox_ledger_guard BEFORE UPDATE OR DELETE ON sandbox_{table} FOR EACH ROW EXECUTE FUNCTION sandbox_ledger_immutable()"
        )
    schema_editor.execute(
        """CREATE FUNCTION sandbox_ledger_attempt_change() RETURNS trigger AS $$
    BEGIN
      IF current_setting('sandbox.ledger_writer',true) IS DISTINCT FROM 'on'
      AND ROW(OLD.user_id,OLD.task_id,OLD.attempt_number,OLD.status,OLD.attempts_count,OLD.restart_count,
        OLD.started_at,OLD.finished_at,OLD.technical_passed_at,OLD.check_status,OLD.check_started_at,OLD.check_finished_at,
        OLD.environment_status,OLD.environment_started_at,OLD.environment_finished_at,OLD.mentor_decision,OLD.mentor_reviewed_by_id,OLD.mentor_reviewed_at,OLD.container_id,OLD.container_name,OLD.terminal_container_name)
      IS DISTINCT FROM ROW(NEW.user_id,NEW.task_id,NEW.attempt_number,NEW.status,NEW.attempts_count,NEW.restart_count,
        NEW.started_at,NEW.finished_at,NEW.technical_passed_at,NEW.check_status,NEW.check_started_at,NEW.check_finished_at,
        NEW.environment_status,NEW.environment_started_at,NEW.environment_finished_at,NEW.mentor_decision,NEW.mentor_reviewed_by_id,NEW.mentor_reviewed_at,NEW.container_id,NEW.container_name,NEW.terminal_container_name)
      AND EXISTS(SELECT 1 FROM sandbox_sandboxattemptcoverage WHERE attempt_id=OLD.id) THEN
        INSERT INTO sandbox_sandboxevidencegap(attempt_id,reason,source,recorded_at) VALUES(OLD.id,'unsupported_update','database',CURRENT_TIMESTAMP);
      END IF; RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    CREATE TRIGGER sandbox_ledger_projection_change BEFORE UPDATE ON sandbox_taskattempt FOR EACH ROW EXECUTE FUNCTION sandbox_ledger_attempt_change();"""
    )


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "DROP TRIGGER sandbox_ledger_projection_change ON sandbox_taskattempt"
    )
    schema_editor.execute("DROP FUNCTION sandbox_ledger_attempt_change()")
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER sandbox_ledger_guard ON sandbox_{table}")
    schema_editor.execute("DROP FUNCTION sandbox_ledger_immutable()")


class Migration(migrations.Migration):
    dependencies = [("sandbox", "0032_evidence_ledger")]
    operations = [migrations.RunPython(install, uninstall)]
