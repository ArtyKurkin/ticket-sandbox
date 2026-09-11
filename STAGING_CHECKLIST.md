# STAGING CHECKLIST

Чеклист ручной проверки Training Platform после деплоя на staging.

Цель — убедиться, что проект работает не только по тестам и CI/CD, но и в полном пользовательском сценарии: стажёр открывает задание, запускает окружение через Celery worker, работает в терминале, проходит автопроверку, отправляет текст на ручную проверку и может открыть историю попыток.

---

## 1. Docker Compose stack

На сервере:

```bash
cd /opt/training-platform-compose/app

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  ps
```

- [ ] `training-platform-db` — `healthy`.
- [ ] `training-platform-redis` — `healthy`.
- [ ] `training-platform-web` — `healthy`.
- [ ] `training-platform-worker` — `healthy`.
- [ ] `training-platform-gateway` — `healthy`.
- [ ] Нет контейнеров основного stack в состоянии `Restarting` или `Exited`.

## 2. Docker socket и non-root runtime

Проверить пользователей:

```bash
docker exec training-platform-web id
docker exec training-platform-worker id
```

- [ ] `web` работает от `uid=10001(app)`.
- [ ] `worker` работает от `uid=10001(app)`.
- [ ] Celery worker не выводит warning о запуске от root.

Проверить, что web не имеет Docker socket:

```bash
docker exec training-platform-web \
  sh -c 'test ! -S /var/run/docker.sock && echo "web: no docker.sock"'
```

- [ ] Получен `web: no docker.sock`.

Проверить Docker API из worker:

```bash
docker exec training-platform-worker python -c "
import docker
print(docker.from_env().ping())
"
```

- [ ] Получено `True`.

Проверить GID socket на host:

```bash
stat -c 'uid=%u gid=%g mode=%a' /var/run/docker.sock
```

- [ ] GID совпадает с `DOCKER_GID` в `.env.prod`.
- [ ] `deploy/check_docker_socket_gid.sh .env.prod` завершается успешно.

## 3. Redis и Celery

Проверить Redis:

```bash
docker exec training-platform-redis redis-cli ping
```

- [ ] Получено `PONG`.

Проверить worker:

```bash
docker exec training-platform-worker \
  celery -A config inspect ping --timeout=5
```

- [ ] Worker отвечает `pong`.

Проверить зарегистрированные задачи:

```bash
docker exec training-platform-worker \
  celery -A config inspect registered
```

- [ ] Есть `sandbox.start_environment`.
- [ ] Есть `sandbox.restart_environment`.
- [ ] Есть `sandbox.run_attempt_check`.
- [ ] Может присутствовать `sandbox.celery_ping`.

## 4. Базовая доступность

- [ ] Открывается `/`.
- [ ] Есть редирект на страницу входа, если пользователь не авторизован.
- [ ] Открывается `/admin/login/`.
- [ ] Открывается `/healthz/`.
- [ ] `/healthz/` возвращает JSON со статусом `ok`.
- [ ] Страницы открываются по HTTPS.
- [ ] Нет mixed content.
- [ ] CSS и JS загружаются корректно.

Проверка извне:

```bash
curl -fsS https://ticket-sandbox-staging.twc1.net/healthz/
```

## 5. Логи основных сервисов

```bash
cd /opt/training-platform-compose/app

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  logs --tail 100 web worker gateway redis
```

- [ ] Нет traceback при обычном открытии страниц.
- [ ] Нет постоянных ошибок Redis connection.
- [ ] Нет постоянных ошибок Celery broker.
- [ ] Нет ошибок Docker permission denied.
- [ ] Нет ошибок CSRF.
- [ ] Нет ошибок static files.
- [ ] Нет постоянных ошибок nginx `auth_request`.

## 6. Авторизация

- [ ] Стажёр может войти.
- [ ] Наставник/admin может войти.
- [ ] Анонимный пользователь не может открыть dashboard.
- [ ] Анонимный пользователь не может открыть страницу задания.
- [ ] Logout работает корректно.

## 7. Dashboard стажёра

