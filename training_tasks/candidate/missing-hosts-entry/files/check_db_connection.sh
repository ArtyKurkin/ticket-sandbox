#!/usr/bin/env bash
# Проверка соединения приложения с сервером базы данных db-internal.

HOST="db-internal"
PORT=3306

if ! getent hosts "$HOST" >/dev/null 2>&1; then
  echo "ERROR: не удаётся найти хост $HOST (не резолвится)" >&2
  exit 1
fi

if ! timeout 3 bash -c "echo > /dev/tcp/$HOST/$PORT" 2>/dev/null; then
  echo "ERROR: хост $HOST найден, но соединение на порт $PORT не устанавливается" >&2
  exit 2
fi

echo "OK: соединение с $HOST:$PORT установлено"
exit 0
