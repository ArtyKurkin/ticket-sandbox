#!/usr/bin/env bash
# Explicit opt-in lab/CI runner. No existing containers, volumes or images removed.
set -euo pipefail
: "${TB_E2E_HOST_ROOT:?Absolute new private directory on the Docker host required}"
: "${TB_E2E_TARGET_IMAGE:?Existing disposable target image required}"
: "${TB_E2E_DRIVER_IMAGE:?Image with repository Python dependencies required}"
prefix=${TB_E2E_PREFIX:-tc-tb2-20261028-}
case "$prefix" in tc-tb2-*- ) ;; *) echo 'Unsafe test prefix' >&2; exit 1;; esac
test ! -e "$TB_E2E_HOST_ROOT/started"
mkdir -p "$TB_E2E_HOST_ROOT"
chmod 700 "$TB_E2E_HOST_ROOT"
touch "$TB_E2E_HOST_ROOT/started"
docker network create "${prefix}network" > /dev/null
source_root=$(pwd)
secret=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
docker run -d --user 0 --name "${prefix}driver" --label "terminal-broker.e2e=$prefix" \
  --network "${prefix}network" --network-alias web \
  -p 127.0.0.1:29180:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$source_root:/app:ro" -v "$TB_E2E_HOST_ROOT:/lab" \
  -w /app -e "TB_E2E_PREFIX=$prefix" -e "TB_E2E_HOST_ROOT=$TB_E2E_HOST_ROOT" \
  -e "TB_E2E_TARGET_IMAGE=$TB_E2E_TARGET_IMAGE" \
  -e DJANGO_SETTINGS_MODULE=config.settings -e DEBUG=True -e "SECRET_KEY=$secret" \
  -e DB_ENGINE=django.db.backends.sqlite3 -e DB_NAME=/lab/e2e.sqlite3 \
  -e ALLOWED_HOSTS='web,localhost,127.0.0.1' -e TERMINAL_GATEWAY_ENABLED=true \
  -e TERMINAL_BROKER_ENABLED=true -e "TERMINAL_DOCKER_NETWORK=${prefix}network" \
  -e TERMINAL_BROKER_IMAGE=ticket-sandbox-terminal-broker:v2 \
  -e TERMINAL_BROKER_TTYD_IMAGE=ticket-sandbox-ttyd:broker-v2 \
  -e TERMINAL_BROKER_AUTHORIZATION_URL=http://web:8000/terminal-broker-auth/ \
  "$TB_E2E_DRIVER_IMAGE" python -m experiments.terminal_broker.e2e_runtime > /dev/null
for i in $(seq 1 120); do
  if test -f "$TB_E2E_HOST_ROOT/ready"; then break; fi
  if test "$(docker inspect -f '{{.State.Running}}' "${prefix}driver")" != true; then
    docker logs "${prefix}driver"; exit 1
  fi
  sleep 1
done
test -f "$TB_E2E_HOST_ROOT/ready"
cp deploy/nginx/docker/default.conf "$TB_E2E_HOST_ROOT/network.conf"
python3 - "$TB_E2E_HOST_ROOT" <<'PY'
import pathlib,sys
root=pathlib.Path(sys.argv[1])
config=pathlib.Path('deploy/nginx/ticket-sandbox-local.conf').read_text()
config=config.replace('listen 8081;', 'listen 29182;').replace('127.0.0.1:8000', '127.0.0.1:29180')
config=config.replace('logs/nginx-error.log', '/tmp/error.log').replace('logs/nginx.pid','/tmp/nginx.pid').replace('logs/nginx-access.log','/tmp/access.log')
(root/'host.conf').write_text(config)
PY
docker run -d --name "${prefix}network-gateway" --network "${prefix}network" \
  -p 127.0.0.1:29181:80 -v "$TB_E2E_HOST_ROOT/network.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:1.28-alpine > /dev/null
docker run -d --name "${prefix}host-gateway" --network host \
  -v "$TB_E2E_HOST_ROOT/host.conf:/etc/nginx/nginx.conf:ro" nginx:1.28-alpine > /dev/null
echo 'E2E fixture ready on loopback ports 29180/29181/29182; private session.json is in the lab directory.'
