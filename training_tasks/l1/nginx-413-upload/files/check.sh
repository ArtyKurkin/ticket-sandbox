#!/usr/bin/env bash

echo "Проверка задания: загрузка файлов больше 2 МБ"
echo

ok=true

# Готовим тестовый файл ~5 МБ
TESTFILE="/tmp/test_upload_5mb.bin"
dd if=/dev/zero of="$TESTFILE" bs=1M count=5 status=none 2>/dev/null

resp="$(curl -s -o /dev/null -w '%{http_code}' -F "doc=@${TESTFILE}" http://127.0.0.1/index.php 2>/dev/null || echo 000)"

if [ "$resp" = "200" ]; then
  body="$(curl -s -F "doc=@${TESTFILE}" http://127.0.0.1/index.php 2>/dev/null || true)"
  if echo "$body" | grep -q "OK: получен файл"; then
    echo "✅ Файл 5 МБ успешно загружен (сервер принял)."
  else
    echo "❌ Сервер ответил 200, но файл не принят. Проверь php-лимиты (upload_max_filesize / post_max_size)."
    ok=false
  fi
elif [ "$resp" = "413" ]; then
  echo "❌ Сервер вернул 413 Request Entity Too Large — nginx режет тело запроса (client_max_body_size)."
  ok=false
else
  echo "❌ Загрузка файла 5 МБ не прошла (код ответа: $resp)."
  echo "   Проверь все три лимита: client_max_body_size (nginx),"
  echo "   upload_max_filesize и post_max_size (php)."
  ok=false
fi

rm -f "$TESTFILE"

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
