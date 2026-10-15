# Sandbox Evidence Ledger

14 октября 2026. Задача №15, ветка `feature/roadmap-react`.

Добавлен неизменяемый журнал проверок, операций окружения, отправленных ответов и решений наставников. Полнота выводится из исходной точки учёта, событий и сверки с существующими фактами, отдельно для проверок, reset и ответов. Для неизвестной истории агрегаты возвращают `null` и причины, а не нули.

**Повышенные автоматические награды не включены.** Каталог achievements, evaluators, Trophy Room, Roadmap, TraineeDiary и правила положительного технического зачёта не изменены. Бронза по `SandboxProgramCompletion`, технические milestones и существующие уведомления продолжают использовать прежние источники. Старые completion snapshots не переписывались. Массового восстановления истории нет.

Все проверки выполнялись на временных локальных БД. Рабочие БД не подключались, production миграции не применялись. Commit, push, merge и деплой не выполнялись. SHA256 754 существовавших файлов зафиксированы до работы: изменены только перечисленные ниже 13 существующих файлов; остальные результаты задач 7–14 сохранены.

## 1. Модели, файлы и миграции

Модели определены в [sandbox/ledger_models.py](sandbox/ledger_models.py) и импортированы из `sandbox.models` для штатной регистрации Django.

| Модель | Назначение |
|---|---|
| `SandboxLedgerBoundary` | Единственная запись начала учёта: timestamp, версия 1, максимальный ID существовавшего пользователя на момент миграции |
| `SandboxProgramManifest` | Immutable user + program_key, версия требований, источник, frozen JSON состава и SHA256 digest; unique(user_id, program_key) |
| `SandboxAttemptCoverage` | Unique attempt_id, снимок user/task/attempt_number, версия журнала, origin, исходные checks/resets и ссылка на manifest |
| `SandboxEvidenceGap` | Append-only причина недостаточности источника: неподдерживаемая запись, старый job, отсутствие submission и т. п. |
| `TechnicalCheckExecution` | Unique run UUID, ownership, ordinal, requested_at, checker_kind, reference digest и источник |
| `TechnicalCheckExecutionEvent` | Неизменяемые started/finished/duplicate, время, result, failure_class, reason, nullable checker_started/exit_code/CheckRun ID; unique(execution, phase) |
| `SandboxEnvironmentEvent` | Операция UUID, ownership, kind start/reset/cleanup, requested/started/finished/duplicate, инициатор, origin, timestamps, outcome/reason; unique(operation_id, phase) |
| `SandboxAnswerSubmission` | Unique operation UUID, ownership, ordinal, submitted_at, исходные client_answer/trainee_report, digest, submitted state |
| `SandboxAnswerReviewEvent` | Версия submission, actor ID, reviewed_at, decision/comment, unique operation UUID, decision/correction и supersedes |

Девять таблиц позволяют не обновлять одну «аудитную» строку по мере исполнения: request и lifecycle facts добавляются отдельно. На execution/operation сохраняется одна отметка duplicate: она доказывает наличие повторной доставки, но не является счётчиком всех повторов.

Идентичность пользователя, задачи, попытки и CheckRun хранится числовыми снимками, без CASCADE из исходных таблиц. Удаление Task/TaskAttempt/CheckRun не уничтожает журнал. Внутренние связи ledger защищены PROTECT. Если детали исчезли, provider сообщает unknown, сохраняя факты журнала.

[0032_evidence_ledger.py](sandbox/migrations/0032_evidence_ledger.py) создаёт таблицы, индексы и unique constraints. [0033_ledger_guards.py](sandbox/migrations/0033_ledger_guards.py) создаёт только boundary и PostgreSQL guards; старые attempts, executions, submissions, reviews и manifests не генерируются.

ORM запрещает UPDATE/DELETE/bulk mutations и повторный save. Новый instance с явным существующим PK использует force_insert, поэтому не заменяет старый факт. PostgreSQL triggers запрещают UPDATE/DELETE всех девяти таблиц, включая прямой SQL. Привилегированные TRUNCATE, отключение triggers и восстановление backup остаются административными операциями, не обычным способом исправления истории.

