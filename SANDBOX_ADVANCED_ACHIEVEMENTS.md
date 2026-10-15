# Sandbox Advanced Achievement Evaluators — задача №16

15 октября 2026. Ветка `feature/roadmap-react`, исходный checkpoint `aac70d92d3f44190b9407b319107e1c530bf51d7`.

## 1. Результат и граница активации

Включены автоматические **silver/gold `sandbox_program`** и фиксированное золото **`sandbox_first_five_clean_answers`**. Bronze и технические milestones сохранены. Выдача, повышение, suppression, история и уведомления используют существующий achievements backend.

**Автоматическая платина не включена.** Её условия оцениваются независимо, но даже идеальный Ledger даёт `unknown: runtime_checker_integrity_unproven`. В `AchievementTier.parameters` platinum по-прежнему `automatic=False`; автоматический grant этого уровня отклоняется. Это предусмотренная задачей остановка активации при недостаточном checker trust, а не включённая платина с фиктивной гарантией.

Причина подтверждена исходниками: `sandbox/services/docker_service.py:check_task_container` исполняет `bash /task/check.sh` внутри учебного контейнера; обычные L1 Dockerfile копируют этот файл в образ, а терминал подключает пользователя через `docker exec ... bash`. Корневая файловая система контейнера не read-only, защищённого runtime attestation нет. Repository SHA256 из `checker_identity` не доказывает идентичность исполняемого файла. Для WordPress внешний исходник checker передаётся сервером, но это не доказывает целостность всего runtime и остальных заданий. Новая система attestation не создавалась. Silver/gold сохраняют существующую политику доверия техническому зачёту; они не объявляются доказательством криптографически защищённой проверки.

## 2. Источники и независимые условия

Evaluator читает публичный `program_evidence(user_id, program_key='l1')`. `attempt_evidence(attempt_id)` остаётся публичным SELECT-only интерфейсом. Никаких попыток, completion или исторических событий при чтении не создаётся. Текущие `attempts_count`, `restart_count`, `status=passed` и последний mentor flag не заменяют историю.

| Уровень | Условия |
|---|---|
| Bronze | Существующий валидный `SandboxProgramCompletion`, прежняя политика |
| Silver | Все frozen credit tasks технически завершены с зарегистрированными успешными Ledger executions; reset coverage complete; ≤2 успешных reset с origin=trainee и actor=owner |
| Gold | Техническое завершение с зарегистрированным успешным Ledger execution; reset и required-answer coverage complete; ≤2 trainee resets; ≤2 эффективных возвратов по обязательным ответам; последние версии всех frozen required answers approved |
| Platinum, оценка без активации | Полные checks/resets/required answers; все первые реальные checks passed; все required answers approved с единственной первой submission; 0 trainee resets; дополнительно нерешённый runtime trust gate |
| «Без замечаний» | Первые пять разных frozen required answers по submitted_at + submission ID имеют approved на первой submission при полном answer coverage |

Условия независимы: неизвестные ответы не уничтожают silver, а неизвестный checker не мешает gold при доказанной технической завершённости и полной истории необходимых reset/ответов. Каталог текущих Task не подменяет frozen manifest. Изменение обязательности review после старта не меняет награду: новые необязательные для исходной программы ответы и их возвраты исключены. Practice, initial start, maintenance, cleanup, duplicate receipts и неуспешные инфраструктурные reset не входят в trainee reset count. Provider дополнительно проверяет actor=owner; несоответствие делает reset coverage unknown.

Подтверждённая ошибка до старта checker пропускается при определении первой реальной проверки. Technical failure первой проверки даёт not_met; timeout, неподтверждённый старт, пропавший CheckRun, gaps или смена criteria digest дают unknown. Поздний watchdog не заменяет сохранённый результат: существующие fencing/immutability guards сохранены и проверены прежними concurrency-тестами.

## 3. Unknown, not_met, eligible

`assess()` возвращает отдельные status/reasons для silver, gold, platinum и clean_answers. Evaluator выбирает наивысший разрешённый eligible уровень одним вызовом grant, без выдачи промежуточных уровней. Если advanced evidence неизвестно, остаётся доказанная бронза. Отсутствие сохранённого completion сохраняет прежний общий `not_met` с отдельной advanced-диагностикой в `context.levels`.

