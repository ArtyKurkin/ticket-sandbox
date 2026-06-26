#!/usr/bin/env bash

echo "Проверка задания: порт 8080 занят, приложение не стартует"
echo

ok=true

# 1. Порт 8080 должен быть занят РОВНО одним слушателем (новым инстансом)
listeners="$(ss -tlnp 2>/dev/null | grep ':8080' | wc -l)"

if [ "$listeners" -eq 0 ]; then
  echo "❌ На порту 8080 никто не слушает — приложение не запущено."
  ok=false
elif [ "$listeners" -gt 1 ]; then
  echo "❌ На порту 8080 несколько слушателей ($listeners). Старый процесс не завершён."
  ok=false
else
  echo "✅ Порт 8080 слушает один процесс."
fi

# 2. Приложение должно отвечать
resp="$(curl -fsS http://127.0.0.1:8080/ 2>/dev/null || true)"
if echo "$resp" | grep -q "APP OK"; then
  echo "✅ Приложение отвечает на порту 8080."
else
  echo "❌ Приложение не отвечает на http://127.0.0.1:8080/"
  ok=false
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
