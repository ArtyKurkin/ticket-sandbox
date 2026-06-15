from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from sandbox.models import Queue, Task, TraineeProfile


TEST_STORAGES = {
    **settings.STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(STORAGES=TEST_STORAGES)
class SandboxTestCase(TestCase):
    def create_user(
        self,
        username,
        level=TraineeProfile.Level.CANDIDATE,
        is_staff=False,
    ):
        user = User.objects.create_user(
            username=username,
            password="test-password",
            is_staff=is_staff,
        )

        user.trainee_profile.level = level
        user.trainee_profile.save()

        return user

    def create_queue(self, slug, name=None, order=1, required_level=None):
        queue, _ = Queue.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name or slug.upper(),
                "order": order,
                "required_level": required_level or slug,
                "is_active": True,
            },
        )

        return queue

    def create_task(self, queue, slug, order=1, title=None):
        task, _ = Task.objects.update_or_create(
            queue=queue,
            slug=slug,
            defaults={
                "title": title or slug,
                "ticket_title": f"Тикет: {title or slug}",
                "description": "Тестовое сообщение клиента.",
                "client_name": "Тестовый клиент",
                "client_email": "client@example.ru",
                "priority": Task.Priority.MEDIUM,
                "order": order,
                "is_active": True,
            },
        )

        return task
