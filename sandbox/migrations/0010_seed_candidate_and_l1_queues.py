from django.db import migrations


def create_queues_and_move_tasks(apps, schema_editor):
    Queue = apps.get_model("sandbox", "Queue")
    Task = apps.get_model("sandbox", "Task")

    candidate_queue, _ = Queue.objects.get_or_create(
        slug="candidate",
        defaults={
            "name": "Кандидат",
            "description": "Тестовые задания для кандидатов до выхода в обучение.",
            "order": 0,
            "required_level": "candidate",
            "is_active": True,
        },
    )

    l1_queue, _ = Queue.objects.get_or_create(
        slug="l1",
        defaults={
            "name": "ОТП Cloud L1",
            "description": "Учебные задачи для подготовки к работе в очереди L1.",
            "order": 1,
            "required_level": "l1",
            "is_active": True,
        },
    )

    Queue.objects.filter(slug="candidate").update(
        name="Кандидат",
        description="Тестовые задания для кандидатов до выхода в обучение.",
        order=0,
        required_level="candidate",
        is_active=True,
    )

    Queue.objects.filter(slug="l1").update(
        name="ОТП Cloud L1",
        description="Учебные задачи для подготовки к работе в очереди L1.",
        order=1,
        required_level="l1",
        is_active=True,
    )

    trainee_queue = Queue.objects.filter(slug="trainee").first()

    if trainee_queue:
        Task.objects.filter(queue=trainee_queue).update(queue=l1_queue)

    Task.objects.filter(queue__isnull=True).update(queue=l1_queue)

    Queue.objects.filter(slug="trainee").delete()


def rollback_queues(apps, schema_editor):
    Queue = apps.get_model("sandbox", "Queue")

    Queue.objects.filter(slug="candidate").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sandbox", "0009_queue_required_level_traineeprofile"),
    ]

    operations = [
        migrations.RunPython(
            create_queues_and_move_tasks,
            rollback_queues,
        ),
    ]
