from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from achievements.models import AchievementDefinition, AchievementEvent, AchievementNotification, AchievementNotificationBoundary, AchievementSourceEvent, UserAchievement
from achievements.services.catalog import seed_catalog
from achievements.services.events import process_source_event
from achievements.services.reconciliation import reconcile
from sandbox.ledger_models import SandboxLedgerBoundary, SandboxAnswerSubmission
from sandbox.models import Queue, Task, TaskAttempt
from sandbox.services.checks import run_attempt_check
from traineediary.models import TraineeJourney, TraineeStage, StageGroup


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locks')
class AdvancedConcurrencyTests(TransactionTestCase):
    def setUp(self):
        seed_catalog()
        SandboxLedgerBoundary.objects.get_or_create(pk=1, defaults={'enabled_at':timezone.now()})
        AchievementNotificationBoundary.objects.get_or_create(pk=1, defaults={'started_at':timezone.now()})
        self.user = User.objects.create_user('advanced-concurrent')
        self.staff = User.objects.create_user('advanced-staff', is_staff=True)
        self.user.trainee_profile.level = 'l1'
        self.user.trainee_profile.save()
        stage = TraineeStage.objects.create(slug='advanced-concurrent', name='Sandbox', order=900, group=StageGroup.WITH_REVIEW)
        TraineeJourney.objects.create(user=self.user, entry_type="new_hire", current_stage=stage, probation_start_date=timezone.localdate(), stage_started_at=timezone.localdate())
        queue = Queue.objects.create(slug='l1', name='L1', required_level='l1')
        task = Task.objects.create(queue=queue, slug='https-ipv4-listener', title='test', order=1, requires_manual_review=True)
        self.attempt = TaskAttempt.objects.create(user=self.user, task=task)
        with patch('sandbox.services.checks.check_task_container', return_value=(0,'mock')), \
             patch('sandbox.services.checks.remove_task_container'), patch('sandbox.services.checks.remove_terminal_container'):
            run_attempt_check(attempt=self.attempt, user_id=self.user.pk)
        self.client.force_login(self.user)
        self.client.post(reverse('sandbox:check_task', args=[self.attempt.pk]), {'client_answer':'test', 'trainee_report':'report', 'operation_id':str(uuid4())})
        self.submission = SandboxAnswerSubmission.objects.get(attempt_id=self.attempt.pk)
        self.review('approved')
        self.definition = AchievementDefinition.objects.get(code='sandbox_program')

    def review(self, decision):
        self.client.force_login(self.staff)
        with patch('achievements.services.events.wake'):
            response = self.client.post(reverse('sandbox:save_mentor_feedback', args=[self.attempt.pk]), {
                'mentor_decision':decision, 'mentor_feedback':decision, 'submission_id':self.submission.pk, 'operation_id':str(uuid4())})
        self.assertEqual(response.status_code,302)

    def parallel(self, functions):
        barrier = Barrier(len(functions))
        def run(f):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return f()
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            futures = [pool.submit(run, f) for f in functions]
            return [f.result(timeout=45) for f in futures]

    def test_parallel_event_and_apply_one_upgrade_notification(self):
        source = AchievementSourceEvent.objects.filter(provider='sandbox_review').latest('pk')
        self.parallel([lambda:process_source_event(source.pk),
                       lambda:reconcile(user_id=self.user.pk, definition=self.definition, apply=True)])
        e = UserAchievement.objects.get(user=self.user, definition=self.definition)
        self.assertEqual(e.active_tier.code,'gold')
        self.assertEqual(e.events.filter(action='upgrade').count(),1)
        self.assertEqual(AchievementNotification.objects.filter(event__entitlement=e,event__action='upgrade').count(),1)

    def test_same_event_parallel_processed_once(self):
        source = AchievementSourceEvent.objects.filter(provider='sandbox_review').latest('pk')
        self.parallel([lambda:process_source_event(source.pk),lambda:process_source_event(source.pk)])
        source.refresh_from_db()
        self.assertEqual(source.attempts,1)
        self.assertEqual(AchievementEvent.objects.filter(entitlement__user=self.user,to_tier__code='gold').count(),1)

    def test_delayed_approval_uses_committed_correction(self):
        source = AchievementSourceEvent.objects.filter(provider='sandbox_review').latest('pk')
        self.review('needs_revision')
        correction = AchievementSourceEvent.objects.filter(provider='sandbox_review').latest('pk')
        self.parallel([lambda:process_source_event(source.pk),lambda:process_source_event(correction.pk)])
        self.assertEqual(UserAchievement.objects.get(user=self.user,definition=self.definition).active_tier.code,'silver')
        self.assertFalse(AchievementEvent.objects.filter(entitlement__user=self.user,to_tier__code='gold').exists())
