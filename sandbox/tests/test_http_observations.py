import json
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from sandbox.models import HTTPObservationRun, SandboxEnvironmentEvent, TaskAttempt, TechnicalCheckExecution
from sandbox.services import http_observations as service, ledger
from sandbox.services.checks import run_attempt_check, start_attempt_check_in_background
from sandbox.services.technical_evidence import get_technical_evidence
from experiments.trusted_checker_mvp.docker_pilot import adapter
from experiments.trusted_checker_mvp.docker_pilot.test_pilot import fixture, FakeAPI, frame
from .base import SandboxTestCase


class HTTPObservationTests(SandboxTestCase):
    def setUp(self):
        self.user = self.create_user("http-observer", level="l1")
        self.queue = self.create_queue("l1")
        self.task = self.create_task(self.queue, "service-bind-localhost", order=1)
        self.environment = uuid4()
        self.attempt = TaskAttempt.objects.create(user=self.user, task=self.task,
            status="in_progress", environment_status="ready", container_id="a" * 64,
            container_name="lab-target", environment_started_at=timezone.now(), environment_finished_at=timezone.now())
        self.env_event()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.artifacts = Path(self.directory.name) / "artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.policy, execution = fixture()
        execution = replace(execution, attempt_id=self.attempt.pk, user_id=self.user.pk, environment_uuid=str(self.environment))
        self.mapping = {key: value for key, value in asdict(execution).items()
                        if key not in ("attempt_id", "user_id", "run_id", "ordinal")}
        TaskAttempt.objects.filter(pk=self.attempt.pk).update(http_observation_runtime=self.mapping)
        self.api = FakeAPI(self.policy, execution)
        self.api.target["Config"]["Labels"]["ticket-sandbox.attempt"] = str(self.attempt.pk)
        self.api.close = MagicMock()
        self.config = dict(daemon_id=self.policy.daemon_id, network_id=self.policy.network_id,
                           scope=self.policy.scope, subnet=self.policy.subnet, target_image=self.policy.target_image,
                           verifier_image=self.policy.verifier_image, api_socket="/approved/fake.sock", artifact_dir=str(self.artifacts))
        config_path = Path(self.directory.name) / "config.json"
        config_path.write_text(json.dumps(self.config))
        override = override_settings(SANDBOX_HTTP_OBSERVATION_ENABLED=True,
            SANDBOX_HTTP_OBSERVATION_ATTEMPT_ID=self.attempt.pk, SANDBOX_HTTP_OBSERVATION_CONFIG=str(config_path))
        override.enable()
        self.addCleanup(override.disable)
        for target, kwargs in (("sandbox.services.http_observations.make_api", {"return_value": self.api}),
                                ("sandbox.tasks.run_http_observation_task.delay", {}),
                                ("experiments.trusted_checker_mvp.docker_pilot.adapter.select.select", {"side_effect": lambda readers, *args: (readers, [], [])})):
            patcher = patch(target, **kwargs)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if target.endswith("make_api"):
                self.factory = mock
            elif target.endswith(".delay"):
                self.delay = mock
        self.client.force_login(self.user)

    def env_event(self, kind="start", complete=True):
        values = dict(operation_id=self.environment, attempt_id=self.attempt.pk, user_id=self.user.pk,
                      task_id=self.task.pk, attempt_number=self.attempt.attempt_number, kind=kind,
                      origin="trainee", actor_id=self.user.pk, requested_at=timezone.now(), occurred_at=timezone.now())
        SandboxEnvironmentEvent.objects.create(**values, phase="requested")
        if complete:
            SandboxEnvironmentEvent.objects.create(**values, phase="finished", outcome="success")

    def request_run(self):
        with self.captureOnCommitCallbacks(execute=True):
            run, created = service.request_observation(attempt_id=self.attempt.pk, user_id=self.user.pk)
        return run

    def run_complete(self):
        run = self.request_run()
        service.run_observation(str(run.run_id))
        run.refresh_from_db()
        return run

    def academic_snapshot(self):
        return (TaskAttempt.objects.get(pk=self.attempt.pk).__dict__.copy(),
                {m._meta.label: m.objects.count() for m in apps.get_models()
                 if m._meta.app_label in ("sandbox", "achievements", "roadmap") and m is not HTTPObservationRun})

    def test_match_persists_without_any_academic_or_legacy_writes(self):
        before = self.academic_snapshot()
        with CaptureQueriesContext(connection) as captured:
            run = self.run_complete()
        writes = [q["sql"] for q in captured if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertTrue(writes)
        self.assertTrue(all('"sandbox_httpobservationrun"' in sql for sql in writes), writes)
        self.assertEqual((run.status, run.http, run.reason), ("finished", "matched", "http_match"))
        self.assertFalse(run.academic_pass)
        self.assertEqual(run.task_verdict, "unknown")
        after = self.academic_snapshot()
        before[0].pop("_state"); after[0].pop("_state")
        self.assertEqual(before, after)
        self.assertFalse(get_technical_evidence(self.attempt, use_cached=False).is_completed)
        self.assertEqual(self.api.workers, {})
        self.assertEqual(run.runtime["attempt_id"], self.attempt.pk)
        self.assertEqual(run.runtime["environment_uuid"], str(self.environment))

    def test_pending_technical_identity_is_reused_read_only(self):
        execution = TechnicalCheckExecution.objects.create(run_id=uuid4(), attempt_id=self.attempt.pk,
            user_id=self.user.pk, task_id=self.task.pk, attempt_number=1, ordinal=8,
            requested_at=timezone.now(), checker_kind="task_checker", source="service")
        run = self.run_complete()
        self.assertEqual((run.run_id, run.ordinal, run.execution_origin), (execution.run_id, 8, "technical_execution"))
        self.assertEqual(run.technical_execution_id, execution.pk)
        self.assertFalse(execution.events.exists())

    def test_finished_technical_execution_is_only_an_anchor(self):
        execution = TechnicalCheckExecution.objects.create(attempt_id=self.attempt.pk, user_id=self.user.pk,
            task_id=self.task.pk, attempt_number=1, ordinal=1, requested_at=timezone.now(), checker_kind="task_checker")
        execution.events.create(phase="finished", occurred_at=timezone.now(), result="unknown")
        run = self.run_complete()
        self.assertEqual(run.execution_origin, "observation")
        self.assertNotEqual(run.run_id, execution.run_id)
        self.assertEqual(run.technical_execution_id, execution.pk)
        self.assertEqual(execution.events.count(), 1)

    def test_disabled_has_no_row_client_or_dispatch(self):
        with override_settings(SANDBOX_HTTP_OBSERVATION_ENABLED=False):
            response = self.client.post(reverse("sandbox:http_observation", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(HTTPObservationRun.objects.exists())
        self.factory.assert_not_called(); self.delay.assert_not_called()

    def test_other_task_keeps_legacy_route_when_pilot_is_enabled(self):
        task = self.create_task(self.queue, "other-task", order=2)
        attempt = TaskAttempt.objects.create(user=self.user, task=task, container_name="other", environment_status="ready")
        with patch.object(TaskAttempt, "is_available", new=property(lambda self: True)), patch("sandbox.views.start_attempt_check_in_background") as legacy:
            self.client.post(reverse("sandbox:check_task", args=[attempt.pk]))
        legacy.assert_called_once()
        self.assertFalse(HTTPObservationRun.objects.exists())

    def test_broker_unavailable_is_diagnostic_unknown(self):
        self.delay.side_effect = RuntimeError("synthetic broker unavailable")
        before = self.academic_snapshot()
        run = self.request_run()
        run.refresh_from_db()
        self.assertEqual((run.http, run.reason, run.status), ("unknown", "dispatch_unavailable", "finished"))
        self.factory.assert_not_called()
        after = self.academic_snapshot()
        before[0].pop("_state"); after[0].pop("_state")
        self.assertEqual(before, after)

    def test_owner_only_and_no_user_configuration_or_result_upload(self):
        url = reverse("sandbox:http_observation", args=[self.attempt.pk])
        for field in ("url", "ip", "command", "image", "result"):
            self.assertEqual(self.client.post(url, {field: "untrusted"}).status_code, 400)
        self.assertEqual(self.client.post(url, '{"http":"matched"}', content_type="application/json").status_code, 400)
        other = self.create_user("other-http", level="l1")
        self.client.force_login(other)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertFalse(HTTPObservationRun.objects.exists())

    def test_current_attempt_and_generation_required_before_docker(self):
        run = self.request_run()
        self.environment = uuid4()
        self.env_event("reset", complete=False)
        service.run_observation(run.run_id)
        run.refresh_from_db()
        self.assertEqual((run.status, run.http), ("finished", "unknown"))
        self.factory.assert_not_called()

    def test_historical_attempt_job_is_stale(self):
        run = self.request_run()
        TaskAttempt.objects.filter(pk=self.attempt.pk).update(is_current=False)
        service.run_observation(run.run_id)
        run.refresh_from_db()
        self.assertEqual(run.http, "unknown")
        self.factory.assert_not_called()

    def test_restart_before_worker_cannot_rebaseline_runtime(self):
        run = self.request_run()
        self.api.target["State"]["Pid"] += 1
        self.api.target["State"]["StartedAt"] = "2026-10-22T12:00:00.000000000Z"
        service.run_observation(run.run_id)
        run.refresh_from_db()
        self.assertEqual((run.http, run.reason), ("unknown", "runtime_changed"))
        self.assertFalse(self.api.workers)

    def test_existing_environment_requires_explicit_pilot_recreation(self):
        TaskAttempt.objects.filter(pk=self.attempt.pk).update(http_observation_runtime={})
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.request_run()
        self.factory.assert_not_called()

    def test_creation_readback_pins_runtime_without_model_writes(self):
        from sandbox.services.observation_config import capture_runtime
        container = MagicMock(id=self.attempt.container_id, attrs=self.api.target)
        with CaptureQueriesContext(connection) as captured:
            mapping = capture_runtime(self.attempt, container)
        self.assertEqual(mapping, self.mapping)
        self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in captured))
        container.reload.assert_called_once()

    def test_explicit_environment_reset_saves_new_generation_mapping(self):
        from sandbox.services import environments
        environments.mark_environment_restarting(self.attempt)
        self.environment = SandboxEnvironmentEvent.objects.filter(attempt_id=self.attempt.pk, phase="requested").latest("pk").operation_id
        self.api.target["Config"]["Labels"]["tc-mvp.environment"] = str(self.environment)
        container = MagicMock(id=self.attempt.container_id, attrs=self.api.target)
        container.name = "lab-target"
        terminal = MagicMock()
        terminal.name = "lab-terminal"
        with patch.object(environments, "remove_task_container"), patch.object(environments, "create_task_container", return_value=container), patch.object(environments, "create_terminal_container", return_value=terminal), patch.object(environments, "wait_for_terminal_ready"), patch.object(environments, "get_free_port", return_value=25001):
            environments.run_environment_restart(self.attempt)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.http_observation_runtime["environment_uuid"], str(self.environment))
        self.assertEqual(self.run_complete().http, "matched")

    def test_new_technical_event_during_probe_makes_observation_stale(self):
        execution = TechnicalCheckExecution.objects.create(attempt_id=self.attempt.pk, user_id=self.user.pk,
            task_id=self.task.pk, attempt_number=1, ordinal=1, requested_at=timezone.now(), checker_kind="task_checker")
        self.api.hooks["start"] = lambda api: execution.events.create(phase="started", occurred_at=timezone.now())
        run = self.run_complete()
        self.assertEqual(run.http, "unknown")
        self.assertFalse(run.result)

    def test_reset_during_capture_discards_match(self):
        def reset(api):
            self.environment = uuid4()
            self.env_event("reset")
        self.api.hooks["start"] = reset
        run = self.run_complete()
        self.assertEqual(run.http, "unknown")
        self.assertFalse(run.result)
        self.assertEqual(self.api.workers, {})

    def test_container_restart_and_malformed_stream_are_unknown(self):
        self.api.hooks["start"] = lambda api: api.target.update(RestartCount=1)
        run = self.run_complete()
        self.assertEqual((run.http, run.reason), ("unknown", "runtime_changed"))
        self.api.hooks.clear()
        self.api.target["RestartCount"] = 0
        self.api.stream.closed = False
        self.api.stream_transform = lambda data: frame(b"{")
        run = self.run_complete()
        self.assertEqual(run.http, "unknown")
        self.assertFalse(run.academic_pass)

    def test_duplicate_request_and_celery_delivery_do_not_redispatch(self):
        run = self.request_run()
        again = self.request_run()
        self.assertEqual(run.pk, again.pk)
        self.delay.assert_called_once()
        service.run_observation(run.run_id)
        calls = len(self.api.calls)
        service.run_observation(run.run_id)
        self.assertEqual(len(self.api.calls), calls)
        with self.assertRaises(IntegrityError), transaction.atomic():
            # Database constraints are tested separately from the service lock.
            HTTPObservationRun.objects.create(attempt=self.attempt, requested_by_id=self.user.pk,
                run_id=run.run_id, ordinal=99, environment_uuid=self.environment, identity={}, policy={})

    def test_source_reads_fresh_db_without_data_writes(self):
        observations = []
        def read(api):
            row = HTTPObservationRun.objects.get(status="running")
            with CaptureQueriesContext(connection) as captured:
                result = service.DjangoObservationSource(row.run_id)(self.attempt.pk)
            observations.append(result)
            self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in captured))
        self.api.hooks["start"] = read
        self.assertEqual(self.run_complete().http, "matched")
        self.assertEqual(len(observations), 1)

    def test_flag_routes_check_endpoint_and_blocks_queued_legacy_job(self):
        with self.captureOnCommitCallbacks(execute=True), patch("sandbox.views.start_attempt_check_in_background") as legacy:
            response = self.client.post(reverse("sandbox:check_task", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 302)
        legacy.assert_not_called()
        self.assertEqual(HTTPObservationRun.objects.count(), 1)
        with patch("sandbox.services.checks.check_task_container") as executor:
            self.assertFalse(run_attempt_check(attempt=self.attempt, user_id=self.user.pk).is_success)
            self.assertIsNone(start_attempt_check_in_background(attempt=self.attempt, user_id=self.user.pk))
        executor.assert_not_called()
        self.assertFalse(TechnicalCheckExecution.objects.exists())

    def test_ui_and_status_keep_http_separate_from_technical_evidence(self):
        self.run_complete()
        response = self.client.get(reverse("sandbox:task_detail", args=[self.attempt.pk]))
        self.assertContains(response, "Проверить HTTP без зачёта")
        self.assertNotContains(response, "Сдать техническую часть")
        data = self.client.get(reverse("sandbox:http_observation_status", args=[self.attempt.pk])).json()
        self.assertEqual(data["observation"]["http"], "matched")
        self.assertFalse(data["academic_pass"])
        legacy = self.client.get(reverse("sandbox:check_task_status", args=[self.attempt.pk])).json()
        self.assertFalse(legacy["technical_passed"])
        self.assertNotIn("runtime", data["observation"])

    def test_opted_in_environment_launch_uses_pinned_profile(self):
        from sandbox.services.docker_service import create_task_container
        client = MagicMock()
        client.info.return_value = {"ID": self.policy.daemon_id}
        network = dict(self.api.network, Containers={})
        client.api.inspect_network.return_value = network
        with patch("sandbox.services.docker_service.get_docker_client", return_value=client):
            create_task_container("l1", "service-bind-localhost", self.attempt.pk)
        kwargs = client.containers.run.call_args.kwargs
        self.assertEqual(kwargs["image"], self.policy.target_image)
        self.assertEqual(kwargs["network"], self.policy.network_id)
        self.assertEqual(kwargs["cap_drop"], ["ALL"])
        self.assertEqual(kwargs["labels"]["tc-mvp.environment"], str(self.environment))
        client.images.build.assert_not_called()
