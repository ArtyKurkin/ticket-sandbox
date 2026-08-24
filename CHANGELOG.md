# CHANGELOG

Журнал изменений Ticket Sandbox.

Формат ведения простой: фиксируем крупные изменения по неделям, чтобы было понятно, как развивался проект и какие архитектурные решения уже приняты.

## Неделя 1 — Базовый MVP тренажера

### Добавлено

- Создан Django-проект Ticket Sandbox.
- Подключена PostgreSQL-база через Docker Compose.
- Добавлено приложение `sandbox`.
- Добавлены базовые модели:
  - `Task` — учебное задание;
  - `TaskAttempt` — попытка прохождения задания стажером.
- Добавлена авторизация через стандартные механизмы Django.
- Реализован дашборд стажера со списком учебных заданий.
- Реализована страница отдельного задания.
- Добавлена базовая логика прохождения:
  - запуск задания;
  - отправка ответа на проверку;
  - хранение статуса попытки;
  - хранение ответа клиенту;
  - хранение внутреннего комментария.
- Добавлена первая структура учебных Docker-заданий в `training_tasks/`.
- Реализован запуск task-контейнера для отдельной попытки.
- Добавлен ttyd-терминал для работы с окружением задания.
- Добавлен вывод команды подключения к контейнеру для наставника.
- Добавлена первая автопроверка через `check.sh`.

### Исправлено

- Настроено подключение Django к PostgreSQL.
- Исправлены проблемы с локальным и Docker PostgreSQL на одном порту.
- Отработана базовая схема запуска Docker-контейнеров из Django.

---

## Неделя 2 — UI, терминал и стабильность попыток

### Добавлено

- Сделан dark UI для Ticket Sandbox.
- Добавлены отдельные шаблоны:
  - `base.html`;
  - `trainee_dashboard.html`;
  - `task_detail.html`;
  - `mentor_dashboard.html`;
  - `registration/login.html`.
- Подключены Lucide-иконки.
- Вынесены стили в `static/css/main.css`.
- Вынесена логика интерфейса в `static/js/app.js`.
- Добавлена инициализация Lucide через JS.
- Добавлена модалка терминала.
- Добавлена очистка iframe терминала перед переходами и отправкой форм.
- Добавлена кнопка перезапуска задания для стажера.
- Добавлены карточки:
  - «Работа с тикетом»;
  - «Терминал сервера»;
  - «Проверка»;
  - «Сообщение клиента»;
  - «Ответ и диагностика».
- Разделены CSS-классы для клиентского сообщения и системных flash-сообщений, чтобы стили не конфликтовали.
- Настроен `STATICFILES_DIRS`.
- Добавлена более аккуратная двухколоночная страница тикета.

### Исправлено

- Исправлена проблема, когда статика не подтягивалась без `STATICFILES_DIRS`.
- Исправлен конфликт классов `.message`.
- Исправлен визуальный блок сообщения клиента.
- Исправлена логика удаления старого task-контейнера при перезапуске задания.
- Добавлена идемпотентность запуска задания: повторное нажатие «Начать работу» не должно ломать контейнеры.
- Добавлен `EXTERNAL_HOST` из env.
- Добавлены `STATIC_ROOT` и `ManifestStaticFilesStorage`.
- Добавлен `ALLOWED_HOSTS` из env с дефолтным значением.
- Исправлены расстояния между кнопками в карточке работы с тикетом.

---

## Неделя 3 — Очереди, уровни и правки после ревью

### Архитектурные решения

- Принято решение убрать отдельную сущность `trainee`.
- Стажер считается претендующим на L1 и решает задачи в очереди `l1`.
- Кандидат получает отдельную очередь `candidate`.
- Фича эскалации на наставника убрана из roadmap.
- Наставник определяется через `User.is_staff`.
- `TraineeProfile.is_mentor` больше не хранится отдельным полем в БД.

### Добавлено

- Добавлена модель `Queue`.
- Добавлена привязка `Task → Queue`.
- Добавлены очереди:
  - `candidate`;
  - `l1`;
  - `l2`;
  - `admin`.
- Добавлена логика доступа к очередям по уровню пользователя:
  - `candidate` видит только `candidate`;
  - `l1` видит `l1`;
  - `l2` видит `l1` и `l2`;
  - `admin` видит все очереди.
- Добавлен `TraineeProfile` с уровнями:
  - `candidate`;
  - `l1`;
  - `l2`;
  - `admin`.
- Добавлен signal для автоматического создания `TraineeProfile` при создании пользователя.
- Реструктурированы учебные задания в `training_tasks/<queue_slug>/<task_slug>/`.
- Docker-сервис начал использовать `queue.slug` в путях и именах контейнеров.
- Добавлен constraint для уникальности `slug` задания внутри очереди.
- Добавлен `priority` через `TextChoices`:
  - `low`;
  - `medium`;
  - `high`;
  - `critical`.

### Исправлено

- Убран `trainee` из `LEVEL_ACCESS`.
- Создана отдельная очередь `candidate`.
- Текущие учебные задачи перенесены в очередь `l1`.
- `Task.queue` сделан обязательным.
- Удалено поле `Task.queue_name`, потому что оно дублировало `task.queue.name`.
- Исправлен `priority`, теперь в админке нельзя ввести произвольную строку.
- Устранен риск рассинхрона между `is_staff` и `is_mentor`.
- Проверено, что задач без очереди нет.
- Проверено, что очередь `trainee` больше не используется.

### Технический долг

- Добавить нормальную защиту терминала.
- Перевести ttyd за reverse proxy или terminal gateway.
- Добавить лимиты ресурсов на Docker-контейнеры.
- Вынести тяжелые Docker-операции в Celery + Redis.
- Добавить ручную проверку качества ответа клиенту.
- Добавить аналитику по прохождению заданий.

---

## Неделя 4 — Тесты, история проверок и документация

### Добавлено

- Добавлен набор автоматических тестов для приложения `sandbox`.
- Тесты разнесены по отдельной директории `sandbox/tests/`.
- Добавлен общий базовый класс `SandboxTestCase` для тестов.
- Добавлены тесты на автоматическое создание `TraineeProfile`.
- Добавлены тесты на доступ к очередям:
  - `candidate`;
  - `l1`;
  - `l2`;
  - `admin`.
- Добавлены тесты на последовательное открытие заданий.
- Добавлены тесты на запрет доступа к чужим попыткам.
- Добавлены тесты на запуск, проверку и перезапуск заданий.
- Добавлены тесты на обязательность авторизации для dashboard, страницы тикета и action-view.
- Добавлены тесты на модельные ограничения:
  - обязательный `Task.queue`;
  - уникальность `Task.slug` внутри очереди;
  - возможность использовать одинаковый `slug` в разных очередях;
  - проверку `priority` через choices;
  - связь наставника с `User.is_staff`.
- Добавлены smoke-тесты для management commands:
  - `build_task_images`;
  - `cleanup_task_containers`.
- Добавлен `Makefile`-target `validate` для локальной проверки проекта.
- Добавлена модель `CheckRun` для хранения истории запусков автопроверки.
- Добавлена запись `CheckRun` при каждой отправке задания на проверку.
- История проверок выведена на странице тикета.
- История проверок добавлена в админку внутри `TaskAttempt` через inline.
- Добавлен отдельный раздел `CheckRun` в админке.
- Улучшен dashboard наставника:
  - добавлена очередь задания;
  - добавлен статус попытки;
  - добавлено количество проверок;
  - добавлено количество перезапусков;
  - добавлен последний результат проверки.
- Добавлен `README.md`.
- Добавлен `CONTRIBUTING.md` с инструкцией по созданию новых задач.
- Добавлен `ARCHITECTURE.md` с описанием связи Django, Docker, task-контейнеров, ttyd и автопроверки.
- Добавлен `CHANGELOG.md`.

### Исправлено

- Исправлена сборка Docker-образов под новую структуру `training_tasks/<queue_slug>/<task_slug>`.
- Команда `build_task_images` теперь учитывает очередь задания.
- Исправлены тесты под `ManifestStaticFilesStorage`, чтобы они не требовали `collectstatic`.
- Исправлены тестовые helpers для очередей и заданий, чтобы они не падали на уже созданных миграциями данных.
- Исправлены тесты авторизации: редирект теперь проверяется через фактический `settings.LOGIN_URL`, а не через захардкоженный `/accounts/login/`.
- В админке запрещено ручное добавление `CheckRun` через inline, чтобы история проверок создавалась только системой.

