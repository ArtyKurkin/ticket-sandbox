# Управление достижениями в TraineeDiary

14 октября 2026. Задача №13, ветка `feature/roadmap-react`.

В карточку адаптации добавлена компактная вкладка «Достижения» для `is_staff`: каталог конкретного сотрудника, текущий максимальный уровень, ручная выдача, повышение, отзыв и реальные события истории. Действия используют существующие session/CSRF API и grants service. Новых моделей, миграций и правил выдачи нет.

## Размещение в карточке

Изучены `traineediary/views/trainee_detail.py`, `traineediary/templates/traineediary/trainee_detail.html`, `_base.html`, маршруты Diary, общие `main.css`/`app.js`, существующий Kanban JS, оба отчёта задач 11–12 и реальные `achievements/views.py`, `urls.py`, `services/grants.py`.

Ранее вкладок не было. После общей шапки сотрудника располагались сведения об адаптации, комментарий наставника, оценка готовности, Sandbox, недельные графики, обратная связь, диаграмма этапов и раскрываемая история. Сама карточка уже закрыта серверной проверкой `is_staff`.

Минимальное изменение — две ссылки «Адаптация» / «Достижения» под общей шапкой. Существующие блоки помещены в одну секцию «Адаптация» с прежним содержимым. Заголовок, риск и верхние действия сотрудника остаются общими. Выбранная вкладка отражается в `?tab=achievements`; работают прямой URL, Back/Forward и ссылки без JavaScript. Переключение с JavaScript не перезагружает страницу. Графики, расчёты, переходы этапов и формы адаптации не изменены.

Раздел использует существующие цвета и кнопки Diary, компактные металлические значки 36 px и одну строку на определение. Полная React-галерея не переносилась. Скрипты — обычные ES modules в Django static, как самостоятельное дополнение к серверной карточке; новых зависимостей и entry points Vite нет. Проверены обе темы и мобильная ширина 390 px.

## Файлы

Изменены четыре существовавших на начало задачи файла:

| Файл | Изменение |
|---|---|
| [traineediary/views/trainee_detail.py](traineediary/views/trainee_detail.py) | Только bootstrap URLs, `user_id`, отображаемое имя и выбранная вкладка в context |
| [traineediary/templates/traineediary/trainee_detail.html](traineediary/templates/traineediary/trainee_detail.html) | Навигация, обёртка прежнего содержимого, staff include, scoped CSS/JS |
| [achievements/views.py](achievements/views.py) | Staff-представление каталога и деталей; автор истории, блокировка auto regrant |
| [achievements/urls.py](achievements/urls.py) | Новый GET деталей конкретного сотрудника |

Созданы:

- [traineediary/templates/traineediary/_achievements.html](traineediary/templates/traineediary/_achievements.html) — список, детали и двухэтапная форма решения.
- [static/css/diary-achievements.css](static/css/diary-achievements.css) — изолированные стили.
- [static/js/diary-achievement-api.js](static/js/diary-achievement-api.js) — проверка DTO, GET/POST, неизменяемое тело операции и cursor history.
- [static/js/diary-achievements.js](static/js/diary-achievements.js) — вкладки, формы, диалоги, обновление и обработка ошибок.
- [achievements/tests/test_staff_management.py](achievements/tests/test_staff_management.py) — восемь тестов staff API.
- [traineediary/tests/test_achievement_management.py](traineediary/tests/test_achievement_management.py) — два теста карточки и доступа.
- [traineediary/tests/js/achievements.test.mjs](traineediary/tests/js/achievements.test.mjs) — восемь тестов клиентского контракта и операций.
- Этот отчёт и PNG в [docs/diary-achievement-management](docs/diary-achievement-management).

Сравнение SHA-256 с начальным снимком 697 файлов подтвердило изменение только четырёх перечисленных существующих файлов; отсутствующих файлов нет. Исходники Trophy Room, Roadmap, evaluators, grants service, Sandbox, модели/метрики Diary и прежние отчёты сохранены. Пересборка frontend дала прежние assets. Результаты предыдущих незакоммиченных задач не удалялись.

## Действия наставника

По умолчанию список показывает все применимые определения, а также уже выданные/отозванные награды независимо от применимости. Checkbox дополнительно раскрывает неприменимые. Неизвестная применимость показана явно. Server stats используются без пересчёта на клиенте. Для каждой линейки есть одна строка, активный максимальный металл, статус, реальные даты первой выдачи/повышения и manual/automatic. Отдельно показаны disputed и блокировка auto regrant.

«История» открывает native dialog: описание, активный уровень, даты и реальные grant/upgrade/revoke/evidence_disputed. События выводятся в порядке backend ID, по 50 записей с «Показать ещё». Повторные ID не дублируются. Используется `recorded_at` события, а не время браузера; `occurred_at` остаётся в DTO. Автор — серверные `actor_id` и `actor_name`, для автоматического события показан сервис. Имена являются текущими именами существующих пользователей, а не историческим снимком имени.

