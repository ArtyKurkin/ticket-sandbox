# Trusted Checker: Docker integration harness — задача №19

15 октября 2026. Ветка `feature/roadmap-react`, исходный HEAD `26cdce0bd3edfbd7d977f855f01d8389d03c06f6`.

Реализован opt-in CLI [trusted_checker_poc.integration](trusted_checker_poc/integration/__main__.py). Новые испытания настоящего Docker: **NOT RUN** — в этой сессии нет доступа к отдельно одобренной VDS. Локальный Docker Desktop/socket, production и рабочие БД не использовались. Результаты ниже разделены на исходные ручные сведения пользователя и новые локальные unit/fake проверки.

## Архитектура и границы

Команды: `preflight`, `run`, `report`, `cleanup`. Импорт CLI не подключается к Docker. Нет `from_env`, выбора context, pull/build и запуска Compose. Поддерживается только явно переданный Unix endpoint: CLI исполняется непосредственно на выделенной VDS. Удалённый plaintext TCP не поддерживается.

`run` после read-only preflight создаёт свою internal bridge network и временные synthetic targets с UUID/generation/ownership token. Scope получает суффикс integration UUID. Существующий target пользователя не принимается и не изменяется. Опциональный `--network-id` только инспектируется в preflight; `run` создаёт новую сеть. Проверки используют штатные `Broker → DockerAdapter → runner → HTTP target → Broker → SQLite`.

Новые модули:

| Файл | Назначение |
|---|---|
| [safety.py](trusted_checker_poc/integration/safety.py) | Explicit approval до SDK, проверка daemon/platform/images/network, exact ownership |
| [evidence.py](trusted_checker_poc/integration/evidence.py) | Private journal, atomic/fsync JSON, exclusive session lock, JSON/Markdown |
| [runtime.py](trusted_checker_poc/integration/runtime.py) | Собственные ресурсы, enrollment, fixture readiness, диагностический adapter и cleanup |
| [scenarios.py](trusted_checker_poc/integration/scenarios.py) | Runtime scenarios и самостоятельные acceptance checks, сохраняющиеся при `python -O` |
| [__main__.py](trusted_checker_poc/integration/__main__.py) | CLI, exit codes, approval и связка с журналом |
| [__init__.py](trusted_checker_poc/integration/__init__.py) | Standalone package marker |

В [DockerAdapter](trusted_checker_poc/docker_adapter.py) добавлен no-op diagnostic hook для pre-start/starting/validated-live/finished. Он не отменяет прежние guards. HTTP outcome читается только после live identity validation; конфигурация повторно проверяется после wait. Production-путь Sandbox не импортирует пакет.

[Synthetic fixture](trusted_checker_poc/synthetic_target.py) теперь подтверждает reload через digest `/fixture/ready.json` и принимает ограниченный `response_delay` 0–10 с. Это специально заданная нагрузка HTTP для concurrency/deadline tests, не sleep checker перед validation. Bind меняется атомарно без Docker restart. Fixture exec администрирует только собственный тестовый target; его stdout/exit не становится источником технического verdict.

## Готовность выделенного окружения

Оператор отдельно подтверждает, что daemon выделен PoC, не содержит `training-platform-*`/`training-platform-prodtest-*`, не разделяет production host/resources/credentials. Сам флаг approval и совпадение daemon ID не доказывают изоляцию. Наличие socket также не доказательство. Здесь не выполняется широкая инвентаризация/поиск контейнеров по labels.

Требования: Linux/amd64, Python 3.12+ для harness, проектный Docker SDK 7.1.0, локальный filesystem, private operator directory. SQLite/journal нельзя монтировать в target/runner или хранить на сетевом FS. Соблюдайте неизменность исходников и Registry во время запуска. Один journal обслуживает один процесс; `flock` не позволяет одновременно запускать cleanup и run. Потоки broker сериализуют диагностические записи тем же lock.

По умолчанию выполнение запрещено. Нужны одновременно `--approve-isolated-daemon`, точный `--approved-daemon-id`, explicit endpoint и для `run`/`cleanup` отдельный `--allow-execution`. Preflight делает только GET info/version/images/network; проверяет ID, Linux/amd64, exact immutable image IDs и отсутствие declared image volumes. Secrets, full inspect/env/history и endpoint в evidence не экспортируются.

Preflight подтверждает доступные configuration facts, а не аудит хоста, правильность сборки или готовность всех adapters. Approved images и оператор остаются частью TCB.

