#!/usr/bin/env bash
set -e

grep -q "portal.example.test" /etc/hosts || \
    echo "127.0.0.1 portal.example.test legacy.example.test" >> /etc/hosts

nginx -t
service nginx start

rm -f /start.sh

tail -f /dev/null
