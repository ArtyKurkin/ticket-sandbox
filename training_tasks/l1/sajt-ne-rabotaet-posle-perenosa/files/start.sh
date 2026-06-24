#!/usr/bin/env bash
set -e

# Сайт клиента "уже перенесён" в /var/www/client-crm
mkdir -p /var/www/client-crm

cat > /var/www/client-crm/index.html <<'EOF'
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Client CRM</title>
</head>
<body>
  <h1>Client CRM работает</h1>
  <p>Это перенесённый сайт клиента.</p>
</body>
</html>
EOF

chown -R www-data:www-data /var/www/client-crm

# Конфига для client-crm нет: nginx отдаёт дефолтный сайт.
# Стажёр должен создать конфиг и активировать его.
rm -f /etc/nginx/sites-available/client-crm.conf
rm -f /etc/nginx/sites-enabled/client-crm.conf

service nginx start

# start.sh больше не нужен
rm -f /start.sh

tail -f /dev/null