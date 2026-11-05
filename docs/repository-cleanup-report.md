# Результат аудита и минимального рефакторинга

05.11.2026. Worktree `/private/tmp/training-platform-repository-cleanup`, ветка
`chore/repository-cleanup-deploy-docs`, база `426ef04` (`origin/main`).
Исходная рабочая ветка и пользовательский untracked diagnostics workflow сохранены.
Push, merge, deployment и обращения к production не выполнялись.

## Переносы и удаления

| Прежний root path | Новый path |
|---|---|
| `ACHIEVEMENT_BACKEND_FOUNDATION.md` | `docs/reports/achievements/ACHIEVEMENT_BACKEND_FOUNDATION.md` |
| `ACHIEVEMENT_SYSTEM_AUDIT.md` | `docs/reports/achievements/ACHIEVEMENT_SYSTEM_AUDIT.md` |
| `TROPHY_ROOM_REACT_INTEGRATION.md` | `docs/reports/achievements/TROPHY_ROOM_REACT_INTEGRATION.md` |
| `ROADMAP_ACTIONS_NAVIGATION.md` | `docs/reports/roadmap/ROADMAP_ACTIONS_NAVIGATION.md` |
| `ROADMAP_BACKEND_FOUNDATION.md` | `docs/reports/roadmap/ROADMAP_BACKEND_FOUNDATION.md` |
| `ROADMAP_REACT_INTEGRATION.md` | `docs/reports/roadmap/ROADMAP_REACT_INTEGRATION.md` |

**Удалённых по содержимому файлов нет.** Screenshots/evidence сохранены.
Ссылки внутри отчётов и в двух `frontend/src/*/README.md` обновлены. Корень:
66 → 60 файлов, 53 → 47 Markdown. Не перемещены integrity-pinned отчёты,
runtime packages, Docker contexts, Terminal Broker и TraineeDiary.
Обоснование каждого решения: [полный аудит](repository-audit.md).

## Основные изменения

- `docs/README.md` — индекс; в README/ARCHITECTURE/CONTRIBUTING/STAGING_CHECKLIST
  исправлены устаревшие ops-утверждения об automatic deploy и recreate Gateway.
- `.gitignore`/`.dockerignore` — env/pins, DB exports/sidecars, caches, private keys
  и локальные server overrides. Публичные примеры и SQL source fixtures разрешены.
  Правила не удаляют уже tracked исторические артефакты.
- Новые `deploy/compose/{release,lite}.yml` и `deploy/releases/images.env.example`
  подключаются только явно; существующие Compose/Dockerfile не изменены.
- `deploy/release_config.py` — read-only проверка merged configuration и печать
  shell-quoted плана одной роли. Только `compose config`; deploy/apply режима нет.
  Проверяются отдельные immutable image pins и согласованность включённого Lite.
- [Runbook](../deploy/manual_releases.md) — snapshot по данным оператора, порядок
  файлов/profile/project, preflight/reconciliation, роли, health/rollback и bind inode.

## Проверки

