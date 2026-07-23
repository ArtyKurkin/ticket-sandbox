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
from sandbox.models import TraineeProfile


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
                "traineediary:trainees_kanban",
            ),
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
