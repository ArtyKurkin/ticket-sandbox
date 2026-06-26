#!/usr/bin/env bash
# Учебный сервис: пишет в лог раз в секунду, держа файл открытым.
# Открываем дескриптор один раз (exec) и пишем в него — как реальный демон.

LOGFILE="/var/log/app/huge.log"
exec 3>>"$LOGFILE"
while true; do
  echo "log line at $(date +%H:%M:%S)" >&3
  sleep 1
done