### Проверки

- `python manage.py check` проходит успешно.
- `python manage.py makemigrations --check --dry-run` проходит успешно.
- `python manage.py test sandbox` проходит успешно.
- `make validate` проходит успешно.

### Технический долг

- Добавить нормальную защиту терминала.
- Перевести ttyd за reverse proxy или terminal gateway.
- Добавить лимиты ресурсов на Docker-контейнеры.
- Вынести тяжелые Docker-операции в Celery + Redis.
- Добавить механику ручной проверки качества ответа клиенту.
- Добавить аналитику по стажерам и заданиям.
- Улучшить mentor dashboard фильтрами по стажеру, очереди и статусу.

---

## Неделя 5 — Ручная проверка, прогресс и разделение технической сдачи от текста

### Архитектурные решения

- Закреплено разделение:
  - `check.sh` проверяет техническую часть;
  - наставник проверяет только ответ клиенту.
- Успешная техническая сдача теперь фиксируется отдельно через `TaskAttempt.technical_passed_at`.
- Если `technical_passed_at` заполнен, техническая часть считается выполненной.
- Если наставник отправил ответ на доработку, стажер правит только текст.
- При доработке текста Docker-контейнер и `check.sh` повторно запускать не нужно.
- Стажер может переходить к следующей задаче после успешной технической сдачи.
- Ручная проверка наставника не должна откатывать технический прогресс.
- Basic Auth для ttyd не используется.
- Временная защита ttyd — bind на `127.0.0.1`.
- Долгосрочное решение для терминала — reverse proxy через Django или nginx.

### Добавлено

- Добавлено поле `TaskAttempt.mentor_feedback`.
- Добавлено поле `TaskAttempt.mentor_decision`.
- Добавлены поля:
  - `mentor_reviewed_by`;
  - `mentor_reviewed_at`.
- Добавлено поле `TaskAttempt.mentor_feedback_seen_at`.
- Добавлено поле `Task.requires_manual_review`.
- Добавлено поле `TaskAttempt.technical_passed_at`.
- Добавлена ручная проверка ответа клиенту наставником.
- Добавлена возможность наставнику принять ответ или отправить его на доработку.
- Добавлен комментарий наставника к попытке.
- Добавлен баннер новых комментариев наставника для стажера.
- Добавлена фиксация просмотра комментария наставника.
- Добавлен прогресс по очереди на дашборде стажера.
- Добавлена логика, при которой прогресс зависит от успешной технической проверки.
- Улучшен mentor dashboard:
  - добавлена статистика;
  - добавлены фильтры;
  - добавлена ручная проверка;
  - добавлено отображение статусов проверки.
- Добавлены тесты для mentor dashboard.
- Добавлены тесты для CheckRun.
- Добавлены тесты для Docker service.
- Добавлены тесты для template filters.

### Исправлено

- Ручная проверка ответа отделена от технической автопроверки.
- Доработка ответа наставником больше не должна восприниматься как необходимость заново проходить техническую часть.
- Успешное прохождение технической части стало храниться отдельно от общего статуса попытки.
- Логика открытия следующего задания теперь может опираться на `technical_passed_at`.
- Уточнена логика прогресса по очереди.
- ttyd больше не пробрасывается наружу напрямую: порт привязан к `127.0.0.1`.
- Убран вариант с Basic Auth для ttyd как нежелательное промежуточное решение.

### Документация

- Обновлен `README.md` под текущее состояние проекта.
- Обновлен `ARCHITECTURE.md`:
  - добавлено разделение технической проверки и ручной проверки ответа;
  - описан `TaskAttempt.technical_passed_at`;
  - описан `Task.requires_manual_review`;
  - описаны поля ручной проверки наставником;
  - описан прогресс по очереди;
  - описана текущая защита ttyd через bind на localhost.
- Обновлен `CONTRIBUTING.md`:
  - добавлены правила по ручной проверке;
  - добавлены правила по `technical_passed_at`;
  - добавлен запрет на возврат `trainee`-очереди;
  - добавлено правило не использовать Basic Auth для ttyd;
- Обновлен `CHANGELOG.md`.

### Проверки

Перед фиксацией состояния нужно выполнить:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test sandbox
```

Или:

```bash
make validate
```

### Технический долг

- Добавить защиту от случайного повторного прохождения после успешной технической сдачи.
- Если `technical_passed_at` заполнен, обычные start/restart действия не должны сбрасывать попытку.
- Для повторного прохождения нужна отдельная осознанная кнопка.
- Повторное прохождение должно создавать новую `TaskAttempt`, а не ломать старую успешную попытку.
- Прогресс по очереди не должен откатываться, если у стажера уже была успешная техническая попытка.
- Вынести тяжелые Docker-операции в Celery + Redis.
- Сделать безопасный terminal gateway через Django или nginx.
- Добавить лимиты Docker-контейнеров:
  - memory;
  - CPU;
  - pids;
  - tmpfs.
- Добавить timeout на выполнение `check.sh`.
- Расширить аналитику по стажерам и заданиям.
- Добавить больше учебных задач.

---

## Неделя 6 — Terminal gateway, повторные попытки и стабилизация перед staging

### Архитектурные решения

- Terminal gateway закреплен как основная схема доступа к ttyd через nginx `auth_request`.
- Прямой внешний доступ к ttyd-портам не используется.
- Локально проект с терминалом запускается через связку:
  - Django dev server на `127.0.0.1:8000`;
  - nginx gateway на `localhost:8081`.
- Исторические попытки считаются read-only.
- Action-view для `start`, `restart` и `check` должны работать только с текущей попыткой `is_current=True`.
- Повторное прохождение после успешной технической сдачи выполняется через отдельную тренировочную попытку, а не через сброс зачётной.
- Тяжелые Docker-операции пока остаются синхронными в Django view, но должны быть защищены от зависаний и базовых ошибок Docker API.
- Полный `make validate` используется как quality gate перед ревью, архивом или деплоем.
- Во время разработки запускаются точечные тесты по измененной области.

### Добавлено

- Добавлен безопасный terminal gateway через nginx `auth_request`.
- Добавлен endpoint `/terminal-auth/` для проверки доступа к терминалу.
- Добавлена передача исходного terminal URI через заголовок `X-Original-URI`.
- Добавлено WebSocket-проксирование терминала через nginx.
- Добавлены локальные nginx-команды в Makefile:
  - `make nginx-test`;
  - `make nginx-start`;
  - `make nginx-reload`;
  - `make nginx-stop`;
  - `make nginx-logs`.
- Добавлены быстрые группы тестов:
  - `make test-terminal`;
  - `make test-actions`;
  - `make test-docker`;
  - `make test-dashboards`.
- Добавлена настройка `CHECK_TASK_TIMEOUT_SECONDS` для ограничения времени выполнения `check.sh`.
- `check.sh` запускается через `timeout --kill-after=5s`.
- Добавлена базовая обработка ошибок Docker API в action-view:
  - `start_task`;
  - `restart_task`;
  - `check_task`.
- При ошибках Docker API попытка переводится в `failed`, а понятное описание сохраняется в `last_check_output`.
- Добавлена защита от действий с историческими попытками во view.
- Добавлен read-only режим исторических попыток в интерфейсе.
- Добавлена плашка для исторической попытки: «Только просмотр».
- Добавлена кнопка копирования shell-команды для наставника.
- Добавлен бейдж о необходимости ручной проверки наставника для задач с `requires_manual_review=True`.
- Добавлен audit-лог `mentor_terminal_access`, когда наставник открывает терминал стажера.
- Добавлено логирование отказов terminal-auth с причинами.
- Добавлено логирование ключевых действий с окружением:
  - запуск;
  - перезапуск;
  - успешная проверка;
  - неуспешная проверка;
  - ошибки запуска окружения;
  - ошибки перезапуска окружения;
  - ошибки запуска автопроверки.
- Добавлен `DB_ENGINE` в настройки Django, чтобы CI мог использовать SQLite.
- CI переведен на запуск полного набора тестов приложения.
- Добавлены тесты для повторных и исторических попыток.
- Добавлены тесты для UI-бейджа ручной проверки.
- Добавлен тест на audit-лог открытия терминала наставником.
- Добавлены тесты для cleanup, чтобы не трогать технически пройденные попытки.
- Добавлены тесты для timeout автопроверки.
- Добавлены тесты для обработки ошибок Docker API в `start_task`, `restart_task` и `check_task`.

### Исправлено

- Исправлен локальный запуск terminal gateway: проект с терминалом нужно открывать через `http://localhost:8081/`, а не напрямую через `http://127.0.0.1:8000/`.
- Исправлен nginx auth subrequest: исходный URI терминала передается в Django через `X-Original-URI`.
- Исправлена проблема с CSRF при локальном запуске через nginx: `Host` передается как `$http_host`.
- Исправлен regex порта в nginx-конфиге без использования `{4}`.
- Исправлено условие показа старого `mentor_feedback`: стажер не видит старый комментарий как актуальный, если `mentor_decision = not_reviewed`.
- Исправлена гонка в расчете следующего `attempt_number` через `select_for_update()`.
- Исправлено поведение `cleanup_task_containers`: команда не должна трогать попытки с заполненным `technical_passed_at`.
- Исправлено отображение исторических попыток: формы, терминал и команды окружения скрываются в read-only режиме.
- Исправлено поведение при зависании `check.sh`: проверка завершается по timeout и возвращает понятное сообщение.
- Исправлено поведение при ошибках Docker API: пользователь больше не получает 500 при ошибке запуска, перезапуска или автопроверки.
- Уточнены nginx example-конфиги: upstream `127.0.0.1:8000` помечен как пример, а не production-истина.