## Сборка и provenance на VDS

Исторический base из ручных испытаний пользователя:

```text
python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe
linux/amd64
```

Это историческое сведение, не автоматическое production approval. Оба существующих Dockerfile уже передают `"$PYTHON_BASE"` в `python -c` и проверяют `sys.argv[1]` регулярным выражением с обязательным SHA256; эти проверки повторно выполнены unit tests, включая `PYTHONOPTIMIZE=1`. Dockerfile в задаче №19 не менялись.

После обновления исходников пересоберите оба PoC images на **уже проверенном dedicated daemon**. Не используйте project Compose, `.env.prod`, default context или fake digest из tests. Значения переменных задаёт оператор; команды ниже не были выполнены здесь:

```sh
cd /opt/trusted-checker-poc
umask 077
POC_ENDPOINT=unix:///var/run/docker.sock
# Этот путь допустим только на отдельно одобренной VDS, не на локальном Desktop.
POC_PYTHON_BASE=python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe
POC_BUILD=$(mktemp -d /tmp/tc19-build.XXXXXX)
docker --host "$POC_ENDPOINT" build --platform linux/amd64 \
  --build-arg "PYTHON_BASE=$POC_PYTHON_BASE" --iidfile "$POC_BUILD/runner.iid" \
  -f trusted_checker_poc/images/runner/Dockerfile trusted_checker_poc/
docker --host "$POC_ENDPOINT" build --platform linux/amd64 \
  --build-arg "PYTHON_BASE=$POC_PYTHON_BASE" --iidfile "$POC_BUILD/target.iid" \
  -f trusted_checker_poc/images/target/Dockerfile trusted_checker_poc/
POC_RUNNER_IMAGE=$(cat "$POC_BUILD/runner.iid")
POC_TARGET_IMAGE=$(cat "$POC_BUILD/target.iid")
```

Особенно важно пересобрать target: старый image не поддерживает readiness/delay protocol. Harness не строит и не подтягивает images автоматически. `report.json` фиксирует операторский base input, actual inspected image IDs, source SHA256 всех Python/Dockerfile файлов и policy/source digest. Correspondence source→image остаётся обязанностью проверенной сборки оператора; полноценной supply-chain attestation здесь нет. Новые реальные image IDs неизвестны до сборки на VDS.

## Safe preflight и запуск

Создайте parent evidence directory отдельно; `--directory` для `run` должен быть новым путём. Harness создаёт его с mode 0700, JSON/Markdown — 0600. Не записывайте туда credentials. Approval daemon ID возьмите из независимого операторского подтверждения выделенного хоста, а не автоматически присваивайте из текущего Docker endpoint.

```sh
POC_DAEMON_ID='REPLACE_WITH_INDEPENDENTLY_APPROVED_DAEMON_ID'
POC_SCOPE=poc-task19
mkdir -p /opt/tc19-evidence
chmod 700 /opt/tc19-evidence
POC_RUN_DIR=/opt/tc19-evidence/run-001
# Bash на VDS: массив сохраняет границы аргументов, без eval.
POC_ARGS=(--endpoint "$POC_ENDPOINT" --approved-daemon-id "$POC_DAEMON_ID"
  --approve-isolated-daemon --scope "$POC_SCOPE"
  --runner-image "$POC_RUNNER_IMAGE" --target-image "$POC_TARGET_IMAGE"
  --python-base "$POC_PYTHON_BASE")
.venv/bin/python -m trusted_checker_poc.integration preflight "${POC_ARGS[@]}"
.venv/bin/python -m trusted_checker_poc.integration run "${POC_ARGS[@]}" \
  --allow-execution --directory "$POC_RUN_DIR" --repetitions 20
.venv/bin/python -m trusted_checker_poc.integration report --directory "$POC_RUN_DIR"
```

`report` — offline восстановление JSON/Markdown из journal и SELECT-only SQLite, затем просмотр; Docker не используется. Новые UUID broker выдаёт сам; старые terminal unknown не перезапускаются. Harness создаёт отдельную SQLite, не читает прежний VDS state и не меняет старый target. При продолжении ручного harness после обновления запускайте новый Python-процесс.

