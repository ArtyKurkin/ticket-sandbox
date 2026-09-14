#!/usr/bin/env bash
set -e

mkdir -p /var/log/customer-api

# Backend исправен и работает отдельно от nginx.
nohup python3 /opt/customer-api/backend.py \
    >/var/log/customer-api/backend.log \
    2>&1 &

# Даём backend немного времени открыть сокет.
sleep 0.3

# Конфигурация nginx синтаксически валидна, поэтому nginx успешно стартует.
# Ошибка проявляется только при обращении к upstream.
service nginx start

rm -f /start.sh

tail -f /dev/null
