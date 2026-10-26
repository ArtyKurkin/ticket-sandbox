"""Run selected regressions on an in-memory Django TEST DB, with Docker forbidden.

Requires existing or freshly built static assets outside the repository.
Does not start a server, contact a Docker daemon or change application settings files.
"""

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch


LABELS = (
    "sandbox.tests.test_check_runs", "sandbox.tests.test_check_service",
    "sandbox.tests.test_checks_service", "sandbox.tests.test_technical_lock",
    "sandbox.tests.test_progress", "sandbox.tests.test_completions",
    "sandbox.tests.test_ledger", "sandbox.tests.test_ledger_concurrency",
    "sandbox.tests.test_rerun_attempt", "sandbox.tests.test_docker_service",
    "sandbox.tests.test_task_checkers", "achievements.tests.test_sandbox_advanced",
    "trusted_checker_shadow.tests.django_regression",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--static-root", type=Path, required=True)
    parser.add_argument("--isolation-only", action="store_true", help="Run only the shadow/legacy isolation regression")
    args = parser.parse_args()
    root = args.static_root.resolve(strict=True)
    manifest = json.loads((root / "frontend/manifest.json").read_text())
    if "src/notifications/main.tsx" not in manifest:
        parser.error("Fresh notification assets are required in --static-root/frontend")
    os.environ.update(
        PYTHON_DOTENV_DISABLED="1", DJANGO_SETTINGS_MODULE="config.settings",
        DB_ENGINE="django.db.backends.sqlite3", DB_NAME=":memory:",
        SECRET_KEY="offline-shadow-regression-only", DEBUG="True", SENTRY_DSN="",
        TERMINAL_GATEWAY_ENABLED="true", TASK_CONTAINER_TZ="MSK-3",
    )
    from django.conf import settings
    settings.STATIC_ROOT = root
    settings.STORAGES = {**settings.STORAGES, "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
    from django.core.management import execute_from_command_line
    with patch("docker.api.client.APIClient.__init__", side_effect=AssertionError(
        "Real Docker client prohibited in offline regressions"
    )):
        labels = (LABELS[-1],) if args.isolation_only else LABELS
        execute_from_command_line(["manage.py", "test", *labels, "--noinput", "--verbosity=1"])


if __name__ == "__main__":
    main()