Exit codes: 0 — preflight/выбранная операция успешны; 2 — test_failed; 3 — test_inconclusive; 4 — cleanup_incomplete; 5 — environment_not_approved. Argparse usage error также возвращает 2, но не создаёт test artifact. **Полный run сейчас имеет минимум пять явно fake-only scenarios**, поэтому общий статус останется `test_inconclusive`/exit 3 даже при успешных остальных runtime assertions. Не интерпретируйте это как all-green; смотрите отдельные scenarios и cleanup_status. Unexpected unknown в положительном тесте даёт inconclusive. Отрицательный identity-тест считается выполненным только если получен именно ожидаемый unknown/identity reason; это не технический pass target.

## Автоматизированные runtime scenarios

| Сценарий | Проверяемое поведение |
|---|---|
| Localhost → network bind | failed/service_unreachable → новый run passed/probe_passed, тот же ID/generation/StartedAt, старый receipt неизменен, runner отсутствует по exact ID |
| Короткие запуски | 1–50 последовательных runs, elapsed/reason, start attempts и live observations, количество `exited` до post-start validation |
| Security | UID/GID, RO rootfs, privilege/caps/NNP, namespaces, mounts/tmpfs, resources, labels, exact image/network; отдельный ограниченный exec в валидированном runner читает `/proc/self/status`, проверяет UID/GID, CapEff/NoNewPrivs, запрет открытия checker на запись и отсутствие socket |
| Независимость FS | Root synthetic target меняет собственные `/task/check.sh`, `/usr/local/bin/curl`, `/checker/runner.py`; runner source digest остаётся эталонным, probe остаётся независимым |
| Identity | Stop/restart собственного target, stale StartedAt/generation enrollment, удалённый old full ID, исчезновение во время probe, чужая/дополнительная сеть |
| Concurrency/replay | Один run одновременно, другой run на active lease, один live/start attempt, immutable replay, новый Broker над той же SQLite |
| Deadline/late completion | Delayed HTTP, broker deadline, immutable terminal после завершения фоновой операции; без observed live runner этот сценарий inconclusive |
| Crash/hang | SIGKILL либо SIGSTOP только валидированного записанного runner; unknown и exact cleanup после deadline |
| Cleanup guards | Target нельзя удалить как runner; неверные image/scope/run отклоняются; повтор подтверждённого cleanup не вызывает новое remove |

Security exec — заранее заданный trusted diagnostic без shell, socket, сетевых запросов, task-кода или чтения secrets. Он не заменяет guard и может оказаться inconclusive при короткой жизни runner. Попытка открыть checker на запись не меняет его bytes. Отказ записи сам по себе не отличает DAC от mount protection, поэтому RO конфигурация фиксируется отдельно. Эти наблюдения не доказывают защиту от kernel exploit, все возможные namespace атаки или неизменность target-приложения. `target_fixture=unknown` сохраняется.

Generation и StartedAt mismatch тестируются с заранее созданной stale enrollment в собственной SQLite **до issue**, без переписывания issued/terminal snapshot и без фиктивного заявления об изменении immutable Docker labels. Network mutations выполняются только после exact ownership проверки собственных сетей/targets.

## Fake-only проверки и race коротких запусков

Docker API timeout, start failure, потеря ответа create/remove и строгое восстановление unregistered orphan проверены fault injection на SDK fakes. Эти faults не навязываются реальному daemon; daemon VDS не останавливается. Late **success**, который пытается перезаписать timeout, проверяется настоящим broker/thread/SQLite с fake adapter; runtime проверяет позднее завершение, но не обещает получить поздний success после force cleanup. Конфигурационные подмены/caps/mounts и межпроцессный admission также имеют прежние fake/SQLite tests.

Новая частота fast-exit race **не измерена**. В JSON предусмотрены `short_runner_measurements`, `short_runner_summary` и `post_start_rejected/state=exited`. Это позволяет отделить наблюдённое раннее завершение от прочих integrity/infrastructure ошибок. Наблюдаемый race блокирует positive test; пустой NetworkID никогда не становится trusted.

Handshake не реализован без runtime evidence. Если на VDS ранний exit воспроизведётся, минимальный кандидат: immutable runner до probe сообщает ready по отдельному authenticated broker-owned каналу, broker валидирует live identity, затем одноразово разрешает probe. Нужны deadline/cancel, защита от replay и запрет HTTP до release; это отдельное исправление с adversarial tests. Произвольный sleep и отключение post-start проверки неприемлемы. Diagnostic journal I/O добавляет overhead, поэтому замер относится именно к harness configuration.

## Evidence, receipts и hardening

