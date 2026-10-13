# Схемы этапов TraineeDiary

## Поведение

Существующие адаптации получают `stage_scheme=legacy`. Новые адаптации, включая внутренние переводы, создаются с `stage_scheme=unified`. Обычное изменение карточки или drag-and-drop не переводит сотрудника между схемами.

| Новая внешняя адаптация | Slug | Min / max, календарные дни | Вес |
|---|---|---:|---:|
| Программа обучения | training-program | 10 / 14 | 35% |
| Задания в Ticket Sandbox | sandbox-candidate | 1 / 2 | 5% |
| В тикетах с проверками | with-review | 15 / 20 | 35% |
| Проверки по желанию | optional-review | 5 / 10 | 10% |
| Без проверок | no-review | 10 / 10 | 15% |
| Выход с ИС | done | 0 / 0 | 0% |

Внутренний перевод использует только последние четыре этапа. ИС остаётся 90 дней для внешнего найма и 30 для внутреннего перевода. Прогресс внутренних сотрудников нормируется на их применимые веса (60%). Числовые `order` общих этапов сохранены: 1, 5, 7, 8, 9, 10; это порядок, а не номера станций Roadmap.

Пять исторических учебных этапов имеют `catalog_scope=legacy`, новая программа — `unified`, остальные — `shared`. Их PK, slug, названия, сроки, веса, цвета и активность миграция не меняет. Для новых адаптаций новые подписи Sandbox и «Проверки по желанию» задаются при отображении, без переименования исторических записей.

`services/stages.py` определяет доступные цели переходов, следующий этап и набор этапов для расчётов и отображения. Неактивный текущий этап остаётся в прогрессе и Kanban; Gantt дополнительно сохраняет все фактически посещённые этапы. История показывает исходные названия, даты, автора и комментарий. Недоступные этапы не становятся разрешёнными целями перехода из-за присутствия в истории.

Kanban разделён на две доски по схеме. Карточки и колонки сохраняют реальные ID этапов; внутренние сотрудники могут переходить только на применимые им этапы. Проверка выполняется в JavaScript, серверном обработчике и `move_to_stage`. Staff может управлять любым сотрудником; сессии и CSRF сохранены.

Ожидание 10/14 дней используется для планирования и риска. Readiness программы требует подтверждения наставника независимо от прошедшего времени. Завершение подтверждается существующим ручным переходом сотрудником с `is_staff=True`, с датой и комментарием в `StageHistory`. Метрики Sandbox и технический зачёт не менялись.

## Миграции и preflight

`0006_stage_schemes` добавляет поля, первоначально помечая адаптации как legacy. `0007_classify_stage_catalog` проверяет замороженный контракт справочника **до записи данных**, классифицирует этапы, создаёт программу с новым PK и устанавливает default unified для новых карточек. На SQLite и PostgreSQL миграция выполняется транзакционно. Переходы, даты, текущие этапы, исходы ИС, недельные метрики и комментарии не переписываются.

Проверка останавливает миграцию при неизвестных slug, несовпадении названия, порядка, группы, применимости, сроков или весов; также при конфликтующей программе или неполном историческом справочнике у существующих адаптаций. В ошибке указаны PK, slug и отличающиеся поля. Цвета и `is_active` допустимы как настройки, они сохраняются. Нестандартный каталог требует отдельного согласованного сопоставления; не исправляйте его массовым seed.

`check_stage_catalog --before-migration` читает модели состояния 0005 и работает до добавления новых колонок. После миграции `check_stage_catalog` также проверяет scope. `seed_stages` создаёт только недостающие шесть этапов unified, не меняет существующие параметры и не включает неактивные этапы обратно. Прежде чем создавать карточки на пустой БД, выполните seed.

`trainee_stages.json` — историческая фикстура для специально подготовленных локальных данных, а не новый bootstrap. Она больше не содержит фиксированных PK: natural key — slug. Это предотвращает замену новой программы историческим этапом при загрузке. **Не загружайте фикстуру поверх действующей базы**: явный `loaddata` может восстановить справочные параметры. Для обычной установки используется seed.

Миграция данных намеренно необратима: удаление признака схемы после появления новых адаптаций смешает программы. Откат требует восстановления согласованного резервного снимка всей БД и соответствующего кода. Если 0007 остановилась, 0006 может уже быть применена; текущие этапы и история при этом сохранены. Разберите отчёт и повторите миграцию только после согласования справочника.

