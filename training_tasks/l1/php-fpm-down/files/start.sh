#!/usr/bin/env bash
set -e

# Определяем установленную версию PHP (например "8.1")
PHP_VER="$(ls /etc/php 2>/dev/null | head -n1)"

if [ -z "$PHP_VER" ]; then
  echo "PHP не установлен — ошибка сборки образа" >&2
  exit 1
fi

# Сокет, который создаёт php-fpm этой версии по умолчанию
PHP_SOCK="/run/php/php${PHP_VER}-fpm.sock"

mkdir -p /run/php

# Генерируем рабочий конфиг nginx, который проксирует PHP на этот сокет.
# Конфиг КОРРЕКТНЫЙ — поломка не в нём, а в том, что php-fpm не запущен.
cat > /etc/nginx/sites-available/default <<EOF
server {
    listen 80 default_server;

    root /var/www/html;
    index index.php index.html;

    server_name _;

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

service nginx start

# ПОЛОМКА: php-fpm намеренно НЕ запускаем.
# nginx проксирует на сокет, которого нет -> 502 Bad Gateway на .php страницах.
# Стажёр должен обнаружить, что служба php-fpm не работает, и запустить её.

rm -f /start.sh

tail -f /dev/null
