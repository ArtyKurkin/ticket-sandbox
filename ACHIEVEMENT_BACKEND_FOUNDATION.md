# Achievement Backend Foundation

14 октября 2026. Задача №11, ветка `feature/roadmap-react`.

Реализовано отдельное приложение `achievements`: каталог 11 семейств, шесть моделей, атомарная выдача максимального уровня, неизменяемая история, явный отзыв, durable события источников, evaluators, resync и session API. React Trophy Room и дизайн Roadmap не изменены. Повышенные уровни с недостаточными источниками зарегистрированы, но автоматически не выдаются.

## Файлы

Созданы:

```text
achievements/
  __init__.py
  apps.py
  models.py
  admin.py
  urls.py
  views.py
  migrations/
    __init__.py
    0001_initial.py
    0002_achievementoperation.py
    0003_catalog_v1.py
    0004_audit_guards.py
  services/
    __init__.py
    catalog.py
    grants.py
    events.py
    reconciliation.py
    evaluators/
      __init__.py
      base.py
      training.py
      sandbox.py
      weekly.py
      probation.py
      independent.py
  management/
    __init__.py
    commands/
      __init__.py
      reconcile_achievements.py
      process_achievement_events.py
  tests/
    __init__.py
    base.py
    test_grants.py
    test_evaluators.py
    test_events.py
    test_api.py
    test_concurrency.py
ACHIEVEMENT_BACKEND_FOUNDATION.md
```

Изменены только следующие существующие файлы относительно состояния на начало задачи:

| Файл | Изменение |
|---|---|
| [config/settings.py](config/settings.py) | Регистрация приложения |
| [config/urls.py](config/urls.py) | `/api/achievements/` |
| [roadmap/services/confirmations.py](roadmap/services/confirmations.py) | Durable событие confirmed/revoked внутри существующей atomic |
| [sandbox/services/checks.py](sandbox/services/checks.py) | Событие только успешно сохранённой технической зачётной проверки L1 в её atomic |
| [sandbox/services/completions.py](sandbox/services/completions.py) | Событие при создании completion, включая явное legacy restore |
| [traineediary/models.py](traineediary/models.py) | События подтверждённого перехода и успешного ИС в существующих atomic |
| [traineediary/views/weekly_metrics.py](traineediary/views/weekly_metrics.py) | Сохранение метрики через narrow service: metric + source event в одной atomic |

Начальные хеши существующих файлов сохранены для проверки. Все остальные существовавшие файлы совпали с начальным состоянием, включая React, отчёт аудита, документы и результаты задач 7–9. Повторная сборка существующего frontend выполнена для имеющихся Django integration tests; исходники не менялись. Commit, push, merge и деплой не выполнялись.

## Модели и миграции

| Модель | Назначение |
|---|---|
| `AchievementDefinition` | Stable code, opaque UUID, metadata, secret, tiered/fixed, active, applicability, evaluator key, rule version, whitelist art key |
| `AchievementTier` | Один общий каталог уровней: definition/code/rank/rarity/criterion/parameters/version; unique definition+code и definition+rank |
| `UserAchievement` | Unique user+definition; nullable active tier, реальные даты выдачи/повышения, revision, auto suppression, evidence_disputed |
| `AchievementEvent` | Append-only grant/upgrade/revoke/evidence_disputed; реальные from/to, actor, occurred/recorded timestamps, source, rule, proof snapshot/digest, reason и unique idempotency key |
| `AchievementSourceEvent` | Durable уникальный provider+external ID, immutable payload/context/user/schema, availability, pending/error/processed, attempts/error/result |
| `AchievementOperation` | Неизменяемая квитанция grant/revoke, включая no-op и suppressed; один request digest на operation key |
| `Rarity` | Это перечисление, не таблица: bronze/silver/gold/platinum |

Итого **шесть таблиц**; `Rarity` — enum. Квитанция необходима, чтобы ранее отклонённая как no-op ручная выдача после отзыва не превратилась при повторе старого HTTP-запроса в новую выдачу.

`0001` создаёт основные таблицы/constraints/indexes; `0002` — квитанции; `0003` — замороженный каталог v1 без пользовательских наград; `0004` — PostgreSQL triggers. События и квитанции защищены от UPDATE/DELETE на уровне PostgreSQL, источники — от удаления и изменения фактов. Processing fields источника остаются изменяемыми. ORM guards блокируют update/delete/bulk mutation; insert-only save использует force_insert, включая защиту от нового instance с существующим PK.

