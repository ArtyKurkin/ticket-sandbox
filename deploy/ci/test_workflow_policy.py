from copy import deepcopy
from pathlib import Path
import unittest

from deploy.ci import workflow_policy as policy


ROOT = Path(__file__).resolve().parents[2]


class WorkflowPolicyTests(unittest.TestCase):
    def setUp(self):
        self.ci = policy.load(ROOT / ".github/workflows/ci.yml")
        self.manual = policy.load(ROOT / ".github/workflows/manual-deploy.yml")

    def check_ci(self):
        policy.automatic_boundary(self.ci)
        policy.check_ci(self.ci)

    def test_current_repository_passes(self):
        policy.check_repository(ROOT)

    def test_all_original_ci_checks_and_local_fixture_migration_remain(self):
        self.check_ci()
        steps = self.ci["jobs"]["tests"]["steps"]
        commands = [s["run"].strip() for s in steps if "run" in s]
        self.assertEqual(set(commands), policy.TEST_RUNS)
        self.assertEqual(len(commands), 9)
        sync = next(s for s in steps if s.get("run", "").strip() == policy.SYNC)
        self.assertEqual(sync["env"]["DB_ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(sync["env"]["DB_NAME"], "ci-sync-check.sqlite3")

    def test_auto_deploy_job_reintroduction_is_rejected(self):
        self.ci["jobs"]["deploy-staging"] = {
            "runs-on": "ubuntu-latest", "if": "github.ref == 'refs/heads/main'",
            "steps": [{"run": "ssh staging python manage.py migrate"}],
        }
        with self.assertRaises(policy.PolicyError):
            self.check_ci()

    def test_server_mutations_in_ci_steps_are_rejected(self):
        original = deepcopy(self.ci)
        for command in (
            "ssh staging python manage.py migrate --noinput",
            "docker compose up -d web worker gateway",
            "docker compose run --rm web python manage.py migrate",
            "python manage.py migrate --noinput",
            "bash deploy/deploy_staging.sh",
        ):
            with self.subTest(command=command):
                self.ci = deepcopy(original)
                self.ci["jobs"]["tests"]["steps"].append({"run": command})
                with self.assertRaises(policy.PolicyError):
                    self.check_ci()

    def test_sqlite_fixture_cannot_be_redirected_to_postgres(self):
        step = next(s for s in self.ci["jobs"]["tests"]["steps"] if s.get("run", "").strip() == policy.SYNC)
        step["env"]["DB_ENGINE"] = "django.db.backends.postgresql"
        with self.assertRaises(policy.PolicyError):
            self.check_ci()

    def test_live_database_host_cannot_be_injected(self):
        self.ci["jobs"]["tests"]["env"]["DB_HOST"] = "example.invalid"
        with self.assertRaises(policy.PolicyError):
            self.check_ci()

    def test_server_secrets_and_remote_actions_are_rejected(self):
        original = deepcopy(self.ci)
        for mutation in ("secret", "action", "environment", "reusable", "self-hosted"):
            with self.subTest(mutation=mutation):
                self.ci = deepcopy(original)
                job = self.ci["jobs"]["tests"]
                if mutation == "secret":
                    job["env"]["SERVER_KEY"] = "${{ secrets.STAGING_SSH_KEY }}"
                elif mutation == "action":
                    job["steps"].append({"uses": "appleboy/ssh-action@v1"})
                elif mutation == "environment":
                    job["environment"] = "production"
                elif mutation == "reusable":
                    job["uses"] = "./.github/workflows/manual-deploy.yml"
                else:
                    job["runs-on"] = ["self-hosted"]
                with self.assertRaises(policy.PolicyError):
                    self.check_ci()

    def test_another_automatic_workflow_cannot_access_a_remote_host(self):
        extra = {"on": {"push": ""}, "jobs": {"new-job": {
            "runs-on": "ubuntu-latest", "steps": [{"run": "scp app.tar example.invalid:/tmp/"}],
        }}}
        with self.assertRaises(policy.PolicyError):
            policy.automatic_boundary(extra)

    def test_policy_job_cannot_be_skipped_by_an_if_condition(self):
        self.ci["jobs"]["workflow-policy"]["if"] = "false"
        with self.assertRaises(policy.PolicyError):
            self.check_ci()

    def test_test_job_cannot_bypass_policy_dependency(self):
        del self.ci["jobs"]["tests"]["needs"]
        with self.assertRaises(policy.PolicyError):
            self.check_ci()

    def test_duplicate_keys_cannot_hide_an_unsafe_job(self):
        import yaml
        with self.assertRaises(policy.PolicyError):
            yaml.load("jobs:\n  tests: {}\n  tests: {environment: production}\n", Loader=policy.UniqueLoader)

    def test_manual_scaffold_remains_dispatch_only_and_hard_blocked(self):
        policy.check_manual(self.manual)
        self.assertEqual(self.manual["jobs"]["deploy-staging"]["steps"][0]["run"].strip(), policy.STOP)

    def test_manual_deploy_cannot_gain_push_or_completion_triggers(self):
        original = deepcopy(self.manual)
        for trigger in ("push", "pull_request", "workflow_run", "schedule"):
            with self.subTest(trigger=trigger):
                self.manual = deepcopy(original)
                self.manual["on"][trigger] = ""
                with self.assertRaises(policy.PolicyError):
                    policy.check_manual(self.manual)

    def test_manual_production_target_and_missing_confirmation_are_rejected(self):
        self.manual["on"]["workflow_dispatch"]["inputs"]["target_environment"]["options"].append("production")
        with self.assertRaises(policy.PolicyError):
            policy.check_manual(self.manual)
        self.setUp()
        self.manual["on"]["workflow_dispatch"]["inputs"]["confirmation"]["required"] = "false"
        with self.assertRaises(policy.PolicyError):
            policy.check_manual(self.manual)

    def test_manual_gates_cannot_be_removed_or_retargeted(self):
        original = deepcopy(self.manual)
        for key, value in (("if", "true"), ("environment", "production"), ("needs", ""), ("runs-on", "self-hosted")):
            with self.subTest(key=key):
                self.manual = deepcopy(original)
                self.manual["jobs"]["deploy-staging"][key] = value
                with self.assertRaises(policy.PolicyError):
                    policy.check_manual(self.manual)

    def test_enabling_variable_alone_cannot_remove_the_hard_stop(self):
        self.manual["jobs"]["deploy-staging"]["steps"][0]["run"] = "docker compose up -d web worker gateway"
        with self.assertRaises(policy.PolicyError):
            policy.check_manual(self.manual)

    def test_validation_must_not_checkout_unreviewed_target_code(self):
        self.manual["jobs"]["validate-request"]["steps"][0]["with"]["ref"] = "${{ inputs.revision }}"
        with self.assertRaises(policy.PolicyError):
            policy.check_manual(self.manual)


if __name__ == "__main__":
    unittest.main()
