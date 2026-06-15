#!/usr/bin/env bash

mkdir -p /var/www/client-crm

cat > /var/www/client-crm/index.html <<'EOF'
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Client CRM</title>
</head>
<body>
  <h1>Client CRM is working</h1>
</body>
</html>
EOF

chown -R www-data:www-data /var/www/client-crm

rm -f /etc/nginx/sites-available/client-crm.conf
rm -f /etc/nginx/sites-enabled/client-crm.conf

service nginx start

rm -f /start.sh

tail -f /dev/null