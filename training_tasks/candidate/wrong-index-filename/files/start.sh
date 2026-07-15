#!/usr/bin/env bash
set -e

mkdir -p /var/www/html
cat > /var/www/html/Index.html <<'EOF'
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Сайт клиента</title></head>
<body><h1>Главная страница сайта</h1></body></html>
EOF
chown www-data:www-data /var/www/html/Index.html

service nginx start

rm -f /start.sh
tail -f /dev/null
