#!/usr/bin/env bash

echo "Проверка задания: сайт отдаёт 502 Bad Gateway"
echo

ok=true

if ! pgrep -x nginx >/dev/null 2>&1; then
  echo "❌ Процесс nginx не запущен."
  ok=false
else
  echo "✅ nginx запущен."
fi

if ! pgrep -f "php-fpm" >/dev/null 2>&1; then
  echo "❌ Процесс php-fpm не запущен — PHP-страницы работать не будут."
  ok=false
else
  echo "✅ php-fpm запущен."
fi

code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/index.php 2>/dev/null || echo 000)"

if [ "$code" != "200" ]; then
  echo "❌ http://127.0.0.1/index.php вернул код $code (ожидается 200)."
  ok=false
else
  echo "✅ PHP-страница открывается (200 OK)."
fi

body="$(curl -fsS http://127.0.0.1/index.php 2>/dev/null || true)"
if ! echo "$body" | grep -q "PHP сайт работает"; then
  echo "❌ PHP-страница не отдаёт ожидаемое содержимое."
  ok=false
else
  echo "✅ PHP-страница отдаёт корректный контент."
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
