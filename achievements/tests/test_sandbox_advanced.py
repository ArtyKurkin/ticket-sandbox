"""Real Ledger/service fixtures; Docker alone is mocked, never evidence providers."""
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from unittest.mock import patch
import io
import json

from django.core.management import call_command
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from achievements.models import AchievementEvent, AchievementNotification, AchievementSourceEvent, UserAchievement
from achievements.services.evaluators.sandbox_advanced import assess
from achievements.services.events import process_source_event, publish
from achievements.services.grants import revoke
from achievements.services.reconciliation import reconcile
from sandbox.models import Queue, Task, TaskAttempt
from sandbox.ledger_models import SandboxLedgerBoundary, SandboxEvidenceGap, SandboxAnswerSubmission
from sandbox.services import ledger
from sandbox.services.checks import run_attempt_check
from sandbox.services.ledger_evidence import program_evidence
from .base import AchievementTestCase


class AdvancedSandboxFixture(AchievementTestCase):
    count = 6
    review_count = None

    def setUp(self):
        # Test flushes may remove migration data. Boundary precedes these new users.
        if not SandboxLedgerBoundary.objects.filter(pk=1).exists():
            SandboxLedgerBoundary.objects.create(pk=1, enabled_at=timezone.now()-timedelta(days=1))
        self.queue, _ = Queue.objects.update_or_create(slug="l1", defaults={"name": "L1", "required_level": "l1"})
        slugs = sorted(p.parent.name for p in Path('training_tasks/l1').glob('*/Dockerfile'))[:self.count]
        self.tasks = [Task.objects.create(queue=self.queue, slug=slug, title=slug, order=i,
                                         requires_manual_review=i <= (self.review_count or self.count)) for i, slug in enumerate(slugs, 1)]
        self.attempts = [TaskAttempt.objects.create(user=self.user, task=t) for t in self.tasks]
        self.user.trainee_profile.level = 'l1'
        self.user.trainee_profile.save()
        self.client.force_login(self.user)

    def check(self, a, code=0, error=None):
        with patch('sandbox.services.checks.check_task_container', return_value=(code, 'mock output'), side_effect=error), \
             patch('sandbox.services.checks.remove_task_container', return_value=(True, 'removed')), patch('sandbox.services.checks.remove_terminal_container'):
            return run_attempt_check(attempt=a, user_id=self.user.pk)

    def complete(self):
        for a in self.attempts:
            self.check(a)

    def submit(self, a):
        self.client.force_login(self.user)
        response = self.client.post(reverse('sandbox:check_task', args=[a.pk]), {
            'client_answer': 'synthetic answer', 'trainee_report': 'synthetic report', 'operation_id': str(uuid4())})
        self.assertEqual(response.status_code, 302)
        return SandboxAnswerSubmission.objects.filter(attempt_id=a.pk).latest('ordinal')

    def review(self, a, decision='approved', comment='test decision'):
        self.client.force_login(self.staff)
        s = SandboxAnswerSubmission.objects.filter(attempt_id=a.pk).latest('ordinal')
        response = self.client.post(reverse('sandbox:save_mentor_feedback', args=[a.pk]), {
            'mentor_decision': decision, 'mentor_feedback': comment,
            'submission_id': s.pk, 'operation_id': str(uuid4())})
        self.assertEqual(response.status_code, 302)

    def approve_all(self):
        for a in self.attempts:
            self.submit(a)
            self.review(a)

    def reset(self, a, origin='trainee', outcome='success', duplicate=False):
        a.refresh_from_db()
        with transaction.atomic(), ledger.writer():
            r, _ = ledger.request_environment(a, 'reset', actor=self.user if origin == 'trainee' else self.staff, origin=origin)
            ledger.environment_phase(r, 'started')
            ledger.environment_phase(r, 'finished', outcome=outcome)
            if duplicate:
                ledger.environment_phase(r, 'duplicate', reason='duplicate_delivery')
            if outcome == 'success':
                a.restart_count += 1
                a.save(update_fields=['restart_count'])

    def levels(self):
        return assess(program_evidence(self.user.pk))


