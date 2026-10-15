# Trusted Checker: стабильность unit suite — задача №19.1.2.1

15 октября 2026. Ветка `feature/roadmap-react`. Изменены **только тесты и этот отчёт**. Broker, Lifecycle, State, integration writer/session lock, recovery, runner/target, Dockerfiles и runtime configuration сохранены. Docker/VDS integration **NOT RUN**; старые evidence/orphan не читались и не изменялись. Commit/staging/push/deploy и задача №20 не выполнялись.

## 1. Установленные причины

Пользователь сообщил о двух полных VDS прогонах 154 tests: 68,524 с и 33,918 с, с разными отказами; отдельные тесты проходили. Нового VDS trace здесь нет. Анализ исходников устанавливает следующие дефекты fixture:

| Симптом | Причина в тестах |
|---|---|
| `RecoveryTests` не имеет `event` | Атрибут создавался только внутри fake `create()`, а setUp выдавал budget 0,12 с. Deadline мог истечь до create; тест затем обращался к неинициализированному атрибуту. Это instance attribute, а не общий mutable class attribute. |
| `entered.is_set()` false в delayed registration | Тест предполагал достижение register_runner за те же 120 мс. Admission, SQLite transactions, fsync диагностик, SDK fakes и scheduling входят в этот путь. Истечение persisted/monotonic deadline до register законно останавливает worker раньше hook. Проверка deadline в production-like коде корректна; требовать entered при таком порядке нельзя. |
| `Directory not empty` при cleanup | `Broker.execute()` возвращает после terminal CAS/своего cleanup, но не обещает завершения worker. Очередь результата заполняется **до worker finally**; при timeout worker может продолжать late ownership/diagnostics/cleanup. Fixtures удаляли TemporaryDirectory без join. Это допускает параллельное создание SQLite/diagnostic/temp-файлов во время rmtree. Конкретный VDS writer без trace неизвестен; опасный порядок подтверждён исходниками. |
| Межтестовое влияние | Незавершённые worker/audit readers могли переживать mocks и временный каталог, удерживать общие Broker._threads / recovery._EVENTS slots. Закрытие результата и завершение потока — разные события. |

Journal RLock сериализует операции своего writer, а session flock исключает параллельные CLI sessions. Они не являются join для worker и не защищают каталог от удаления самим тестом. Каждый fixture имел собственный TemporaryDirectory, но его lifetime был короче lifetime возможного writer. Новые тесты явно закрывают этот разрыв.

Скорость конкретного filesystem и место задержки на VDS не измерялись. Причина отсутствующего entered не объявляется новой ошибкой cancellation. Добавлена отдельная регрессия: expiry **до** registration закономерно оставляет hook невызванным и запрещает start; expiry до create не требует существующего event. Обратный сценарий теперь явно гарантирует достижение registration перед expiry.

## 2. Исправление fixture lifecycle

Новый [support.py](trusted_checker_poc/tests/support.py) содержит test-only Clock, Inbox, Threads, RuntimeScope и WorkerTestCase:

- Каждый case получает свои clock, thread group, release gates и temporary directory. `self.event` инициализируется как None в RecoveryTests; tests, которым нужен create event, требуют его фактического появления.
- Патчатся только ссылки модулей broker/lifecycle/state на test time и фабрики потоков broker/recovery. Глобальные Python time/threading не заменяются; SQLite transactions, filesystem и внутренние locks остаются настоящими.
- Часы не расходуют test budget на scheduling/fsync. Тест сначала ждёт именованный этап через Event, затем явно переводит wall/monotonic clock за deadline. Test Inbox будит coordinator при этом переходе; частичное продвижение до срока не создаёт fake timeout.
- Общий **30-секундный watchdog** ограничивает ожидание зависшего теста. Его срабатывание даёт AssertionError, а не успешный результат или искусственный timeout receipt. Это предел диагностики зависания, не увеличение tested policy budget. Production budgets не менялись.
- Все Broker workers, recovery audit readers и дополнительные fixture caller threads регистрируются и join-ятся. Cleanup сначала освобождает все зарегистрированные gates, затем ждёт finally, и лишь потом снимает patches/удаляет временные файлы. При watchdog failure с живым потоком каталог сохраняется, а тест падает; rmtree с живым writer не запускается.
- Необработанное BaseException фонового тестового потока передаётся в ошибку основного теста. Единственный намеренный SystemExit crash отмечается явно и проверяется как ожидаемый. Обычные AdapterError по-прежнему обрабатываются самим Broker.
- В fake blocking operations убраны автоматические `wait(1/2/3)` и sleep после release: таймер больше не выпускает fake operation самостоятельно. Вместо них — принадлежащие тесту gates и join. Assertions в concurrent scenarios не оставляют implicit executor shutdown ждать неосвобождённый gate.
- Spawned admission processes используют общий test wall-clock anchor; родитель гарантированно join-ит свои дочерние процессы и завершает их при неуспешном watchdog. Каждый child дожидается собственных broker threads перед выходом.

