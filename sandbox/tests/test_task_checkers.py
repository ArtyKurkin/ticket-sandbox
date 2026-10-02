"""Execute real checker scripts with deterministic OS/HTTP boundary doubles."""
import os
from pathlib import Path
import subprocess
import tempfile

from django.conf import settings
from django.test import SimpleTestCase


class TaskCheckerTests(SimpleTestCase):
    def run_checker(self, slug, scripts, env=None):
        with tempfile.TemporaryDirectory() as directory:
            for name, content in scripts.items():
                path = Path(directory) / name
                path.write_text('#!/usr/bin/env bash\n' + content)
                path.chmod(0o755)
            return subprocess.run(
                ['bash', str(Path(settings.BASE_DIR) / 'training_tasks/l1' / slug / 'files/check.sh')],
                env={**os.environ, 'PATH': directory + os.pathsep + os.environ['PATH'], **(env or {})},
                text=True, capture_output=True, timeout=10,
            )

    def test_bind_checker_uses_live_http_not_launcher_state(self):
        for local, network, ip, passed in (
            ('app', 'app', '172.17.0.16', True),  # manual launch without PID file
            ('app', 'fail', '172.17.0.16', False),  # initial loopback bind
            ('fail', 'fail', '172.17.0.16', False),  # stopped / wrong port
            ('fail', 'app', '172.17.0.16', False),  # local access must remain
            ('other', 'app', '172.17.0.16', False),
            ('app', 'other', '172.17.0.16', False),
            ('app', 'app', '', False),
        ):
            with self.subTest(local=local, network=network, ip=ip):
                result = self.run_checker('service-bind-localhost', {
                    'ip': 'if [ -n "$TEST_IP" ]; then echo "2: eth0 inet $TEST_IP/16 scope global eth0"; fi\n',
                    'curl': '''
# Ensure proxy environment cannot produce a false positive.
[[ "$*" == *"--noproxy *"* ]] || exit 2
case "${!#}" in
  http://127.0.0.1:8080/) result="$TEST_LOCAL" ;;
  http://172.17.0.16:8080/) result="$TEST_NETWORK" ;;
  *) exit 2 ;;
esac
case "$result" in
  app) echo 'APP OK: customer service is running' ;;
  other) echo 'Another application' ;;
  *) exit 7 ;;
esac
''',
                }, {'TEST_LOCAL': local, 'TEST_NETWORK': network, 'TEST_IP': ip})
                self.assertEqual(result.returncode, 0 if passed else 1, result.stdout + result.stderr)
                self.assertNotIn('Приложение не запущено.', result.stdout)

    def test_wordpress_local_script_cannot_grant_a_pass(self):
        result = self.run_checker('wordpress-500-after-move', {})
        self.assertEqual(result.returncode, 1)
        self.assertIn('Ticket Sandbox', result.stdout)
        self.assertNotIn('Задание пройдено', result.stdout)
