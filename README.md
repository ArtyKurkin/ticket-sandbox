# Training Platform

Training Platform — внутренняя платформа обучения и оценки сотрудников технической поддержки.

Проект объединяет несколько Django-приложений в одной системе:

- `sandbox` — Ticket Sandbox: практические технические задания в изолированных Docker-окружениях;
- `traineediary` — дневник адаптации стажёров и внутренних переходов;
- `assessment` — оценка знаний сотрудников: банк вопросов, навыки, темы, экзамены и результаты.

Все приложения используют общую Django-авторизацию и одну PostgreSQL-базу.

README — короткая входная точка в проект. Более подробная техническая документация:

- `ARCHITECTURE.md` — архитектура Django, Docker, terminal gateway, Celery lifecycle и автопроверок;
- `CONTRIBUTING.md` — правила разработки, добавления заданий, тестов;
- `STAGING_CHECKLIST.md` — ручная проверка staging после деплоя;
- `CHANGELOG.md` — история крупных изменений.

---

## Что входит в платформу

### Ticket Sandbox — `sandbox`

Учебная тикетница для практики технической поддержки.

Стажёр получает обращение клиента, запускает изолированное Docker-окружение, диагностирует проблему через веб-терминал, исправляет техническую часть и готовит ответ клиенту.

Основные возможности:

- очереди `candidate`, `l1`, `l2`, `admin`;
- последовательное открытие заданий;
- отдельная `TaskAttempt` для каждого пользователя и задания;
- Docker task-контейнер под конкретную попытку;
- веб-терминал через `ttyd`;
- terminal gateway через nginx `auth_request`;
- доступ к терминалу только владельцу попытки или наставнику;
- автопроверка технической части через `check.sh`;
- история автопроверок через `CheckRun`;
- ручная проверка ответа клиенту;
- повторные тренировочные попытки;
- read-only режим исторических попыток;
- dashboard стажёра;
- dashboard наставника;
- Telegram-уведомления;
- polling статусов окружения и проверки;
- watchdog зависших background-операций;
- Celery + Redis для запуска окружений, restart и `check.sh`.

Наставник определяется стандартным Django-полем:

```python
User.is_staff
```

Отдельного `is_mentor` нет.

### Дневник стажёра — `traineediary`

Внутреннее приложение для сопровождения адаптации.

Основные возможности:

- канбан сотрудников по этапам;
- новые сотрудники и внутренние переходы;
- история движения между этапами;
- недельные показатели качества и скорости;
- карточка сотрудника;
- контроль длительности испытательного периода;
- фиксация рисков и зон внимания;
- завершение испытательного периода с решением и комментарием.

Основные сущности:

- `TraineeStage` — этап адаптации;
- `TraineeJourney` — путь сотрудника;
- `StageHistory` — история этапов;
- `WeeklyMetric` — недельные показатели.

Дневник доступен по адресу:

```text
/diary/
```

и предназначен для пользователей с `User.is_staff=True`.

Справочник этапов создаётся командой:

```bash
python manage.py seed_stages
```

### Оценка знаний — `assessment`

Приложение для оценки знаний сотрудников.

В нём хранится и развивается отдельный банк оценочных материалов:

- темы;
- навыки;
- семейства вопросов;
- вопросы;
- варианты ответов;
- matching-задания;
- ordering-задания;
- диагностические блоки;
- blueprint экзамена;
- квоты навыков;
- назначения;
- попытки;
- снимки вопросов на момент экзамена;
- ответы;
- результаты;
- профили поддержки.

`assessment` использует ту же PostgreSQL-базу и Django users, что `sandbox` и `traineediary`.

Это важно при backup/migration: резервная копия должна включать всю БД, а не только таблицы `sandbox_*`.

---

## Общая архитектура

Текущая staging/production-схема контейнерного runtime:

