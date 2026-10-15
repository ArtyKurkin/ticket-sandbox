# Trusted Checker: timeout/cancellation — задача №19.1.1

15 октября 2026. Исправление ограничено standalone PoC. Docker integration, локальный Docker Desktop/socket и VDS не использовались. Существующие VDS journal/SQLite/evidence не изменялись. Commit/push/deploy не выполнялись.

## Причина регрессии

Пользователь сообщил о прогоне на Ubuntu 24.04.5: 112 tests / 23,535 с, один отказ в `test_timeout_late_pass_never_replaces_receipt`: `execution_cancelled` вместо `runner_deadline_exceeded`.

В №19.1 `Lifecycle.check()` объединял три разных основания отказа: cancellation Event, monotonic deadline и persisted deadline/status. Все они превращались в `AdapterError('execution_cancelled', 'unknown_execution')`. State gates для create/start также смешивали expired deadline и закрытое execution; `Lifecycle.start()` дополнительно заменял любой InvalidRequest на cancellation.

Время учитывается на двух границах:

1. Broker вычисляет wall-clock deadline до `State.admit()` и сохраняет его в SQLite.
2. Admission, чтение row, policy checks и прочая подготовка занимают время.
3. Локальный monotonic deadline ожидания результата создаётся позже. Он не продлевает persisted разрешение запуска: Lifecycle/State всё равно проверяют более раннюю сохранённую границу.
4. На медленном filesystem или при scheduling задержке persisted deadline может истечь раньше локального queue timeout.
5. Worker раньше координатора замечает expired persisted deadline, но старый Lifecycle отправляет cancellation. Пока локальный queue deadline ещё не наступил, Broker принимает эту причину и сохраняет её как terminal unknown.
6. При другом порядке координатор первым получает queue timeout и сохраняет ожидаемый `runner_deadline_exceeded`. Поэтому локальные 112 tests ранее могли проходить, а VDS — давать другую причину.

Точное место задержки на VDS без trace неизвестно. Подтверждённая по коду ветка воспроизведена детерминированно: в отдельной временной копии пакета восстановлены исходные `lifecycle.py/state.py` из архива №19.1 с SHA256 `107c869653c7f85389fa4ef03ab7274ef1e971249aa1bcfc9c91dbcb915d45e8`. Новый тест `test_worker_persisted_deadline_timeout_arrives_before_coordinator_timer` на старом коде воспроизводит `execution_cancelled / unknown_execution` вместо timeout. Лог ожидаемого отказа: `/tmp/task1911-old-code-regression.log`. Рабочие исходники этим экспериментом не заменялись.

## Контракт причин завершения

| Наблюдаемое основание | result / reason / failure_class |
|---|---|
| Локальный monotonic deadline достигнут либо persisted deadline истёк | `unknown / runner_deadline_exceeded / timeout` |
| Event cancellation или execution уже закрыто, оба наблюдаемых срока ещё не истекли | `unknown / execution_cancelled / unknown_execution` |
| Ошибка БД/adapter, исход которой не доказан | прежний `unknown` с infrastructure/unknown_execution; никогда не technical failed |
| Старый running receipt после потери процесса, неизвестен исход исполнения | прежний recovery `execution_outcome_unknown / unknown_execution` |
| Ранее сохранённый terminal receipt | возвращается без переклассификации |

Event используется также для fencing после timeout/terminal closure и не хранит отдельный reason/time. По одному установленному Event нельзя доказать, что произошла именно явная пользовательская отмена. Пока оба срока ещё действуют, cancellation различима от timeout. Если deadline уже наблюдаемо истёк, generic Event не скрывает timeout; исторический порядок установки Event по этому флагу не угадывается. Новый публичный cancellation API не добавлялся.

`timeout` означает потерю разрешённого временного окна, а не доказанный технический провал target. Результат остаётся unknown; no auto retry под старым run UUID. Поведение recovery после потери процесса не заменяется timeout постфактум, поскольку исход физической операции тогда неизвестен.

## Изменения кода

- [lifecycle.py](trusted_checker_poc/lifecycle.py): отдельная проверка monotonic deadline, повтор после чтения State; persisted deadline проверяется до generic cancellation/status. Проверка внутри start fence также различает timeout и cancellation. Из State преобразуются только известные execution gates; unrelated validation/storage errors не объявляются отменой.
- [state.py](trusted_checker_poc/state.py): create/start gates под SQLite lock возвращают отдельный `InvalidRequest('runner_deadline_exceeded')` при expired persisted deadline. Закрытие execution до deadline сохраняет `execution_cancelled`. Callback start при отказе не вызывается.
- [test_foundation.py](trusted_checker_poc/tests/test_foundation.py): исходная проверка позднего pass сохранена и сделана независимой от скорости диска.
- [test_timeout_semantics.py](trusted_checker_poc/tests/test_timeout_semantics.py): 18 новых регрессионных тестов для worker-before-coordinator порядка, границ обоих clocks, cancellation до срока, окончания срока внутри State/start fence, инфраструктурных ошибок и replay прежнего receipt.

