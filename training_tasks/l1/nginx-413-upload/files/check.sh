#!/usr/bin/env bash

echo "Проверка задания: загрузка файла 10 МБ"
echo

ok=true

# Проверяем реальную загрузку, а не конкретные значения конфигурации.
# multipart/form-data добавляет служебные данные сверх размера файла:
# client_max_body_size и post_max_size должны пропускать весь запрос,
# а upload_max_filesize — сам файл размером 10 МБ.
TESTDIR="$(mktemp -d /tmp/task-upload.XXXXXX)" || exit 1
trap 'rm -rf "$TESTDIR"' EXIT
TESTFILE="$TESTDIR/test_upload_10mb.bin"
RESPONSE_FILE="$TESTDIR/response"
EXPECTED_SIZE=10485760

if ! dd if=/dev/zero of="$TESTFILE" bs=1M count=10 status=none; then
  echo "❌ Не удалось создать тестовый файл 10 МБ."
  exit 1
fi

resp="$(curl -sS --noproxy '*' --max-time 30 \
  -o "$RESPONSE_FILE" -w '%{http_code}' \
  -F "doc=@${TESTFILE}" http://127.0.0.1/index.php 2>/dev/null)"
curl_code=$?
body="$(cat "$RESPONSE_FILE" 2>/dev/null)"

if [ "$curl_code" -ne 0 ]; then
  echo "❌ Не удалось завершить загрузку файла 10 МБ (ошибка curl: $curl_code)."
  ok=false
elif [ "$resp" = "200" ]; then
  if [ "$body" = "OK: получен файл размером ${EXPECTED_SIZE} байт" ]; then
    echo "✅ Файл 10 МБ успешно загружен и принят PHP полностью."
  else
    echo "❌ Сервер ответил 200, но не подтвердил приём файла 10 МБ целиком."
    echo "   Проверь обработчик загрузки и PHP-лимиты (upload_max_filesize / post_max_size)."
    ok=false
  fi
elif [ "$resp" = "413" ]; then
  echo "❌ Сервер вернул 413 Request Entity Too Large — nginx режет тело запроса (client_max_body_size)."
  ok=false
else
  echo "❌ Загрузка файла 10 МБ не прошла (код ответа: $resp)."
  echo "   Проверь все три лимита: client_max_body_size (nginx),"
  echo "   upload_max_filesize и post_max_size (php)."
  ok=false
fi

echo
if [ "$ok" = true ]; then
  echo "Задание пройдено."
  exit 0
fi
echo "Задание ещё не выполнено. Посмотри сообщения выше."
exit 1
