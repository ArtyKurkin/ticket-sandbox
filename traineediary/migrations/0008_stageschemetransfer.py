import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("traineediary", "0007_classify_stage_catalog")]
    operations = [
        migrations.CreateModel(
            name="StageSchemeTransferBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_snapshot_sha256", models.CharField(max_length=64, unique=True)),
                ("baseline", models.JSONField()),
                ("verification", models.JSONField(default=dict)),
                ("as_of", models.DateField()),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("reverted_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="StageSchemeTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_scheme", models.CharField(default="legacy", max_length=16)),
                ("source_stage_started_at", models.DateField()),
                ("source_history_ids", models.JSONField(default=list)),
                ("progress_basis", models.JSONField()),
                ("audit_sha256", models.CharField(max_length=64)),
                ("source_sha256", models.CharField(max_length=64)),
                ("migrated_at", models.DateTimeField(auto_now_add=True)),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers", to="traineediary.stageschemetransferbatch")),
                ("journey", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="scheme_transfer", to="traineediary.traineejourney")),
                ("source_open_history", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="traineediary.stagehistory")),
                ("source_stage", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="traineediary.traineestage")),
                ("target_stage", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="traineediary.traineestage")),
            ],
        ),
        # Never drop provenance as a side effect of reversing migration history.
        # The explicit data rollback restores original fields and retains records.
        migrations.RunPython(migrations.RunPython.noop),
    ]
