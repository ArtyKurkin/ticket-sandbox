#!/usr/bin/env bash
set -e

PHP_VER="$(ls /etc/php 2>/dev/null | head -n1)"
PHP_SOCK="/run/php/php${PHP_VER}-fpm.sock"
mkdir -p /run/php

# ПОЛОМКА 1: nginx ограничивает тело запроса 1 мегабайтом
cat > /etc/nginx/sites-available/default <<EOF
server {
    listen 80 default_server;
    root /var/www/html;
    index index.php index.html;
    server_name _;

    client_max_body_size 1m;

    location / {
        try_files \$uri \$uri/ =404;
    }

    location ~ \.php\$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:${PHP_SOCK};
    }
}
EOF
ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default

# ПОЛОМКА 2 и 3: php-лимиты тоже маленькие
PHP_INI="/etc/php/${PHP_VER}/fpm/php.ini"
sed -i 's/^upload_max_filesize = .*/upload_max_filesize = 2M/' "$PHP_INI"
sed -i 's/^post_max_size = .*/post_max_size = 2M/' "$PHP_INI"

service php${PHP_VER}-fpm start
service nginx start

rm -f /start.sh
tail -f /dev/null