«Выдать награду» позволяет выбрать только существующее определение и его допустимые уровни. «Повысить» предлагает только уровни выше активного. Можно сразу выдать платину: это один реальный grant, без синтетических промежуточных медалей. Причина обязательна. Выбранный уровень с выключенным автоматическим evaluator остаётся доступным для явного ручного решения в соответствии с уже существующим backend. Для неприменимой награды показано предупреждение о ручном исключении.

«Отозвать» сначала открывает форму обязательной причины, затем отдельное подтверждение. В предупреждении явно указаны полное снятие активной награды, блокировка последующей автоматической выдачи, сохранение истории и отсутствие восстановления прежнего уровня. После отзыва возможна только явная ручная повторная выдача через существующий сервис; блокировка автоматической выдачи сохраняется.

Диалоги поддерживают Escape, удержание клавиатурного фокуса и возврат фокуса после закрытия. Во время POST кнопки и закрытие блокируются. После успеха читается новый каталог из API без перезагрузки страницы; фокус переходит на «Обновить».

## API и безопасность

| Путь | Использование |
|---|---|
| GET `/api/achievements/users/<user_id>/` | Существующий staff endpoint, дополнен management metadata |
| GET `/api/achievements/users/<user_id>/<public_id>/` | Новый staff endpoint деталей и cursor history |
| POST `/api/achievements/users/<user_id>/<public_id>/grant/` | Существующий grants service, без изменения POST контракта |
| POST `/api/achievements/users/<user_id>/<public_id>/revoke/` | Существующий revoke service, без изменения политики |

`user_id` берётся из владельца journey, а не из `journey_id` или session наставника. GET не запускает evaluator, не создаёт projection и не выдаёт награды; тест проверяет SELECT-only. Новый endpoint использует тот же server-side `api(staff=True)`, session, private/no-store и ownership filter истории.

В staff-представлении секретные определения раскрыты для выбора разрешённого уровня и аудита, включая отозванный секрет. Только защищённые staff endpoints получают эту metadata. `/me/` и персональные details сохраняют прежнее скрытие неполученного/отозванного секрета; новые поля и имя автора туда не добавляются. Обычный пользователь получает 403 на staff GET/POST и на карточку Diary, даже если вручную укажет новую вкладку. Изменений политики staff-прав нет.

При выдаче отправляются `tier`, `reason`, новый `operation_id` и `expected_revision` из прочитанного DTO. При отзыве — те же поля без `tier`. Session cookies: same-origin; POST: JSON и `X-CSRFToken` из существующего серверного csrf input. Каталог и history вставляются через textContent, без HTML из причин/имён. Клиент не создаёт определения, tiers, evidence, provider или даты.

При 409 исходная операция сбрасывается, каталог перечитывается и предлагается проверить действие заново. Автоматического второго POST нет. После сетевой ошибки/таймаута/5xx результат признаётся неопределённым: доступны проверка состояния и явный повтор **исходного неизменяемого тела с тем же operation_id/revision**. Это сохраняет серверную идемпотентность, если первый POST успел коммититься. Одновременная повторная отправка блокируется. Ошибки 400/401/403/404 показывают соответствующее сообщение; истёкшая session даёт ссылку входа. При ошибке загрузки список не заменяется fixtures.

## Скриншоты

Все данные синтетические; ни один скриншот не содержит production сотрудника. Снимки получены настоящим headless Chromium, desktop 1440×1000 и mobile 390×844.

| Вид | Снимок |
|---|---|
| Вкладка, исходный каталог | [desktop.png](docs/diary-achievement-management/desktop.png) |
| Текущие металлы и состояния | [current-desktop.png](docs/diary-achievement-management/current-desktop.png) |
| Мобильная вкладка | [mobile.png](docs/diary-achievement-management/mobile.png), [mobile-current.png](docs/diary-achievement-management/mobile-current.png) |
| Форма выдачи | [grant-form.png](docs/diary-achievement-management/grant-form.png) |
| Подтверждение выдачи | [grant-confirm.png](docs/diary-achievement-management/grant-confirm.png) |
| Форма отзыва | [revoke-form.png](docs/diary-achievement-management/revoke-form.png) |
| Подтверждение отзыва | [revoke-confirm.png](docs/diary-achievement-management/revoke-confirm.png), [mobile-revoke.png](docs/diary-achievement-management/mobile-revoke.png) |
| История grant → upgrade → revoke | [history.png](docs/diary-achievement-management/history.png) |
| Спорное автоматическое доказательство | [disputed-history.png](docs/diary-achievement-management/disputed-history.png) |
| Пагинация реальных 51 событий | [history-pagination.png](docs/diary-achievement-management/history-pagination.png) |
| Конфликт версии | [conflict.png](docs/diary-achievement-management/conflict.png) |
| Потеря ответа после commit | [network-recovery.png](docs/diary-achievement-management/network-recovery.png) |
| Светлая тема | [light-desktop.png](docs/diary-achievement-management/light-desktop.png), [light-grant.png](docs/diary-achievement-management/light-grant.png) |