### Документация

- Обновлен `.env.example`:
  - добавлен `DB_ENGINE`;
  - добавлен `CHECK_TASK_TIMEOUT_SECONDS`.
- Обновлен `README.md`:
  - добавлен локальный запуск через nginx gateway;
  - добавлены Makefile-команды для nginx;
  - добавлены быстрые группы тестов;
  - добавлен `test_rerun_attempt.py`;
  - уточнен CI и `DB_ENGINE`;
  - добавлена настройка `CHECK_TASK_TIMEOUT_SECONDS`.
- Обновлен `ARCHITECTURE.md`:
  - описаны исторические попытки;
  - описан audit-лог открытия терминала наставником;
  - описан timeout для `check.sh`;
  - описана базовая обработка ошибок Docker API;
  - обновлены Makefile-команды и структура тестов.
- Обновлен `CONTRIBUTING.md`:
  - добавлены правила точечного запуска тестов;
  - обновлены правила terminal gateway;
  - обновлены правила повторных и исторических попыток;
  - добавлено правило учитывать timeout `check.sh`;
  - добавлено правило проверять обработку ошибок Docker API при изменении Docker-логики.
- Обновлен `CHANGELOG.md`.

### Проверки

Для точечных правок используются команды по области изменений:

```bash
make test-terminal
make test-actions
make test-docker
make test-dashboards
```

Для изменений terminal gateway:

```bash
make test-terminal
```

Для изменений action-view, повторных и исторических попыток:

```bash
make test-actions
```

Для изменений Docker service и management-команд:

```bash
make test-docker
```

Для изменений dashboard:

```bash
make test-dashboards
```

Перед ревью, архивом или деплоем нужно выполнить:

```bash
make validate
```

### Технический долг

- Вынести тяжелые Docker-операции в Celery + Redis.
- Добавить промежуточные фоновые статусы для запуска, проверки и перезапуска окружений.
- Добавить более детальную обработку ошибок Docker API для отдельных сценариев:
  - образ не найден;
  - контейнер не найден;
  - конфликт имени контейнера;
  - ошибка Docker daemon;
  - ошибка сборки образа.
- Подготовить production-инструкцию для nginx, TLS, cookies и безопасных заголовков.
- Добавить мониторинг и production-логирование.
- Улучшить аналитику по стажерам и заданиям.
- Добавить больше учебных задач.

---

---

## Неделя 7 — Подготовка к staging-деплою

### Архитектурные решения

- Staging/production-запуск проекта выполняется через связку:
  - Django application через gunicorn;
  - nginx как reverse proxy и terminal gateway;
  - PostgreSQL как основная база данных;
  - Docker для task-контейнеров и ttyd-терминала.
- `runserver` остается только для локальной разработки.
- Static-файлы в staging/production должны обслуживаться из `STATIC_ROOT` после выполнения `collectstatic`.
- Production-настройки Django включаются при `DEBUG=False`.
- Cleanup старых task/terminal-контейнеров должен запускаться регулярно через cron или systemd timer.
- Docker image для ttyd должен использовать фиксированную версию, а не `latest`.

### Добавлено

- Добавлен `gunicorn` в `requirements.txt`.
- Добавлена команда `make serve` для запуска Django через gunicorn.
- Добавлена переменная `CSRF_TRUSTED_ORIGINS` в `.env.example`.
- Добавлена поддержка `CSRF_TRUSTED_ORIGINS` через env в `settings.py`.
- Добавлены production security-настройки для режима `DEBUG=False`:
  - `SECURE_PROXY_SSL_HEADER`;
  - `SECURE_SSL_REDIRECT`;
  - `SESSION_COOKIE_SECURE`;
  - `CSRF_COOKIE_SECURE`;
  - `SECURE_HSTS_SECONDS`;
  - `SECURE_HSTS_INCLUDE_SUBDOMAINS`;
  - `SECURE_HSTS_PRELOAD` пока не включается автоматически для staging;
  - `SECURE_CONTENT_TYPE_NOSNIFF`;
  - `X_FRAME_OPTIONS = "SAMEORIGIN"`.
- Добавлен раздел `Деплой на сервер` в `README.md`.
- В README добавлен обязательный шаг `python manage.py collectstatic --noinput`.
- В README уточнено, что nginx должен смотреть на `staticfiles/`, а не на исходную директорию `static/`.
- Добавлен пример systemd unit для gunicorn:
  - `deploy/systemd/ticket-sandbox.service.example`.
- Добавлен пример cron для регулярной очистки контейнеров:
  - `deploy/cron/cleanup_task_containers.example`.
- Зафиксирована версия базового ttyd-образа в `terminal/Dockerfile`.

### Исправлено

- Исправлены переменные подключения к базе в `.env.example`: используются `DB_HOST` и `DB_PORT`, которые реально читает `settings.py`.
- Убрана зависимость terminal image от `tsl0922/ttyd:latest`.
- Уточнена staging/production-схема запуска: приложение запускается через gunicorn, а не через Django `runserver`.
- Уточнен порядок деплоя: установка зависимостей, миграции, `collectstatic`, сборка Docker-образов, запуск systemd, настройка nginx и cleanup.

### Документация

- Обновлен `README.md`:
  - добавлен раздел деплоя;
  - добавлен шаг `collectstatic`;
  - добавлена схема запуска через gunicorn и systemd;
  - добавлена настройка nginx;
  - добавлена регулярная очистка контейнеров;
  - добавлен staging checklist.
- Обновлен `.env.example` под staging/production.
- Добавлены deploy-примеры для systemd и cron.
- Обновлен `CHANGELOG.md`.

### Проверки

После деплойных правок нужно выполнить:

```bash
python manage.py check
python manage.py check --deploy
python manage.py test sandbox.tests.test_terminal_gateway sandbox.tests.test_task_actions
```

Перед staging-деплоем нужно выполнить полный quality gate:

```bash
make validate
```

### Технический долг

- Подготовить полноценную production-инструкцию под конкретный домен и сервер.
- Добавить systemd timer как альтернативу cron для cleanup.
- Добавить ротацию логов gunicorn/nginx/cleanup.
- Вынести тяжелые Docker-операции в Celery + Redis.
- Добавить фоновые статусы для запуска, проверки и перезапуска окружений.
---

## Неделя 8 — Staging CI/CD, sync_training_tasks и управление заданиями

### Архитектурные решения

- `training_tasks/<queue_slug>/<task_slug>/task.json` закреплен как источник правды для учебных заданий.
- Django admin используется для просмотра, фильтров, массовых действий и ручного запуска sync, но не как основной источник постоянных правок задания.
- `sync_training_tasks` стал частью delivery-процесса: новые и измененные задания должны попадать в БД через команду синхронизации.
- В CI и CD используется строгая проверка `training_tasks`: сломанные задания не должны молча пропускаться и уезжать на staging.
- Staging deploy выполняется через GitHub Actions после успешных тестов и только для ветки `main`.
- CD должен не только перезапускать сервис, но и показывать понятный summary по этапам деплоя.
- Smoke-check staging выполняется с GitHub runner, чтобы проверить доступность сервиса снаружи через nginx/HTTPS.
- `TaskAttempt.terminal_url` хранит относительный путь terminal gateway, поэтому поле должно быть `CharField`, а не `URLField`.