- [ ] Стажёр видит доступные очереди.
- [ ] Видит задания своей очереди.
- [ ] Недоступные задания заблокированы до прохождения предыдущих.
- [ ] Отображается прогресс по очереди.
- [ ] Баннер нового комментария наставника отображается при непрочитанном feedback.
- [ ] Нет ошибок шаблона или пустых блоков.

## 8. Запуск окружения через Celery

Перед тестом можно открыть worker logs:

```bash
docker logs -f training-platform-worker
```

В интерфейсе:

- [ ] Стажёр открывает доступное задание.
- [ ] «Начать работу» переводит окружение в `starting`.
- [ ] Polling работает без ошибок.
- [ ] В worker logs появляется `Task sandbox.start_environment[...] received`.
- [ ] Создаётся task-контейнер.
- [ ] Создаётся terminal-контейнер.
- [ ] `environment_status` становится `ready`.
- [ ] `status` становится `in_progress`.
- [ ] Заполнены `environment_started_at` и `environment_finished_at`.
- [ ] На странице появляется терминал.
- [ ] У staff отображается shell-команда для наставника, если предусмотрено интерфейсом.

Проверить, что start не выполнялся в web:

```bash
docker logs --since 5m training-platform-web 2>&1 \
  | grep 'task_environment_started' \
  || echo "web did not run environment start"
```

- [ ] Получено `web did not run environment start`.

## 9. Terminal gateway

В актуальном `docker_network` режиме:

- [ ] Терминал открывается в iframe.
- [ ] Терминал принимает ввод.
- [ ] URL имеет вид `/terminal/<attempt_id>/`.
- [ ] В URL нет случайного host-порта `20000–30000`.
- [ ] ttyd не публикуется наружу через отдельный host-порт.
- [ ] nginx проксирует WebSocket.
- [ ] terminal-контейнер подключён к `training-platform-runtime`.
- [ ] В gateway logs нет `auth request unexpected status`.

Проверить сеть:

```bash
docker ps --format 'table {{.Names}}\t{{.Networks}}' \
  | grep -E 'training-platform|ticket-sandbox-terminal'
```

## 10. Доступ к терминалу

- [ ] Стажёр может открыть только свой терминал.
- [ ] Стажёр не может открыть чужой terminal URL.
- [ ] Наставник с `is_staff=True` может открыть терминал стажёра.
- [ ] Открытие наставником логируется как `mentor_terminal_access`.
- [ ] Анонимный пользователь не может открыть terminal URL.

## 11. Перезапуск окружения через Celery

- [ ] До технической сдачи доступен restart.
- [ ] `environment_status` становится `restarting`.
- [ ] В worker logs появляется `sandbox.restart_environment`.
- [ ] Старые task/terminal-контейнеры удаляются.
- [ ] Создаются новые контейнеры.
- [ ] `restart_count` увеличивается.
- [ ] `finished_at` сбрасывается.
- [ ] `check_status` сбрасывается в `idle`.
- [ ] `stuck_reason` сбрасывается.
- [ ] После restart терминал снова доступен.

Проверить, что restart не выполнялся в web:

```bash
docker logs --since 5m training-platform-web 2>&1 \
  | grep 'task_environment_restarted' \
  || echo "web did not run environment restart"
```

- [ ] Получено `web did not run environment restart`.

## 12. Автопроверка check.sh через Celery

- [ ] Стажёр выполняет техническую часть задания.
- [ ] Кнопка проверки переводит `check_status` в `running`.
- [ ] Повторный быстрый клик не создаёт вторую проверку.
- [ ] В worker logs появляется `sandbox.run_attempt_check`.
- [ ] Polling проверки работает.
- [ ] Создаётся `CheckRun`.
- [ ] `last_check_output` обновляется.
- [ ] После успешной проверки заполняется `technical_passed_at`.
- [ ] `check_status` становится `passed`.
- [ ] После успешной технической сдачи task/terminal-контейнеры удаляются.
- [ ] Пользователь видит вывод `check.sh`, а не инфраструктурный cleanup.
- [ ] Если `requires_manual_review=False`, задача принимается автоматически.
- [ ] Если `requires_manual_review=True`, появляется форма ответа клиенту и внутреннего комментария.

Проверить, что check не выполнялся в web:

```bash
docker logs --since 5m training-platform-web 2>&1 \
  | grep -E 'task_check_(passed|failed|docker_error)' \
  || echo "web did not run technical check"
```

- [ ] Получено `web did not run technical check`.

## 13. Неуспешная автопроверка

- [ ] Если `check.sh` возвращает exit code `1`, создаётся failed `CheckRun`.
- [ ] `check_status=failed`.
- [ ] `TaskAttempt.status=failed`.
- [ ] Стажёр видит понятный вывод.
- [ ] Повторная проверка доступна после исправления.
- [ ] Celery task при этом может иметь статус `succeeded` — это нормально, потому что worker корректно обработал пользовательский failed-result.

## 14. Ошибка автопроверки

- [ ] При технической ошибке Docker API `check_status=error`.
- [ ] `TaskAttempt.status=failed`.
- [ ] `check_finished_at` заполнен.
- [ ] Пользователь получает понятное сообщение, а не HTTP 500.
- [ ] При настроенном Sentry появляется событие.

## 15. Ошибка окружения

- [ ] При ошибке start/restart `environment_status=error`.
- [ ] `TaskAttempt.status=failed`.
- [ ] `environment_finished_at` заполнен.
- [ ] Автопроверка блокируется, пока окружение в `error`.
- [ ] Пользователь может повторить restart.
- [ ] Ошибка попадает в Sentry, если Sentry настроен.

## 16. Watchdog зависших операций

Dry-run через web, потому что Docker API этой команде не нужен:

```bash
cd /opt/training-platform-compose/app

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps web \
  python manage.py detect_stuck_attempts --dry-run
```

- [ ] Команда выполняется без traceback.
- [ ] Dry-run не меняет данные.
- [ ] Watchdog понимает старые `starting`, `restarting`, `running`.
- [ ] При реальном recovery заполняется `stuck_reason`.
- [ ] Технически пройденные попытки не ломаются.

Если на сервере есть cron/systemd timer для watchdog:

- [ ] Расписание существует.
- [ ] Команда запускается в актуальном контейнерном окружении, а не через удалённый host `.venv`.
- [ ] Логи расписания доступны.

## 17. Ручная проверка наставником

- [ ] После технической сдачи стажёр видит форму ответа при `requires_manual_review=True`.
- [ ] Заполняет `client_answer`.
- [ ] Заполняет `trainee_report`.
- [ ] Отправка переводит попытку в `on_review`.
- [ ] Попытка появляется в mentor dashboard.
- [ ] Бейдж «Ждут проверки» увеличивается.
- [ ] Наставник видит ответ и внутренний комментарий.
- [ ] Может принять ответ.
- [ ] Может отправить на доработку.
- [ ] Feedback отображается стажёру.
- [ ] Просмотр feedback заполняет `mentor_feedback_seen_at`.

## 18. Доработка текста

- [ ] При `needs_revision` стажёр правит только текст.
- [ ] `technical_passed_at` не сбрасывается.
- [ ] Docker runtime повторно не требуется.
- [ ] `check.sh` повторно не требуется.
- [ ] После повторной отправки наставник видит обновлённый текст.

## 19. Повторная тренировочная попытка

- [ ] После успешной технической сдачи обычный restart заблокирован.
- [ ] Можно создать дополнительную тренировочную попытку.
- [ ] `attempt_number > 1`.
- [ ] Новая попытка становится `is_current=True`.
- [ ] Предыдущая становится исторической.
- [ ] Дополнительная попытка не откатывает прогресс.
- [ ] Не попадает в mentor dashboard как зачётная.

## 20. Историческая попытка

- [ ] Открывается read-only.
- [ ] Нет кнопок start/restart/check.
- [ ] Терминал недоступен.
- [ ] Формы не редактируются.
- [ ] Backend блокирует POST-действия.

## 21. Admin

- [ ] Открывается список Task.
- [ ] Работают фильтры Task.
- [ ] Работают массовые actions.
- [ ] Открывается Queue.
- [ ] `order` редактируется.
- [ ] В TaskAttempt видны `environment_status`, `check_status`, `stuck_reason`.
- [ ] Работают фильтры по этим полям.
- [ ] Работают admin actions сброса статусов.
- [ ] Superuser видит синхронизацию `training_tasks`.
- [ ] Dry-run strict работает.

