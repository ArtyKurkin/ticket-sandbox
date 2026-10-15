# Trusted Checker: prepare diagnostics и остановка каскада — задача №19.1.2

15 октября 2026. Ветка `feature/roadmap-react`. Изменения ограничены standalone PoC. Новые Docker/VDS испытания: **NOT RUN**. Docker Desktop/socket, production и старые VDS evidence не использовались. Commit/staging/push/deploy не выполнялись; задача №20 не начата.

## 1. Что известно об инциденте

Следующие сведения получены от пользователя, а не новым runtime-прогоном: Ubuntu 24.04.5, Engine 29.9.1, linux/amd64; 130 unit/fake tests OK. Integration `f09a7c21-e9e9-4c8f-8a96-31e17b30a836`, directory `/opt/tc19-evidence/run-191-001`: create/register race и localhost/network cases прошли, дальнейшие scenarios преимущественно inconclusive, cleanup_incomplete / exit 4. В short batch — 20 unknown, 0 passed, 0 наблюдений exited до validation. Terminal receipts всего пять: два prepare unknown, один timeout, один pass, один service_unreachable.

| Run / контейнер | Состояние по сообщению пользователя |
|---|---|
| `a567743c-75a8-49e3-a45a-50a5df62bfde` / `6e3dd5a2252453326e2c7ff3c98f4bfb48d67efc240f2f7454be8612409f0e23` | Created, intent есть, ownership нет, lease активна. Reconcile отказал: independent_daemon_create_evidence_missing. Остаётся quarantine. |
| `ad3cac13-6bca-4673-9120-676817bf92fe` / `6772a11b95186be695a9aac9ea5455263459209859cb5831dcba3e5c4de5e4b3` | Пользователь подтвердил ownership независимым evidence и удалил через audited apply и cleanup. Здесь эти действия не повторялись. |
| Старый `f0697295277e151a931d6ee69361e65663e18196295a79baa225fb3cf8905d1d` | Остаётся quarantine. Не инспектировался, не изменялся и не удалялся. |

## 2. Разбор причины по коду

Путь: admission → durable intent → HostConfig builder → raw SDK create → проверка response/Id → durable ownership → get/reload/validation → fenced start. В №19.1.1 широкий `except Exception` в `prepare()` заменял исходную ошибку на `runner_prepare_unknown / unknown_execution`. Поэтому старый terminal receipt не позволяет установить точный этап или класс ошибки.

**Точная причина на VDS пока не установлена.** Код допускает несколько неразличимых по прежнему receipt причин:

| Возможный источник | Почему может быть создан контейнер, но отсутствовать ownership |
|---|---|
| Docker API timeout / transport failure | Daemon мог принять create, а клиент не получил полный ответ. Ошибка не доказывает отсутствие контейнера. |
| Decode/форма SDK response | Ошибка JSON decode, не dict, отсутствие `Id`, неправильный full ID происходят до ownership. Нельзя угадывать ID по имени/labels/альтернативному полю. |
| SQLite write failure | Exact ID уже получен, но own_runner не закоммитился: busy/locked, storage error, binding conflict. Deadline сам по себе не запрещает позднюю запись ownership. |
| Crash между response и commit | Durable intent остаётся, ownership может отсутствовать. |
| Разные исходники/процессы или другой state directory | Не проверено на VDS. Для интерпретации нужны source digests и точная привязка journal/SQLite к запуску. |

Ошибки HostConfig builder до API также попадали в generic prepare unknown; сами по себе они не объясняют появление контейнера. При актуальном managed пути ошибка **после успешного ownership commit**, например `get()`/`reload()`, уже должна оставлять ownership. Поэтому чистая inspect-ошибка не объясняет отсутствие ownership при условии того же кода и той же SQLite.

Локально изучен установленный Docker SDK **7.1.0** без подключения к daemon: low-level create отправляет JSON и декодирует результат через `_result(..., True)`. Текущий контракт ожидает object с `Id`. Реальный ответ Engine 29.9.1 здесь не читался. Общая несовместимость SDK/Engine не доказана: пользователь уже получил успешные basic cases. В новых evidence дополнительно фиксируется версия установленного SDK, рядом с прежней версией daemon. Raw API body не экспортируется.

SQLite busy timeout остаётся 10 с, SDK timeout — 3 с, policy обычного harness — 8 с. Storage contention может пересечь deadline или завершиться write error; это не technical failure target. Лимиты здесь не увеличивались. Связать именно эти события с конкретным VDS receipt без новых диагностик нельзя.

## 3. Почему unknown было больше, чем terminal receipts

`State.admit()` оставляет новый request в issued при `target_busy` или `capacity_exhausted`. Broker возвращает unknown/broker_capacity, но terminal row не записывает. Старый short loop считал каждый такой ответ как очередной unknown и продолжал выдавать UUID.

