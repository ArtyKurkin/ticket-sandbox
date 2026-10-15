from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from achievements.models import AchievementDefinition, AchievementNotification, AchievementNotificationBoundary
from achievements.services.catalog import seed_catalog
from achievements.services.grants import grant
from achievements.services.notifications import acknowledge, claim, NotificationConflict


@skipUnless(connection.vendor=='postgresql','Requires PostgreSQL row locks')
class NotificationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        seed_catalog()
        AchievementNotificationBoundary.objects.update_or_create(pk=1,defaults={'started_at':timezone.now()})
        self.user=User.objects.create_user('notification-race')
        definition=AchievementDefinition.objects.get(code='independent_speed')
        self.event=grant(user_id=self.user.pk,definition_id=definition.pk,tier_code='bronze',evidence={},occurred_at=timezone.now(),source_type='test',source_ref='n',operation_id='n')[2]

    def parallel(self,functions):
        barrier=Barrier(len(functions))
        def run(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:return fn()
                except NotificationConflict:return 'conflict'
            finally:connection.close()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return [f.result(timeout=20) for f in [pool.submit(run,fn) for fn in functions]]

    def test_only_one_concurrent_claim_wins(self):
        first,second=uuid4(),uuid4()
        result=self.parallel([lambda:claim(self.user.pk,self.event.pk,first),lambda:claim(self.user.pk,self.event.pk,second)])
        self.assertEqual(result.count('conflict'),1)
        self.assertEqual(AchievementNotification.objects.count(),1)

    def test_concurrent_ack_same_timestamp(self):
        t=uuid4();claim(self.user.pk,self.event.pk,t)
        result=self.parallel([lambda:acknowledge(self.user.pk,self.event.pk,t),lambda:acknowledge(self.user.pk,self.event.pk,t)])
        self.assertEqual(result[0],result[1])
        self.assertIsNotNone(AchievementNotification.objects.get().read_at)
