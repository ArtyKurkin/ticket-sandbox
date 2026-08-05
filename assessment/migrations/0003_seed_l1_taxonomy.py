from django.db import migrations


TOPICS = (
    {
        "name": "Linux и VDS",
        "slug": "linux-vds",
        "description": (
            "Диагностика Linux-серверов, файловых систем, "
            "ресурсов, сервисов и подключений."
        ),
        "order": 10,
    },
    {
        "name": "Web",
        "slug": "web",
        "description": (
            "Диагностика веб-серверов, PHP, сайтов "
            "и баз данных."
        ),
        "order": 20,
    },
    {
        "name": "Сети",
        "slug": "networks",
        "description": (
            "Диагностика сетевой доступности, маршрутов, "
            "портов, файрволлов и IPv6."
        ),
        "order": 30,
    },
    {
        "name": "Внутренние регламенты",
        "slug": "internal-regulations",
        "description": (
            "Зоны ответственности, безопасность действий "
            "и порядок работы с обращениями."
        ),
        "order": 40,
    },
)


SKILLS = {
    "linux-vds": (
        {
            "name": "Расхождение df и du",
            "slug": "df-du-open-files",
            "description": (
                "Понимает причины расхождения df и du, "
                "включая удалённые, но открытые файлы."
            ),
            "order": 10,
        },
        {
            "name": "Место, inode и read-only",
            "slug": "space-inodes-read-only",
            "description": (
                "Отличает нехватку места, законченные inode "
                "и переход файловой системы в read-only."
            ),
            "order": 20,
        },
        {
            "name": "Разделы и точки монтирования",
            "slug": "partitions-mounts-disks",
            "description": (
                "Диагностирует проблемы с разделами, "
                "точками монтирования и дополнительными дисками."
            ),
            "order": 30,
        },
        {
            "name": "CPU, I/O и load average",
            "slug": "cpu-io-load-average",
            "description": (
                "Различает нагрузку на CPU, ожидание диска "
                "и причины высокого load average."
            ),
            "order": 40,
        },
        {
            "name": "Память, swap и OOM Killer",
            "slug": "memory-swap-oom",
            "description": (
                "Диагностирует нехватку памяти, работу swap "
                "и завершение процессов через OOM Killer."
            ),
            "order": 50,
        },
        {
            "name": "Поиск источника нагрузки",
            "slug": "resource-source-analysis",
            "description": (
                "Находит процесс или подсистему, создающую "
                "нагрузку, по совокупности показателей."
            ),
            "order": 60,
        },
        {
            "name": "Ошибки запуска systemd-сервисов",
            "slug": "systemd-startup-failures",
            "description": (
                "Определяет причину, по которой сервис "
                "не запускается или завершается с ошибкой."
            ),
            "order": 70,
        },
        {
            "name": "Сервис, журнал и порт",
            "slug": "service-log-port-correlation",
            "description": (
                "Связывает состояние сервиса, журналы, "
                "занятый порт и адрес прослушивания."
            ),
            "order": 80,
        },
        {
            "name": "Диагностика SSH и FTP",
            "slug": "ssh-ftp-diagnostic-layer",
            "description": (
                "Разделяет сетевую проблему, недоступность "
                "сервиса и ошибку авторизации."
            ),
            "order": 90,
        },
        {
            "name": "Контекст выполнения Cron",
            "slug": "cron-runtime-context",
            "description": (
                "Понимает влияние окружения, пользователя, "
                "путей и параллельных запусков на задачи Cron."
            ),
            "order": 100,
        },
    ),
    "web": (
        {
            "name": "Источник ошибки 4XX или 5XX",
            "slug": "http-error-layer",
            "description": (
                "Определяет, на каком уровне возникла ошибка: "
                "веб-сервер, upstream, PHP или приложение."
            ),
            "order": 10,
        },
        {
            "name": "Следующий шаг по логам",
            "slug": "next-step-from-logs",
            "description": (
                "Выбирает полезный следующий шаг диагностики "
                "по журналам и другим вводным."
            ),
            "order": 20,
        },
        {
            "name": "Виртуальные хосты и маршрутизация",
            "slug": "virtual-host-routing",
            "description": (
                "Диагностирует проблемы server_name, "
                "виртуального хоста, порта и выбора конфигурации."
            ),
            "order": 30,
        },
        {
            "name": "Reverse proxy и редиректы",
            "slug": "reverse-proxy-redirects",
            "description": (
                "Разбирается с reverse proxy, циклами "
                "редиректов и неправильным направлением запросов."
            ),
            "order": 40,
        },
        {
            "name": "Сокет, порт и версия PHP",
            "slug": "php-endpoint-version",
            "description": (
                "Определяет несовпадение сокета, порта "
                "или версии PHP между компонентами."
            ),
            "order": 50,
        },
        {
            "name": "Пулы и лимиты PHP-FPM",
            "slug": "php-fpm-pool-limits",
            "description": (
                "Диагностирует нехватку процессов пула, "
                "лимиты и периодические ошибки PHP-FPM."
            ),
            "order": 60,
        },
        {
            "name": "Нестабильная работа сайта",
            "slug": "website-instability",
            "description": (
                "Разделяет причины нестабильности между PHP, "
                "базой, диском, памятью и веб-сервером."
            ),
            "order": 70,
        },
        {
            "name": "Доступность и производительность базы",
            "slug": "database-availability-performance",
            "description": (
                "Диагностирует недоступность и замедление базы, "
                "лимиты соединений, сокеты и адрес прослушивания."
            ),
            "order": 80,
        },
    ),
    "networks": (
        {
            "name": "Доступность IP и порта",
            "slug": "ip-vs-port",
            "description": (
                "Отличает недоступность IP-адреса "
                "от недоступности конкретного порта."
            ),
            "order": 10,
        },
        {
            "name": "Порт и работа приложения",
            "slug": "port-vs-application",
            "description": (
                "Понимает, что открытый TCP-порт не означает "
                "корректную работу приложения или протокола."
            ),
            "order": 20,
        },
        {
            "name": "Потери на промежуточных узлах",
            "slug": "mtr-intermediate-loss",
            "description": (
                "Правильно интерпретирует потери в MTR "
                "на промежуточных и конечных узлах."
            ),
            "order": 30,
        },
        {
            "name": "Задержка, маршрут и протокол проверки",
            "slug": "latency-route-protocol",
            "description": (
                "Анализирует рост задержки и периодическую "
                "недоступность, выбирает подходящий вид проверки."
            ),
            "order": 40,
        },
        {
            "name": "Уровень сетевой блокировки",
            "slug": "firewall-layer",
            "description": (
                "Разделяет облачный файрволл, локальный "
                "файрволл и настройки самого сервиса."
            ),
            "order": 50,
        },
        {
            "name": "Ошибки правил файрволла",
            "slug": "firewall-rule-errors",
            "description": (
                "Находит ошибки в протоколе, источнике, "
                "порядке правил и адресе прослушивания."
            ),
            "order": 60,
        },
        {
            "name": "Маршрутизация и сервисы IPv6",
            "slug": "ipv6-routing-listening",
            "description": (
                "Диагностирует IPv6-маршрут, шлюз "
                "и адрес прослушивания сервиса."
            ),
            "order": 70,
        },
        {
            "name": "Качество сетевого соединения",
            "slug": "network-quality",
            "description": (
                "Разделяет потери, задержку, MTU, ограничения "
                "сервера и пропускную способность канала."
            ),
            "order": 80,
        },
    ),
}


