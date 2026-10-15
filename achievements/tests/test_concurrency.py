from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from datetime import timedelta
from unittest.mock import patch
from unittest import skipUnless

from django.contrib.auth.models import User
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from achievements.models import AchievementDefinition, AchievementEvent, AchievementSourceEvent, UserAchievement
from achievements.services.catalog import seed_catalog
from achievements.services.events import process_source_event
from achievements.services.grants import grant, revoke


@skipUnless(connection.vendor == "postgresql", "Requires real PostgreSQL row locks/triggers")
class ConcurrentGrantTests(TransactionTestCase):
    def setUp(self):
        seed_catalog()
        self.user = User.objects.create_user("concurrent-award")
        self.staff = User.objects.create_user("concurrent-award-staff", is_staff=True)
        self.definition = AchievementDefinition.objects.get(code="independent_speed")

    def parallel(self, functions):
        barrier = Barrier(len(functions))
        def run(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            futures = [pool.submit(run, f) for f in functions]
            return [f.result(timeout=30) for f in futures]

    def award(self, tier="platinum", operation="op"):
        return grant(user_id=self.user.pk, definition_id=self.definition.pk, tier_code=tier,
            evidence={"value": tier}, occurred_at=timezone.now(), source_type="test", source_ref=operation, operation_id=operation)[1]

    def test_parallel_first_same_operation_one_grant(self):
        results = self.parallel([lambda: self.award(), lambda: self.award()])
        self.assertCountEqual(results, ["grant", "duplicate"])
        self.assertEqual(UserAchievement.objects.count(), 1)
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_parallel_independent_proofs_one_grant(self):
        results = self.parallel([lambda: self.award(operation="one"), lambda: self.award(operation="two")])
        self.assertCountEqual(results, ["grant", "no_op"])
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_parallel_different_tiers_never_downgrades(self):
        self.parallel([lambda: self.award("bronze", "bronze"), lambda: self.award("platinum", "platinum")])
        self.assertEqual(UserAchievement.objects.get().active_tier.code, "platinum")
        self.assertLessEqual(AchievementEvent.objects.count(), 2)

    def test_concurrent_revoke_and_upgrade_finish_with_suppression(self):
        self.award("bronze")
        self.parallel([lambda: self.award("platinum", "new"), lambda: revoke(user_id=self.user.pk,
            definition_id=self.definition.pk, actor=self.staff, reason="Ошибка", operation_id="revoke")])
        entitlement = UserAchievement.objects.get()
        self.assertTrue(entitlement.auto_grant_blocked)
        self.assertIsNone(entitlement.active_tier_id)

    def test_parallel_source_processing_once(self):
        source = AchievementSourceEvent.objects.create(provider="roadmap_confirmation", external_id="legacy",
            user=self.user, context={}, payload={})
        self.parallel([lambda: process_source_event(source.pk), lambda: process_source_event(source.pk)])
        source.refresh_from_db()
        self.assertEqual(source.attempts, 1)
        self.assertEqual(source.status, "processed")

    def test_correction_committing_before_grant_is_used_without_fk_deadlock(self):
        from achievements.services.events import metric_values, publish
        from achievements.services.grants import lock_user
        from traineediary.models import EntryType, StageGroup, TraineeJourney, TraineeStage, WeeklyMetric
        start = timezone.localdate() - timedelta(days=30)
        stage = TraineeStage.objects.create(name="Review", slug="concurrent-review", order=999, group=StageGroup.WITH_REVIEW)
        journey = TraineeJourney.objects.create(user=self.user, entry_type=EntryType.NEW_HIRE,
            probation_start_date=start, stage_started_at=start, current_stage=stage)
        metric = WeeklyMetric.objects.create(journey=journey, week_number=1, week_start_date=start, quality_percent=96)
        source = AchievementSourceEvent.objects.create(provider="weekly_metric", external_id="original",
            user=self.user, context={"journey_id": journey.pk}, payload={"values": metric_values(metric)})
        writer_locked = Event()
        evaluator_locked = Event()

        def tracked_lock(user_id):
            result = lock_user(user_id)
            evaluator_locked.set()
            return result

        def correct():
            with transaction.atomic():
                TraineeJourney.objects.select_for_update().get(pk=journey.pk)
                WeeklyMetric.objects.filter(pk=metric.pk).update(quality_percent=80)
                writer_locked.set()
                self.assertTrue(evaluator_locked.wait(timeout=10))
                publish(provider="weekly_metric", external_id="corrected", user_id=self.user.pk,
                    context={"journey_id": journey.pk}, payload={"values": metric_values(WeeklyMetric.objects.get(pk=metric.pk))})

        def process():
            self.assertTrue(writer_locked.wait(timeout=10))
            return process_source_event(source.pk)

        with patch("achievements.services.events.lock_user", side_effect=tracked_lock), patch("achievements.services.events.wake"):
            self.parallel([correct, process])
        entitlement = UserAchievement.objects.get()
        self.assertEqual(entitlement.active_tier.code, "bronze")
        self.assertEqual(AchievementEvent.objects.count(), 1)

    def test_database_triggers_reject_raw_audit_and_source_mutations(self):
        self.award()
        event = AchievementEvent.objects.get()
        source = AchievementSourceEvent.objects.create(provider="stage_transition", external_id="x", user=self.user)
        for sql, pk in [("UPDATE achievements_achievementevent SET reason='forged' WHERE id=%s", event.pk),
                        ("DELETE FROM achievements_achievementevent WHERE id=%s", event.pk),
                        ("UPDATE achievements_achievementsourceevent SET payload='{}'::jsonb, provider='forged' WHERE id=%s", source.pk)]:
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [pk])