SQLite использует ORM guards, без SQL triggers. PostgreSQL TRUNCATE остаётся доступным привилегированному обслуживанию и Django test flush. Каталог и projection не являются append-only журналами. Admin предоставляет read-only просмотр; управление выдачей проходит через сервис/API. FK на пользователей, определения, уровни и журнал защищены PROTECT.

## Каталог и автоматизация

| Код | Уровни и условие | Автоматически сейчас |
|---|---|---|
| `training_program` | bronze confirmed; silver ≤11 учебных рабочих дней и >90%; gold ≤6 и >95%; platinum ≤6 и ровно 100% | Только bronze, последнее действующее подтверждение Roadmap |
| `sandbox_program` | bronze frozen completion; silver ≤2 successful resets; gold все ответы approved, ≤2 resets/≤2 revisions; platinum first check + first submission + **0 resets** | Только bronze из сохранённого `SandboxProgramCompletion` |
| `review_quality` | bronze ≥80; silver ≥90; gold >95 | Все три, по лучшей достоверной законченной неделе WITH_REVIEW |
| `independent_speed` | bronze ≥5; silver ≥7; gold ≥9; platinum >10 т/ч | Все четыре, по лучшей достоверной законченной неделе NO_REVIEW, без качества |
| `probation_new_hire` | bronze >60; silver 46–60; gold 31–45; platinum ≤30 календарных дней | Все четыре, только подтверждённый успешный NEW_HIRE |
| `sandbox_first_success` | Fixed bronze, первый технический credit success L1 | Да |
| `sandbox_five_successes` | Fixed silver, пять distinct технических credit tasks L1 | Да |
| `sandbox_first_five_clean_answers` | Fixed gold, первые пять различных ответов с первой отправки | Нет: нужен immutable журнал submissions/reviews с coverage |
| `review_quality_streak` | Fixed gold, три полные последовательные недели ≥90% WITH_REVIEW | Нет: нужны finalized недели и coverage |
| `independent_engineer` | Fixed silver, staff-confirmed OPTIONAL_REVIEW → NO_REVIEW | Да; пропуск промежуточного этапа не подходит |
| `clean_week` | Отдельная secret fixed platinum, полная проверенная неделя WITH_REVIEW с 100% | Нет: нужны финальность и подтверждённое фактическое покрытие |

Применимость v1: обучение, основная программа Sandbox, Sandbox extras и ИС — NEW_HIRE. Качество, скорость, independent engineer и будущие weekly extras применимы обоим entry types. Добровольный Sandbox внутреннего сотрудника пока не даёт автоматических наград: его применимость требует отдельной политики. `not_required` не становится earned. Без адаптации NEW_HIRE-only evaluator возвращает unknown; INTERNAL_TRANSFER — not_applicable.

Manual grant staff может осознанно выдать зарегистрированный уровень, включая отключённый автоматический, с явным source=manual и причиной. Это не включает автоматическое правило и не создаёт фиктивный технический или учебный результат.

## Доказательства и календарь

Evaluators только читают. Возвращают eligible / not_met / not_applicable / unknown; eligible содержит максимальный подходящий tier, context, proof IDs/values, occurred_at и rule_version; unknown — причину и необходимые доказательства. Независимые условия уровней не требуют предварительного получения низших уровней.

Обучение: действующее подтверждение конкретного journey, author/time проверены. Award создаётся автоматически, но evidence содержит `source=manual`: это решение наставника, не результат Teachbase. Ни score, ни точный course start не выдумываются. Для будущего adapter каталог фиксирует учебные рабочие дни: Пн–Пт, без выходных; исключение первого неполного дня только по подтверждённому факту, без автоматического исключения праздников/отсутствий. Пока timed/scored evaluators отключены.

Sandbox: только L1, attempt_number=1, техническое доказательство из общего сервиса. `status=passed`, mentor approved, attempts_count=1 или restart_count=0 не заменяют доказательства. Practice не считается; is_current не используется. Frozen completion сохраняет результат при удалении/изменении каталога. Для milestones объединяются distinct positive proofs живых credit rows и frozen snapshot, выбираются первые 1/5 по времени успеха. Существующие связанные attempts проверяются на owner/task/credit identity; отсутствие удалённых деталей не отменяет сохранённый completion. Контекст — существующая user+L1 программа; новые enrollment/истории попыток не создавались.

Недельные метрики: сохранённая week_start_date, непустое соответствующее значение (0 допустим), законченный интервал `[start, start+7 дней)`. Вся история должна быть непрерывной, применимой по scheme/entry, без пропусков/наложений, с одной последней открытой записью, совпадающей с карточкой. Весь период покрывается **одним посещением** нужной группы. UI fallback текущего этапа не используется. Прошлая корректная неделя остаётся доказательством после возврата; разные посещения не складываются в streak. Итоговое fixed_quality_percent не используется, скорость не зависит от качества.

