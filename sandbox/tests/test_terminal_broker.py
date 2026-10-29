import json
import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from sandbox.models import Task, TaskAttempt, Queue, TraineeProfile
from sandbox.services.docker_service import create_terminal_container, create_task_container, task_resource_name
from sandbox.services.terminal_broker import authorization_header, credential, lease_credential, revoke


@override_settings(TERMINAL_BROKER_ENABLED=True, SECURE_SSL_REDIRECT=False)
class BrokerAuthorizationTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="broker-owner")
        profile, _ = TraineeProfile.objects.get_or_create(user=user)
        profile.level = "l1"
        profile.save(update_fields=["level"])
        queue, _ = Queue.objects.get_or_create(slug="l1", defaults={"name": "L1", "required_level": "l1"})
        task = Task.objects.create(queue=queue, title="Broker", slug="broker-task")
        self.attempt = TaskAttempt.objects.create(user=user, task=task,
            status=TaskAttempt.Status.IN_PROGRESS, environment_status="ready", container_id="a" * 64,
            container_name="task", terminal_container_name="terminal", terminal_url="/terminal/1/",
            terminal_port=24000, environment_generation=uuid.uuid4())
        self.identity = {"container_id": self.attempt.container_id, "attempt": self.attempt.pk,
                         "queue": "l1", "task": "broker-task", "generation": str(self.attempt.environment_generation)}
        self.token = lease_credential(self.attempt.pk, self.attempt.environment_generation)
        self.url = reverse("sandbox:terminal_broker_authorize")

    def authorize(self, identity=None, token=None):
        return self.client.post(self.url, data=json.dumps(identity or self.identity),
            content_type="application/json", HTTP_AUTHORIZATION="Bearer " + (token or self.token))

    def test_exact_identity_authorized(self):
        self.assertEqual(self.authorize().status_code, 204)

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_internal_http_lease_works_with_https_enforced_for_browser(self):
        self.assertEqual(self.authorize().status_code, 204)
        self.assertEqual(self.authorize(token='wrong').status_code, 403)
        self.assertEqual(self.client.get('/').status_code, 301)

    def test_basic_password_cannot_authorize_a_lease(self):
        basic_password = credential(self.attempt.pk, self.attempt.environment_generation)
        self.assertNotEqual(self.token, basic_password)
        self.assertEqual(self.authorize(token=basic_password).status_code, 403)

    def test_disabled_owner_revokes_existing_lease(self):
        get_user_model().objects.filter(pk=self.attempt.user_id).update(is_active=False)
        self.assertEqual(self.authorize().status_code, 403)

    def test_each_foreign_component_and_wrong_credential_denied(self):
        for key, value in self.identity.items():
            with self.subTest(key=key):
                changed = {**self.identity, key: value + 1 if key == "attempt" else "foreign"}
                self.assertEqual(self.authorize(changed).status_code, 403)
        self.assertEqual(self.authorize(token="bad").status_code, 403)

    def test_restart_finish_and_historical_attempt_revoke_lease(self):
        for changes in ({"environment_status": "restarting"}, {"environment_status": "idle"},
                        {"status": TaskAttempt.Status.PASSED}, {"is_current": False}):
            with self.subTest(changes=changes):
                TaskAttempt.objects.filter(pk=self.attempt.pk).update(**changes)
                self.assertEqual(self.authorize().status_code, 403)
                TaskAttempt.objects.filter(pk=self.attempt.pk).update(environment_status="ready",
                    status=TaskAttempt.Status.IN_PROGRESS, is_current=True)

    def test_replacement_generation_revokes_old_token(self):
        TaskAttempt.objects.filter(pk=self.attempt.pk).update(environment_generation=uuid.uuid4())
        self.assertEqual(self.authorize().status_code, 403)

    def test_browser_must_be_owner_and_gateway_injects_private_credential(self):
        url = reverse("sandbox:terminal_auth", args=[self.attempt.pk, 24000])
        self.assertEqual(self.client.get(url).status_code, 401)
        other = get_user_model().objects.create_user(username="other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.attempt.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["X-Terminal-Authorization"],
                         authorization_header(self.attempt.pk, self.attempt.environment_generation))

    @override_settings(TERMINAL_BROKER_ENABLED=False)
    def test_flag_disable_revokes_existing_broker_leases(self):
        self.assertEqual(self.authorize().status_code, 403)


@override_settings(TERMINAL_BROKER_ENABLED=True)
class BrokerLaunchTests(SimpleTestCase):
    def test_long_task_names_remain_dns_safe_and_attempt_specific(self):
        name = task_resource_name('l1', 'a' * 100, 123456789, terminal=True)
        self.assertLessEqual(len(name), 63)
        self.assertEqual(name, task_resource_name('l1', 'a' * 100, 123456789, terminal=True))
        self.assertNotEqual(name, task_resource_name('l1', 'a' * 100, 123456788, terminal=True))

    @patch("sandbox.services.docker_service.Path.exists", return_value=True)
    @patch("sandbox.services.docker_service.get_docker_client")
    def test_new_task_generation_is_unique_and_orphans_are_reaped(self, get_client, exists):
        client = get_client.return_value
        create_task_container("l1", "task", 17)
        first = client.containers.run.call_args.kwargs
        create_task_container("l1", "task", 17)
        second = client.containers.run.call_args.kwargs
        self.assertTrue(first["init"])
        generation = first["labels"]["ticket-sandbox.generation"]
        self.assertEqual(str(uuid.UUID(generation)), generation)
        self.assertNotEqual(generation, second["labels"]["ticket-sandbox.generation"])

    @patch("sandbox.services.docker_service.remove_terminal_container")
    @patch("sandbox.services.terminal_broker.launch")
    @patch("sandbox.services.docker_service.get_docker_client")
    def test_both_modes_have_no_docker_access_in_ttyd(self, get_client, launch, remove):
        client = get_client.return_value
        generation = str(uuid.uuid4())
        launch.return_value = (MagicMock(), "private-socket-volume", generation)
        for mode in ("host_port", "docker_network"):
            with self.subTest(mode=mode), override_settings(TERMINAL_NETWORK_MODE=mode):
                create_terminal_container("l1", "task", 1, "target", 24000)
                kwargs = client.containers.run.call_args.kwargs
                self.assertEqual(kwargs["volumes"], {"private-socket-volume": {"bind": "/run/terminal", "mode": "ro"}})
                self.assertNotIn("docker", kwargs["command"])
                self.assertIn("terminal.broker_client", kwargs["command"])
                self.assertTrue(kwargs["read_only"])
                if mode == "host_port":
                    self.assertEqual(kwargs["ports"], {"7681/tcp": ("127.0.0.1", 24000)})
                else:
                    self.assertNotIn("ports", kwargs)
                    self.assertIn("network", kwargs)

    def test_foreign_broker_never_stopped(self):
        client = MagicMock()
        client.containers.get.return_value.labels = {"ticket-sandbox.type": "other"}
        with self.assertRaises(RuntimeError):
            revoke(client, "terminal")
        client.containers.get.return_value.stop.assert_not_called()

    def test_nonzero_exit_does_not_block_teardown(self):
        client = MagicMock()
        broker = client.containers.get.return_value
        broker.labels = {"ticket-sandbox.type": "terminal-broker", "ticket-sandbox.terminal": "terminal"}
        broker.wait.return_value = {"StatusCode": 1}
        broker.attrs = {"State": {"Running": False}}
        revoke(client, "terminal")
        broker.remove.assert_called_once()