Private run directory содержит `journal.json`, `report.json`, `report.md`, `state.sqlite`, lock. JSON содержит integration UUID, daemon ID/version/platform, scope, actual network/target/image identities, generations/enrollments, source digests, policy, timestamps, scenarios/reasons, наблюдения, start attempts, immutable terminal и отдельные cleanup receipts. `physical_starts` означает число **валидированных live наблюдений**, а `start_attempts` фиксирует обращение к start до SDK call: start error/fast exit не считаются подтверждённым live запуском. Не выдавайте один счётчик за полный daemon audit.

Journal и отчёты unsigned и изменяемы trusted оператором; они не являются runtime attestation. Artifact writer запрещает замену уже экспортированного terminal receipt. Raw Docker attrs/env/HTTP body/challenge, exceptions, Docker endpoint, credentials и произвольные host paths не экспортируются. Если SDK/парсер ошибся, сохраняется нейтральный reason. State/journal входят в TCB, их нельзя подменять или редактировать ради зелёного результата.

Дополнительные исправления Broker:

1. При восстановлении running receipt используется исходный persisted policy snapshot, а не новый timeout/artifact Registry.
2. Повтор подтверждённого cleanup использует durable receipt и освобождает оставшуюся lease без нового Docker remove.
3. Завершившийся отказ **до вызова `prepare()`** освобождает lease: физический create положительно исключён. Ошибка/timeout внутри prepare, потерянный create response или ещё выполняющийся inspect не дают такого доказательства и сохраняют quarantine. Это закрывает исчерпание лимита после обычных отрицательных identity tests.

Cleanup сначала обрабатывает записанные runner через Broker, затем все собственные targets, затем сети. Этот порядок нужен и для дополнительной сети, созданной после target. Network с оставшимися endpoints не удаляется. При неподтверждённом create/active lease удаление fixtures блокируется.

## Exact-ID cleanup и orphan reconciliation

```sh
.venv/bin/python -m trusted_checker_poc.integration cleanup "${POC_ARGS[@]}" \
  --allow-execution --directory "$POC_RUN_DIR"
```

Cleanup повторно проверяет daemon/images и привязку journal к исходному scope/UUID. Runner удаляется только по durable full ID + image + role/scope/run. Targets/networks — только по full ID, записанному из ответа **собственного create**, с integration ID/token/scope/role, target image/generation. Ни `list/prune`, ни поиск по имени/labels, ни удаление чужих ресурсов отсутствуют. Подтверждённое отсутствие записанного fixture отмечается отдельно, без изготовления runner cleanup receipt. Потерянный ответ удаления runner с последующим NotFound остаётся ambiguous: lease не снимается автоматически.

При `cleanup_incomplete`:

1. Остановить только данный harness, не daemon/platform. Сохранить private journal/SQLite; не удалять receipts и не исполнять `DELETE FROM locks`.
2. Проверить исходный одобренный daemon ID, integration UUID, exact зарегистрированные IDs, image, generation и tokens. Для известных runner с неизменной identity повторить штатный cleanup. Успешный технический receipt при cleanup fault остаётся прежним.
3. `create_intent` без full ID или running row без runner handle — orphan window. Автоматического adoption/удаления по похожему имени или labels нет. Оператор отдельно собирает trusted create/API audit, связывающий конкретный full ID с исходным create intent; labels и совпадение image сами по себе недостаточны. Только после независимого подтверждения ownership допустимо операторское exact-ID действие на dedicated daemon.
4. Если такого доказательства нет — **не удалять** кандидата и не снимать lease. Сохранить quarantine для расследования/отдельной операторской процедуры. Текущий CLI намеренно не предоставляет флаг «принудительно считать orphan своим» и не записывает произвольный cleanup receipt.
5. Для lost remove response подтвердить отсутствие именно записанного ID на исходном daemon и отсутствие исполнителя независимым операторским аудитом. Автоматического подтверждения и journal surgery здесь нет; формализованный audited reconciliation command остаётся задачей hardening.

## Что действительно проверено

