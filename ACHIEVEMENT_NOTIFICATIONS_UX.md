# Achievement Notifications & TraineeDiary UX Polish

14 октября 2026. Задача №14, ветка `feature/roadmap-react`.

Реализованы реальные уведомления текущего пользователя по `AchievementEvent.grant/upgrade`: durable очередь, серверная граница запуска, эксклюзивный временный claim, идемпотентный ack и один общий React host. Он подключён к Roadmap, Trophy Room и общему Django layout, включая Ticket Sandbox и Diary. В Diary добавлены цветные текстовые метки уровней, понятные системные объяснения и удалено повторение названия в деталях. Правила выдачи, evaluators и геометрия медальонов сохранены.

## Архитектура и точки подключения

Изучены отчёты задач 11–13, модели/история/receipts, grants service и API, frontend Trophy Room и entry points, Django layouts Roadmap/Trophy Room/Sandbox. Существующий `TrophyUnlockToast` использовался только для явно обозначенной staff demo; реального event feed и read state не было. Telegram notifications Sandbox относятся к сообщениям наставникам и не участвуют в новой доставке.

Выбран отдельный Vite entry `src/notifications/main.tsx`, использующий существующие `TrophyUnlockToast` и `TrophyMedallion`. Один template inclusion tag формирует config через `reverse`, CSRF через `get_token` и подключает host только authenticated пользователю. Tag предотвращает повторный include в одном request; bootstrap дополнительно устанавливает singleton marker в document. React страницы получают тот же fragment, а Django страницы — его через `templates/base.html`. Локальные компоненты Roadmap/TrophyRoom не создают вторые polling cycles.

Новый host не является второй галереей и не выводит формы выдачи. SVG art, paths и палитры Trophy Room не менялись. Toast получает название, металл и настоящий переход из конкретного события. В анимации сохранено появление Trophy Room toast, добавлены краткое свечение/выделение выбранного металла. `prefers-reduced-motion` отключает анимации host. Для настоящего уведомления автоматическое закрытие отключено: просмотр подтверждается действием пользователя. Demo сохраняет прежний пятисекундный toast с явной пометкой и не вызывает notification ack.

## Модели и первоначальный запуск

Миграция [0005_notifications.py](achievements/migrations/0005_notifications.py) создаёт две небольшие таблицы:

| Модель | Назначение |
|---|---|
| `AchievementNotificationBoundary` | Singleton `id=1`, `started_at`: время включения доставки, записанное миграцией |
| `AchievementNotification` | OneToOne `event`, владелец `user`, nullable `read_at`, UUID `claim_token`, `claim_expires_at`; индекс user/read/event |

Миграция не создаёт уведомления из прошлой истории. Выдающий сервис добавляет delivery только для реально созданного grant/upgrade с `recorded_at >= started_at`. Это происходит в той же atomic транзакции, что событие, projection и receipt. При rollback откатывается и уведомление. Duplicate operation, no-op, suppressed, revoke и evidence_disputed не вызывают enqueue.

Граница задаётся сервером при миграции, а не первым входом пользователя. Событие после границы сохраняется, даже если сотрудник ещё ни разу не открывал страницу. Старое предметное доказательство, по которому после запуска действительно впервые выдана награда, создаёт новое событие выдачи и новое уведомление; старые **существовавшие события выдачи** не превращаются в новую очередь.

OneToOne гарантирует одну delivery-запись на event. Записи прочтения не создаются из GET. `AchievementEvent` остаётся неизменяемым; notification state хранится отдельно. Admin обеих новых моделей — read-only.

## Notification API

Все маршруты session-authenticated, только для текущего владельца, private/no-store. Staff личный feed содержит только его собственные награды, без выбора стажёра. Клиент получает URLs через Django reverse и не строит путь Trophy Room самостоятельно.

| Метод / путь | Поведение |
|---|---|
| GET `/api/achievements/me/notifications/` | SELECT-only список до 10 доступных непрочитанных событий и общий unread count |
| POST `/api/achievements/me/notifications/<event_id>/claim/` | CSRF + атомарное получение/продление права показа на 90 секунд |
| POST `/api/achievements/me/notifications/<event_id>/ack/` | CSRF + идемпотентное подтверждение просмотра |

