# CONTRIBUTING

Этот файл описывает правила разработки Ticket Sandbox: как добавлять задания, менять архитектуру, писать проверки и готовить проект к ревью.

## Общий принцип

Ticket Sandbox — учебная тикетница для практики стажеров технической поддержки.

Проект должен оставаться простым и предсказуемым:

- стажер решает техническую задачу в Docker-окружении;
- `check.sh` проверяет технический результат;
- наставник проверяет только ответ клиенту;
- история проверок и решений должна сохраняться;
- прогресс стажера не должен ломаться случайными действиями.

Любые изменения лучше делать маленькими шагами и сразу закрывать тестами.

## Базовые архитектурные правила

### Не возвращать очередь trainee

В проекте нет отдельной очереди `trainee`.

Стажер считается претендующим на L1 и работает в очереди:

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

Добавлять обратно очередь `trainee` не нужно.

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

Так меньше риск рассинхрона прав.

### Не смешивать техническую проверку и проверку текста

Техническую часть проверяет только:

```text
check.sh
```

Наставник проверяет только:

```text
ответ клиенту
```

Если `check.sh` прошел успешно и `technical_passed_at` заполнен, техническая часть считается выполненной.

Если наставник отправил ответ на доработку, стажер правит только текст.

Docker-контейнер и `check.sh` повторно запускать не нужно.

### CheckRun должен хранить историю автопроверок

Каждый запуск `check.sh` должен создавать запись `CheckRun`.

Не нужно хранить только последний вывод проверки.

`last_check_output` удобен для быстрого отображения, но история должна оставаться в `CheckRun`.

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

Terminal-контейнер публикует ttyd только на localhost:

```python
ports = {"7681/tcp": ("127.0.0.1", port)}
```

Доступ к терминалу контролируется через Django-сессию и nginx `auth_request`.

Правила:

- не открывать ttyd-порты наружу;
- не возвращать Basic Auth для ttyd;
- не оставлять случайные порты как production-решение;
- проверять доступ через `/terminal-auth/`;
- разрешать доступ владельцу попытки или наставнику с `User.is_staff=True`;
- логировать открытие терминала стажера наставником через `mentor_terminal_access`.

### slug должен совпадать с папкой

Если папка называется:

```text
training_tasks/l1/site-shows-nginx-page/
```

то в базе должно быть:

```text
slug = site-shows-nginx-page
```

### очередь должна совпадать с папкой

Если задание лежит в:

```text
training_tasks/l1/
```

то у задания должна быть очередь:

```text
queue.slug = l1
```

Если задание лежит в:

```text
training_tasks/candidate/
```

то очередь должна быть:

```text
queue.slug = candidate
```


### task.json — источник правды для задания

Задания синхронизируются командой:

```bash
python manage.py sync_training_tasks
```

Поэтому постоянные правки задания нужно делать в файле:

```text
training_tasks/<queue_slug>/<task_slug>/task.json
```

А не руками в Django admin.

Django admin можно использовать для просмотра, фильтров и быстрых массовых действий, но при следующем deploy/CD команда `sync_training_tasks` снова применит значения из файлов.

Перед применением изменений лучше запускать dry-run:

```bash
python manage.py sync_training_tasks --dry-run
```

## Проверка нового задания

После добавления или изменения задания проверь проект:

```bash
python manage.py check
```

Проверь, что команда синхронизации видит изменения:

```bash
python manage.py sync_training_tasks --dry-run
```

Если dry-run показывает ожидаемые изменения, примени синхронизацию:

```bash
python manage.py sync_training_tasks
```

Проверь, что Django видит задачу:

```bash
python manage.py shell
```

```python
from sandbox.models import Task

task = Task.objects.select_related("queue").get(slug="task-slug")
print(task.queue.slug, task.slug)
```

Проверь, что папка существует:

```bash
ls training_tasks/l1/task-slug/
```

Проверь, что `check.sh` исполняемый:

```bash
ls -la training_tasks/l1/task-slug/files/check.sh
```

## Management commands

В проекте есть команды:

```bash
python manage.py build_task_images
python manage.py cleanup_task_containers
python manage.py sync_training_tasks
```

`build_task_images` собирает Docker-образы заданий.

`cleanup_task_containers` удаляет контейнеры тренажера.

`sync_training_tasks` создает и обновляет задания в БД из папки `training_tasks`.

Если меняешь Docker-логику, структуру `training_tasks` или `task.json`, проверь management-команды и тесты для них.

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

Тесты не должны запускать реальные Docker-контейнеры.

Docker-вызовы нужно мокировать.

Для точечной проверки используй тесты по измененной области:

```bash
make test-terminal
make test-actions
make test-docker
make test-dashboards
```

Что проверяют команды:

```text
make test-terminal   # terminal auth и terminal gateway
make test-actions    # действия с попытками, check/restart/rerun
make test-docker     # Docker service и management-команды
make test-dashboards # дашборды стажера и наставника
```

Полный `make validate` нужен после пачки изменений, перед ревью, архивом или деплоем.

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
- создание `CheckRun`;
- ручная проверка наставником;
- прогресс по очереди;
- баннер комментариев наставника;
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

Быстрые группы тестов:

```bash
make test-terminal
make test-actions
make test-docker
make test-dashboards
```

