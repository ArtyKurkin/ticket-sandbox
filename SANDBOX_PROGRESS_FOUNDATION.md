# Sandbox Progress Foundation

## Единый контракт

Владелец расчёта — `sandbox/services/progress.py`. Старый модуль `traineediary/services/sandbox_progress.py` только переэкспортирует сервис и DTO: второго расчёта больше нет.

```python
from sandbox.services.progress import (
    build_sandbox_queue_progress,
    build_sandbox_queue_progress_map,
)

progress = build_sandbox_queue_progress(user, queue_slug="l1")
progress_by_user_id = build_sandbox_queue_progress_map(users, queue_slug="l1")
```

Сервис возвращает неизменяемый `SandboxQueueProgress`. Основные поля и свойства:

| Значение | Значение контракта |
|---|---|
| queue_exists, queue_slug, queue_name | Активная очередь; отсутствующая или неактивная очередь не даёт зачёта |
| total_count | Число обязательных активных заданий выбранной очереди |
| technical_completed_count | Число уникальных технически завершённых заданий по попытке №1 |
| remaining_count, progress_percent | Оставшиеся технические задания и технический процент |
| is_technically_completed | Все обязательные задания технически выполнены, набор непустой |
| needs_revision_count | Зачётные клиентские ответы с решением наставника needs_revision |
| on_review_count | Зачётные ответы с status=on_review и mentor_decision=not_reviewed |
| unsubmitted_count | Технический зачёт получен, но ответ ещё не отправлен/не принят/не возвращён на доработку |
| approved_answer_count | Ответы, принятые наставником; отдельно от доказательства технического зачёта |
| unread_feedback_count | Зачётные ответы с непустым непрочитанным комментарием наставника |
| feedback_read_state_unknown_count | Комментарий отмечен прочитанным, но отсутствует дата проверки: невозможно сравнить даты |
| required_task_ids | Упорядоченный состав обязательного набора на момент чтения |
| technically_completed_task_ids | Уникальные ID заданий с техническим доказательством в том же порядке |
| diagnostics | Неоднозначные результаты и противоречивые CheckRun, без изменения данных |

Для совместимости с существующими Django-потребителями сохранены `passed_count` (то же, что technical_completed_count) и `is_ready` (то же, что is_technically_completed). `is_ready` в этом DTO не означает принятие ответов или перевод между рабочими этапами. Будущий API должен явно сериализовать технические поля, а не использовать эти старые названия как общий статус адаптации.

Счётчики ответов относятся к активным обязательным заданиям, требующим ручной проверки, и только к попыткам №1. Тренировочные попытки в них не входят. Ревизия/проверка/неотправленный ответ — отдельные состояния ответа, непрочитанность может пересекаться с ними. Эти состояния не вычитаются из технического прогресса. Даже у неоднозначного исторического технического результата могут существовать принятый ответ или запрос доработки.

Batch-расчёт выполняет три SELECT независимо от числа пользователей и заданий: очередь, задания, зачётные попытки с аннотациями доказательств. Повторяющиеся пользователи дедуплицируются. Отсутствующие попытки остаются отсутствующими. Сервис не вызывает `get_current_attempt`, не создаёт попытки, не меняет is_current, не записывает дату технического зачёта и не переводит адаптацию.

## Правило технического зачёта

Общее правило реализовано в `sandbox/services/technical_evidence.py` и используется свойствами TaskAttempt, прогрессом, доступностью следующего задания, dashboard и уведомлениями.

1. Для новых результатов доказательство — непустой `technical_passed_at`.
2. При отсутствии даты допускается исторический CheckRun этой же зачётной попытки с **обоими** признаками: `result=passed` и `exit_code=0`. Используется время первого такого запуска. Последующее замечание к ответу или неуспешный исторический запуск не отменяют доказательство прежнего успеха.
3. `status=passed`, `check_status=passed` и `mentor_decision=approved` сами по себе не доказывают техническое прохождение. Наставник действительно может установить passed через `save_mentor_feedback`.
4. CheckRun с противоречивыми result/exit_code не доказывает успех. Он попадает в диагностику; наличие такого запуска не отменяет отдельное достоверное доказательство.
5. Техническое выполнение тренировочной попытки описывает эту попытку, но не заменяет результат попытки №1. Прогресс, открытие следующего задания и завершение очереди используют только зачётную попытку.

`TaskAttempt.technical_passed` и `is_technically_completed` теперь согласованы. `technical_locked` использует это же доказательство. Обычные действия с окружением и техническая проверка после зачёта блокируются. Ограничение проверено также в сервисе фонового запуска и worker/direct обработчике, включая исторические CheckRun. Для самостоятельной тренировки по-прежнему создаётся отдельная попытка с номером больше 1.

Новые AI-снимки ответа также используют это доказательство в technical_check_passed; старые AI-снимки не меняются. История CheckRun, даты, авторы и решения наставников не переписываются. Миграции и backfill не требуются.

## Независимая работа с ответами

