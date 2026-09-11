# CONTRIBUTING

Этот файл описывает правила разработки Training Platform с акцентом на Ticket Sandbox: как добавлять задания, менять архитектуру, писать проверки и готовить проект к ревью.

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

---

## Базовые архитектурные правила

### Не возвращать очередь trainee

В проекте нет отдельной очереди `trainee`.

Текущие очереди:

```text
candidate
l1
l2
admin
```

Стажёр L1 работает в `l1`, кандидат — в `candidate`.

### Task.queue обязателен

Каждое задание должно быть привязано к очереди через:

```python
Task.queue
```

Путь к Docker-окружению:

```text
training_tasks/<queue_slug>/<task_slug>
```

`queue_name` возвращать не нужно.

### Наставник определяется через User.is_staff

```python
User.is_staff
```

Отдельный флаг наставника в `TraineeProfile` не нужен.

### Не смешивать техническую проверку и проверку текста

Техническую часть проверяет:

```text
check.sh
```

Наставник проверяет только ответ клиенту.

Если `technical_passed_at` заполнен, техническая часть считается выполненной.

При доработке текста Docker-контейнер и `check.sh` повторно запускать не нужно.

### Не показывать стажёру инфраструктурный шум

`last_check_output` должен содержать полезный результат проверки.

Сообщения об удалении task/terminal-контейнеров, Docker API и внутреннем cleanup нужно писать в application logs.

### task.json — источник правды

Постоянные изменения задания делаются в:

```text
training_tasks/<queue_slug>/<task_slug>/task.json
```

Проверка:

```bash
python manage.py sync_training_tasks --dry-run --strict
```

Применение:

```bash
python manage.py sync_training_tasks --strict
```

---

## Terminal gateway

Basic Auth для ttyd не используем.

Актуальный production/staging режим:

```text
Browser
  ↓
nginx /terminal/<attempt_id>/
  ↓
auth_request /_terminal_auth
  ↓
Django /terminal-auth/
  ↓
X-Terminal-Upstream: <terminal-container>:7681
  ↓
ttyd
```

Правила:

- не публиковать ttyd host-порты наружу в `docker_network` режиме;
- не возвращать Basic Auth;
- проверять доступ через Django terminal auth;
- разрешать доступ владельцу попытки или `User.is_staff=True`;
- логировать доступ наставника через `mentor_terminal_access`.

Legacy-режим `host_port` поддерживается кодом для совместимости, но новая staging/production-схема использует:

```env
TERMINAL_NETWORK_MODE=docker_network
```

---

## Background lifecycle: только через Celery

Запуск окружения, restart и автопроверка выполняются через Redis + Celery worker.

Новые `threading.Thread` для Docker/background lifecycle добавлять не нужно.

Текущие задачи:

```text
sandbox.start_environment
sandbox.restart_environment
sandbox.run_attempt_check
```

Поток:

```text
Django web
  ↓
Redis
  ↓
Celery worker
  ↓
Docker API
```

### Важное правило Docker-доступа

`web` не имеет `/var/run/docker.sock`.

Нельзя добавлять socket обратно в `web` ради новой фичи или management command.

Docker-операции должны выполняться:

- через Celery worker;
- либо через management command, запущенную сервисом `worker`.

Если новая web-функция требует Docker API, правильный путь — добавить Celery task, а не прямой вызов Docker из view.

---

## Celery tasks

Celery tasks храним в:

```text
sandbox/tasks.py
```

Task должен получать простые сериализуемые аргументы, например:

```text
attempt_id
user_id
```

Не передавай Django model instance в Celery message.

Worker должен заново загрузить актуальный объект из PostgreSQL.

Основная бизнес-логика по возможности остаётся в service-функциях, а Celery task выступает transport/wrapper слоем.

Это позволяет:

- тестировать бизнес-логику отдельно;
- не дублировать Docker-логику;
- сохранять понятные recovery-функции;
- легче менять transport позже.

Если состояние БД создаётся внутри транзакции и задача не должна стартовать до commit, используй `transaction.on_commit(...)` или эквивалентный Celery/Django механизм. Не добавляй это автоматически там, где текущий код уже безопасен — оценивай конкретный transaction lifecycle.

---

## Environment status

Используется:

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

Правила:

- start не должен перезаписывать `starting` или `restarting`;
- restart не должен перезаписывать `starting` или `restarting`;
- restart сбрасывает `finished_at`, check state/timestamps и `stuck_reason`;
- при ошибке окружение переводится в `error`, попытка — в `failed`.

---

## Check status

Используется:

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

Правила:

- запуск автопроверки должен быть атомарным;
- двойной клик не должен создавать две Celery-задачи;
- пока `check_status=running`, повторный запуск запрещён;
- если окружение `starting`, `restarting` или `error`, автопроверку запускать нельзя.

Важно различать:

```text
Celery task succeeded
```

и:

```text
check.sh failed with exit code 1
```

Второе — нормальный пользовательский результат проверки, а не сбой Celery.

---

## Watchdog

Переход на Celery не отменяет watchdog.

`detect_stuck_attempts` нужен, если:

- Celery worker был остановлен;
- Docker daemon/операция зависли;
- контейнер был убит;
- задача прервалась после перевода статуса в `starting`, `restarting` или `running`.

Команды:

```bash
python manage.py detect_stuck_attempts --dry-run
python manage.py detect_stuck_attempts
```

Не завязывай recovery на текст `last_check_output`. Используй явные status/timestamps и `stuck_reason`.

---

## Docker image и non-root runtime

