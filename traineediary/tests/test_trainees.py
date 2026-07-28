import json
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
)
from sandbox.models import (
    Queue,
    Task,
    TaskAttempt,
    TraineeProfile,
)


class TraineeKanbanAndCreationTests(TestCase):
    def setUp(self):
        self.first_day = TraineeStage.objects.create(
            name="Первый день", slug="first-day-kanban", order=1,
            progress_weight_percent=3, group=StageGroup.TEACHBASE,
            applies_to_new_hire=True, applies_to_internal_transfer=False,
        )
        self.with_review = TraineeStage.objects.create(
            name="В тикетах с проверками", slug="with-review-kanban", order=7,
            min_days=15, max_days=20, progress_weight_percent=35,
            group=StageGroup.WITH_REVIEW,
        )
        self.staff_user = User.objects.create_user(
            username="mentor-kanban", password="test", is_staff=True,
        )

    def _create_l1_tasks(self):
        queue, _ = Queue.objects.update_or_create(
            slug="l1",
            defaults={
                "name": "ОТП Cloud L1",
                "description": "",
                "order": 2,
                "is_active": True,
                "required_level": (
                    TraineeProfile.Level.L1
                ),
            },
        )

        Task.objects.filter(
            queue=queue,
        ).delete()

        first_task = Task.objects.create(
            queue=queue,
            title="Первое L1-задание",
            slug="pre-adaptation-first",
            order=1,
            description="Тестовое задание.",
            is_active=True,
        )

        second_task = Task.objects.create(
            queue=queue,
            title="Второе L1-задание",
            slug="pre-adaptation-second",
            order=2,
            description="Тестовое задание.",
            is_active=True,
        )

        return first_task, second_task

    def test_kanban_renders_for_staff(self):
        self.client.login(username="mentor-kanban", password="test")
        response = self.client.get(reverse("traineediary:trainees_kanban"))
        self.assertEqual(response.status_code, 200)

    def test_create_trainee_creates_user_journey_and_history(
        self,
    ):
        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:create_trainee",
            ),
            {
                "first_name": "Иван",
                "last_name": "Петров",
                "username": "ivan.petrov",
                "entry_type": EntryType.NEW_HIRE,
                "probation_start_date": (
                    date.today().isoformat()
                ),
                "current_stage": self.first_day.id,
                "comment": "Новая адаптация",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        user = User.objects.get(
            username="ivan.petrov",
        )

        self.assertEqual(
            user.first_name,
            "Иван",
        )
        self.assertEqual(
            user.last_name,
            "Петров",
        )
        self.assertEqual(
            user.trainee_profile.level,
            TraineeProfile.Level.L1,
        )

        journey = TraineeJourney.objects.get(
            user=user,
        )

        self.assertEqual(
            journey.entry_type,
            EntryType.NEW_HIRE,
        )
        self.assertEqual(
            journey.current_stage,
            self.first_day,
        )
        self.assertEqual(
            journey.probation_start_date,
            date.today(),
        )

        self.assertEqual(
            journey.stage_history.count(),
            1,
        )

        initial_history = (
            journey.stage_history.get()
        )

        self.assertEqual(
            initial_history.stage,
            self.first_day,
        )
        self.assertEqual(
            initial_history.started_at,
            date.today(),
        )
        self.assertEqual(
            initial_history.changed_by,
            self.staff_user,
        )

        self.assertContains(
            response,
            "Иван Петров",
        )
        self.assertContains(
            response,
            "ivan.petrov",
        )
        self.assertContains(
            response,
            "Новая адаптация",
        )
        self.assertContains(
            response,
            reverse(
                "traineediary:trainee_detail",
                args=[journey.id],
            ),
        )

    def test_internal_transfer_creates_only_user_and_profile(
        self,
    ):
        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:create_trainee",
            ),
            {
                "first_name": "Мария",
                "last_name": "Смирнова",
                "username": "maria.smirnova",
                "entry_type": (
                    EntryType.INTERNAL_TRANSFER
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        user = User.objects.get(
            username="maria.smirnova",
        )

        self.assertEqual(
            user.first_name,
            "Мария",
        )
        self.assertEqual(
            user.last_name,
            "Смирнова",
        )
        self.assertEqual(
            user.trainee_profile.level,
            TraineeProfile.Level.L1,
        )

        self.assertFalse(
            TraineeJourney.objects.filter(
                user=user,
            ).exists(),
        )

        self.assertContains(
            response,
            "Мария Смирнова",
        )
        self.assertContains(
            response,
            "maria.smirnova",
        )
        self.assertContains(
            response,
            "Сотрудник из другого отдела",
        )
        self.assertContains(
            response,
            reverse(
                "traineediary:pre_adaptation_users",
            ),
        )
        self.assertContains(
            response,
            "К сотрудникам до адаптации",
        )
        self.assertContains(
            response,
            reverse(
                "sandbox:dashboard",
            ),
        )

    def test_internal_transfer_ignores_adaptation_fields(
        self,
    ):
        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:create_trainee",
            ),
            {
                "first_name": "Олег",
                "last_name": "Иванов",
                "username": "oleg.ivanov",
                "entry_type": (
                    EntryType.INTERNAL_TRANSFER
                ),
                "probation_start_date": (
                    date.today().isoformat()
                ),
                "current_stage": self.first_day.id,
                "comment": (
                    "Этот комментарий "
                    "не должен сохраняться"
                ),
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        user = User.objects.get(
            username="oleg.ivanov",
        )

        self.assertEqual(
            user.trainee_profile.level,
            TraineeProfile.Level.L1,
        )

        self.assertFalse(
            TraineeJourney.objects.filter(
                user=user,
            ).exists(),
        )

    def test_move_trainee_stage_via_ajax(self):
        user = User.objects.create_user(
            username="trainee-move",
            password="test",
        )
        current_stage_started_at = date.today() - timedelta(days=3)
        transition_date = date.today() - timedelta(days=1)

        journey = TraineeJourney.objects.create(
            user=user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today() - timedelta(days=10),
            current_stage=self.first_day,
            stage_started_at=current_stage_started_at,
        )
        new_stage = TraineeStage.objects.create(
            name="VDS",
            slug="vds-kanban",
            order=2,
            progress_weight_percent=15,
            group=StageGroup.TEACHBASE,
            applies_to_new_hire=True,
            applies_to_internal_transfer=False,
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )
        response = self.client.post(
            reverse(
                "traineediary:move_trainee_stage",
                args=[journey.id],
            ),
            data=json.dumps({
                "stage_id": new_stage.id,
                "transition_date": transition_date.isoformat(),
                "note": "Переведён после проверки результатов",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        journey.refresh_from_db()

        self.assertEqual(journey.current_stage, new_stage)
        self.assertEqual(journey.stage_started_at, transition_date)

        previous_history = journey.stage_history.get(stage=self.first_day)
        current_history = journey.stage_history.get(stage=new_stage)

        self.assertEqual(previous_history.ended_at, transition_date)
        self.assertEqual(current_history.started_at, transition_date)
        self.assertEqual(
            current_history.note,
            "Переведён после проверки результатов",
        )
        self.assertEqual(current_history.changed_by, self.staff_user)

    def test_move_trainee_stage_rejects_inapplicable_stage(self):
        user = User.objects.create_user(username="trainee-move2", password="test")
        journey = TraineeJourney.objects.create(
            user=user, entry_type=EntryType.INTERNAL_TRANSFER,
            probation_start_date=date.today(),
            current_stage=self.with_review, stage_started_at=date.today(),
        )

        self.client.login(username="mentor-kanban", password="test")
        response = self.client.post(
            reverse("traineediary:move_trainee_stage", args=[journey.id]),
            data=json.dumps({"stage_id": self.first_day.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        journey.refresh_from_db()
        self.assertEqual(journey.current_stage, self.with_review)

    def test_kanban_contains_move_dialog_and_dynamic_urls(self):
        user = User.objects.create_user(
            username="trainee-dialog",
            password="test",
        )
        journey = TraineeJourney.objects.create(
            user=user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.first_day,
            stage_started_at=date.today(),
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )
        response = self.client.get(
            reverse("traineediary:trainees_kanban"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="stage-move-dialog"')
        self.assertContains(
            response,
            (
                'data-refresh-url="'
                f'{reverse("traineediary:kanban_board_fragment")}'
                '"'
            ),
        )
        self.assertContains(
            response,
            (
                'data-move-url="'
                f'{reverse("traineediary:move_trainee_stage", args=[journey.id])}'
                '"'
            ),
        )

    def test_done_stage_is_rendered_as_collapsible_drop_zone(self):
        done_stage = TraineeStage.objects.create(
            name="Выход с ИС",
            slug="done-kanban",
            order=10,
            group=StageGroup.DONE,
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )
        response = self.client.get(
            reverse("traineediary:trainees_kanban"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="kanban-done-section kanban-dropzone"',
        )
        self.assertContains(
            response,
            'class="kanban-done-header"',
        )
        self.assertContains(
            response,
            'class="kanban-done-content"',
        )
        self.assertContains(
            response,
            f'data-stage-id="{done_stage.id}"',
        )
        self.assertContains(
            response,
            'data-stage-name="Выход с ИС"',
        )
        self.assertContains(
            response,
            'class="kanban-done-count"',
        )

    def test_pre_adaptation_page_contains_only_l1_users_without_journey(
        self,
    ):
        waiting_user = User.objects.create_user(
            username="waiting.for.adaptation",
            first_name="Роман",
            last_name="Гурин",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=waiting_user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        active_trainee = User.objects.create_user(
            username="active.adaptation",
            first_name="Анна",
            last_name="Тестова",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=active_trainee,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        TraineeJourney.objects.create(
            user=active_trainee,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.first_day,
            stage_started_at=date.today(),
        )

        candidate_user = User.objects.create_user(
            username="candidate.without.journey",
            first_name="Пётр",
            last_name="Кандидатов",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=candidate_user,
            defaults={
                "level": (
                    TraineeProfile.Level.CANDIDATE
                ),
            },
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:pre_adaptation_users",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Роман Гурин",
        )
        self.assertContains(
            response,
            "waiting.for.adaptation",
        )
        self.assertNotContains(
            response,
            "active.adaptation",
        )
        self.assertNotContains(
            response,
            "candidate.without.journey",
        )

    def test_kanban_shows_pre_adaptation_users_count(
        self,
    ):
        for username in (
            "waiting-one",
            "waiting-two",
        ):
            user = User.objects.create_user(
                username=username,
                password="test",
            )

            TraineeProfile.objects.update_or_create(
                user=user,
                defaults={
                    "level": TraineeProfile.Level.L1,
                },
            )

        active_user = User.objects.create_user(
            username="already-in-adaptation",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=active_user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        TraineeJourney.objects.create(
            user=active_user,
            entry_type=EntryType.NEW_HIRE,
            probation_start_date=date.today(),
            current_stage=self.first_day,
            stage_started_at=date.today(),
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:trainees_kanban",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "До начала адаптации · 2",
        )
        self.assertContains(
            response,
            reverse(
                "traineediary:pre_adaptation_users",
            ),
        )

    def test_start_adaptation_form_contains_only_internal_transfer_stages(
        self,
    ):
        user = User.objects.create_user(
            username="waiting-stage-options",
            first_name="Иван",
            last_name="Ожидающий",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:start_adaptation",
                args=[user.id],
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        stage_queryset = (
            response.context[
                "form"
            ].fields[
                "current_stage"
            ].queryset
        )

        self.assertNotIn(
            self.first_day,
            stage_queryset,
        )
        self.assertIn(
            self.with_review,
            stage_queryset,
        )

        self.assertContains(
            response,
            "Иван Ожидающий",
        )

    def test_start_adaptation_creates_journey_and_history(
        self,
    ):
        user = User.objects.create_user(
            username="start.adaptation",
            first_name="Мария",
            last_name="Смирнова",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        start_date = date.today()

        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.post(
            reverse(
                "traineediary:start_adaptation",
                args=[user.id],
            ),
            {
                "probation_start_date": (
                    start_date.isoformat()
                ),
                "current_stage": self.with_review.id,
                "comment": (
                    "Переход из другого отдела"
                ),
            },
        )

        journey = TraineeJourney.objects.get(
            user=user,
        )

        self.assertRedirects(
            response,
            reverse(
                "traineediary:trainee_detail",
                args=[journey.id],
            ),
        )

        self.assertEqual(
            journey.entry_type,
            EntryType.INTERNAL_TRANSFER,
        )
        self.assertEqual(
            journey.probation_start_date,
            start_date,
        )
        self.assertEqual(
            journey.current_stage,
            self.with_review,
        )
        self.assertEqual(
            journey.stage_started_at,
            start_date,
        )
        self.assertEqual(
            journey.comment,
            "Переход из другого отдела",
        )

        self.assertEqual(
            journey.stage_history.count(),
            1,
        )

        initial_history = (
            journey.stage_history.get()
        )

        self.assertEqual(
            initial_history.stage,
            self.with_review,
        )
        self.assertEqual(
            initial_history.started_at,
            start_date,
        )
        self.assertEqual(
            initial_history.changed_by,
            self.staff_user,
        )

        pre_adaptation_response = self.client.get(
            reverse(
                "traineediary:pre_adaptation_users",
            ),
        )

        self.assertNotContains(
            pre_adaptation_response,
            "start.adaptation",
        )

    def test_inactive_user_cannot_start_adaptation(
        self,
    ):
        user = User.objects.create_user(
            username="inactive.before.adaptation",
            first_name="Олег",
            last_name="Отключённый",
            password="test",
            is_active=False,
        )

        TraineeProfile.objects.update_or_create(
            user=user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        list_response = self.client.get(
            reverse(
                "traineediary:pre_adaptation_users",
            ),
        )

        self.assertEqual(
            list_response.status_code,
            200,
        )
        self.assertContains(
            list_response,
            "inactive.before.adaptation",
        )
        self.assertContains(
            list_response,
            "Сначала включи аккаунт",
        )
        self.assertNotContains(
            list_response,
            reverse(
                "traineediary:start_adaptation",
                args=[user.id],
            ),
        )

        start_response = self.client.get(
            reverse(
                "traineediary:start_adaptation",
                args=[user.id],
            ),
        )

        self.assertEqual(
            start_response.status_code,
            404,
        )

        self.assertFalse(
            TraineeJourney.objects.filter(
                user=user,
            ).exists(),
        )

    def test_new_adaptation_rejects_future_probation_start_date(
        self,
    ):
        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        future_date = (
            date.today()
            + timedelta(days=1)
        )

        response = self.client.post(
            reverse(
                "traineediary:create_trainee",
            ),
            {
                "first_name": "Будущий",
                "last_name": "Стажёр",
                "username": "future.trainee",
                "entry_type": EntryType.NEW_HIRE,
                "probation_start_date": (
                    future_date.isoformat()
                ),
                "current_stage": self.first_day.id,
                "comment": "",
            },
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            (
                "Дата начала испытательного срока "
                "не может быть в будущем."
            ),
        )

        self.assertFalse(
            User.objects.filter(
                username="future.trainee",
            ).exists(),
        )

        self.assertFalse(
            TraineeJourney.objects.filter(
                user__username="future.trainee",
            ).exists(),
        )

    def test_pre_adaptation_page_shows_l1_progress(
        self,
    ):
        user = User.objects.create_user(
            username="pre.adaptation.progress",
            first_name="Роман",
            last_name="Гурин",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        first_task, second_task = (
            self._create_l1_tasks()
        )

        TaskAttempt.objects.create(
            user=user,
            task=first_task,
            attempt_number=1,
            is_current=True,
            status=TaskAttempt.Status.PASSED,
        )

        TaskAttempt.objects.create(
            user=user,
            task=second_task,
            attempt_number=1,
            is_current=True,
            status=TaskAttempt.Status.ON_REVIEW,
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        response = self.client.get(
            reverse(
                "traineediary:pre_adaptation_users",
            ),
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        users = response.context[
            "pre_adaptation_users"
        ]

        progress_user = next(
            trainee_user
            for trainee_user in users
            if trainee_user.id == user.id
        )

        progress = (
            progress_user.sandbox_l1_progress
        )

        self.assertEqual(
            progress.total_count,
            2,
        )
        self.assertEqual(
            progress.passed_count,
            1,
        )
        self.assertEqual(
            progress.on_review_count,
            1,
        )
        self.assertEqual(
            progress.progress_percent,
            50,
        )
        self.assertFalse(
            progress.is_ready,
        )

        self.assertContains(
            response,
            "50%",
        )
        self.assertContains(
            response,
            "На проверке:",
        )
        self.assertContains(
            response,
            "Осталось зачесть:",
        )

    def test_incomplete_l1_progress_warns_but_does_not_block_adaptation(
        self,
    ):
        user = User.objects.create_user(
            username="start.with.incomplete.l1",
            first_name="Мария",
            last_name="Смирнова",
            password="test",
        )

        TraineeProfile.objects.update_or_create(
            user=user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        first_task, _ = self._create_l1_tasks()

        TaskAttempt.objects.create(
            user=user,
            task=first_task,
            attempt_number=1,
            is_current=True,
            status=TaskAttempt.Status.PASSED,
        )

        self.client.login(
            username="mentor-kanban",
            password="test",
        )

        start_url = reverse(
            "traineediary:start_adaptation",
            args=[user.id],
        )

        get_response = self.client.get(
            start_url,
        )

        self.assertEqual(
            get_response.status_code,
            200,
        )
        self.assertContains(
            get_response,
            (
                "Сотрудник ещё не завершил "
                "задания L1."
            ),
        )
        self.assertContains(
            get_response,
            "Начать всё равно",
        )

        post_response = self.client.post(
            start_url,
            {
                "probation_start_date": (
                    date.today().isoformat()
                ),
                "current_stage": (
                    self.with_review.id
                ),
                "comment": (
                    "Адаптация начата до "
                    "завершения L1"
                ),
            },
        )

        journey = TraineeJourney.objects.get(
            user=user,
        )

        self.assertRedirects(
            post_response,
            reverse(
                "traineediary:trainee_detail",
                args=[journey.id],
            ),
        )

        self.assertEqual(
            journey.entry_type,
            EntryType.INTERNAL_TRANSFER,
        )