Пример GET:

```json
{
  "items": [{
    "event_id": 123,
    "action": "upgrade",
    "public_id": "00000000-0000-4000-8000-000000000001",
    "title": "Скорость обработки тикетов",
    "secret": false,
    "from_tier": {"code":"bronze","rank":1,"rarity":"bronze"},
    "to_tier": {"code":"platinum","rank":4,"rarity":"platinum"},
    "recorded_at": "2026-10-14T12:00:00+00:00",
    "art_key": "speed",
    "read": false,
    "read_at": null
  }],
  "unread_count": 1,
  "has_more": false,
  "poll_after_seconds": 50,
  "trophy_room_url": "/achievements/"
}
```

Это пример контракта, не fixture для рабочего UI. Используются фактические событие/дата/металл backend. Raw evidence, Sandbox answers/comments, reason/actor и provider internals отсутствуют. Art key проверяется серверным whitelist, с generic fallback; React экранирует названия, клиент не вставляет HTML.

Оба POST принимают только:

```json
{"claim_token":"<UUID конкретного показа>"}
```

Claim возвращает `read=false`, безопасный `notification`, тот же `claim_token`, `lease_seconds=90`. Если событие уже просмотрено — `read=true, event_id`. Ack возвращает `event_id`, `read=true`, фактический серверный `read_at`. Повтор ack сохраняет первую дату просмотра.

401 — нет session; 403 — CSRF; 404 — чужая/отсутствующая delivery или скрытый secret при claim; 409 — другое действующее право показа либо отсутствующий/сменившийся token для ack; 400 — некорректный JSON/token/лишние поля; 405 — неправильный method. Grant/revoke через эти endpoints невозможны. Проверяются владелец delivery **и** владелец связанного event.

## Секретные достижения

GET и claim проверяют актуальную definition/entitlement. Неполученный секрет не имеет delivery, а отозванный секрет с `active_tier=NULL` полностью исключён из feed и unread count. Старый notification не раскрывает название, металл, art, ID или историю скрытого секрета. Claim такого события возвращает общий 404.

Claim блокирует user в том же порядке, что grants/revoke, затем только строку delivery; актуальное состояние секрета не меняется посередине построения claim response. Feed выполняет фильтр видимости в SELECT. При следующем renewal уже открытый toast исчезает, если источник стал скрыт. Это polling, поэтому уже показанный ранее активный секрет может оставаться на открытой странице до следующей проверки (около 50 секунд); server API после revoke его больше не раскрывает.

## Очередь, прочтение и несколько вкладок

Host показывает один toast. Первая автоматическая порция — максимум три события за посещение; после неё появляется «Показать новые уведомления (N)». Следующая порция открывается явно. Все остальные уведомления продолжают храниться на сервере. Feed не имеет архива прочитанного: доступные порции продвигаются после ack, `has_more` описывает оставшиеся доступные записи, unread count включает также lease в другой вкладке.

Закрытие toast или открытие Trophy Room сначала отправляет ack. До успешного ответа событие не считается просмотренным; при ошибке пользователь видит сообщение и может повторить действие. Переход в Trophy Room выполняется только после подтверждённого ack. При неопределённом результате повтор с тем же token безопасен. Двойной клик и параллельный poll/ack сериализуются клиентом; серверный row lock сериализует ack и сохраняет один `read_at`.

Poll — один последовательный цикл с timeout запроса 15 секунд и интервалом 50 секунд после завершения. Он обновляет счётчик и продлевает текущий lease. При hidden tab циклы прекращаются, запрос отменяется, toast не рисуется; при возврате выполняется немедленная проверка. `pagehide` приостанавливает host, `pageshow` возобновляет; unmount останавливает timer/request/listeners. Поздний ответ отменённого поколения не восстанавливает прежний toast. 401/403 прекращают автоматические запросы; повторная проверка после восстановления session запускается явной кнопкой. Network/5xx сохраняют непрочитанное состояние и допускают повтор.

Для нескольких окон используются два уровня:

1. Серверный claim/lease: одновременно действителен один UUID показа для одного event. Другой claim получает 409, чужая session — 404. Lease можно продлить тем же UUID; после истечения его может забрать другое окно. Старый UUID после передачи больше не может подтвердить unread событие.
2. Опциональный BroadcastChannel с namespace владельца: передаёт только ID после успешного ack и будит проверку в других окнах. Сообщение само по себе **не** меняет read state и не снимает toast: решение подтверждает сервер. При отсутствии BroadcastChannel работает серверный протокол и обычный polling.

Это не обещание абсолютного однократного визуального показа: падение окна до ack, длительная потеря связи или истечение lease могут привести к новому показу непрочитанного события. Передача между скрытыми окнами иногда ждёт истечения 90 секунд. Подтверждение просмотра остаётся идемпотентным и серверным; истечение claim не означает прочтение.

Demo Trophy Room приостанавливает настоящий host без ack. При возврате может продолжиться тот же непрочитанный реальный event. Само переключение/фильтр/перечитывание галереи не создаёт нового события или повышения; demo toast и состояние real очереди разделены. Начальная загрузка уже прочитанной истории ничего не показывает.

## `process_achievement_events`

Команда обновлена: после штатной обработки source events она выполняет `repair_delivery(--limit)` для grant/upgrade после `started_at`, у которых нет delivery. Это закрывает разрыв между миграцией и обновлением старых workers при rolling deployment, либо пропуск enqueue сторонним trusted writer. Повтор ремонта безопасен из-за OneToOne; прочитанные delivery не пересоздаются. Команда не изменяет события/награды и не подтверждает просмотр.

Для обычного grant/upgrade worker доставки не нужен: enqueue атомарный и немедленный. Регулярный запуск существующего drain по-прежнему нужен для pending/error sources и недель, достигших конца периода; теперь он также постепенно восстанавливает пропущенные notification rows. Нового broker, Channels или WebSocket нет. При ремонте ненулевого числа rows команда печатает дополнительный JSON `notification_deliveries_repaired`.

## UX TraineeDiary

Компактная вкладка, список и действия сохранены. Металлические значки дополнены текстовыми badges «Бронза», «Серебро», «Золото», «Платина», с разными цветами в dark/light темах. По одному активному badge и значку на определение.

Автоматический `evidence_disputed` в истории получает понятное объяснение: «Данные, на основании которых выдана награда, изменились. Проверь результат и при необходимости отзови награду». Вместо технической блокировки показано: «После отзыва награду можно выдать повторно только вручную». Тексты списка, деталей, предупреждения, подтверждения и повторной выдачи согласованы. Backend enum, evidence и сохранённая причина не меняются.

Ручные причины наставников выводятся дословно через textContent, даже если в них есть технические слова или HTML-like текст. Системное объяснение выбирается по action/manual, а не поиском/заменой слов в пользовательском комментарии. Если description совпадает с title (после trim/case), повторное описание не выводится; содержательное описание сохраняется. Сложные фильтры/поиск не добавлены. Chromium повторно выполнил обычные grant → upgrade → revoke после polish.

## Файлы

Изменены существующие исходники задачи:

- [achievements/models.py](achievements/models.py), [admin.py](achievements/admin.py), [urls.py](achievements/urls.py).
- [achievements/services/grants.py](achievements/services/grants.py): только вызов enqueue после настоящей выдачи, внутри существующей atomic; условия и policy не изменены.
- [achievements/management/commands/process_achievement_events.py](achievements/management/commands/process_achievement_events.py): восстановление отсутствующей delivery.
- [templates/base.html](templates/base.html), [React Roadmap template](react_frontend/templates/react_frontend/roadmap.html), [Trophy Room template](react_frontend/templates/react_frontend/achievements.html): общий host.
- [frontend/vite.config.ts](frontend/vite.config.ts): notifications entry.
- [TrophyUnlockToast.tsx](frontend/src/achievements/TrophyUnlockToast.tsx): optional label, autoDismiss и disabled; demo defaults сохранены.
- [diary-achievement-api.js](static/js/diary-achievement-api.js), [diary-achievements.js](static/js/diary-achievements.js), [diary-achievements.css](static/css/diary-achievements.css), [Diary fragment](traineediary/templates/traineediary/_achievements.html), [Diary JS tests](traineediary/tests/js/achievements.test.mjs).

Созданы:

```text
achievements/notification_views.py
achievements/services/notifications.py
achievements/migrations/0005_notifications.py
achievements/templatetags/__init__.py
achievements/templatetags/achievement_notifications.py
achievements/templates/achievements/_notifications.html
achievements/tests/test_notifications.py
achievements/tests/test_notification_concurrency.py
achievements/tests/test_notification_migration.py
frontend/src/notifications/api.ts
frontend/src/notifications/controller.ts
frontend/src/notifications/NotificationHost.tsx
frontend/src/notifications/main.tsx
frontend/src/notifications/styles.css
frontend/tests/notifications.test.cjs
react_frontend/test_notification_integration.py
ACHIEVEMENT_NOTIFICATIONS_UX.md
docs/achievement-notifications/*.png
```

Vite обновил ignored `static/frontend/manifest.json` и hashed assets; исходники предыдущих задач сохранены. Начальный SHA-256 snapshot содержал 723 файла. Отличия существующих исходников ограничены перечисленным scope. Roadmap SVG/CSS, Trophy Room medal art/geometry, evaluators/catalog/пороги, Sandbox technical code, Diary models/transitions и предыдущие отчёты не изменены.

## Скриншоты

Сняты настоящим Chromium на синтетической SQLite, через реальные backend grant/claim/ack. Ручная тестовая платина не включает выключенный evaluator и не является доказательством курса/Sandbox/full-week реального сотрудника.

| Сценарий | Скриншот |
|---|---|
| Bronze на Roadmap | [bronze.png](docs/achievement-notifications/bronze.png) |
| Gold в Trophy Room | [gold.png](docs/achievement-notifications/gold.png) |
| Platinum в Django Ticket Sandbox | [platinum.png](docs/achievement-notifications/platinum.png) |
| Один upgrade bronze → platinum | [upgrade.png](docs/achievement-notifications/upgrade.png) |
| Ошибка ack, toast остаётся | [ack-error.png](docs/achievement-notifications/ack-error.png) |
| Очередь после первой порции | [queue-more.png](docs/achievement-notifications/queue-more.png) |
| Mobile gold/platinum, reduced motion | [mobile-gold.png](docs/achievement-notifications/mobile-gold.png), [mobile-platinum.png](docs/achievement-notifications/mobile-platinum.png) |
| Исправленный Diary, desktop/mobile | [diary-desktop.png](docs/achievement-notifications/diary-desktop.png), [diary-mobile.png](docs/achievement-notifications/diary-mobile.png) |
| Понятная история без повторного заголовка | [diary-history.png](docs/achievement-notifications/diary-history.png) |

Размеры: desktop 1440×1000, mobile 390×844. Горизонтальный overflow и выход toast за viewport отсутствуют.

## Проверки

| Проверка | Итог |
|---|---|
| Full Django suite, временная SQLite | **866 тестов, OK**, 265,734 с; 10 PostgreSQL skips |
| PostgreSQL achievements + Roadmap + React + Diary integration | **148 тестов, OK**, без skips |
| Финальные новые notification/concurrency/migration/host tests, PostgreSQL | **17 тестов, OK**, включая реальное конкурентное ack/claim |
| Дополнительные migration/host integration, SQLite | **3 теста, OK** |
| Frontend Node suite | **60/60 OK**, включая 14 новых notification tests |
| Diary JS + существующий Kanban | **14/14 OK**, включая два новых UX tests |
| TypeScript typecheck | OK |
| Vite production build | OK |
| Fresh migrate SQLite/PostgreSQL | OK |
| System checks SQLite/PostgreSQL | 0 issues |
| `makemigrations --check --dry-run`, `migrate --check`, обе БД | OK |
| `git diff --check`, scope SHA-256 | OK |
| Chromium | **43 сценария, OK**, три required pages, desktop/mobile, несколько окон, reduced motion |

Backend проверяет grant/upgrade и no-op/duplicate/source retries, отсутствие revoke/disputed delivery, rollback, cutoff и настоящий migration upgrade с прежним event, сохранение unread между сессиями, SELECT-only GET, CSRF, 400/401/403/404/405/409, чужой event, redaction после secret revoke, lease takeover, идемпотентный ack и bounded repair. PostgreSQL отдельно проверяет две одновременно запрошенные leases и два одновременных ack с одинаковым `read_at`.

