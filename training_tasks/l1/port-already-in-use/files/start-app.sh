#!/usr/bin/env bash
# Запуск приложения на порту 8080.

# Проверяем, свободен ли порт 8080
if ss -tln | grep -q ':8080'; then
  echo "ERROR: address already in use — порт 8080 уже занят. Освободите его перед запуском." >&2
  exit 98
fi

nohup python3 /opt/app/app_server.py >/var/log/app.out 2>/var/log/app.err &
sleep 1

if ss -tln | grep -q ':8080'; then
  echo "OK: приложение запущено на порту 8080"
  exit 0
else
  echo "ERROR: приложение не смогло занять порт 8080" >&2
  cat /var/log/app.err >&2
  exit 1
fi