Если наставник возвращает зачётный ответ после создания тренировочной попытки, владельцу доступна доработка **исходной попытки №1**. Исключение из блокировки исторических действий действует только для технически зачтённого ответа с needs_revision. Оно не открывает запуск, перезапуск, повторный технический check или создание новой тренировки из старой попытки.

Форма сохраняет клиентский ответ и внутренний комментарий в исходной попытке и отправляет её на повторную ручную проверку. `technical_passed_at`, CheckRun, attempts_count и is_current сохраняются. Текущая тренировочная попытка и её окружение не меняются; при исторической текстовой доработке cleanup окружения не вызывается. Для исторического доказательства через CheckRun дата technical_passed_at также не заполняется автоматически.

Dashboard показывает отдельную ссылку на возвращённый зачётный ответ и непрочитанные комментарии из попытки №1, даже когда текущая попытка тренировочная. Панель наставника учитывает повторную проверку старой зачётной попытки независимо от is_current. Новый блок уведомлений по ответам виден отдельно от технического процента в Sandbox, TraineeDiary, карточке и Kanban. Панель наставника отдельно показывает технически выполненные попытки и предупреждает о passed без доказательства.

Ограничения владельца/чужих попыток, login и CSRF сохранены. Терминал для passed/on_review закрыт независимо от достоверности старого технического результата; неоднозначный исторический статус не открывает терминал автоматически.

Чтение самого сервиса не отмечает комментарии прочитанными. При открытии своей карточки прежний обработчик `task_detail` продолжает явно сохранять факт прочтения. Прежний workflow dashboard продолжает подготавливать текущие попытки через get_current_attempt; этот сценарий отделён от чистого расчёта прогресса и не используется будущим Roadmap.

## Диагностика

Команда читает зачётные попытки указанной очереди, включая неактивные исторические задания. Она не исправляет историю и не запускает технические проверки.

```sh
python manage.py audit_sandbox_progress --queue l1
python manage.py audit_sandbox_progress --queue l1 --user-id 123 --json
```

Отчёт содержит только code, attempt_id, user_id, task_id:

- `passed_without_technical_evidence` — workflow passed без даты и достоверного CheckRun;
- `check_status_without_technical_evidence` — check_status passed без доказательства;
- `conflicting_check_run` — несогласованность result и exit_code.

Диагностика в DTO ограничена текущими обязательными заданиями, а команда включает также исторические неактивные задания. Разбор неоднозначных записей и любые исправления данных требуют отдельного решения; автоматического зачёта по ответу наставника нет.

## Состав программы и будущий Roadmap

В репозитории подтверждены 15 активных `training_tasks/l1/*/task.json`, все с ручной проверкой ответа. Расчёт использует текущие записи Task активной очереди со slug l1, без числа 15 в коде. Реальная конфигурация production не читалась.

**Ограничение текущей модели:** результат сервиса описывает текущий набор заданий, а не сохранённый факт завершения фиксированной версии программы. Добавление/активация нового задания может изменить is_technically_completed с true на false; удаление/деактивация может уменьшить обязательный набор. required_task_ids позволяет явно обнаружить изменение состава. Предыдущие результаты попыток сохраняются, но из них невозможно надёжно восстановить прежний состав программы и момент её завершения.

Не используйте live-флаг как единственный источник для уже подтверждённого `completed` в будущем Roadmap. Минимальная следующая мера — отдельный неизменяемый факт завершения в Sandbox, например `SandboxProgramCompletion`: пользователь/адаптация, стабильный ключ версии программы, completed_at, снимок обязательных task_ids и ссылок/типов технических доказательств. Создание выполняется явным write-сервисом после технического успеха, с идемпотентностью по участнику и версии; чтение прогресса остаётся чистым. Старые завершения сохраняются при изменении текущего каталога, новая версия программы не заменяет их. Это не требует миграции StageHistory или приложения roadmap. В этой задаче такая модель не создаётся, неизвестные исторические завершения не восстанавливаются автоматически.

Станции React и новая схема TraineeDiary не меняются. Sandbox readiness в дневнике рекомендует переход после всех технических зачётов; доработки и ручная проверка текста не блокируют эту рекомендацию. Критерии качества, скорости и завершения ИС сохранены. Даже при полном техническом прогрессе текущий этап дневника не изменяется; переход остаётся ручным и аудируемым.

Будущий Roadmap сможет использовать доказанное завершение Sandbox для станции 02 и доступности «Карты эскалаций» (03), сохраняя независимые уведомления по ответам. Сервис не подтверждает прохождение «Карты эскалаций» или «Анализа тикетов», не создаёт их приложения и не предоставляет API. Прежде чем подключать `completed`, нужно реализовать и согласовать сохранение факта завершения и версионирование программы.

## Изолированная проверка

Используйте только тестовую БД. Не запускайте диагностику против production в рамках этой задачи.

```sh
export DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: SENTRY_DSN=''
.venv/bin/python manage.py test --noinput
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
```

