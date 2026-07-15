#!/usr/bin/env bash

echo "Проверка задания: приложение не может подключиться к базе данных"
echo

ok=true

output="$(/opt/app/check_db_connection.sh 2>&1)"
code=$?

if [ "$code" -eq 0 ]; then
  echo "✅ Соединение с db-internal установлено."
  echo "   $output"
else
  echo "❌ Соединение не установлено."
  echo "   $output"
  ok=false
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
