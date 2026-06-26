#!/usr/bin/env bash
set -e

mkdir -p /var/log

# Запускаем СТАРЫЙ инстанс приложения — он и занимает порт 8080.
# Это полноценный живой процесс (как старая копия, забытая после прошлого запуска).
nohup python3 /opt/app/app_server.py >/var/log/app-old.out 2>/var/log/app-old.err &

sleep 1

rm -f /start.sh
tail -f /dev/null
