#!/usr/bin/env bash
set -e

/usr/local/bin/report-api start
sleep 0.2

nginx -t
service nginx start

rm -f /start.sh
tail -f /dev/null
