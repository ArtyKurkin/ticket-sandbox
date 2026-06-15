from django.db import migrations


def normalize_priority(apps, schema_editor):
    Task = apps.get_model("sandbox", "Task")

    priority_map = {
        "Low": "low",
        "LOW": "low",
        "low": "low",
        "Низкий": "low",
        "низкий": "low",

        "Medium": "medium",
        "MEDIUM": "medium",
        "medium": "medium",
        "Средний": "medium",
        "средний": "medium",
        "Normal": "medium",
        "normal": "medium",
        "": "medium",

        "High": "high",
        "HIGH": "high",
        "high": "high",
        "Высокий": "high",
        "высокий": "high",

        "Critical": "critical",
        "CRITICAL": "critical",
        "critical": "critical",
        "Критический": "critical",
        "критический": "critical",
    }

    for task in Task.objects.all():
        task.priority = priority_map.get(task.priority, "medium")
        task.save(update_fields=["priority"])


def rollback_priority(apps, schema_editor):
    Task = apps.get_model("sandbox", "Task")

    priority_map = {
        "low": "Low",
        "medium": "Medium",
        "high": "High",
        "critical": "Critical",
    }

    for task in Task.objects.all():
        task.priority = priority_map.get(task.priority, "Medium")
        task.save(update_fields=["priority"])


class Migration(migrations.Migration):

    dependencies = [
        ("sandbox", "0012_remove_task_queue_name"),
    ]

    operations = [
        migrations.RunPython(normalize_priority, rollback_priority),
    ]
