#!/usr/bin/env bash
# Приложение клиента. Запускается под appuser.
# Читает конфиг, читает файл данных, пишет результат.

CONFIG="/opt/myapp/config.ini"
DATA="/opt/myapp/data/records.txt"
OUT="/opt/myapp/output/result.txt"

if [ ! -r "$CONFIG" ]; then
    echo "ERROR: не могу прочитать конфиг $CONFIG" >&2
    exit 11
fi

if [ ! -r "$DATA" ]; then
    echo "ERROR: не могу прочитать данные $DATA (нет доступа к файлу или директории)" >&2
    exit 12
fi

if [ ! -w "/opt/myapp/output" ]; then
    echo "ERROR: не могу писать в /opt/myapp/output" >&2
    exit 13
fi

lines=$(wc -l < "$DATA")
echo "processed $lines records at $(date +%H:%M:%S)" > "$OUT"
echo "OK: приложение отработало, обработано $lines записей"
exit 0