Например, один ambiguous create с удержанной target lease способен заблокировать следующие 19 запросов к тому же target. Две удержанные leases достигают общего лимита и блокируют и другие targets. Это подтверждённый механизм каскада, **не восстановленная точная разбивка** старых 20 запросов: исходные VDS JSON/SQLite здесь не читались. Нулевой exited counter не доказывает отсутствие всех start attempts и не подтверждает fast-exit race.

## 4. Изменения

- [diagnostics.py](trusted_checker_poc/diagnostics.py): allowlist этапов и классов ошибок, строгая схема, до 32 событий на run. Ошибки классифицируются по типу/SQLite code, без `str(error)`, body или traceback.
- [lifecycle.py](trusted_checker_poc/lifecycle.py), [docker_adapter.py](trusted_checker_poc/docker_adapter.py): стадийная диагностика и проверка raw response. При получении валидного full ID ownership записывается **до inspect, reload и диагностического filesystem I/O**. При write failure сохраняется только факт известного ID, start запрещён; новый create и release не выполняются.
- [broker.py](trusted_checker_poc/broker.py): подключение диагностического sink; устранена повторная запись уже сохранённого ownership в managed пути. Coordinator timeout фиксируется отдельно, после terminal CAS, не затирая текущий этап незавершённого SDK call. Поздний SDK error остаётся виден на своём этапе.
- [evidence.py](trusted_checker_poc/integration/evidence.py): private `prepare-events.jsonl`, mode 0600, append/flush/fsync; строгая проверка при экспорте в `prepare_diagnostics` report.json. Ограничения: 2 MiB / 4096 читаемых событий / строка ≤2048 символов. Ошибка записи поднимает health flag и останавливает дальнейшие сценарии.
- [health.py](trusted_checker_poc/integration/health.py), [runtime.py](trusted_checker_poc/integration/runtime.py), [scenarios.py](trusted_checker_poc/integration/scenarios.py): SELECT-only health, sticky halt, раздельные счётчики, NOT RUN и узкий diagnostic case.
- [CLI](trusted_checker_poc/integration/__main__.py): `run --scenario prepare` — новый default, одна проверка без repetitions/fault injection. Полный suite требует явного `--scenario full`; сейчас его запускать не следует.

Данные нового diagnostic event строго ограничены: run UUID, stage, elapsed_ms от monotonic clock, has_exact_id, конечный error_code, intent_persisted, ownership_persisted, start_invoked. Нет exact ID value, token, nonce, endpoint, environment, inspect, HTTP body, exception strings или credentials. Точный ID для cleanup хранится прежним durable ownership, а не восстанавливается из diagnostic booleans.

Этапы: before_create, create_requested, create_response_received, ownership_persisted, inspect_pending, prepare_finished, start_invoked, cancellation, timeout. Примеры error codes: api_timeout, api_error, transport_error, response_decode_error, response_type_invalid, response_id_missing/invalid, sqlite_busy/locked/error, ownership_binding_error, cancelled, deadline_expired. ValueError/KeyError и неизвестные ошибки имеют нейтральные коды.

В момент raw response данные сначала фиксируются в памяти; response diagnostic записывается после попытки ownership commit. Crash до неё может оставить только create_requested — это честный unknown, а не доказательство отсутствия ответа. Событие start_invoked получает timestamp непосредственно перед SDK callback, но запись sidecar выполняется в finally после callback: диагностический fsync не вставляется между разрешением start и самим SDK вызовом. Если процесс погиб внутри API, отсутствие этого diagnostic event не доказывает отсутствия start; durable runner_starts остаётся отдельным start request.

Все прежние image/user/entrypoint/rootfs/caps/namespaces/mounts/tmpfs/resources/labels/environment/NetworkID guards сохранены. После validation failure HTTP outcome не становится trusted. Integrity по-прежнему означает проверенную конфигурацию в ограниченном scope, не криптографическую аттестацию.

## 5. Fail-fast и метрики

Health проверяется до нового case, до создания network/target, до issue, между short iterations и после case. Halt вызывают unresolved create outcome, lease без подтверждённого handle, cleanup_incomplete, незавершённое исполнение на границе сценариев, environmental integrity failure, ошибка диагностического хранения и prepare failure даже после подтверждённого cleanup. Причина, run UUID и время сохраняются в `halt`.

Начатый case остаётся attempted/test_inconclusive либо test_failed, если уже нарушил assertion. Остальные cases имеют **NOT RUN**, null started_at/finished_at. Прерванный short batch сохраняет фактические измерения и явно перечисляет неисполненные repetitions. После halt новые runtime fixtures и следующие mutation scenarios не создаются. Ожидаемые service_unreachable и намеренные identity-negative cases с подтверждённым cleanup не вызывают halt.

