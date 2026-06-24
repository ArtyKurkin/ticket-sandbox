#!/usr/bin/env bash

echo "Проверка задания: после переноса открывается не тот сайт"
echo

ok=true

if ! nginx -t >/dev/null 2>&1; then
  echo "❌ Конфигурация nginx содержит ошибки (nginx -t не проходит)."
  ok=false
else
  echo "✅ Конфигурация nginx валидна."
fi

if ! pgrep -x nginx >/dev/null 2>&1; then
  echo "❌ Процесс nginx не запущен."
  ok=false
else
  echo "✅ nginx запущен."
fi

body="$(curl -fsS http://127.0.0.1/ 2>/dev/null || true)"

if ! echo "$body" | grep -q "Client CRM работает"; then
  echo "❌ По адресу сервера открывается не сайт клиента."
  echo "   Ожидается содержимое из /var/www/client-crm."
  ok=false
else
  echo "✅ Открывается сайт клиента из /var/www/client-crm."
fi

echo

if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi

echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1