PostgreSQL trigger дополнительно сохраняет gap при изменении защищённых полей TaskAttempt вне штатного writer. Доверенная запись использует transaction-local `sandbox.ledger_writer`; значение восстанавливается после операции. Это внутренний контракт серверных writers, а не защита от администратора БД, способного установить GUC самостоятельно. SQLite обеспечивает ORM guards и ORM gap markers; прямой SQL там не контролируется.

Новые сервисы: [ledger.py](sandbox/services/ledger.py), [ledger_execution.py](sandbox/services/ledger_execution.py), [ledger_evidence.py](sandbox/services/ledger_evidence.py). Новая команда: [audit_sandbox_ledger.py](sandbox/management/commands/audit_sandbox_ledger.py). Новые тесты: `test_ledger.py`, `test_ledger_concurrency.py`, `test_ledger_migration.py`. Примеры находятся в `docs/sandbox-ledger/examples/`.

Из существовавших файлов изменены только:

| Файлы | Изменение |
|---|---|
| `sandbox/models.py` | Creation coverage, frozen manifest до INSERT попытки, контроль неподдерживаемых обновлений |
| `sandbox/admin.py` | Read-only просмотр ledger; существующие действия над TaskAttempt отмечают gap при изменении защищённых фактов |
| `sandbox/services/checks.py` | Request/result lifecycle, idempotency, атомарная запись CheckRun + projection + ledger |
| `sandbox/services/environments.py` | Request/lifecycle, идемпотентность и атомарный successful reset + restart_count |
| `sandbox/services/docker_service.py` | Пометка подтверждённой ошибки до exec; команды checker и существующий timeout output сохранены |
| `sandbox/tasks.py` | Необязательные стабильные run_id/operation_id в Celery аргументах |
| `sandbox/views.py` | Атомарная отправка и review конкретной версии, operation IDs и проверка stale submission |
| `sandbox/management/commands/detect_stuck_attempts.py` | Терминальное unknown и запрет позднему worker перезаписать закрытую операцию |
| `sandbox/management/commands/cleanup_task_containers.py` | Maintenance cleanup lifecycle, закрытие pending операций и защита позднего успеха |
| `templates/sandbox/task_detail.html` | Только hidden operation_id и submission_id; визуальный интерфейс сохранён |
| `sandbox/tests/test_check_service.py`, `test_environment_service.py`, `test_task_actions.py` | Ожидания post-commit dispatch и стабильного ID вместо broker receipt |

`sandbox/services/completions.py` уже имел незакоммиченные изменения предыдущей задачи; его хеш совпадает с состоянием на начало задачи №15.

## 2. Реальные источники событий

| Источник | Что фиксируется |
|---|---|
| `TaskAttempt.save()` при создании, включая rerun/get_current_attempt | Pristine creation либо imported_state; практика остаётся attempt_number > 1 |
| `try_mark_attempt_check_running()` / `mark_attempt_check_running()` | Request + ordinal до dispatch, вместе с attempts_count/RUNNING |
| `run_attempt_check()` и Celery/background wrappers | Однократный admission, finished result, CheckRun ID, duplicate, background/unknown ошибки |
| `try_mark_environment_restarting()`, start/reset services и wrappers | Инициатор/origin, request, admission, outcome; успешный reset вместе со счётчиком |
| `check_task()` | Только действительная отправка технически зачтённого credit answer; черновики отдельно |
| `save_mentor_feedback()` | Решение для текущей immutable версии, либо gap для legacy без версии |
| Watchdog checks/environment | Закрытие pending операций с reason watchdog, без выдуманного результата checker |
| Cleanup management command | Maintenance cleanup до физических действий; interruption pending execution и финальный outcome |
| Admin/сторонний ORM writer | Gap при изменении защищённых фактов; не создаёт фиктивную историческую отправку или решение |

Журнал технических проверок и окружений работает также для practice и очередей вне L1. В программу будущих наград включаются только L1 credit attempts исходного frozen состава. Practice ответы не становятся обязательными клиентскими submissions.

