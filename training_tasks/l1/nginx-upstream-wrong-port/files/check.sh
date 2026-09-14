#!/usr/bin/env bash

echo "Проверка задания: сайт возвращает 502 Bad Gateway"
echo

ok=true

if ! nginx -t >/dev/null 2>&1; then
  echo "❌ Конфигурация nginx содержит ошибку."
  ok=false
fi

if ! pgrep -x nginx >/dev/null 2>&1; then
  echo "❌ nginx не запущен."
  ok=false
fi

backend_body="$(curl -fsS --max-time 2 http://127.0.0.1:9000/ 2>/dev/null || true)"
if ! printf '%s' "$backend_body" | grep -q "CUSTOMER API OK"; then
  echo "❌ Внутренняя часть учебного окружения работает некорректно."
  echo "   Перезапусти окружение и попробуй ещё раз."
  ok=false
fi

site_code="$(curl -sS --max-time 3 -o /tmp/task-site-body -w '%{http_code}' http://127.0.0.1/ 2>/dev/null || true)"
site_body="$(cat /tmp/task-site-body 2>/dev/null || true)"
rm -f /tmp/task-site-body

if [ "$site_code" != "200" ]; then
  echo "❌ Сайт всё ещё недоступен через веб-сервер (HTTP ${site_code:-000})."
  ok=false
elif ! printf '%s' "$site_body" | grep -q "CUSTOMER API OK"; then
  echo "❌ Сайт отвечает, но возвращает некорректное содержимое."
  ok=false
else
  echo "✅ Сайт корректно открывается через nginx."
fi

echo

if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi

echo "Задание ещё не выполнено. Проведи дополнительную диагностику."
exit 1
