# CONTRIBUTING

Этот файл описывает правила разработки Ticket Sandbox: как добавлять задания, менять архитектуру, писать проверки и готовить проект к ревью.

## Общий принцип

Ticket Sandbox должен оставаться простым и предсказуемым:

- стажёр решает техническую задачу в Docker-окружении;
- `check.sh` проверяет технический результат;
- наставник проверяет только ответ клиенту;
- история проверок и решений сохраняется;
- прогресс стажёра не должен ломаться случайными действиями;
- фоновые операции должны иметь понятные статусы и recovery;
- внешние уведомления и мониторинг не должны ломать основной сценарий.

Любые изменения лучше делать маленькими шагами и сразу закрывать тестами.

## Базовые архитектурные правила

### Не возвращать очередь trainee

В проекте нет отдельной очереди `trainee`.

Стажёр считается претендующим на L1 и работает в очереди:

```text
l1
```

Кандидат работает в отдельной очереди:

```text
candidate
```

Текущие очереди:

```text
candidate
l1
l2
admin
```

### Task.queue обязателен

Каждое задание должно быть привязано к очереди через:

```python
Task.queue
```

Заданий без очереди быть не должно.

Поле `queue_name` удалено и не должно возвращаться.

Путь к Docker-окружению строится через очередь и slug задачи:

```text
training_tasks/<queue_slug>/<task_slug>
```

### Наставник определяется через User.is_staff

Для доступа к mentor dashboard используется стандартное поле Django:

```python
User.is_staff
```

Отдельный флаг наставника в `TraineeProfile` не нужен.

### Не смешивать техническую проверку и проверку текста

Техническую часть проверяет только:

```text
check.sh
```

Наставник проверяет только:

```text
ответ клиенту
```

Если `check.sh` прошёл успешно и `technical_passed_at` заполнен, техническая часть считается выполненной.

Если наставник отправил ответ на доработку, стажёр правит только текст.

Docker-контейнер и `check.sh` повторно запускать не нужно.

### Не показывать стажёру инфраструктурный шум

Стажёр должен видеть результат проверки, а не внутренние детали очистки инфраструктуры.

В `last_check_output` после успешной автопроверки должен оставаться вывод `check.sh`.

Сообщения вида:

```text
Контейнер терминала удалён
Контейнер задания удалён
```

нужно писать в application logs, а не показывать стажёру.

### task.json — источник правды для задания

Задания синхронизируются командой:

```bash
python manage.py sync_training_tasks
```

Постоянные правки задания нужно делать в файле:

```text
training_tasks/<queue_slug>/<task_slug>/task.json
```

Django admin можно использовать для просмотра, фильтров и быстрых массовых действий. Но при следующем deploy/CD команда `sync_training_tasks` снова применит значения из файлов.

Перед применением изменений:

```bash
python manage.py sync_training_tasks --dry-run --strict
```

Потом:

```bash
python manage.py sync_training_tasks --strict
```

### Не делать Basic Auth для ttyd

Basic Auth для ttyd в проекте не используем.

Актуальное решение:

```text
nginx /terminal/<attempt_id>/<port>/
  ↓
auth_request /_terminal_auth
  ↓
Django /terminal-auth/
  ↓
204 разрешает proxy_pass на 127.0.0.1:<port>
401/403 запрещает доступ
```

Правила:

- не открывать ttyd-порты наружу;
- не возвращать Basic Auth для ttyd;
- проверять доступ через `/terminal-auth/`;
- разрешать доступ владельцу попытки или наставнику с `User.is_staff=True`;
- логировать открытие терминала стажёра наставником через `mentor_terminal_access`.

## Background lifecycle

Запуск окружения, перезапуск окружения и автопроверка выполняются через background thread.

### Environment status

Для окружения используется:

```python
TaskAttempt.environment_status
```

Значения:

```text
idle
starting
ready
restarting
error
```

Время:

```python
environment_started_at
environment_finished_at
```

Правила:

- start не должен перезаписывать `starting` или `restarting`;
- restart не должен перезаписывать `starting` или `restarting`;
- restart должен сбрасывать `finished_at`, `check_status`, check timestamps и `stuck_reason`;
- при ошибке окружение переводится в `error`, а попытка — в `failed`.

### Check status

Для автопроверки используется:

```python
TaskAttempt.check_status
```

Значения:

```text
idle
running
passed
failed
error
```

Время:

```python
check_started_at
check_finished_at
```

Правила:

- запуск автопроверки должен быть атомарным;
- двойной клик не должен запускать две проверки;
- пока `check_status=running`, повторный запуск запрещён;
- если окружение `starting`, `restarting` или `error`, автопроверку запускать нельзя.

### Watchdog

Фоновые thread-и могут оборваться при рестарте gunicorn/сервиса.

Для recovery есть команда:

```bash
python manage.py detect_stuck_attempts
```

Dry-run:

```bash
python manage.py detect_stuck_attempts --dry-run
```

Команда должна:

- находить старые `environment_status=starting/restarting`;
- находить старые `check_status=running`;
- переводить их в `error`;
- ставить `TaskAttempt.status=failed`;
- заполнять `stuck_reason`;
- не трогать технически пройденные попытки;
- не маркировать одну попытку дважды;
- отправлять Telegram-уведомление наставникам, если Telegram настроен.

Не завязывай бизнес-логику на текст `last_check_output`. Для зависших попыток есть явное поле:

```python
TaskAttempt.stuck_reason
```

Значения:

```text
""
environment
check
```

### Cron

