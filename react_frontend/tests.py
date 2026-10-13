import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import resolve, reverse


class ReactIntegrationTests(TestCase):
    def test_anonymous_redirects_to_existing_login(self):
        response = self.client.get(reverse('react-readiness'))
        self.assertRedirects(response, '/login/?next=/internal/react-readiness/', fetch_redirect_response=False)

    @override_settings(DEBUG=True)
    def test_authenticated_page_and_csrf(self):
        self.client.force_login(get_user_model().objects.create_user(username='react-test'))
        response = self.client.get(reverse('react-readiness'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-react-island="readiness"')
        self.assertContains(response, 'type="module"')
        self.assertContains(response, 'frontend/assets/')
        self.assertNotContains(response, 'localhost:5173')
        self.assertIn('csrftoken', response.cookies)
        self.assertIn('no-store', response['Cache-Control'])

    def test_existing_routes(self):
        self.assertEqual(resolve(reverse('sandbox:dashboard')).namespace, 'sandbox')
        self.assertEqual(resolve(reverse('traineediary:dashboard')).namespace, 'traineediary')
        self.assertEqual(resolve(reverse('login')).url_name, 'login')

    def test_production_collectstatic_and_manifest(self):
        with TemporaryDirectory() as directory:
            with override_settings(DEBUG=False, STATIC_ROOT=directory, SECURE_SSL_REDIRECT=False,
                                   STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                                             'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}):
                call_command('collectstatic', interactive=False, verbosity=0)
                self.client.force_login(get_user_model().objects.create_user(username='react-production'))
                response = self.client.get(reverse('react-readiness'))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'localhost:5173')
                manifest = json.loads((Path(directory) / 'frontend/manifest.json').read_text())
                entry = manifest['src/main.tsx']
                self.assertTrue(entry['isEntry'])
                for asset in [entry['file'], *entry.get('css', [])]:
                    self.assertTrue((Path(directory) / 'frontend' / asset).is_file())
                # Check every emitted resource URL resolves to a collected file.
                import re
                for url in re.findall(r'(?:src|href)="([^"]+)"', response.content.decode()):
                    self.assertTrue((Path(directory) / url.split('/static/', 1)[-1]).is_file(), url)


class TrophyRoomTests(TestCase):
    def test_anonymous_redirect(self):
        response = self.client.get(reverse("achievements"))
        self.assertRedirects(response, "/login/?next=/achievements/", fetch_redirect_response=False)

    @override_settings(DEBUG=True)
    def test_session_profile_and_separate_entrypoint(self):
        user = get_user_model().objects.create_user(username="trophy-user", first_name="<script>unsafe</script>")
        self.client.force_login(user)
        response = self.client.get(reverse("achievements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-react-island="trophy-room"')
        self.assertContains(response, "achievements-")
        self.assertContains(response, "modulepreload")
        self.assertNotContains(response, "<script>unsafe</script>")
        self.assertNotContains(response, "cdn.tailwindcss.com")
        self.assertNotContains(response, "localhost:5173")
        self.assertIn("csrftoken", response.cookies)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(resolve("/achievements/").url_name, "achievements")
        self.assertEqual(resolve(reverse("react-readiness")).url_name, "react-readiness")

    def test_production_assets_and_static_dependencies(self):
        import re
        with TemporaryDirectory() as directory:
            with override_settings(DEBUG=False, STATIC_ROOT=directory, SECURE_SSL_REDIRECT=False,
                                   STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                                             "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}):
                call_command("collectstatic", interactive=False, verbosity=0)
                self.client.force_login(get_user_model().objects.create_user(username="trophy-production"))
                response = self.client.get(reverse("achievements"))
                self.assertEqual(response.status_code, 200)
                manifest = json.loads((Path(directory) / "frontend/manifest.json").read_text())
                self.assertTrue(manifest["src/achievements/main.tsx"]["isEntry"])
                self.assertTrue(manifest["src/main.tsx"]["isEntry"])
                for chunk in manifest.values():
                    for asset in [chunk["file"], *chunk.get("css", []), *chunk.get("assets", [])]:
                        self.assertTrue((Path(directory) / "frontend" / asset).is_file(), asset)
                for url in re.findall(r'(?:src|href)="([^"]+)"', response.content.decode()):
                    self.assertTrue((Path(directory) / url.split("/static/", 1)[-1]).is_file(), url)
