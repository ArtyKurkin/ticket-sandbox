import json
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from traineediary.forms.trainee_management import NewTraineeForm, StartAdaptationForm
from traineediary.models import (
    CompletionStatus,
    EntryType,
    StageScheme,
    StageScope,
    TraineeJourney,
    TraineeStage,
    WeeklyMetric,
)
from traineediary.services.assessment import build_readiness_summary
from traineediary.services.stage_catalog import contract
from traineediary.services.stages import journey_stages, next_stage, selectable_stages
from traineediary.views.trainee_detail import _build_gantt_rows


class StageSchemeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for slug, fields in contract.LEGACY_CATALOG.items():
            TraineeStage.objects.create(
                slug=slug,
                **fields,
                catalog_scope=(
                    StageScope.LEGACY
                    if slug in contract.LEGACY_SLUGS
                    else StageScope.SHARED
                ),
            )
        call_command("seed_stages", stdout=StringIO())
        cls.staff = User.objects.create_user("scheme-staff", is_staff=True)
        cls.other_staff = User.objects.create_user("scheme-other-staff", is_staff=True)
        cls.nonstaff = User.objects.create_user("scheme-nonstaff")

    def journey(
        self,
        slug="training-program",
        scheme=StageScheme.UNIFIED,
        entry=EntryType.NEW_HIRE,
        days=0,
    ):
        user = User.objects.create_user(f"trainee-{TraineeJourney.objects.count()}")
        today = timezone.localdate()
        return TraineeJourney.objects.create(
            user=user,
            current_stage=TraineeStage.objects.get(slug=slug),
            stage_scheme=scheme,
            entry_type=entry,
            probation_start_date=today - timedelta(days=max(days, 30)),
            stage_started_at=today - timedelta(days=days),
        )

    def test_legacy_and_unified_selectors_and_internal_transfer(self):
        legacy = selectable_stages(StageScheme.LEGACY, EntryType.NEW_HIRE)
        unified = selectable_stages(StageScheme.UNIFIED, EntryType.NEW_HIRE)
        self.assertEqual(legacy.count(), 10)
        self.assertEqual(unified.count(), 6)
        self.assertNotIn("training-program", legacy.values_list("slug", flat=True))
        self.assertNotIn("before-tickets", unified.values_list("slug", flat=True))
        for scheme in StageScheme.values:
            self.assertEqual(
                list(
                    selectable_stages(scheme, EntryType.INTERNAL_TRANSFER).values_list(
                        "slug", flat=True
                    )
                ),
                [
                    "with-review",
                    "optional-review",
                    "no-review",
                    "done",
                ],
            )

    def test_new_journey_defaults_to_unified(self):
        journey = self.journey()
        self.assertEqual(
            TraineeJourney._meta.get_field("stage_scheme").default, StageScheme.UNIFIED
        )
        self.assertEqual(journey.stage_scheme, StageScheme.UNIFIED)

    def test_scheme_change_requires_separate_migration(self):
        journey = self.journey("with-review", StageScheme.LEGACY)
        journey.stage_scheme = StageScheme.UNIFIED
        with self.assertRaisesMessage(ValidationError, "Смена схемы"):
            journey.full_clean()

    def test_progress_uses_own_scheme_and_100_percent_weights(self):
        unified = self.journey("with-review", days=8)
        legacy = self.journey("with-review", StageScheme.LEGACY, days=8)
        # Both schemes contain 40% before review; different education catalogs sum to 35%.
        self.assertEqual(unified.progress_percent, 54)
        self.assertEqual(legacy.progress_percent, 54)
        program = self.journey(days=7)
        self.assertEqual(program.progress_percent, 18)
        self.assertEqual(
            program.expected_stage_transition_date,
            program.stage_started_at + timedelta(days=14),
        )
        self.assertEqual(program.probation_days_total, 90)
        internal = self.journey(
            "with-review", entry=EntryType.INTERNAL_TRANSFER, days=10
        )
        self.assertEqual(internal.probation_days_total, 30)
        self.assertEqual(internal.progress_percent, 29)

    def test_legacy_sandbox_next_is_repeat_teachbase_unified_next_is_review(self):
        legacy = self.journey("sandbox-candidate", StageScheme.LEGACY)
        unified = self.journey("sandbox-candidate")
        self.assertEqual(next_stage(legacy).slug, "before-tickets")
        self.assertEqual(next_stage(unified).slug, "with-review")

    def test_time_never_confirms_training_program(self):
        journey = self.journey(days=40)
        history_before = list(journey.stage_history.values())
        readiness = build_readiness_summary(journey)
        self.assertFalse(readiness.is_ready)
        self.assertEqual(readiness.reasons[0].code, "manual_training_confirmation")
        self.assertEqual(readiness.next_stage.slug, "sandbox-candidate")
        journey.refresh_from_db()
        self.assertEqual(journey.current_stage.slug, "training-program")
        self.assertEqual(history_before, list(journey.stage_history.values()))

    def test_cross_scheme_and_inactive_transitions_are_atomic(self):
        for slug, scheme, target in (
            ("vds", StageScheme.LEGACY, "training-program"),
            ("training-program", StageScheme.UNIFIED, "before-tickets"),
        ):
            journey = self.journey(slug, scheme)
            before = list(journey.stage_history.values())
            with self.assertRaises(ValidationError):
                journey.move_to_stage(
                    TraineeStage.objects.get(slug=target), changed_by=self.staff
                )
            journey.refresh_from_db()
            self.assertEqual(journey.current_stage.slug, slug)
            self.assertEqual(before, list(journey.stage_history.values()))
        target = TraineeStage.objects.get(slug="sandbox-candidate")
        target.is_active = False
        target.save()
        with self.assertRaises(ValidationError):
            journey.move_to_stage(target)

    def test_manual_program_confirmation_preserves_actor_dates_notes_metrics(self):
        journey = self.journey(days=20)
        WeeklyMetric.objects.create(
            journey=journey, week_number=1, mentor_comment="Keep feedback"
        )
        before_metrics = list(journey.weekly_metrics.values())
        transition_date = timezone.localdate() - timedelta(days=1)
        journey.move_to_stage(
            TraineeStage.objects.get(slug="sandbox-candidate"),
            changed_by=self.other_staff,
            transition_date=transition_date,
            note="Teachbase подтверждён",
        )
        previous = journey.stage_history.get(stage__slug="training-program")
        current = journey.stage_history.get(stage__slug="sandbox-candidate")
        self.assertEqual(previous.ended_at, transition_date)
        self.assertEqual(current.started_at, transition_date)
        self.assertEqual(current.changed_by, self.other_staff)
        self.assertEqual(current.note, "Teachbase подтверждён")
        self.assertEqual(before_metrics, list(journey.weekly_metrics.values()))

    def test_inactive_current_and_historical_stages_stay_visible_in_gantt_and_kanban(
        self,
    ):
        journey = self.journey("vds", StageScheme.LEGACY, days=10)
        journey.move_to_stage(
            TraineeStage.objects.get(slug="before-tickets"), changed_by=self.staff
        )
        TraineeStage.objects.filter(slug__in=["vds", "before-tickets"]).update(
            is_active=False
        )
        journey.refresh_from_db()
        history = list(journey.stage_history.select_related("stage"))
        gantt = _build_gantt_rows(journey, history, timezone.localdate())
        self.assertIn("vds", [row["stage"].slug for row in gantt])
        self.assertIn("before-tickets", [row["stage"].slug for row in gantt])
        self.assertIn(
            journey.current_stage, journey_stages(journey, include_current=True)
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse("traineediary:trainees_kanban"))
        self.assertContains(
            response, f'data-current-stage-id="{journey.current_stage_id}"'
        )
        self.assertContains(response, "Перед выходом в тикеты")
        self.assertContains(response, 'data-stage-active="false"')

    def test_kanban_has_six_unified_columns_and_actual_legacy_ids(self):
        legacy = self.journey("first-day", StageScheme.LEGACY)
        unified = self.journey()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("traineediary:trainees_kanban"))
        boards = {board["scheme"]: board for board in response.context["boards"]}
        self.assertEqual(len(boards["unified"]["columns"]), 5)
        self.assertEqual(
            boards["unified"]["columns"][0]["stage"].pk, unified.current_stage_id
        )
        self.assertEqual(
            boards["legacy"]["columns"][0]["stage"].pk, legacy.current_stage_id
        )
        self.assertContains(response, "Проверки по желанию")
        self.assertContains(response, "Кнопка по желанию")
        self.assertContains(response, 'data-stage-scheme="legacy"')

    def test_kanban_api_rejects_cross_scheme_and_accepts_any_staff(self):
        journey = self.journey()
        self.client.force_login(self.other_staff)
        url = reverse("traineediary:move_trainee_stage", args=[journey.pk])

        def move(slug):
            return self.client.post(
                url,
                json.dumps(
                    {
                        "stage_id": TraineeStage.objects.get(slug=slug).pk,
                        "note": "Confirmed by another staff",
                    }
                ),
                content_type="application/json",
            )

        self.assertEqual(move("first-day").status_code, 400)
        self.assertEqual(move("sandbox-candidate").status_code, 200)
        journey.refresh_from_db()
        self.assertEqual(journey.current_stage.slug, "sandbox-candidate")
        self.assertEqual(
            journey.stage_history.get(ended_at=None).changed_by, self.other_staff
        )
        self.client.force_login(self.nonstaff)
        self.assertEqual(move("with-review").status_code, 403)
        self.client.logout()
        self.assertEqual(move("with-review").status_code, 302)

    def test_csrf_protection_retained(self):
        journey = self.journey()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        response = client.post(
            reverse("traineediary:move_trainee_stage", args=[journey.pk]),
            json.dumps(
                {"stage_id": TraineeStage.objects.get(slug="sandbox-candidate").pk}
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_forms_only_offer_unified_applicable_stages(self):
        new = NewTraineeForm()
        self.assertEqual(new.fields["current_stage"].queryset.count(), 6)
        internal = StartAdaptationForm(user=self.nonstaff)
        self.assertEqual(
            list(
                internal.fields["current_stage"].queryset.values_list("slug", flat=True)
            ),
            [
                "with-review",
                "optional-review",
                "no-review",
                "done",
            ],
        )
        rejected = NewTraineeForm(
            {
                "username": "form-new",
                "first_name": "A",
                "last_name": "B",
                "entry_type": EntryType.NEW_HIRE,
                "probation_start_date": timezone.localdate(),
                "current_stage": TraineeStage.objects.get(slug="first-day").pk,
            }
        )
        self.assertFalse(rejected.is_valid())
        self.assertIn("current_stage", rejected.errors)

    def test_completion_in_both_schemes_and_internal_transfer(self):
        for scheme in StageScheme.values:
            journey = self.journey(
                "no-review", scheme, EntryType.INTERNAL_TRANSFER, days=30
            )
            journey.complete_probation(
                status=CompletionStatus.SUCCESS, completed_by=self.other_staff
            )
            journey.refresh_from_db()
            self.assertEqual(journey.stage_scheme, scheme)
            self.assertEqual(journey.current_stage.slug, "done")
            self.assertEqual(journey.progress_percent, 100)
            self.assertEqual(
                journey.stage_history.get(ended_at=None).changed_by, self.other_staff
            )
