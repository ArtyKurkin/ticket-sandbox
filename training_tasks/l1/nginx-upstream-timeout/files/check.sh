#!/usr/bin/env bash

echo "Проверка задания: API отвечает 504 Gateway Timeout"
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

if ! /usr/local/bin/report-api status >/dev/null 2>&1; then
  echo "❌ API-приложение не запущено."
  ok=false
fi

health_body="$(curl -fsS --max-time 2 http://127.0.0.1:9000/health 2>/dev/null || true)"
if ! printf '%s' "$health_body" | grep -q "API HEALTH OK"; then
  echo "❌ API-приложение работает некорректно."
  ok=false
fi

direct_start="$(date +%s)"
direct_body="$(curl -fsS --max-time 6 http://127.0.0.1:9000/report 2>/dev/null || true)"
direct_end="$(date +%s)"
direct_elapsed=$((direct_end - direct_start))

if ! printf '%s' "$direct_body" | grep -q "REPORT READY"; then
  echo "❌ API не формирует отчёт напрямую."
  ok=false
elif [ "$direct_elapsed" -lt 2 ]; then
  echo "❌ Исходное поведение API было изменено."
  ok=false
fi

proxy_start="$(date +%s)"
proxy_code="$(
  curl -sS --max-time 7 \
    -o /tmp/task-report-body \
    -w '%{http_code}' \
    http://127.0.0.1/api/report \
    2>/dev/null || true
)"
proxy_end="$(date +%s)"
proxy_elapsed=$((proxy_end - proxy_start))
proxy_body="$(cat /tmp/task-report-body 2>/dev/null || true)"
rm -f /tmp/task-report-body

if [ "$proxy_code" != "200" ]; then
  echo "❌ Запрос отчёта через nginx всё ещё завершается ошибкой (HTTP ${proxy_code:-000})."
  ok=false
elif ! printf '%s' "$proxy_body" | grep -q "REPORT READY"; then
  echo "❌ Через nginx возвращается некорректный ответ API."
  ok=false
elif [ "$proxy_elapsed" -lt 2 ]; then
  echo "❌ Запрос через nginx не проходит через исходный backend."
  ok=false
else
  echo "✅ Отчёт успешно формируется через nginx."
fi

echo

if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi

echo "Задание ещё не выполнено. Проведи дополнительную диагностику."
exit 1
