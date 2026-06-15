from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from sandbox.tests.base import SandboxTestCase
from sandbox.models import Queue, Task, TaskAttempt, TraineeProfile


class RerunAttemptTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="rerun_trainee",
            password="password",
        )

        profile, _ = TraineeProfile.objects.get_or_create(
            user=self.user,
        )
        profile.level = TraineeProfile.Level.L1
        profile.save(update_fields=["level"])

        self.queue, _ = Queue.objects.get_or_create(
            slug="l1",
            defaults={
                "name": "ОТП Cloud L1",
                "required_level": TraineeProfile.Level.L1,
                "order": 1,
            },
        )

        self.task = Task.objects.create(
            queue=self.queue,
            title="Rerun task",
            slug="rerun-task",
            order=1,
            description="Учебное сообщение клиента",
            requires_manual_review=True,
        )

        self.client.login(
            username="rerun_trainee",
            password="password",
        )

    def test_rerun_creates_new_current_attempt_and_preserves_old_attempt(self):
        old_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            is_current=True,
            technical_passed_at=timezone.now(),
            client_answer="Старый ответ клиенту",
            trainee_report="Старая диагностика",
        )

        url = reverse(
            "sandbox:rerun_task",
            args=[old_attempt.id],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        old_attempt.refresh_from_db()

        self.assertFalse(old_attempt.is_current)
        self.assertEqual(old_attempt.status, TaskAttempt.Status.PASSED)
        self.assertIsNotNone(old_attempt.technical_passed_at)
        self.assertEqual(old_attempt.client_answer, "Старый ответ клиенту")

        new_attempt = TaskAttempt.objects.get(
            user=self.user,
            task=self.task,
            attempt_number=2,
        )

        self.assertTrue(new_attempt.is_current)
        self.assertEqual(new_attempt.status, TaskAttempt.Status.NEW)
        self.assertIsNone(new_attempt.technical_passed_at)
        self.assertEqual(new_attempt.client_answer, "")
        self.assertEqual(new_attempt.trainee_report, "")

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                args=[new_attempt.id],
            ),
        )

    def test_rerun_is_blocked_if_attempt_is_not_technically_completed(self):
        attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            attempt_number=1,
            is_current=True,
        )

        url = reverse(
            "sandbox:rerun_task",
            args=[attempt.id],
        )

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                args=[attempt.id],
            ),
        )

        self.assertEqual(
            TaskAttempt.objects.filter(
                user=self.user,
                task=self.task,
            ).count(),
            1,
        )

        attempt.refresh_from_db()

        self.assertTrue(attempt.is_current)
        self.assertEqual(attempt.status, TaskAttempt.Status.IN_PROGRESS)

    def test_rerun_is_blocked_for_not_current_attempt(self):
        old_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            is_current=False,
            technical_passed_at=timezone.now(),
        )

        TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.NEW,
            attempt_number=2,
            is_current=True,
        )

        url = reverse(
            "sandbox:rerun_task",
            args=[old_attempt.id],
        )

        response = self.client.post(url)

        self.assertRedirects(
            response,
            reverse("sandbox:dashboard"),
        )

        self.assertEqual(
            TaskAttempt.objects.filter(
                user=self.user,
                task=self.task,
            ).count(),
            2,
        )

    def test_queue_progress_does_not_regress_after_rerun(self):
        old_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            is_current=True,
            technical_passed_at=timezone.now(),
        )

        self.client.post(
            reverse(
                "sandbox:rerun_task",
                args=[old_attempt.id],
            )
        )

        response = self.client.get(
            reverse("sandbox:dashboard")
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Технически выполнено",
        )

        self.assertContains(
            response,
            "1 из 1",
        )

    def test_extra_attempt_success_does_not_go_to_manual_review(self):
        old_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            is_current=False,
            technical_passed_at=timezone.now(),
        )

        extra_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            attempt_number=2,
            is_current=True,
            container_name="fake-container",
        )

        self.assertTrue(extra_attempt.is_extra_attempt)
        self.assertFalse(extra_attempt.is_credit_attempt)

        # Тут мы не запускаем настоящий Docker/check.sh.
        # Проверяем именно бизнес-правило, которое должно сработать
        # после успешной технической проверки.
        if extra_attempt.task.requires_manual_review and extra_attempt.is_credit_attempt:
            extra_attempt.status = TaskAttempt.Status.ON_REVIEW
        else:
            extra_attempt.status = TaskAttempt.Status.PASSED
            extra_attempt.finished_at = timezone.now()

        extra_attempt.technical_passed_at = timezone.now()
        extra_attempt.save(
            update_fields=[
                "status",
                "finished_at",
                "technical_passed_at",
            ]
        )

        extra_attempt.refresh_from_db()

        self.assertEqual(extra_attempt.status, TaskAttempt.Status.PASSED)
        self.assertIsNotNone(extra_attempt.finished_at)
        self.assertIsNotNone(extra_attempt.technical_passed_at)
        self.assertNotEqual(extra_attempt.status, TaskAttempt.Status.ON_REVIEW)

        old_attempt.refresh_from_db()

        self.assertEqual(old_attempt.status, TaskAttempt.Status.PASSED)
        self.assertFalse(old_attempt.is_current)

    def test_mentor_dashboard_shows_credit_attempt_not_extra_attempt(self):
        User.objects.create_user(
            username="mentor",
            password="password",
            is_staff=True,
        )

        credit_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=1,
            is_current=False,
            technical_passed_at=timezone.now(),
        )

        extra_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.IN_PROGRESS,
            attempt_number=2,
            is_current=True,
        )

        self.client.logout()
        self.client.login(
            username="mentor",
            password="password",
        )

        response = self.client.get(
            reverse("sandbox:dashboard")
        )

        self.assertEqual(response.status_code, 200)

        attempts = response.context["attempts"]

        self.assertIn(credit_attempt, attempts)
        self.assertNotIn(extra_attempt, attempts)

    def test_mentor_cannot_review_extra_attempt(self):
        User.objects.create_user(
            username="review_mentor",
            password="password",
            is_staff=True,
        )

        extra_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            status=TaskAttempt.Status.PASSED,
            attempt_number=2,
            is_current=True,
            technical_passed_at=timezone.now(),
        )

        self.client.logout()
        self.client.login(
            username="review_mentor",
            password="password",
        )

        response = self.client.post(
            reverse(
                "sandbox:save_mentor_feedback",
                args=[extra_attempt.id],
            ),
            {
                "mentor_decision": TaskAttempt.MentorDecision.APPROVED,
                "mentor_feedback": "Принято",
            },
        )

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                args=[extra_attempt.id],
            ),
        )

        extra_attempt.refresh_from_db()

        self.assertEqual(
            extra_attempt.mentor_decision,
            TaskAttempt.MentorDecision.NOT_REVIEWED,
        )
        self.assertEqual(extra_attempt.mentor_feedback, "")
        self.assertIsNone(extra_attempt.mentor_reviewed_by)
        self.assertIsNone(extra_attempt.mentor_reviewed_at)


