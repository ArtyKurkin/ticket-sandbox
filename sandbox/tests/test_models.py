from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from sandbox.models import Task, TaskAttempt, TraineeProfile

from .base import SandboxTestCase


class ModelConstraintTests(SandboxTestCase):
    def setUp(self):
        self.l1_queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.l2_queue = self.create_queue(
            slug="l2",
            name="L2",
            order=2,
            required_level=TraineeProfile.Level.L2,
        )

    def test_task_queue_is_required(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.create(
                    queue=None,
                    slug="task-without-queue",
                    title="Task without queue",
                    ticket_title="Тикет без очереди",
                    description="Тестовое сообщение клиента.",
                    client_name="Тестовый клиент",
                    client_email="client@example.ru",
                    priority=Task.Priority.MEDIUM,
                    order=1,
                    is_active=True,
                )

    def test_task_slug_must_be_unique_inside_queue(self):
        self.create_task(
            queue=self.l1_queue,
            slug="same-slug",
            order=1,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Task.objects.create(
                    queue=self.l1_queue,
                    slug="same-slug",
                    title="Duplicate task",
                    ticket_title="Дубликат тикета",
                    description="Тестовое сообщение клиента.",
                    client_name="Тестовый клиент",
                    client_email="client@example.ru",
                    priority=Task.Priority.MEDIUM,
                    order=2,
                    is_active=True,
                )

    def test_same_task_slug_is_allowed_in_different_queues(self):
        l1_task = self.create_task(
            queue=self.l1_queue,
            slug="same-slug",
            order=1,
        )

        l2_task = self.create_task(
            queue=self.l2_queue,
            slug="same-slug",
            order=1,
        )

        self.assertNotEqual(l1_task.id, l2_task.id)
        self.assertEqual(l1_task.slug, l2_task.slug)
        self.assertNotEqual(l1_task.queue, l2_task.queue)

    def test_task_priority_rejects_unknown_value(self):
        task = Task(
            queue=self.l1_queue,
            slug="bad-priority",
            title="Bad priority",
            ticket_title="Тикет с плохим приоритетом",
            description="Тестовое сообщение клиента.",
            client_name="Тестовый клиент",
            client_email="client@example.ru",
            priority="super-mega-critical",
            order=1,
            is_active=True,
        )

        with self.assertRaises(ValidationError):
            task.full_clean()

    def test_trainee_profile_does_not_store_is_mentor_flag(self):
        user = User.objects.create_user(
            username="regular-user",
            password="password",
        )

        field_names = {
            field.name
            for field in TraineeProfile._meta.fields
        }

        self.assertNotIn("is_mentor", field_names)
        self.assertFalse(hasattr(user.trainee_profile, "is_mentor"))


class TaskAttemptCheckStatusTests(SandboxTestCase):
    def test_task_attempt_has_idle_check_status_by_default(self):
        queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        user = self.create_user(
            username="trainee",
            level=TraineeProfile.Level.L1,
        )
        task = self.create_task(
            queue=queue,
            slug="check-status-task",
            order=1,
        )

        attempt = TaskAttempt.objects.create(
            user=user,
            task=task,
        )

        self.assertEqual(
            attempt.check_status,
            TaskAttempt.CheckStatus.IDLE,
        )
        self.assertIsNone(attempt.check_started_at)
        self.assertIsNone(attempt.check_finished_at)

    def test_task_attempt_has_idle_environment_status_by_default(self):
        queue = self.create_queue(
            slug="environment-status-l1",
            name="Environment Status L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )
        user = self.create_user(
            username="environment-status-trainee",
            level=TraineeProfile.Level.L1,
        )
        task = self.create_task(
            queue=queue,
            slug="environment-status-task",
            order=1,
        )

        attempt = TaskAttempt.objects.create(
            user=user,
            task=task,
        )

        self.assertEqual(
            attempt.environment_status,
            TaskAttempt.EnvironmentStatus.IDLE,
        )
        self.assertIsNone(attempt.environment_started_at)
        self.assertIsNone(attempt.environment_finished_at)