```text
Browser
  |
  v
Host nginx :443
TLS / Let's Encrypt
  |
  v
127.0.0.1:8080
  |
  v
Docker nginx gateway
  |
  +---------------------> Django / Gunicorn (web)
  |                           |
  |                           +----> PostgreSQL
  |                           |
  |                           +----> Redis
  |                                      |
  |                                      v
  |                                 Celery worker
  |                                      |
  |                                      v
  |                                 Docker daemon
  |
  +---------------------> ttyd terminal container
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

Дополнительно Ticket Sandbox динамически создаёт:

```text
task container
terminal container
```

Task-контейнер содержит учебную проблему.

Terminal-контейнер содержит `ttyd` и подключается к `training-platform-runtime`. В Docker network режиме отдельный host-порт для ttyd не публикуется.

Production/staging используют:

```env
TERMINAL_GATEWAY_ENABLED=true
TERMINAL_NETWORK_MODE=docker_network
TERMINAL_DOCKER_NETWORK=training-platform-runtime
```

Terminal URL в этом режиме:

```text
/terminal/<attempt_id>/
```

Gateway обращается к terminal-контейнеру через Docker network и перед проксированием проверяет доступ через Django `terminal-auth`.

---

## Background-задачи: Celery + Redis

Запуск окружения, restart и техническая автопроверка больше не выполняются через `threading.Thread` внутри Gunicorn.

Текущий поток:

```text
Django web
   |
   v
Redis
   |
   v
Celery worker
   |
   +----> start environment
   +----> restart environment
   +----> run check.sh
```

Зарегистрированные задачи:

```text
sandbox.start_environment
sandbox.restart_environment
sandbox.run_attempt_check
```

Тестовая задача `sandbox.celery_ping` используется для проверки Celery-инфраструктуры.

Celery result backend сейчас не используется. Состояние пользовательской операции хранится в PostgreSQL через поля `TaskAttempt`.

Redis используется как broker.

Watchdog `detect_stuck_attempts` сохраняется: он нужен для recovery, если worker, Docker-операция или процесс выполнения прервались и попытка слишком долго остаётся в `starting`, `restarting` или `running`.

---

## Docker access и безопасность

Контейнеры приложения запускаются от non-root пользователя:

```text
uid=10001(app)
gid=10001(app)
```

`training-platform-web` не получает `/var/run/docker.sock`.

Docker socket монтируется в `worker`, потому что именно Celery worker создаёт, перезапускает и проверяет учебные контейнеры.

Динамический terminal-контейнер также может получать Docker socket для `docker exec` в task-контейнер в рамках terminal runtime.

Для доступа non-root worker к Docker socket используется дополнительная группа:

```env
DOCKER_GID=<gid /var/run/docker.sock>
```

GID зависит от Docker host и не должен хардкодиться одинаково для всех серверов.

Проверить значение на Linux:

```bash
stat -c '%g' /var/run/docker.sock
```

Примеры из проверенных окружений:

```text
Docker Desktop на Mac: 0
текущий staging:       113
```

Перед deploy выполняется:

```text
deploy/check_docker_socket_gid.sh
```

Скрипт сравнивает `DOCKER_GID` из `.env.prod` с реальным GID socket и останавливает deploy при несовпадении.

В Dockerfile используется:

```dockerfile
COPY --chown=app:app . .
USER app
```

Это необходимо, чтобы приложение корректно запускалось non-root пользователем и `manage.py` был доступен внутри image.

---

## Главная логика Ticket Sandbox

Тренажёр разделяет техническую часть и текст ответа:

```text
check.sh
  |
  v
техническая проверка

наставник
  |
  v
проверка ответа клиенту
```

После успешного `check.sh` у попытки фиксируется:

```python
TaskAttempt.technical_passed_at
```

После этого техническая часть считается выполненной.

Если наставник отправляет ответ на доработку, стажёр исправляет только текст — повторно поднимать контейнер и запускать `check.sh` не требуется.

Если:

```python
Task.requires_manual_review = False
```

то после успешной технической проверки задание принимается автоматически.

---

## Очереди Ticket Sandbox

| Уровень | Очереди |
|---|---|
| `candidate` | `candidate` |
| `l1` | `l1` |
| `l2` | `l1`, `l2` |
| `admin` | `candidate`, `l1`, `l2`, `admin` |

Отдельной очереди `trainee` нет.

---

## Workflow учебного задания

1. Стажёр открывает dashboard.
2. Выбирает доступное задание.
3. Нажимает «Начать работу».
4. Django переводит окружение в `starting`.
5. Django ставит `sandbox.start_environment` в Redis.
6. Celery worker создаёт task-контейнер и terminal-контейнер.
7. Frontend polling ждёт `environment_status=ready`.
8. Стажёру становится доступен терминал.
9. Стажёр диагностирует и исправляет проблему.
10. При restart Django ставит `sandbox.restart_environment` в очередь.
11. При автопроверке Django атомарно переводит `check_status` в `running` и ставит `sandbox.run_attempt_check` в очередь.
12. Worker запускает `check.sh`.
13. Frontend polling показывает результат.
14. После успешной технической сдачи временные контейнеры удаляются.
15. При необходимости стажёр пишет ответ клиенту и внутренний комментарий.
16. Наставник принимает ответ или отправляет его на доработку.

---

## Структура проекта

```text
training-platform/
├── .github/
│   └── workflows/
│       └── ci.yml
├── assessment/
├── config/
│   └── celery.py
├── deploy/
│   ├── nginx/
│   ├── cron/
│   └── check_docker_socket_gid.sh
├── sandbox/
│   ├── services/
│   └── tasks.py
├── traineediary/
├── static/
├── templates/
├── terminal/
├── training_tasks/
├── .env.example
├── .env.prod.example
├── Dockerfile
├── docker-compose.yml
├── docker-compose.local.yml
├── docker-compose.prod.yml
├── Makefile
├── manage.py
└── requirements.txt
```

Часть внутренних имён всё ещё содержит legacy-префикс `ticket-sandbox`, например Docker images заданий и некоторые service identifiers. Это не означает, что проект состоит только из Ticket Sandbox — постепенно их можно переименовать в `training-platform`.

---

## Локальный запуск

### Django на host + инфраструктура в Docker

Создать окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Поднять PostgreSQL и Redis:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  up -d db redis
```