### Добавлено

- Доработана команда `sync_training_tasks`:
  - добавлен понятный summary для обычного режима;
  - добавлен понятный summary для `--dry-run`;
  - добавлен режим `--strict`;
  - добавлена валидация `task.json`;
  - некорректный JSON, неправильные типы полей и некорректный `priority` теперь останавливают команду;
  - в strict-режиме команда падает, если хотя бы одно задание было пропущено.
- Добавлена admin-страница для синхронизации `training_tasks`:
  - GET выполняет `sync_training_tasks --dry-run --strict`;
  - POST выполняет `sync_training_tasks --strict`;
  - при ошибке dry-run кнопка применения не показывается;
  - доступ к запуску sync ограничен superuser.
- Добавлена кнопка `Синхронизировать training_tasks` на странице списка заданий в Django admin.
- Добавлены тесты для `sync_training_tasks`:
  - создание задачи из `task.json`;
  - `--dry-run` без записи в БД;
  - обновление существующей задачи;
  - skip без `Dockerfile`;
  - skip без `check.sh`;
  - skip при отсутствующей очереди;
  - ошибка при некорректном `task.json`;
  - ошибка при неправильном `priority`;
  - ошибка strict-режима при skipped tasks;
  - корректный summary для dry-run create/update.
- Добавлены тесты для admin sync-страницы:
  - dry-run для superuser;
  - apply sync для superuser;
  - запрет доступа для staff без superuser;
  - скрытие кнопки применения при ошибке dry-run.
- Добавлена проверка `sync_training_tasks --dry-run --strict` в CI.
- Добавлена команда `make sync-check`.
- `make validate` теперь включает `sync-check`.
- В CD добавлена сборка Docker-образов заданий через `python manage.py build_task_images`.
- В CD добавлен GitHub Actions summary по шагам staging deploy:
  - pull latest code;
  - migrations;
  - sync training tasks;
  - build task images;
  - collectstatic;
  - restart service;
  - systemd status;
  - staging smoke-check.
- В CD добавлен staging smoke-check:
  - проверка главной страницы;
  - проверка `/admin/login/`.
- Добавлен secret `STAGING_URL` для проверки staging из GitHub Actions.
- Добавлен deploy-check в CI через `python manage.py check --deploy`.
- Улучшены `TaskAdmin` и `QueueAdmin`:
  - редактируемый `order`;
  - сортировка;
  - фильтры;
  - массовые actions для включения/выключения заданий;
  - массовые actions для включения/отключения ручной проверки.
- Добавлен `sandbox/tests/test_admin.py`.

### Изменено

- `TaskAttempt.terminal_url` изменен с `URLField` на `CharField(max_length=255)`, потому что в режиме terminal gateway хранится относительный путь вида `/terminal/<attempt_id>/<port>/`.
- CD-порядок staging deploy уточнен:
  - `git pull --ff-only`;
  - установка зависимостей;
  - `migrate`;
  - `sync_training_tasks --strict`;
  - `build_task_images`;
  - `collectstatic`;
  - restart `ticket-sandbox`;
  - smoke-check staging.
- Admin sync-страница переведена на strict-режим, чтобы поведение совпадало с CI/CD.
- `sync_training_tasks --dry-run` теперь считает `would_create` и `would_update`, а не показывает нули из-за того, что dry-run ничего не записывает.
- `test-dashboards` в Makefile обновлен и больше не должен ссылаться на несуществующий тестовый модуль.
- README, CONTRIBUTING и ARCHITECTURE обновлены под новый процесс добавления заданий через `task.json` и `sync_training_tasks`.
- В документации зафиксировано, что постоянные правки задания нужно делать в `task.json`, а не руками в Django admin.
- В staging/CD закреплено, что `collectstatic` выполняется до рестарта systemd-сервиса.

### Исправлено

- Исправлен риск, при котором `sync_training_tasks` мог молча пропустить сломанную папку задания в CD.
- Исправлен риск, при котором задача могла появиться в БД, но Docker-образ задания не был собран на staging.
- Исправлена потенциальная проблема с `terminal_url`: относительный путь больше не хранится в поле, рассчитанном на полноценный URL.
- Исправлена ошибка CI `sqlite3.OperationalError: no such table: sandbox_queue` для проверки `sync_training_tasks`: перед sync-check в CI выполняются миграции на временной SQLite-базе.
- Исправлен тест admin sync-страницы, который слишком жестко зависел от форматирования flash-message в Django admin.
- Исправлен риск непрозрачного деплоя: теперь в GitHub Actions summary видно, какой именно шаг прошел или упал.
- Исправлен риск случайной ручной правки задания в админке без фиксации в файлах: документация явно предупреждает, что следующий sync применит значения из `task.json`.

### Документация

- Обновлен `README.md`:
  - добавлено описание `task.json`;
  - добавлен процесс `sync_training_tasks --dry-run` → `sync_training_tasks`;
  - уточнено, что задания не создаются вручную в admin;
  - добавлен `sync_training_tasks` в staging/deploy flow.
- Обновлен `CONTRIBUTING.md`:
  - добавлено правило `task.json` как источника правды;
  - добавлена проверка `sync_training_tasks --dry-run`;
  - добавлена команда `sync_training_tasks` в список management-команд;
  - уточнены правила работы с admin.
- Обновлен `ARCHITECTURE.md`:
  - описана роль `training_tasks` и `task.json`;
  - описана синхронизация заданий с БД;
  - зафиксировано разделение code/files как источника задания и admin как оперативного интерфейса.
- CHANGELOG обновлен под фактическую staging/CD-пачку.

### Проверки

Точечные проверки для этой пачки:

```bash
python manage.py test sandbox.tests.test_admin
python manage.py test sandbox.tests.test_management_commands
make sync-check
```

Полная проверка перед push/review/deploy:

```bash
make validate
```

Deploy-check:

```bash
DEBUG=False \
SECRET_KEY=ci-deploy-check-secret-key-with-enough-length-and-variety-2026 \
ALLOWED_HOSTS=example.com \
CSRF_TRUSTED_ORIGINS=https://example.com \
DB_ENGINE=django.db.backends.sqlite3 \
DB_NAME=:memory: \
TERMINAL_GATEWAY_ENABLED=true \
CHECK_TASK_TIMEOUT_SECONDS=60 \
python manage.py check --deploy
```

Ожидаемые предупреждения на текущем этапе:

- `security.W019` — ожидаемо, потому что используется `X_FRAME_OPTIONS = "SAMEORIGIN"` для терминала в iframe на том же origin.
- `security.W021` — ожидаемо, потому что `SECURE_HSTS_PRELOAD=True` пока не включается автоматически для staging.

### Технический долг

- Добавить уведомления о результате CD в Telegram, если это станет нужно.
- Улучшить визуальный вывод admin sync-страницы: отдельно подсвечивать `WOULD CREATE`, `WOULD UPDATE`, `SKIP` и финальный summary.
- Добавить больше учебных заданий в `training_tasks`.
- Проверить полный сценарий на staging вручную:
  - вход стажером;
  - вход наставником;
  - запуск задания;
  - терминал в iframe;
  - `check.sh`;
  - ручная проверка;
  - повторная тренировочная попытка;
  - историческая попытка read-only;
  - cleanup контейнеров.
- Вынести тяжелые Docker-операции в Celery + Redis.
- Добавить фоновые статусы для долгих операций запуска, проверки и перезапуска.
- Подготовить production-инструкцию под конкретный домен и сервер.
---

## Неделя 9 — L1-задания, healthcheck, staging checklist и Telegram-уведомления

### Архитектурные решения

- Первый staging-пилот должен проверяться не только тестами, но и ручным пользовательским сценарием по `STAGING_CHECKLIST.md`.
- `/healthz/` добавлен как простой endpoint для smoke-check после деплоя.
- Telegram-уведомления считаются необязательным побочным эффектом: если токен или chat id не заданы, тренажер работает без уведомлений.
- Ошибки Telegram API не должны ломать основной сценарий стажера или наставника.
- Уведомления о событиях отправляются после успешного сохранения состояния через `transaction.on_commit(...)`.
- Уведомление «требуется ручная проверка» отправляется только когда попытка реально перешла в `on_review`.
- Бейдж «Ждут проверки» в mentor dashboard считается отдельно от текущих фильтров, чтобы наставник видел общий объем ожидающих проверок.

### Добавлено