## 3. Жизненный цикл технической проверки

1. Под атомарной защитой текущей попытки регистрируются UUID и монотонный ordinal, увеличивается прежний attempts_count и сохраняется RUNNING.
2. Dispatch выполняется после commit. Durable request уже существует, даже если брокер не принял job. Helper возвращает стабильный run_id, не AsyncResult.
3. Worker проверяет ownership и допускается к исполнению один раз. Повторная доставка того же ID не запускает checker заново, не увеличивает счётчик и не создаёт второй CheckRun.
4. Docker выполняется вне долгой DB-транзакции. Started означает admission worker; `checker_started` определяется отдельно по фактам результата.
5. В одной atomic сохраняются прежние CheckRun/projection/technical_passed_at, finished event и существующие completion/achievement source hooks. Только прежний положительный сервис даёт технический зачёт.
6. Перед записью результата проверяется, что execution не закрыт watchdog/cleanup. Поздний физический успех после закрытия не создаёт новый технический факт.

| Наблюдение | Ledger result / classification |
|---|---|
| Реальный exit 0 | passed, checker_started=true |
| Exit 1 — объявленный отрицательный результат checker | failed / technical, checker_started=true; прежний CheckRun FAILED сохраняется |
| Другие неизвестные nonzero codes, например PHP fatal 255 | unknown / checker_exit_unclassified; прежний CheckRun FAILED сохраняется, причина не объявляется ошибкой стажёра |
| Exit 124 | unknown / timeout, checker_started=true; прежний timeout остаётся FAILED в текущем Sandbox |
| Exit 137 | unknown / timeout, факт старта checker не подтверждён |
| Exit 125/126/127 | unknown / infrastructure; одного кода недостаточно доказать, что checker не запускался |
| Exception при Docker lookup/config до exec_run | unknown / infrastructure, checker_started=false: подтверждённый prelaunch failure |
| Exception при/после exec, background failure, watchdog | unknown; результат не восстанавливается из отсутствующего exit code |
| Отсутствующий exit code | ERROR в projection, unknown / exit_code_missing, без фиктивного CheckRun |

До первой действительной проверки подтверждённый prelaunch infrastructure failure не является технической ошибкой стажёра. Первый check определяется по реальному `checker_started=true`, в request ordinal порядке, только при полной достоверной истории. Timeout и неизвестный исход блокируют достоверное platinum eligibility до отдельного разбора.

Если процесс погиб после Docker execution до commit, остаётся pending/unknown request. Повтор того же key не запускает неопределённую операцию снова. Watchdog закрывает её как unknown. Падение сохранения после физического успеха откатывает CheckRun/credit/ledger result; background handler сохраняет unknown, без дополнительного технического зачёта.

`checker_kind` различает обычный task checker и серверный PHP checker WordPress. SHA256 фиксирует **эталонный файл репозитория** на момент регистрации, а не аттестует содержимое запущенного контейнера. Существующая доверенная модель checker сохранена. Для включения высоких наград необходимо принять эту границу доверия либо добавить runtime/image evidence; совпадение digest само по себе не доказывает неизменность checker внутри контейнера.

Старые Celery сообщения без run_id поддерживаются, но получают legacy_delivery/gap: их нельзя выдать за полный процесс с достоверным первоначальным ключом. Сигнатуры новых tasks принимают IDs необязательно.

## 4. Окружение и успешные reset

Для future achievements reset — **успешно сохранённое пересоздание окружения credit attempt по инициативе его владельца**. Start, check, practice reset, maintenance repair, cleanup и duplicate не увеличивают award-facing counter.

HTTP writer передаёт origin=trainee и actor=owner; maintenance допускает staff либо server actor=NULL. Внешний browser не выбирает origin. Прямой сервис без доказанного origin получает unknown. Нельзя назвать повторный trainee start reset незаметно: для существующего окружения требуется reset path.

