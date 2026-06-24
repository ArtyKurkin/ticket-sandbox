#!/usr/bin/env bash
set -e

mkdir -p /var/www/html

# ПОЛОМКА (одна): в crontab указан НЕВЕРНЫЙ путь к скрипту.
# Файл называется update_data.sh, а в задании прописан update.sh.
# Стажёр должен найти опечатку (через логи cron / сравнение пути) и исправить.
cat > /etc/cron.d/app-update <<'EOF'
* * * * * root /opt/app/update.sh
EOF

chmod 0644 /etc/cron.d/app-update

service cron start

rm -f /start.sh

tail -f /dev/null