class AdvancedSandboxTests(AdvancedSandboxFixture):
    def test_silver_limits_and_maintenance_failed_duplicates_practice(self):
        a = self.attempts[0]
        self.reset(a, origin='maintenance')
        self.reset(a, outcome='failed')
        practice = TaskAttempt.objects.create(user=self.user, task=self.tasks[0], attempt_number=2, is_current=False)
        self.reset(practice)
        self.complete()
        for count in range(4):
            with self.subTest(resets=count):
                self.assertEqual(self.levels()['silver']['status'], 'eligible' if count <= 2 else 'not_met')
            if count < 3:
                self.reset(a, duplicate=True)

    def test_gold_revision_limits_and_corrected_error(self):
        self.complete()
        self.approve_all()
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'gold')
        for count, a in enumerate(self.attempts[:3], 1):
            self.review(a, 'needs_revision')
            self.submit(a)
            self.review(a)
            self.assertEqual(self.levels()['gold']['status'], 'eligible' if count <= 2 else 'not_met')
        # Explicit correction of current version removes a raw erroneous return.
        a = self.attempts[3]
        before = program_evidence(self.user.pk)['valid_returns']
        self.review(a, 'needs_revision', 'mistake')
        self.review(a, 'approved', 'correction')
        self.assertEqual(program_evidence(self.user.pk)['valid_returns'], before)

    def test_silver_survives_pending_or_unknown_answers(self):
        self.complete()
        for a in self.attempts[:-1]:
            self.submit(a)
            self.review(a)
        self.submit(self.attempts[-1])
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'silver')
        SandboxEvidenceGap.objects.create(attempt_id=self.attempts[-1].pk, reason='review_without_submission')
        self.assertEqual(self.levels()['gold']['status'], 'unknown')
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'silver')

    def test_platinum_assessment_blocked_by_actual_checker_trust(self):
        self.complete()
        self.approve_all()
        self.assertEqual(self.levels()['platinum'], {'status':'unknown', 'reasons':['runtime_checker_integrity_unproven']})
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'gold')
        self.assertFalse(self.definition('sandbox_program').tiers.get(code='platinum').parameters['automatic'])

    def test_first_failed_then_passed_disqualifies_platinum(self):
        self.check(self.attempts[0], 1)
        self.complete()
        self.approve_all()
        self.assertIn('first_real_check_failed', self.levels()['platinum']['reasons'])

    def test_prelaunch_error_is_skipped_but_trust_gate_remains(self):
        error = RuntimeError('mock Docker prelaunch')
        error._sandbox_checker_started = False
        self.check(self.attempts[0], error=error)
        self.complete()
        self.approve_all()
        self.assertEqual(self.levels()['platinum']['reasons'], ['runtime_checker_integrity_unproven'])

    def test_timeout_unknown_and_missing_coverage_do_not_prevent_silver(self):
        self.check(self.attempts[0], 124)
        self.complete()
        self.approve_all()
        self.assertEqual(self.levels()['platinum']['status'], 'unknown')
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'gold')
        SandboxEvidenceGap.objects.create(attempt_id=self.attempts[0].pk, reason='reset_history_unknown')
        self.assertEqual(self.levels()['silver']['status'], 'unknown')

    def test_first_five_order_distinct_tasks_and_sixth_cannot_replace_fifth(self):
        self.complete()
        for a in reversed(self.attempts):
            self.submit(a)
            self.review(a)
        self.assertEqual(self.evaluate('sandbox_first_five_clean_answers').tier_code, 'gold')
        fifth = self.attempts[1]
        self.review(fifth, 'needs_revision')
        self.assertEqual(self.evaluate('sandbox_first_five_clean_answers').status, 'not_met')
        self.submit(fifth)
        self.review(fifth)
        self.assertEqual(self.evaluate('sandbox_first_five_clean_answers').status, 'not_met')

    def test_correction_of_first_answer_restores_clean_eligibility(self):
        self.complete()
        self.approve_all()
        self.review(self.attempts[0], 'needs_revision')
        self.assertEqual(self.levels()['clean_answers']['status'], 'not_met')
        self.review(self.attempts[0], 'approved', 'corrected mistake')
        self.assertEqual(self.levels()['clean_answers']['status'], 'eligible')
        self.tasks[0].requires_manual_review = False
        self.tasks[0].save()
        self.assertEqual(len([a for a in program_evidence(self.user.pk)['attempts'] if a['requires_review']]), self.count)

    def test_old_account_manifest_is_unknown_even_with_new_attempts(self):
        # A second old account cannot gain enrollment from absent history.
        from django.contrib.auth.models import User
        User.objects.filter(pk=self.other.pk).update(date_joined=timezone.now()-timedelta(days=100))
        TaskAttempt.objects.create(user=self.other, task=self.tasks[0])
        result = assess(program_evidence(self.other.pk))
        self.assertEqual(result['silver']['status'], 'unknown')
        self.journey.entry_type = 'internal_transfer'
        self.journey.save()
        self.assertEqual(self.evaluate('sandbox_program').status, 'not_applicable')
        self.assertEqual(self.evaluate('sandbox_first_five_clean_answers').status, 'not_applicable')

    def test_review_events_atomic_retry_out_of_order_notifications_and_dispute(self):
        self.complete()
        self.approve_all()
        events = list(AchievementSourceEvent.objects.filter(provider='sandbox_review').order_by('-pk'))
        self.assertEqual(len(events), self.count)
        # Repeated save emits nothing; a rollback cannot leave a durable event.
        self.review(self.attempts[-1])
        self.assertEqual(AchievementSourceEvent.objects.filter(provider='sandbox_review').count(), self.count)
        a = self.attempts[0]
        a.refresh_from_db()
        s = SandboxAnswerSubmission.objects.filter(attempt_id=a.pk).latest('ordinal')
        try:
            with transaction.atomic():
                ledger.review_answer(a, self.staff, 'needs_revision', 'rolled back', s.pk)
                raise RuntimeError('rollback')
        except RuntimeError:
            pass
        self.assertEqual(AchievementSourceEvent.objects.filter(provider='sandbox_review').count(), self.count)
        for e in events:
            process_source_event(e.pk)
            process_source_event(e.pk)
        entitlement = UserAchievement.objects.get(user=self.user, definition=self.definition('sandbox_program'))
        self.assertEqual(entitlement.active_tier.code, 'gold')
        self.assertEqual(entitlement.events.filter(action__in=['grant','upgrade']).count(), 1)
        self.assertEqual(AchievementNotification.objects.filter(event__entitlement=entitlement).count(), 1)
        self.review(a, 'needs_revision', 'correction')
        corrected = AchievementSourceEvent.objects.filter(provider='sandbox_review').latest('pk')
        process_source_event(corrected.pk)
        entitlement.refresh_from_db()
        self.assertEqual(entitlement.active_tier.code, 'gold')
        self.assertTrue(entitlement.evidence_disputed)
        self.assertEqual(entitlement.events.filter(action='evidence_disputed').count(), 1)
        revoke(user_id=self.user.pk, definition_id=entitlement.definition_id, actor=self.staff,
               reason='staff review', operation_id='revoke')
        process_source_event(publish(provider='sandbox_review', external_id='retry', user_id=self.user.pk,
                                    context={}, payload={}).pk)
        entitlement.refresh_from_db()
        self.assertTrue(entitlement.auto_grant_blocked)
        self.assertIsNone(entitlement.active_tier_id)

    def test_silver_to_gold_upgrade_and_dry_run_batch(self):
        self.complete()
        d = self.definition('sandbox_program')
        report = reconcile(user_id=self.user.pk, definition=d, apply=True)
        self.assertEqual(report['tier'], 'silver')
        self.approve_all()
        process_source_event(AchievementSourceEvent.objects.filter(provider='sandbox_review').latest('pk').pk)
        entitlement = UserAchievement.objects.get(user=self.user, definition=d)
        self.assertEqual(entitlement.active_tier.code, 'gold')
        self.assertEqual(list(entitlement.events.filter(action__in=['grant','upgrade']).values_list('action', flat=True)), ['grant','upgrade'])
        before = AchievementEvent.objects.count()
        output = io.StringIO()
        call_command('reconcile_achievements', user_ids=[self.user.pk,self.other.pk],
                     families=['sandbox_program','sandbox_first_five_clean_answers'], stdout=output)
        self.assertEqual(AchievementEvent.objects.count(), before)
        rows = json.loads(output.getvalue())
        self.assertTrue(all('unknown_reasons' in r and 'current_tier' in r and not r['applied'] for r in rows))

    def test_check_catalog_change_blocks_platinum_independently(self):
        with patch('sandbox.services.ledger.checker_identity', return_value=('local', 'changed')):
            self.check(self.attempts[0])
        for a in self.attempts[1:]:
            self.check(a)
        self.approve_all()
        self.assertIn('criteria_version_changed', self.levels()['platinum']['reasons'])
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'gold')

    def test_bronze_to_silver_then_gold_keeps_one_trophy(self):
        self.complete()
        self.award('bronze', code='sandbox_program', operation='old-bronze')
        reconcile(user_id=self.user.pk, definition=self.definition('sandbox_program'), apply=True)
        self.approve_all()
        reconcile(user_id=self.user.pk, definition=self.definition('sandbox_program'), apply=True)
        e = UserAchievement.objects.get(user=self.user, definition=self.definition('sandbox_program'))
        self.assertEqual(list(e.events.filter(action__in=['grant','upgrade']).values_list('to_tier__code', flat=True)), ['bronze','silver','gold'])
        self.assertEqual(AchievementNotification.objects.filter(event__entitlement=e).count(), 3)

    def test_bronze_directly_to_gold_and_platinum_requests_blocked(self):
        from django.core.exceptions import ValidationError
        self.complete()
        self.approve_all()
        self.award('bronze', code='sandbox_program', operation='old-bronze')
        reconcile(user_id=self.user.pk, definition=self.definition('sandbox_program'), apply=True)
        e = UserAchievement.objects.get(user=self.user, definition=self.definition('sandbox_program'))
        self.assertEqual(list(e.events.filter(action__in=['grant','upgrade']).values_list('to_tier__code', flat=True)), ['bronze','gold'])
        with self.assertRaises(ValidationError):
            self.award('platinum', code='sandbox_program', operation='forbidden-platinum')

    def test_comment_only_review_creates_no_new_source_event(self):
        self.complete()
        self.submit(self.attempts[0])
        self.review(self.attempts[0])
        before = AchievementSourceEvent.objects.filter(provider='sandbox_review').count()
        self.review(self.attempts[0], comment='clarified comment')
        self.assertEqual(AchievementSourceEvent.objects.filter(provider='sandbox_review').count(), before)

    def test_raw_pass_without_registered_ledger_execution_is_not_advanced(self):
        from sandbox.models import CheckRun
        for a in self.attempts:
            CheckRun.objects.create(attempt=a, result='passed', exit_code=0, output='unregistered')
        result = self.levels()
        self.assertEqual(result['silver'], {'status':'unknown', 'reasons':['technical_success_not_registered']})
        self.assertEqual(result['gold']['status'], 'unknown')

    def test_legacy_imported_credit_attempt_never_becomes_advanced(self):
        legacy = TaskAttempt.objects.create(user=self.other, task=self.tasks[0], attempts_count=1,
                                           technical_passed_at=timezone.now())
        result = assess(program_evidence(self.other.pk))
        self.assertEqual(result['silver']['status'], 'unknown')
        self.assertEqual(result['platinum']['status'], 'unknown')