Полная проверка перед ревью, архивом или деплоем:

```bash
make validate
```

`make validate` должен проходить успешно перед тем, как отдавать проект на ревью, собирать архив или деплоить.

Во время разработки не нужно гонять полный набор после каждой мелкой правки. Достаточно запускать тесты по измененной области.

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

Миграции должны быть понятными и последовательными.

Не стоит вручную править уже примененные миграции, если проектом уже пользовались.

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

Перед архивом проекта не нужно включать лишние временные файлы.

## Что не нужно добавлять в архив

Перед отправкой проекта на ревью не нужно включать:

```text
.venv
__pycache__
*.pyc
db.sqlite3
media
.DS_Store
```

Если нужно сделать архив без лишнего:

```bash
zip -r ticket-sandbox.zip .   -x ".venv/*"   -x "*/__pycache__/*"   -x "*.pyc"   -x "db.sqlite3"   -x "media/*"   -x "logs/*"   -x ".env"   -x ".DS_Store"   -x "*/.DS_Store"
```

Если `staticfiles/` не нужен для ревью, его тоже можно исключить:

```bash
zip -r ticket-sandbox.zip .   -x ".venv/*"   -x "*/__pycache__/*"   -x "*.pyc"   -x "db.sqlite3"   -x "media/*"   -x "logs/*"   -x ".env"   -x "staticfiles/*"   -x ".DS_Store"   -x "*/.DS_Store"
```

## Правила для mentor review

Ручная проверка наставником должна оставаться проверкой текста.

Наставник не должен повторно проверять техническое состояние окружения руками.

Если `technical_passed_at` заполнен, техническая часть уже пройдена.

При решении наставника:

- `mentor_feedback` хранит комментарий;
- `mentor_decision` хранит решение;
- `mentor_reviewed_by` хранит наставника;
- `mentor_reviewed_at` хранит дату проверки;
- `mentor_feedback_seen_at` показывает, видел ли стажер новый комментарий.

Если наставник отправил на доработку, нельзя сбрасывать `technical_passed_at`.

## Правила для progress logic

Прогресс по очереди должен опираться на успешную техническую сдачу.

Критерий:

```python
technical_passed_at is not None
```

Ручная доработка текста не должна откатывать технический прогресс.

## Правила для повторных и исторических попыток

Если `technical_passed_at` заполнен, обычные `start` и `restart` не должны сбрасывать попытку.

Для повторного прохождения используется отдельная осознанная тренировочная попытка:

```text
attempt_number > 1
is_current = True
```

Старая попытка остается в истории:

```text
is_current = False
```

Правила:

- старую успешную попытку не ломать;
- историю `CheckRun` не удалять;
- прогресс по очереди не откатывать;
- случайный перезапуск контейнера не должен переводить задачу обратно в работу;
- дополнительные тренировочные попытки не должны попадать в mentor dashboard как зачётные;
- исторические попытки должны быть read-only;
- action-view `start`, `restart` и `check` должны блокировать исторические попытки.

## Timeout check.sh и ошибки Docker API

`check.sh` не должен выполняться бесконечно.

Время автопроверки задается переменной:

```env
CHECK_TASK_TIMEOUT_SECONDS=60
```

Если меняешь логику автопроверки, запуска контейнеров или Docker service, нужно проверить:

```bash
make test-docker
make test-actions
```

Минимальные ожидания:

- зависший `check.sh` должен завершаться по timeout;
- пользователь не должен получать 500 при ошибке Docker API;
- ошибка должна сохраняться в `last_check_output`;
- ошибка должна логироваться через `sandbox.terminal`;
- попытка должна переходить в понятное состояние, обычно `failed`.

Полный `make validate` запускается после пачки изменений, перед ревью, архивом или деплоем.

## Технический долг

Текущий технический долг:

- вынести тяжелые Docker-операции в Celery + Redis;
- добавить timeout на выполнение `check.sh`;
- улучшить обработку ошибок Docker API;
- добавить промежуточные фоновые статусы для долгих операций:
  - `starting`;
  - `checking`;
  - `restarting`;
  - `cleanup_failed`;
- подготовить production-инструкцию для nginx, TLS, cookies и безопасных заголовков;
- добавить мониторинг и более подробное production-логирование;
- улучшить аналитику по стажерам и заданиям;
- добавить больше учебных заданий.

## Чек-лист перед ревью

Перед ревью нужно проверить:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py sync_training_tasks --dry-run
python manage.py test sandbox
```

Или одной командой:

```bash
make validate
```

Также стоит проверить:

- нет ли случайно возвращенной очереди `trainee`;
- нет ли задач без `Task.queue`;
- не вернулось ли поле `queue_name`;
- mentor dashboard закрыт для обычных пользователей;
- Docker-вызовы в тестах мокируются;
- `CheckRun` создается при автопроверке;
- `technical_passed_at` заполняется после успешной проверки;
- доработка наставника не сбрасывает технический успех;
- ttyd не проброшен наружу напрямую;
- terminal gateway работает через nginx `auth_request`;
- `/terminal-auth/` проверяет доступ к терминалу;
- открытие терминала стажера наставником логируется;
- исторические попытки открываются в read-only режиме;
- точечные тесты по измененной области проходят успешно.