Применить миграции:

```bash
python manage.py migrate
```

Запустить Django:

```bash
python manage.py runserver
```

В этом режиме `CELERY_BROKER_URL` по умолчанию может использовать локально опубликованный Redis:

```text
redis://127.0.0.1:6379/0
```

Worker можно запускать через Compose.

### Полный локальный Compose

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  up -d --build
```

Основной вход через gateway:

```text
http://localhost:8081/
```

Прямой Django:

```text
http://localhost:8000/
```

Терминалы нужно проверять через gateway `:8081`, а не через прямой Gunicorn `:8000`.

---

## Переменные окружения

Production-пример:

```text
.env.prod.example
```

Основные переменные:

```env
DEBUG=False
SECRET_KEY=...
ALLOWED_HOSTS=...
CSRF_TRUSTED_ORIGINS=...
EXTERNAL_HOST=...

DB_ENGINE=django.db.backends.postgresql
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_HOST=db
DB_PORT=5432

CELERY_BROKER_URL=redis://redis:6379/0

TERMINAL_GATEWAY_ENABLED=true
TERMINAL_NETWORK_MODE=docker_network
TERMINAL_DOCKER_NETWORK=training-platform-runtime

# Должен совпадать с:
# stat -c '%g' /var/run/docker.sock
DOCKER_GID=...

CHECK_TASK_TIMEOUT_SECONDS=60

LOG_LEVEL=INFO
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

SENTRY_DSN=
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=
SENTRY_TRACES_SAMPLE_RATE=0

TIME_ZONE=Europe/Moscow
TASK_CONTAINER_TZ=MSK-3
```

`.env.prod` содержит секреты и не должен попадать в Git.

---

## Добавление задания Ticket Sandbox

Задания:

```text
training_tasks/<queue_slug>/<task_slug>/
```

Минимальный пример:

```text
training_tasks/l1/nginx-not-starting/
├── Dockerfile
├── task.json
└── files/
    └── check.sh
```

`task.json` — источник правды для постоянной конфигурации задания.

Проверить синхронизацию:

```bash
python manage.py sync_training_tasks --dry-run --strict
```

Применить:

```bash
python manage.py sync_training_tasks --strict
```

Сборка task images требует Docker socket. В контейнерном runtime её нужно выполнять через `worker`:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps worker \
  python manage.py build_task_images
```

---

## Management commands

Основные команды:

```bash
python manage.py sync_training_tasks --dry-run --strict
python manage.py sync_training_tasks --strict
python manage.py build_task_images
python manage.py cleanup_task_containers --dry-run
python manage.py cleanup_task_containers
python manage.py detect_stuck_attempts --dry-run
python manage.py detect_stuck_attempts
python manage.py seed_stages
python manage.py check_trainee_integrity
```

В Docker production/staging:

- команды без Docker API можно выполнять через `web`;
- `build_task_images` и `cleanup_task_containers` нужно выполнять через `worker`, потому что у `web` нет Docker socket.

Пример:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps worker \
  python manage.py cleanup_task_containers --dry-run
```

---

## Docker Compose

Основные сервисы:

```text
db
redis
web
worker
gateway
```

Конфигурации:

```text
docker-compose.yml
docker-compose.local.yml
docker-compose.prod.yml
```

Проверить production-конфигурацию:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  config --quiet
```

