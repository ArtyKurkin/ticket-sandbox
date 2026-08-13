from django.db import migrations


TOPIC_SLUG = "linux-vds"

CRON_SLUG = "cron-runtime-context"
PANELS_SLUG = "control-panels"

BLUEPRINT_SLUG = "l1-technical-assessment"


def forwards(apps, schema_editor):
    Skill = apps.get_model(
        "assessment",
        "Skill",
    )

    ExamBlueprint = apps.get_model(
        "assessment",
        "ExamBlueprint",
    )

    BlueprintSkillQuota = apps.get_model(
        "assessment",
        "BlueprintSkillQuota",
    )

    cron_skill = Skill.objects.get(
        topic__slug=TOPIC_SLUG,
        slug=CRON_SLUG,
    )

    panels_skill, _ = (
        Skill.objects.update_or_create(
            topic_id=cron_skill.topic_id,
            slug=PANELS_SLUG,
            defaults={
                "name": "Панели управления",
                "description": (
                    "Диагностика FASTPANEL, "
                    "ISPmanager и BitrixVM."
                ),
                "order": cron_skill.order,
                "is_active": True,
            },
        )
    )

    cron_skill.is_active = False
    cron_skill.save(
        update_fields=["is_active"]
    )

    blueprint = ExamBlueprint.objects.get(
        slug=BLUEPRINT_SLUG,
    )

    cron_quota = (
        BlueprintSkillQuota.objects
        .filter(
            blueprint=blueprint,
            skill=cron_skill,
        )
        .first()
    )

    if cron_quota is None:
        return

    panels_quota, created = (
        BlueprintSkillQuota.objects
        .get_or_create(
            blueprint=blueprint,
            skill=panels_skill,
            defaults={
                "question_count": (
                    cron_quota.question_count
                ),
                "order": cron_quota.order,
            },
        )
    )

    if not created:
        panels_quota.question_count = (
            cron_quota.question_count
        )
        panels_quota.order = cron_quota.order
        panels_quota.save(
            update_fields=[
                "question_count",
                "order",
            ]
        )

    cron_quota.delete()


def backwards(apps, schema_editor):
    Skill = apps.get_model(
        "assessment",
        "Skill",
    )

    ExamBlueprint = apps.get_model(
        "assessment",
        "ExamBlueprint",
    )

    BlueprintSkillQuota = apps.get_model(
        "assessment",
        "BlueprintSkillQuota",
    )

    cron_skill = Skill.objects.get(
        topic__slug=TOPIC_SLUG,
        slug=CRON_SLUG,
    )

    panels_skill = Skill.objects.get(
        topic__slug=TOPIC_SLUG,
        slug=PANELS_SLUG,
    )

    blueprint = ExamBlueprint.objects.get(
        slug=BLUEPRINT_SLUG,
    )

    panels_quota = (
        BlueprintSkillQuota.objects
        .filter(
            blueprint=blueprint,
            skill=panels_skill,
        )
        .first()
    )

    if panels_quota is not None:
        cron_quota, created = (
            BlueprintSkillQuota.objects
            .get_or_create(
                blueprint=blueprint,
                skill=cron_skill,
                defaults={
                    "question_count": (
                        panels_quota.question_count
                    ),
                    "order": panels_quota.order,
                },
            )
        )

        if not created:
            cron_quota.question_count = (
                panels_quota.question_count
            )
            cron_quota.order = (
                panels_quota.order
            )
            cron_quota.save(
                update_fields=[
                    "question_count",
                    "order",
                ]
            )

        panels_quota.delete()

    cron_skill.is_active = True
    cron_skill.save(
        update_fields=["is_active"]
    )

    panels_skill.is_active = False
    panels_skill.save(
        update_fields=["is_active"]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("assessment", "0013_examanswer_response_time_seconds_and_more"),
    ]

    operations = [
        migrations.RunPython(
            forwards,
            backwards,
        ),
    ]
