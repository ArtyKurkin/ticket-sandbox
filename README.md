# Training Platform

Training Platform — внутренняя платформа обучения и оценки сотрудников технической поддержки.

Проект объединяет несколько Django-приложений в одной системе:

- `sandbox` — Ticket Sandbox: практические технические задания в изолированных Docker-окружениях;
- `traineediary` — дневник адаптации стажёров и внутренних переходов;
- `assessment` — оценка знаний сотрудников: банк вопросов, навыки, темы, экзамены и результаты.

Все приложения используют общую Django-авторизацию и одну PostgreSQL-базу.

README — короткая входная точка в проект. Более подробная техническая документация вынесена отдельно:

- `ARCHITECTURE.md` — архитектура Django, Docker, terminal gateway, lifecycle окружений и автопроверок;
- `CONTRIBUTING.md` — правила разработки, добавления заданий, тестов и ревью;
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
- watchdog зависших background-операций.

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

Текущая production/staging-схема:

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
  +---------------------> Django / Gunicorn
  |                         |
  |                         v
  |                     PostgreSQL
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
web      Django + Gunicorn
gateway  nginx
```

Дополнительно Ticket Sandbox динамически создаёт:

```text
task container
terminal container
```

Task-контейнер содержит учебную проблему.

Terminal-контейнер содержит `ttyd`, имеет доступ к Docker socket и выполняет `docker exec` в task-контейнер.

Для Docker production-режима отдельные host-порты ttyd не используются:

```env
TERMINAL_NETWORK_MODE=docker_network
TERMINAL_DOCKER_NETWORK=training-platform-runtime
```

Gateway обращается к terminal-контейнеру внутри Docker network.

---

## Background-задачи

На текущем этапе запуск окружения, restart и автопроверка выполняются background threads внутри Django-процесса.

Есть отдельный watchdog:

```bash
python manage.py detect_stuck_attempts
```

который находит зависшие состояния и не даёт попыткам навсегда оставаться в `starting`, `restarting` или `running`.

### Следующий инфраструктурный этап: Celery + Redis

Celery и Redis ещё не являются частью production runtime.

План:

```text
Django web
   |
   +----> Redis
            |
            v
       Celery worker
            |
            +----> start environment
            +----> restart environment
            +----> run check.sh
            +----> другие долгие background-задачи
```

Цель — убрать долгие операции из процесса Gunicorn и сделать background lifecycle устойчивым к restart/deploy web-контейнера.

После внедрения в Docker Compose должны появиться как минимум:

```text
redis
worker
```

При необходимости позже можно добавить отдельный scheduler (`celery beat`), если появятся периодические Celery-задачи.

До завершения этого этапа текущие background threads и watchdog остаются рабочим механизмом.

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

Текущая схема:

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
5. В background запускается создание task-контейнера и terminal-контейнера.
6. Frontend polling ждёт `environment_status=ready`.
7. Стажёру становится доступен терминал.
8. Стажёр диагностирует и исправляет проблему.
9. Запускается автопроверка.
10. `check.sh` проверяет техническую часть.
11. Frontend polling показывает результат.
12. После успешной технической сдачи временные контейнеры удаляются.
13. При необходимости стажёр пишет ответ клиенту и внутренний комментарий.
14. Наставник принимает ответ или отправляет его на доработку.

---

## Структура проекта

```text
training-platform/
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── assessment/             # оценка знаний
├── config/                 # Django settings / urls / wsgi
├── deploy/                 # nginx, cron, systemd examples
├── sandbox/                # Ticket Sandbox
├── traineediary/           # адаптация и дневник стажёров
├── static/
├── templates/
├── terminal/               # ttyd image
├── training_tasks/         # Docker-задания Ticket Sandbox
│
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

### Вариант с Django на host и PostgreSQL в Docker

