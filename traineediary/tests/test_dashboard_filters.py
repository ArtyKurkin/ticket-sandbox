from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from sandbox.models import TraineeProfile
from traineediary.models import (
    EntryType,
    StageGroup,
    TraineeJourney,
    TraineeStage,
)


class DashboardFilterTests(TestCase):
    def setUp(self):
        self.staff_user = self.create_user(
            username="filter-mentor",
            is_staff=True,
        )

        self.with_review_stage = (
            TraineeStage.objects.create(
                name="С проверками",
                slug="filter-with-review",
                order=10,
                min_days=10,
                max_days=20,
                progress_weight_percent=35,
                group=StageGroup.WITH_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.optional_stage = (
            TraineeStage.objects.create(
                name="Кнопка по желанию",
                slug="filter-optional-review",
                order=20,
                min_days=5,
                max_days=10,
                progress_weight_percent=25,
                group=StageGroup.OPTIONAL_REVIEW,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.done_stage = (
            TraineeStage.objects.create(
                name="Завершено",
                slug="filter-done",
                order=100,
                min_days=1,
                max_days=1,
                progress_weight_percent=0,
                group=StageGroup.DONE,
                applies_to_new_hire=True,
                applies_to_internal_transfer=True,
            )
        )

        self.ivan = self.create_journey(
            username="ivan.petrov",
            first_name="Иван",
            last_name="Петров",
            entry_type=EntryType.NEW_HIRE,
            stage=self.with_review_stage,
            stage_days=5,
            probation_days=20,
        )

        self.maria = self.create_journey(
            username="maria.smirnova",
            first_name="Мария",
            last_name="Смирнова",
            entry_type=(
                EntryType.INTERNAL_TRANSFER
            ),
            stage=self.optional_stage,
            stage_days=2,
            probation_days=5,
        )

        self.overdue = self.create_journey(
            username="overdue.trainee",
            first_name="Пётр",
            last_name="Просроченный",
            entry_type=EntryType.NEW_HIRE,
            stage=self.with_review_stage,
            stage_days=25,
            probation_days=40,
        )

        self.completed = self.create_journey(
            username="completed.trainee",
            first_name="Анна",
            last_name="Завершённая",
            entry_type=EntryType.NEW_HIRE,
            stage=self.done_stage,
            stage_days=1,
            probation_days=90,
        )

        self.url = reverse(
            "traineediary:dashboard",
        )

        self.client.login(
            username="filter-mentor",
            password="test",
        )

    def create_user(
        self,
        *,
        username,
        first_name="",
        last_name="",
        is_staff=False,
    ):
        user = User.objects.create_user(
            username=username,
            password="test",
            first_name=first_name,
            last_name=last_name,
            is_staff=is_staff,
        )

        TraineeProfile.objects.update_or_create(
            user=user,
            defaults={
                "level": TraineeProfile.Level.L1,
            },
        )

        return user

    def create_journey(
        self,
        *,
        username,
        first_name,
        last_name,
        entry_type,
        stage,
        stage_days,
        probation_days,
    ):
        user = self.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
        )

        return TraineeJourney.objects.create(
            user=user,
            entry_type=entry_type,
            probation_start_date=(
                date.today()
                - timedelta(
                    days=probation_days,
                )
            ),
            current_stage=stage,
            stage_started_at=(
                date.today()
                - timedelta(
                    days=stage_days,
                )
            ),
        )

    def usernames_from_response(
        self,
        response,
    ):
        return {
            row["journey"].user.username
            for row in response.context["rows"]
        }

    def test_default_shows_only_active_journeys(self):
        response = self.client.get(
            self.url,
        )

        usernames = (
            self.usernames_from_response(
                response,
            )
        )

        self.assertIn(
            "ivan.petrov",
            usernames,
        )

        self.assertNotIn(
            "completed.trainee",
            usernames,
        )

    def test_search_filters_by_name(self):
        response = self.client.get(
            self.url,
            {
                "q": "Иван",
            },
        )

        self.assertEqual(
            self.usernames_from_response(
                response,
            ),
            {
                "ivan.petrov",
            },
        )

    def test_search_filters_by_username(self):
        response = self.client.get(
            self.url,
            {
                "q": "maria",
            },
        )

        self.assertEqual(
            self.usernames_from_response(
                response,
            ),
            {
                "maria.smirnova",
            },
        )

    def test_entry_type_filter(self):
        response = self.client.get(
            self.url,
            {
                "entry_type": (
                    EntryType.INTERNAL_TRANSFER
                ),
            },
        )

        self.assertEqual(
            self.usernames_from_response(
                response,
            ),
            {
                "maria.smirnova",
            },
        )

    def test_stage_filter(self):
        response = self.client.get(
            self.url,
            {
                "stage": (
                    str(
                        self.optional_stage.id,
                    )
                ),
            },
        )

        self.assertEqual(
            self.usernames_from_response(
                response,
            ),
            {
                "maria.smirnova",
            },
        )

    def test_attention_filter(self):
        response = self.client.get(
            self.url,
            {
                "attention": "1",
            },
        )

        self.assertEqual(
            self.usernames_from_response(
                response,
            ),
            {
                "overdue.trainee",
            },
        )

        self.assertEqual(
            response.context[
                "needs_attention_count"
            ],
            1,
        )

    def test_completed_filter(self):
        response = self.client.get(
            self.url,
            {
                "status": "completed",
            },
        )

        self.assertEqual(
            self.usernames_from_response(
                response,
            ),
            {
                "completed.trainee",
            },
        )

    def test_all_status_filter(self):
        response = self.client.get(
            self.url,
            {
                "status": "all",
            },
        )

        self.assertEqual(
            len(
                self.usernames_from_response(
                    response,
                )
            ),
            4,
        )
