# Ticket Sandbox

Ticket Sandbox — учебная тикетница для практики стажеров технической поддержки.

Проект имитирует работу с клиентским обращением: стажер открывает учебный тикет, запускает изолированное Docker-окружение, проводит диагностику в терминале, исправляет техническую проблему и готовит ответ клиенту.

Тренажер разделяет две части работы:

1. Техническое выполнение задания.
2. Качество ответа клиенту.

Техническую часть проверяет `check.sh`.
Ответ клиенту при необходимости проверяет наставник вручную.

## Возможности

- Авторизация пользователей.
- Профили пользователей с уровнями доступа.
- Очереди заданий для разных сценариев обучения.
- Учебные тикеты с сообщением клиента.
- Отдельная попытка прохождения задания для каждого пользователя.
- Запуск Docker-контейнера под конкретную попытку.
- Веб-терминал через ttyd.
- Безопасный terminal gateway через nginx `auth_request`.
- Проксирование WebSocket-соединения терминала через nginx.
- Доступ к терминалу только владельцу попытки или наставнику с `User.is_staff=True`.
- Привязка ttyd-портов к `127.0.0.1`.
- Автоматическая техническая проверка через `check.sh`.
- История автопроверок через `CheckRun`.
- Перезапуск окружения задания до успешной технической сдачи.
- Защита от случайного перезапуска после успешной технической сдачи через `technical_locked`.
- Осознанные повторные тренировочные попытки после технической сдачи.
- Разделение зачётной попытки и дополнительных тренировочных попыток.
- Фиксация успешного технического прохождения через `technical_passed_at`.
- Ручная проверка ответа клиенту наставником.
- Комментарии наставника и статус ручной проверки.
- Баннер новых комментариев наставника для стажера.
- Прогресс по очереди заданий.
- Дашборд стажера.
- Дашборд наставника со статистикой, фильтрами и ручной проверкой.
- Логирование отказов terminal-auth и ключевых действий с окружением.
- GitHub Actions workflow для базовой CI-проверки.
- Локальные Makefile-команды для nginx gateway и быстрых групп тестов.
- Audit-лог открытия терминала стажера наставником.
- Read-only режим для исторических попыток.
- Кнопка копирования shell-команды для наставника.
- Dark UI с Lucide-иконками.

## Архитектурное решение по уровням

В проекте нет отдельного уровня или очереди `trainee`.

Стажер считается претендующим на L1 и решает задачи из очереди `l1`.

Кандидат — отдельный сценарий. Для него используется очередь `candidate`.

Текущая логика доступа:

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

Отдельное поле `is_mentor` в базе не используется, чтобы не было рассинхрона прав.

## Основной workflow

### 1. Стажер открывает дашборд

На дашборде стажер видит доступные задания своей очереди.

Задания открываются последовательно: следующая задача становится доступной после успешного прохождения предыдущей технической части.

### 2. Стажер начинает работу

При нажатии «Начать работу» создается окружение задания:

- task-контейнер с учебной проблемой;
- terminal-контейнер с ttyd;
- ссылка на терминал;
- команда подключения для диагностики.

Состояние хранится в `TaskAttempt`.

### 3. Стажер исправляет проблему

Стажер работает в терминале, диагностирует проблему и исправляет окружение.

После этого он заполняет:

- ответ клиенту;
- внутренний комментарий по диагностике.

### 4. Автопроверка проверяет техническую часть

При отправке на проверку Django запускает `check.sh` внутри task-контейнера.

Результат каждой проверки сохраняется в `CheckRun`.

Если `check.sh` завершился успешно, у попытки заполняется:

```python
TaskAttempt.technical_passed_at
```

Это означает, что техническая часть задания выполнена.

### 5. Наставник проверяет только ответ клиенту

Если у задания включено:

```python
Task.requires_manual_review = True
```

то после успешной технической проверки попытка попадает на ручную проверку наставнику.

Важно: наставник проверяет только ответ клиенту, а не техническую часть.

Техническая часть уже подтверждена автопроверкой.

### 6. Если наставник отправил на доработку

Если наставник отправил ответ на доработку, стажер правит только текст ответа клиенту.

Docker-контейнер и `check.sh` повторно запускать не нужно.

