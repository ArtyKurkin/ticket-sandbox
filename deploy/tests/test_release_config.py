"""Read-only release tests: Compose config only, no Docker daemon or application DB."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from deploy import release_config as release


ROOT = Path(__file__).resolve().parents[2]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for filename in release.FILES:
            destination = self.root / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / filename, destination)
        self.runtime = self.root / "private-runtime.env"
        self.runtime.write_text((ROOT / ".env.prod.example").read_text())
        self.pins = {key: "example.invalid/" + key.lower() + "@sha256:" + f"{i:064x}"
                     for i, key in enumerate(sorted(release.KEYS - {"BROKER_AUTHORIZATION_URL"}), 1)}
        self.pins["BROKER_AUTHORIZATION_URL"] = "http://web:8000/terminal-broker-auth/"
        self.images = self.root / "images.env"
        self.write_pins()

    def write_pins(self):
        self.images.write_text("\n".join(f"{key}={value}" for key, value in self.pins.items()))

    def test_release_template_is_incomplete_until_operator_supplies_pins(self):
        with self.assertRaises(release.ReleaseError):
            release.load_pins(ROOT / "deploy/releases/images.env.example")

    def test_mutable_unknown_duplicate_and_missing_pins_are_rejected(self):
        original = self.images.read_text()
        for invalid in (original.replace(self.pins["WEB_IMAGE"], "example.invalid/app:latest"),
                        original + "\nWEB_IMAGE=" + self.pins["WEB_IMAGE"],
                        original + "\nUNREVIEWED=1", "WEB_IMAGE=sha256:" + "a" * 64):
            with self.subTest(invalid=invalid):
                self.images.write_text(invalid)
                with self.assertRaises(release.ReleaseError):
                    release.load_pins(self.images)

    def test_shell_cannot_override_reviewed_pins_db_or_compose_files(self):
        with patch.dict(os.environ, {"WEB_IMAGE": "bad:latest", "DB_PASSWORD": "wrong",
                                     "COMPOSE_FILE": "unreviewed.yml", "COMPOSE_PROFILES": "other"}):
            environment = release.compose_environment(self.root, self.runtime, self.pins)
        self.assertEqual(environment["WEB_IMAGE"], self.pins["WEB_IMAGE"])
        self.assertNotIn("DB_PASSWORD", environment)
        self.assertNotIn("COMPOSE_FILE", environment)
        self.assertNotIn("COMPOSE_PROFILES", environment)

    def test_plans_target_one_role_without_recreating_dependencies(self):
        command = release.compose_command(self.root, self.runtime, self.images)
        for service in release.UPDATABLE:
            with self.subTest(service=service):
                planned = release.planned_commands(command, service)
                self.assertEqual(planned[-1][-1], service)
                for flag in ("--no-deps", "--no-build", "never"):
                    self.assertIn(flag, planned[-1])
                self.assertEqual(len(planned), 2 if service == "terminal_scheduler" else 1)
        for service in ("db", "redis", "all", "web worker"):
            with self.subTest(service=service), self.assertRaises(release.ReleaseError):
                release.planned_commands(command, service)

    def test_cli_only_executes_config_and_does_not_disclose_compose_errors(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(release.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, stdout="PRIVATE_CONFIG_SENTINEL", stderr="PRIVATE_ENV_SENTINEL")) as run:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = release.main(["--root", str(self.root), "--runtime-env", str(self.runtime),
                                       "--release-env", str(self.images), "plan", "web"])
        self.assertEqual(result, 1)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-3:], ["config", "--format", "json"])
        self.assertNotIn("PRIVATE_", stdout.getvalue() + stderr.getvalue())

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required; daemon not used")
    def test_successful_plan_executes_only_config_and_preserves_reviewed_inputs(self):
        stdout = io.StringIO()
        with patch.object(release.subprocess, "run", wraps=subprocess.run) as run:
            with redirect_stdout(stdout):
                result = release.main(["--root", str(self.root), "--runtime-env", str(self.runtime),
                                       "--release-env", str(self.images), "plan", "worker"])
        self.assertEqual(result, 0)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-3:], ["config", "--format", "json"])
        planned = shlex.split(stdout.getvalue().splitlines()[-1])
        self.assertIn("-u", planned)
        self.assertIn("DB_PASSWORD", planned)
        self.assertIn("TP_RUNTIME_ENV_FILE=" + str(self.runtime.resolve()), planned)
        self.assertIn("WORKER_IMAGE=" + self.pins["WORKER_IMAGE"], planned)
        self.assertEqual(planned[-1], "worker")
        self.assertNotIn("change-me-to-a-strong-database-password", stdout.getvalue())

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required; daemon not used")
    def test_real_compose_merge_keeps_runtime_topology_and_distinct_role_images(self):
        # No .env.prod in the fixture: !override must replace that inherited path.
        command = release.validate(self.root, self.runtime, self.images, self.pins)
        result = subprocess.run(command + ["config", "--format", "json"],
                                env=release.compose_environment(self.root, self.runtime, self.pins),
                                text=True, capture_output=True, check=True, timeout=30)
        model = json.loads(result.stdout)
        self.assertEqual(model["name"], "training-platform")
        services = model["services"]
        self.assertNotEqual(services["web"]["image"], services["worker"]["image"])
        self.assertNotEqual(services["worker"]["image"], services["terminal_scheduler"]["image"])
        for role in ("web", "worker", "terminal_scheduler"):
            self.assertNotIn("build", services[role])
            self.assertEqual(services[role]["environment"]["TERMINAL_BROKER_ENABLED"], "true")
        self.assertEqual(services["terminal_scheduler"]["profiles"], ["terminal-broker"])
        self.assertEqual(services["worker"]["group_add"], ["999"])
        self.assertFalse(any(v["target"] == "/var/run/docker.sock" for v in services["web"].get("volumes", [])))
        self.assertTrue(any(v["target"] == "/var/run/docker.sock" for v in services["worker"]["volumes"]))
        for role in ("db", "redis", "web"):
            self.assertFalse(services[role].get("ports"))
        self.assertEqual(services["gateway"]["ports"][0]["host_ip"], "127.0.0.1")
        self.assertEqual(str(services["gateway"]["ports"][0]["published"]), "8080")
        self.assertIn("X-Forwarded-Proto", services["gateway"]["healthcheck"]["test"][-1])
        self.assertEqual(model["networks"]["platform"]["name"], "training-platform-runtime")
        self.assertEqual(model["volumes"]["postgres_data"]["name"], "training-platform_postgres_data")
        self.assertEqual(model["volumes"]["redis_data"]["name"], "training-platform_redis_data")
