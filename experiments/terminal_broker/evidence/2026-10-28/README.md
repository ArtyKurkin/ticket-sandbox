# Terminal Broker v2 laboratory evidence — 2026-10-28

Final strict browser run: **both modes passed**. Chrome ran headless on the Mac;
HTTP/WebSocket traffic went over SSH tunnels to the isolated Linux VDS fixture.

- `results.json`: browser results, real `stty size` changes and independent PIDs.
- `host_port-top.png`, `docker_network-top.png`: actual fullscreen terminal images
  after browser viewport changes.
- `isolation.json`: probes inside ttyd, rejected target/command/Exec selection,
  credential rejection and denial of direct network access without gateway auth.
- `cleanup.json`: real Django stop/reconcile/removal of the newly created brokers
  and terminals. Remaining fixture gateway/driver containers and its private network
  were subsequently removed. Volumes, images and DBs were retained.

The final browser script checks for any `ERROR:terminal.broker` in runtime logs,
preserves a separate process without a session token and PID 1, and verifies that
closing the second tab leaves the first tab operational. Recovery uses an orphan
that ignores HUP/TERM and disables automatic restart until the explicit test start.

The fixture used `tc-e2e-django:lab`, newly built
`ticket-sandbox-terminal-broker:v2` and `ticket-sandbox-ttyd:broker-v2`, nginx
`1.28-alpine` and disposable clones of the existing task image `d1c3e8c95745`.
The original target was not modified. Source and private fixture artifacts remain
under `/root/tc-e2e-pilot/terminal-broker-2-20261028-run1` on the lab VDS.
No private `session.json`, DB, SSH material or environment file is included here.

This evidence does not establish safety against hostile root descendants, all
task-image compatibility, a full PostgreSQL/Celery restart, host reboot, Docker
daemon restart or production deployment. See `TERMINAL_BROKER_V2.md` for limits.
