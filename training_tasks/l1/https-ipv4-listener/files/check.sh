#!/usr/bin/env bash

echo "Проверка задания: доступность HTTPS по IPv4 и IPv6"
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

ipv6_body="$(
  curl -g -6 -ksS --noproxy '*' --max-time 3 \
    https://[::1]/ 2>/dev/null || true
)"

if ! printf '%s' "$ipv6_body" | grep -q "CUSTOMER HTTPS OK"; then
  echo "❌ HTTPS-сайт перестал работать по IPv6."
  ok=false
fi

ipv4_body="$(
  curl -4 -ksS --noproxy '*' --max-time 3 \
    https://127.0.0.1/ 2>/dev/null || true
)"

if ! printf '%s' "$ipv4_body" | grep -q "CUSTOMER HTTPS OK"; then
  echo "❌ HTTPS-сайт всё ещё недоступен по IPv4."
  ok=false
else
  echo "✅ HTTPS-сайт доступен по IPv4."
fi

echo

if [ "$ok" = true ]; then
  echo "✅ Сайт доступен по IPv4 и IPv6."
  echo
  echo "Задание пройдено."
  exit 0
fi

echo "Задание ещё не выполнено. Проведи дополнительную диагностику."
exit 1