Неделя трактуется как авторитетный введённый агрегат периода по утверждённой в задаче политике. Это не доказательство full working week, финальности или полного объёма выборки. Поэтому 100% дают основное gold качества, но не secret platinum.

ИС: SUCCESS, staff completion author, непротиворечивые реальные даты, финальный DONE и соответствующая история. `day_number=(completed_at-probation_start_date).days+1`; выходные включены, тот же день = 1. TERMINATED и INTERNAL_TRANSFER исключены. Для DateField доказательств occurred_at — полночь соответствующей локальной даты; это календарная точность, не неизвестное время нажатия кнопки. recorded_at/first_granted_at — фактическое время новой выдачи.

## Повышение, отзыв и коррекции

Сервис блокирует **существующего user**, затем definition и projection; отсутствие UserAchievement не оставляет гонку первой вставки. На PostgreSQL user lock — NO KEY UPDATE: он сериализует выдачи и позволяет исходному writer вставить source FK без deadlock с journey lock. Nullable tier join блокируется `of=(self,)`. Unique constraints и квитанции защищают повторное действие; projection, event и receipt коммитятся вместе.

Первое доказательство platinum → один grant NULL→platinum. Bronze→platinum → один upgrade. Тот же/меньший уровень → no-op; новая плохая неделя ничего не понижает. Разные доказательства одного уровня не создают дополнительные выдачи. Повтор operation ID с другими параметрами → conflict.

Политика отзыва v1 — **отзыв активной награды целиком**: отдельный staff revoke с причиной и ссылкой на последнюю выдачу, active tier=NULL, auto_grant_blocked=true. Предыдущие события остаются. Автоматически восстанавливать нижний уровень из истории система не пытается. После отзыва запрещены автоматические выдачи и по прежнему, и по новому proof. Staff может явно повторно выдать уровень новой операцией с причиной; автоматический блок остаётся. Автоматического unblock/regrant по новому независимому proof нет: эта политика требует отдельного решения.

Исправление выдавшей награду метрики или отзыв исходного подтверждения создаёт evidence_disputed и устанавливает соответствующий flag; текущий уровень сохраняется. Resync обнаруживает также изменение/удаление метрики через maintenance-путь, без события writer. Только явный revoke меняет активную награду. Новая другая неделя не делает старое доказательство спорным. Пока award рассматривается как disputed, флаг не очищается автоматически.

Worker/resync блокируют journey перед оценкой метрик. Если correction уже коммитится до выдачи, evaluator читает исправленное значение; отложенное сообщение с прежними 96% не выдаёт золото после исправления на 80%. Это проверено отдельной многопоточной PostgreSQL гонкой.

## Durable события и обработка

| Provider | Идентификатор | Источник |
|---|---|---|
| roadmap_confirmation | confirmation PK | Atomic staff confirmation/revocation |
| sandbox_completion | completion PK | Создание нового frozen completion |
| sandbox_technical | CheckRun PK | Atomic credit technical success |
| weekly_metric | metric PK + UUID ревизии записи | Atomic save + before/after safe values + actor |
| stage_transition | StageHistory PK | Действительный переход с staff author |
| probation_completion | journey PK + completion date | Успешный staff-confirmed результат после сохранения |

Incoming record сохраняется **в той же транзакции**, что предметный факт. on_commit только делает best-effort inline wake; брокер/Redis не нужны. При падении обработки transaction выдачи откатывается, source получает error и остаётся durable. Команда `process_achievement_events` повторяет pending/error. Unfinished новые недели имеют available_at на локальное окончание периода; corrections проверяются сразу и при необходимости снова ждут окончания нового периода. Один source обрабатывается один раз под row lock; результат и grant commit атомарны.

Нужен регулярный запуск drain-команды, чтобы после падения wake и по достижении конца недели награды не ждали следующего изменения источника. Планировщик инфраструктуры не изменялся. Неизвестный provider/schema, отсутствующий каталог и ошибки остаются retryable. Окончательный unknown по неоднозначным данным отражается в result; после исправления фактов используется новый source или explicit reconciliation.

История источника хранит небольшие значения/IDs, без client_answer/internal_report/mentor feedback. Новые недельные записи получают UUID события, даже при возвращении значения A→B→A. Текущий WeeklyMetric остаётся существующим агрегатом; полноценного domain revision/finality/coverage ledger задача не создаёт.

## API