Успешная техническая проверка не сбрасывается.

### 7. Стажер может идти дальше

Если `technical_passed_at` заполнен, техническая часть задания считается выполненной.

Стажер может переходить к следующему заданию по очереди, даже если наставник позже попросил доработать текст ответа.

## Структура проекта

```text
ticket-sandbox/
├── .github/             # GitHub Actions workflow
├── config/              # настройки Django
├── deploy/              # nginx-конфиги и примеры деплоя
├── sandbox/             # основное приложение
├── static/              # CSS и JS
├── templates/           # HTML-шаблоны
├── training_tasks/      # Docker-задания
├── terminal/            # окружение ttyd
├── docker-compose.yml
├── Makefile
├── manage.py
└── requirements.txt
```

## Очереди

В проекте используются очереди:

- `candidate` — задания для кандидатов до выхода в обучение;
- `l1` — основная очередь для стажеров, которые готовятся к работе на L1;
- `l2` — будущие более сложные задания;
- `admin` — служебная очередь.

## Основные модели

### Queue

Очередь учебных заданий.

Важные поля:

- `name`;
- `slug`;
- `description`;
- `order`;
- `required_level`;
- `is_active`.

Очередь определяет:

- какие задания видит пользователь;
- где искать Docker-окружение задания;
- в каком порядке показывать задачи.

### Task

Учебное задание.

Важные поля:

- `queue`;
- `title`;
- `slug`;
- `ticket_title`;
- `description`;
- `client_name`;
- `client_email`;
- `priority`;
- `order`;
- `is_active`;
- `requires_manual_review`.

`Task.queue` является обязательным.

`Task.queue_name` в проекте больше не используется.

`priority` использует фиксированные значения:

- `low`;
- `medium`;
- `high`;
- `critical`.

`requires_manual_review` определяет, нужна ли ручная проверка ответа клиенту после успешной технической проверки.

### TaskAttempt

Попытка прохождения задания конкретным пользователем.

Важные поля:

- `user`;
- `task`;
- `status`;
- `client_answer`;
- `trainee_report`;
- `attempts_count`;
- `restart_count`;
- `container_id`;
- `container_name`;
- `terminal_container_name`;
- `terminal_port`;
- `terminal_url`;
- `shell_command`;
- `attempt_number`;
- `is_current`;
- `last_check_output`;
- `technical_passed_at`;
- `mentor_feedback`;
- `mentor_decision`;
- `mentor_reviewed_by`;
- `mentor_reviewed_at`;
- `mentor_feedback_seen_at`.

Именно `TaskAttempt`, а не `Task`, хранит состояние прохождения задания.

Одно и то же задание могут проходить разные пользователи. У каждого пользователя должна быть своя попытка и свои контейнеры.

### CheckRun

История запусков автопроверки.

Каждый запуск `check.sh` сохраняется отдельной записью.

`CheckRun` нужен, чтобы видеть не только последний результат проверки, но и всю историю:

- когда запускалась проверка;
- какой был результат;
- какой был exit code;
- какой вывод вернул `check.sh`.

### TraineeProfile

Профиль пользователя в тренажере.

Важные поля:

- `user`;
- `level`.

Доступные уровни:

- `candidate`;
- `l1`;
- `l2`;
- `admin`.

Профиль создается автоматически через signal при создании пользователя.

## Структура учебных заданий

Задания хранятся по очередям:

```text
training_tasks/
└── l1/
    └── task-slug/
        ├── Dockerfile
        └── files/
            ├── check.sh
            └── остальные файлы окружения
```

`queue.slug` и `task.slug` используются для поиска папки задания.

Например, если окружение лежит здесь:

```text
training_tasks/l1/sajt-ne-rabotaet-posle-perenosa/
```

то в базе у задания должны быть такие значения:

```python
queue.slug = "l1"
slug = "sajt-ne-rabotaet-posle-perenosa"
```

Docker-сервис собирает путь к заданию так:

```text
training_tasks/<queue_slug>/<task_slug>
```

## Запуск проекта локально

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

### 6. Запустить Django dev server

```bash
python manage.py runserver
```

Django dev server будет доступен по адресу:

```text
http://127.0.0.1:8000/
```