Исправлены fixtures в Foundation, Recovery, PrepareDiagnostics, Hardening, BrokerDeadline, Integration и одном DockerContract subtest. Там, где mock используется worker, join выполняется **до выхода из patch context**. Прямой replay/cleanup остаётся прежним вызовом; helpers не добавляют permissions и не меняют receipts.

Delayed registration теперь идёт в следующем порядке:

1. Admission, durable intent, raw fake create, ownership и prepare проходят при действующем test deadline.
2. Hook register_runner выставляет entered и блокируется на release gate.
3. Главный тест дожидается entered и явно истекает оба clocks.
4. Broker сохраняет terminal unknown/runner_deadline_exceeded.
5. Тест выпускает hook и ждёт полного завершения worker.
6. Late registration/start запрещены; ownership позволяет только прежний exact cleanup. Terminal replay остаётся прежним.

Отдельный тест блокирует prepare diagnostic I/O **до** registration и проверяет тот же порядок после release. Для случая late success сначала гарантирован реальный fake pass, затем expiry, затем доставка pass; CAS не позволяет заменить terminal unknown. Увеличение sleep или случайного policy timeout для получения зелёного результата не применялось.

## 3. Контракты приложения сохранены

Runtime код **не изменён**: ранний deadline/cancellation правильно запрещает новый create/start. Само возвращение terminal receipt до завершения worker — существующий asynchronous lifecycle, нужный для late ownership/cleanup; тест обязан учитывать его.

Все image/network/security invariants, независимые recovery proofs и quarantine остаются прежними. Никаких SQL UPDATE технических результатов, ретроспективной переклассификации, backfill, force import, удаления orphan или снятия lease нет. Сохранённые technical terminal receipts не затрагиваются. Test clocks/inboxes никогда не подключаются к integration CLI/runtime.

## 4. Проверки и повторные прогоны

Все **154 прежних test IDs сохранены**. Добавлены **12** регрессий: 9 в [test_fixture_lifecycle.py](trusted_checker_poc/tests/test_fixture_lifecycle.py) и 3 в [test_orphan_recovery.py](trusted_checker_poc/tests/test_orphan_recovery.py). Текущее число — **166**.

Новый offline [stability.py](trusted_checker_poc/tests/stability.py) каждый раз создаёт свежие TestCase instances, проверяет уникальность IDs и выполняет normal/reverse/shuffle в одном процессе последовательно. Shuffle seeds: 19121, 19122, 19123. После **каждого теста** проверяются новые live threads/children и восстановление Broker/audit semaphore capacity. Дополнительно учитываются threading.excepthook и sys.unraisablehook.

Финальное дерево проверено на macOS двумя интерпретаторами:

| Интерпретатор / порядок | Полных прогонов | Tests в каждом | Время прогонов, с | Результат |
|---|---|---|---|---|
| Python 3.13.3, обычный | 3 | 166 | 4,457 / 5,150 / 4,439 | OK |
| Python 3.13.3, обратный | 3 | 166 | 5,648 / 4,871 / 5,480 | OK |
| Python 3.13.3, shuffle | 3 | 166 | 4,507 / 5,936 / 4,538 | OK |
| Python 3.12.10, обычный | 3 | 166 | 6,236 / 4,783 / 5,822 | OK |
| Python 3.12.10, обратный | 3 | 166 | 4,637 / 6,200 / 4,658 | OK |
| Python 3.12.10, shuffle | 3 | 166 | 5,777 / 4,878 / 5,414 | OK |

Итого **18 audited полных прогонов / 2988 выполнений tests**, без failures/errors/skips. Во всех 18 отчётах — 0 dangling threads, 0 active children, 0 escaped thread exceptions, 0 unraisable exceptions; проверки capacity после каждого case успешны. Дополнительный обычный `unittest discover -v`: **166 tests / 4,607 с, OK**. Таким образом, полный suite финального дерева прошёл 19 раз.

Три сообщённых проблемных теста отдельно выполнены по **10 раз каждый**, с чередованием прямого/обратного порядка: **30 tests / 1,580 с, OK**. После каждого также проверены threads/processes/capacity; escaped exceptions и dangling threads отсутствуют. Эти 30 не считаются полными прогонами.

Логи/JSON оставлены только в `/tmp/`: `task19121-final-stability.log/json`, `task19121-final-python312-stability.log/json`, `task19121-unittest.log`, `task19121-final-problem-tests.log`. Они не входят в репозиторий/архив. Времена матрицы включают runner overhead и не являются performance benchmark.

Python 3.13.3 использовал проектный venv. Для Python 3.12.10 создан отдельный временный venv без установки из сети; pure-Python dependencies скопированы из локального окружения во временный PYTHONPATH, без native binaries. Docker SDK 7.1.0, requests 2.34.2, urllib3 2.7.0. Начальная попытка системным python3.12 без venv дала два Dockerfile subtest failure из-за отсутствия команды `python` для /bin/sh; после создания нормального venv с этим alias все девять финальных прогонов успешны. Dockerfile test и его ожидания не менялись. Это локальная проверка интерпретатора 3.12, **не Ubuntu/VDS verification**.