- `unknown`: нет trusted начала manifest, incomplete/gap coverage, отсутствующая credit attempt, несовпадение frozen/completion identity, неизвестный порядок или версия criteria, будущие/naive timestamps, runtime trust gate.
- `not_met`: техническая программа не завершена, доказанно превышены лимиты, required ответ не отправлен/не принят, менее пяти required/submitted answers, ошибочный ответ среди первых пяти или неудачная первая реальная проверка.
- `eligible`: все необходимые для конкретного уровня условия доказаны. Unknown по другому независимому условию не считается успехом и не стирает доказанный нижний уровень.

«Без замечаний» не выбирает последние пять approved. Шестой ответ не заменяет ошибку в пятом, повторные submissions не становятся разными заданиями. Коррекция ошибочного решения применяется через эффективное решение версии; сырые needs_revision не суммируются. Успешный raw CheckRun без зарегистрированного Ledger execution не даёт advanced eligibility; исчезнувшие или изменённые CheckRun details также дают unknown. Будущие события не используются для ранней выдачи. В доказательстве сохраняются только manifest IDs/digest, task/attempt IDs, ссылки и digest submissions, IDs эффективной review chain и результаты checks; raw тексты, комментарии и Docker output не копируются.

## 4. Review events и надёжность

`ledger.review_answer` создаёт `AchievementSourceEvent(provider='sandbox_review', external_id=review.pk)` в той же транзакции, что immutable review. В штатном view внешняя транзакция включает и обновление projection. Post-commit wake прежний; при сбое durable событие остаётся для существующего drain-command/retry.

Событие создаётся для L1 credit attempt при действительном первом решении или изменении решения. Повтор с тем же operation ID или тем же решением/комментарием не создаёт нового события. Редактирование только комментария сохраняет Ledger correction, но не создаёт нового achievement source. Staff авторизуется прежним сервисом. User lock сериализует решение с автоматической выдачей; общая блокировка grants остаётся прежней.

Technical success и program completion также запускают advanced reevaluation. Events не содержат готовой eligibility: delayed, retry и out-of-order delivery перечитывают актуальное доказательство. В пределах одной обработки provider читается один раз для обеих advanced families; cache не глобальный. Повтор processed event не запускает evaluator повторно.

## 5. Corrections, история и уведомления

При утрате основания уже выданного автоматического уровня review source или explicit reconciliation вызывает прежний `flag_disputed`, добавляет audit event и оставляет tier на месте. Manual grant не объявляется ошибочным автоматически. Нет автоматического downgrade или revoke; дальнейшее решение принимает staff. Revoke сохраняет прежний auto-grant suppression.

Один `UserAchievement` сохраняет всю историю. Проверены direct gold, bronze→silver→gold, bronze→gold, silver→gold, повторный source, параллельные event/apply и suppression. На фактический grant/upgrade создаётся ровно одно существующее уведомление. No-op, duplicate, dispute и suppressed не создают уведомление о повышении.

Сценарии gold→platinum, bronze→platinum и direct platinum **преднамеренно недоступны автоматически**: существующие общие grant/concurrency-тесты проверяют механизм повышения на других разрешённых семействах, а Sandbox-тесты проверяют запрет автоматической платины. Нельзя выдавать тестовую платину за включённую production-функцию.

## 6. Применимость и старые аккаунты

Сохранена v1 применимость NEW_HIRE, только L1 credit program. INTERNAL_TRANSFER остаётся not_applicable, включая добровольный Sandbox. Номера станций Roadmap не используются.

`from_start` и полный trusted manifest/source coverage обязательны для advanced наград. `existing_account`, imported_state, legacy completion и старые attempts без coverage не становятся новой программой из-за нулевых текущих counters или отсутствия сохранившихся attempts. Массовый backfill и enrollment не выполнялись.

Последующая задача для старых аккаунтов: отдельный авторизованный start/enrollment workflow с audit, версией программы и однозначным отделением новой зачётной программы от удалённой/неполной истории. Автоматически включать такой режим здесь нельзя.

## 7. Reconciliation и каталог

Команда `reconcile_achievements` по-прежнему требует явные user IDs, по умолчанию SELECT-only dry-run; запись только с `--apply`. Отчёт дополнен `current_tier`, `suppressed`, `source`, `missing_evidence`, `unknown_reasons` и независимыми `context.levels`, сохраняя rule_version и eligibility. Disputed выводится отдельно; revoked entitlement виден как current_tier=null и suppressed=true.