Для диагностической команды нужна БД с таблицами: отдельно создайте временную SQLite, выполните migrate, подготовьте синтетические попытки и запустите audit. В рамках реализации использованы только изолированные SQLite и синтетические данные, реальная БД не читалась и не изменялась. PostgreSQL-копия не предоставлена; проверка запросов/параллельных операций на ней остаётся следующей проверкой перед выпуском. Никаких commit, push или деплоя не выполнялось.


## Результаты проверки

Проверено 13 октября 2026 на изолированной SQLite, Python 3.13 / Django 6.0.5:

| Проверка | Результат |
|---|---|
| Полный `manage.py test --noinput` | 706 тестов, OK (256 секунд) |
| Новые тесты Foundation в полном suite | 31 тест, OK |
| `manage.py check` | 0 ошибок |
| `makemigrations --check --dry-run` | No changes detected; новые миграции не нужны |
| Отсутствие записей при чтении прогресса | SELECT-only, попытки/is_current/CheckRun/даты неизменны |
| Диагностическая команда | Проверена на синтетических исторических и неактивных заданиях; JSON и отсутствие изменений |
| Batch-расчёт | 3 SELECT для нескольких пользователей |
| Совместимость legacy/unified | Общий источник прогресса, ручные этапы и StageHistory сохраняются |
| Сохранение исходных изменений | Файлы схем, миграций, React, assessment, production-конфигурации и CI/CD совпадают со снимком начала задачи |
| `git diff --check` | OK |

Проверки включают реальные Django-запросы владельца/staff, CSRF, чужие попытки, исправление старого зачётного ответа после создания тренировки, запрет повторного checker/worker после успеха, исторический CheckRun, неоднозначный passed, независимые уведомления, новые AI-снимки и отсутствие автоматического перехода дневника.

Первый полный прогон обнаружил три старых fixture-сценария карточки с одним status=passed без доказательства. В них добавлены дата технического зачёта и признак ручной проверки задачи; отдельные тесты неоднозначного passed сохраняют запрет на автоматический зачёт. После исправления выполнен успешный полный прогон.

PostgreSQL не проверялся: обезличенная копия недоступна. Отчёт по реальным пользователям не формировался; подготовлена read-only команда для отдельного согласованного аудита. Ветка `feature/roadmap-react` сохранена; commit, push и деплой не выполнялись.

## Файлы задачи 5

Список относительно начала этой задачи; незакоммиченные изменения предыдущего этапа сохранены.

Изменены:

- [CHANGELOG.md](CHANGELOG.md)
- [README.md](README.md)
- [sandbox/models.py](sandbox/models.py)
- [sandbox/services/ai_reviewer.py](sandbox/services/ai_reviewer.py)
- [sandbox/services/attempt_display.py](sandbox/services/attempt_display.py)
- [sandbox/services/attempts.py](sandbox/services/attempts.py)
- [sandbox/services/checks.py](sandbox/services/checks.py)
- [sandbox/services/mentor_dashboard.py](sandbox/services/mentor_dashboard.py)
- [sandbox/services/trainee_dashboard.py](sandbox/services/trainee_dashboard.py)
- [sandbox/tests/test_task_availability.py](sandbox/tests/test_task_availability.py)
- [sandbox/views.py](sandbox/views.py)
- [templates/sandbox/mentor_dashboard.html](templates/sandbox/mentor_dashboard.html)
- [templates/sandbox/task_detail.html](templates/sandbox/task_detail.html)
- [templates/sandbox/trainee_dashboard.html](templates/sandbox/trainee_dashboard.html)
- [traineediary/services/assessment.py](traineediary/services/assessment.py)
- [traineediary/services/sandbox_progress.py](traineediary/services/sandbox_progress.py)
- [traineediary/templates/traineediary/_kanban_scheme_fragment.html](traineediary/templates/traineediary/_kanban_scheme_fragment.html)
- [traineediary/templates/traineediary/_sandbox_l1_progress.html](traineediary/templates/traineediary/_sandbox_l1_progress.html)
- [traineediary/templates/traineediary/trainee_detail.html](traineediary/templates/traineediary/trainee_detail.html)
- [traineediary/tests/test_assessment.py](traineediary/tests/test_assessment.py)
- [traineediary/tests/test_sandbox_progress.py](traineediary/tests/test_sandbox_progress.py)
- [traineediary/tests/test_trainee_detail.py](traineediary/tests/test_trainee_detail.py)
- [traineediary/tests/test_trainees.py](traineediary/tests/test_trainees.py)

Созданы:

- [SANDBOX_PROGRESS_FOUNDATION.md](SANDBOX_PROGRESS_FOUNDATION.md)
- [sandbox/management/commands/audit_sandbox_progress.py](sandbox/management/commands/audit_sandbox_progress.py)
- [sandbox/services/progress.py](sandbox/services/progress.py)
- [sandbox/services/technical_evidence.py](sandbox/services/technical_evidence.py)
- [sandbox/tests/test_progress.py](sandbox/tests/test_progress.py)
- [templates/sandbox/_answer_progress.html](templates/sandbox/_answer_progress.html)