Проверка health не прерывает намеренное промежуточное running состояние внутри concurrency/create-register-race case; контроль выполняется на согласованных границах. Уже начатый bounded SDK request нельзя отозвать задним числом. Late ownership и подтверждённый exact cleanup остаются допустимы, technical receipt не меняется.

| Счётчик | Смысл |
|---|---|
| issued / admitted / not_admitted | Разные UUID в SQLite и реально допущенные requests |
| blocked_by_active_lease | Уникальные возвращённые target_busy/capacity_exhausted requests |
| start_requests | Durable runner_starts: намерение вызвать start, не доказательство запуска |
| start_invocations | Run с наблюдённым вызовом start; sidecar может отсутствовать при crash внутри API |
| physically_started_observed | Run с успешно валидированным live runner; нижняя граница наблюдённых физических запусков |
| start_outcome_unobserved | Start invocation без подтверждённого live наблюдения |
| infrastructure_unknown / timeout | Terminal unknown соответствующих классов; capacity ответы сюда не смешиваются |
| post_start_validation_failure | Уникальные post_start_rejected |
| terminal_receipts | Число сохранённых terminal результатов |

Это счётчики наблюдений, а не полный daemon audit. Динамический fake HTTP всё ещё может удовлетворить synthetic criterion; target_fixture остаётся unknown. Journal/sidecar unsigned, trusted operator directory и daemon остаются TCB. Диагностический I/O добавляет overhead; строгая wall-clock SLA не заявляется.

Cleanup сохраняет прежние exact ID/image/role/scope/run/intent/daemon проверки. Неизвестный ID не ищется и не удаляется, активная неразрешённая lease удерживает fixtures. Новые диагностические flags **не являются ownership evidence** для reconcile. [recovery.py](trusted_checker_poc/recovery.py) и State schema не изменены; independent daemon event/исходный trusted trace по-прежнему обязательны.

## 6. Тесты

Baseline: **130 tests, OK, 4,822 с**. Финальный полный прогон: **154 tests, OK, 5,526 с**, 24 новых сверх baseline. Лог: `/tmp/task1912-tests.log`.

```sh
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

Новые проверки в [test_prepare_diagnostics.py](trusted_checker_poc/tests/test_prepare_diagnostics.py) и [test_integration.py](trusted_checker_poc/tests/test_integration.py): ID перед diagnostic I/O/inspect, failed ownership persistence, API timeout/lost response, malformed response, ошибки с известным/неизвестным ID, quarantine, redaction/bounds, immutable replay без повторного create, fail-fast без новых mutations, 1 attempted + 19 NOT RUN, раздельные counters, expected negative без halt, один diagnostic UUID, post-start integrity failure, fsync failure без потери ownership, отдельный coordinator timeout, отсутствие diagnostic I/O перед start.

Все Docker operations — mocks/fakes. SQLite, threads/processes и filesystem настоящие. Новый start diagnostic fixture сначала не имел обязательной runner projection; исправлена fixture registration, security gate не ослаблялся. Финальный suite прошёл полностью. Django/frontend не запускались: imports и код приложения не менялись.

Проверены SHA256 757 исходных tracked/untracked файлов: изменены только восемь перечисленных PoC-файлов, удалений нет. Добавлены три PoC-файла и этот отчёт. Все прежние отчёты, 83 PNG, Sandbox/Ledger/achievements, migrations, Compose и frontend сохранены. Новые/изменённые файлы проверены на whitespace отдельно, включая untracked paths.

## 7. Архив и обновление исходников на VDS

Минимальный patch поверх №19.1.1: `/tmp/trusted-checker-task19-1-2-update.tar.gz`; SHA256 рядом в `/tmp/trusted-checker-task19-1-2-update.tar.gz.sha256`. Ровно 12 файлов:

```text
trusted_checker_poc/broker.py
trusted_checker_poc/docker_adapter.py
trusted_checker_poc/lifecycle.py
trusted_checker_poc/diagnostics.py
trusted_checker_poc/integration/__main__.py
trusted_checker_poc/integration/evidence.py
trusted_checker_poc/integration/runtime.py
trusted_checker_poc/integration/scenarios.py
trusted_checker_poc/integration/health.py
trusted_checker_poc/tests/test_integration.py
trusted_checker_poc/tests/test_prepare_diagnostics.py
TRUSTED_CHECKER_PREPARE_DIAGNOSTICS.md
```

В архиве нет SQLite/journal/evidence, logs, .env, credentials, .venv, cache, images, PNG, production files или старых отчётов. Runner/target sources и Dockerfiles не менялись: **rebuild images не требуется**. Не изменять Registry, budgets или ownership proofs ради зелёного результата.

На отдельно одобренной VDS остановить только активный PoC Python harness. Сохранить исходники; оригинальные evidence directories не открывать для записи. Сравнить SHA256 архива до/после передачи (`shasum -a 256` локально / `sha256sum` на VDS); затем:

```sh
cd /opt/trusted-checker-poc
umask 077
POC_DIAG_BACKUP=$(mktemp -d /tmp/tc1912-code-backup.XXXXXX)
cp -a trusted_checker_poc "$POC_DIAG_BACKUP/"
if [ -f TRUSTED_CHECKER_PREPARE_DIAGNOSTICS.md ]; then
  cp TRUSTED_CHECKER_PREPARE_DIAGNOSTICS.md "$POC_DIAG_BACKUP/"
