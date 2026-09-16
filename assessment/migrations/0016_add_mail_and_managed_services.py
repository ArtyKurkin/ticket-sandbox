from django.db import migrations


def add_taxonomy_and_quotas(apps, schema_editor):
    Topic = apps.get_model("assessment", "Topic")
    Skill = apps.get_model("assessment", "Skill")
    ExamBlueprint = apps.get_model(
        "assessment",
        "ExamBlueprint",
    )
    BlueprintSkillQuota = apps.get_model(
        "assessment",
        "BlueprintSkillQuota",
    )

    # ----- Почта -----

    mail_topic, _ = Topic.objects.update_or_create(
        slug="mail",
        defaults={
            "name": "Почта",
            "order": 40,
            "is_active": True,
        },
    )

    mail_skill, _ = Skill.objects.update_or_create(
        topic=mail_topic,
        slug="mail-diagnostics",
        defaults={
            "name": "Почтовая диагностика",
            "order": 1,
            "is_active": True,
        },
    )

    # ----- Управляемые сервисы -----

    managed_topic, _ = Topic.objects.update_or_create(
        slug="managed-services",
        defaults={
            "name": "Управляемые сервисы",
            "order": 50,
            "is_active": True,
        },
    )

    managed_skill, _ = Skill.objects.update_or_create(
        topic=managed_topic,
        slug="managed-services-diagnostics",
        defaults={
            "name": "Диагностика управляемых сервисов",
            "order": 1,
            "is_active": True,
        },
    )

    # Внутренние регламенты оставляем,
    # просто сдвигаем в конец списка.
    Topic.objects.filter(
        slug="internal-regulations",
    ).update(order=60)

    # ----- Blueprint -----

    blueprint = ExamBlueprint.objects.get(
        slug="l1-technical-assessment",
    )

    BlueprintSkillQuota.objects.update_or_create(
        blueprint=blueprint,
        skill=mail_skill,
        defaults={
            "question_count": 2,
            "order": 270,
        },
    )

    BlueprintSkillQuota.objects.update_or_create(
        blueprint=blueprint,
        skill=managed_skill,
        defaults={
            "question_count": 2,
            "order": 280,
        },
    )


def remove_taxonomy_and_quotas(apps, schema_editor):
    Topic = apps.get_model("assessment", "Topic")
    Skill = apps.get_model("assessment", "Skill")
    BlueprintSkillQuota = apps.get_model(
        "assessment",
        "BlueprintSkillQuota",
    )

    topic_slugs = [
        "mail",
        "managed-services",
    ]

    skills = Skill.objects.filter(
        topic__slug__in=topic_slugs,
    )

    # Сначала удаляем квоты,
    # которые ссылаются на навыки.
    BlueprintSkillQuota.objects.filter(
        skill__in=skills,
    ).delete()

    # Потом сами навыки.
    Skill.objects.filter(
        topic__slug__in=topic_slugs,
    ).delete()

    # И только после этого темы.
    Topic.objects.filter(
        slug__in=topic_slugs,
    ).delete()

    # Возвращаем исходный порядок.
    Topic.objects.filter(
        slug="internal-regulations",
    ).update(order=40)


class Migration(migrations.Migration):

    dependencies = [
        ("assessment", "0015_examquestionsnapshot_diagnostic_blocks_and_more"),
    ]

    operations = [
        migrations.RunPython(
            add_taxonomy_and_quotas,
            remove_taxonomy_and_quotas,
        ),
    ]
