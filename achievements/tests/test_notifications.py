import json
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch

from django.db import connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from achievements.models import AchievementEvent, AchievementNotification, AchievementNotificationBoundary
from achievements.services.grants import flag_disputed, revoke
from achievements.services.notifications import acknowledge, claim, enqueue, NotificationConflict
from .base import AchievementTestCase


class NotificationTests(AchievementTestCase):
    def setUp(self):
        AchievementNotificationBoundary.objects.update_or_create(pk=1, defaults={"started_at": timezone.now()-timedelta(seconds=1)})
        self.client.force_login(self.user)

    def url(self, name="notifications", event=None):
        return reverse(f"achievement_api:{name}", args=[event.pk] if event else [])

    def post(self, name, event, token=None, client=None):
        return (client or self.client).post(self.url(name,event), json.dumps({"claim_token":str(token or uuid4())}), content_type="application/json")

    def test_grant_upgrade_delivery_and_repeated_operation(self):
        self.award()
        self.award()
        self.award("platinum")
        data=self.client.get(self.url()).json()
        self.assertEqual([n["action"] for n in data["items"]],["grant","upgrade"])
        self.assertEqual(data["items"][1]["from_tier"]["rarity"],"bronze")
        self.assertEqual(data["items"][1]["to_tier"]["rarity"],"platinum")
        self.assertEqual(AchievementNotification.objects.count(),2)
        self.assertEqual(data["items"][0]["recorded_at"],AchievementEvent.objects.first().recorded_at.isoformat())
        self.assertNotIn("evidence",json.dumps(data))
        self.assertNotIn("reason",json.dumps(data))

    def test_revoke_disputed_and_noop_do_not_create_delivery(self):
        self.award(code="training_program")
        flag_disputed(user_id=self.user.pk,confirmation_revoked=True,source_id="correction")
        revoke(user_id=self.user.pk,definition_id=self.definition("training_program").pk,actor=self.staff,reason="Ошибка",operation_id="r")
        self.assertEqual(AchievementEvent.objects.count(),3)
        self.assertEqual(AchievementNotification.objects.count(),1)
        self.assertEqual(self.client.get(self.url()).json()["items"][0]["action"],"grant")

    def test_boundary_excludes_history_and_keeps_pre_login_new_delivery(self):
        AchievementNotificationBoundary.objects.filter(pk=1).update(started_at=timezone.now()+timedelta(days=1))
        self.award()
        old=AchievementEvent.objects.first()
        self.assertFalse(AchievementNotification.objects.exists())
        AchievementNotificationBoundary.objects.filter(pk=1).update(started_at=timezone.now())
        enqueue(old)
        self.award("gold")
        self.client.logout()
        self.assertEqual(self.client.get(self.url()).status_code,401)
        self.client.force_login(self.user)
        first=self.client.get(self.url()).json()
        self.client.logout();self.client.force_login(self.user)
        self.assertEqual(first,self.client.get(self.url()).json())
        self.assertEqual(len(first["items"]),1)
        self.assertEqual(first["items"][0]["action"],"upgrade")

    def test_feed_read_only_and_private_current_user_only(self):
        self.award()
        with CaptureQueriesContext(connection) as queries:
            data=self.client.get(self.url())
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        self.assertEqual(data["Cache-Control"],"private, no-store")
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url()).json()["items"],[])
        self.assertEqual(AchievementNotification.objects.first().read_at,None)

    def test_claim_ack_idempotency_and_foreign_event(self):
        self.award()
        event=AchievementEvent.objects.first();t=uuid4()
        self.assertEqual(self.post("notification_ack",event,t).status_code,409)
        self.assertEqual(self.post("notification_claim",event,t).status_code,200)
        self.assertEqual(self.post("notification_claim",event,uuid4()).status_code,409)
        self.assertEqual(self.client.get(self.url()).json()["items"],[])
        one=self.post("notification_ack",event,t).json()
        two=self.post("notification_ack",event,t).json()
        self.assertEqual(one,two)
        self.assertEqual(self.client.get(self.url()).json()["unread_count"],0)
        self.client.force_login(self.other)
        self.assertEqual(self.post("notification_ack",event,t).status_code,404)
        self.assertEqual(self.post("notification_claim",event,t).status_code,404)

    def test_claim_expiry_reassignment_rejects_old_ack(self):
        self.award();event=AchievementEvent.objects.first();old,new=uuid4(),uuid4()
        claim(self.user.pk,event.pk,old)
        AchievementNotification.objects.update(claim_expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(len(self.client.get(self.url()).json()["items"]),1)
        claim(self.user.pk,event.pk,new)
        with self.assertRaises(NotificationConflict):acknowledge(self.user.pk,event.pk,old)
        self.assertTrue(acknowledge(self.user.pk,event.pk,new)["read"])

    def test_csrf_auth_method_body_and_no_arbitrary_mutation(self):
        self.award();event=AchievementEvent.objects.first()
        csrf=Client(enforce_csrf_checks=True);csrf.force_login(self.user)
        self.assertEqual(self.post("notification_claim",event,client=csrf).status_code,403)
        csrf.get(reverse("achievements"))
        t=uuid4();payload=json.dumps({"claim_token":str(t)})
        for name in ["notification_claim","notification_ack"]:
            response=csrf.post(self.url(name,event),payload,content_type="application/json",HTTP_X_CSRFTOKEN=csrf.cookies['csrftoken'].value)
            self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get(self.url("notification_ack",event)).status_code,405)
        self.assertEqual(self.client.post(self.url("notification_ack",event),json.dumps({"claim_token":"bad","tier":"gold"}),content_type="application/json").status_code,400)
        self.client.logout()
        self.assertEqual(self.post("notification_ack",event).status_code,401)
        self.assertEqual(AchievementEvent.objects.count(),1)

    def test_secret_revoke_feed_and_claim_do_not_reveal(self):
        self.award("platinum",code="clean_week",manual=True)
        event=AchievementEvent.objects.first()
        data=self.client.get(self.url()).json()
        self.assertEqual(data['items'][0]['to_tier']['rarity'],'platinum')
        revoke(user_id=self.user.pk,definition_id=self.definition('clean_week').pk,actor=self.staff,reason='Ошибка',operation_id='r')
        data=self.client.get(self.url()).json()
        self.assertEqual(data['items'],[])
        self.assertEqual(data['unread_count'],0)
        self.assertNotIn('Чистая',json.dumps(data,ensure_ascii=False))
        self.assertEqual(self.post('notification_claim',event).status_code,404)

    def test_projection_rolls_back_with_grant(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.award()
                raise RuntimeError('rollback')
        self.assertFalse(AchievementNotification.objects.exists())
        self.assertFalse(AchievementEvent.objects.exists())

    def test_worker_repairs_only_new_delivery_gap_idempotently(self):
        from django.core.management import call_command
        from io import StringIO
        with patch('achievements.services.notifications.enqueue'):
            self.award()
        self.assertFalse(AchievementNotification.objects.exists())
        call_command('process_achievement_events',stdout=StringIO())
        call_command('process_achievement_events',stdout=StringIO())
        self.assertEqual(AchievementNotification.objects.count(),1)

    def test_portions_preserve_all_unread_and_safe_art(self):
        for i in range(12):
            self.award(operation=f'g{i}',manual=True)
            if i<11:revoke(user_id=self.user.pk,definition_id=self.definition().pk,actor=self.staff,reason='Синтетический цикл',operation_id=f'r{i}')
        data=self.client.get(self.url()).json()
        self.assertEqual(len(data['items']),10);self.assertTrue(data['has_more']);self.assertEqual(data['unread_count'],12)
        from achievements.models import AchievementDefinition
        AchievementDefinition.objects.filter(pk=self.definition().pk).update(art_key='javascript:bad')
        self.assertEqual(self.client.get(self.url()).json()['items'][0]['art_key'],'generic')

    def test_repeated_source_processing_creates_one_notification(self):
        from roadmap.services.confirmations import change_training_confirmation
        from achievements.services.events import process_source_event
        from achievements.models import AchievementSourceEvent
        change_training_confirmation(journey_id=self.journey.pk,actor=self.staff,confirmed=True,comment='Подтверждено')
        source=AchievementSourceEvent.objects.get(provider='roadmap_confirmation')
        process_source_event(source.pk);process_source_event(source.pk)
        self.assertEqual(AchievementNotification.objects.count(),1)