| Метод / путь | Доступ / назначение |
|---|---|
| GET `/api/achievements/me/` | Собственный полный активный каталог, текущие tiers, stats, pending_source_events |
| GET `/api/achievements/me/<public_id>/` | Собственные details + реальная history, по 50 событий, `?cursor=<last event id>` |
| GET `/api/achievements/users/<user_id>/` | Только staff, каталог конкретного пользователя |
| POST `/api/achievements/users/<user_id>/<public_id>/grant/` | Staff + CSRF, ручная выдача |
| POST `/api/achievements/users/<user_id>/<public_id>/revoke/` | Staff + CSRF, явный отзыв |

Session auth; JSON mutation bodies; private/no-store; 401 без session, 403 без staff/CSRF, 405 неправильный method, 400 плохой body/tier/reason, 404 неизвестная сущность, 409 operation conflict/expected revision. Штатный CSRF failure и Django 404 используют стандартный handler; остальные ответы JSON. POST body ограничен полями; browser не задаёт provider, proof, score, actor или rules.

```json
{"tier":"gold","reason":"Подтверждено при ручной проверке","operation_id":"<unique request ID>","expected_revision":0}
```

Для revoke `tier` отсутствует. expected_revision необязателен; если задан, проверяется под блокировкой. Response: action, event_id, revision. Идемпотентный повтор возвращает duplicate; no-op тоже получает receipt без фиктивного события получения.

Collection response: items + stats `{earned, applicable_total, rarities}` + pending_source_events. DTO: public_id, раскрытый code/title/description/category/kind, secret/revealed, applicable true/false/null, status earned/locked/revoked, nullable highest_tier, supported_tiers с criteria/automatic, rule_version, safe art_key, real earned_at/last_upgraded_at, revision, manual, data_quality и `progress=null`. GET не запускает evaluator, не создаёт missing projections и не восстанавливает Sandbox.

Unearned secret имеет только opaque ID, общие state/applicability/date/revision и placeholder `Секретное достижение`, description=null, generic art, progress=null. Semantic code, настоящее название, condition/thresholds, category, специализированный art, evidence, tiers и history отсутствуют. После revoke secret снова скрыт, пока active tier=NULL. Полученный secret раскрывается. Сырые proof snapshots отсутствуют и в публичной истории раскрытых наград; history отдаёт IDs реальных событий, from/to, dates, источник, manual, actor ID, reason и rule version.

Одна definition = один count; rarity определяется active maximum. Revoked не входит в earned. Знаменатель v1 — применимые активные definitions, включая безопасный secret placeholder; неприменимые excluded. Missing NEW_HIRE context даёт applicability=null и не увеличивает denominator. Полный каталог сейчас небольшой и отдаётся целиком; фильтры collection не реализованы. История paginated. Фиктивного процента выполнения нет.

Manual flag относится к **ручной выдаче награды** через staff API. Автоматическая бронза обучения по manual подтверждению имеет provider=roadmap_confirmation, а в защищённом evidence source=manual; это не Teachbase score.

## Реестр и дальнейшее расширение

Catalog schemas и evaluator/provider registry находятся на сервере. Definition и tier проходят серверную валидацию при сохранении и перед оценкой/выдачей; unknown version/evaluator/parameters/art key не исполняются. Нельзя редактированием JSON включить Sandbox platinum. Code/public UUID защищены от обычного ORM изменения. Добавление семейства не требует менять UserAchievement; новый evaluator/schema/version вводится кодом и versioned migration. Metadata admin остаётся read-only; произвольного Python/SQL/eval-конструктора нет.

## Проверки

Результаты окончательных прогонов приведены ниже; тестирование выполнялось только на свежих временных SQLite и PostgreSQL 16.9. Рабочие базы не подключались и production миграции не применялись.

| Проверка | Результат |
|---|---|
| Full Django suite, финальный SQLite | **841 тест за 265,975 с, OK**; 8 skip — PostgreSQL-specific tests |
| Achievements + Roadmap + затронутые Sandbox/Diary сервисы, PostgreSQL | 186 тестов, OK, без пропусков |
| PostgreSQL concurrency и raw SQL audit guards | 7 тестов, OK, входят в 186 |
| Fresh SQLite / PostgreSQL migrate | OK, четыре achievements migrations |
| System checks SQLite / PostgreSQL | 0 ошибок |
| makemigrations --check --dry-run SQLite / PostgreSQL | No changes detected |
| migrate --check SQLite / PostgreSQL | OK |
| Existing frontend build для Django integration tests | OK; TS/React source не менялся |
| GET API и resync dry-run под CaptureQueriesContext | SELECT-only |
| git diff --check; проверка исходных хешей | OK; изменены только семь разрешённых существующих backend-файлов |