`web` и `worker` запускаются от:

```text
uid=10001(app)
gid=10001(app)
```

В Dockerfile должен сохраняться:

```dockerfile
COPY --chown=app:app . .
USER app
```

Не заменяй это на `chmod 777`.

Причина: non-root runtime должен иметь доступ к приложению без выдачи лишних прав.

---

## DOCKER_GID

Worker получает Docker socket как дополнительную группу.

Переменная:

```env
DOCKER_GID=...
```

должна совпадать с:

```bash
stat -c '%g' /var/run/docker.sock
```

Нельзя копировать GID со staging на production вслепую.

Перед deploy используется:

```text
deploy/check_docker_socket_gid.sh
```

Если добавляешь или меняешь production/staging deployment, не убирай эту preflight-проверку.

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

`web`:

- без Docker socket;
- Django/Gunicorn;
- producer Celery tasks.

`worker`:

- с Docker socket;
- дополнительная группа `DOCKER_GID`;
- Celery consumer;
- Docker management commands.

Redis в production не должен публиковаться наружу без отдельной причины. Локальная публикация `6379:6379` находится только в local override и нужна для Django/Celery, которые могут запускаться с host.

---

## Management commands

Основные команды:

```bash
python manage.py build_task_images
python manage.py cleanup_task_containers
python manage.py sync_training_tasks
python manage.py detect_stuck_attempts
python manage.py seed_stages
python manage.py check_trainee_integrity
```

Команды, которым Docker API не нужен, можно запускать через `web`.

Docker-зависимые команды запускаем через `worker`:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps worker \
  python manage.py build_task_images
```

Аналогично для `cleanup_task_containers`.

---

## CI/CD правила

Deploy staging выполняется только после зелёного tests job при push в `main`.

Не возвращать host deployment шаги:

```text
pip install на сервере
collectstatic на сервере
systemctl restart ticket-sandbox
```

Dependencies и static входят в application image.

Актуальный deploy должен сохранять последовательность:

```text
fetch exact commit
check Docker socket GID
compose config
build web + worker
start db
migrate via web
sync tasks via web
build task images via worker
start web + worker
force-recreate gateway
compose ps
external smoke checks
```

Gateway пересоздаётся после web, потому что nginx внутри долгоживущего контейнера может сохранить старый IP пересозданного `web` и начать отдавать `502`.

---

## Healthchecks

Healthchecks должны оставаться у:

```text
db
redis
web
worker
gateway
```

Worker healthcheck использует Celery ping.

Не считай просто `Up` достаточной проверкой worker — нужен `healthy`.

---

## Уведомления

### Telegram

Telegram — побочный эффект, а не часть критического пути.

Если credentials не заданы — уведомления выключены.

Если Telegram API недоступен — пользовательский сценарий не должен падать.

### Sentry

Не хардкодить DSN.

Если `SENTRY_DSN` пустой, Sentry не должен мешать запуску проекта.

Ошибки background/Celery wrappers, которые ловятся вручную, можно отправлять через `capture_exception(error)`.

---

## Тесты

Тесты не должны запускать реальные Docker-контейнеры или настоящий Redis/Celery broker для обычных unit/service tests.

Docker-вызовы мокируются.

Celery `.delay()` в service tests также мокируется, если тест проверяет постановку задачи в очередь.

Примеры важных тестов:

```text
start_environment_in_background → вызывает start_environment_task.delay
restart_environment → вызывает restart_environment_task.delay
start_attempt_check_in_background → атомарно ставит running и вызывает run_attempt_check_task.delay
already running → Celery task не ставится
```

Точечные проверки:

```bash
python manage.py test sandbox.tests.test_environment_service
python manage.py test sandbox.tests.test_check_service
python manage.py test sandbox.tests.test_task_actions
python manage.py test sandbox.tests.test_management_commands
```

Полный прогон перед merge/deploy:

```bash
python manage.py test
```

---

## Когда добавлять тесты

Тесты нужно добавлять/обновлять, если меняется:

- модель или миграция;
- доступ к очередям;
- mentor dashboard;
- start/restart/check;
- Celery task dispatch;
- background lifecycle;
- polling;
- watchdog;
- `stuck_reason`;
- `CheckRun`;
- ручная проверка;
- Telegram/Sentry;
- healthchecks;
- Docker service;
- management command;
- CI/CD shell logic, если её можно проверить локально.

---

## Локальная проверка

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Compose validation:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.local.yml \
  config --quiet
```

Проверка worker:

```bash
celery -A config inspect ping
celery -A config inspect registered
```

Проверка Docker API внутри worker:

```bash
docker exec training-platform-worker python -c "
import docker
print(docker.from_env().ping())
"
```

---

## Перед push

Обычно:

```bash
git status --short
git diff --stat
git diff --check
```

Затем точечные тесты и полный прогон.

После зелёных проверок:

```bash
git add ...
git commit -m "Meaningful commit message"
git push
```

Не пушить напрямую в `main`, если изменение идёт через feature/infra branch и PR.

---

## Перед merge в main

Для инфраструктурных изменений обязательно:

1. CI ветки зелёный.
2. Изменения вручную проверены на staging.
3. `web` не имеет Docker socket.
4. `worker` работает non-root и имеет доступ к Docker API.
5. `DOCKER_GID` staging соответствует реальному socket GID.
6. `start`, `restart`, `check.sh` выполняются через worker.
7. Gateway/terminal работают после пересоздания web.
8. После этого создаётся PR в `main` и выполняется merge.
9. Push/merge в `main` должен пройти автоматический staging deploy.