Важно: если включен `TERMINAL_GATEWAY_ENABLED=true`, для полноценной работы с терминалом проект нужно открывать не напрямую через `127.0.0.1:8000`, а через локальный nginx gateway.

### 7. Запустить локальный nginx gateway для терминала

При включенном terminal gateway адреса вида:

```text
/terminal/<attempt_id>/<port>/
```

обрабатывает nginx, а не Django dev server.

Запуск nginx gateway во втором терминале:

```bash
make nginx-test
make nginx-start
```

После этого проект нужно открывать по адресу:

```text
http://localhost:8081/
```

Именно этот адрес используется для локальной работы с терминалом.

Полезные команды для nginx gateway:

```bash
make nginx-reload
make nginx-stop
make nginx-logs
```

Если открыть проект напрямую через `http://127.0.0.1:8000/`, страницы Django будут работать, но терминал будет отдавать `404`, потому что `/terminal/...` должен обрабатывать nginx.

## Переменные окружения

Пример `.env`:

```env
DEBUG=True
SECRET_KEY=dev-secret-key
ALLOWED_HOSTS=127.0.0.1,localhost
EXTERNAL_HOST=localhost

DB_ENGINE=django.db.backends.postgresql
DB_NAME=ticket_sandbox
DB_USER=ticket_sandbox_user
DB_PASSWORD=ticket_sandbox_password
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

TERMINAL_GATEWAY_ENABLED=true
CHECK_TASK_TIMEOUT_SECONDS=60
LOG_LEVEL=INFO
```

Важные переменные:

- `DB_ENGINE` — backend базы данных. По умолчанию используется PostgreSQL, в CI можно использовать SQLite.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD` — используются Django для подключения к базе;
- `POSTGRES_HOST`, `POSTGRES_PORT` — адрес и порт PostgreSQL;
- `TERMINAL_GATEWAY_ENABLED=true` — включает построение ссылок на терминал через `/terminal/<attempt_id>/<port>/`;
- `CHECK_TASK_TIMEOUT_SECONDS` — ограничивает время выполнения `check.sh` при автопроверке;
- `EXTERNAL_HOST` — используется только при выключенном terminal gateway;
- `LOG_LEVEL` — уровень логирования приложения.

## Makefile

В проекте есть `Makefile` с основными командами для разработки.

Основные команды:

```bash
make up
make migrate
make run
make build-images
make cleanup
make makemigrations
make shell
make check
make migrations-check
make test
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

Основная проверка перед ревью:

```bash
make validate
```

Она запускает:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test sandbox
```

Что проверяют команды:

```bash
make test-terminal   # terminal auth и terminal gateway
make test-actions    # действия с попытками, check/restart/rerun
make test-docker     # Docker service и management-команды
make test-dashboards # дашборды стажера и наставника
```

Во время разработки обычно достаточно запускать тесты по измененной области.
Полный `make validate` стоит запускать после пачки изменений, перед ревью, архивом или деплоем.

## Как добавить новое задание

### 1. Создать папку задания

Например:

```text
training_tasks/l1/nginx-not-starting/
```

### 2. Добавить Dockerfile

Внутри папки задания должен быть `Dockerfile`, который собирает окружение с проблемой.

### 3. Добавить check.sh

`check.sh` должен проверять, исправил ли стажер проблему.

Пример:

```bash
#!/usr/bin/env bash
set -e

nginx -t
curl -fsS http://127.0.0.1/ > /dev/null

