"""Runner-only offline tests. APIClient factory always replaced; no Docker I/O."""
from contextlib import redirect_stdout
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from docker.errors import NotFound

from . import real_lab as lab
from .test_pilot import FakeAPI, fixture


class RealLabRunnerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.artifacts = self.directory / "artifacts"
        self.artifacts.mkdir(mode=0o700)
        self.policy, execution = fixture()
        self.execution = replace(execution, attempt_id=1, user_id=1)
        self.api = FakeAPI(self.policy, self.execution)
        self.api.target["Config"]["Labels"]["ticket-sandbox.attempt"] = "1"
        self.foreign = [{"Id": "9" * 64, "State": "running", "Labels": {"old-lab": "untouched"}}]
        self.api.containers = lambda all: [
            {"Id": value["Id"], "State": value["State"]["Status"], "Labels": value["Config"]["Labels"]}
            for value in [self.api.target, *self.api.workers.values()]] + self.foreign
        self.api.version = lambda: {"Version": "29.1.3", "ApiVersion": "1.52"}
        self.api.close = MagicMock()
        self.config = dict(api_socket="/approved/fake.sock", artifact_dir=str(self.artifacts),
                           environment_uuid=execution.environment_uuid, target_id=execution.container_id,
                           policy=asdict(self.policy))
        self.config_path = self.directory / "config.json"
        self.config_path.write_text(json.dumps(self.config))
        self.config_path.chmod(0o600)
        self.record = self.directory / "execution.json"
        for name, kwargs in (("experiments.trusted_checker_mvp.docker_pilot.real_lab.docker.APIClient", {"return_value": self.api}),
                             ("experiments.trusted_checker_mvp.docker_pilot.adapter.select.select", {"side_effect": lambda readers, *args: (readers, [], [])})):
            patcher = patch(name, **kwargs)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if name.endswith("APIClient"):
                self.factory = mock

    def invoke(self, command, *, permit=False):
        args = [command, "--config", str(self.config_path), "--record", str(self.record)]
        if permit:
            args += ["--allow-verifier-effects", self.policy.scope]
        output = io.StringIO()
        with redirect_stdout(output):
            code = lab.main(args)
        return code, json.loads(output.getvalue())

    def test_pin_is_read_only_and_preserves_full_runtime(self):
        code, result = self.invoke("pin")
        self.assertEqual(code, 0)
        pinned = lab.read_record(self.record, self.config, self.policy)
        self.assertEqual(pinned.container_id, self.execution.container_id)
        self.assertEqual((pinned.pid, pinned.started_at), (self.execution.pid, self.execution.started_at))
        self.assertEqual(result["engine"]["Version"], "29.1.3")
        self.assertFalse(result["academic_pass"])
        self.assertFalse(any(call[0] in ("create", "start", "remove") for call in self.api.calls))
        original = self.record.read_bytes()
        self.assertEqual(self.invoke("pin")[0], 2)
        self.assertEqual(self.record.read_bytes(), original)

    def test_observe_requires_explicit_permission_before_client_creation(self):
        code, result = self.invoke("observe")
        self.assertEqual((code, result["reason"]), (2, "operator_permission_required"))
        self.factory.assert_not_called()

    def test_actual_adapter_positive_replay_and_no_foreign_cleanup(self):
        self.invoke("pin")
        code, result = self.invoke("observe", permit=True)
        self.assertEqual((code, result["http"], result["reason"]), (0, "matched", "http_match"))
        self.assertEqual(result["binding"]["container_id"], self.execution.container_id)
        self.assertEqual(result["task_verdict"], "unknown")
        self.assertFalse(result["academic_pass"])
        self.assertFalse(result["real_pilot_passed"])
        self.assertTrue(result["inventory"]["foreign_inventory_unchanged"])
        self.assertFalse(result["inventory"]["remaining_scope_verifier_ids"])
        creates = sum(call[0] == "create" for call in self.api.calls)
        self.assertEqual(self.invoke("observe", permit=True)[1]["reason"], "replay")
        self.assertEqual(sum(call[0] == "create" for call in self.api.calls), creates)
        self.assertTrue(all(call[1] == "d" * 64 for call in self.api.calls if call[0] == "remove"))

    def test_restart_does_not_repin_before_observe(self):
        self.invoke("pin")
        self.api.target["State"]["Pid"] += 1
        self.api.target["RestartCount"] += 1
        code, result = self.invoke("observe", permit=True)
        self.assertEqual((code, result["http"], result["reason"]), (2, "unknown", "runtime_changed"))
        self.assertFalse(any(call[0] == "create" for call in self.api.calls))

    def test_old_network_and_unsafe_target_are_refused_before_effects(self):
        self.api.network["Name"] = "tc-mvp-lab"
        self.assertEqual(self.invoke("pin")[1]["reason"], "network_unapproved")
        self.assertFalse(self.record.exists())
        self.api.network["Name"] = "tc-mvp-" + self.policy.scope
        self.api.target["Mounts"] = [{"Source": "/var/run/docker.sock"}]
        self.assertEqual(self.invoke("pin")[1]["reason"], "unsafe_target")
        self.assertFalse(any(call[0] in ("create", "remove") for call in self.api.calls))

    def test_missing_verifier_is_unknown_without_removing_any_image(self):
        self.api.inspect_image = MagicMock(side_effect=NotFound("synthetic absent image"))
        self.assertFalse(self.invoke("pin")[1]["verifier_image_available"])
        code, result = self.invoke("observe", permit=True)
        self.assertEqual((code, result["http"]), (2, "unknown"))
        self.assertIsNone(result["binding"])
        self.assertFalse(self.api.workers)

    def test_changed_record_and_public_storage_are_refused(self):
        self.invoke("pin")
        value = json.loads(self.record.read_text())
        value["execution"]["container_id"] = "8" * 64
        self.record.write_text(json.dumps(value))
        self.assertEqual(self.invoke("observe", permit=True)[1]["reason"], "record_schema")
        self.config_path.chmod(0o644)
        self.assertEqual(self.invoke("audit")[1]["reason"], "private_storage_required")
        self.assertFalse(any(call[0] == "create" for call in self.api.calls))

    def test_unresolved_verifier_is_reported_and_not_pruned(self):
        self.invoke("pin")
        self.api.remove_fails = True
        code, result = self.invoke("observe", permit=True)
        self.assertEqual((code, result["reason"]), (2, "cleanup_unknown"))
        self.assertEqual(result["inventory"]["remaining_scope_verifier_ids"], ["d" * 64])
        creates = sum(call[0] == "create" for call in self.api.calls)
        self.assertEqual(self.invoke("observe", permit=True)[1]["reason"], "scope_not_quiescent")
        self.assertEqual(sum(call[0] == "create" for call in self.api.calls), creates)

    def test_foreign_state_change_invalidates_inventory_audit(self):
        self.invoke("pin")
        self.api.hooks["start"] = lambda api: self.foreign[0].update(State="exited")
        code, result = self.invoke("observe", permit=True)
        self.assertEqual(result["http"], "matched")
        self.assertEqual(code, 2)
        self.assertFalse(result["inventory"]["foreign_inventory_unchanged"])


if __name__ == "__main__":
    unittest.main()
