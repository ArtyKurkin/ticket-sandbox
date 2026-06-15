#!/usr/bin/env bash

echo "Проверка задания"

if ! service nginx status >/dev/null 2>&1; then
  echo "❌ nginx не запущен."

  exit 1
fi

if ! nginx -t >/dev/null 2>&1; then
  echo "❌ Конфигурация nginx содержит ошибки."

  exit 1
fi

if ! curl -fsS http://127.0.0.1/ | grep -q "Client CRM is working"; then
  echo "❌ nginx все еще отдает неправильный сайт."

  exit 1
fi

echo "✅ nginx запущен."
echo "✅ Конфигурация nginx корректна."
echo "✅ Открывается сайт клиента."
echo "Задание пройдено."