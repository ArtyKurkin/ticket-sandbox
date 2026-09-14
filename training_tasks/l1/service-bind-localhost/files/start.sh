#!/usr/bin/env bash
set -e

/usr/local/bin/customer-app start

rm -f /start.sh

tail -f /dev/null
