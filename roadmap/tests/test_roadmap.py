import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from roadmap.models import TrainingConfirmationEvent
from roadmap.services.confirmations import change_training_confirmation
from roadmap.services.projection import build_roadmap
from sandbox.models import CheckRun, Queue, Task, TaskAttempt
from sandbox.services.completions import record_completion_after_success
from traineediary.models import CompletionStatus, EntryType, StageHistory, StageScheme, TraineeJourney, TraineeStage, WeeklyMetric


class RoadmapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_stages", verbosity=0)
        cls.user = User.objects.create_user("roadmap-user")
        cls.other = User.objects.create_user("roadmap-other")
        cls.staff = User.objects.create_user("roadmap-staff", is_staff=True)
        cls.today = timezone.localdate()
        cls.journey = TraineeJourney.objects.create(
            user=cls.user, entry_type=EntryType.NEW_HIRE,
            probation_start_date=cls.today - timedelta(days=100),
            current_stage=TraineeStage.objects.get(slug="training-program"),
            stage_started_at=cls.today - timedelta(days=100),
        )

    def roadmap(self):
        self.journey.refresh_from_db()
        return build_roadmap(self.journey)

    def stages(self):
        return {row["id"]: row for row in self.roadmap()["stages"]}

    def move(self, slug):
        self.journey.move_to_stage(TraineeStage.objects.get(slug=slug), changed_by=self.staff)

    def action(self, action="confirm", **data):
        return self.client.post(reverse(f"roadmap_api:{action}", args=[self.journey.pk]), json.dumps(data), content_type="application/json")

    def confirm(self):
        return change_training_confirmation(journey_id=self.journey.pk, actor=self.staff, confirmed=True)

    def complete_sandbox(self):
        queue, _ = Queue.objects.update_or_create(slug="l1", defaults={"name": "L1", "is_active": True})
        Task.objects.filter(queue=queue).delete()
        task = Task.objects.create(queue=queue, slug="roadmap-task", title="Task", requires_manual_review=True)
        attempt = TaskAttempt.objects.create(user=self.user, task=task, technical_passed_at=timezone.now())
        run = CheckRun.objects.create(attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0)
        completion, _ = record_completion_after_success(attempt_id=attempt.pk, check_run_id=run.pk)
        return task, attempt, completion

    def test_eight_stations_and_external_denominator(self):
        data = self.roadmap()
        self.assertEqual([s["id"] for s in data["stages"]], ["training", "sandbox", "escalation", "ticket_analysis", "with_review", "optional_review", "no_review", "probation"])
        self.assertEqual([s["order"] for s in data["stages"]], list(range(1, 9)))
        self.assertEqual(data["overall"]["applicable_count"], 6)
        self.assertEqual(data["overall"]["percent"], 0)
        self.assertEqual(data["overall"]["completed_count"], 0)
        for row in data["stages"][2:4]:
            self.assertEqual(row["availability"], "coming_soon")
            self.assertEqual(row["display_status"], "coming_soon")
            self.assertEqual(row["badge"], "COMING SOON")
            self.assertFalse(row["applicable"])
            self.assertIsNone(row["state"])
            self.assertEqual(row["actions"], [])
            self.assertNotIn("url", row)
            self.assertTrue(row["description"])

    def test_internal_not_required(self):
        self.journey.entry_type = EntryType.INTERNAL_TRANSFER
        self.journey.current_stage = TraineeStage.objects.get(slug="with-review")
        self.journey.save()
        data = self.roadmap()
        self.assertEqual(data["overall"]["applicable_count"], 4)
        for row in data["stages"][:2]:
            self.assertEqual(row["display_status"], "not_required")
            self.assertIsNone(row["state"])
        self.client.force_login(self.staff)
        self.assertEqual(self.action().status_code, 409)
        self.assertFalse(TrainingConfirmationEvent.objects.exists())

    def test_confirmation_audit_idempotency_revoke_and_no_transition(self):
        self.client.force_login(self.staff)
        original = self.journey.current_stage_id
        self.assertTrue(self.action(comment="Teachbase проверен").json()["changed"])
        self.assertFalse(self.action().json()["changed"])
        self.assertEqual(self.roadmap()["overall"]["percent"], 16.7)
        self.assertTrue(self.action("revoke", comment="Отмена").json()["changed"])
        self.assertFalse(self.action("revoke").json()["changed"])
        self.assertEqual(self.roadmap()["overall"]["percent"], 0)
        self.assertEqual(TrainingConfirmationEvent.objects.count(), 2)
        self.assertEqual(TrainingConfirmationEvent.objects.first().comment, "Teachbase проверен")
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.current_stage_id, original)
        self.assertEqual(StageHistory.objects.filter(journey=self.journey).count(), 1)
        self.action()
        self.assertEqual(TrainingConfirmationEvent.objects.count(), 3)

    def test_event_instance_is_immutable(self):
        event, _ = self.confirm()
        with self.assertRaises(ValueError):
            event.save()
        with self.assertRaises(ValueError):
            event.delete()

    def test_sandbox_completion_and_text_notifications(self):
        self.confirm()
        task, attempt, completion = self.complete_sandbox()
        attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        attempt.mentor_feedback = "Исправьте ответ"
        attempt.mentor_reviewed_at = timezone.now()
        attempt.save()
        data = self.roadmap()
        stages = {row["id"]: row for row in data["stages"]}
        self.assertEqual(stages["sandbox"]["state"], "completed")
        self.assertEqual(stages["sandbox"]["completion"]["id"], completion.pk)
        self.assertEqual(stages["sandbox"]["progress"]["completed"], 1)
        notifications = {n["code"]: n for n in stages["sandbox"]["notifications"]}
        self.assertEqual(notifications["text_revision_required"]["count"], 1)
        self.assertFalse(notifications["text_revision_required"]["blocking"])
        self.assertEqual(stages["with_review"]["state"], "available")
        self.assertEqual(data["overall"]["percent"], 33.3)

    def test_snapshot_survives_catalog_change(self):
        task, _, completion = self.complete_sandbox()
        Task.objects.create(queue=task.queue, slug="roadmap-new", title="New", order=2)
        sb = self.stages()["sandbox"]
        self.assertEqual(sb["state"], "completed")
        self.assertEqual(sb["progress"]["total"], 2)
        self.assertEqual(sb["completion"]["total"], 1)
        task.queue.is_active = False
        task.queue.save()
        self.assertEqual(self.stages()["sandbox"]["completion"]["id"], completion.pk)
        self.assertEqual(self.stages()["sandbox"]["state"], "completed")

    def test_status_passed_and_practice_do_not_prove_completion(self):
        queue, _ = Queue.objects.update_or_create(slug="l1", defaults={"name": "L1", "is_active": True})
        Task.objects.filter(queue=queue).delete()
        task = Task.objects.create(queue=queue, slug="unproven", title="Unproven")
        TaskAttempt.objects.create(user=self.user, task=task, status=TaskAttempt.Status.PASSED, is_current=False)
        TaskAttempt.objects.create(user=self.user, task=task, attempt_number=2, technical_passed_at=timezone.now())
        self.assertNotEqual(self.stages()["sandbox"]["state"], "completed")
        self.assertEqual(self.stages()["sandbox"]["progress"]["completed"], 0)

    def test_technical_success_without_snapshot_is_not_completion(self):
        _, _, completion = self.complete_sandbox()
        # Privileged fixture SQL, never the production API.
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sandbox_sandboxprogramcompletion WHERE id = %s", [completion.pk])
        self.assertEqual(self.stages()["sandbox"]["progress"]["completed"], 1)
        self.assertNotEqual(self.stages()["sandbox"]["state"], "completed")

    def test_sequential_staff_transitions(self):
        self.move("with-review")
        self.move("optional-review")
        self.assertEqual(self.stages()["with_review"]["state"], "completed")
        self.move("no-review")
        self.assertEqual(self.stages()["optional_review"]["state"], "completed")
        self.assertNotEqual(self.stages()["training"]["state"], "completed")

    def test_skip_does_not_complete(self):
        self.move("with-review")
        self.move("no-review")
        stages = self.stages()
        self.assertNotEqual(stages["with_review"]["state"], "completed")
        self.assertNotEqual(stages["optional_review"]["state"], "completed")
        self.assertEqual(stages["no_review"]["state"], "in_progress")
        self.assertTrue(self.roadmap()["data_quality"])

    def test_return_invalidates_previous_completion(self):
        self.move("with-review")
        self.move("optional-review")
        self.move("with-review")
        self.assertEqual(self.stages()["with_review"]["state"], "in_progress")
        self.assertNotEqual(self.stages()["optional_review"]["state"], "completed")

    def test_nonstaff_transition_is_not_evidence(self):
        self.move("with-review")
        self.journey.move_to_stage(TraineeStage.objects.get(slug="optional-review"), changed_by=self.user)
        self.assertNotEqual(self.stages()["with_review"]["state"], "completed")

    def test_ambiguous_history_preserves_current(self):
        self.move("with-review")
        self.move("optional-review")
        StageHistory.objects.filter(journey=self.journey, stage__slug="with-review").update(ended_at=None)
        self.assertNotEqual(self.stages()["with_review"]["state"], "completed")
        self.assertEqual(self.stages()["optional_review"]["state"], "in_progress")
        self.assertTrue(self.roadmap()["data_quality"])

    def test_successful_probation_and_full_progress(self):
        self.confirm()
        self.complete_sandbox()
        for slug in ("with-review", "optional-review", "no-review"):
            self.move(slug)
        self.journey.complete_probation(status=CompletionStatus.SUCCESS, completed_by=self.staff)
        data = self.roadmap()
        self.assertEqual(data["journey"]["state"], "success")
        self.assertEqual(data["overall"]["completed_count"], 6)
        self.assertEqual(data["overall"]["percent"], 100)

    def test_terminated_probation_is_not_success(self):
        self.move("no-review")
        self.journey.complete_probation(status=CompletionStatus.TERMINATED, completed_by=self.staff, comment="Прекращение")
        self.assertEqual(self.roadmap()["journey"]["state"], "terminated")
        self.assertNotEqual(self.stages()["probation"]["state"], "completed")
        self.assertNotEqual(self.stages()["no_review"]["state"], "completed")

    def test_done_without_result_is_unknown(self):
        self.move("done")
        self.assertEqual(self.roadmap()["journey"]["state"], "insufficient_data")
        self.assertNotEqual(self.stages()["probation"]["state"], "completed")

    def test_legacy_without_training_stage(self):
        TraineeJourney.objects.filter(pk=self.journey.pk).update(stage_scheme=StageScheme.LEGACY)
        self.journey.refresh_from_db()
        self.journey.current_stage = TraineeStage.objects.get(slug="with-review")
        self.journey.save()
        self.journey.stage_history.all().delete()
        StageHistory.objects.create(journey=self.journey, stage=self.journey.current_stage, started_at=self.journey.stage_started_at)
        self.move("optional-review")
        self.assertEqual(self.roadmap()["journey"]["scheme"], "legacy")
        self.assertEqual(self.stages()["with_review"]["state"], "completed")
        self.assertNotEqual(self.stages()["training"]["state"], "completed")

    def test_metrics_and_readiness_are_real(self):
        self.move("with-review")
        WeeklyMetric.objects.create(journey=self.journey, week_number=1, speed_hours="3.2", quality_percent=95)
        data = self.roadmap()
        self.assertEqual(str(data["journey"]["metrics"][0]["speed_tickets_per_hour"]), "3.2")
        self.assertEqual(data["journey"]["metrics"][0]["quality_percent"], 95)
        self.assertIn("readiness", self.stages()["with_review"])
        self.assertNotIn("tickets_count", data["journey"])

    def test_internal_percent(self):
        TraineeJourney.objects.filter(pk=self.journey.pk).update(entry_type=EntryType.INTERNAL_TRANSFER, current_stage=TraineeStage.objects.get(slug="with-review"))
        self.journey.refresh_from_db()
        self.journey.stage_history.all().delete()
        StageHistory.objects.create(journey=self.journey, stage=self.journey.current_stage, started_at=self.journey.stage_started_at)
        self.move("optional-review")
        self.assertEqual(self.roadmap()["overall"]["percent"], 25)
        self.move("no-review")
        self.assertEqual(self.roadmap()["overall"]["percent"], 50)
        self.journey.complete_probation(status=CompletionStatus.SUCCESS, completed_by=self.staff)
        self.assertEqual(self.roadmap()["overall"]["percent"], 100)

    def test_access_and_errors(self):
        me = reverse("roadmap_api:me")
        detail = reverse("roadmap_api:trainee", args=[self.journey.pk])
        self.assertEqual(self.client.get(me).status_code, 401)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(detail).status_code, 403)
        self.assertEqual(self.action().status_code, 403)
        self.assertEqual(self.client.get(me).json()["journey"]["state"], "not_started")
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.get(reverse("roadmap_api:trainee", args=[999999])).status_code, 404)
        self.assertEqual(self.action(comment=[]).status_code, 400)
        self.assertEqual(self.action(source="course").status_code, 400)
        self.assertEqual(self.client.get(reverse("roadmap_api:confirm", args=[self.journey.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("roadmap_api:confirm", args=[999999]), "{}", content_type="application/json").status_code, 404)
        self.assertEqual(self.client.post(reverse("roadmap_api:confirm", args=[self.journey.pk]), "[", content_type="application/json").status_code, 400)

    def test_service_enforces_staff(self):
        with self.assertRaises(PermissionDenied):
            change_training_confirmation(journey_id=self.journey.pk, actor=self.user, confirmed=True)
        self.assertFalse(TrainingConfirmationEvent.objects.exists())

    def test_orm_audit_guards(self):
        event, _ = self.confirm()
        with self.assertRaises(ValueError):
            TrainingConfirmationEvent.objects.filter(pk=event.pk).update(comment="changed")
        with self.assertRaises(ValueError):
            TrainingConfirmationEvent.objects.all().delete()

    def test_answer_counters_are_independent(self):
        _, attempt, _ = self.complete_sandbox()
        notifications = self.stages()["sandbox"]["notifications"]
        counts = {n["code"]: n["count"] for n in notifications}
        self.assertEqual(counts["text_answer_not_submitted"], 1)
        attempt.status = TaskAttempt.Status.ON_REVIEW
        attempt.save()
        counts = {n["code"]: n["count"] for n in self.stages()["sandbox"]["notifications"]}
        self.assertEqual(counts["text_waiting_for_review"], 1)
        self.assertEqual(counts["text_answer_not_submitted"], 0)
        self.assertEqual(self.stages()["sandbox"]["state"], "completed")

    def test_get_does_not_restore_missing_snapshot(self):
        _, _, completion = self.complete_sandbox()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sandbox_sandboxprogramcompletion WHERE id = %s", [completion.pk])
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as queries:
            data = self.client.get(reverse("roadmap_api:me")).json()
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        self.assertNotEqual(data["stages"][1]["state"], "completed")


    def test_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        url = reverse("roadmap_api:confirm", args=[self.journey.pk])
        self.assertEqual(client.post(url, "{}", content_type="application/json").status_code, 403)
        token = "a" * 32
        client.cookies["csrftoken"] = token
        self.assertEqual(client.post(url, "{}", content_type="application/json", HTTP_X_CSRFTOKEN=token).status_code, 200)

    def test_get_is_select_only_and_own_journey(self):
        self.complete_sandbox()
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("roadmap_api:me"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["journey"]["id"], self.journey.pk)
        for query in queries:
            self.assertTrue(query["sql"].lstrip().upper().startswith("SELECT"), query["sql"])
        self.assertFalse(TrainingConfirmationEvent.objects.exists())
        self.client.force_login(self.staff)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("roadmap_api:trainee", args=[self.journey.pk]))
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))

    def test_no_journey_has_no_fictional_progress(self):
        data = build_roadmap(None)
        self.assertEqual(len(data["stages"]), 8)
        self.assertEqual(data["overall"]["completed_count"], 0)
        self.assertEqual(data["overall"]["applicable_count"], 0)
        self.assertIsNone(data["overall"]["adaptation_progress_percent"])
        self.assertFalse(any(s["state"] == "completed" for s in data["stages"]))


class ConcurrentConfirmationTests(TransactionTestCase):
    def test_parallel_staff_actions(self):
        if connection.vendor != "postgresql":
            self.skipTest("Real row locks require PostgreSQL")
        call_command("seed_stages", verbosity=0)
        user = User.objects.create_user("parallel-trainee")
        staff = User.objects.create_user("parallel-staff", is_staff=True)
        journey = TraineeJourney.objects.create(user=user, entry_type=EntryType.NEW_HIRE, probation_start_date=timezone.localdate(), current_stage=TraineeStage.objects.get(slug="training-program"), stage_started_at=timezone.localdate())
        second_staff = User.objects.create_user("parallel-staff-two", is_staff=True)
        actor_ids = [staff.pk, second_staff.pk]
        for confirmed in (True, False, True):
            barrier = Barrier(2)
            def change(index):
                close_old_connections()
                try:
                    actor = User.objects.get(pk=actor_ids[index])
                    barrier.wait(timeout=10)
                    return change_training_confirmation(journey_id=journey.pk, actor=actor, confirmed=confirmed)[1]
                finally:
                    close_old_connections()
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(sorted(pool.map(change, range(2))), [False, True])
        self.assertEqual(TrainingConfirmationEvent.objects.count(), 3)