- Добавлен первый полноценный L1-пакет из 10 заданий:
  - `nginx_not_starting`;
  - `sajt-ne-rabotaet-posle-perenosa`;
  - `disk-full`;
  - `cron-not-working`;
  - `php-fpm-down`;
  - `nginx-413-upload`;
  - `wordpress-500-after-move`;
  - `restored-backup-permissions`;
  - `port-already-in-use`;
  - `deleted-file-descriptor`.
- Добавлен healthcheck endpoint `/healthz/`.
- Добавлен тест `sandbox/tests/test_healthcheck.py`.
- В GitHub Actions staging smoke-check добавлена проверка `/healthz/`.
- Добавлен `STAGING_CHECKLIST.md` для ручной проверки staging после деплоя.
- Добавлен сервис Telegram-отправки `sandbox/services/telegram.py`.
- Добавлены переменные окружения:
  - `TELEGRAM_BOT_TOKEN`;
  - `TELEGRAM_CHAT_ID`.
- Добавлен сервис бизнес-уведомлений `sandbox/services/notifications.py`.
- Добавлено уведомление наставникам, когда попытка отправлена на ручную проверку.
- Добавлено уведомление наставникам, когда стажер технически прошел все активные задания в доступных очередях.
- Добавлены тесты `sandbox/tests/test_telegram_notifications.py`.
- Уведомления подключены к `check_task` через `transaction.on_commit(...)`.
- В mentor dashboard добавлен бейдж «Ждут проверки».
- Добавлен подсчет `pending_review_count` в `sandbox/services/mentor_dashboard.py`.
- Добавлены CSS-стили для бейджа и адаптивного hero-заголовка.

### Изменено

- Уточнен staging checklist под текущий flow: сначала техническая сдача через `check.sh`, потом заполнение ответа клиенту и внутреннего комментария для задач с ручной проверкой.
- README обновлен под Telegram-уведомления, `/healthz/`, `sync-check`, strict sync и staging smoke-check.
- ARCHITECTURE обновлен под фактический flow ручной проверки после технической сдачи.
- CONTRIBUTING обновлен правилами по Telegram-уведомлениям, мокам внешних HTTP-вызовов и актуальным списком тестов.
- Документация по тестам обновлена: удалена ссылка на несуществующий `test_trainee_dashboard.py`, добавлены актуальные тестовые модули.

### Исправлено

- Закрыт технический долг недели 8 по отдельному healthcheck endpoint.
- Исправлен риск, что наставник не заметит новые попытки на ручной проверке без постоянного открытого dashboard.
- Исправлен рассинхрон в документации, где ответ клиенту и внутренний комментарий описывались как обязательные до запуска `check.sh`.
- Исправлен staging checklist: команда `cleanup_task_containers --dry-run` убрана из обязательных проверок, потому что dry-run для этой команды пока не реализован.

### Документация

- Обновлен `README.md`.
- Обновлен `ARCHITECTURE.md`.
- Обновлен `CONTRIBUTING.md`.
- Обновлен `CHANGELOG.md`.
- Обновлен `STAGING_CHECKLIST.md`.

### Проверки

Точечные проверки для этой пачки:

```bash
python manage.py test sandbox.tests.test_healthcheck
python manage.py test sandbox.tests.test_telegram_notifications
python manage.py test sandbox.tests.test_task_actions
python manage.py test sandbox.tests.test_mentor_dashboard
python manage.py check
```

Полная проверка перед push/review/deploy:

```bash
make validate
```

### Технический долг

- Добавить polling статуса проверки.
- Вынести тяжелые Docker-операции в Celery + Redis.
- Добавить фоновые статусы для долгих операций запуска, проверки и перезапуска.
- Добавить `--dry-run` для `cleanup_task_containers`, если понадобится безопасная проверка очистки на staging.
- Настроить реальные Telegram env на staging, если уведомления нужны в пилоте.
- Пройти полный staging checklist на реальных стажерских и наставнических пользователях.

---
---

## Неделя 10 — Background lifecycle, watchdog, Sentry и эксплуатационная готовность

### Архитектурные решения

- Запуск окружения, перезапуск окружения и автопроверка больше не должны держать пользовательский HTTP-запрос до завершения Docker-операции.
- Для долгих операций используется промежуточный background lifecycle:
  - `environment_status` для запуска и перезапуска окружения;
  - `check_status` для автопроверки.
- Frontend получает актуальный статус через polling endpoint и обновляет страницу без ручного refresh.
- Так как текущая background-реализация использует `threading.Thread`, добавлен watchdog для восстановления зависших состояний после рестарта gunicorn/сервиса, OOM или падения worker-процесса.
- Зависшие попытки определяются не по тексту `last_check_output`, а через явное поле `TaskAttempt.stuck_reason`.
- Sentry подключается только при наличии `SENTRY_DSN` и используется для ошибок Django и background-wrapper-ов.
- Технический вывод удаления контейнеров после успешной автопроверки не показывается стажёру, а пишется в application logs.

### Добавлено

- Добавлен lifecycle автопроверки:
  - `TaskAttempt.CheckStatus.IDLE`;
  - `TaskAttempt.CheckStatus.RUNNING`;
  - `TaskAttempt.CheckStatus.PASSED`;
  - `TaskAttempt.CheckStatus.FAILED`;
  - `TaskAttempt.CheckStatus.ERROR`.
- Добавлены поля автопроверки:
  - `check_status`;
  - `check_started_at`;
  - `check_finished_at`.
- Логика автопроверки вынесена в `sandbox/services/checks.py`.
- Добавлен background-запуск автопроверки через `start_attempt_check_in_background`.
- Добавлена защита от повторного запуска автопроверки через атомарный `try_mark_attempt_check_running`.
- Добавлен endpoint статуса автопроверки.
- Добавлен polling статуса автопроверки в `static/js/app.js`.
- Добавлен lifecycle окружения:
  - `TaskAttempt.EnvironmentStatus.IDLE`;
  - `TaskAttempt.EnvironmentStatus.STARTING`;
  - `TaskAttempt.EnvironmentStatus.READY`;
  - `TaskAttempt.EnvironmentStatus.RESTARTING`;
  - `TaskAttempt.EnvironmentStatus.ERROR`.
- Добавлены поля окружения:
  - `environment_status`;
  - `environment_started_at`;
  - `environment_finished_at`.
- Логика запуска и перезапуска окружения вынесена в `sandbox/services/environments.py`.
- `start_task` переведён на background-запуск окружения.
- `restart_task` переведён на background-перезапуск окружения.
- Добавлен endpoint статуса окружения.
- Добавлен polling статуса окружения в `static/js/app.js`.
- Добавлены UI-состояния:
  - «Окружение запускается»;
  - «Окружение перезапускается»;
  - «Окружение не запустилось»;
  - «Проверка выполняется».
- Добавлен backoff для polling после нескольких подряд сетевых ошибок.
- Добавлена management command `detect_stuck_attempts`.
- Для `detect_stuck_attempts` добавлен `--dry-run`.
- Добавлен cron example `deploy/cron/detect_stuck_attempts.example`.
- Добавлено поле `TaskAttempt.stuck_reason`.
- Watchdog заполняет `stuck_reason=environment` или `stuck_reason=check`.
- Mentor dashboard считает зависшие попытки через `stuck_reason`.
- В mentor dashboard добавлен бейдж зависших попыток за последние 24 часа.
- В Django admin для `TaskAttempt` добавлены `environment_status`, `check_status`, `stuck_reason`.
- В Django admin добавлены фильтры по `environment_status`, `check_status`, `stuck_reason`.
- В Django admin добавлены actions для сброса статуса окружения и автопроверки.
- Добавлено Telegram-уведомление о зависших попытках, найденных watchdog.
- Добавлен race-fix в `get_current_attempt` через обработку `IntegrityError`.
- Добавлена Sentry-интеграция через `sentry-sdk[django]`.
- Добавлены env-переменные:
  - `SENTRY_DSN`;
  - `SENTRY_ENVIRONMENT`;
  - `SENTRY_RELEASE`;
  - `SENTRY_TRACES_SAMPLE_RATE`.
- В background-wrapper-ы окружения и автопроверки добавлен `capture_exception(error)`.
- Добавлен тестовый модуль `sandbox/tests/test_checks_service.py`.
- Добавлены тесты для background Sentry capture.
- Добавлены тесты для watchdog, `stuck_reason`, admin visibility/actions, mentor dashboard и recovery-сценариев.

### Изменено