На стадии разработки общий join сначала ошибочно ожидал также намеренно заблокированный первый request при проверке второго capacity ответа. Это исправлено разделением asynchronous caller и явного release/join; завершённый итог проверен матрицей выше. Ни отдельный предыдущий зелёный прогон, ни конечная локальная матрица не гарантируют стабильность на любом диске/планировщике. На VDS нужно повторить offline проверку.

Все Docker operations — mocks/fakes; реальные SQLite, threads/processes и filesystem сохраняются. Dockerfile tests запускают только ARG validation через /bin/sh, без Docker build. Django/frontend не запускались: код приложения и imports не менялись.

SHA256 исходных 761 tracked/untracked файлов сверены: изменены только восемь test-файлов; удалений нет. Все runtime sources, прежние отчёты и 83 PNG сохранены. Добавлены три test/support-файла и этот отчёт. Whitespace и Python syntax новых/изменённых файлов проверены отдельно, включая untracked paths.

## 5. Минимальный архив

Patch поверх установленного №19.1.2: `/tmp/trusted-checker-task19-1-2-1-update.tar.gz`; SHA256 — `/tmp/trusted-checker-task19-1-2-1-update.tar.gz.sha256`. Только 12 файлов:

```text
trusted_checker_poc/tests/fakes.py
trusted_checker_poc/tests/support.py
trusted_checker_poc/tests/stability.py
trusted_checker_poc/tests/test_fixture_lifecycle.py
trusted_checker_poc/tests/test_docker_contract.py
trusted_checker_poc/tests/test_foundation.py
trusted_checker_poc/tests/test_integration.py
trusted_checker_poc/tests/test_orphan_recovery.py
trusted_checker_poc/tests/test_prepare_diagnostics.py
trusted_checker_poc/tests/test_runtime_hardening.py
trusted_checker_poc/tests/test_timeout_semantics.py
TRUSTED_CHECKER_TEST_STABILITY_FIX.md
```

Нет runtime sources, SQLite/journal/evidence, logs, .env, credentials, .venv, caches, images, PNG и production files. Старые отчёты не заменяются. Images/Registry/Compose не менялись: rebuild и restart Docker daemon не требуются.

## 6. Обновление VDS и только unit verification

Завершить активный PoC unit/harness процесс перед заменой тестов. Сохранить старые tests; **не копировать и не открывать старые evidence для записи**. Сравнить SHA256 до/после передачи (`shasum -a 256` локально / `sha256sum` на VDS), проверить manifest, затем:

```sh
cd /opt/trusted-checker-poc
umask 077
POC_TEST_BACKUP=$(mktemp -d /tmp/tc19121-tests-backup.XXXXXX)
cp -a trusted_checker_poc/tests "$POC_TEST_BACKUP/"
if [ -f TRUSTED_CHECKER_TEST_STABILITY_FIX.md ]; then
  cp TRUSTED_CHECKER_TEST_STABILITY_FIX.md "$POC_TEST_BACKUP/"
fi
(cd /tmp && sha256sum -c trusted-checker-task19-1-2-1-update.tar.gz.sha256)
tar -tzf /tmp/trusted-checker-task19-1-2-1-update.tar.gz
tar -xzf /tmp/trusted-checker-task19-1-2-1-update.tar.gz --no-same-owner -C /opt/trusted-checker-poc
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

Запускать из project root новым Python process. Использовать существующий venv Python 3.12 с установленными dependencies, включая Docker SDK 7.1.0; новый пакет не требуется. Никакой Docker endpoint для unit suite не нужен.

Повторить полную offline матрицу на VDS; результат записать в **новый /tmp directory**, вне прежних evidence:

```sh
POC_STABILITY_DIR=$(mktemp -d /tmp/tc19121-unit-results.XXXXXX)
.venv/bin/python -m trusted_checker_poc.tests.stability \
  --repeats 3 --orders normal reverse shuffle --seed 19121 \
  --output "$POC_STABILITY_DIR/results.json" \
  > "$POC_STABILITY_DIR/results.log" 2>&1
```

Ожидается девять прогонов по 166 без skips, failures/errors, dangling threads/processes, unhandled/unraisable exceptions. Driver прекращает матрицу и возвращает exit 1 при первом отказе; watchdog не следует лечить добавлением sleep. При ошибке сохранить свежие unit logs и traceback. Существующие VDS journal/SQLite/orphan не входят в эти tests и не читаются.

Один зелёный прогон не считается достаточной проверкой стабильности. Даже успешная unit матрица не даёт runtime acceptance: Docker integration, prepare diagnostic, reconcile/apply, cleanup старых ресурсов и задача №20 **не запускаются** частью этого обновления.