def seed_l1_taxonomy(apps, schema_editor):
    Topic = apps.get_model(
        "assessment",
        "Topic",
    )
    Skill = apps.get_model(
        "assessment",
        "Skill",
    )

    topics_by_slug = {}

    for topic_data in TOPICS:
        topic, _ = Topic.objects.update_or_create(
            slug=topic_data["slug"],
            defaults={
                "name": topic_data["name"],
                "description": topic_data["description"],
                "order": topic_data["order"],
                "is_active": True,
            },
        )

        topics_by_slug[topic.slug] = topic

    for topic_slug, skills in SKILLS.items():
        topic = topics_by_slug[topic_slug]

        for skill_data in skills:
            Skill.objects.update_or_create(
                topic=topic,
                slug=skill_data["slug"],
                defaults={
                    "name": skill_data["name"],
                    "description": skill_data["description"],
                    "order": skill_data["order"],
                    "is_active": True,
                },
            )


def remove_l1_taxonomy(apps, schema_editor):
    Topic = apps.get_model(
        "assessment",
        "Topic",
    )
    Skill = apps.get_model(
        "assessment",
        "Skill",
    )

    for topic_slug, skills in SKILLS.items():
        Skill.objects.filter(
            topic__slug=topic_slug,
            slug__in=[
                skill["slug"]
                for skill in skills
            ],
        ).delete()

    Topic.objects.filter(
        slug__in=[
            topic["slug"]
            for topic in TOPICS
        ],
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        (
            "assessment",
            "0002_topic_skill_questionfamily_and_more",
        ),
    ]

    operations = [
        migrations.RunPython(
            seed_l1_taxonomy,
            remove_l1_taxonomy,
        ),
    ]