Создать окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Поднять локальную PostgreSQL:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  up -d db
```

Применить миграции:

```bash
python manage.py migrate
```

При необходимости:

```bash
python manage.py createsuperuser
```

Запустить Django:

```bash
python manage.py runserver
```

Приложение:

```text
http://127.0.0.1:8000/
```

### Local terminal gateway

Если:

```env
TERMINAL_GATEWAY_ENABLED=true
```

для полноценной проверки terminal gateway удобнее использовать локальный nginx:

```bash
make nginx-test
make nginx-start
```

После этого:

```text
http://localhost:8081/
```

Полезные команды:

```bash
make nginx-reload
make nginx-stop
make nginx-logs
```

---

## Переменные окружения

Dev-пример:

```text
.env.example
```

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

TERMINAL_GATEWAY_ENABLED=true
TERMINAL_NETWORK_MODE=docker_network
TERMINAL_DOCKER_NETWORK=training-platform-runtime

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

Собрать images:

```bash
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

`cleanup_task_containers` очищает старые незавершённые runtime-окружения и переводит их в состояние для повторного запуска.

`detect_stuck_attempts` обрабатывает зависшие background-состояния.

`check_trainee_integrity` проверяет целостность данных дневника без изменения БД.

---

## Docker Compose

Общая конфигурация:

```text
docker-compose.yml
```

Локальные overrides:

```text
docker-compose.local.yml
```

Production overrides:

```text
docker-compose.prod.yml
```

Проверить production-конфигурацию:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  config
```

Запустить production stack:

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

## Healthcheck

Endpoint:

```text
/healthz/
```

Используется Docker healthcheck и CI/CD smoke-check.

Сейчас endpoint является liveness-check приложения и не выполняет отдельный SQL-запрос к PostgreSQL.

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

Схема:

```text
fetch target commit
        |
        v
docker compose config
        |
        v
build web image
        |
        v
start/wait PostgreSQL
        |
        v
migrate
        |
        v
sync_training_tasks --strict
        |
        v
build_task_images
        |
        v
docker compose up web gateway --wait
        |
        v
HTTPS smoke-check
```

Dependencies и static входят в Docker image, поэтому на сервере больше не выполняются отдельные:

```text
pip install
collectstatic
systemctl restart ticket-sandbox
```

---

## Staging

Текущий staging работает через Docker Compose.

Схема внешнего трафика:

```text
Internet
   |
   v
host nginx :443
   |
   v
127.0.0.1:8080
   |
   v
training-platform-gateway
   |
   +----> training-platform-web
   |
   +----> terminal containers
```

Основные контейнеры:

```text
training-platform-db
training-platform-web
training-platform-gateway
```

Проверка:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  ps
```

После deploy минимально проверить:

- `/healthz/`;
- вход пользователем;
- Ticket Sandbox;
- запуск окружения;
- terminal HTTP + WebSocket;
- автопроверку;
- Дневник стажёра;
- Оценку знаний;
- admin.

Полный ручной сценарий:

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
- Docker logs;
- Sentry;
- `/healthz/`;
- Docker healthchecks;
- watchdog background-операций.

Если `SENTRY_DSN` пустой, Sentry не инициализируется.

Если Telegram credentials пустые, уведомления отключены.

---

## Ближайшие инфраструктурные задачи

1. Добавить Redis в Docker Compose.
2. Добавить Celery worker.
3. Перенести создание/restart окружения из background threads в Celery.
4. Перенести автопроверку `check.sh` в Celery.
5. Добавить retry/time-limit правила для Celery tasks.
6. Адаптировать watchdog под Celery lifecycle.
7. Добавить healthcheck Redis и Celery worker.
8. Добавить Celery/Redis в CI/staging checks.
9. После периода наблюдения удалить legacy systemd/host deployment.
10. Постепенно переименовать legacy `ticket-sandbox` identifiers в `training-platform`.

---

## Тесты

Полный прогон:

```bash
python manage.py test
```

Текущий основной набор включает:

```text
sandbox
traineediary
assessment
```

Во время разработки обычно достаточно точечных тестов изменённой области.

Перед merge/deploy рекомендуется полный прогон.

---

## Коротко

Training Platform — это уже не только Ticket Sandbox.

Сейчас проект объединяет:

```text
Training Platform
├── Ticket Sandbox
├── Дневник стажёра
└── Оценка знаний
```

Текущий runtime уже переведён на Docker Compose.

Следующий инфраструктурный этап — Redis + Celery и перенос долгих background-операций из Gunicorn-процесса в отдельный worker.
