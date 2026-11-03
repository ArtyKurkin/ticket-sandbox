from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deploy.ci import manual_deploy_request as request


ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


class ManualRequestTests(unittest.TestCase):
    def arguments(self, **changes):
        return dict(event="workflow_dispatch", workflow_ref="refs/heads/main", target="staging", revision=SHA,
                    confirmation=f"DEPLOY STAGING {SHA}", root=ROOT) | changes

    def test_valid_request_runs_only_local_git_read_commands(self):
        with patch.object(request.subprocess, "run", side_effect=[
            SimpleNamespace(returncode=0, stdout=SHA + "\n"), SimpleNamespace(returncode=0),
        ]) as run:
            result = request.validate_request(**self.arguments())
        self.assertEqual(result["status"], "validated_deployment_disabled")
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["git", "rev-parse", "--verify", SHA + "^{commit}"],
            ["git", "merge-base", "--is-ancestor", SHA, "origin/main"],
        ])

    def test_main_revision_is_validated_against_real_local_git_objects(self):
        sha = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
        result = request.validate_request(**self.arguments(revision=sha, confirmation=f"DEPLOY STAGING {sha}"))
        self.assertEqual(result["revision"], sha)

    def test_push_branch_dispatch_and_production_are_rejected_before_git(self):
        for changes in ({"event": "push"}, {"workflow_ref": "refs/heads/feature/example"}, {"target": "production"}):
            with self.subTest(changes=changes), patch.object(request.subprocess, "run") as run:
                with self.assertRaises(request.RequestError):
                    request.validate_request(**self.arguments(**changes))
                run.assert_not_called()

    def test_mutable_refs_short_shas_and_shell_injection_are_rejected(self):
        for value in ("main", "v1.0", "abcdef0", "A" * 40, SHA + "; echo unsafe", "$(echo unsafe)", SHA + "\n"):
            with self.subTest(value=value), patch.object(request.subprocess, "run") as run:
                with self.assertRaises(request.RequestError):
                    request.validate_request(**self.arguments(revision=value))
                run.assert_not_called()

    def test_confirmation_is_bound_to_the_exact_revision(self):
        with patch.object(request.subprocess, "run") as run:
            with self.assertRaises(request.RequestError):
                request.validate_request(**self.arguments(confirmation="DEPLOY STAGING " + "b" * 40))
            run.assert_not_called()

    def test_unavailable_and_non_main_commits_are_rejected(self):
        for responses in ([SimpleNamespace(returncode=1, stdout="")],
                          [SimpleNamespace(returncode=0, stdout=SHA), SimpleNamespace(returncode=1)]):
            with self.subTest(responses=responses), patch.object(request.subprocess, "run", side_effect=responses):
                with self.assertRaises(request.RequestError):
                    request.validate_request(**self.arguments())

    def test_cli_outputs_validated_sha_and_explicit_disabled_status(self):
        with tempfile.TemporaryDirectory(prefix="manual-deploy-request-") as directory:
            output, summary = Path(directory) / "output", Path(directory) / "summary"
            env = {"ACTION_EVENT_NAME": "workflow_dispatch", "ACTION_WORKFLOW_REF": "refs/heads/main",
                   "REQUESTED_ENVIRONMENT": "staging", "REQUESTED_REVISION": SHA,
                   "REQUEST_CONFIRMATION": f"DEPLOY STAGING {SHA}", "GITHUB_OUTPUT": str(output),
                   "GITHUB_STEP_SUMMARY": str(summary)}
            result = {"status": "validated_deployment_disabled", "target": "staging", "revision": SHA}
            with patch.dict(os.environ, env, clear=True), patch.object(request, "validate_request", return_value=result), patch("sys.stdout", new_callable=StringIO) as stdout:
                self.assertEqual(request.main(), 0)
            self.assertEqual(output.read_text(), f"revision={SHA}\n")
            self.assertIn("Deployment remains disabled", summary.read_text())
            self.assertEqual(json.loads(stdout.getvalue()), result)


if __name__ == "__main__":
    unittest.main()