Frontend проверяет реальный transition, одну геометрию/один toast, portions, повтор GET/ack, queue, network/5xx/auth failures, lifecycle, late response, API CSRF/credentials, singleton и advisory BroadcastChannel. Chromium дополнительно подтвердил фактические POST/read state на трёх страницах, две одновременно видимые windows с одним server claim, 409 второго окна, BroadcastChannel после ack, остановку скрытой страницы и pagehide, немедленный resume и один 50-second timer. Интервал и visibility проверялись инструментированием browser timers/events без изменения app исходников. Проверены скрытие уже открытого secret после revoke на очередном renewal, пауза real host в demo и прежние Diary действия.

Окончательные отдельные migration/host tests были добавлены после старта полного suite; они дополнительно прошли SQLite/PostgreSQL, поэтому не выдаются за часть числа 866. Первоначально проверки шаблонов обнаружили устаревший collected manifest; финальные suite использовали fresh build/collectstatic во временном STATIC_ROOT. Migration test также проверен после TransactionTestCase flush с самостоятельным seed каталога. Рабочие staticfiles и БД не использовались для тестовых записей. PostgreSQL работал только через `/tmp/achievement14-pg/socket`, без TCP.

## Production и ограничения

1. Перед запуском нового grants code требуется применить `0005_notifications`, затем выпустить fresh Vite build и collectstatic. Это schema/asset requirement существующего Vite tag; все authenticated Django pages теперь также используют notification entry. В этой задаче production миграции/деплой не выполнялись.
2. Граница `started_at` фиксируется один раз миграцией. При rolling deploy новые workers/drain должны быть обновлены: repair восстанавливает только grant/upgrade после этой границы. Массового уведомления по старым событиям нет. Границу и пользовательский read state нельзя заменять датой первого посещения.
3. Продолжать регулярный `process_achievement_events --limit 100` по существующему scheduler. Если после границы много пропусков, повторные bounded запуски восстановят delivery постепенно. Infrastructure scheduler не менялся.
4. Read delivery следует сохранять: отдельной retention/архивации с tombstones нет. Удаление read rows без новой политики приведёт к их восстановлению repair и потере факта просмотра. Admin не разрешает такие удаления.
5. Lease обеспечивает эксклюзивное действующее право, но не абсолютную однократность визуального показа при сбоях/expiry. Серверный read остаётся окончательным источником. Hidden-window handover может ждать до 90 секунд. Web Locks не требуются; BroadcastChannel опционален.
6. Read подтверждается закрытием/открытием Trophy Room, не автоматическим таймером. При ошибке ack переход не выполняется; session/CSRF требуют восстановления входа или обновления страницы. Общая коллекция Trophy Room по-прежнему обновляется своей кнопкой: toast не переписывает локальные tiers карточек.
7. Feed — очередь непрочитанных, без отдельного архива/bell center и без staff выбора чужого feed. Nonsecret старый grant может оставаться unread после последующего revoke как реальное историческое событие; revoke сам поздравления не создаёт. Скрытые revoked secrets полностью исключены.
8. Polling заменяет push, поэтому обновление на открытой странице/скрытие ранее раскрытого секрета может ждать следующей проверки. Если lease renewal не подтверждается из-за сети, toast может временно оставаться показанным до восстановления связи; другой window после expiry может получить его вновь.
9. Тестирование выполнялось на свежих временных SQLite/PostgreSQL и синтетических пользователях. Исторический production backfill не запускался. Повышенные неподтверждённые Sandbox rules и «Чистая неделя» автоматически не включались.

Локальная проверка требует свежих assets перед Django integration tests:

```sh
npm run build --prefix frontend
npm test --prefix frontend
node --test traineediary/tests/js/*.test.*
# Укажите отдельные локальные DB settings и временный STATIC_ROOT.
# На них: collectstatic --noinput, migrate, check, test --noinput,
# makemigrations --check --dry-run, migrate --check.
# process_achievement_events — операция записи; запускать только на выбранной локальной БД.
```

Задача №14 завершена. Commit, push, merge и деплой не выполнялись. Следующая задача не начата.