- POST `check_task` больше не ждёт завершения `check.sh`, а запускает проверку в фоне.
- POST `start_task` больше не ждёт полного создания окружения, а запускает создание в фоне.
- POST `restart_task` больше не ждёт полного пересоздания окружения, а запускает перезапуск в фоне.
- UI страницы задания теперь зависит от `environment_status` и `check_status`.
- Автопроверка запрещена, если окружение находится в `starting`, `restarting` или `error`.
- Start/restart защищены от повторного запуска, если окружение уже `starting` или `restarting`.
- После `environment_status=error` разрешён recovery через перезапуск окружения.
- При перезапуске окружения сбрасываются `finished_at`, `check_status`, timestamps автопроверки и `stuck_reason`.
- `cleanup_task_containers` сбрасывает environment/check lifecycle-поля и `stuck_reason`.
- После успешной автопроверки `last_check_output` содержит только вывод `check.sh`, без строк про удаление контейнеров.
- Технический результат удаления task/terminal-контейнеров теперь пишется в `sandbox.terminal` logs.
- `requirements.txt` обновлён зависимостью `sentry-sdk[django]`.
- `.env.example` обновлён Sentry-переменными.

### Исправлено

- Закрыт риск вечного зависания попытки в `check_status=running`, если background thread оборвался.
- Закрыт риск вечного зависания попытки в `environment_status=starting/restarting`, если background thread оборвался.
- Закрыт риск, что mentor dashboard перестанет считать stuck-попытки из-за изменения текста `last_check_output`.
- Закрыт race condition при одновременном создании текущей попытки.
- Закрыт риск двойного запуска автопроверки по двойному клику.
- Закрыт риск запуска автопроверки во время запуска или перезапуска окружения.
- Закрыт риск показа кнопки автопроверки при ошибке окружения.
- Закрыт риск, что `finished_at` останется заполненным после recovery-перезапуска окружения.
- Убран технический шум про удаление контейнеров из интерфейса стажёра.

### Документация

- README сокращён до входной точки проекта, без попытки хранить всю архитектуру в одном файле.
- Обновлён `ARCHITECTURE.md`:
  - background lifecycle;
  - polling;
  - watchdog;
  - `stuck_reason`;
  - Sentry;
  - скрытие cleanup-output от стажёра.
- Обновлён `CONTRIBUTING.md`:
  - правила для background lifecycle;
  - правила для watchdog;
  - правила для Sentry;
  - правило не показывать стажёру инфраструктурный cleanup-output;
  - актуальные точечные тесты.
- Обновлён `STAGING_CHECKLIST.md`:
  - проверки `environment_status`;
  - проверки `check_status`;
  - проверки polling;
  - проверки watchdog cron;
  - проверки Sentry;
  - проверка отсутствия cleanup-output в интерфейсе стажёра.
- Обновлён `CHANGELOG.md`.

### Проверки

Точечные проверки для этой пачки:

```bash
python manage.py test sandbox.tests.test_environment_service
python manage.py test sandbox.tests.test_checks_service
python manage.py test sandbox.tests.test_task_actions
python manage.py test sandbox.tests.test_management_commands
python manage.py test sandbox.tests.test_mentor_dashboard
python manage.py test sandbox.tests.test_admin
python manage.py test sandbox.tests.test_telegram_notifications
python manage.py check
```

Полная проверка перед push/review/deploy:

```bash
make validate
```

### Технический долг

- Вынести background thread-операции в Celery + Redis.
- Добавить более детальные типы ошибок Docker API.
- Настроить реальные Sentry DSN/env на staging.
- Проверить watchdog cron на staging после деплоя.
- Проверить Sentry-события для background-ошибок на staging.
- Добавить аналитику по времени запуска окружения и времени автопроверки.
- Подумать над структурированной оценкой ответа клиенту.
- Добавить hints для сложных заданий.
- Добавить SLA-таймер для учебных тикетов.

---


## Неделя 11 — Основа Дневника стажёра

### Архитектурные решения

- Дневник стажёра реализован как отдельное приложение `traineediary` внутри проекта Ticket Sandbox.
- Приложения используют общую базу данных, стандартный `auth.User` и `sandbox.TraineeProfile`.
- Доступ к Дневнику разрешён только пользователям с `User.is_staff=True`.
- Сотрудники Дневника получают уровень `l1`.
- Для интеграции с Ticket Sandbox используется очередь `l1`, а не очередь кандидатов.
- Для новой адаптации установлен срок 90 дней.
- Для внутреннего перехода установлен срок 30 дней.

### Добавлено

- Добавлено приложение `traineediary`.
- Добавлены основные модели:
  - `TraineeStage`;
  - `TraineeJourney`;
  - `StageHistory`.
- Добавлены типы входа:
  - новая адаптация;
  - внутренний переход.
- Добавлен справочник этапов адаптации.
- Добавлена management-команда `seed_stages`.
- Добавлен основной dashboard Дневника.
- Добавлено создание нового сотрудника.
- Для новой адаптации создаются:
  - пользователь;
  - профиль уровня L1;
  - путь адаптации;
  - начальная запись истории этапов.
- Для внутреннего перехода сначала создаются только пользователь и профиль L1.
- Добавлен отдельный список сотрудников до начала адаптации.
- Добавлен отдельный сценарий запуска адаптации внутреннего сотрудника.
- Добавлены формы создания, редактирования и запуска адаптации.
- Добавлены проверки доступа для сотрудников без `is_staff`.

### Изменено

- Тесты `traineediary` добавлены в CI вместе с тестами `sandbox`.
- Очередь Ticket Sandbox для сотрудников Дневника во всех местах передаётся явно как `queue_slug="l1"`.

### Исправлено

- Исправлена первоначальная привязка этапа заданий к очереди кандидатов.
- Исключено создание `TraineeJourney` для внутреннего сотрудника до фактического начала адаптации.
- Добавлены проверки допустимости этапов для разных типов входа.

---

## Неделя 12 — Канбан, метрики и карточка сотрудника

### Архитектурные решения

- Основным интерфейсом управления этапами стал канбан.
- История переходов хранится отдельно от текущего состояния сотрудника.
- Качество учитывается только на этапе `WITH_REVIEW`.
- После перехода на этапы `OPTIONAL_REVIEW` или `NO_REVIEW` сохраняется последнее качество с этапа работы с проверками.
- При возврате на этап с проверками фиксация качества сбрасывается.

### Добавлено

- Добавлен канбан сотрудников по этапам адаптации.
- Добавлено перемещение карточек между этапами.
- Добавлен горизонтальный автоскролл канбана во время перетаскивания.
- Добавлена отдельная сворачиваемая секция завершивших испытательный срок.
- Добавлена страница сотрудника.
- На странице сотрудника добавлены:
  - текущий этап;
  - история переходов;
  - длительность этапов;
  - план против факта;
  - прогресс адаптации;
  - информация о сроках испытательного периода.
- Добавлена страница недельных метрик.
- Добавлены недельные показатели:
  - скорость;
  - качество;
  - комментарий наставника;
  - цель на следующую неделю.
- Добавлены графики скорости и качества.
- Добавлены средние значения и последние показатели.
- Добавлен прогресс Ticket Sandbox по очереди L1.
- Прогресс L1 выведен:
  - на странице сотрудников до адаптации;
  - в карточках канбана;
  - на странице сотрудника.
- Добавлена возможность редактирования карточки сотрудника.

### Исправлено

- Исправлено сохранение истории при переходах между этапами.
- Добавлена проверка даты перехода.
- Исправлен расчёт дней на этапе и общего прогресса.
- Исключено качество из недель, которые не относятся к этапу работы с проверками.
- Добавлена защита от добавления недельных метрик в неправильном порядке.

---

## Неделя 13 — Assessment, готовность и риски

### Архитектурные решения

- Логика готовности к переходу вынесена в единый сервис `traineediary/services/assessment.py`.
- Для каждого типа этапа используются отдельные правила готовности.
- Старые разрозненные расчёты готовности удалены.
- Assessment используется как единый источник данных для dashboard, канбана и страницы сотрудника.

### Добавлено

- Добавлены состояния готовности:
  - готов к переходу;
  - почти готов;
  - не готов;
  - адаптация завершена.
- Добавлены причины, мешающие переходу на следующий этап.
- Для этапа Ticket Sandbox учитывается прохождение всех активных заданий L1.
- Для этапа с проверками учитываются:
  - минимальный срок;
  - качество не ниже 80%.
