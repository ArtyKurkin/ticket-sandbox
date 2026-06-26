#!/usr/bin/env bash
set -e

mkdir -p /var/log/app

# Создаём "большой" лог и раздуваем его
dd if=/dev/zero of=/var/log/app/huge.log bs=1M count=300 status=none

# Запускаем сервис, который ДЕРЖИТ дескриптор этого файла открытым
nohup /opt/logger/logger.sh >/dev/null 2>&1 &
sleep 2

# === ИМИТАЦИЯ ДЕЙСТВИЯ КЛИЕНТА ===
# Клиент удалил файл через rm, НО сервис продолжает держать дескриптор.
# Место не освобождается, файла в ls нет, а дескриптор (deleted) висит.
rm -f /var/log/app/huge.log

rm -f /start.sh
tail -f /dev/null