class HistoricalAttemptActionTests(SandboxTestCase):
    def setUp(self):
        self.user = self.create_user("historical_attempt_user")
        self.client.force_login(self.user)

        self.queue = self.create_queue(slug="l1")
        self.task = self.create_task(
            queue=self.queue,
            slug="historical-attempt-task",
        )

        self.old_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            attempt_number=1,
            is_current=False,
            status=TaskAttempt.Status.NEW,
        )

        self.current_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            attempt_number=2,
            is_current=True,
            status=TaskAttempt.Status.NEW,
        )

    @patch("sandbox.views.create_task_container")
    def test_start_task_is_blocked_for_historical_attempt(self, create_task_container):
        response = self.client.post(
            reverse(
                "sandbox:start_task",
                kwargs={"attempt_id": self.old_attempt.id},
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                kwargs={"attempt_id": self.old_attempt.id},
            ),
        )

        create_task_container.assert_not_called()

    @patch("sandbox.views.create_task_container")
    def test_restart_task_is_blocked_for_historical_attempt(self, create_task_container):
        response = self.client.post(
            reverse(
                "sandbox:restart_task",
                kwargs={"attempt_id": self.old_attempt.id},
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                kwargs={"attempt_id": self.old_attempt.id},
            ),
        )

        create_task_container.assert_not_called()

    @patch("sandbox.views.check_task_container")
    def test_check_task_is_blocked_for_historical_attempt(self, check_task_container):
        self.old_attempt.client_answer = "Ответ клиенту"
        self.old_attempt.trainee_report = "Внутренний комментарий"
        self.old_attempt.container_name = "old-container"
        self.old_attempt.save()

        response = self.client.post(
            reverse(
                "sandbox:check_task",
                kwargs={"attempt_id": self.old_attempt.id},
            )
        )

        self.assertRedirects(
            response,
            reverse(
                "sandbox:task_detail",
                kwargs={"attempt_id": self.old_attempt.id},
            ),
        )

        check_task_container.assert_not_called()

    def test_historical_attempt_detail_is_read_only(self):
        self.client.force_login(self.user)

        next_attempt_number = (
            TaskAttempt.objects
            .filter(user=self.user, task=self.task)
            .order_by("-attempt_number")
            .values_list("attempt_number", flat=True)
            .first()
            or 0
        ) + 1

        historical_attempt = TaskAttempt.objects.create(
            user=self.user,
            task=self.task,
            attempt_number=next_attempt_number,
            is_current=False,
            status=TaskAttempt.Status.IN_PROGRESS,
            client_answer="Старый ответ",
            trainee_report="Старая диагностика",
            terminal_url="/terminal/1/24000/",
            terminal_port=24000,
            container_name="old-task-container",
            terminal_container_name="old-terminal-container",
            shell_command="docker exec -it old-task-container bash",
        )
        response = self.client.get(
            reverse(
                "sandbox:task_detail",
                kwargs={"attempt_id": historical_attempt.id},
            )
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Историческая попытка")
        self.assertContains(response, "Только просмотр")
        self.assertContains(response, "Старый ответ")
        self.assertContains(response, "Старая диагностика")

        self.assertNotContains(response, "Начать работу")
        self.assertNotContains(response, "Перезапустить")
        self.assertNotContains(response, "Отправить на проверку")
        self.assertNotContains(response, "Терминал сервера")
        self.assertNotContains(response, "Команда подключения к окружению")
        self.assertNotContains(response, "old-task-container")
