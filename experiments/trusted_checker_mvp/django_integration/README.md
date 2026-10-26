# Django HTTP observation integration

Default OFF. No deployment or real Docker run was performed for this integration.
Only `l1/service-bind-localhost` and one configured disposable attempt are selected.
HTTP match never grants technical or academic success. Existing Docker pilot
[adapter](../docker_pilot/adapter.py), [worker](../docker_pilot/worker.py) and
[probe](../verifier.py) are reused without edits.

## Lab configuration (operator action, not performed)

1. Review/apply migration `sandbox.0034_http_observation` on the separate lab DB.
   It adds one diagnostic table and an initially empty runtime JSON field;
   it does not backfill observation, technical or academic results.
2. Use a fresh, current, not-passed test attempt. Quiesce all legacy check jobs
   before enabling. Do not use an attempt with a running legacy check. Do not
   alter existing user results to make an attempt eligible.
3. Prepare approved target/verifier images locally and pin their actual image IDs
   (`sha256:<64 hex>`), not the `:lab` tag. Approve the verifier source/build.
   Prepare an empty dedicated network using the existing Docker pilot
   [network template](../docker_pilot/network-profile.json). It must be the
   approved internal isolated bridge for this attempt, never the platform network.
4. Copy [policy.example.json](policy.example.json) to a host-owned file, replace
   every placeholder and keep it unavailable to trainees. Prepare the artifact
   directory owned by the worker UID, mode 0700, with trusted ancestors. For the
   repository image the UID is 10001. All workers must share this directory.
5. Set the same three settings on web and worker:

   ```text
   SANDBOX_HTTP_OBSERVATION_ENABLED=true
   SANDBOX_HTTP_OBSERVATION_ATTEMPT_ID=<one test attempt ID>
   SANDBOX_HTTP_OBSERVATION_CONFIG=/etc/tc-http-observation/policy.json
   ```

   [enablement.compose.example.yml](enablement.compose.example.yml) is an explicit
   optional lab override of the existing Compose services. It does not create a
   network or add Docker access to web. Worker already has daemon access in the
   base configuration. Mere entries in `.env` do not pass these settings through
   the existing Compose `environment` blocks; use an explicit override.
6. Start/reset that test environment through the normal authorized Sandbox
   action. Only this opt-in branch uses the pinned target image, dedicated network,
   cap-drop ALL and no tmpfs. Before READY, host readback pins full ID, start time,
   PID, restart count, endpoint/IP and environment operation UUID. Old environments
   without that mapping are refused; there is no adoption/backfill button.
7. Use **Проверить HTTP без зачёта**, or authenticated CSRF-protected
   `POST /attempts/<id>/http-observation/` with an empty form body. No query
   parameters, IP, URL, command, image or uploaded result are accepted.
   `GET /attempts/<id>/http-observation-status/` returns the limited public summary
   to the owner or staff. Refresh the task page to view the timestamped observation.
8. Verify CheckRun, technical timestamp, Ledger completion, achievements and
   progress remain unchanged. Complete the real Docker adapter/network and
   PostgreSQL concurrency review described in the main report before pilot use.

Turning the flag off restores the legacy path, which remains vulnerable to
`check.sh` spoofing. Do not present disabling the pilot as a security fix. Drain
active observation jobs and inspect owned worker/artifact state when changing
configuration. A hard-killed/lost Celery job conservatively remains queued/running;
there is no automatic redispatch or artifact deletion. Operator diagnosis is needed.

## Reproduce offline checks

From repository root, with the existing virtual environment:

```sh
DJANGO_SETTINGS_MODULE=sandbox.tests.observation_settings PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m django test sandbox.tests.test_http_observations --noinput
DJANGO_SETTINGS_MODULE=sandbox.tests.observation_settings PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python -W error::ResourceWarning -m django test sandbox.tests --noinput
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning \
  -m unittest experiments.trusted_checker_mvp.docker_pilot.test_pilot
```

The dedicated test settings use in-memory SQLite, skip dotenv loading and disable
Sentry; no real user DB, broker or daemon is used. Docker calls are fake SDK calls,
including the explicit environment provisioning test. See [integration-tests.txt](integration-tests.txt),
[sandbox-tests.txt](sandbox-tests.txt) and [adapter-tests.txt](adapter-tests.txt).

The user-reported VDS Docker HTTP smoke predates this integration and used
synthetic identity. It is not evidence for the new ORM mapping, execution fencing,
network isolation or full adapter acceptance. No H1/H2 or physical gates are used.