Request записывается до dispatch/физического создания. Admission сериализован по попытке, не допускает двух pending операций. Перед исполнением worker обновляет попытку из БД. Success event и прежний restart_count коммитятся атомарно после создания/готовности новых контейнеров. Duplicate одного operation_id не пересоздаёт окружение и не увеличивает счётчик повторно.

Прежний `restart_count` по-прежнему учитывает все успешно сохранённые resets данной попытки, включая maintenance/practice. Evidence отдельно сверяет этот агрегат со всеми successful reset events, а для будущей награды считает только trainee + attempt_number=1. Ошибка создания не увеличивает счётчик; неизвестный фактический исход или origin даёт unknown вместо льготного нуля.

Cleanup отмечается самостоятельным kind=cleanup/origin=maintenance. Старые фоновые jobs без registered request сохраняют прежнюю ERROR/FAILED обработку при отсутствии новой операции, но получают gap. Поздние ошибки старого job не перезаписывают успешную новую операцию.

## 5. Версии отправленных ответов

Submission создаётся только при действительной отправке ответа наставнику: актуальная credit attempt, реальное техническое доказательство, необходимость manual review и допустимое состояние. Сохраняются исходные POST строки до нормализации, ordinal, UUID операции и digest. Существующие TaskAttempt.client_answer/trainee_report и AIReview продолжают получать прежний нормализованный текст.

Сохранение черновика не создаёт submission. Practice не создаёт обязательного review answer. Проверка/сохранение черновика и финальная отправка используют короткие locked транзакции с повторной проверкой текущего состояния; сбой финальной отправки не удаляет уже сохранённый допустимый черновик.

Submission + переход ON_REVIEW + существующая AIReview создаются атомарно. AIReview остаётся optional и не используется вместо журнала. Один operation_id не создаёт две версии; повтор старой отправки после возврата не отправляет новый текст и не возвращает projection к старой версии. Новый действительный исправленный ответ получает новый ordinal и ключ операции.

## 6. Решения и корректировки наставника

HTTP и сервис проверяют staff, ownership, актуальную отправленную версию и соответствие текущего текста её снимку. Hidden submission_id позволяет отвергнуть stale форму после новой отправки. Нельзя одобрить изменённый, ещё не отправленный черновик как старую версию. Неверная/чужая версия не меняет projection.

Review + текущие mentor fields + существующая AIReview связь сохраняются в одной транзакции. Первое решение — decision. Изменение решения или комментария — correction, с supersedes на предыдущее событие этой версии. Повтор того же решения и комментария не создаёт событие; один operation UUID не воспроизводит старое решение поверх более новой correction.

Один **последний действительный needs_revision для конкретной submission** даёт один возврат. Правка комментария сохраняет один возврат; исправление ошибочного needs_revision на approved сохраняет историю, но исключает отменённый возврат. Два needs_revision на двух разных отправленных версиях дают два возврата. После новой версии нельзя переписать решение старой версии через текущую форму.

Staff authorization и идентичность проверяются также при обычном INSERT модели ReviewEvent. Сохранённый actor ID не исчезает при удалении аккаунта; последующее изменение staff flag не меняет факт авторизации в момент записи.

Legacy решение без зарегистрированной submission продолжает работать в старом Sandbox, но записывает review gap. Текущие поля и optional AIReview не превращаются задним числом в «первую отправку».

## 7. Frozen требования

Manifest v1 создаётся перед INSERT первой новой L1 attempt под user/queue/task locks. Он фиксирует программу `l1`, версии schema/requirements, активный обязательный состав, стабильные task IDs/slug/order, requires_review, criteria_version и reference digest. Практика не добавляет отдельное обязательное задание.

Обычный admin toggle manual review, деактивация и добавление Task не меняют manifest. Для завершённой исторической программы новый legacy manifest может брать только состав существующего completion: отсутствующие требования ответов/версии checker остаются NULL. Старый `SandboxProgramCompletion` не изменяется.

Read provider сверяет manifest digest/версию и состав с completion. Если новый текущий каталог дал completion другого состава, сообщается composition_mismatch: прежний completion сохраняет своё техническое значение для бронзы, но не подменяет frozen набор для повышений. Замена удалённой credit attempt новой строкой выявляется по original attempt IDs completion. Отсутствующие Task/Attempt/CheckRun details дают unknown.

