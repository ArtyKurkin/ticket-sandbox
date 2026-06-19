import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sandbox.models import Queue, Task


DEFAULT_CLIENTS = [
    ("Алексей Морозов", "a.morozov@example.com"),
    ("Мария Соколова", "m.sokolova@example.com"),
    ("Иван Крылов", "i.krylov@example.com"),
    ("Елена Федорова", "e.fedorova@example.com"),
    ("Дмитрий Орлов", "d.orlov@example.com"),
    ("Анна Белова", "a.belova@example.com"),
]


DEFAULT_TITLES = {
    "nginx-not-starting": "Nginx не запускается после изменения конфига",
    "site-opens-wrong-directory": "Сайт открывается из неправильной директории",
    "php-error": "Ошибка PHP на странице сайта",
    "disk-full": "На сервере закончилось место",
    "cron-not-working": "Cron-задача не выполняется",
    "mysql-access-denied": "Сайт не подключается к базе данных",
}


DEFAULT_DESCRIPTIONS = {
    "nginx-not-starting": (
        "Здравствуйте.\n\n"
        "После изменения конфигурации сайт перестал открываться. "
        "В браузере появляется ошибка, что страница недоступна.\n\n"
        "Пожалуйста, проверьте веб-сервер, найдите причину проблемы и восстановите работу сайта. "
        "После исправления напишите, что именно было не так и что вы сделали."
    ),
    "site-opens-wrong-directory": (
        "Здравствуйте.\n\n"
        "После переноса сайта открывается не та страница: вместо сайта отображается стандартная заглушка "
        "или содержимое другой директории.\n\n"
        "Пожалуйста, проверьте настройки веб-сервера и исправьте путь к корневой директории сайта."
    ),
    "php-error": (
        "Здравствуйте.\n\n"
        "На сайте появилась ошибка PHP. Раньше страница открывалась корректно, но после изменений "
        "часть функционала перестала работать.\n\n"
        "Пожалуйста, проведите диагностику, найдите причину ошибки и восстановите работу страницы."
    ),
    "disk-full": (
        "Здравствуйте.\n\n"
        "Сайт начал работать нестабильно: часть страниц открывается медленно, а загрузка файлов завершается ошибкой.\n\n"
        "Пожалуйста, проверьте свободное место на сервере, найдите причину заполнения диска и освободите место безопасным способом."
    ),
    "cron-not-working": (
        "Здравствуйте.\n\n"
        "Автоматическая задача перестала выполняться по расписанию. Из-за этого данные на сайте не обновляются.\n\n"
        "Пожалуйста, проверьте cron-задачи, найдите причину проблемы и восстановите выполнение задания."
    ),
    "mysql-access-denied": (
        "Здравствуйте.\n\n"
        "Сайт не может подключиться к базе данных. На странице отображается ошибка подключения.\n\n"
        "Пожалуйста, проверьте настройки подключения к БД и восстановите работу сайта."
    ),
}

REQUIRED_STRING_FIELDS = (
    "title",
    "ticket_title",
    "client_name",
    "client_email",
    "description",
)

BOOL_FIELDS = (
    "requires_manual_review",
    "is_active",
)


def normalize_slug(slug):
    return slug.replace("_", "-")


def humanize_slug(slug):
    return slug.replace("-", " ").replace("_", " ").capitalize()


def read_task_json(task_dir):
    metadata_path = task_dir / "task.json"

    if not metadata_path.exists():
        return {}

    try:
        with metadata_path.open("r", encoding="utf-8") as file:
            metadata = json.load(file)
    except json.JSONDecodeError as error:
        raise CommandError(f"Invalid JSON in {metadata_path}: {error}") from error

    if not isinstance(metadata, dict):
        raise CommandError(
            f"Invalid JSON in {metadata_path}: root value must be an object"
        )

    return metadata


def get_check_paths(task_dir):
    return [
        task_dir / "check.sh",
        task_dir / "files" / "check.sh",
    ]


def get_default_metadata(task_slug, order):
    normalized_slug = normalize_slug(task_slug)
    client_name, client_email = DEFAULT_CLIENTS[(order - 1) % len(DEFAULT_CLIENTS)]

    title = DEFAULT_TITLES.get(
        task_slug,
        DEFAULT_TITLES.get(normalized_slug, humanize_slug(task_slug)),
    )

    description = DEFAULT_DESCRIPTIONS.get(
        task_slug,
        DEFAULT_DESCRIPTIONS.get(
            normalized_slug,
            (
                "Здравствуйте.\n\n"
                f"Возникла проблема в учебном задании «{title}». "
                "Пожалуйста, подключитесь к серверу, проведите диагностику, исправьте причину проблемы "
                "и подготовьте понятный ответ клиенту.\n\n"
                "В ответе укажите, что было обнаружено, какие действия выполнены и какой сейчас результат."
            ),
        ),
    )

    return {
        "title": title,
        "ticket_title": title,
        "client_name": client_name,
        "client_email": client_email,
        "description": description,
        "priority": Task.Priority.MEDIUM,
        "order": order,
        "requires_manual_review": True,
        "is_active": True,
    }