| Проверка | Результат |
|---|---|
| Django system check | PASS, без issues |
| Django check --deploy | Exit 0; прежние W019 (X-Frame SAMEORIGIN), W021 (HSTS preload=false); settings не менялись |
| Migration drift | No changes detected; production-БД не подключалась |
| Полный Django suite: 6 apps | PASS: 1044 run, 28 skipped, 308,0 с; временная SQLite |
| Frontend | npm ci, 60 JS tests, typecheck и Vite build PASS |
| Broker Lite | 46 unit/PTY tests PASS |
| Gateway DNS, основной + fullstack config | 2 Docker-теста PASS за 43,7 с: nginx 1.28.3, IP .10→.11, HTTP recovery 5,4/9,1 с; auth, старый/новый WS, healthy, прежние nginx PID |
| Действующие локальные контейнеры | Все 8 сохранили ID/image/StartedAt/RestartCount после тестов |
| Release configuration | 7 tests PASS, включая реальный Compose merge, distinct image pins, fixed file set, env precedence/redaction и отсутствие выполнения плана |
| Existing workflows | YAML/workflow policy и 26 regression tests PASS; workflows byte-identical базе |
| Existing Compose | base+prod, base+local, base+override с profile terminal-broker: config PASS на synthetic env |
| Isolated lab Compose | standalone PoC и base+observation example: config PASS, без запуска |
| Docker build | PASS, отдельный tag `training-platform-repository-audit:426ef04`, image `sha256:4325ac5bf33876e373fc05cc4b62d056589331cef524f1af1dbd0c536f412ed5` |
| Финальный Docker build | PASS, `training-platform-repository-audit:426ef04-final`, image `sha256:19257ab8e84bdc2f3aefe68fd225e41ccded7159d08d130696523db4273e63cc`; editor/design/Git исключены, runtime/frontend/release tool/report присутствуют |
| Docker context hygiene | Проверка нового image в --rm/--network none/--read-only контейнере: нет Git, SQLite/SQL и env sentinel; runtime/task/static/report files присутствуют |
| Git hygiene | DB sidecars/dumps/private env/server overrides/keys игнорируются; публичные env examples и SQL source fixtures разрешены |
| Links | 85 Markdown-файлов, все outgoing targets 6 переносов сохранены; новых broken relative paths 0, прежних 14 |
| Existing source integrity | 1012 исходных non-Markdown files (кроме двух ignore) byte-identical; Terminal/TraineeDiary docs тоже не изменены |
| Syntax / whitespace | Python AST, Bash snippets и git diff --check PASS |

Первый запуск Django suite в свежем worktree выполнен без предварительного
`collectstatic` и получил ошибки Vite assets (не изменение приложения). Подготовка
исправлена тем же порядком, что в CI: npm build → collectstatic → новый test process.
Временные SQL/SQLite/env context sentinels были не секретами и удалены после проверки.

Основные команды для воспроизведения (в подготовленном venv из корня checkout):

```sh
python -m unittest deploy.tests.test_release_config -v
python deploy/ci/workflow_policy.py
python -m unittest discover -s deploy/ci -p 'test_*.py' -v
python -m unittest discover -s experiments/terminal_broker -p 'test_*.py' -v
# npm ci && npm test && npm run build — из frontend/
DEBUG=False DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
  python manage.py collectstatic --noinput
DEBUG=True DB_ENGINE=django.db.backends.sqlite3 DB_NAME=:memory: \
  python manage.py test sandbox traineediary assessment achievements roadmap react_frontend --noinput
RUN_GATEWAY_DNS_TESTS=1 python -m unittest discover -s deploy/tests -p test_gateway_dns.py -v
```

Workflow policy и Gateway test требуют PyYAML (как в существующем CI);
release tool/tests — stdlib и Docker Compose CLI. Gateway/Docker tests используют
только новые случайные lab projects, а не application project `training-platform`.

## Что не является результатом этой работы

Серверные `docker-compose.release.yml`/`docker-compose.lite-pilot.yml` не получены.
Эквивалентность новой модели production не доказана. Их перенос требует read-only
сверки env/command/mounts/networks/volumes/health и отдельного разрешения на внедрение.
Никакие роли, флаги, схемы БД или production-данные не переключались.
Hosted CI для этой ветки не запускался, поскольку push запрещён.

## Оставшийся долг и будущие шаги

1. Архивировать integrity-pinned отчёты отдельным проектом, сохраняя исторические
   manifests и воспроизводимость; не пересчитывать их задним числом.
2. Обновить внешние ссылки на 6 прежних root URLs. Неизменённые старые документы
   могут содержать исторические paths; новые локальные Markdown-поломки не допускаются.
3. Сверить серверные overrides, закрепить точные registry digests, OCI revision,
   платформу, hashes runtime/config и image availability в private release manifest.
4. Добавить новые read-only tests/documentation checks в hosted CI отдельным review.
   Все нынешние workflows и disabled manual CD сохранены.
5. Отдельно рассмотреть Scheduler health/heartbeat, очередь/drain, retention evidence,
   полный history secret scan, mutable base tags и Docker socket isolation.
6. Развивать CD только после доказанной изоляции staging и рассмотренной Lite-aware
   процедуры. Здесь нет автоматических deploy, SSH, новых background processes
   или задач миграции.
