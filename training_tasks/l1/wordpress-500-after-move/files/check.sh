#!/usr/bin/env bash

echo "Проверка задания: сайт отдаёт 500 после переноса"
echo

ok=true

code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/index.php 2>/dev/null || echo 000)"

if [ "$code" = "200" ]; then
  body="$(curl -fsS http://127.0.0.1/index.php 2>/dev/null || true)"
  if echo "$body" | grep -q "работает"; then
    echo "✅ Сайт открывается (200) и подключается к базе данных."
  else
    echo "❌ Код 200, но контент неожиданный. Проверь работу приложения."
    ok=false
  fi
elif [ "$code" = "500" ]; then
  echo "❌ Сайт всё ещё отдаёт 500. Смотри логи:"
  echo "   - /var/log/nginx/error.log"
  echo "   - /var/log/php-fpm-error.log"
  echo "   Там видно, какие именно проблемы (их может быть несколько)."
  ok=false
else
  echo "❌ Сайт вернул код $code. Проверь, запущены ли nginx и php-fpm."
  ok=false
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
