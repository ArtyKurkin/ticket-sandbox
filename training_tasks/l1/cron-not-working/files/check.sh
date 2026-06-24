#!/usr/bin/env bash

echo "Проверка задания: cron не выполняет задачу"
echo

ok=true

if [ ! -f /var/www/html/status.txt ]; then
  echo "❌ Файл /var/www/html/status.txt не создан — cron-задача не отработала."
  ok=false
else
  now=$(date +%s)
  mtime=$(stat -c %Y /var/www/html/status.txt)
  age=$(( now - mtime ))
  if [ "$age" -gt 90 ]; then
    echo "❌ Файл status.txt не обновлялся ${age} сек — cron всё ещё не работает."
    ok=false
  else
    echo "✅ status.txt обновлён ${age} сек назад — задача выполняется."
  fi
fi

if ! pgrep -x cron >/dev/null 2>&1; then
  echo "❌ Служба cron не запущена."
  ok=false
else
  echo "✅ Служба cron запущена."
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. После правок подожди до минуты и проверь снова."
exit 1
