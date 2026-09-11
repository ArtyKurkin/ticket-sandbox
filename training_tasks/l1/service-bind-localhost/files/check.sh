#!/usr/bin/env bash

echo "Проверка задания: сервис недоступен по сети"
echo

ok=true

if ! /usr/local/bin/customer-app status >/dev/null 2>&1; then
  echo "❌ Приложение не запущено."
  ok=false
fi

local_body="$(curl -fsS --max-time 2 http://127.0.0.1:8080/ 2>/dev/null || true)"
if ! printf '%s' "$local_body" | grep -q "APP OK: customer service is running"; then
  echo "❌ Приложение не отвечает локально на ожидаемом порту."
  ok=false
fi

container_ip="$(
  ip -4 -o addr show scope global 2>/dev/null \
    | awk '{split($4, a, "/"); print a[1]; exit}'
)"

if [ -z "$container_ip" ]; then
  echo "❌ Не удалось определить сетевой адрес учебного окружения."
  echo "   Перезапусти окружение и попробуй ещё раз."
  ok=false
else
  network_body="$(curl -fsS --noproxy '*' --max-time 2 "http://${container_ip}:8080/" 2>/dev/null || true)"

  if ! printf '%s' "$network_body" | grep -q "APP OK: customer service is running"; then
    echo "❌ Сервис всё ещё недоступен через сетевой интерфейс."
    ok=false
  else
    echo "✅ Сервис доступен через сетевой интерфейс."
  fi
fi

echo

if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi

echo "Задание ещё не выполнено. Проведи дополнительную диагностику."
exit 1
