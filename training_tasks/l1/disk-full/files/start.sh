#!/usr/bin/env bash
set -e

# Учебная директория логов приложения
mkdir -p /var/log/app

# "Раздутый" лог-файл, который забил диск.
# 700 МБ нулями — занимает место, легко находится через du.
dd if=/dev/zero of=/var/log/app/debug.log bs=1M count=700 status=none

# Немного шумовых файлов поменьше, чтобы было что анализировать
dd if=/dev/zero of=/var/log/app/access.log.1 bs=1M count=40 status=none
dd if=/dev/zero of=/var/log/app/access.log.2 bs=1M count=25 status=none

# Полезный конфиг, который трогать НЕ нужно (проверяется в check.sh)
mkdir -p /etc/app
cat > /etc/app/app.conf <<'EOF'
# Важный конфиг приложения. Не удалять.
app_name=client-crm
log_dir=/var/log/app
EOF

rm -f /start.sh

tail -f /dev/null
