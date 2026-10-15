from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class AdvancedActivationMigrationTests(TransactionTestCase):
    def test_catalog_activation_preserves_history_and_creates_no_awards(self):
        previous = [('achievements','0005_notifications'),('sandbox','0033_ledger_guards')]
        current = [('achievements','0006_sandbox_advanced_activation')]
        try:
            from achievements.services.catalog import seed_catalog
            seed_catalog()
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model('auth','User')
            Definition = apps.get_model('achievements','AchievementDefinition')
            Tier = apps.get_model('achievements','AchievementTier')
            Entitlement = apps.get_model('achievements','UserAchievement')
            Event = apps.get_model('achievements','AchievementEvent')
            d = Definition.objects.get(code='sandbox_program')
            tier = Tier.objects.get(definition=d,code='bronze')
            user = User.objects.create(username='before-advanced')
            entitlement = Entitlement.objects.create(user=user,definition=d,active_tier=tier)
            event = Event.objects.create(entitlement=entitlement,action='grant',to_tier=tier,
                occurred_at=timezone.now(),source_type='test',source_ref='old',rule_version=1,
                evidence={'completion_id':123},evidence_digest='old',idempotency_key='old')
            before = Event.objects.filter(pk=event.pk).values().get()
            public_id = d.public_id
            self.assertFalse(Tier.objects.get(definition=d,code='silver').parameters['automatic'])
            MigrationExecutor(connection).migrate(current)
            apps = MigrationExecutor(connection).loader.project_state(current).apps
            self.assertEqual(apps.get_model('achievements','AchievementEvent').objects.get(pk=event.pk).evidence, before['evidence'])
            self.assertEqual(apps.get_model('achievements','AchievementEvent').objects.values().get(), before)
            self.assertEqual(apps.get_model('achievements','AchievementDefinition').objects.get(pk=d.pk).public_id,public_id)
            tiers = apps.get_model('achievements','AchievementTier')
            self.assertTrue(tiers.objects.get(definition_id=d.pk,code='silver').parameters['automatic'])
            self.assertTrue(tiers.objects.get(definition_id=d.pk,code='gold').parameters['automatic'])
            self.assertFalse(tiers.objects.get(definition_id=d.pk,code='platinum').parameters['automatic'])
            self.assertFalse(apps.get_model('achievements','AchievementSourceEvent').objects.exists())
            self.assertEqual(apps.get_model('achievements','UserAchievement').objects.count(),1)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
