#!/usr/bin/env bash

echo "Проверка задания: HTTPS открывает не тот сайт"
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

portal_body="$(
  curl -ksS --noproxy '*' --max-time 3 \
    --resolve portal.example.test:443:127.0.0.1 \
    https://portal.example.test/ 2>/dev/null || true
)"

if ! printf '%s' "$portal_body" | grep -q "CUSTOMER PORTAL OK"; then
  echo "❌ По домену портала всё ещё открывается некорректный сайт."
  ok=false
fi

cert_subject="$(
  printf '' \
    | openssl s_client \
        -connect 127.0.0.1:443 \
        -servername portal.example.test \
        2>/dev/null \
    | openssl x509 -noout -subject 2>/dev/null \
    || true
)"

if ! printf '%s' "$cert_subject" | grep -q "CN *= *portal.example.test"; then
  echo "❌ Для домена портала nginx всё ещё отдаёт некорректный сертификат."
  ok=false
fi

legacy_body="$(
  curl -ksS --noproxy '*' --max-time 3 \
    --resolve legacy.example.test:443:127.0.0.1 \
    https://legacy.example.test/ 2>/dev/null || true
)"

if ! printf '%s' "$legacy_body" | grep -q "LEGACY SERVICE"; then
  echo "❌ Служебный HTTPS-сайт повреждён."
  ok=false
fi

echo

if [ "$ok" = true ]; then
  echo "✅ HTTPS-виртуальный хост портала работает корректно."
  echo
  echo "Задание пройдено."
  exit 0
fi

echo "Задание ещё не выполнено. Проведи дополнительную диагностику."
exit 1
