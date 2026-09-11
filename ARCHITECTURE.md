# ARCHITECTURE

Этот файл описывает архитектуру Training Platform с акцентом на Ticket Sandbox: Django, Redis, Celery, Docker-контейнеры, terminal gateway, автопроверку, ручную проверку наставником, watchdog и CI/CD.

## Общая идея

Training Platform объединяет несколько внутренних Django-приложений:

- `sandbox` — Ticket Sandbox;
- `traineediary` — сопровождение адаптации;
- `assessment` — оценка знаний.

Ticket Sandbox имитирует полный цикл работы с клиентским обращением:

1. Стажёр открывает учебный тикет.
2. Запускает изолированное Docker-окружение.
3. Диагностирует проблему через веб-терминал.
4. Исправляет техническую проблему.
5. Отправляет техническую часть на автопроверку.
6. После успешной технической сдачи пишет ответ клиенту и внутренний комментарий, если заданию нужна ручная проверка.
7. При необходимости получает ручную проверку ответа от наставника.

Главное архитектурное разделение:

```text
check.sh проверяет техническую часть
наставник проверяет только ответ клиенту
```

Если техническая часть уже успешно пройдена, доработка текста наставником не требует повторного запуска Docker-контейнера и `check.sh`.

---

## Runtime-архитектура

```text
Browser
  |
  v
Host nginx :443
  |
  v
127.0.0.1:8080
  |
  v
Docker nginx gateway
  |
  +----------------------> Django / Gunicorn (web)
  |                            |
  |                            +------> PostgreSQL
  |                            |
  |                            +------> Redis
  |                                        |
  |                                        v
  |                                   Celery worker
  |                                        |
  |                                        v
  |                                   Docker daemon
  |                                        |
  |                                        +--> task container
  |                                        +--> terminal container
  |
  +----------------------> terminal container / ttyd
                               |
                               v
                           docker exec
                               |
                               v
                         task container
```

Основные Compose-сервисы:

```text
db       PostgreSQL 16
redis    Redis 7
web      Django + Gunicorn
worker   Celery
gateway  nginx
```

Все основные сервисы подключены к Docker network:

```text
training-platform-runtime
```

Task-контейнеры по-прежнему запускаются в обычной Docker bridge-сети, а terminal-контейнер подключается к `training-platform-runtime`, чтобы gateway мог обращаться к нему по Docker DNS.

---

## Разделение ответственности web и worker

### web

`training-platform-web` отвечает за:

- HTTP request/response;
- авторизацию;
- dashboard;
- изменение бизнес-состояния в PostgreSQL;
- постановку фоновых задач в Redis;
- terminal auth;
- polling endpoints.

`web` не имеет `/var/run/docker.sock` и не должен напрямую создавать, удалять или проверять Docker-контейнеры.

### worker

`training-platform-worker` отвечает за длительные Docker-операции:

- запуск окружения;
- restart окружения;
- запуск `check.sh`;
- Docker management commands, когда им нужен Docker API.

Worker получает `/var/run/docker.sock` и работает через Python Docker SDK.

### Redis

Redis используется как broker для Celery.

Celery result backend сейчас отключён. Пользовательское состояние хранится в PostgreSQL, а не в Celery result backend.

---

## Non-root контейнеры

`web` и `worker` запускаются от пользователя:

```text
uid=10001(app)
gid=10001(app)
```

В Dockerfile код приложения копируется так:

```dockerfile
COPY --chown=app:app . .
```

и runtime переключается на:

```dockerfile
USER app
```

Это исключает запуск Django/Gunicorn и Celery от root.

### Доступ worker к Docker socket

Docker socket на Linux обычно имеет права вида:

```text
srw-rw---- root:<docker_gid> /var/run/docker.sock
```

Worker получает дополнительную группу через:

```yaml
group_add:
  - "${DOCKER_GID:?DOCKER_GID must match /var/run/docker.sock GID}"
```

`DOCKER_GID` задаётся в env конкретного Docker host.

Проверить значение:

```bash
stat -c '%g' /var/run/docker.sock
```

Проверенные значения:

```text
Mac / Docker Desktop: 0
staging Linux:        113
```

Перед deploy выполняется `deploy/check_docker_socket_gid.sh`. Если значение в `.env.prod` не совпадает с реальным GID socket, deploy останавливается до запуска приложения.

---

## Основной поток Ticket Sandbox

```text
Пользователь
  ↓
Django dashboard
  ↓
TaskAttempt
  ↓
Redis
  ↓
Celery worker
  ↓
Docker task + terminal containers
  ↓
check.sh
  ↓
CheckRun
  ↓
TaskAttempt.technical_passed_at
  ↓
ручная проверка ответа наставником, если требуется
```

---

## Основные сущности

### Queue

Очередь учебных заданий.

Используемые очереди:

```text
candidate
l1
l2
admin
```

Отдельной очереди `trainee` нет.

### TraineeProfile

Хранит уровень пользователя:

```text
candidate
l1
l2
admin
```

Наставник определяется через:

```python
User.is_staff
```

### Task

