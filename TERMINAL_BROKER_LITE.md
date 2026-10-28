# Terminal Broker 2.0 Lite — реализация и проверка

2026-10-28. Ветка `feature/terminal-broker-v2`, база `ac91823`.
Снимок локальных и лабораторных проверок перед публикацией Lite в feature-ветке.
**Функциональная модель Lite прошла лабораторный E2E. Production: NO-GO из-за F1
и оставшихся эксплуатационных проверок.** Флаг по умолчанию остаётся `false`.
Staging/production, PR, merge и deploy не выполнялись. README пользователя
сохранён. Материалы прежних cgroup-экспериментов сохранены отдельно вне checkout;
в коммиты Lite они не включены.

## Контракт

Вкладка владеет одним интерактивным Docker Exec. При закрытии завершается этот
Exec; фоновые сервисы могут продолжать работу до удаления task-контейнера.
Restart/cleanup отзывают доступ, останавливают ttyd/Broker и удаляют точный task.
Это изменение требований, а не доказательство containment против враждебного root.

Bootstrap получает namespace PID и `/proc/self/stat` starttime, сообщает их Broker
и ждёт ACK не более пяти секунд. Broker fsync-сохраняет identity до ACK и запуска
Bash через `execv`, сохраняющий PID. Cleanup адресует этот PID через pidfd после
проверки starttime, исключает PID 1, посылает HUP/KILL и проверяет состояние Exec.
Рекурсивного обхода `/proc/*/environ` нет. Фоновые процессы не являются ошибкой.
Журнал v3 сохраняется до подтверждённого завершения интерактивного процесса.
Старые v2 журналы не интерпретируются как v3; старое окружение снимается через
проверенный teardown, его state volume сохраняется.

## Lifecycle и восстановление

- `terminal_teardown.py` сначала проверяет полный Docker ID task и labels
  attempt/queue/slug/generation всех найденных ресурсов; ttyd/Broker также должны
  иметь правильный target ID. Имена используются для поиска шлюзов, а SDK-объекты
  адресуют удаление по immutable ID. Чужая identity блокирует действия.
- Перед Docker-действиями сохраняются отзыв доступа и operation checkpoint.
  При restart новое UUID поколения сразу отзывает старый lease. При cleanup
  durable `environment_cleanup_requested` запрещает gateway/lease ещё до ожидания
  блокировки исполнителя.
- Порядок teardown: отключить autorestart, остановить/удалить ttyd, остановить/
  удалить Broker, force-remove точный task, подтвердить отсутствие task. Exit code
  Broker может быть ненулевым; неподтверждённая остановка, ошибка Docker или identity
  не считаются успешным удалением. Volumes/images автоматически не удаляются.
- `environment_operation` хранит operation ID, старую identity, новое поколение,
  стадии `teardown/create/terminal/ready/done`, target ID и порт. Имена новых
  ресурсов включают поколение. Существующий ресурс принимается только после
  проверки identity; контейнер `created` возобновляется через start. SDK-состояние
  после run перечитывается. `ready`, счётчик restart и ledger finished публикуются
  одной DB-транзакцией. Повторная доставка завершённой операции ничего не сбрасывает.
- PostgreSQL session advisory lock сериализует исполнителей попытки без длинной
  транзакции вокруг Docker. Проверка DB session PID обнаруживает переподключение.
  SQLite/file lock предназначен для локальных тестов, не распределённой установки.
  [PostgreSQL advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS).