echo "OK: nginx работает, сайт отвечает"
```

Файл должен быть исполняемым:

```bash
chmod +x training_tasks/l1/nginx-not-starting/files/check.sh
```

### 4. Добавить task.json

`task.json` — основной источник правды для учебного задания.

Постоянные правки текста тикета, клиента, приоритета, порядка, активности и ручной проверки нужно делать в файле, а не руками в Django admin.

Минимальный пример:

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

Важно: `slug` берется из названия папки задания и должен совпадать со slug задачи в БД.

Для примера выше папка задания может выглядеть так:

```text
training_tasks/l1/nginx-not-starting/
```

### 5. Синхронизировать задания

Сначала посмотри, что будет создано или обновлено:

```bash
python manage.py sync_training_tasks --dry-run
```

Потом примени изменения:

```bash
python manage.py sync_training_tasks
```

Django admin можно использовать для просмотра, фильтров и быстрых массовых действий, но постоянные правки учебных заданий нужно фиксировать в `training_tasks/<queue_slug>/<task_slug>/task.json`.

Если поправить задание только через admin, следующий запуск `sync_training_tasks` может вернуть значения из файлов.

## Проверка проекта

Проверить Django-проект:

```bash
python manage.py check
```

Проверить, что нет несозданных миграций:

```bash
python manage.py makemigrations --check --dry-run
```

Показать миграции приложения:

```bash
python manage.py showmigrations sandbox
```

Запустить тесты:

```bash
python manage.py test sandbox
```

Полная локальная проверка:

```bash
make validate
```

## CI

В проект добавлен GitHub Actions workflow:

```text
.github/workflows/ci.yml
```

CI запускается на `push` и `pull_request`.

Workflow выполняет базовые проверки:

```text
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py check --deploy
python manage.py test sandbox
```

Для CI используется SQLite in-memory база, чтобы проверки не требовали отдельного PostgreSQL-сервиса.

Если проект будет перенесен во внутренний GitLab, можно добавить отдельный файл:

```text
.gitlab-ci.yml
```

GitHub Actions и GitLab CI не конфликтуют между собой, но держать обе CI-системы одновременно имеет смысл только после выбора основной платформы хранения проекта.

## Тесты

Тесты лежат в директории:

```text
sandbox/tests/
```

Текущие группы тестов:

```text
sandbox/tests/
├── base.py
├── test_check_runs.py
├── test_docker_service.py
├── test_management_commands.py
├── test_mentor_dashboard.py
├── test_models.py
├── test_profiles.py
├── test_queue_access.py
├── test_rerun_attempt.py
├── test_task_actions.py
├── test_task_availability.py
├── test_template_filters.py
├── test_terminal_auth.py
├── test_terminal_gateway.py
└── test_trainee_dashboard.py
```

Тесты не запускают реальные Docker-контейнеры.

Docker-вызовы мокируются, чтобы проверки были быстрыми и безопасными.

Ключевые проверки terminal gateway:

```bash
python manage.py test sandbox.tests.test_terminal_auth
python manage.py test sandbox.tests.test_terminal_gateway
```

Ключевые проверки повторных и исторических попыток:

```bash
python manage.py test sandbox.tests.test_rerun_attempt
```

Быстрые группы тестов через Makefile:

```bash
make test-terminal
make test-actions
make test-docker
make test-dashboards
```

Полный набор тестов приложения:

```bash
python manage.py test sandbox
```

Полная локальная проверка:

```bash
make validate
```

## ttyd и terminal gateway

ttyd используется для веб-доступа к терминалу задания.

Terminal-контейнер публикует порт только на localhost:

```python
ports = {"7681/tcp": ("127.0.0.1", port)}
```

Это значит, что ttyd не открывается наружу напрямую.

При включенном terminal gateway:

```env
TERMINAL_GATEWAY_ENABLED=true
```

ссылка на терминал строится так:

```text
/terminal/<attempt_id>/<port>/
```

Запросы на `/terminal/...` принимает nginx.

Перед проксированием терминала nginx выполняет `auth_request` во внутренний location:

```nginx
auth_request /_terminal_auth;
```

Внутренний nginx location обращается к Django endpoint:

```text
/terminal-auth/
```

Исходный URI терминала передается в Django через заголовок:

```text
X-Original-URI
```

Django разбирает URI, получает `attempt_id` и `port`, затем проверяет:

- пользователь авторизован;
- попытка существует;
- пользователь является владельцем попытки или имеет `User.is_staff=True`;
- запрошенный порт совпадает с `TaskAttempt.terminal_port`;
- terminal-контейнер существует;
- `terminal_url` не пустой;
- попытка не закрыта технически;
- попытка доступна пользователю.

Если проверка успешна, Django возвращает `204`, и nginx проксирует WebSocket-соединение на:

```text
127.0.0.1:<port>
```

Если проверка неуспешна, Django возвращает `401` или `403`, и терминал не открывается.

Открытие терминала стажера наставником логируется отдельным audit-событием `mentor_terminal_access` через логгер `sandbox.terminal`.

Basic Auth для ttyd в проекте не используется. Доступ к терминалу контролируется через Django-сессию и nginx `auth_request`.

Конфиги nginx лежат в:

```text
deploy/nginx/ticket-sandbox-local.conf
deploy/nginx/ticket-sandbox.conf.example
```

Важные особенности nginx-конфига:

- `proxy_pass` для terminal не должен заканчиваться слешем;
- WebSocket-заголовки `Upgrade` и `Connection` должны проксироваться;
- `Host` передается как `$http_host`, чтобы не ломать CSRF при локальном запуске через `localhost:8081`;
- диапазон ttyd-портов ограничен `20000-30000`;
- regex порта записан без `{4}`, чтобы не ловить ошибку nginx-конфига.

## Важные ограничения MVP

На текущем этапе проект является учебным MVP.

Уже закрыто:

- ttyd-порты привязаны к `127.0.0.1`;
- terminal gateway работает через nginx `auth_request`;
- доступ к терминалу проверяется через Django-сессию;
- task-контейнеры имеют базовые resource limits;
- обычный перезапуск заблокирован после успешной технической сдачи;
- повторное прохождение сделано через отдельную тренировочную попытку.

Перед использованием с живыми стажерами нужно дополнительно доработать:

- вынести тяжелые Docker-операции из Django view;
- добавить Celery + Redis для запуска, перезапуска и проверки окружений;
- добавить timeout на выполнение `check.sh`;
- усилить обработку ошибок Docker API;
- добавить production-настройки nginx, TLS и заголовков безопасности;
- улучшить аналитику по стажерам и заданиям;
- добавить больше учебных заданий.

## Технический долг

- Вынести тяжелые Docker-операции в Celery + Redis.
- Добавить timeout на выполнение автопроверки.
- Улучшить обработку ошибок Docker API.
- Добавить отдельные фоновые статусы для долгих операций запуска и проверки.
- Добавить мониторинг и более подробное production-логирование.
- Подготовить production-инструкцию для nginx, TLS и безопасных заголовков.
- Улучшить аналитику по прохождению заданий.
- Добавить больше учебных задач для очередей `candidate`, `l1` и `l2`.

## Что считается стабильной базой

На текущем этапе стабильной базой считаются:

- очереди `candidate`, `l1`, `l2`, `admin`;
- отсутствие очереди `trainee`;
- обязательный `Task.queue`;
- отсутствие `Task.queue_name`;
- `priority` через choices;
- наставник через `User.is_staff`;
- автопроверка технической части через `check.sh`;
- история автопроверок через `CheckRun`;
- ручная проверка ответа клиенту наставником;
- разделение технической проверки и проверки текста;
- прогресс по очереди;
- баннер новых комментариев наставника;
- ttyd, привязанный к `127.0.0.1`;
- terminal gateway через nginx `auth_request`;
- endpoint `/terminal-auth/` для проверки доступа к терминалу;
- WebSocket-проксирование терминала через nginx;
- защита от открытия чужого терминала;
- защита от открытия терминала закрытой технической попытки;
- audit-лог открытия терминала наставником;
- resource limits для task-контейнеров;
- защита от случайного перезапуска после `technical_passed_at`;
- повторные тренировочные попытки через `attempt_number > 1`;
- исторические попытки открываются в read-only режиме;
- дополнительные попытки не идут в mentor dashboard как зачётные;
- тесты на доступы, очереди, модели, action-view, CheckRun, Docker service, terminal gateway, rerun attempts и mentor dashboard;
- логирование отказов terminal-auth и ключевых действий с окружением;
- GitHub Actions workflow;
- `make validate`.

## Ближайшие планы

Ближайшие задачи:

1. Вынести тяжелые Docker-операции в Celery + Redis.
2. Добавить timeout на выполнение `check.sh`.
3. Улучшить обработку ошибок Docker API.
4. Расширить production-документацию по nginx и terminal gateway.
5. Улучшить аналитику по стажерам и заданиям.
6. Добавить больше учебных заданий для очередей `candidate`, `l1` и `l2`.
7. При необходимости добавить GitLab CI, если проект будет храниться во внутреннем GitLab.

## Деплой на сервер

Этот раздел описывает минимальный staging/production-запуск Ticket Sandbox через venv, gunicorn, nginx и Docker.

### Требования

На сервере должны быть установлены:

- Python 3.12+;
- PostgreSQL 16;
- nginx;
- Docker;
- git;
- systemd.

Docker нужен для запуска task-контейнеров и ttyd-терминала.

### Подготовка проекта

```bash
git clone <repo-url> /opt/ticket-sandbox
cd /opt/ticket-sandbox

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Настройка `.env`

