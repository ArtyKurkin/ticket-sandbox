#!/usr/bin/env bash

echo "Проверка задания: главная страница отдаёт 404"
echo

ok=true

code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/ 2>/dev/null || echo 000)"

if [ "$code" = "200" ]; then
  body="$(curl -fsS http://127.0.0.1/ 2>/dev/null || true)"
  if echo "$body" | grep -q "Главная страница сайта"; then
    echo "✅ Главная страница открывается (200 OK)."
  else
    echo "❌ Код 200, но контент не тот, что ожидался."
    ok=false
  fi
else
  echo "❌ Главная страница вернула код $code (ожидается 200)."
  ok=false
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
