#!/usr/bin/env bash
# Run inside the freshly built service-bind-localhost task image.
set -euo pipefail

expect_failed_check() {
    if /task/check.sh; then
        echo 'ERROR: checker accepted an invalid state' >&2
        exit 1
    fi
}

/usr/local/bin/customer-app start
expect_failed_check  # original loopback-only bind
/usr/local/bin/customer-app stop

# No launcher/PID file; argument order and buffering flag differ from startup.
python3 -u /opt/customer-app/app_server.py --port 8080 --bind 0.0.0.0 &
app_pid=$!
for _ in {1..50}; do
    if curl --noproxy '*' -fsS http://127.0.0.1:8080/ >/dev/null 2>&1; then break; fi
    sleep 0.1
done
/task/check.sh
if /usr/local/bin/customer-app status; then
    echo 'ERROR: manual launch unexpectedly has a launcher PID file' >&2
    exit 1
fi
kill "$app_pid"
wait "$app_pid" || true
expect_failed_check  # stopped

python3 /opt/customer-app/app_server.py --bind 0.0.0.0 --port 8081 &
app_pid=$!
expect_failed_check  # wrong port
kill "$app_pid"
wait "$app_pid" || true
echo 'PASS: loopback, manual wildcard launch, stopped application, wrong port'
