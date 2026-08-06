from django.db import migrations


BLUEPRINT_SLUG = "l1-technical-assessment"


SKILL_QUOTAS = (
    # Linux и VDS — 10
    ("linux-vds", "df-du-open-files"),
    ("linux-vds", "space-inodes-read-only"),
    ("linux-vds", "partitions-mounts-disks"),
    ("linux-vds", "cpu-io-load-average"),
    ("linux-vds", "memory-swap-oom"),
    ("linux-vds", "resource-source-analysis"),
    ("linux-vds", "systemd-startup-failures"),
    ("linux-vds", "service-log-port-correlation"),
    ("linux-vds", "ssh-ftp-diagnostic-layer"),
    ("linux-vds", "cron-runtime-context"),

    # Web — 8
    ("web", "http-error-layer"),
    ("web", "next-step-from-logs"),
    ("web", "virtual-host-routing"),
    ("web", "reverse-proxy-redirects"),
    ("web", "php-endpoint-version"),
    ("web", "php-fpm-pool-limits"),
    ("web", "website-instability"),
    ("web", "database-availability-performance"),

    # Сети — 8
    ("networks", "ip-vs-port"),
    ("networks", "port-vs-application"),
    ("networks", "mtr-intermediate-loss"),
    ("networks", "latency-route-protocol"),
    ("networks", "firewall-layer"),
    ("networks", "firewall-rule-errors"),
    ("networks", "ipv6-routing-listening"),
    ("networks", "network-quality"),
)


def seed_l1_technical_blueprint(apps, schema_editor):
    ExamBlueprint = apps.get_model(
        "assessment",
        "ExamBlueprint",
    )
    BlueprintSkillQuota = apps.get_model(
        "assessment",
        "BlueprintSkillQuota",
    )
    Skill = apps.get_model(
        "assessment",
        "Skill",
    )

    blueprint, _ = ExamBlueprint.objects.update_or_create(
        slug=BLUEPRINT_SLUG,
        defaults={
            "name": "Техническая оценка L1",
            "level": "l1",
            "pass_percentage": 85,
            "allow_back_navigation": False,
            "shuffle_questions": True,
            "shuffle_answer_options": True,
            "is_active": False,
        },
    )

    for position, (
        topic_slug,
        skill_slug,
    ) in enumerate(
        SKILL_QUOTAS,
        start=1,
    ):
        try:
            skill = Skill.objects.get(
                topic__slug=topic_slug,
                slug=skill_slug,
            )
        except Skill.DoesNotExist as error:
            raise RuntimeError(
                (
                    "Не найден навык для шаблона L1: "
                    f"{topic_slug} → {skill_slug}"
                )
            ) from error

        BlueprintSkillQuota.objects.update_or_create(
            blueprint=blueprint,
            skill=skill,
            defaults={
                "question_count": 1,
                "order": position * 10,
            },
        )


def remove_l1_technical_blueprint(
    apps,
    schema_editor,
):
    ExamBlueprint = apps.get_model(
        "assessment",
        "ExamBlueprint",
    )

    ExamBlueprint.objects.filter(
        slug=BLUEPRINT_SLUG,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        # Оставь зависимость, которую Django
        # автоматически указал в пустой миграции.
        (
            "assessment",
            "0007_blueprintskillquota_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            seed_l1_technical_blueprint,
            remove_l1_technical_blueprint,
        ),
    ]
