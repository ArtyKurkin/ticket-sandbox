from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone

from roadmap.services.actions import external_action_hosts, training_destination
from roadmap.services.confirmations import change_training_confirmation
from roadmap.services.projection import build_roadmap
from sandbox.models import CheckRun, Queue, Task, TaskAttempt, TraineeProfile
from sandbox.services.completions import record_completion_after_success
from traineediary.models import CompletionStatus, EntryType, TraineeJourney, TraineeStage


@override_settings(ROADMAP_TEACHBASE_URL='', ROADMAP_TEACHBASE_ALLOWED_HOSTS=[])
class NavigationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_stages', verbosity=0)
        cls.user = User.objects.create_user('navigation-trainee')
        cls.staff = User.objects.create_user('navigation-staff', is_staff=True)
        cls.other = User.objects.create_user('navigation-other')
        cls.journey = TraineeJourney.objects.create(
            user=cls.user, entry_type=EntryType.NEW_HIRE,
            current_stage=TraineeStage.objects.get(slug='training-program'),
            probation_start_date=timezone.localdate() - timedelta(days=100),
            stage_started_at=timezone.localdate() - timedelta(days=100),
        )

    def stages(self, viewer=None):
        self.journey.refresh_from_db()
        data = build_roadmap(self.journey, viewer=viewer or self.user)
        return {stage['id']: stage for stage in data['stages']}

    def unlock_sandbox(self):
        change_training_confirmation(journey_id=self.journey.pk, actor=self.staff, confirmed=True)

    def complete_sandbox(self):
        queue, _ = Queue.objects.update_or_create(slug='l1', defaults={'name': 'Navigation L1', 'is_active': True})
        Task.objects.filter(queue=queue).delete()
        task = Task.objects.create(queue=queue, title='Navigation task', slug='navigation-task', requires_manual_review=True)
        attempt = TaskAttempt.objects.create(user=self.user, task=task, technical_passed_at=timezone.now())
        run = CheckRun.objects.create(attempt=attempt, result=CheckRun.Result.PASSED, exit_code=0)
        record_completion_after_success(attempt_id=attempt.pk, check_run_id=run.pk)
        profile = self.user.trainee_profile
        profile.level = TraineeProfile.Level.L1
        profile.save()
        return attempt

    def test_sandbox_link_uses_real_named_route_and_is_accessible(self):
        self.unlock_sandbox()
        action = self.stages()['sandbox']['actions'][0]
        self.assertEqual(action, {'code': 'open_sandbox', 'label': 'Перейти к заданиям', 'url': reverse('sandbox:dashboard'), 'enabled': True, 'kind': 'learning', 'external': False})
        self.assertEqual(resolve(action['url']).view_name, 'sandbox:dashboard')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(action['url']).status_code, 200)

    def test_locked_sandbox_action_is_disabled(self):
        action = self.stages()['sandbox']['actions'][0]
        self.assertFalse(action['enabled'])
        self.assertIn('заблокирован', action['reason'])

    def test_completed_sandbox_and_revisions_keep_action(self):
        attempt = self.complete_sandbox()
        attempt.mentor_decision = TaskAttempt.MentorDecision.NEEDS_REVISION
        attempt.mentor_feedback = 'Исправьте ответ'
        attempt.mentor_reviewed_at = timezone.now()
        attempt.save()
        sb = self.stages()['sandbox']
        self.assertEqual(sb['state'], 'completed')
        self.assertTrue(sb['actions'][0]['enabled'])
        self.assertEqual(sb['actions'][0]['url'], reverse('sandbox:dashboard'))
        self.assertEqual(next(n['count'] for n in sb['notifications'] if n['code'] == 'text_revision_required'), 1)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(sb['actions'][0]['url']).status_code, 200)

    def test_unconfigured_training_has_reason_and_no_url(self):
        action = self.stages()['training']['actions'][0]
        self.assertFalse(action['enabled'])
        self.assertIsNone(action['url'])
        self.assertIn('не настроена', action['reason'])
        self.assertEqual(external_action_hosts(), [])

    @override_settings(ROADMAP_TEACHBASE_URL='https://courses.example.org/program/42', ROADMAP_TEACHBASE_ALLOWED_HOSTS=['courses.example.org'])
    def test_configured_training_uses_only_explicit_validated_configuration(self):
        action = self.stages()['training']['actions'][0]
        self.assertEqual(action['url'], 'https://courses.example.org/program/42')
        self.assertTrue(action['enabled'])
        self.assertTrue(action['external'])
        self.assertEqual(external_action_hosts(), ['courses.example.org'])
        self.client.force_login(self.user)
        response = self.client.get(reverse('roadmap_api:me') + '?url=https://evil.example/&next=https://evil.example/')
        self.assertEqual(response.json()['stages'][0]['actions'][0], action)
        self.assertNotIn('Location', response)

    def test_unsafe_or_unapproved_external_urls_never_leave_backend(self):
        values = [
            'http://courses.example.org/program', 'javascript:alert(1)', '//courses.example.org/program',
            'https://evil.example/program', 'https://courses.example.org.evil.example/',
            'https://courses.example.org@evil.example/', 'https://user:secret@courses.example.org/',
            'https://courses.example.org:8443/', 'https://courses.example.org\\@evil.example/',
            'https://courses.example.org/\npath', 'https://courses.example.org./',
        ]
        for url in values:
            with self.subTest(url=url), override_settings(ROADMAP_TEACHBASE_URL=url, ROADMAP_TEACHBASE_ALLOWED_HOSTS=['courses.example.org']):
                self.assertIsNone(training_destination()[0])
                action = self.stages()['training']['actions'][0]
                self.assertIsNone(action['url'])
                self.assertFalse(action['enabled'])
                self.assertEqual(external_action_hosts(), [])

    def test_coming_soon_and_nonapplicable_training_never_offer_actions(self):
        for viewer in (self.user, self.staff):
            stages = self.stages(viewer)
            for code in ('escalation', 'ticket_analysis'):
                self.assertEqual(stages[code]['actions'], [])
        TraineeJourney.objects.filter(pk=self.journey.pk).update(entry_type=EntryType.INTERNAL_TRANSFER, current_stage=TraineeStage.objects.get(slug='with-review'))
        for viewer in (self.user, self.staff):
            for code in ('training', 'sandbox'):
                self.assertEqual(self.stages(viewer)[code]['actions'], [])

    def test_no_personal_diary_means_no_staff_only_links_for_trainee(self):
        stages = self.stages()
        for code in ('with_review', 'optional_review', 'no_review', 'probation'):
            self.assertEqual(stages[code]['actions'], [])
            self.assertTrue(stages[code]['action_notice'])
        self.client.force_login(self.user)
        for name, args in (('trainee_detail', [self.journey.pk]), ('dashboard', []), ('weekly_metrics', []), ('complete_trainee', [self.journey.pk])):
            self.assertEqual(self.client.get(reverse('traineediary:' + name, args=args)).status_code, 403)

    def test_staff_read_action_can_inspect_even_locked_working_stages(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('roadmap_api:trainee', args=[self.journey.pk]))
        stages = {s['id']: s for s in response.json()['stages']}
        for code in ('with_review', 'optional_review', 'no_review', 'probation'):
            action = stages[code]['actions'][0]
            self.assertEqual(action['url'], reverse('traineediary:trainee_detail', args=[self.journey.pk]))
            self.assertEqual(action['kind'], 'view')
            self.assertTrue(action['enabled'])
            self.assertNotIn('/complete/', action['url'])
        self.assertEqual(self.client.get(stages['with_review']['actions'][0]['url']).status_code, 200)

    def test_result_read_action_for_success_and_termination_never_completes_probation(self):
        for status in (CompletionStatus.SUCCESS, CompletionStatus.TERMINATED):
            with self.subTest(status=status):
                self.journey.refresh_from_db()
                TraineeJourney.objects.filter(pk=self.journey.pk).update(completion_status='', completed_at=None, completed_by=None, completion_comment='')
                self.journey.refresh_from_db()
                self.journey.complete_probation(status=status, completed_by=self.staff, comment='Синтетический результат')
                action = self.stages(self.staff)['probation']['actions'][0]
                self.assertEqual(action['code'], 'view_probation_result')
                self.assertEqual(action['kind'], 'view')
                self.client.force_login(self.staff)
                self.assertEqual(self.client.get(action['url']).status_code, 200)
                self.journey.refresh_from_db()
                self.assertEqual(self.journey.completion_status, status)
                self.assertEqual(self.stages()['probation']['actions'], [])

    def test_other_user_and_anonymous_cannot_obtain_foreign_actions(self):
        for viewer in (self.other, AnonymousUser()):
            data = build_roadmap(self.journey, viewer=viewer)
            self.assertTrue(all(stage['actions'] == [] for stage in data['stages']))
        self.assertEqual(self.client.get(reverse('roadmap_api:me')).status_code, 401)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse('roadmap_api:trainee', args=[self.journey.pk])).status_code, 403)
        self.assertTrue(all(s['actions'] == [] for s in self.client.get(reverse('roadmap_api:me')).json()['stages']))

    def test_action_generation_get_remains_select_only_and_creates_no_attempts(self):
        self.unlock_sandbox()
        self.client.force_login(self.user)
        before = TaskAttempt.objects.count()
        with patch('sandbox.services.attempts.get_current_attempt', side_effect=AssertionError('Must not prepare attempts')), CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('roadmap_api:me'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['stages'][1]['actions'][0]['enabled'])
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.assertEqual(TaskAttempt.objects.count(), before)

    def test_user_body_cannot_set_destination_and_csrf_is_preserved(self):
        self.client.force_login(self.staff)
        url = reverse('roadmap_api:confirm', args=[self.journey.pk])
        response = self.client.post(url, {'url': 'https://evil.example/'}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        self.assertEqual(client.post(url, {}, content_type='application/json').status_code, 403)
