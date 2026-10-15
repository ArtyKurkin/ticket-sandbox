"""Activate existing v1 thresholds against Ledger policy sandbox-ledger-v1.

No awards/backfill. Platinum remains disabled until checker trust is resolved.
Historical rules, events and snapshots remain untouched.
"""
from django.db import migrations


def configure(apps, schema_editor, automatic):
    Tier = apps.get_model("achievements", "AchievementTier")
    for family, codes in (("sandbox_program", ("silver", "gold")),
                          ("sandbox_first_five_clean_answers", ("gold",))):
        for tier in Tier.objects.using(schema_editor.connection.alias).filter(
                definition__code=family, definition__rule_version=1, code__in=codes, rule_version=1):
            tier.parameters = {**tier.parameters, "automatic": automatic}
            tier.save(update_fields=["parameters"])


def activate(apps, schema_editor):
    configure(apps, schema_editor, True)


def deactivate(apps, schema_editor):
    configure(apps, schema_editor, False)


class Migration(migrations.Migration):
    dependencies = [("achievements", "0005_notifications"), ("sandbox", "0033_ledger_guards")]
    operations = [migrations.RunPython(activate, deactivate)]
