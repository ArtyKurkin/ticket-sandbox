# Task image regression scenarios

These scenarios use **disposable task containers**, never
existing trainee environments. They change processes, packages and task database
credentials inside their own container. They need no platform database, tokens,
Docker socket mount or published ports. WordPress needs package repository access.

From the repository root:

```sh
docker build -t training-platform-fix-review-bind training_tasks/l1/service-bind-localhost
docker run --rm \
  --mount "type=bind,src=$PWD/sandbox/tests/task_scenarios/service-bind-localhost.sh,dst=/tmp/scenario.sh,readonly" \
  training-platform-fix-review-bind bash /tmp/scenario.sh

docker build -t training-platform-fix-review-wordpress training_tasks/l1/wordpress-500-after-move
.venv/bin/python sandbox/tests/task_scenarios/wordpress-500-after-move.py
```

The bind scenario rejects the original loopback state, a stopped process and a
wrong port, and accepts a manual wildcard launch without a launcher PID file.
The WordPress runner uses the platform Docker SDK checker (Django and Docker SDK
are required locally). It checks each partial repair, static HTML substitution
before and after repair, a read-only alternative DB user, CLI/FPM extension
mismatch, and restoration of DB content after every check. The trusted checker
is in `sandbox/task_checks/wordpress_runtime.php`, outside the task image.
`/task/check.sh` directs trainees to the platform button and cannot grant a pass.

Fast checker boundary tests run as part of `manage.py test sandbox` (no Docker).
Form event tests use `node --test sandbox/tests/js/answer_validation.test.cjs`.
