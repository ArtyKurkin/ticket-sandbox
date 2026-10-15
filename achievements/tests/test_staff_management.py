import json
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from achievements.models import AchievementEvent, UserAchievement
from achievements.services.grants import flag_disputed
from .base import AchievementTestCase


class StaffManagementTests(AchievementTestCase):
    def url(self, name="user", code="independent_speed", user_id=None):
        args = [user_id or self.user.pk]
        if name != "user":
            args.append(self.definition(code).public_id)
        return reverse(f"achievement_api:{name}", args=args)

    def post(self, name="grant", *, tier="bronze", operation="op", revision=0, reason="Проверено наставником", code="independent_speed"):
        body = dict(reason=reason, operation_id=operation, expected_revision=revision)
        if name == "grant":
            body["tier"] = tier
        return self.client.post(self.url(name, code), json.dumps(body), content_type="application/json")

    def test_staff_catalogue_reveals_management_metadata_but_me_keeps_secret_hidden(self):
        self.client.force_login(self.staff)
        data = self.client.get(self.url()).json()
        self.assertEqual(len(data["items"]), 11)
        secret = next(i for i in data["items"] if i["code"] == "clean_week")
        self.assertTrue(secret["revealed"])
        self.assertEqual(secret["supported_tiers"][0]["rarity"], "platinum")
        self.assertEqual(secret["revision"], 0)
        personal = self.client.get(reverse("achievement_api:me")).json()
        self.assertNotIn("clean_week", json.dumps(personal))

    def test_staff_details_permission_ownership_and_read_only(self):
        self.award(manual=True)
        self.assertEqual(self.client.get(self.url("user_detail")).status_code, 401)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url("user_detail")).status_code, 403)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.client.force_login(self.staff)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url("user_detail"))
            self.client.get(self.url())
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in queries))
        event = response.json()["history"][0]
        self.assertEqual(event["actor_id"], self.staff.pk)
        self.assertEqual(event["actor_name"], self.staff.username)
        other = self.client.get(self.url("user_detail", user_id=self.other.pk)).json()
        self.assertEqual(other["history"], [])
        self.assertIsNone(other["achievement"]["highest_tier"])

    def test_grant_upgrade_revoke_repeat_and_revision_conflict(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.post().json()["action"], "grant")
        self.assertEqual(self.post().json()["action"], "duplicate")
        self.assertEqual(self.post(tier="platinum", operation="upgrade", revision=1).json()["action"], "upgrade")
        self.assertEqual(self.post(tier="gold", operation="stale", revision=0).status_code, 409)
        self.assertEqual(UserAchievement.objects.count(), 1)
        self.assertEqual(self.post("revoke", operation="revoke", revision=2).json()["action"], "revoke")
        data = self.client.get(self.url("user_detail")).json()
        self.assertEqual([e["action"] for e in data["history"]], ["grant", "upgrade", "revoke"])
        self.assertEqual(data["history"][1]["from_tier"], "bronze")
        self.assertEqual(data["history"][1]["to_tier"], "platinum")
        self.assertTrue(data["achievement"]["auto_grant_blocked"])
        self.assertIsNone(data["achievement"]["highest_tier"])
        self.assertEqual(AchievementEvent.objects.count(), 3)

    def test_direct_platinum_and_invalid_requests(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.post(tier="platinum").json()["action"], "grant")
        self.assertEqual(AchievementEvent.objects.count(), 1)
        self.assertEqual(self.post("revoke", reason=" ", operation="r", revision=1).status_code, 400)
        self.assertEqual(self.post(tier="fake", operation="f", revision=1).status_code, 400)
        self.assertEqual(self.client.get(self.url("user_detail", user_id=999999)).status_code, 404)
        self.assertEqual(self.client.get(self.url("user_detail") + "?cursor=-1").status_code, 400)

    def test_staff_secret_history_available_after_revoke_without_personal_leak(self):
        self.client.force_login(self.staff)
        self.post(tier="platinum", code="clean_week")
        self.post("revoke", code="clean_week", operation="r", revision=1)
        staff = self.client.get(self.url("user_detail", "clean_week")).json()
        self.assertEqual([e["action"] for e in staff["history"]], ["grant", "revoke"])
        self.client.force_login(self.user)
        own = self.client.get(reverse("achievement_api:detail", args=[self.definition("clean_week").public_id])).json()
        self.assertEqual(own["history"], [])
        self.assertNotIn("clean_week", json.dumps(own))

    def test_cursor_pagination_preserves_real_dates_and_author(self):
        self.client.force_login(self.staff)
        for i in range(26):
            self.post(operation=f"g{i}", revision=i*2)
            if i < 25:
                self.post("revoke", operation=f"r{i}", revision=i*2+1)
        first = self.client.get(self.url("user_detail")).json()
        second = self.client.get(self.url("user_detail"), {"cursor": first["next_cursor"]}).json()
        history = first["history"] + second["history"]
        self.assertEqual(len(history), 51)
        self.assertEqual(len({e["id"] for e in history}), 51)
        self.assertEqual({e["actor_id"] for e in history}, {self.staff.pk})
        self.assertEqual(history[0]["recorded_at"], AchievementEvent.objects.first().recorded_at.isoformat())

    def test_staff_post_csrf_and_trainee_forbidden(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        body = json.dumps(dict(tier="bronze", reason="Проверено", operation_id="csrf", expected_revision=0))
        self.assertEqual(client.post(self.url("grant"), body, content_type="application/json").status_code, 403)
        client.get(reverse("login"))
        response = client.post(self.url("grant"), body, content_type="application/json", HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 200)
        self.client.force_login(self.user)
        self.assertEqual(self.post().status_code, 403)

    def test_automatic_award_and_disputed_evidence_keep_real_history_and_tier(self):
        self.award(code="training_program")
        flag_disputed(user_id=self.user.pk, confirmation_revoked=True, source_id="test-revocation")
        self.client.force_login(self.staff)
        data = self.client.get(self.url("user_detail", "training_program")).json()
        self.assertEqual(data["achievement"]["highest_tier"]["code"], "bronze")
        self.assertFalse(data["achievement"]["manual"])
        self.assertEqual(data["achievement"]["data_quality"], "disputed")
        self.assertEqual([e["action"] for e in data["history"]], ["grant", "evidence_disputed"])
        self.assertIsNone(data["history"][1]["actor_id"])
        self.assertIsNone(data["history"][1]["actor_name"])