## 22. Trainee Diary

- [ ] Открывается `/diary/` для staff.
- [ ] Kanban загружается.
- [ ] Карточки сотрудников открываются.
- [ ] Weekly metrics отображаются.
- [ ] Нет ошибок после миграции runtime.

## 23. Assessment

- [ ] Модуль оценки знаний открывается.
- [ ] Банк вопросов доступен.
- [ ] Существующие данные на месте.
- [ ] Создание/прохождение тестовой оценки работает согласно текущему сценарию.

## 24. Management commands на staging

Проверки без Docker API:

```bash
cd /opt/training-platform-compose/app

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps web python manage.py check

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps web python manage.py check --deploy

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps web python manage.py sync_training_tasks --dry-run --strict
```

Docker-зависимые команды — только через worker:

```bash
docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps worker python manage.py build_task_images

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps worker python manage.py cleanup_task_containers --dry-run
```

- [ ] Все команды выполняются без `Permission denied`.
- [ ] `build_task_images` действительно имеет доступ к Docker API.
- [ ] `web` не получает Docker socket ради этих команд.

## 25. CI/CD

- [ ] GitHub Actions tests job зелёный.
- [ ] GitHub Actions deploy-staging job зелёный после merge/push в `main`.
- [ ] Deploy summary содержит успешные шаги:
  - Fetch latest code;
  - Check Docker socket GID;
  - Validate Docker Compose config;
  - Build application images;
  - Start database;
  - Run migrations;
  - Sync training tasks in strict mode;
  - Build task images;
  - Start application;
  - Recreate gateway;
  - Show Docker Compose status;
  - Check staging healthz;
  - Check staging homepage;
  - Check staging admin login.
- [ ] После автоматического deploy staging реально открывается в браузере.
- [ ] Gateway не отдаёт `502` после пересоздания web.

## 26. Gateway после deploy

- [ ] Gateway пересоздан после нового web.
- [ ] `docker compose ps` показывает gateway healthy.
- [ ] `/` отдаёт ответ без `502`.
- [ ] `/healthz/` отдаёт `200`.
- [ ] Terminal WebSocket работает после deploy.

## 27. Cleanup

Dry-run:

```bash
cd /opt/training-platform-compose/app

docker compose \
  --env-file .env.prod \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  run --rm --no-deps worker \
  python manage.py cleanup_task_containers --dry-run
```

- [ ] Нет traceback.
- [ ] Старые runtime-контейнеры не копятся.
- [ ] Успешно завершённые попытки не ломаются.
- [ ] `docker ps -a` не показывает большое количество забытых контейнеров.

## 28. Sentry

Если Sentry включён:

- [ ] `SENTRY_DSN` задан.
- [ ] `SENTRY_ENVIRONMENT=staging`.
- [ ] Django стартует без ошибок SDK.
- [ ] Ошибки Celery start/restart/check попадают в Sentry.
- [ ] Не отправляются лишние персональные данные.

Если Sentry выключен:

- [ ] При пустом `SENTRY_DSN` проект работает нормально.

## 29. Telegram

Если Telegram включён:

- [ ] Уведомление при `on_review` приходит.
- [ ] При недоступном Telegram основной сценарий не падает.
- [ ] Ошибки уведомлений логируются.

## 30. Итоговые worker logs

После полного smoke-сценария:

```bash
docker logs --since 10m training-platform-worker 2>&1 \
  | grep -E 'sandbox.start_environment|sandbox.restart_environment|sandbox.run_attempt_check'
```

- [ ] Есть `sandbox.start_environment ... received` и `succeeded`.
- [ ] Есть `sandbox.restart_environment ... received` и `succeeded`.
- [ ] Есть `sandbox.run_attempt_check ... received` и `succeeded`.

## 31. Итог проверки

Дата:

```text
YYYY-MM-DD
```

Проверял:

```text
ФИО / username
```

Commit / release:

```text
<git sha>
```

Результат:

```text
passed / failed / needs fixes
```

Найденные проблемы:

```text
1.
2.
3.
```

Что нужно исправить:

```text
1.
2.
3.
```