Исходный baseline: **50 unit/fake tests, OK, 2,230 с**. Новые tests находятся в [test_integration.py](trusted_checker_poc/tests/test_integration.py) и [test_runtime_hardening.py](trusted_checker_poc/tests/test_runtime_hardening.py). Они проверяют CLI admission до SDK, explicit endpoint, read-only preflight, image/network/platform guards, private artifacts, lock, receipt immutability, cleanup ordering/ownership/ambiguity, no-create proof, recovery policy, lifecycle diagnostics, optimization safety и fixture schema. Docker SDK везде mocked; SQLite/threads/processes и artifact filesystem настоящие. **Финальный прогон: 86 тестов, OK, 2,928 с** (36 новых тестов сверх baseline). Лог: `/tmp/task19-tests.log`. Ошибки первого прогона новых SDK fixtures были связаны с фиксированным run label вместо issued UUID; fixture исправлен без ослабления guards. Повторное обнаружение импортированного unittest-класса также устранено; итоговые 86 — без такого дублирования.

Новые реальные Docker builds, namespaces, network HTTP, сигналы, runtime security probes, orphan/daemon-loss recovery и performance: **NOT RUN**. Django/frontend не запускались: общие imports и исходники приложения не менялись. Dockerfiles проверяются реальным `/bin/sh` в unit suite, без Docker build.

Исторические ручные результаты **со слов пользователя**, до этой автоматизации: отдельная Timeweb VDS Ubuntu 24.04.5, Engine 29.9.1, linux/amd64, 2 vCPU/~4 GB; 50 Python tests; localhost failed/service_unreachable и network bind passed/probe_passed (~1,1 с), verified_configuration, matched_before_and_after, неизменный target ID/generation/StartedAt, RestartCount0, runners удалены. Эти результаты не являются новым прогоном harness, не имеют новых artifact IDs и не обобщаются на другие Engine/host policies.

## Передача и следующий этап

Архив `/tmp/trusted-checker-task19-update.tar.gz` содержит только перечисленные ниже исходники/тесты и этот отчёт. Он рассчитан на существующий checkout задачи №18 с NetworkID fix, не является полным standalone дистрибутивом.

```text
trusted_checker_poc/broker.py
trusted_checker_poc/docker_adapter.py
trusted_checker_poc/synthetic_target.py
trusted_checker_poc/integration/__init__.py
trusted_checker_poc/integration/__main__.py
trusted_checker_poc/integration/safety.py
trusted_checker_poc/integration/evidence.py
trusted_checker_poc/integration/runtime.py
trusted_checker_poc/integration/scenarios.py
trusted_checker_poc/tests/test_foundation.py
trusted_checker_poc/tests/test_integration.py
trusted_checker_poc/tests/test_runtime_hardening.py
TRUSTED_CHECKER_DOCKER_INTEGRATION.md
```

На VDS завершите только PoC harness и сохраните копии заменяемых файлов. Сравните SHA256 архива до/после передачи (`shasum -a 256` / `sha256sum`); проверьте `tar -tzf`. Распакуйте в существующий `/opt/trusted-checker-poc` с `--no-same-owner`; старые Registry settings/state/VDS scripts не входят в архив. Выполните unit suite, пересоберите images, запустите preflight/run по инструкции выше. Прежние отчёты №17–18/NetworkID fix и PNG не заменяются. В архиве нет `.venv`, SQLite, `.env`, logs, credentials, production files или PNG.

```sh
cd /opt/trusted-checker-poc
POC_UPDATE_BACKUP=$(mktemp -d /tmp/tc19-backup.XXXXXX)
cp -a trusted_checker_poc "$POC_UPDATE_BACKUP/"
if [ -f TRUSTED_CHECKER_DOCKER_INTEGRATION.md ]; then
  cp TRUSTED_CHECKER_DOCKER_INTEGRATION.md "$POC_UPDATE_BACKUP/"
fi
tar -tzf /tmp/trusted-checker-task19-update.tar.gz
tar -xzf /tmp/trusted-checker-task19-update.tar.gz --no-same-owner -C /opt/trusted-checker-poc
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

Перед задачей №20 нужен отдельный **runtime acceptance на VDS**: сохранить JSON/Markdown, разобрать каждый inconclusive/failure и cleanup, измерить fast-exit ratio, подтвердить security observations, согласовать orphan/lost-response reconciliation и проверить совместимость SDK/daemon defaults. Если race воспроизведётся — требуется исправление handshake до следующего пилота. Без этих результатов runtime foundation остаётся неподтверждённой.

Sandbox scoring/check_task_container/CheckRun/Ledger/achievements/платина/Roadmap/Trophy/Diary, migrations, Compose и отчёты №17–18 не менялись. Нет Sandbox attempts/source events/notifications/ordinals, commit/staging/push/merge/deploy и production operations. 83 PNG сохранены. Platinum остаётся выключенной.
