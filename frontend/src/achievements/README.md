# Trophy Room

Маршрут `/achievements/`, Django session. Обычный режим загружает только
`GET /api/achievements/me/`; модалка — `GET /api/achievements/me/<public_id>/`.
GET не выдаёт наград, не запускает reconciliation и не восстанавливает Sandbox.

## Запуск

```sh
npm run build --prefix frontend
python manage.py runserver
```

Сначала войти через `/login/`. Backend achievements migrations должны быть
применены к выбранной локальной БД. Для отдельных API проверок и синтетических
данных см. `ACHIEVEMENT_BACKEND_FOUNDATION.md` в корне проекта.

## Данные и отображение

- `api.ts` проверяет JSON, UUID, nullable tier, stats и cursor; запросы только
  GET, same-origin cookies, no-store, AbortSignal. HTTP/network/contract ошибки
  различаются; повтор загрузки доступен без fixture fallback.
- `useTrophies.ts` управляет loading/error/ready и отменяет устаревшие запросы.
- `types.ts` отделяет текущий DTO от demo fixture; дата форматируется только из
  серверного timestamp. Неполученная tiered линейка имеет нейтральный металл;
  раскрытая fixed награда может показывать известную редкость до получения.
- `TrophyRoom` строит одну карточку на public UUID, показывает server stats и
  pending state. Общая статистика не меняется при фильтрации. При progress=null
  нет полосы, процента или вычисленного прогресса комнаты.
- `TrophyDetails` загружает настоящую историю по 50 событий, продолжает по
  next_cursor, объединяет по event ID. Native dialog, Escape, focus trap,
  возврат фокуса и прокрутка сохранены. История показывает recorded_at выдачи,
  from/to tier, ручное решение и причину отзыва. Пропущенных уровней нет.
- Секретность берётся только из secret/revealed API. Закрытый секрет имеет
  нейтральный вопросительный медальон, не участвует в metal/category фильтрах
  и не раскрывает condition/progress. UUID/code не используются для угадывания.
- `TrophyMedallion` выбирает локальную геометрию по whitelist art_key с generic
  fallback. `palette.ts` задаёт rim/bevel/core/facet/accent цвета; SVG art/*
  используют CSS variables вместо зашитых металлов. Пути, transforms,
  размеры viewBox, фильтры, градиентные offsets и объём сохранены.

## Демонстрация и уведомления

Django передаёт canDemo из request.user.is_staff и reverse URL; query-параметры
не влияют на права. Только явный staff demo вызывает lazy import
`demonstration.ts`/`data.ts`. Demo state отделён от API state и обозначен на
экране. Unlock меняет только React state; POST не выполняется, даты не создаются.
Выход из demo очищает его toast и возвращает реальную коллекцию.

Текущий collection API не отдаёт ID/action последнего grant/upgrade.
Revision включает также revoke и evidence_disputed. Обычные toast пока
не запускаются: загрузка, фильтр, details, retry и выход из demo не являются
доказательствами нового события. Компонент анимации сохранён в staff demo.
Для настоящих уведомлений нужен отдельный read-only event cursor/feed;
предложение описано в `TROPHY_ROOM_REACT_INTEGRATION.md` в корне проекта.

## Проверки

```sh
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
python manage.py check
python manage.py test achievements react_frontend roadmap
```

Tests/fixtures/trophies содержат ответы настоящего Django API на изолированной
синтетической БД и не входят в Vite bundle. Скриншоты и результаты Chromium
для 1440×900, 1280×800, 768×1024, 390×844 — в отчёте интеграции.
Ручная выдача/отзыв в обычной комнате не представлены; API/правила backend
не менялись. Не включать WHITENOISE_KEEP_ONLY_HASHED_FILES: общие Vite imports
обслуживаются через собранные относительные chunks.
