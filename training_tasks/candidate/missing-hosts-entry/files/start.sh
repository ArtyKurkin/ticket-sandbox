#!/usr/bin/env bash
set -e

nohup python3 /opt/app/db_stub.py >/var/log/db_stub.log 2>&1 &
sleep 1

# ПОЛОМКА: в /etc/hosts нет записи для db-internal.
# (ничего не добавляем — это и есть единственная причина)

rm -f /start.sh
tail -f /dev/null