Скопируй пример переменных окружения:

```bash
cp .env.example .env
```

На сервере обязательно укажи production-значения:

```env
DEBUG=False
SECRET_KEY=<strong-secret-key>
ALLOWED_HOSTS=staging.example.com
CSRF_TRUSTED_ORIGINS=https://staging.example.com

DB_ENGINE=django.db.backends.postgresql
DB_NAME=ticket_sandbox
DB_USER=ticket_sandbox_user
DB_PASSWORD=<strong-db-password>
DB_HOST=127.0.0.1
DB_PORT=5432

TERMINAL_GATEWAY_ENABLED=true
CHECK_TASK_TIMEOUT_SECONDS=60
LOG_LEVEL=INFO
```

Важно: на сервере `DEBUG` должен быть `False`.

### База данных и static-файлы

Применить миграции:

```bash
python manage.py migrate
```

Синхронизировать учебные задания из `training_tasks`:

```bash
python manage.py sync_training_tasks
```

Собрать static-файлы:

```bash
python manage.py collectstatic --noinput
```

При `ManifestStaticFilesStorage` этот шаг обязателен. Без `collectstatic` страницы со static-файлами могут отдавать ошибку.

Создать администратора:

```bash
python manage.py createsuperuser
```

### Сборка Docker-образов

