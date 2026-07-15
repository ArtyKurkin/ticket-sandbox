#!/usr/bin/env bash

echo "Проверка задания: сайт совсем не открывается"
echo

ok=true

if ! pgrep -x nginx >/dev/null 2>&1; then
  echo "❌ Процесс nginx не запущен."
  ok=false
else
  echo "✅ nginx запущен."
fi

if ! curl -fsS http://127.0.0.1/ >/dev/null 2>&1; then
  echo "❌ Сайт не отвечает на http://127.0.0.1/"
  ok=false
else
  echo "✅ Сайт открывается."
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
