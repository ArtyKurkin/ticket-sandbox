# Совместимость каталога 0007 и повторная репетиция

Подтверждённый администратором read-only результат от 2026-10-30 содержит ровно
10 изменений. Неизвестных/отсутствующих slug и изменений остальных проверяемых
полей нет.

Повторная репетиция администратора 30.10.2026 прошла успешно:
[согласованная сводка](database_rehearsal_2026-10-30.md).

| slug | Поле | Эталон | Подтверждённый вариант |
| --- | --- | ---: | ---: |
| before-tickets | order | 6 | 5 |
| client-service | max_days | 2 | 3 |
| managed-services | max_days | 3 | 4 |
| no-review | max_days | 10 | 14 |
| optional-review | min_days | 5 | 10 |
| optional-review | max_days | 10 | 14 |
| sandbox-candidate | order | 5 | 6 |
| sandbox-candidate | max_days | 2 | 3 |
| with-review | min_days | 15 | 28 |
| with-review | max_days | 20 | 35 |

В frozen-контракт 0007 добавлен один полный исторический профиль. Он выбирается
только при наличии всех десяти legacy-этапов и совпадении всех десяти изменений.
Все 1022 частичных комбинации отклоняются. Исходный LEGACY_CATALOG остаётся
эталоном для исходного варианта и новых seed-записей. TRAINING_PROGRAM не меняется.
Неизвестные этапы, неподдерживаемые группы, названия, веса, применимость, параметры,
отсутствующие исторические этапы при наличии истории и используемый до миграции
training-program по-прежнему блокируют миграцию.

Тело forwards не изменено: существующие этапы получают только новое поле
catalog_scope, существующие journeys — stage_scheme=legacy. Исходные ID, FK,
названия, порядок, сроки, веса, цвета, активность, история и WeeklyMetric не
перезаписываются. Проверка catalog_issues одна для миграции, runtime preflight,
seed и сценария репетиции, в том числе postflight.

## Локальные проверки

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 DEBUG=True \
DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: SENTRY_DSN='' \
.venv/bin/python -B manage.py test \
  traineediary.tests.test_stage_migrations \
  traineediary.tests.test_seed_stages \
  traineediary.tests.test_stage_schemes \
  traineediary.tests.test_weekly_metrics

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover \
  -s deploy/tests -p test_database_rehearsal.py -v
```

SQLite используется только в памяти. DEBUG=True нужен HTTP-тестам, чтобы
production-настройка HTTPS redirect не превращала ответы в 301. Тесты deploy
подставляют все внешние команды и не обращаются к Docker или действующей БД.

## Повторное использование backup

Существующий database.dump пригоден для проверки исправления на том же снимке,
если сохранён исходный приватный report.json, в нём backup.valid=true,
toc_checked=true, SHA-256 и размер совпадают, source_revision соответствует
92a1123486c1e8ca348ce28e8726944532bed63b. Проверяются права файлов и каталогов,
PGDMP header, исходный бюджет размера БД для ресурсов, а на новой копии повторяется
pg_restore --list и проверка обязательных таблиц.

Новый режим --reuse-backup-report не вызывает pg_dump, не проверяет checkout,
не инспектирует действующие web/db и не выполняет запросов в основной БД.
Он создаёт новый изолированный container/volume, восстанавливает архив атомарно,
ограничивает роль копии до владельца без superuser и выполняет прежние проверки
плана, каталога, зачётов, отпечатков всех исходных колонок/таблиц и sequence.
Старые report.json и database.dump не изменяются. Старый контейнер копии не
используется повторно. Его удаление/остановка остаются отдельной ручной операцией.

В отчёте явно устанавливаются snapshot_reused=true,
source_database_contacted=false и readiness_scope=historical_snapshot_only.
PASS относится только к этому снимку. Новые записи основной БД в нём отсутствуют;
результат не подтверждает готовность текущей БД к deploy и не является актуальным
rollback-backup. Перед реальным обновлением нужен новый backup в согласованном
окне без записей и отдельная проверка актуальной БД. Восстанавливать старый backup
поверх действующей БД нельзя: это потеряет новые записи.

## Пакет нового образа

Образ собирается штатным Dockerfile из git archive нового локального коммита,
на платформу linux/amd64, с org.opencontainers.image.revision=<полный новый SHA>.
Изменения README.md и диагностического workflow вне этой задачи не входят в
коммит или build context. Образ 7f1811d не содержит исправленного контракта.
Актуальная методика: [database_rehearsal.md](database_rehearsal.md).

Пакет содержит точный image archive, его SHA-256, source archive и Git bundle,
сценарий репетиции, этот документ, manifest.json, SHA256SUMS и run-rehearsal.sh.
Ни backup, ни пользовательские записи, ни рабочие .env в пакет не включаются.
manifest.json фиксирует commit, платформу, image ID, хеш миграции и артефактов.
run-rehearsal.sh жёстко закрепляет новый SHA и image ID. Подмена только OCI label
старого образа не является проверкой исправленного кода.

План ручного запуска после отдельного разрешения:

1. Сохранить пакет в приватном каталоге вне рабочего checkout. Проверить
   SHA256SUMS. Проверить архитектуру сервера: x86_64/amd64. Импортировать точный
   image archive через docker load; действующие web/worker не перезапускаются.
2. Найти report.json неуспешной репетиции и соседний database.dump. Не передавать
   их содержимое в чат или Actions artifacts. Каталог 0700, файлы 0600,
   владелец — пользователь запуска. Новый backup-root также должен быть приватным.
3. Получить immutable PostgreSQL image ID из старого контейнера копии, указанного
   в предыдущем отчёте, через docker container inspect --format '{{.Image}}'.
   Это не обращение к основной БД. Переданный образ должен быть локальным PG 16.
4. Вначале выполнить только план (без Docker/БД и создания файлов):

   ```bash
   bash ./run-rehearsal.sh \
     --backup-root /var/backups/training-platform \
     --reuse-backup-report /ABSOLUTE/PREVIOUS-RUN/report.json \
     --postgres-image sha256:REPLACE_WITH_POSTGRES_IMAGE_ID
   ```

5. После отдельного разрешения повторить ту же команду с --execute.
   Пакет не отправляется на сервер и не запускается автоматически.
6. Ожидать catalog_issues=0 до и после миграции, ровно 15 миграций,
   nonlegacy_journeys=0, tables_changed=0, sequences_regressed=0,
   отсутствие массовых наград, неизменность рассчитанных зачётов. Значения
   lost_credit_pairs=0, gained_credit_pairs=13, affected_users=1 должны повториться,
   если это тот самый снимок исходной неуспешной репетиции.

Любая несовместимость, потеря данных или неожиданный план останавливают сценарий.
Никакого --fake, deploy, push, merge или миграций основной БД эти команды не делают.