- Для этапа с необязательной проверкой учитывается минимальный срок.
- Для этапа без проверок учитываются:
  - минимальный срок;
  - окончание испытательного периода;
  - скорость не ниже 6 тикетов в час.
- Добавлена оценка рисков сотрудника.
- Добавлены причины, требующие внимания наставника.
- Добавлены ручные риски.
- Добавлены предупреждения о просроченных этапах и низких показателях.
- Добавлена недельная динамика скорости и качества.
- Добавлены рекомендации по переходу на следующий этап.
- Assessment выведен:
  - на основном dashboard;
  - в канбане;
  - на странице сотрудника.
- В канбан добавлена кнопка быстрого перехода на следующий этап.

### Изменено

- Dashboard упрощён и переведён на единый assessment.
- Удалены перегружающие показатели готовности из табличных строк.
- Удалены временные compatibility-поля `risk`, `attention_summary` и отдельный счётчик почти готовых сотрудников.
- Старое имя этапа `SANDBOX_CANDIDATE` заменено на `SANDBOX_L1`.
- Значение в базе `sandbox_candidate` сохранено для обратной совместимости без переноса данных.

### Исправлено

- Исправлены ложные риски на ранних неделях адаптации.
- Исправлена оценка качества после выхода с этапа работы с проверками.
- Исправлена готовность сотрудников при отсутствии метрик.
- Удалён мёртвый код старого расчёта переходов.

---

## Неделя 14 — Завершение испытательного срока

### Архитектурные решения

- Завершение испытательного срока выполняется отдельным доменным методом `complete_probation()`.
- Обычное перемещение карточки в финальный этап не может обходить форму завершения.
- Завершённый сотрудник сохраняется в системе вместе со всей историей этапов и недельных показателей.
- Результат испытательного срока отделён от самого нахождения на этапе `DONE`.

### Добавлено

- Добавлены результаты завершения:
  - `success` — испытательный срок успешно пройден;
  - `terminated` — испытательный срок прекращён.
- В `TraineeJourney` добавлены:
  - `completion_status`;
  - `completed_at`;
  - `completion_comment`;
  - `completed_by`.
- Добавлена отдельная форма завершения испытательного срока.
- Добавлена обязательная причина при прекращении испытательного срока.
- Добавлена проверка даты завершения.
- Добавлена итоговая карточка результата на странице сотрудника.
- В канбане завершённые сотрудники различаются по результату.
- Добавлены дата завершения и итоговый комментарий.
- В dashboard добавлены:
  - фильтр завершённых сотрудников;
  - фильтр по результату ИС;
  - отдельные счётчики успешных и прекращённых испытательных сроков;
  - отображение старых записей без результата.
- Добавлена backend-защита от прямого переноса в `DONE`.
- Добавлена frontend-навигация с канбана на форму завершения.
- После завершения фиксируются:
  - общий срок адаптации;
  - прогресс;
  - длительность этапов.

### Исправлено

- Исправлена потеря итогового комментария в интерфейсе.
- Исправлен обход формы завершения через drag-and-drop.
- Исправлен обход формы через кнопку быстрого перехода.
- Добавлена обработка старых сотрудников, которые уже находились в `DONE` без результата.
- Исправлены стили формы завершения и формы запуска адаптации.
- Удалены старые неиспользуемые CSS-классы dashboard.
- Добавлены тесты модели, формы, view, канбана, dashboard и страницы сотрудника.

### Проверки

- `traineediary` включён в общий CI.
- Добавлены тесты основных пользовательских сценариев Дневника.
- Полная проверка выполняется командой:

```bash
python manage.py test sandbox traineediary
```

## Ближайший план

- Добавить результат завершения ИС в Django admin.
- Разбить крупные `views.py` и `forms.py` приложения `traineediary` на тематические модули.
- Добавить проверку целостности данных Дневника.
- Провести пилот на нескольких реальных сотрудниках.
- Добавить архивирование завершённых сотрудников.
- Добавить уведомления наставникам.
- Развивать аналитику скорости, качества и прохождения этапов.

--------------------------------------------------------------

## Неделя 15 — Модуль оценки знаний сотрудников

### Архитектурные решения

- Новый модуль оценки знаний реализован отдельным приложением `assessment` внутри существующего Django-проекта.
- Для уровня сотрудника используется отдельный `SupportProfile` с уровнями:
  - `L1`;
  - `L2`;
  - `Prime`.
- Уровень оценки знаний отделён от ролей и очередей Ticket Sandbox.
- Банк вопросов построен по иерархии:
  - тематика;
  - навык;
  - семейство вопросов;
  - конкретный вариант вопроса.
- Семейство объединяет разные варианты одной диагностической ситуации, поэтому банк можно расширять без изменения шаблона теста.
- Уже начатая попытка не зависит от дальнейших изменений банка: при старте создаются snapshots вопросов и вариантов ответов.
- Один вопрос даёт максимум 1 балл, итоговый результат рассчитывается как среднее по всем вопросам.
- Проходной процент фиксируется в момент старта попытки и не меняется задним числом при изменении шаблона.
- Для вопросов используется серверный таймер: закрытие вкладки или потеря соединения не останавливают время.

### Добавлено

- Создано приложение `assessment`.
- Добавлены модели:
  - `SupportProfile`;
  - `Topic`;
  - `Skill`;
  - `QuestionFamily`;
  - `Question`;
  - `AnswerOption`;
  - `MatchingPair`;
  - `OrderingItem`;
  - `SelectableLine`;
  - `ExamBlueprint`;
  - `BlueprintSkillQuota`;
  - `AssessmentCampaign`;
  - `ExamAssignment`;
  - `ExamAttempt`;
  - `ExamQuestionSnapshot`;
  - `ExamAnswer`;
  - `AssessmentResult`.
- Добавлены 4 основные тематики:
  - Linux и VDS;
  - Web;
  - Сети;
  - Внутренние регламенты.
- Добавлены 26 технических навыков L1:
  - 10 по Linux/VDS;
  - 8 по Web;
  - 8 по сетям.
- Создан базовый технический шаблон оценки L1 на 26 вопросов.
- Добавлены 5 форматов вопросов:
  - один правильный ответ;
  - несколько правильных ответов;
  - сопоставление;
  - последовательность;
  - выбор одной или нескольких строк в логах/конфигурации.
- Добавлена проверка корректности конфигурации каждого формата вопроса.
- Добавлен детерминированный подбор вопросов по шаблону:
  - учитывается уровень;
  - используются только активные вопросы;
  - исключаются повторения семейств;
  - одинаковый seed формирует одинаковый набор.
- Добавлены кампании тестирования и назначения конкретным сотрудникам.
- Добавлены лимиты попыток.
- Добавлено создание попытки с фиксацией:
  - шаблона;
  - проходного процента;
  - порядка вопросов;
  - вариантов ответов;
  - правильных ответов.
- Добавлена автоматическая проверка всех форматов.
- Для сопоставления и последовательности поддерживается частичный балл.
- Добавлено завершение попытки с расчётом:
  - общего результата;
  - pass/fail;
  - результатов по тематикам;
  - результатов по навыкам.
- Добавлен серверный таймер на каждый вопрос.
- Добавлена фиксация timeout и времени ответа.
- Добавлена защита от повторной отправки ответа, если возврат к вопросу запрещён.
- Добавлен пользовательский интерфейс `/assessment/`:
  - список назначенных тестов;
  - статусы тестов;
  - начало и продолжение попытки;
  - прогресс;
  - последовательное прохождение вопросов;
  - таймер;
  - отдельное отображение логов и конфигураций.
- Добавлен отдельный визуальный стиль модуля оценки знаний с упором на читаемость и контраст.
- Добавлен интерфейс наставника:
  - банк вопросов;
  - поиск;
  - фильтры по уровню, тематике и статусу;
  - создание и редактирование вопросов;
  - отдельные редакторы для всех 5 форматов;
  - управление семействами вопросов.
- Добавлена страница семейств вопросов:
  - поиск;
  - фильтры;
  - создание;
  - редактирование;
  - отключение без удаления истории.
- Добавлен отдельный редактор семейства с выбором конкретного навыка.
- Добавлена навигация между банком вопросов, семействами, тестированиями и результатами.
- `assessment` добавлен в CI и общую проверку проекта.

### Исправлено

