#!/usr/bin/env bash

echo "Проверка задания: приложение не видит свои файлы после распаковки"
echo

ok=true

# 1. Приложение должно успешно отработать ПОД appuser
run_out="$(su appuser -c '/opt/myapp/run.sh' 2>&1)"
run_code=$?

if [ "$run_code" -eq 0 ] && echo "$run_out" | grep -q "OK:"; then
  echo "✅ Приложение успешно запускается под appuser и обрабатывает данные."
else
  echo "❌ Приложение под appuser не отработало."
  echo "   Вывод: $run_out"
  ok=false
fi

# 2. Запрет на ленивое решение через 777
# Проверяем, что ключевые объекты НЕ имеют world-writable бит (последняя цифра не 2,3,6,7)
check_not_world_writable() {
  local path="$1"
  if [ -e "$path" ]; then
    local perm
    perm=$(stat -c '%a' "$path")
    local last="${perm: -1}"
    case "$last" in
      2|3|6|7)
        echo "❌ $path имеет права $perm — доступ на запись для всех (world-writable)."
        echo "   Так делать нельзя. Используй владельца/группу, а не 777."
        ok=false
        ;;
    esac
  fi
}

check_not_world_writable /opt/myapp
check_not_world_writable /opt/myapp/config.ini
check_not_world_writable /opt/myapp/data
check_not_world_writable /opt/myapp/data/records.txt
check_not_world_writable /opt/myapp/output

if [ "$ok" = true ]; then
  echo "✅ Права выставлены аккуратно, без world-writable."
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
