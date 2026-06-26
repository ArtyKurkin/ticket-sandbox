#!/usr/bin/env bash
set -e

PHP_VER="$(ls /etc/php 2>/dev/null | head -n1)"
PHP_SOCK="/run/php/php${PHP_VER}-fpm.sock"
mkdir -p /run/php

# Поднимаем MySQL и создаём базу + пользователя с ПРАВИЛЬНЫМ паролем
service mysql start
sleep 3
mysql -e "CREATE DATABASE IF NOT EXISTS client_db;"
mysql -e "CREATE USER IF NOT EXISTS 'client_user'@'localhost' IDENTIFIED BY 'CorrectPass123';"
mysql -e "GRANT ALL PRIVILEGES ON client_db.* TO 'client_user'@'localhost';"
mysql -e "FLUSH PRIVILEGES;"

# ПОЛОМКА 1: в wp-config.php НЕВЕРНЫЙ пароль БД (после переноса забыли обновить)
cat > /var/www/html/wp-config.php <<'EOF'
<?php
define('DB_NAME', 'client_db');
define('DB_USER', 'client_user');
define('DB_PASSWORD', 'OldPassword999');
define('DB_HOST', 'localhost');
EOF
chown www-data:www-data /var/www/html/wp-config.php

# ПОЛОМКА 2: PHP-модуль mbstring НЕ установлен (его нет в образе),
# поэтому mb_strlen() недоступна -> fatal error.
# (в Dockerfile намеренно не ставим php-mbstring)

# nginx-конфиг корректный
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

# Настроим php-fpm писать ошибки в видимый лог
PHP_FPM_CONF="/etc/php/${PHP_VER}/fpm/pool.d/www.conf"
sed -i 's@^;catch_workers_output.*@catch_workers_output = yes@' "$PHP_FPM_CONF" || true
echo "php_admin_value[error_log] = /var/log/php-fpm-error.log" >> "$PHP_FPM_CONF"
echo "php_admin_flag[log_errors] = on" >> "$PHP_FPM_CONF"
touch /var/log/php-fpm-error.log
chmod 666 /var/log/php-fpm-error.log

service php${PHP_VER}-fpm start
service nginx start

rm -f /start.sh
tail -f /dev/null