Покрыты прямой platinum, все повышения и jump, repeated delivery, no downgrade, reason/staff/CSRF, suppression и старый no-op после revoke, rollback, immutable ORM/explicit PK/raw SQL, реальные source hooks и existing metric POST, frozen completion с удалением деталей, credit vs practice, distinct tasks, legacy fallback, история посещений/возвратов/неоднозначных периодов, wrong stage, terminated/internal transfer, quality 79/80/89/90/95/96/100, speed 4.9/5/6.9/7/8.9/9/10/10.1, inclusive probation 1/30/31/45/46/60/61, секретный JSON, resync версии и correction до/после выдачи. PostgreSQL проверяет первая вставка, разные proofs/tiers, revoke race, source delivery и correction/FK-lock race.

В achievements добавлен 71 тест; числовые границы дополнительно проверяются subtests. Восемь SQLite skips — семь новых PostgreSQL проверок и существующий concurrency test Roadmap; все они прошли в PostgreSQL прогоне. Временный кластер использовал только Unix-сокет `/tmp/achievement-foundation-pg/socket`, TCP был выключен. После проверок PostgreSQL остановлен, его временные данные удалены.

## Локальная проверка

Выберите новую локальную тестовую БД; эти команды не предназначены для production:

```sh
export DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=/tmp/achievement-local-check.sqlite3 SENTRY_DSN=''
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py migrate --check
.venv/bin/python manage.py test achievements --noinput
# Полный suite также требует существующие собранные React assets:
npm run build --prefix frontend
.venv/bin/python manage.py test --noinput

# Замените 123 фактическим ID синтетического пользователя выбранной локальной БД.
.venv/bin/python manage.py reconcile_achievements --user-ids 123 --families review_quality independent_speed --rule-version 1
# После просмотра dry-run явное применение на выбранной локальной БД:
.venv/bin/python manage.py reconcile_achievements --user-ids 123 --families review_quality independent_speed --rule-version 1 --apply
.venv/bin/python manage.py process_achievement_events --limit 100
```

Можно выбрать `--source weekly_metric` вместо `--families`. Без user IDs resync не запускается. Dry-run не создаёт source events/entitlements; apply заново оценивает текущие trusted факты под блокировкой и проверяет version. Миграции не запускают resync/backfill. Drain-command — операция записи, обрабатывает уже зарегистрированные события, без новой реконструкции исходных фактов.

## Ограничения и React следующей задачей

1. Нет полного Sandbox execution/reset/submission/review ledger, frozen answer requirements/coverage и course score/start. Высшие автоматические правила остаются выключенными.
2. Недельные метрики не доказывают полный рабочий coverage/finality; streak и clean_week выключены. Имеющаяся mutable история этапов и старые метрики не стали глобально immutable.
3. Автоматические hooks работают в штатных сервисах записи. Прямой ORM/SQL, сторонние maintenance writers и импорт обязаны регистрировать durable event или пройти явный resync; общий post_save намеренно не используется. Historical data/backfill production не проверялся и не запускался.
4. SQLite не заменяет PostgreSQL row locks/DB triggers. Конкурентная корректность проверена на PostgreSQL; SQLite предназначена для локальной функциональной проверки.
5. Для source recovery и maturation недель требуется регулярный drain. Inline wake увеличивает время завершения write-request; перенос wake в Celery позже не меняет durable guarantees. Не внедрялись deployment scheduler/Redis-настройки.
6. Legacy author trust проверяется по сохранённому автору и его текущему staff flag; это не исторический снимок роли. Сомнительные даты/история дают unknown. Старые записи не объявляются coverage-complete.
7. Revoke v1 снимает активную награду целиком и блокирует все automatic regrant; частичный отзыв одного proof с восстановлением ранее полученного lower tier и automatic unblock требуют отдельной политики. Disputed flag очищается только будущим явным review-механизмом; сейчас доступен audited revoke/manual regrant.
8. Source/events/receipts пока без retention/архивации; защита аудита требует отдельного осознанного плана хранения при росте объёма.

В отдельной React Integration задаче заменить fixtures на GET DTO, оставить одну карточку на definition, отображать nullable highest tier и server stats, различать unknown/not_applicable/revoked/disputed, скрывать секрет строго по placeholder. Историю показывать по реальным from/to событиям; toast дедуплицировать по event ID, не по первичной загрузке. Для manual staff actions использовать session CSRF и новый operation ID/expected revision. `art_key` маппить через локальный whitelist с generic fallback; геометрию SVG отделить от палитры rarity. Фиктивные 40%/даты браузера и demo unlock не использовать как настоящие выдачи. Никакая React-интеграция в этой задаче не выполнена.