## Проверки

| Проверка | Результат |
|---|---|
| Django: `traineediary achievements roadmap react_frontend` | **324 теста, OK**, 8 PostgreSQL-specific skips; 163,716 с |
| Окончательные staff API + новые Diary tests | **10 тестов, OK**, включая добавленный сценарий disputed automatic evidence |
| Node: `traineediary/tests/js/*.test.*` | **12/12 OK**, восемь новых и четыре существующих Kanban |
| `npm test --prefix frontend` | **46/46 OK**, Roadmap и Trophy Room regression |
| TypeScript `tsc --noEmit` | OK |
| Vite production build | OK |
| Свежая временная SQLite: migrate | OK |
| Django system check | 0 issues |
| `makemigrations --check --dry-run` | No changes detected |
| `migrate --check` | OK |
| `git diff --check` и SHA-256 исходных файлов | OK |
| Chromium | **37 проверок, OK**, desktop/mobile, dark/light |

Django tests проверяют staff/trainee/session, CSRF, конкретного владельца, бронзу/прямую платину/повышение/отзыв, reason, одну projection, repeated operation, 400/401/403/404/409, реальную историю/авторов/дату/51-событийную пагинацию, disputed, секретную redaction и SELECT-only. Тест карточки сравнивает context существующих метрик/готовности/истории между вкладками и проверяет наличие всех прежних разделов без записей наград.

Chromium выполнил реальные POST выдачи бронзы, jump до платины, отзыв и direct platinum на отдельной линейке. Потеря ответа моделировалась **после настоящего commit**: повтор использовал идентичное тело и оставил одно событие. Для 409 другая операция действительно изменила revision при открытой форме; UI обновился и не отправил второй запрос. Проверены настоящие 51 события и cursor UI, автоматическое disputed evidence, Escape/focus trap, Back, отсутствие горизонтального overflow и размещение мобильных диалогов. 401/403/404/offline состояния интерфейса дополнительно проверены подменой GET response; реальные endpoint permissions отдельно проверены Django и browser trainee session.

Тесты и preview работали только на временных SQLite, созданных специально для задачи. PostgreSQL suite здесь не запускался: grants/concurrency/SQL guards не менялись, восемь таких проверок пропущены SQLite. Результаты прошлой PostgreSQL проверки не выдаются за новый прогон. Рабочая/production БД не подключалась; схемы production не применялись.

## Локальный повтор

```sh
# Изолированная тестовая БД: не использовать production настройки.
DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: SENTRY_DSN='' \
  .venv/bin/python manage.py test traineediary achievements roadmap react_frontend --noinput
node --test traineediary/tests/js/*.test.*
npm test --prefix frontend
npm run typecheck --prefix frontend
npm run build --prefix frontend
DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: SENTRY_DSN='' \
  .venv/bin/python manage.py check
```

Для browser preview создать новую локальную БД, выполнить migrate, завести синтетические staff/employee/journey и открыть карточку employee под staff session. Новые static-файлы при штатном релизе собираются существующим collectstatic; дополнительных Vite entry или зависимостей не требуется. Деплой в этой задаче не выполнялся.

## Ограничения

1. Каталог загружается целиком, как существующий небольшой API; фильтры/поиск большого каталога не добавлены. История серверно paginated по 50.
2. API выдаёт текущие имена пользователей; immutable исторического имени нет. Показанное время истории — фактическая регистрация события, не предположительная дата предметного результата.
3. Флаг disputed и auto regrant block нельзя очистить новым UI. Доступны существующие audited revoke и manual regrant; политика не расширялась.
4. Метаданные неприменимых наград доступны staff для осознанного ручного исключения, которое уже разрешает grants service. Это не включает их автоматические evaluators.
5. Для управления нужен JavaScript; оригинальная адаптация и навигационные ссылки доступны без него. Обновление после действий явное, непрерывного polling других вкладок нет; устаревшая ревизия выявляется сервером.
6. Браузерный preview подтверждает функциональные сценарии на SQLite, не заменяет конкурентные PostgreSQL проверки. Новых locks, audit guards и схем хранения задача не вводит.

Реализация задачи №13 завершена. Commit, push, merge и деплой не выполнялись. Следующая задача не начата.
