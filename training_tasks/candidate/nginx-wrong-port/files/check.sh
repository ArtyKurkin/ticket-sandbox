#!/usr/bin/env bash

echo "Проверка задания: сайт не открывается по обычному адресу"
echo

ok=true

code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:80/ 2>/dev/null || echo 000)"

if [ "$code" = "200" ]; then
  body="$(curl -fsS http://127.0.0.1:80/ 2>/dev/null || true)"
  if echo "$body" | grep -q "Сайт работает"; then
    echo "✅ Сайт открывается на стандартном порту 80."
  else
    echo "❌ Код 200, но контент не тот, что ожидался."
    ok=false
  fi
else
  echo "❌ Сайт на порту 80 вернул код $code (ожидается 200)."
  echo "   Проверь, на каком порту слушает nginx."
  ok=false
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