def validate_task_metadata(metadata, task_dir):
    metadata_path = task_dir / "task.json"

    for field_name in REQUIRED_STRING_FIELDS:
        value = metadata.get(field_name)

        if not isinstance(value, str) or not value.strip():
            raise CommandError(
                f'Invalid metadata in {metadata_path}: "{field_name}" must be a non-empty string'
            )

    priority = metadata.get("priority", Task.Priority.MEDIUM)
    allowed_priorities = {value for value, _label in Task.Priority.choices}

    if priority not in allowed_priorities:
        allowed = ", ".join(sorted(allowed_priorities))
        raise CommandError(
            f'Invalid metadata in {metadata_path}: "priority" must be one of: {allowed}'
        )

    order = metadata.get("order")

    if isinstance(order, bool) or not isinstance(order, int) or order < 1:
        raise CommandError(
            f'Invalid metadata in {metadata_path}: "order" must be a positive integer'
        )

    for field_name in BOOL_FIELDS:
        value = metadata.get(field_name)

        if not isinstance(value, bool):
            raise CommandError(
                f'Invalid metadata in {metadata_path}: "{field_name}" must be true or false'
            )


class Command(BaseCommand):
    help = "Create or update Task records from training_tasks/<queue_slug>/<task_slug>/ directories."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving to the database.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Завершать команду ошибкой, если хотя бы одно задание было пропущено.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        strict = options["strict"]
        base_dir = Path(settings.BASE_DIR) / "training_tasks"

        if not base_dir.exists():
            raise CommandError(f"Directory not found: {base_dir}")

        created_count = 0
        updated_count = 0
        skipped_count = 0
        order_by_queue = {}

        task_dirs = sorted(
            task_dir
            for task_dir in base_dir.glob("*/*")
            if task_dir.is_dir()
        )

        if not task_dirs:
            self.stdout.write(self.style.WARNING("No task directories found."))
            return

        for task_dir in task_dirs:
            queue_slug = task_dir.parent.name
            task_slug = task_dir.name

            order_by_queue[queue_slug] = order_by_queue.get(queue_slug, 0) + 1
            default_order = order_by_queue[queue_slug]

            dockerfile_path = task_dir / "Dockerfile"

            if not dockerfile_path.exists():
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"SKIP {queue_slug}/{task_slug}: Dockerfile not found"
                    )
                )
                continue

            if not any(path.exists() for path in get_check_paths(task_dir)):
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"SKIP {queue_slug}/{task_slug}: check.sh not found"
                    )
                )
                continue

            queue = Queue.objects.filter(slug=queue_slug).first()

            if queue is None:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"SKIP {queue_slug}/{task_slug}: queue not found"
                    )
                )
                continue

            metadata = get_default_metadata(task_slug, default_order)
            metadata.update(read_task_json(task_dir))
            validate_task_metadata(metadata, task_dir)

            task_values = {
                "title": metadata["title"],
                "ticket_title": metadata.get("ticket_title", metadata["title"]),
                "client_name": metadata["client_name"],
                "client_email": metadata["client_email"],
                "description": metadata["description"],
                "priority": metadata.get("priority", Task.Priority.MEDIUM),
                "order": metadata.get("order", default_order),
                "requires_manual_review": metadata.get("requires_manual_review", True),
                "is_active": metadata.get("is_active", True),
            }

            exists = Task.objects.filter(queue=queue, slug=task_slug).exists()

            if dry_run:
                if exists:
                    updated_count += 1
                    action = "WOULD UPDATE"
                else:
                    created_count += 1
                    action = "WOULD CREATE"

                self.stdout.write(
                    f"{action} {queue_slug}/{task_slug}: {task_values['title']}"
                )
                continue

            task, was_created = Task.objects.update_or_create(
                queue=queue,
                slug=task_slug,
                defaults=task_values,
            )

            if was_created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"CREATED {queue_slug}/{task_slug}: {task.title}"
                    )
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"UPDATED {queue_slug}/{task_slug}: {task.title}"
                    )
                )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry run done. "
                    f"would_create={created_count}, "
                    f"would_update={updated_count}, "
                    f"skipped={skipped_count}"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Done. "
                    f"created={created_count}, "
                    f"updated={updated_count}, "
                    f"skipped={skipped_count}"
                )
            )

        if strict and skipped_count:
            raise CommandError(
                f"sync_training_tasks skipped {skipped_count} task(s) in strict mode."
            )