## 8. Coverage и legacy

Нет массового complete=True и нет одиночного mutable «история полная». Полнота получается из:

- boundary/version и immutable coverage, созданной вместе с pristine новой попыткой;
- исходных нулевых счётчиков и отсутствия импортированного результата/старта/ответа/решения/контейнера;
- непрерывных request ordinals и завершённых lifecycle events;
- совпадения ownership, CheckRun результатов и текущих counters;
- отсутствия gaps, неизвестного исхода и противоречий submitted/review projection;
- доказанного frozen начала программы и полного набора required credit attempts.

Проверки, reset и ответы имеют отдельные confidence statuses. Например, неизвестный checker не стирает достоверное число сохранённых reset, однако общий perfect-run результат остаётся unknown. `first_check`, successful_resets, valid_returns и first-answer flags выдаются как trusted агрегаты только при полной соответствующей истории; observed-поля — диагностика, не замена trusted значений.

Существующие attempts получают legacy_observed только при новом действительном событии, либо остаются вообще без coverage. Новая строка с уже заполненными counts/result/text/timestamps получает imported_state. Bulk/import без штатного creation hook не получает creation coverage. Последующее включение журнала не делает прошлое полным.

Manifest source=from_start допускается для аккаунта, созданного после boundary и выше максимального user ID при активации. Старый аккаунт без сохранившихся attempts получает existing_account, а не доказанный новый старт: отсутствие строк не доказывает отсутствие удалённого прошлого. Новая pristine попытка такого аккаунта может иметь полную **собственную** историю, но программа остаётся unknown. Для этого случая следующей задаче понадобится явно доверенный enrollment/start policy; автоматическое объявление всей старой программы новой не реализовано.

Неподдерживаемые ORM/admin/SQL исправления защищённых полей помечают coverage gap. Журнал не ремонтируется автоматически по current counters. Raw SQL защиты и конкурентная корректность проверены на PostgreSQL; SQLite не даёт эквивалентных row locks.

## 9. Read-only evidence service

[ledger_evidence.py](sandbox/services/ledger_evidence.py) предоставляет `attempt_evidence(attempt_id)` и `program_evidence(user_id, program_key='l1')`. Сервис выполняет только SELECT; не вызывает get_current_attempt, restoration, evaluator, grant или resync.

DTO содержит manifest/время включения, completion ID, task/attempt IDs, coverage + reasons + отдельные sources, технические request ordinals/results, CheckRun IDs, trusted/observed reset counts, submission IDs/digests/dаты, review IDs/эффективные решения, valid return count и первые distinct required answers. **Raw ответы, отчёты, mentor comments, Docker output и контейнерные секреты в DTO отсутствуют.** В AchievementEvent они не копируются. Публичных новых HTTP endpoints нет.

Management command использует те же SELECT-only providers:

```sh
.venv/bin/python manage.py audit_sandbox_ledger --attempt-id 123
.venv/bin/python manage.py audit_sandbox_ledger --user-id 123
```

Команда доступна серверному оператору с доступом к manage.py; это не пользовательский endpoint. Django admin разрешает только staff read-only просмотр ledger, включая защищённые raw submissions. Существующие пользовательские маршруты сохраняют прежние owner/staff permissions.

Синтетические примеры созданы на отдельной временной SQLite БД, через mock Docker и штатные services; это не production evidence:

- [Новая попытка](docs/sandbox-ledger/examples/new-attempt.json): полная история, первый реальный check passed, первая submission approved, trusted resets=0/returns=0.
- [Новая программа](docs/sandbox-ledger/examples/new-program.json): frozen requirements, сохранённый completion, полные source statuses.
- [Историческая попытка](docs/sandbox-ledger/examples/legacy-attempt.json): сохранившиеся старые counters, нет доказанного начала ledger; trusted counts/first-check=NULL, unknown reasons. Пустой массив observed событий не доказывает отсутствие старых событий.

