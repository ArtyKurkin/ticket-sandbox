from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class HomeRedirectTests(TestCase):
    def setUp(self):
        self.mentor = User.objects.create_user(
            username="home-mentor",
            password="test-password",
            is_staff=True,
        )

        self.trainee = User.objects.create_user(
            username="home-trainee",
            password="test-password",
            is_staff=False,
        )

    def test_anonymous_user_is_sent_to_login(
        self,
    ):
        response = self.client.get(
            reverse("home"),
        )

        self.assertRedirects(
            response,
            (
                f"{reverse('login')}"
                f"?next={reverse('home')}"
            ),
        )

    def test_mentor_is_sent_to_trainee_diary(
        self,
    ):
        self.client.force_login(
            self.mentor,
        )

        response = self.client.get(
            reverse("home"),
        )

        self.assertRedirects(
            response,
            reverse(
                "traineediary:dashboard",
            ),
        )

    def test_trainee_is_sent_to_ticket_sandbox(
        self,
    ):
        self.client.force_login(
            self.trainee,
        )

        response = self.client.get(
            reverse("home"),
        )

        self.assertRedirects(
            response,
            reverse(
                "sandbox:dashboard",
            ),
        )

    def test_sandbox_dashboard_has_separate_url(
        self,
    ):
        self.assertEqual(
            reverse("sandbox:dashboard"),
            "/sandbox/",
        )