## Контракт будущего приложения roadmap

Этот раздел задаёт будущую архитектуру; приложение, таблицы подтверждений и API сейчас не создаются. Это согласованная граница текущей задачи.

Восемь станций React сохраняются. `training-program` соответствует 01, Sandbox — 02, независимые модули `escalation-map` и `ticket-analysis` — 03 и 04. Работа с тикетами и завершение — 05–08. Модули 03/04 не добавляются в `TraineeStage`, Kanban, веса дневника или `StageHistory`; переход из Sandbox в работу с тикетами сейчас не получает нового блокирующего условия.

Будущее приложение `roadmap` владеет отдельным журналом подтверждений, например `ModuleConfirmationEvent`:

| Поле контракта | Назначение |
|---|---|
| participant / adaptation | Пользователь и конкретная адаптация; допустима ссылка на TraineeJourney, без FK на TraineeStage/StageHistory |
| module_code | Стабильный код escalation-map либо ticket-analysis |
| action | confirmed / revoked; отзыв создаёт новое событие |
| occurred_at / recorded_at | Время прохождения и время получения подтверждения |
| source_type | manual либо automatic |
| provider | manual-staff или имя доверенного Django-приложения |
| provider_event_id | Идентификатор события источника; ключ идемпотентности вместе с provider |
| actor | Автор ручного решения; только is_staff=True, для системного события может отсутствовать |
| note / evidence_reference | Комментарий и ссылка на подтверждающий результат без копирования бизнес-данных учебного приложения |

Ручной сервис обязан проверять staff на сервере, использовать Django-сессию и CSRF в будущей форме и добавлять событие в транзакции. Автоматические события принимаются только от доверенных backend-сервисов соответствующих учебных приложений; frontend не выбирает provider и не подделывает источник. Журнал сохраняет автора и источник, события не перезаписываются и не удаляются при смене провайдера.

Текущий статус модуля — проекция подтверждений и отзывов; приоритет и разрешение конфликтов источников потребуется согласовать перед реализацией. После появления автоматического провайдера новые события записываются в этот же журнал. Ручные подтверждения и история TraineeDiary сохраняются. Для подключения автоматического источника не потребуется миграция истории дневника.

Применимость модулей для внутренних переводов задаётся отдельной политикой Roadmap. Отсутствие подтверждения не означает провал, и внутренний перевод не обязан проходить все станции внешнего найма. Данные демонстрационного React Roadmap пока не связаны с этим контрактом.

## Изолированная локальная проверка

Не запускайте следующие команды с настройками реальной базы. Переменные явно выбирают временную SQLite; production-конфигурация не меняется.

```sh
export DEBUG=True
export DB_ENGINE=django.db.backends.sqlite3
export DB_NAME="$(mktemp -t training-stage-audit)"
export SENTRY_DSN=''
.venv/bin/python manage.py migrate traineediary 0005 --noinput
.venv/bin/python manage.py check_stage_catalog --before-migration
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py seed_stages
.venv/bin/python manage.py seed_stages
.venv/bin/python manage.py check_stage_catalog
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py migrate --check
.venv/bin/python manage.py test --noinput
node --test traineediary/tests/js/kanban.test.cjs
```

Тесты миграций сами создают отдельное соединение SQLite в памяти, разворачивают схему 0005 и исторические записи и сравнивают все исходные поля после 0007. Проверяются FK, текущие этапы, история, метрики, исход ИС, отказ preflight и запрет опасного отката. Функциональные тесты проверяют обе схемы, внутренний перевод, расчёты, ручное подтверждение, формы, Kanban, staff и CSRF.

Для ручной проверки создайте staff на этой же временной БД через `createsuperuser`, затем `runserver`: откройте `/diary/trainees/`, создайте новую адаптацию и подтвердите программу переходом в Sandbox. Для доступа без авторизации ожидается redirect на login, без staff — 403. Исторические примеры для этого сценария создавайте явно со схемой legacy на изолированной БД, не импортируйте реальные персональные данные.

Анонимизированная PostgreSQL-копия не предоставлена, миграции на PostgreSQL не выполнялись. SQLite не заменяет проверку PostgreSQL: перед отдельным согласованным выпуском требуется прогон на обезличенной копии, проверка preflight, блокировок и снимка данных до/после. Проверка реальных активных сотрудников и их нестандартных параметров остаётся обязанностью владельца этой копии. В этой задаче реальные базы не читались и не изменялись.

