#!/bin/sh

set -eu

ENV_FILE="${1:-.env.prod}"
DOCKER_SOCKET="/var/run/docker.sock"

if [ ! -S "$DOCKER_SOCKET" ]; then
    echo "ERROR: Docker socket not found: $DOCKER_SOCKET" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Environment file not found: $ENV_FILE" >&2
    exit 1
fi

EXPECTED_GID="$(
    sed -n 's/^DOCKER_GID=//p' "$ENV_FILE" \
        | tail -n 1 \
        | tr -d '\r'
)"

ACTUAL_GID="$(stat -c '%g' "$DOCKER_SOCKET")"

case "$EXPECTED_GID" in
    ''|*[!0-9]*)
        echo "ERROR: DOCKER_GID is missing or invalid in $ENV_FILE" >&2
        exit 1
        ;;
esac

if [ "$EXPECTED_GID" != "$ACTUAL_GID" ]; then
    echo "ERROR: Docker socket GID mismatch" >&2
    echo "Expected from $ENV_FILE: $EXPECTED_GID" >&2
    echo "Actual $DOCKER_SOCKET GID: $ACTUAL_GID" >&2
    echo "Run: stat -c '%g' $DOCKER_SOCKET" >&2
    exit 1
fi

echo "Docker socket GID OK: $ACTUAL_GID"