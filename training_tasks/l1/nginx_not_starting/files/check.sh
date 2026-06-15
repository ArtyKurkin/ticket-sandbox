#!/usr/bin/env bash

echo "Проверка задания: nginx не стартует"

if ! nginx -t; then
  echo "❌ Конфигурация nginx всё еще невалидна."
  exit 1
fi

if ! pgrep nginx >/dev/null; then
  echo "❌ nginx не запущен."
  exit 1
fi

if ! curl -fsS http://127.0.0.1/ >/dev/null; then
  echo "❌ Сайт не открывается локально."
  exit 1
fi

echo "✅ Конфигурация nginx валидна."
echo "✅ nginx запущен."
echo "✅ Сайт открывается."
echo "Задание пройдено."