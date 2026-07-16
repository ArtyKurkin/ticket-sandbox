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

    def test_create_trainee_creates_user_and_journey(self):
        self.client.login(username="mentor-kanban", password="test")
        response = self.client.post(reverse("traineediary:create_trainee"), {
            "first_name": "Иван",
            "last_name": "Петров",
            "username": "ivan.petrov",
            "entry_type": EntryType.NEW_HIRE,
            "probation_start_date": date.today().isoformat(),
            "current_stage": self.first_day.id,
            "comment": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(User.objects.filter(username="ivan.petrov").exists())
        self.assertTrue(
            TraineeJourney.objects.filter(user__username="ivan.petrov").exists(),
        )

    def test_create_trainee_rejects_inapplicable_stage_for_internal_transfer(self):
        self.client.login(username="mentor-kanban", password="test")
        response = self.client.post(reverse("traineediary:create_trainee"), {
            "first_name": "Мария",
            "last_name": "Смирнова",
            "username": "maria.smirnova",
            "entry_type": EntryType.INTERNAL_TRANSFER,
            "probation_start_date": date.today().isoformat(),
            "current_stage": self.first_day.id,  # неприменим для internal_transfer
            "comment": "",
        })
        self.assertEqual(response.status_code, 200)  # форма не сохранилась, показала ошибку
        self.assertFalse(User.objects.filter(username="maria.smirnova").exists())

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