```sh
# Только на отдельно выбранной оператором БД, не команда автоматического backfill:
python manage.py reconcile_achievements --user-ids 123 --families sandbox_program sandbox_first_five_clean_answers --rule-version 1
# Запись требует отдельного явного добавления --apply.
```

Новая миграция **achievements/0006_sandbox_advanced_activation** зависит от achievements/0005 и sandbox/0033. Она включает automatic только для существующих silver/gold Sandbox и fixed gold, не создаёт user awards/source events. Reverse выключает эти flags без изменения истории/tiers пользователей. Стабильные коды, public UUID и rule_version=1 сохранены: критерии v1 не изменены, активирован ранее описанный контракт через отдельную версионированную migration policy. Новые evidence snapshots маркируются `policy=sandbox-ledger-v1`; старые snapshots и `AchievementEvent.rule_version` не переписываются. Новая версия thresholds/доверия при будущем включении платины потребует отдельной catalog policy.

## 8. Производительность

Замеры выполняются тестом `AdvancedPerformanceTests` на 15 frozen required review tasks с реальными Ledger/CheckRun/submission/review, Docker замокан. Это локальная синтетическая нагрузка, не production benchmark.

До оптимизации на SQLite: provider **168 SELECT / 77,25 мс**, event **227 запросов**, batch двух пользователей/двух families **195 запросов / 98,24 мс**. После пакетной загрузки — **12 SELECT** независимо от числа задач в этом сценарии. Общая валидация single/program DTO сохранена; bulk loading не отключает guards. Query budget ≤12 проверяется тестом. Ответы/отчёты не попадают в DTO, CheckRun output не загружается.

Финальный замер:

| Операция | SQLite | PostgreSQL |
|---|---|---|
| Provider, 15 заданий | 12 SELECT / 12,10 мс | 12 SELECT / 15,72 мс |
| Обработка review source с выдачей | 71 запрос | 71 запрос |
| Повтор processed source | 5 запросов, без INSERT/UPDATE | 5 запросов, без INSERT/UPDATE |
| Dry-run batch, 2 пользователя × 2 families | 39 запросов / 29,17 мс | 39 запросов / 37,45 мс |

 Request-scoped cache разделяет одно доказательство между двумя families при event/dry-run. Apply перечитывает состояние под locks, не использует устаревший batch cache. Повтор processed event ограничивается проверкой inbox и lock; наградных INSERT/UPDATE нет. Полный evaluator не вызывается из GET Trophy Room/Roadmap. При больших пользовательских batch оператор задаёт явные ограниченные наборы IDs; память cache ограничена одним запуском, количество самих исторических событий всё ещё влияет на объём чтения.

## 9. Проверки

Использованы только временные локальные SQLite и PostgreSQL 16 с Unix-сокетом `/tmp/training-task16/socket`, `listen_addresses=''`, без TCP/production. STATIC_ROOT также временный. Временные settings принудительно переопределяют DATABASES на изолированные SQLite/PostgreSQL; Sentry DSN задан пустым через окружение. Production-параметры БД из config не используются. Password hasher ускорен только для синтетических тестовых аккаунтов.

Новые тесты проверяют границы reset/revisions, maintenance/practice/duplicate/failed reset, pending/unknown answers, prelaunch/timeout/first-fail, trust gate, first-five ordering/correction/resubmission, frozen review flags, legacy enrollment, NEW_HIRE/INTERNAL_TRANSFER, atomic review rollback, повтор/задержку events, dispute/revoke/suppression, реальные upgrades/notifications, dry-run/batch, query budget и миграцию с сохранением исторического события. PostgreSQL добавляет реальные параллельные source/apply и delayed correction. Существующие Ledger concurrency/audit tests сохраняют проверки watchdog, raw SQL guards, checker/reset fencing и review races.

Окончательное дерево кода проверено после добавления запрета unregistered raw pass. От checkpoint добавлены 26 тестов; изменены ожидания нескольких прежних тестов.

