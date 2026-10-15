from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class NotificationMigrationTests(TransactionTestCase):
    def test_existing_events_stay_out_and_new_grant_is_delivered(self):
        previous=('achievements','0004_audit_guards')
        current=('achievements','0005_notifications')
        executor=MigrationExecutor(connection)
        try:
            from achievements.services.catalog import seed_catalog
            seed_catalog()  # TransactionTestCase flush may have cleared migration-seeded data.
            executor.migrate([previous])
            apps=executor.loader.project_state([previous]).apps
            User=apps.get_model('auth','User')
            Definition=apps.get_model('achievements','AchievementDefinition')
            Tier=apps.get_model('achievements','AchievementTier')
            Entitlement=apps.get_model('achievements','UserAchievement')
            Event=apps.get_model('achievements','AchievementEvent')
            user=User.objects.create(username='before-notifications')
            definition=Definition.objects.get(code='independent_speed')
            bronze=Tier.objects.get(definition=definition,code='bronze')
            entitlement=Entitlement.objects.create(user=user,definition=definition,active_tier=bronze)
            old=Event.objects.create(entitlement=entitlement,action='grant',to_tier=bronze,occurred_at=timezone.now(),source_type='test',source_ref='old',rule_version=1,evidence={},evidence_digest='old',idempotency_key='old')
            executor=MigrationExecutor(connection);executor.migrate([current])
            from achievements.models import AchievementNotification,AchievementNotificationBoundary
            from achievements.services.grants import grant
            self.assertFalse(AchievementNotification.objects.exists())
            self.assertGreater(AchievementNotificationBoundary.objects.get(pk=1).started_at,old.recorded_at)
            grant(user_id=user.pk,definition_id=definition.pk,tier_code='platinum',evidence={},occurred_at=timezone.now(),source_type='test',source_ref='new',operation_id='new')
            self.assertEqual(AchievementNotification.objects.count(),1)
            self.assertNotEqual(AchievementNotification.objects.get().event_id,old.pk)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