- Celery использует late ACK, reject-on-worker-lost и ограниченные retry для
  временных ошибок. Identity errors не превращаются в разрешение на удаление.
  Незавершённые операции подхватываются при старте worker, периодическим reconciler
  и management-командой. Это обработка повторов, а не exactly-once доставка.
  [Celery task acknowledgement](https://docs.celeryq.dev/en/stable/userguide/tasks.html).
- Retirement history сохраняет принадлежность старых поколений. Reaper сверяет
  их с Docker, включая позднее завершение create после потери worker; активное
  поколение защищено. Это eventual reconciliation: 30 секунд плюс очередь и API
  timeouts, не атомарная транзакция PostgreSQL+Docker. При недоступном daemon удаление
  не объявляется подтверждённым. История требует отдельной retention-политики.

Миграция: `0036_terminal_lite_operation.py`. До запуска обновлённых процессов её
нужно применить. Broker/ttyd образы нужно собрать из той же ревизии и явно задать
`TERMINAL_BROKER_IMAGE`/`TERMINAL_BROKER_TTYD_IMAGE`; старый образ под тем же v2 tag
не является Lite. Добавлен opt-in Compose profile `terminal-broker` с сервисом
`terminal_scheduler` (Celery Beat, без Docker socket). Для восстановления после
пропущенного publish нужен один активный scheduler; одного worker-ready hook
недостаточно. Расписание активно только при включённом флаге. После выключения
флага ручная reconciliation разрешает cleanup/retirement, но не новые запуски.
Требуются согласованные настройки web/worker/scheduler, общий сильный SECRET_KEY,
приватный Django listener, корректный lease URL/ALLOWED_HOSTS. Legacy при выключенном
флаге сохраняется; автоматического fallback нет. Legacy без generation требует
отдельного контролируемого снятия перед переходом на Lite.

## Проверки

| Проверка | Результат |
|---|---|
| Broker unit / настоящий локальный PTY в Lite checkout | 46 passed |
| Focused Lite teardown/lifecycle/auth | 40 passed |
| Полный Django suite | **834 run, 7 skipped, без ошибок** |
| PostgreSQL/Redis/Celery/Beat E2E | **host_port PASS, docker_network PASS** |
| Прежний Docker/browser CI fixture на Lite | **оба PASS** |
| actionlint 1.7.7 | PASS, shellcheck отключён |
| Compose YAML, Python/JS/shell syntax, migration drift, Django check, whitespace | PASS |
| Hosted GitHub Actions | Не входят в этот лабораторный снимок; актуальные результаты — в Actions feature-ветки |

Unit/integration покрывают несовпадение каждой identity, Docker API failure,
ненулевой exit Broker, повторный teardown, конкурирующего исполнителя, потерю worker
до ответа create и до start, восстановление после временной ошибки, cleanup после
смены generation, late delivery, поздний create уже после cleanup, защиту нового
поколения от reaper, reconciliation пропущенного publish и decommission при OFF.
Согласованный чужой checkpoint также отклоняется: его attempt/queue/slug сверяются
с текущей строкой БД независимо от совпадения его Docker labels.
В первоначальные 55 offline-тестов входили 9 исторических cgroup-тестов. После
отделения этих материалов Lite checkout содержит 46 offline-тестов; прежний
результат 55 сохранён в лабораторном manifest как историческая запись.

Финальный полный VDS прогон: `tc-tb2-20261028-lite6`, свежие PostgreSQL БД и Redis
очереди на режим, два prefork executor на worker, отдельный Beat. Factory настоящая;
test-only wrapper вызывает её, затем SIGKILL завершает prefork worker до публикации
ID в БД. По два таких сбоя на режим (start и restart), плюс дубли тех же operation ID.
ID из fault records совпали с принятыми окружениями: повтор не создал другое
поколение, restart_count остался **1**. Проверены реальный HTTP start/restart,
независимые попытки/вкладки, resize `46 124 → 56 182`, Ctrl+C, fullscreen top,
Broker SIGKILL/recovery, новый Docker ID/UUID, закрытие старого WebSocket,
старые Basic **401** и lease **403**, отсутствие старого task, cleanup через Celery
и последующий gateway **403**. Интерактивный Bash завершён после закрытия вкладки,
а HUP/TERM-resistant background sleep сохранился до удаления его task.

Дополнительный прежний CI fixture проверил SIGWINCH, reconnect и сохранность PID 1
и постороннего sentinel Exec при закрытии вкладок и recovery. Census теперь читает
собственные Exec-журналы, а не сканирует environment всех процессов.

Начальные неуспешные прогоны не засчитаны: исправлены пропущенный статус NEW,
устаревший SDK inspection после run и гонка runner, печатавшего следующую команду
до восстановления termios после top. Финальный runner ждёт нового Bash prompt.
Отдельный прогон остановился на transport failure управляющего fetch без сбоя
контейнеров; точная низкоуровневая причина не установлена. Финальный runner открывает
отдельные control HTTP соединения и по-прежнему падает при ошибке, без её подавления.

Публичные результаты и manifest:
[evidence/lite-2026-10-28](experiments/terminal_broker/evidence/lite-2026-10-28/).
Приватные stack/session JSON, cookies и control tokens находятся только в lab и
Mac `/tmp`; они не включены в Git/artifacts. Старые образы, volumes и БД сохранены.

Изменённые файлы:

- Runtime: `terminal/{broker_v2,session_exec,runtime_probe}.py`.
- Lifecycle: `sandbox/services/{terminal_teardown,terminal_lite,terminal_broker,docker_service,environments,ledger_execution}.py`.
- Persistence/jobs: `sandbox/models.py`, миграция `0036_terminal_lite_operation.py`,
  `sandbox/tasks.py`, command `reconcile_broker_environments.py`, `config/{settings,celery}.py`.
- Tests: `sandbox/tests/{test_terminal_lite,test_terminal_broker}.py`,
  `experiments/terminal_broker/test_v2{,_transport}.py`, shared `browser_terminal.cjs`,
  `e2e_{start.sh,runtime.py,browser.cjs}`, `fullstack_{start.py,tasks.py,urls.py,security.py,browser.cjs}`.
- Ops/docs: четыре Compose-файла, `.github/workflows/terminal-broker.yml`, этот
  отчёт, ссылка из `TERMINAL_BROKER_V2.md`, публичная evidence-директория.

После штатного Django cleanup удалены только созданные этим проходом контейнеры
и пустые тестовые сети. Все volumes/images/БД сохранены. Исходный
`ticket-sandbox-l1-service-bind-localhost-1` продолжает работу с StartedAt
`2026-10-22T14:02:54.421725064Z`, RestartCount **0**.

Локальные команды:

```sh
.venv/bin/python -m unittest discover -s experiments/terminal_broker -p 'test_*.py' -q
DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
  .venv/bin/python manage.py test sandbox traineediary assessment react_frontend --noinput
DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
  .venv/bin/python manage.py makemigrations --check --dry-run
```

Финальные образы собраны на VDS из локального source snapshot:

```sh
docker build -t ticket-sandbox-terminal-broker:lite-20261028-r3 -f terminal/Dockerfile.service .
docker build -t ticket-sandbox-ttyd:broker-lite-20261028-r3 -f terminal/Dockerfile.broker .
```

Полный стенд запущен в `/root/tc-e2e-pilot/terminal-broker-lite-20261028-run6`:

```sh
docker run --name tc-tb2-20261028-lite6-driver --user 0 \
  --label terminal-broker.fullstack=tc-tb2-20261028-lite6 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /root/tc-e2e-pilot/terminal-broker-lite-20261028-run6/source:/app:ro \
  -v /root/tc-e2e-pilot/terminal-broker-lite-20261028-run6/fullstack:/lab -w /app \
  tc-e2e-django:lab python -m experiments.terminal_broker.fullstack_start \
  --prefix tc-tb2-20261028-lite6 \
  --host-source /root/tc-e2e-pilot/terminal-broker-lite-20261028-run6/source \
  --host-state /root/tc-e2e-pilot/terminal-broker-lite-20261028-run6/fullstack \
  --broker-image ticket-sandbox-terminal-broker:lite-20261028-r3 \
  --ttyd-image ticket-sandbox-ttyd:broker-lite-20261028-r3
```

Chrome запускался на Mac через SSH forwards 29190–29193:

```sh
NODE_PATH=/tmp/terminal-broker-browser/node_modules \
  TB_CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  node experiments/terminal_broker/fullstack_browser.cjs \
  /tmp/tb-lite-private-stack6.json /tmp/tb-lite-evidence-run6
```

Не повторять использованные prefix/state; это сохранённые доказательства, не
готовый сценарий переиспользования БД. Opt-in E2E требует лабораторной авторизации.

## Security review и решение

**F1 остаётся CRITICAL trust boundary.** Broker и worker имеют полный Docker socket.
Compose допускает их размещение с Django/PostgreSQL на одном daemon. Компрометация
Broker позволяет обойти его Python-код и управлять host/другими контейнерами;
cap_drop, readonly rootfs и фиксированный command не ограничивают уже захваченный
daemon credential. Lite не добавляет Docker-доступ в ttyd, task или scheduler.
[Docker daemon security](https://docs.docker.com/engine/security/).

Для дальнейшего пилота допустим отдельный disposable Docker host/VM без Django,
production DB и посторонних workload с явно принятой моделью доверия. Для production
нужны изоляция daemon/control plane и/или независимо проверяемая daemon-side policy,
охватывающая target/Exec/attach/resize и запрет создания привилегированных контейнеров.
Python allowlist внутри Broker не является таким ограничением.

F2 в прежнем виде (фоновые потомки переживают вкладку) теперь разрешён контрактом.
Это не исправление adversarial containment. F3: обязательный env-scanner удалён,
restart не зависит от task-side helper. Адресное завершение вкладки всё ещё требует
работающих Python/pidfd/Bash в task. Намеренно или случайно сломанный interpreter
может сорвать cleanup сессии; Broker сохраняет journal и закрывает новые подключения,
а teardown всего task остаётся внешним Docker-действием. Гарантия против враждебного
root не заявляется. Все 20 образов в этом проходе заново не квалифицировались.

Остаются daemon restart, host reboot, disk-full/fsync, сетевые разрывы DB/daemon,
нагрузка и retention history/volumes. Показанный late-daemon-response случай покрыт
unit-моделью, не полноценной сетевой fault injection. SIGKILL prefork worker не
доказывает host-reboot recovery. Lifecycle предполагает коммиты стадий вне внешней
длинной транзакции и прямое PostgreSQL session-соединение: transaction-pooling
PgBouncer для advisory lock не квалифицирован. Hosted CI проверяется отдельно при публикации.

**Рекомендация: функциональный GO только для изолированного lab pilot модели Lite;
NO-GO для production и общего с production данными Docker-host.**