## 10. Проверки

Новых тестов ledger — 38: 31 функциональный, 6 PostgreSQL concurrency/audit, 1 upgrade migration. PostgreSQL проверяет обычный и raw SQL audit, competing first requests, duplicate checker/reset, submission/review races и watchdog против позднего физического успеха.

| Проверка | Результат |
|---|---|
| Full Django suite, окончательный SQLite | **907 тестов за 270,947 с, OK**; 16 PostgreSQL-specific skips |
| PostgreSQL: Sandbox + achievements + Roadmap + React integration | **556 тестов, OK**, без пропусков |
| PostgreSQL после уточнения unknown exit codes: весь новый ledger suite | **38 тестов, OK**, включая 6 concurrency/audit и upgrade migration |
| Fresh SQLite / PostgreSQL migrate | OK, новые 0032/0033 применены только на временных БД |
| System checks SQLite / PostgreSQL | 0 ошибок |
| makemigrations --check --dry-run SQLite / PostgreSQL | No changes detected |
| migrate --check SQLite / PostgreSQL | OK |
| Frontend typecheck + Vite build | OK; существующие assets пересобраны, React source не менялся |
| Frontend tests / Diary JS regression | 60 / 10 тестов, OK |
| Read-only evidence, защищённые ORM/SQL записи, исходные хеши, git diff --check | OK |

После широкого PostgreSQL прогона уточнена только обработка незнакомых nonzero codes; весь новый PostgreSQL ledger suite и окончательный полный Django suite проверяют окончательную классификацию. Прогоны использовали PostgreSQL 16.9, UTF8, отдельный Unix-сокет `/tmp/sandbox15-pg/socket`, без TCP и подключений к рабочей БД. После проверок временный кластер остановлен; его данные и временные SQLite БД удалены.

Migration test переносит реально созданную историческую строку 0031 → 0033, проверяет неизменность исходных полей и отсутствие выдуманных coverage/manifests/events. SELECT-only проверяется через CaptureQueriesContext; DTO проверяется на отсутствие raw текстов. Регрессии покрывают completion, practice, text revision без rerun, бронзу, Roadmap, achievement events/notifications и права.

Для самостоятельного запуска выберите **новую временную** БД и временный STATIC_ROOT, поскольку существующие Django integration tests требуют собранных frontend assets:

```sh
npm run build --prefix frontend
cat > /tmp/sandbox_ledger_local_settings.py <<'PY'
from config.settings import *
STATIC_ROOT = '/tmp/sandbox-ledger-local-static'
PY
export PYTHONPATH=/tmp DEBUG=True DB_ENGINE=django.db.backends.sqlite3
export DB_NAME=/tmp/sandbox-ledger-local.sqlite3 SENTRY_DSN=''
.venv/bin/python manage.py collectstatic --noinput --settings=sandbox_ledger_local_settings
.venv/bin/python manage.py migrate --noinput --settings=sandbox_ledger_local_settings
.venv/bin/python manage.py check --settings=sandbox_ledger_local_settings
.venv/bin/python manage.py makemigrations --check --dry-run --settings=sandbox_ledger_local_settings
.venv/bin/python manage.py migrate --check --settings=sandbox_ledger_local_settings
.venv/bin/python manage.py test --noinput --settings=sandbox_ledger_local_settings
```

PostgreSQL-specific tests требуют отдельную локальную PostgreSQL БД и права создать её test database. Эти команды не предназначены для production/backfill.

## 11. Производительность и эксплуатация

Creation hook добавляет lookup boundary и короткие user/queue/task locks для однократного freeze. Обычные saves добавляют проверку identity/unsupported change; trusted PostgreSQL writers выполняют дополнительные set_config запросы. Результаты, counters и lifecycle коммитятся короткими транзакциями; Docker и ожидание readiness находятся вне них.

Evidence provider использует prefetch lifecycle/reviews, но выполняет отдельные запросы по required attempts и CheckRuns: это диагностический provider с затратами, растущими с размером программы. Он не добавлен к Trophy Room polling или существующим progress GET. Перед массовым evaluator/resync понадобятся измерение query count/latency, пакетная загрузка и индексы согласно реальной выборке. CheckRun сверка не загружает большие output fields.

