from django.urls import reverse
from django.utils import timezone

from sandbox.models import CheckRun, TaskAttempt, TraineeProfile

from .base import SandboxTestCase


class MentorDashboardTests(SandboxTestCase):
    def setUp(self):
        self.queue = self.create_queue(
            slug="l1",
            name="ОТП Cloud L1",
            order=1,
            required_level=TraineeProfile.Level.L1,
        )

        self.task = self.create_task(
            queue=self.queue,
            slug="mentor-dashboard-task",
            order=1,
            title="Nginx не стартует",
        )

        self.trainee = self.create_user(
            username="mentor-dashboard-trainee",
            level=TraineeProfile.Level.L1,
        )

        self.mentor = self.create_user(
            username="mentor-dashboard-mentor",
            level=TraineeProfile.Level.ADMIN,
            is_staff=True,
        )

        self.attempt = TaskAttempt.objects.create(
            user=self.trainee,
            task=self.task,
            status=TaskAttempt.Status.FAILED,
            attempts_count=2,
            restart_count=1,
            last_check_output="Последняя проверка не прошла.",
        )

        CheckRun.objects.create(
            attempt=self.attempt,
            result=CheckRun.Result.FAILED,
            output="Nginx все еще не запущен.",
            exit_code=1,
        )

    def test_mentor_dashboard_displays_attempt_summary(self):
        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "mentor-dashboard-trainee")
        self.assertContains(response, "ОТП Cloud L1")
        self.assertContains(response, "Nginx не стартует")
        self.assertContains(response, "Не пройдена")
        self.assertContains(response, "2")
        self.assertContains(response, "1")

    def test_mentor_dashboard_revision_stat_counts_only_manual_revisions(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NOT_REVIEWED
        self.attempt.save(
            update_fields=[
                "status",
                "mentor_decision",
            ]
        )

        revision_task = self.create_task(
            queue=self.queue,
            slug="manual-revision-task",
            order=2,
            title="Ответ требует доработки",
        )

        TaskAttempt.objects.create(
            user=self.trainee,
            task=revision_task,
            status=TaskAttempt.Status.FAILED,
            mentor_decision=TaskAttempt.MentorDecision.NEEDS_REVISION,
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        dashboard_stats = response.context["dashboard_stats"]

        self.assertEqual(dashboard_stats["failed"], 2)
        self.assertEqual(dashboard_stats["needs_revision"], 1)

    def test_mentor_dashboard_shows_failed_check_status_reason(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NOT_REVIEWED
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "mentor_decision",
            ]
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Автопроверка не пройдена")
        self.assertNotContains(response, "Доработка ответа")

    def test_mentor_dashboard_shows_check_error_status_reason(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.ERROR
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NOT_REVIEWED
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "mentor_decision",
            ]
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ошибка автопроверки")
        self.assertNotContains(response, "Доработка ответа")

    def test_mentor_dashboard_shows_manual_revision_status_reason(self):
        self.attempt.status = TaskAttempt.Status.FAILED
        self.attempt.check_status = TaskAttempt.CheckStatus.FAILED
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        self.attempt.save(
            update_fields=[
                "status",
                "check_status",
                "mentor_decision",
            ]
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Доработка ответа")
        self.assertContains(response, "Нужна доработка")

    def test_regular_user_does_not_see_mentor_dashboard(self):
        self.client.login(
            username="mentor-dashboard-trainee",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(response, "Панель наставника")

    def test_mentor_dashboard_can_filter_attempts_by_status(self):
        passed_task = self.create_task(
            queue=self.queue,
            slug="passed-mentor-dashboard-task",
            order=2,
            title="Успешное задание",
        )

        TaskAttempt.objects.create(
            user=self.trainee,
            task=passed_task,
            status=TaskAttempt.Status.PASSED,
            attempts_count=1,
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(
            reverse("sandbox:dashboard"),
            data={
                "status": TaskAttempt.Status.FAILED,
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Nginx не стартует")
        self.assertNotContains(response, "Успешное задание")

    def test_mentor_dashboard_can_search_attempts(self):
        other_user = self.create_user(
            username="another-trainee",
            level=TraineeProfile.Level.L1,
        )

        other_task = self.create_task(
            queue=self.queue,
            slug="apache-task",
            order=2,
            title="Apache не отвечает",
        )

        TaskAttempt.objects.create(
            user=other_user,
            task=other_task,
            status=TaskAttempt.Status.IN_PROGRESS,
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(
            reverse("sandbox:dashboard"),
            data={
                "q": "apache",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Apache не отвечает")
        self.assertNotContains(response, "Nginx не стартует")

    def test_mentor_dashboard_can_filter_attempts_by_queue(self):
        l2_queue = self.create_queue(
            slug="l2",
            name="L2",
            order=2,
            required_level=TraineeProfile.Level.L2,
        )

        l2_task = self.create_task(
            queue=l2_queue,
            slug="l2-mentor-dashboard-task",
            order=1,
            title="Сложное L2-задание",
        )

        TaskAttempt.objects.create(
            user=self.trainee,
            task=l2_task,
            status=TaskAttempt.Status.IN_PROGRESS,
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(
            reverse("sandbox:dashboard"),
            data={
                "queue": "l2",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Сложное L2-задание")
        self.assertNotContains(response, "Nginx не стартует")

    def test_mentor_dashboard_keeps_selected_filters_in_form(self):
        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(
            reverse("sandbox:dashboard"),
            data={
                "q": "nginx",
                "queue": "l1",
                "status": TaskAttempt.Status.FAILED,
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context["search_query"], "nginx")
        self.assertEqual(response.context["selected_queue"], "l1")
        self.assertEqual(
            response.context["selected_status"],
            TaskAttempt.Status.FAILED,
        )

    def test_mentor_can_open_trainee_attempt_detail(self):
        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Nginx не стартует")
        self.assertContains(response, "mentor-dashboard-trainee")
        self.assertContains(response, "Режим просмотра наставника")

    def test_mentor_attempt_detail_does_not_show_action_buttons(self):
        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(response, "Начать работу")
        self.assertNotContains(response, "Перезапустить")
        self.assertNotContains(response, "Отправить на проверку")

    def test_mentor_dashboard_displays_summary_stats(self):
        passed_task = self.create_task(
            queue=self.queue,
            slug="summary-passed-task",
            order=2,
            title="Пройденное задание",
        )

        TaskAttempt.objects.create(
            user=self.trainee,
            task=passed_task,
            status=TaskAttempt.Status.PASSED,
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Всего попыток")
        self.assertContains(response, "Доработать")
        self.assertContains(response, "Пройдено")

    def test_mentor_can_save_feedback_for_attempt(self):
        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.post(
            reverse("sandbox:save_mentor_feedback", args=[self.attempt.id]),
            data={
                "mentor_feedback": "Хорошая диагностика, но ответ клиенту можно сделать короче.",
            },
        )

        self.assertRedirects(
            response,
            reverse("sandbox:task_detail", args=[self.attempt.id]),
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.mentor_feedback,
            "Хорошая диагностика, но ответ клиенту можно сделать короче.",
        )
        self.assertEqual(
            self.attempt.mentor_reviewed_by.username,
            "mentor-dashboard-mentor",
        )
        self.assertIsNotNone(self.attempt.mentor_reviewed_at)

    def test_regular_user_cannot_save_mentor_feedback(self):
        self.client.login(
            username="mentor-dashboard-trainee",
            password="test-password",
        )

        response = self.client.post(
            reverse("sandbox:save_mentor_feedback", args=[self.attempt.id]),
            data={
                "mentor_feedback": "Попытка оставить комментарий от стажера.",
            },
        )

        self.assertRedirects(response, reverse("sandbox:dashboard"))

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.mentor_feedback, "")
        self.assertIsNone(self.attempt.mentor_reviewed_by)
        self.assertIsNone(self.attempt.mentor_reviewed_at)

    def test_mentor_can_save_feedback_with_decision(self):
        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.post(
            reverse("sandbox:save_mentor_feedback", args=[self.attempt.id]),
            data={
                "mentor_decision": TaskAttempt.MentorDecision.NEEDS_REVISION,
                "mentor_feedback": "Нужно подробнее описать диагностику.",
            },
        )

        self.assertRedirects(
            response,
            reverse("sandbox:task_detail", args=[self.attempt.id]),
        )

        self.attempt.refresh_from_db()

        self.assertEqual(
            self.attempt.mentor_decision,
            TaskAttempt.MentorDecision.NEEDS_REVISION,
        )
        self.assertEqual(
            self.attempt.mentor_feedback,
            "Нужно подробнее описать диагностику.",
        )
        self.assertEqual(
            self.attempt.mentor_reviewed_by.username,
            "mentor-dashboard-mentor",
        )
        self.assertIsNotNone(self.attempt.mentor_reviewed_at)

    def test_trainee_dashboard_shows_unread_mentor_feedback_icon(self):
        self.attempt.mentor_feedback = "Нужно поправить ответ клиенту."
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        self.attempt.mentor_reviewed_by = self.mentor
        self.attempt.mentor_reviewed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "mentor_feedback",
                "mentor_decision",
                "mentor_reviewed_by",
                "mentor_reviewed_at",
            ]
        )

        self.client.login(
            username="mentor-dashboard-trainee",
            password="test-password",
        )

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Новый комментарий наставника")

    def test_trainee_opening_attempt_marks_mentor_feedback_as_seen(self):
        self.attempt.mentor_feedback = "Нужно поправить ответ клиенту."
        self.attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        self.attempt.mentor_reviewed_by = self.mentor
        self.attempt.mentor_reviewed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "mentor_feedback",
                "mentor_decision",
                "mentor_reviewed_by",
                "mentor_reviewed_at",
            ]
        )

        self.client.login(
            username="mentor-dashboard-trainee",
            password="test-password",
        )

        response = self.client.get(
            reverse("sandbox:task_detail", args=[self.attempt.id])
        )

        self.assertEqual(response.status_code, 200)

        self.attempt.refresh_from_db()

        self.assertIsNotNone(self.attempt.mentor_feedback_seen_at)

        response = self.client.get(reverse("sandbox:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Новый комментарий наставника")

    def test_mentor_approved_decision_marks_attempt_as_passed(self):
        self.attempt.status = TaskAttempt.Status.ON_REVIEW
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.post(
            reverse("sandbox:save_mentor_feedback", args=[self.attempt.id]),
            data={
                "mentor_decision": TaskAttempt.MentorDecision.APPROVED,
                "mentor_feedback": "Ответ хороший, можно засчитывать.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.PASSED)
        self.assertEqual(
            self.attempt.mentor_decision,
            TaskAttempt.MentorDecision.APPROVED,
        )
        self.assertIsNotNone(self.attempt.finished_at)
        self.assertIsNotNone(self.attempt.technical_passed_at)
    
    def test_mentor_needs_revision_keeps_technical_part_passed(self):
        self.attempt.status = TaskAttempt.Status.ON_REVIEW
        self.attempt.technical_passed_at = timezone.now()
        self.attempt.save(
            update_fields=[
                "status",
                "technical_passed_at",
            ]
        )

        self.client.login(
            username="mentor-dashboard-mentor",
            password="test-password",
        )

        response = self.client.post(
            reverse("sandbox:save_mentor_feedback", args=[self.attempt.id]),
            data={
                "mentor_decision": TaskAttempt.MentorDecision.NEEDS_REVISION,
                "mentor_feedback": "Ответ клиенту нужно сделать понятнее.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.attempt.refresh_from_db()

        self.assertEqual(self.attempt.status, TaskAttempt.Status.FAILED)
        self.assertEqual(
            self.attempt.mentor_decision,
            TaskAttempt.MentorDecision.NEEDS_REVISION,
        )
        self.assertIsNone(self.attempt.finished_at)
        self.assertIsNotNone(self.attempt.technical_passed_at)
        self.assertEqual(
            self.attempt.mentor_feedback,
            "Ответ клиенту нужно сделать понятнее.",
        )
