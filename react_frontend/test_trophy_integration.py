import json
import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(DEBUG=True)
class TrophyApiBootstrapTests(TestCase):
    def test_bootstrap_permission_and_routes_are_server_owned(self):
        for staff in (False, True):
            user = User.objects.create_user(username=f"trophy-bootstrap-{staff}", is_staff=staff)
            self.client.force_login(user)
            response = self.client.get(reverse("achievements") + "?canDemo=true&is_staff=true&achievementsApiUrl=/fake/")
            props = json.loads(re.search(r'<script id="trophy-room-props" type="application/json">(.*?)</script>', response.content.decode(), re.S)[1])
            self.assertIs(props["canDemo"], staff)
            self.assertEqual(props["achievementsApiUrl"], reverse("achievement_api:me"))
            self.assertEqual(props["loginUrl"], reverse("login"))
            self.assertNotIn("achievements", props)
            self.assertNotIn("stats", props)
            self.assertIn("csrftoken", response.cookies)
            self.assertIn("no-store", response["Cache-Control"])
