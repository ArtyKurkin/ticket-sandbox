#!/usr/bin/env bash
set -e

mkdir -p /var/www/html
cat > /var/www/html/index.html <<'EOF'
<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Сайт клиента</title></head>
<body><h1>Сайт работает</h1></body></html>
EOF

# ПОЛОМКА: слушаем 8081 вместо стандартного 80
cat > /etc/nginx/sites-available/default <<'EOF'
server {
    listen 8081 default_server;
    root /var/www/html;
    index index.html;
    server_name _;
    location / {
        try_files $uri $uri/ =404;
    }
}
EOF

service nginx start

rm -f /start.sh
tail -f /dev/null