Пример watchdog cron:

```text
deploy/cron/detect_stuck_attempts.example
```

Рекомендуемый интервал:

```cron
*/5 * * * * cd /opt/ticket-sandbox && /opt/ticket-sandbox/.venv/bin/python manage.py detect_stuck_attempts >> /var/log/ticket-sandbox/detect_stuck_attempts.log 2>&1
```

## Уведомления

### Telegram

Telegram-уведомления — побочный эффект, а не часть критического пути.

Правила:

- если `TELEGRAM_BOT_TOKEN` или `TELEGRAM_CHAT_ID` не заданы, уведомления молча выключены;
- если Telegram API недоступен, пользовательский сценарий не должен падать;
- ошибки отправки нужно логировать через `sandbox.telegram`;
- реальные HTTP-запросы в тестах должны мокироваться;
- бизнес-тексты уведомлений держим в `sandbox/services/notifications.py`;
- низкоуровневую отправку держим в `sandbox/services/telegram.py`;
- уведомления после изменения состояния лучше отправлять через `transaction.on_commit(...)`.

### Sentry

Sentry включается только при наличии:

```env
SENTRY_DSN=
```

Правила:

- не хардкодить DSN в коде;
- `send_default_pii=False`;
- performance tracing по умолчанию выключен через `SENTRY_TRACES_SAMPLE_RATE=0`;
- ошибки background-wrapper-ов отправлять через `capture_exception(error)`;
- в тестах мокировать `capture_exception`.

## Management commands

В проекте есть команды:

```bash
python manage.py build_task_images
python manage.py cleanup_task_containers
python manage.py sync_training_tasks
python manage.py detect_stuck_attempts
```

`build_task_images` собирает Docker-образы заданий.

`cleanup_task_containers` удаляет старые контейнеры тренажёра.

`sync_training_tasks` создаёт и обновляет задания в БД из `training_tasks`.

`detect_stuck_attempts` восстанавливает зависшие фоновые статусы.

Если меняешь Docker-логику, background lifecycle, структуру `training_tasks`, `task.json` или management command — добавляй/обновляй тесты.

## Тесты

Тесты лежат в директории:

```text
sandbox/tests/
```

Тесты не должны запускать реальные Docker-контейнеры.

Docker-вызовы нужно мокировать.

Внешние HTTP-вызовы, включая Telegram API, тоже нужно мокировать.

Sentry `capture_exception` в тестах тоже мокируется.

### Точечные проверки

```bash
make test-terminal
make test-actions
make test-docker
make test-dashboards
python manage.py test sandbox.tests.test_environment_service
python manage.py test sandbox.tests.test_checks_service
python manage.py test sandbox.tests.test_management_commands
python manage.py test sandbox.tests.test_telegram_notifications
```

Что проверяют группы:

```text
make test-terminal   # terminal auth и terminal gateway
make test-actions    # действия с попытками, check/restart/rerun
make test-docker     # Docker service и management-команды
make test-dashboards # дашборды стажёра и наставника
```

Полный `make validate` нужен после пачки изменений, перед ревью, архивом или деплоем.

Во время разработки не нужно гонять полный набор после каждой мелкой правки. Достаточно запускать тесты по изменённой области.

## Когда добавлять тесты

Тесты нужно добавлять или обновлять, если меняется:

- модель;
- миграция;
- доступ к очередям;
- доступ к mentor dashboard;
- логика открытия следующей задачи;
- запуск задания;
- перезапуск задания;
- автопроверка;
- background lifecycle;
- polling статусов;
- watchdog;
- `stuck_reason`;
- создание `CheckRun`;
- ручная проверка наставником;
- прогресс по очереди;
- баннер комментариев наставника;
- бейдж «Ждут проверки»;
- Telegram-уведомления;
- Sentry capture;
- healthcheck endpoint;
- Docker service;
- management command.

## Локальная проверка

Базовая проверка Django:

```bash
python manage.py check
```

Проверка миграций:

```bash
python manage.py makemigrations --check --dry-run
```

Запуск всех тестов приложения:

```bash
python manage.py test sandbox
```

Полная проверка:

```bash
make validate
```

`make validate` должен проходить успешно перед тем, как отдавать проект на ревью, собирать архив или деплоить.

## Работа с миграциями

Если меняешь модели, нужно создать миграцию:

```bash
python manage.py makemigrations
```

После этого проверить:

```bash
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py test sandbox
```

Не стоит вручную править уже применённые миграции, если проектом уже пользовались.

## Работа со статикой

Исходные CSS и JS лежат в:

```text
static/
```

Собранная статика может появляться в:

```text
staticfiles/
```

В проекте используется `ManifestStaticFilesStorage`, поэтому тесты настроены так, чтобы не требовать обязательный `collectstatic`.

## Что не добавлять в архив

Перед отправкой проекта на ревью не нужно включать:

```text
.venv
__pycache__
*.pyc
db.sqlite3
media
.DS_Store
.env
staticfiles
```

Лучший вариант архива из git:

```bash
git archive \
  --format=tar.gz \
  --prefix=ticket-sandbox/ \
  -o ../ticket-sandbox-review-$(date +%F).tar.gz \
  HEAD
```

Так в архив попадут только файлы, которые реально находятся в git.

## Перед push

Обычно порядок такой:

```bash
git status --short
git diff --stat
```

Точечные тесты по изменённой области.

Потом:

```bash
make validate
```

Если всё зелёное:

```bash
git add ...
git commit -m "Meaningful commit message"
git push origin main
```