Учебное задание.

Задание принадлежит очереди через обязательное поле:

```python
Task.queue
```

Путь к Docker-окружению:

```text
training_tasks/<queue_slug>/<task_slug>
```

Ключевое поле ручной проверки:

```python
Task.requires_manual_review
```

### TaskAttempt

`TaskAttempt` хранит состояние работы пользователя:

- `status`;
- `environment_status`;
- `check_status`;
- `attempts_count`;
- `restart_count`;
- container/terminal runtime fields;
- `attempt_number`;
- `is_current`;
- `last_check_output`;
- `technical_passed_at`;
- mentor feedback/decision;
- timestamps;
- `stuck_reason`.

Ключевой критерий технической сдачи:

```python
TaskAttempt.technical_passed_at is not None
```

### CheckRun

Каждый запуск `check.sh` создаёт отдельную запись `CheckRun`.

`CheckRun` хранит историю запусков, а `TaskAttempt.last_check_output` — только последний результат для интерфейса.

---

## Доступы к очередям

```text
candidate → candidate
l1        → l1
l2        → l1, l2
admin     → candidate, l1, l2, admin
```

Наставники и администраторы с `User.is_staff=True` попадают в mentor dashboard.

---

## Статусы попытки

Основной lifecycle:

```text
new
 ↓
in_progress
 ↓
on_review / failed / passed
```

`technical_passed_at` хранится отдельно и не должен зависеть от ручной проверки текста.

---

## Background lifecycle окружения

Запуск и restart выполняются через Celery.

Поле состояния:

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

Поля времени:

```python
environment_started_at
environment_finished_at
```

### Start

Когда пользователь нажимает «Начать работу»:

1. Django атомарно переводит попытку в `environment_status=starting`.
2. Django вызывает `start_environment_in_background()`.
3. Wrapper ставит Celery task `sandbox.start_environment` в Redis.
4. Celery worker получает `attempt_id`.
5. Worker загружает `TaskAttempt` из PostgreSQL.
6. Worker создаёт task-контейнер.
7. Worker создаёт terminal-контейнер.
8. Worker ждёт готовность terminal.
9. Попытка переводится в `environment_status=ready`.
10. Frontend polling показывает терминал пользователю.

### Restart

Restart работает через задачу:

```text
sandbox.restart_environment
```

При restart:

- старые task/terminal-контейнеры удаляются;
- создаются новые;
- увеличивается `restart_count`;
- сбрасываются `finished_at`, check state/timestamps и `stuck_reason`;
- окружение снова переходит в `ready`.

### Ошибки

При ошибке background wrapper:

- исключение отправляется в Sentry через `capture_exception`, если Sentry настроен;
- `environment_status` переводится в `error`;
- `TaskAttempt.status` переводится в `failed`;
- заполняется понятный `last_check_output`.

---

## Background lifecycle автопроверки

Автопроверка выполняется через Celery task:

```text
sandbox.run_attempt_check
```

Поле состояния:

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

Алгоритм:

1. Django атомарно вызывает `try_mark_attempt_check_running()`.
2. Только один запрос может перевести попытку в `running`.
3. Увеличивается `attempts_count`.
4. Django ставит Celery task в Redis.
5. Worker получает `attempt_id` и `user_id`.
6. Worker запускает `check.sh` через Docker API.
7. Создаётся `CheckRun`.
8. Обновляются `check_status`, `last_check_output`, `check_finished_at`.
9. При успехе заполняется `technical_passed_at`.
10. При успешной технической сдаче временные task/terminal-контейнеры удаляются.

Защита от двойного клика сохраняется: при `check_status=running` вторая задача не ставится в очередь.

Celery task считается успешно выполненной, даже если пользовательский `check.sh` вернул exit code `1`: это нормальный бизнес-результат проверки, а не ошибка Celery-инфраструктуры.

---

## Frontend polling

Polling используется для:

- `environment_status`;
- `check_status`.

Пользователь не ждёт длительный HTTP-запрос и видит промежуточные состояния:

```text
Окружение запускается...
Окружение перезапускается...
Проверка выполняется...
```

---

## Watchdog зависших операций

`detect_stuck_attempts` сохраняется и после перехода на Celery.

Теперь его задача — восстановить состояние БД, если Celery worker, Docker daemon или конкретная операция прервались до финального обновления `TaskAttempt`.

Команда:

```bash
python manage.py detect_stuck_attempts
```

Dry-run:

```bash
python manage.py detect_stuck_attempts --dry-run
```

Она ищет старые состояния:

```text
environment_status = starting / restarting
check_status = running
```

и переводит зависшую попытку в `error`, заполняя `stuck_reason`.

Watchdog не должен определять зависание по тексту `last_check_output`.

---

## Terminal gateway

Production/staging работают в режиме:

```env
TERMINAL_GATEWAY_ENABLED=true
TERMINAL_NETWORK_MODE=docker_network
TERMINAL_DOCKER_NETWORK=training-platform-runtime
```

Terminal URL:

```text
/terminal/<attempt_id>/
```

Схема:

```text
Browser
  ↓
nginx gateway /terminal/<attempt_id>/
  ↓
auth_request /_terminal_auth
  ↓
Django /terminal-auth/
  ↓
X-Terminal-Upstream: <terminal-container>:7681
  ↓
nginx proxy / WebSocket
  ↓
ttyd
```

Django проверяет:

- пользователь авторизован;
- попытка существует;
- пользователь — владелец попытки или `User.is_staff=True`;
- terminal runtime заполнен;
- попытка доступна пользователю.

Результаты auth:

```text
204 → доступ разрешён
401 → пользователь не авторизован
403 → доступ запрещён
```

В Docker network режиме `terminal_port` может быть `NULL`, а отдельный диапазон host-портов `20000–30000` не требуется.

Код сохраняет legacy-совместимость с `host_port`, но staging/новая production-схема используют `docker_network`.

---

## Автопроверка и вывод для стажёра

После успешного `check.sh`:

- создаётся `CheckRun`;
- заполняется `technical_passed_at`;
- `check_status` становится `passed`;
- task/terminal-контейнеры удаляются;
- runtime-поля очищаются;
- стажёру показывается только полезный вывод `check.sh`.

Инфраструктурный cleanup логируется, но не показывается стажёру.

---

## Ручная проверка наставником

```text
check.sh успешен
  ↓
technical_passed_at заполнен
  ↓
Task.requires_manual_review=True
  ↓
client_answer + trainee_report
  ↓
on_review
  ↓
mentor review
```

При доработке ответа техническая сдача не сбрасывается.

---

## Повторные тренировочные попытки

После успешной технической сдачи restart текущей попытки блокируется.

Для повторного прохождения создаётся новая тренировочная попытка:

- `attempt_number > 1`;
- новая попытка становится `is_current=True`;
- предыдущая становится исторической;
- прогресс не откатывается;
- дополнительная попытка не считается зачётной для mentor dashboard.

---

## Cleanup контейнеров

Команда:

```bash
python manage.py cleanup_task_containers
```

Dry-run:

```bash
python manage.py cleanup_task_containers --dry-run
```

Так как команда использует Docker API, в контейнерной production/staging-схеме её нужно запускать через `worker`:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps worker \
  python manage.py cleanup_task_containers --dry-run
```

---

## Telegram

Telegram — побочный эффект, а не критический путь.

Если credentials не заданы, уведомления выключены.

Если Telegram API недоступен, основной пользовательский сценарий не должен падать.

---

## Sentry

Sentry включается только при наличии:

```env
SENTRY_DSN=
```

Ошибки Celery/background wrappers отправляются через `capture_exception(error)` в тех местах, где они обрабатываются вручную.

---

## Healthchecks

Используются healthchecks для:

```text
db
redis
web
worker
gateway
```

Django:

```text
/healthz/
```

Celery worker проверяется через `celery inspect ping`.

---

## CI/CD

GitHub Actions выполняет CI и staging deploy.

### CI

```text
makemigrations --check --dry-run
python manage.py check
python manage.py check --deploy
migrate
sync_training_tasks --dry-run --strict
python manage.py test sandbox traineediary assessment
```

### Staging deploy

```text
fetch exact target commit
  ↓
check Docker socket GID
  ↓
docker compose config
  ↓
build web + worker
  ↓
start/wait db
  ↓
migrate via web
  ↓
sync_training_tasks via web
  ↓
build_task_images via worker
  ↓
start/wait web + worker
  ↓
force-recreate gateway
  ↓
compose ps
  ↓
HTTPS smoke-check
```

Gateway пересоздаётся после web, чтобы nginx не использовал старый IP пересозданного контейнера.

---

## Management commands и Docker-доступ

Команды, которым Docker API не нужен, можно запускать через `web`.

Команды, которым нужен Docker daemon, запускаются через `worker`:

```text
build_task_images
cleanup_task_containers
```

`web` не должен получать Docker socket ради management command.

---

## Текущие ограничения

- Redis используется как единичный broker без отдельной HA-схемы.
- Celery result backend отключён.
- Для start/restart/check пока нет отдельных retry/time-limit политик Celery сверх существующих application/Docker timeout-механизмов.
- Watchdog по-прежнему основан на состояниях и timestamps в PostgreSQL.
- Docker socket остаётся высокопривилегированным интерфейсом; он изолирован от web, но worker и terminal runtime требуют аккуратного контроля.
- Часть внутренних идентификаторов всё ещё использует legacy-префикс `ticket-sandbox`.

---

## Следующие архитектурные шаги

1. Подготовить production-сервер по той же Compose-схеме, что staging.
2. Перед production deploy определить `DOCKER_GID` на новом host.
3. Проверить backup/restore всей PostgreSQL-базы.
4. Добавить осознанные retry/time-limit правила для Celery tasks.
5. Проверить watchdog при остановке/restart worker во время задачи.
6. После периода наблюдения удалить legacy systemd/host deployment.
7. При необходимости добавить `celery beat` для периодических задач.
8. Постепенно переименовать legacy `ticket-sandbox` identifiers.