Запустить stack:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  up -d --wait
```

Проверить:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  ps
```

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

Django endpoint:

```text
/healthz/
```

`/healthz/` является liveness-check приложения и не выполняет отдельный SQL-запрос к PostgreSQL.

Celery worker healthcheck выполняет `celery inspect ping` для конкретного worker node.

---

## CI/CD

Workflow:

```text
.github/workflows/ci.yml
```

### CI

GitHub Actions использует Python 3.13 и выполняет:

```text
makemigrations --check --dry-run
python manage.py check
python manage.py check --deploy
migrate
sync_training_tasks --dry-run --strict
python manage.py test sandbox traineediary assessment
```

### Deploy staging

Deploy выполняется после успешных тестов при push в `main`.

Актуальная схема:

```text
fetch exact target commit
        |
        v
check Docker socket GID
        |
        v
docker compose config
        |
        v
build web + worker images
        |
        v
start/wait PostgreSQL
        |
        v
migrate via web
        |
        v
sync_training_tasks via web
        |
        v
build_task_images via worker
        |
        v
start/wait web + worker
        |
        v
force-recreate gateway
        |
        v
show compose status
        |
        v
HTTPS smoke-check:
  /healthz/
  /
  /admin/login/
```

Gateway пересоздаётся после `web`, чтобы nginx не оставался привязан к старому IP пересозданного web-контейнера и не отдавал `502`.

Dependencies и static входят в Docker image. На сервере больше не нужны отдельные:

```text
pip install
collectstatic
systemctl restart ticket-sandbox
```

---

## Staging

Текущий staging работает через Docker Compose.

Основные контейнеры:

```text
training-platform-db
training-platform-redis
training-platform-web
training-platform-worker
training-platform-gateway
```

Минимальная проверка:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  ps
```

Ожидается `healthy` для основных сервисов.

Дополнительно проверить:

```bash
docker exec training-platform-web id
docker exec training-platform-worker id
```

`web` и `worker` должны работать как `app`, а не root.

Проверка изоляции web:

```bash
docker exec training-platform-web \
  sh -c 'test ! -S /var/run/docker.sock && echo "web: no docker.sock"'
```

Проверка Docker API из worker:

```bash
docker exec training-platform-worker python -c "
import docker
print(docker.from_env().ping())
"
```

Полный ручной сценарий описан в:

```text
STAGING_CHECKLIST.md
```

---

## Backup данных

Все приложения используют одну PostgreSQL-базу.

Backup должен содержать всю БД:

```text
sandbox_*
traineediary_*
assessment_*
auth_*
django_*
```

Для миграций между PostgreSQL удобно использовать:

```bash
pg_dump --format=custom ...
pg_restore ...
```

Файлы заданий Ticket Sandbox в `training_tasks/` не находятся в PostgreSQL и должны ехать вместе с Git-кодом.

---

## Наблюдаемость

Поддерживаются:

- Django/application logs;
- Celery worker logs;
- Docker logs;
- Sentry;
- `/healthz/`;
- Docker healthchecks;
- watchdog зависших операций.

Логи основных контейнеров:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  logs --tail 100 web worker gateway
```

Если `SENTRY_DSN` пустой, Sentry не инициализируется.

Если Telegram credentials пустые, уведомления отключены.

---

## Ближайшие инфраструктурные задачи

1. Добавить retry/time-limit правила для Celery tasks там, где это действительно нужно.
2. Адаптировать и проверить watchdog с учётом Celery lifecycle.
3. Подготовить и выполнить перенос staging-схемы на production-сервер.
4. После периода наблюдения удалить legacy systemd/host deployment.
5. Проверить резервное копирование и rollback уже на production-схеме.
6. При необходимости добавить отдельный scheduler (`celery beat`) для периодических задач.
7. Постепенно переименовать legacy `ticket-sandbox` identifiers в `training-platform`.

---

## Тесты

Полный прогон:

```bash
python manage.py test
```

Основной набор:

```text
sandbox
traineediary
assessment
```

Во время разработки обычно достаточно точечных тестов изменённой области.

Перед merge/deploy рекомендуется полный прогон.

---

## Коротко

Training Platform объединяет:

```text
Training Platform
├── Ticket Sandbox
├── Дневник стажёра
└── Оценка знаний
```

Runtime уже переведён на Docker Compose.

Долгие Docker-операции Ticket Sandbox выполняются через Redis + Celery worker.

`web` работает без Docker socket, а Docker-доступ вынесен в worker. Контейнеры приложения запускаются от non-root пользователя `app`.
