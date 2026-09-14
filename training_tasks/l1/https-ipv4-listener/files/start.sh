#!/usr/bin/env bash
set -e

nginx -t
service nginx start

rm -f /start.sh
tail -f /dev/null