Ordinal/identity uniques и indexed attempt IDs ограничивают поиск истории одной попыткой. Raw submission rows растут с количеством настоящих отправок, а не keystrokes. Duplicate receipts ограничены одной phase-marker на операцию.

Post-commit dispatch оставляет durable requests при падении wake/брокера, но ledger не является новым механизмом автоматического повторного исполнения неопределённого Docker job. Watchdog/оператор должны закрывать зависшие процессы; повторное физическое выполнение тем же ключом запрещено. Разрешение спорного unknown и безопасный retry требуют отдельной аудируемой политики.

При будущей выкладке сначала применить schema/guards, затем совместимые web/workers. Старые queue messages без ключей сохраняют совместимость и дают unknown coverage. Старые workers, продолжившие писать вне ledger, создадут gaps. Scheduler/инфраструктура/deployment в задаче не менялись.

## 12. Retention и безопасность raw данных

Raw ответы и отчёты нужны для доказательства конкретной отправленной версии; сейчас это защищённые TextField snapshots, без новой криптографической системы. Mentor comment хранится только в private review ledger. Lifecycle payloads содержат IDs и reason codes, без Docker output, exception текста, паролей, container environment или terminal URL.

Предлагаемая политика для согласования: raw snapshots хранить в течение адаптации и 90 дней после её завершения, дольше — только при документированном споре/обязательстве; обезличенные IDs/digests/decisions/coverage — по отдельно утверждённому сроку аудита. Это предложение, не действующий purge. Необходимы минимальный staff доступ, защищённые backup и проверка доступа к выгрузкам.

Append-only guards сейчас намеренно не разрешают удалить или заменить raw тексты. Будущая retention реализация должна предусмотреть явно согласованную архитектуру архивирования/шифрования и аудируемой очистки либо cryptographic erasure с tombstone/provenance. Нельзя просто удалить submission и продолжить считать её отсутствие «чистым первым ответом». Никакого автоматического удаления, архивации или изменения старых данных в этой задаче нет.

## 13. Подготовка включения высоких наград

Условия следующей задачи зафиксированы по задаче №15:

| Правило | Необходимое доказательство |
|---|---|
| Sandbox silver | Технически завершён весь frozen required состав; суммарно ≤2 successful trainee credit resets; reset source full |
| Sandbox gold | Тот же технический состав; все required client answers приняты; ≤2 resets и ≤2 действительных needs_revision; полная история |
| Sandbox platinum | Весь состав завершён; первая действительная техническая проверка каждого task passed; каждый required answer принят с первой submission; **0 trainee resets**; полная история всех источников |
| «Без замечаний» | Первые пять **разных обязательных** client answers, по фактическим submitted_at и устойчивому submission_id, приняты с первой submission |

Поздняя успешная resubmission не заменяет неудачный ранний ответ в first five. Ordinary infrastructure failure до исполнения checker не штрафует автоматически; неизвестный старт/timeout/result не превращается в платину. Требования берутся из frozen manifest, а не текущего requires_manual_review или Task.order. Practice исключается. Independent conditions оцениваются независимо, без искусственных выдач промежуточных уровней.

Provider подготовлен как источник доказательств, но **eligibility высоких наград не вычисляется и automatic flags не изменены**. До включения необходимо отдельно утвердить: checker trust/reference vs runtime evidence, явную новую enrollment policy для старых аккаунтов, аудируемое разрешение unknown/corrections, применимость программы, source hooks для awards и проверку delayed events/reconciliation. При изменении схемы требований нужна новая versioned manifest policy, а не редактирование старых снимков.

Исторические counters, последнее approved, attempts_count=1 и пустой журнал не подходят для legacy platinum. Существующие данные остаются unknown там, где начало или полнота не доказаны. Следующее действие — отдельная задача включения повышенных Sandbox evaluators; в этой задаче оно не выполняется.
