# Ticket Sandbox

Ticket Sandbox — учебная тикетница для практики стажёров технической поддержки.

Проект имитирует работу с клиентским обращением: стажёр открывает учебный тикет, запускает изолированное Docker-окружение, диагностирует проблему в веб-терминале, исправляет техническую часть и готовит ответ клиенту.

README — это короткая входная точка в проект. Подробности вынесены в отдельные документы:

- `ARCHITECTURE.md` — как устроены Django, Docker, terminal gateway, автопроверка, ручная проверка, background lifecycle и watchdog.
- `CONTRIBUTING.md` — правила разработки, добавления заданий, тестов и ревью.
- `STAGING_CHECKLIST.md` — ручная проверка staging после деплоя.
- `CHANGELOG.md` — история крупных изменений по неделям.

## Что умеет проект

- Авторизация пользователей через Django.
- Профили пользователей с уровнями `candidate`, `l1`, `l2`, `admin`.
- Очереди учебных заданий.
- Последовательное открытие заданий внутри очереди.
- Учебные тикеты с сообщением клиента.
- Отдельная попытка `TaskAttempt` для каждого пользователя и задания.
- Docker task-контейнер под конкретную попытку.
- Веб-терминал через ttyd.
- Безопасный terminal gateway через nginx `auth_request`.
- Доступ к терминалу только владельцу попытки или наставнику с `User.is_staff=True`.
- Автопроверка технической части через `check.sh`.
- История автопроверок через `CheckRun`.
- Ручная проверка ответа клиенту наставником.
- Разделение технической сдачи и проверки текста ответа.
- Повторные тренировочные попытки после технической сдачи.
- Read-only режим исторических попыток.
- Dashboard стажёра.
- Dashboard наставника со статистикой, фильтрами, бейджами и ручной проверкой.
- Telegram-уведомления наставникам.
- Background lifecycle для запуска окружения, перезапуска окружения и автопроверки.
- Polling статусов на фронте.
- Watchdog для зависших фоновых операций.
- Sentry для ошибок Django и background-задач.
- Healthcheck endpoint `/healthz/`.
- GitHub Actions CI/CD и staging deploy.

## Главная логика

Тренажёр разделяет две части работы:

```text
check.sh проверяет техническую часть
наставник проверяет только ответ клиенту
```

Если `check.sh` прошёл успешно, у попытки заполняется:

```python
TaskAttempt.technical_passed_at
```

После этого техническая часть считается выполненной. Если наставник отправил ответ на доработку, стажёр правит только текст. Docker-контейнер и `check.sh` повторно запускать не нужно.

Если задание не требует ручной проверки:

```python
Task.requires_manual_review = False
```

то после успешной технической проверки задание сразу считается принятым.

## Очереди и уровни

В проекте нет отдельной очереди `trainee`.

Стажёр считается претендующим на L1 и решает задачи из очереди `l1`.

Текущая схема доступа:

| Уровень пользователя | Доступные очереди |
|---|---|
| `candidate` | `candidate` |
| `l1` | `l1` |
| `l2` | `l1`, `l2` |
| `admin` | `candidate`, `l1`, `l2`, `admin` |

Наставник определяется через стандартное поле Django:

```python
User.is_staff
```

Отдельное поле `is_mentor` не используется.

## Основной workflow

1. Стажёр открывает dashboard.
2. Выбирает доступное задание.
3. Нажимает «Начать работу».
4. Django переводит окружение в `starting` и запускает создание контейнеров в background thread.
5. Frontend polling показывает текущий статус окружения.
6. После готовности появляется терминал.
7. Стажёр исправляет проблему.
8. Нажимает автопроверку.
9. Django переводит проверку в `running` и запускает `check.sh` в background thread.
10. Frontend polling показывает результат проверки.
11. При успехе task/terminal-контейнеры удаляются.
12. Если ручная проверка нужна, стажёр пишет ответ клиенту и внутренний комментарий.
13. Наставник принимает ответ или отправляет его на доработку.
14. Стажёр видит комментарий наставника и при необходимости правит только текст.

## Структура проекта

```text
ticket-sandbox/
├── .github/             # GitHub Actions workflow
├── config/              # настройки Django
├── deploy/              # nginx, cron и примеры деплоя
├── sandbox/             # основное приложение
├── static/              # CSS и JS
├── templates/           # HTML-шаблоны
├── training_tasks/      # Docker-задания
├── terminal/            # окружение ttyd
├── STAGING_CHECKLIST.md # чеклист ручной проверки staging
├── docker-compose.yml
├── Makefile
├── manage.py
└── requirements.txt
```

## Локальный запуск

### 1. Создать виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Запустить PostgreSQL

```bash
docker compose up -d db
```

### 4. Применить миграции

```bash
python manage.py migrate
```

### 5. Создать суперпользователя

```bash
python manage.py createsuperuser
```