| Проверка | Результат |
|---|---|
| Full Django suite, SQLite | **933 теста / 46,338 с, OK**, 19 PostgreSQL-specific skips |
| PostgreSQL: achievements + Sandbox + Roadmap + React integration | **582 теста / 52,030 с, OK**, без пропусков, включая все concurrency/audit и новую migration policy |
| Fresh SQLite/PostgreSQL migrate, включая 0006 | OK, только временные БД |
| System checks, SQLite/PostgreSQL | 0 ошибок |
| makemigrations --check --dry-run, SQLite/PostgreSQL | No changes detected |
| migrate --check, SQLite/PostgreSQL | OK |
| Frontend regression / Diary JS | **60 / 10 тестов, OK** |
| TypeScript typecheck / Vite build | OK |
| git diff --check; staging | Чисто; staging пуст |

Новые конкурентные tests сначала выявили ошибку собственного fixture (не указан NEW_HIRE), затем mixed-review fixture выявил неполный mock cleanup. Исправлены тестовые данные/mocks; финальные полные прогоны выше успешны. Финальная проверка кода отдельно закрыла raw CheckRun без Ledger execution. Ни один из этих случаев не исправлялся ослаблением evidence checks.

Логи проверок оставлены в `/tmp/training-task16/`: `complete-sqlite.log`, `complete-postgres.log`, `frontend-tests.log`, `diary-js.log`, `typecheck.log`, `build.log`, `migrate-sqlite.log`, `migrate-postgres.log`. Они не добавлены в репозиторий. Временный PostgreSQL остановлен после проверок, временные SQLite и PostgreSQL данные удалены.

## 10. Изменённые файлы

Новые:

- `achievements/services/evaluators/sandbox_advanced.py` — независимые условия и compact evidence.
- `achievements/migrations/0006_sandbox_advanced_activation.py` — только текущие catalog flags.
- `achievements/tests/test_sandbox_advanced.py`, `test_sandbox_advanced_concurrency.py`, `test_sandbox_advanced_migration.py`.
- `SANDBOX_ADVANCED_ACHIEVEMENTS.md`.

Обновлены:

- `achievements/services/evaluators/sandbox.py`, `evaluators/__init__.py`, `catalog.py` — интеграция и регистрация.
- `achievements/services/events.py`, `grants.py`, `reconciliation.py`, `management/commands/reconcile_achievements.py` — sources, dispute и диагностика.
- `sandbox/services/ledger.py` — минимальный transactional review source hook и user lock.
- `sandbox/services/ledger_evidence.py` — пакетная загрузка при прежнем публичном API, actor/reset validation, исключение nonrequired answers, factual finish/review timestamps.
- `achievements/tests/test_events.py`, `test_grants.py`, `sandbox/tests/test_ledger.py` — ожидания новых разрешённых уровней/providers и сохранение запрета платины.
- `achievements/tests/test_notification_migration.py`, `sandbox/tests/test_ledger_migration.py` — восстановление всех актуальных migration leaves после upgrade tests.

Схема Ledger, его append-only guards и старые миграции не изменены. UI Sandbox, Trophy Room, медальоны, SVG Roadmap, frontend sources и пороги качества/скорости не менялись. 83 локальных PNG сохранены вне Git. `.gitignore` не изменён.

## 11. Безопасное включение и риски

Никаких production операций в этой задаче нет. Будущая выкладка требует совместимого переключения кода и catalog flags: старый evaluator валидирует прежние flags, поэтому нельзя оставлять старые web/workers писать после activation migration.

1. Резервная копия и staging-проверка; временно остановить приём новых записей, остановить/дренировать старые workers и scheduler.
2. Из нового release применить согласованную цепочку schema/guards и catalog activation; проверить migration plan и checks.
3. Запустить совместимые новые web/workers; проверить обычный технический зачёт, mentor review, notifications и повтор доставки на staging.
4. Для выбранных пользователей сначала dry-run; никакого глобального apply/backfill по умолчанию. Drain существующих source events также является записью и требует операционного контроля.
5. При rollback согласованно выключить activation flags обратной миграцией и вернуть совместимый код; существующие награды и история сохраняются, спорные выдачи разбирает staff.

Платина остаётся заблокированной до отдельного решения checker trust/runtime integrity. Старым аккаунтам нужен отдельный enrollment workflow. Исторические gaps не ремонтируются автоматически. Retention raw Ledger snapshots остаётся ограничением задачи №15; новая выгрузка/удаление raw данных здесь не добавлялась. SQLite не заменяет PostgreSQL locks/triggers. Событийная обработка остаётся существующей best-effort wake + durable retry, отдельный внешний worker deployment в задаче не менялся.

Commit, staging, push, merge, PR, деплой, production migration и массовая выдача не выполнялись.