class AdvancedSmallProgramTests(AdvancedSandboxFixture):
    # Run only dedicated small-program assertion; all shared fixtures are real.
    count = 4
    def test_fewer_than_five_required_tasks(self):
        self.complete()
        self.approve_all()
        self.assertEqual(self.levels()['clean_answers'], {'status':'not_met','reasons':['fewer_than_five_required_answers']})


class AdvancedPerformanceTests(AdvancedSandboxFixture):
    count = 15

    def test_fifteen_task_provider_and_cached_family_evaluation(self):
        self.complete()
        self.approve_all()
        start = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            proof = program_evidence(self.user.pk)
        elapsed = (perf_counter()-start)*1000
        self.assertEqual(assess(proof)['gold']['status'], 'eligible')
        self.assertLessEqual(len(queries), 12)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        print(f'PERF {connection.vendor} provider 15 tasks: {len(queries)} queries, {elapsed:.2f} ms')
        from achievements.services.evaluators import evaluate
        cache = {}
        with patch('sandbox.services.ledger_evidence.program_evidence', wraps=program_evidence) as provider:
            for code in ('sandbox_program','sandbox_first_five_clean_answers'):
                evaluate(user_id=self.user.pk, definition=self.definition(code), evidence_cache=cache)
            self.assertEqual(provider.call_count, 1)
        event = AchievementSourceEvent.objects.filter(provider='sandbox_review').latest('pk')
        with CaptureQueriesContext(connection) as queries:
            process_source_event(event.pk)
        print(f'PERF {connection.vendor} event: {len(queries)} queries')
        with CaptureQueriesContext(connection) as queries:
            process_source_event(event.pk)
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT','UPDATE')) for q in queries))
        print(f'PERF {connection.vendor} repeated event: {len(queries)} queries')
        start = perf_counter()
        with CaptureQueriesContext(connection) as queries:
            call_command('reconcile_achievements', user_ids=[self.user.pk,self.other.pk],
                         families=['sandbox_program','sandbox_first_five_clean_answers'], stdout=io.StringIO())
        print(f'PERF {connection.vendor} batch 2 users/2 families: {len(queries)} queries, {(perf_counter()-start)*1000:.2f} ms')


class AdvancedFrozenReviewTests(AdvancedSandboxFixture):
    review_count = 5

    def test_newly_required_sixth_answer_is_not_in_frozen_obligations(self):
        optional = self.tasks[-1]
        optional.requires_manual_review = True
        optional.save()
        self.complete()
        for a in self.attempts[:-1]:
            self.submit(a)
            self.review(a)
        a = self.attempts[-1]
        self.submit(a)
        for i in range(3):
            self.review(a, 'needs_revision')
            self.submit(a)
        self.review(a)
        self.assertEqual(program_evidence(self.user.pk)['valid_returns'], 0)
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'gold')
        self.assertEqual(self.evaluate('sandbox_first_five_clean_answers').tier_code, 'gold')

    def test_nonrequired_answer_gap_does_not_block_required_answer_evidence(self):
        self.complete()
        for a in self.attempts[:-1]:
            self.submit(a)
            self.review(a)
        SandboxEvidenceGap.objects.create(attempt_id=self.attempts[-1].pk, reason='review_without_submission')
        self.assertEqual(self.evaluate('sandbox_program').tier_code, 'gold')