`broker.py`, DockerAdapter, ownership/recovery и schema не менялись. Сериализация start/finish и cleanup из №19.1 сохранена. Пропущенный deadline не разрешает новый Docker start. In-flight request, уже отправленный daemon до timeout, по-прежнему нельзя отменить задним числом; он остаётся под прежним unknown/cleanup lifecycle.

## Почему уточнён исходный тест

Старый тест требовал одновременно budget 30 мс и ровно один physical fake run. На медленной VDS эти 30 мс могут закончиться ещё до create/start. Ноль запусков в таком случае — правильное выполнение запрета late start, а не ошибка реализации. Следовательно, такой timing fixture не гарантировал сценарий «late success уже начатой проверки».

Ожидаемая причина не ослаблена. Новый fixture сначала гарантированно получает настоящий `passed` от fake adapter и удерживает его доставку. Затем управляемый локальный clock достигает deadline, coordinator сохраняет timeout, после чего доставка success освобождается. Проверяется:

- строго `unknown / runner_deadline_exceeded / timeout`;
- поздний worker также распознаёт timeout;
- replay возвращает точно прежний receipt;
- physical fake execution ровно один;
- дополнительная попытка записать passed отклоняется terminal CAS.

Случай окончания срока **до** выполнения независимо проверен новыми тестами: никаких create/start/physical calls. Управляемые clocks и queue используются только в tests; production timeout budget и сценарии Docker не увеличивались. Нет sleep для «лечения» scheduling race.

## Уже сохранённые terminal receipts

Исправление применяется к новым решениям о завершении. Старые `execution_cancelled`, `runner_deadline_exceeded`, passed и другие terminal receipts остаются байт-в-байт прежними при replay. Не выполняются backfill, SQL UPDATE результата, пересоздание run UUID или изменение evidence.

Это особенно важно для receipts №19.1 с ошибочно выбранной причиной: новое понимание причины описывается отчётом, но immutable история не переписывается. Late ID registration по-прежнему разрешена только для ownership/cleanup и не даёт права заменить terminal unknown на passed. Для отдельного нового испытания в будущем нужен новый run ID; автоматически оно здесь не запускается.

## Проверки

Исходный локальный baseline: **112 tests, OK, 4,937 с**. Это не повтор результата VDS: внешние 112 tests имели один отказ.

**Полный финальный прогон: 130 tests, OK, 4,793 с; 18 новых tests сверх baseline.** Лог: `/tmp/task1911-tests.log`. Команда:

```sh
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

Все Docker operations в suite — mocks/fakes. SQLite, threads/processes и filesystem используются реально. Новые проверки не подключаются к daemon; Docker integration не запускался. Django/frontend не запускались: общие imports и код приложения не менялись.

## Минимальное обновление VDS

Архив `/tmp/trusted-checker-task19-1-1-update.tar.gz` рассчитан на установленный №19.1. В нём только пять файлов:

```text
trusted_checker_poc/lifecycle.py
trusted_checker_poc/state.py
trusted_checker_poc/tests/test_foundation.py
trusted_checker_poc/tests/test_timeout_semantics.py
TRUSTED_CHECKER_TIMEOUT_CANCELLATION_FIX.md
```

SHA256 находится в `/tmp/trusted-checker-task19-1-1-update.tar.gz.sha256`. Архив не содержит SQLite/journal/evidence, `.env`, credentials, `.venv`, logs, images, production files и PNG.

На отдельной VDS остановить только активный PoC Python harness перед заменой исходников, не daemon. Проверить SHA256 архива до и после передачи (`shasum -a 256` локально / `sha256sum` на VDS), сохранить старые исходники, проверить manifest, распаковать и выполнить **только unit/fake suite**:

```sh
cd /opt/trusted-checker-poc
umask 077
POC_FIX_BACKUP=$(mktemp -d /tmp/tc1911-backup.XXXXXX)
cp --parents trusted_checker_poc/lifecycle.py trusted_checker_poc/state.py \
  trusted_checker_poc/tests/test_foundation.py "$POC_FIX_BACKUP/"
if [ -f trusted_checker_poc/tests/test_timeout_semantics.py ]; then
  cp --parents trusted_checker_poc/tests/test_timeout_semantics.py "$POC_FIX_BACKUP/"
fi
if [ -f TRUSTED_CHECKER_TIMEOUT_CANCELLATION_FIX.md ]; then
  cp TRUSTED_CHECKER_TIMEOUT_CANCELLATION_FIX.md "$POC_FIX_BACKUP/"
fi
sha256sum /tmp/trusted-checker-task19-1-1-update.tar.gz
tar -tzf /tmp/trusted-checker-task19-1-1-update.tar.gz
tar -xzf /tmp/trusted-checker-task19-1-1-update.tar.gz --no-same-owner -C /opt/trusted-checker-poc
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

Не запускать integration run, reconcile/apply или cleanup как часть этого обновления. Images/Registry не менялись, rebuild не требуется. Unit suite создаёт свои временные SQLite и не читает существующие evidence на VDS. Использовать новый Python process после замены исходников.

Sandbox, Ledger, achievements, production, Compose, Django migrations, платина и 83 PNG не изменены. Прежние отчёты №17–19.1 сохранены. Commit/push/deploy и удалённые операции не выполнялись. Docker integration и №20 не начаты.
