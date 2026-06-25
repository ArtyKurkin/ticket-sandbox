#!/usr/bin/env bash

echo "Проверка задания: логи приложения занимают слишком много места"
echo

ok=true

# 1. Большой лог должен быть очищен или удалён
if [ -f /var/log/app/debug.log ]; then
  size_mb=$(du -m /var/log/app/debug.log | cut -f1)
  if [ "$size_mb" -gt 50 ]; then
    echo "❌ Файл /var/log/app/debug.log всё ещё занимает ${size_mb} МБ."
    echo "   Его нужно очистить или удалить."
    ok=false
  else
    echo "✅ Большой лог-файл очищен (сейчас ${size_mb} МБ)."
  fi
else
  echo "✅ Большой лог-файл удалён."
fi

# 2. Важный конфиг НЕ должен быть удалён
if [ ! -f /etc/app/app.conf ]; then
  echo "❌ Удалён нужный конфиг /etc/app/app.conf — так делать нельзя."
  ok=false
else
  echo "✅ Важный конфиг приложения на месте."
fi

echo

if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi

echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