## Результаты проверки

Проверено 13 октября 2026 на изолированной SQLite, Python 3.13 / Django 6.0.5:

| Проверка | Результат |
|---|---|
| Полный `manage.py test --noinput` | 675 тестов, OK (395 секунд) |
| Тесты схем, миграций и seed после окончательных правок | 26 тестов, OK |
| `node --test traineediary/tests/js/kanban.test.cjs` | 4 теста, OK |
| `node --check static/js/kanban.js` | OK |
| `manage.py check` | 0 ошибок |
| `makemigrations --check --dry-run` | No changes detected |
| Схема 0005 → preflight → все миграции на временной БД | OK |
| Двукратный seed | Создано 5 недостающих общих этапов; затем 0 изменений, всего 6 |
| Preflight после миграции / `migrate --check` | OK |
| `git diff --check` | OK |

Реальные базы не читались и не изменялись. PostgreSQL не проверен: обезличенная копия недоступна. Ветка сохранена `feature/roadmap-react`; commit, push и деплой не выполнялись. React, Sandbox, модели наград, CI/CD и production-конфигурация не изменялись.

## Файлы текущего изменения

Изменены:

- [CHANGELOG.md](CHANGELOG.md)
- [README.md](README.md)
- [static/js/kanban.js](static/js/kanban.js)
- [traineediary/admin.py](traineediary/admin.py)
- [traineediary/fixtures/trainee_stages.json](traineediary/fixtures/trainee_stages.json)
- [traineediary/forms/trainee_management.py](traineediary/forms/trainee_management.py)
- [traineediary/management/commands/seed_stages.py](traineediary/management/commands/seed_stages.py)
- [traineediary/models.py](traineediary/models.py)
- [traineediary/services/assessment.py](traineediary/services/assessment.py)
- [traineediary/services/integrity.py](traineediary/services/integrity.py)
- [traineediary/templates/traineediary/_kanban_board_fragment.html](traineediary/templates/traineediary/_kanban_board_fragment.html)
- [traineediary/templates/traineediary/complete_trainee.html](traineediary/templates/traineediary/complete_trainee.html)
- [traineediary/templates/traineediary/dashboard.html](traineediary/templates/traineediary/dashboard.html)
- [traineediary/templates/traineediary/edit_trainee.html](traineediary/templates/traineediary/edit_trainee.html)
- [traineediary/templates/traineediary/trainee_detail.html](traineediary/templates/traineediary/trainee_detail.html)
- [traineediary/templates/traineediary/weekly_metrics.html](traineediary/templates/traineediary/weekly_metrics.html)
- [traineediary/tests/test_journey.py](traineediary/tests/test_journey.py)
- [traineediary/tests/test_seed_stages.py](traineediary/tests/test_seed_stages.py)
- [traineediary/tests/test_trainee_detail.py](traineediary/tests/test_trainee_detail.py)
- [traineediary/views/dashboard.py](traineediary/views/dashboard.py)
- [traineediary/views/kanban.py](traineediary/views/kanban.py)
- [traineediary/views/trainee_detail.py](traineediary/views/trainee_detail.py)

Созданы:

- [TRAINEEDIARY_STAGE_SCHEMES.md](TRAINEEDIARY_STAGE_SCHEMES.md)
- [traineediary/management/commands/check_stage_catalog.py](traineediary/management/commands/check_stage_catalog.py)
- [traineediary/migrations/0006_stage_schemes.py](traineediary/migrations/0006_stage_schemes.py)
- [traineediary/migrations/0007_classify_stage_catalog.py](traineediary/migrations/0007_classify_stage_catalog.py)
- [traineediary/services/stage_catalog.py](traineediary/services/stage_catalog.py)
- [traineediary/services/stages.py](traineediary/services/stages.py)
- [traineediary/templates/traineediary/_kanban_scheme_fragment.html](traineediary/templates/traineediary/_kanban_scheme_fragment.html)
- [traineediary/tests/js/kanban.test.cjs](traineediary/tests/js/kanban.test.cjs)
- [traineediary/tests/test_stage_migrations.py](traineediary/tests/test_stage_migrations.py)
- [traineediary/tests/test_stage_schemes.py](traineediary/tests/test_stage_schemes.py)