Собрать образ терминала:

```bash
docker build -t ticket-sandbox-ttyd terminal/
```

Собрать образы учебных заданий:

```bash
python manage.py build_task_images
```

### Запуск приложения

Для staging/production Django запускается через gunicorn:

```bash
make serve
```

Для постоянной работы на сервере лучше использовать systemd unit из примера:

```text
deploy/systemd/ticket-sandbox.service.example
```

После копирования unit-файла:

```bash
sudo systemctl daemon-reload
sudo systemctl enable ticket-sandbox
sudo systemctl start ticket-sandbox
sudo systemctl status ticket-sandbox
```

### nginx

В качестве основы используй пример:

```text
deploy/nginx/ticket-sandbox.conf.example
```

В nginx static должен смотреть на `STATIC_ROOT`, то есть на собранную директорию `staticfiles/`, а не на исходную директорию `static/`.

Пример:

```nginx
location /static/ {
    alias /opt/ticket-sandbox/staticfiles/;
}
```

После настройки nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### Очистка старых контейнеров

Для регулярной очистки старых task/terminal-контейнеров нужно настроить cron или systemd timer.

Пример cron находится здесь:

```text
deploy/cron/cleanup_task_containers.example
```

Команда очистки:

```bash
python manage.py cleanup_task_containers
```

### Проверка перед запуском

Перед первым запуском на staging:

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py sync_training_tasks --dry-run
python manage.py sync_training_tasks
python manage.py collectstatic --noinput
python manage.py build_task_images
```

Также нужно проверить:

```bash
docker ps
docker build -t ticket-sandbox-ttyd terminal/
sudo nginx -t
sudo systemctl status ticket-sandbox
```

### Проверка после запуска

После деплоя нужно пройти минимальный сценарий:

1. Открыть `/` и увидеть страницу входа.
2. Войти стажером и открыть dashboard.
3. Открыть L1-задание.
4. Нажать «Начать работу».
5. Убедиться, что терминал открылся через `/terminal/<attempt_id>/<port>/`.
6. Выполнить задание и отправить на проверку.
7. Убедиться, что `check.sh` отработал.
8. Проверить ручную проверку наставником, если задача требует `requires_manual_review=True`.
9. Проверить, что после успешной технической сдачи обычный перезапуск заблокирован.
10. Проверить, что историческая попытка открывается только в read-only режиме.