fi
(cd /tmp && sha256sum -c trusted-checker-task19-1-2-update.tar.gz.sha256)
tar -tzf /tmp/trusted-checker-task19-1-2-update.tar.gz
tar -xzf /tmp/trusted-checker-task19-1-2-update.tar.gz --no-same-owner -C /opt/trusted-checker-poc
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

Checksum file содержит basename. Старые receipts и SQLite не входят в обновление и не переписываются. Unit suite создаёт только свои временные state directories. Использовать новый Python process.

## 8. Единственный следующий runtime diagnostic

**Здесь не запускался.** Только после подтверждения оператором dedicated daemon, его независимо одобренного ID, Unix endpoint и прежних approved immutable images. `POC_ARGS` — Bash-массив тех же явных approval аргументов из [№19](TRUSTED_CHECKER_DOCKER_INTEGRATION.md); нельзя автоматически получать approval из текущего socket или использовать production/default context. Создать новый private directory, не `/opt/tc19-evidence/run-191-001`:

```sh
cd /opt/trusted-checker-poc
umask 077
POC_DIAG_DIR=/opt/tc19-evidence/run-1912-diagnostic-001
# POC_ARGS заранее задаёт оператор: endpoint, independently approved daemon ID,
# approve-isolated-daemon, scope, approved runner/target IDs и python-base.
.venv/bin/python -m trusted_checker_poc.integration preflight "${POC_ARGS[@]}"
.venv/bin/python -m trusted_checker_poc.integration run "${POC_ARGS[@]}" \
  --allow-execution --scenario prepare --directory "$POC_DIAG_DIR"
.venv/bin/python -m trusted_checker_poc.integration report --directory "$POC_DIAG_DIR"
```

Проверка создаёт собственную temporary internal network и один synthetic target, настраивает bind, выдаёт **один новый run UUID** и делает максимум один runner create. Это не один Docker object в целом: target/network нужны как fixture. Нет 20 repetitions, intentional faults, старого state, старых orphan и повторного исполнения прежнего UUID. Обычный подтверждённый exact cleanup касается только новых собственных ресурсов; ambiguity оставляет quarantine/cleanup_incomplete.

Сохранить новый private journal/SQLite/prepare-events.jsonl и report.json. Проверить последовательность stages, первый ненулевой error_code, has_exact_id и ownership_persisted, metrics и cleanup_status. Например, create_requested/api_timeout без ID указывает на неизвестный API исход; create_response_received/sqlite_busy с ID и без ownership — на write failure; inspect_pending с ownership — на более позднюю ошибку. Это классифицирует этап, но api_error без raw response может потребовать отдельного безопасного operator-side расследования API. Не публиковать private resources/token/state.

Exit 4 означает cleanup_incomplete; 3 — test_inconclusive; 2 — test_failed; 5 — environment_not_approved; 0 узкого run означает только успех этого synthetic case и cleanup. Offline report возвращает 0 за построение отчёта, а не за runtime acceptance.

Не запускать полный suite, старый reconcile/apply/cleanup или orphan removal частью обновления. Если diagnostic дал ambiguous create, остановиться и сохранить evidence; не повторять запросы серией и не снимать lease вручную.

## 9. Условия возврата к полному acceptance

Нужны новый diagnostic с установленным этапом и устранённой причиной ошибки, подтверждённый durable exact ID, сохранённые security invariants, отсутствие unresolved lease/create/cleanup в **новом** запуске, подтверждённые metrics и безопасный cleanup. Затем отдельно согласованный полный runtime acceptance с явным `--scenario full`, новым directory и review каждого failure/NOT RUN/inconclusive. Fast-exit/handshake проверять по live observations; текущие нулевые exited counters его не доказывают. Старые quarantine не считать устранёнными новым green run.

Ранее сохранённые terminal receipts возвращаются неизменными, в том числе generic prepare unknown. Диагностика относится к новым событиям; backfill/reclassification старых результатов нет. Платина выключена. Новые Docker/VDS тесты, orphan recovery и №20 **не выполнялись**.