- Исправлена несовместимость `select_for_update()` с nullable `LEFT JOIN` при поиске текущего вопроса в PostgreSQL.
- Поиск неотвеченных вопросов переведён на подзапрос без блокировки nullable-части join.
- Исправлено повторное отображение кнопки «Новый вопрос».
- Исправлена вёрстка фильтров банка вопросов.
- Исправлено обрезание текста в фильтрах.
- Выровнены select-поля и стрелки выбора в фильтрах и формах.
- Упрощены названия фильтров:
  - `Уровень`;
  - `Тематика`;
  - `Статус`.
- Исправлен редактор вариантов ответа:
  - большие textarea заменены на компактные поля;
  - техническое поле `order` скрыто;
  - варианты стали визуально компактнее.
- Исправлены стили формы создания вопросов и страницы банка.
- Добавлена корректная обработка сотрудников без `SupportProfile`.
- Добавлена защита от открытия чужой попытки или назначения.

### Проверки

- Добавлены тесты моделей банка вопросов.
- Добавлены тесты валидации всех форматов вопросов.
- Добавлены тесты шаблонов и квот.
- Добавлены тесты детерминированного подбора вопросов.
- Добавлены тесты кампаний и назначений.
- Добавлены тесты создания попыток и snapshots.
- Добавлены тесты проверки ответов.
- Добавлены тесты завершения и расчёта результата.
- Добавлены тесты серверного таймера и timeout.
- Добавлены тесты пользовательского dashboard.
- Добавлены тесты банка вопросов наставника.
- Добавлены тесты редактора вопросов.
- Добавлены тесты управления семействами.
- Основная проверка проекта теперь включает:

```bash
python manage.py test sandbox traineediary assessment
```

### Ближайший план

- Улучшить выбор семейства в форме вопроса:
  - показывать тематику;
  - навык;
  - название семейства.
- Добавить динамические кнопки:
  - «Добавить вариант»;
  - «Добавить пару»;
  - «Добавить строку»;
  - «Добавить шаг».
- Начать наполнение реального банка L1 вопросами.
- Добавить 4 навыка и вопросы по внутренним регламентам.
- Довести полный шаблон L1 до 30 вопросов.
- Сделать страницу управления тестированиями и массовыми назначениями.
- Сделать страницу результатов для наставника.
- Добавить просмотр конкретной попытки:
  - вопрос;
  - ответ сотрудника;
  - правильный ответ;
  - балл;
  - время ответа.
- Добавить аннулирование попытки и выдачу повторного прохождения из интерфейса.
- Добавить служебную статистику сессии:
  - потеря фокуса;
  - visibility;
  - heartbeat;
  - повторные подключения.
- Подготовить первые реальные L1-сценарии для пилотного прохождения.


---------------------------------------------------------------------

## Неделя 16 — Развитие банка вопросов и подготовка L1-контента

### Архитектурные решения

- Уточнена логика выбора семейств в редакторе вопросов:
  - в списке отображается полный путь `Тематика → Навык → Семейство`;
  - для новых вопросов доступны только активные семейства;
  - при редактировании старого вопроса его текущее семейство остаётся доступным даже после деактивации.
- Для L1 решено заменить навык Cron на отдельный навык `Панели управления`.
- Старый навык Cron не удаляется из истории, а деактивируется.
- Квота L1 blueprint перенесена с Cron на `Панели управления`, поэтому количество Linux/VDS-вопросов в шаблоне осталось прежним.
- Для навыка `Панели управления` используются отдельные семейства по диагностическим сценариям FASTPANEL, ISPmanager и BitrixVM.
- Зафиксированы правила подготовки вопросов:
  - сложность должна быть в диагностике, а не в знании редких флагов команд;
  - один вопрос описывает один инцидент;
  - правильный ответ не должен выделяться длиной или количеством деталей;
  - неправильные варианты должны быть правдоподобными;
  - подробное объяснение выносится в комментарий наставнику;
  - вопросы с несколькими логами получают увеличенный таймер.
- Для первых L1-вопросов выбран уровень сложности `Средняя`.
- Ориентир по времени:
  - 150–180 секунд для обычных диагностических вопросов;
  - 180–240 секунд для вопросов с несколькими логами и выводами команд.

### Добавлено

- Улучшено отображение семейства в форме создания вопроса:
  - тематика;
  - навык;
  - название семейства.
- Добавлены динамические элементы редактора ответов:
  - `Добавить вариант`;
  - `Добавить пару`;
  - `Добавить шаг`;
  - `Добавить строку`;
  - удаление и восстановление строк без ручного управления formset.
- Количество первоначальных строк в редакторах приведено к минимально необходимому для каждого типа вопроса.
- Добавлен навык `Панели управления` в Linux/VDS.
- Выполнена data migration:
  - `cron-runtime-context` деактивирован;
  - создан `control-panels`;
  - квота L1 blueprint перенесена на новый навык.
- Начато наполнение реального L1-банка диагностическими вопросами.
- Подготовлены и добавлены первые семейства и сценарии Linux/VDS:
  - расхождение `df` и `du` из-за удалённого открытого файла;
  - различие между заполнением диска, исчерпанием inode и read-only;
  - данные, скрытые точкой монтирования;
  - высокий Load Average из-за дискового I/O;
  - OOM, произошедший до момента диагностики;
  - ошибки запуска и контекст systemd-сервисов.
- Подготовлены сценарии для навыка `Панели управления`:
  - версия PHP сайта отличается от PHP CLI;
  - BitrixVM: nginx продолжает обслуживать frontend, а backend упирается в ограничения.
- Начато наполнение Web-банка:
  - 504 при долгом ответе backend;
  - 502 при недоступном или неверно настроенном upstream;
  - диагностика лимитов пула PHP-FPM.
- Для 502 и 504 выбраны отдельные семейства, чтобы разные причины ошибок не смешивались в одном диагностическом сценарии.

### Интерфейс

- Убрано техническое поле `order` из формы создания и редактирования вопроса.
- Исправлен цвет текста в полях вариантов ответа.
- Сохранён внутренний `order` в модели, но наставнику больше не нужно управлять им вручную.
- Динамические строки редакторов автоматически получают порядок при добавлении и сохранении.

### Исправлено

- Обновлены старые тесты seeded taxonomy после замены Cron на `Панели управления`.
- Проверка количества навыков теперь учитывает активные навыки, а не общее количество записей.
- Убрано старое предположение тестов о том, что все seeded-навыки всегда должны оставаться активными.
- Добавлена отдельная проверка состояния:
  - Cron — неактивен;
  - `Панели управления` — активны;
  - в L1 blueprint используется новая квота.

### Проверки

- Добавлены и обновлены тесты:
  - выбора семейства в редакторе вопроса;
  - скрытия неактивных семейств для новых вопросов;
  - сохранения старого неактивного семейства при редактировании;
  - динамических элементов редактора;
  - управления семействами;
  - замены Cron на `Панели управления`;
  - seeded taxonomy после изменения состава навыков.
- Полный прогон проекта обнаружил 2 устаревшие проверки taxonomy из 535 тестов.
- Падения были связаны только со старыми ожиданиями:
  - все навыки должны быть активными;
  - Linux/VDS должен содержать ровно 10 записей, а не 10 активных навыков.
- Проверки приведены в соответствие с новой архитектурой taxonomy.
- Для небольших изменений по-прежнему используются targeted-тесты и `python manage.py check`, без обязательного полного прогона всего проекта после каждой правки.

### Начато в следующем техническом шаге

- Начата подготовка структурированных диагностических данных вместо одного большого поля `diagnostic_data`.
- Добавлена идея разделять содержимое вопроса на последовательные блоки:
  - обычный текст;
  - код / лог.
- Подготовлена backend-модель `QuestionDiagnosticBlock`.
- Для snapshot предусмотрено сохранение диагностических блоков отдельно от живого вопроса.
- Старое поле `diagnostic_data` сохраняется для обратной совместимости.

### Ближайший план

- Завершить поддержку структурированных диагностических блоков:
  - backend;
  - snapshot;
  - редактор наставника;
  - отображение сотруднику.
- Добавить в редактор кнопки:
  - `Добавить текст`;
  - `Добавить код / лог`.
- Продолжить наполнение реального банка L1.
- Довести Linux/VDS-блок до полного набора утверждённых сценариев.
- Добавить отдельный сценарий по ISPmanager.
- Продолжить Web-вопросы по:
  - PHP-FPM;
  - сокетам и портам PHP;
  - виртуальным хостам;
  - reverse proxy;
  - БД и нестабильной работе сайта.
- После Linux/VDS и Web перейти к сетевому блоку.
- После наполнения банка выполнить тестовое прохождение полного L1 assessment от лица сотрудника.