import json
import uuid

from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from achievements.models import AchievementEvent, AchievementSourceEvent, UserAchievement
from .base import AchievementTestCase


class ApiTests(AchievementTestCase):
    def url(self, name="me", code="independent_speed"):
        if name in ("grant", "revoke"):
            args = [self.user.pk, self.definition(code).public_id]
        elif name == "detail":
            args = [self.definition(code).public_id]
        elif name == "user":
            args = [self.other.pk]
        else:
            args = []
        return reverse(f"achievement_api:{name}", args=args)

    def post(self, name="grant", **values):
        body = {"reason": "Проверено наставником", "operation_id": "manual-op", **values}
        if name == "grant":
            body.setdefault("tier", "platinum")
        return self.client.post(self.url(name), json.dumps(body), content_type="application/json")

    def test_auth_staff_ownership_and_methods(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.assertEqual(self.client.get(self.url("user")).status_code, 403)
        self.assertEqual(self.post().status_code, 403)
        self.assertEqual(self.client.post(self.url()).status_code, 405)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url("user")).status_code, 200)
        self.assertEqual(self.client.get(self.url("grant")).status_code, 405)

    def test_manual_grant_revoke_repeats_and_reason(self):
        self.client.force_login(self.staff)
        result = self.post()
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()["action"], "grant")
        self.assertEqual(self.post().json()["action"], "duplicate")
        self.assertEqual(self.post(reason=" ", operation_id="bad").status_code, 400)
        self.assertEqual(self.post(tier="fake", operation_id="bad").status_code, 400)
        self.assertEqual(self.post(tier="bronze").status_code, 409)
        self.assertEqual(self.post("revoke", operation_id="revoke").json()["action"], "revoke")
        self.assertEqual(self.post("revoke", operation_id="revoke").json()["action"], "duplicate")
        self.assertEqual(AchievementEvent.objects.count(), 2)

    def test_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        body = json.dumps({"reason": "Проверено", "operation_id": "csrf", "tier": "bronze"})
        self.assertEqual(client.post(self.url("grant"), body, content_type="application/json").status_code, 403)
        client.get(reverse("login"))
        token = client.cookies["csrftoken"].value
        response = client.post(self.url("grant"), body, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200, response.content)

    def test_get_collection_and_details_are_select_only_and_do_not_reconcile(self):
        self.metric()
        self.client.force_login(self.user)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url())
            detail = self.client.get(self.url("detail", "review_quality"))
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(UserAchievement.objects.exists())
        self.assertFalse(AchievementSourceEvent.objects.exists())
        self.assertEqual(response.json()["stats"]["earned"], 0)
        self.assertEqual(len(response.json()["items"]), 11)
        self.assertTrue(all(i["progress"] is None for i in response.json()["items"]))
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_secret_json_redaction_collection_detail_and_unearned_history(self):
        self.client.force_login(self.user)
        for url in (self.url(), self.url("detail", "clean_week")):
            response = self.client.get(url)
            text = response.content.decode()
            self.assertNotIn("clean_week", text)
            self.assertNotIn("Чистая неделя", text)
            data = response.json()
            placeholder = data.get("achievement") or next(i for i in data["items"] if i["secret"])
            for forbidden in ("code", "category", "supported_tiers", "criterion", "evidence", "rule_version"):
                self.assertNotIn(forbidden, placeholder)
            self.assertEqual(placeholder["title"], "Секретное достижение")

    def test_earned_secret_reveals_only_after_real_manual_grant(self):
        self.award("platinum", code="clean_week", manual=True)
        self.client.force_login(self.user)
        data = self.client.get(self.url("detail", "clean_week")).json()
        self.assertEqual(data["achievement"]["code"], "clean_week")
        self.assertTrue(data["achievement"]["manual"])
        self.assertEqual(len(data["history"]), 1)

    def test_stats_and_history_count_families_not_metals(self):
        self.award()
        self.award("platinum")
        self.client.force_login(self.user)
        data = self.client.get(self.url()).json()
        self.assertEqual(data["stats"]["earned"], 1)
        self.assertEqual(data["stats"]["rarities"]["platinum"], 1)
        self.assertEqual(data["stats"]["rarities"]["bronze"], 0)
        history = self.client.get(self.url("detail")).json()["history"]
        self.assertEqual([(e["action"], e["to_tier"]) for e in history], [("grant", "bronze"), ("upgrade", "platinum")])

    def test_nonexistent_definition_invalid_body_revision_and_cursor(self):
        self.client.force_login(self.staff)
        url = reverse("achievement_api:grant", args=[self.user.pk, uuid.uuid4()])
        self.assertEqual(self.client.post(url, "{}", content_type="application/json").status_code, 404)
        for body in ([], {"reason": "x", "operation_id": "op", "tier": "bronze", "score": 100},
                     {"reason": "x", "operation_id": "op", "tier": "bronze", "expected_revision": True}):
            self.assertEqual(self.client.post(self.url("grant"), json.dumps(body), content_type="application/json").status_code, 400)
        self.award()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url("detail"), {"cursor": "invalid"}).status_code, 400)