### 6. Запустить Django

```bash
python manage.py runserver
```

Django dev server будет доступен по адресу:

```text
http://127.0.0.1:8000/
```

## Локальный terminal gateway

Если включен terminal gateway:

```env
TERMINAL_GATEWAY_ENABLED=true
```

то терминал нужно открывать через локальный nginx gateway, а не напрямую через `127.0.0.1:8000`.

Во втором терминале:

```bash
make nginx-test
make nginx-start
```

После этого проект открывается здесь:

```text
http://localhost:8081/
```

Полезные команды:

```bash
make nginx-reload
make nginx-stop
make nginx-logs
```

## Переменные окружения

Базовый пример есть в `.env.example`.

Ключевые переменные:

```env
DEBUG=True
SECRET_KEY=dev-secret-key
ALLOWED_HOSTS=127.0.0.1,localhost
EXTERNAL_HOST=localhost

DB_ENGINE=django.db.backends.postgresql
DB_NAME=ticket_sandbox
DB_USER=ticket_sandbox_user
DB_PASSWORD=ticket_sandbox_password
DB_HOST=127.0.0.1
DB_PORT=5432

TERMINAL_GATEWAY_ENABLED=true
CHECK_TASK_TIMEOUT_SECONDS=60
LOG_LEVEL=INFO

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

SENTRY_DSN=
SENTRY_ENVIRONMENT=local
SENTRY_RELEASE=
SENTRY_TRACES_SAMPLE_RATE=0
```

Если Telegram-переменные не заданы, уведомления выключены и не мешают работе проекта.

Если `SENTRY_DSN` не задан, Sentry не инициализируется.

## Как добавить новое задание

Задания лежат в `training_tasks/<queue_slug>/<task_slug>/`.

Минимальная структура:

```text
training_tasks/l1/nginx-not-starting/
├── Dockerfile
├── task.json
└── files/
    └── check.sh
```

`task.json` — источник правды для учебного задания. Постоянные правки названия, текста тикета, клиента, приоритета, порядка, активности и ручной проверки нужно делать в `task.json`, а не руками в Django admin.

Пример:

```json
{
  "title": "Nginx не запускается после изменения конфига",
  "ticket_title": "Сайт перестал открываться после правки nginx",
  "client_name": "Алексей Морозов",
  "client_email": "a.morozov@example.com",
  "description": "Здравствуйте. После изменения конфигурации сайт перестал открываться.",
  "priority": "medium",
  "order": 1,
  "requires_manual_review": true,
  "is_active": true
}
```

Проверить синхронизацию:

```bash
python manage.py sync_training_tasks --dry-run --strict
```

Применить:

```bash
python manage.py sync_training_tasks --strict
```

Собрать Docker-образы заданий:

```bash
python manage.py build_task_images
```

## Management commands

```bash
python manage.py sync_training_tasks --dry-run --strict
python manage.py build_task_images
python manage.py cleanup_task_containers --dry-run
python manage.py detect_stuck_attempts --dry-run
```

`cleanup_task_containers` очищает старые незавершённые контейнеры.

`detect_stuck_attempts` переводит зависшие background-операции в `error`, чтобы попытки не оставались навсегда в `starting`, `restarting` или `running`.

## Cron-примеры

Примеры cron-команд лежат в:

```text
deploy/cron/
```

Рекомендуемые задачи:

```text
cleanup_task_containers
```

```text
detect_stuck_attempts
```

Watchdog обычно запускается каждые 5 минут, а дефолтный порог зависания — 10 минут.

## Makefile

Основные команды:

```bash
make up
make migrate
make run
make build-images
make cleanup
make sync-check
make test-terminal
make test-actions
make test-docker
make test-dashboards
make validate
make nginx-test
make nginx-start
make nginx-reload
make nginx-stop
make nginx-logs
```

Во время разработки обычно достаточно точечных тестов по изменённой области.

Перед ревью, архивом или деплоем нужно запускать:

```bash
make validate
```

## CI/CD

GitHub Actions выполняет проверки и staging deploy.

CI проверяет:

```text
makemigrations --check --dry-run
check
check --deploy
migrate
sync_training_tasks --dry-run --strict
test sandbox
```

Staging deploy выполняет:

```text
pull latest code
install dependencies
migrate
sync_training_tasks --strict
build_task_images
collectstatic
restart service
smoke-check /
smoke-check /healthz/
smoke-check /admin/login/
```

## Проверка staging

После деплоя staging нужно пройти ручной сценарий по:

```text
STAGING_CHECKLIST.md
```

Минимально проверить:

- вход стажёром;
- вход наставником;
- запуск окружения;
- терминал в iframe;
- автопроверку;
- ручную проверку ответа;
- повторную тренировочную попытку;
- историческую попытку read-only;
- watchdog cron;
- Sentry/логи;
- cleanup контейнеров.
