#!/usr/bin/env bash
set -e

mkdir -p /var/www/html
cat > /var/www/html/index.html <<'EOF'
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Сайт клиента</title></head>
<body><h1>Сайт работает</h1></body></html>
EOF

# Имитация загрузки через FTP-клиент под root с закрытыми правами
chown root:root /var/www/html/index.html
chmod 600 /var/www/html/index.html

service nginx start

rm -f /start.sh
tail -f /dev/null
