# Аудит репозитория и план минимальных изменений

Дата: 05.11.2026. База: `426ef04` (origin/main), отдельный worktree, ветка
`chore/repository-cleanup-deploy-docs`. Production не исследовался и не изменялся.

## Область и метод

В базе **1095 tracked files**, **66 файлов в корне**,
из них **53 Markdown**. Проиндексированы все tracked paths, размеры/расширения,
буквальные обратные ссылки на корневые документы, Python imports (AST), Docker COPY,
Compose mounts/env/profiles, workflow commands, settings paths, management commands,
Makefile и integrity manifests. Возраст файла не использован как критерий удаления.
Это статический аудит зависимостей; отсутствие ссылки не доказывает отсутствие
внешнего потребителя. История секретов Git отдельно не сертифицируется.

## Полный перечень корневых файлов (до изменений)

| Файл | Назначение / зависимости | Решение |
|---|---|---|
| `.dockerignore` | Фильтр Docker build context; COPY в Dockerfile и E2E driver. | Оставить в корне. |
| `.env.example` | Публичный образец локальных переменных; не секреты. | Оставить в корне. |
| `.env.prod.example` | Публичный образец production env; Broker по умолчанию false, не снимок сервера. | Оставить в корне. |
| `.gitignore` | Правила локальных/секретных/генерируемых файлов. | Оставить в корне. |
| `.gitleaks.toml` | Настройки secret scanner и исключения integrity hashes. | Оставить в корне. |
| `ACHIEVEMENT_BACKEND_FOUNDATION.md` | Achievement Backend Foundation; входящих ссылок в tracked текстах: 1. | Перенести в `docs/reports/achievements/ACHIEVEMENT_BACKEND_FOUNDATION.md`; обновить relative links. |
| `ACHIEVEMENT_NOTIFICATIONS_UX.md` | Achievement Notifications & TraineeDiary UX Polish; входящих ссылок в tracked текстах: 0. | Оставить в корне. |
| `ACHIEVEMENT_SYSTEM_AUDIT.md` | Achievement System Audit — Training Platform; входящих ссылок в tracked текстах: 0. | Перенести в `docs/reports/achievements/ACHIEVEMENT_SYSTEM_AUDIT.md`; обновить relative links. |
| `ARCHITECTURE.md` | ARCHITECTURE; входящих ссылок в tracked текстах: 2. | Оставить в корне. |
| `CHANGELOG.md` | CHANGELOG; входящих ссылок в tracked текстах: 4. | Оставить в корне. |
| `CONTRIBUTING.md` | CONTRIBUTING; входящих ссылок в tracked текстах: 2. | Оставить в корне. |
| `Dockerfile` | Multi-stage Node/Vite + Python/Gunicorn; collectstatic при build. | Оставить в корне. |
| `Makefile` | Локальные dev/test/nginx команды; make up не production release. | Оставить в корне. |
| `README.md` | Training Platform; входящих ссылок в tracked текстах: 23. | Оставить в корне. |
| `ROADMAP_ACTIONS_NAVIGATION.md` | Roadmap Actions & Navigation; входящих ссылок в tracked текстах: 3. | Перенести в `docs/reports/roadmap/ROADMAP_ACTIONS_NAVIGATION.md`; обновить relative links. |
| `ROADMAP_BACKEND_FOUNDATION.md` | Roadmap Backend Foundation; входящих ссылок в tracked текстах: 2. | Перенести в `docs/reports/roadmap/ROADMAP_BACKEND_FOUNDATION.md`; обновить relative links. |
| `ROADMAP_REACT_INTEGRATION.md` | React Roadmap Integration; входящих ссылок в tracked текстах: 2. | Перенести в `docs/reports/roadmap/ROADMAP_REACT_INTEGRATION.md`; обновить relative links. |
| `SANDBOX_ADVANCED_ACHIEVEMENTS.md` | Sandbox Advanced Achievement Evaluators — задача №16; входящих ссылок в tracked текстах: 1. | Оставить в корне. |
| `SANDBOX_COMPLETION_SNAPSHOT.md` | Sandbox Completion Snapshot; входящих ссылок в tracked текстах: 3. | Оставить в корне. |
| `SANDBOX_EVIDENCE_LEDGER.md` | Sandbox Evidence Ledger; входящих ссылок в tracked текстах: 1. | Оставить в корне. |
| `SANDBOX_PROGRESS_FOUNDATION.md` | Sandbox Progress Foundation; входящих ссылок в tracked текстах: 3. | Оставить в корне. |
| `STAGING_CHECKLIST.md` | STAGING CHECKLIST; входящих ссылок в tracked текстах: 2. | Оставить в корне. |
| `TERMINAL_BROKER_LITE.md` | Terminal Broker 2.0 Lite — реализация и проверка; входящих ссылок в tracked текстах: 1. | Оставить без изменений по ограничениям задачи. |
| `TERMINAL_BROKER_V2.md` | Terminal Broker 2.0 — итоговый отчёт и security-review; входящих ссылок в tracked текстах: 2. | Оставить без изменений по ограничениям задачи. |
| `TRAINEEDIARY_ACHIEVEMENT_MANAGEMENT.md` | Управление достижениями в TraineeDiary; входящих ссылок в tracked текстах: 0. | Оставить без изменений по ограничениям задачи. |
| `TRAINEEDIARY_STAGE_SCHEMES.md` | Схемы этапов TraineeDiary; входящих ссылок в tracked текстах: 2. | Оставить без изменений по ограничениям задачи. |
| `TROPHY_ROOM_REACT_INTEGRATION.md` | Trophy Room React Integration; входящих ссылок в tracked текстах: 1. | Перенести в `docs/reports/achievements/TROPHY_ROOM_REACT_INTEGRATION.md`; обновить relative links. |
| `TRUSTED_CHECKER_COUNTER_EVIDENCE.md` | Trusted Checker: nftables Counter Evidence Foundation — №20.1b-6; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_DOCKER_INTEGRATION.md` | Trusted Checker: Docker integration harness — задача №19; входящих ссылок в tracked текстах: 7. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_FOUNDATION.md` | Trusted Checker Foundation & Isolated PoC — задача №18; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_KERNEL_COMPATIBILITY_AUDIT.md` | Trusted Checker: Kernel Evidence Compatibility Audit — №20.1b-7b; входящих ссылок в tracked текстах: 7. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_LIVE_RUNTIME_IMPLEMENTATION.md` | Trusted Checker: Live Docker Runtime Implementation — №20.1b-2; входящих ссылок в tracked текстах: 7. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_MVP_DJANGO_INTEGRATION.md` | Trusted Checker MVP — Django Observation Integration; входящих ссылок в tracked текстах: 2. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_MVP_DOCKER_PILOT.md` | Trusted Checker MVP — Observation-only Docker Pilot; входящих ссылок в tracked текстах: 4. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_MVP_REAL_ADAPTER_PILOT.md` | Trusted Checker MVP — Real Docker Adapter Pilot; входящих ссылок в tracked текстах: 1. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_MVP_SIMPLIFICATION.md` | Trusted Checker — Architecture Simplification & MVP Implementation Plan; входящих ссылок в tracked текстах: 6. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_COMPATIBILITY_V2_DESIGN.md` | Trusted Checker: Native Compatibility Contract v2 — №20.1b-8a; входящих ссылок в tracked текстах: 8. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_COLLECTOR_IMPLEMENTATION.md` | Trusted Checker v2: Fenced Read-only Collector — №20.1b-8g; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_HELPER_IMPLEMENTATION.md` | Trusted Checker v2: Standalone Helper Protocol & Identity Boundary — №20.1b-8i; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_IDENTITY_IMPLEMENTATION.md` | Trusted Checker: Native v2 Typed Contracts & Scoped Identity — №20.1b-8b; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_KERNEL_FIXTURES_REVIEW.md` | Trusted Checker: Native Kernel Fixtures & Compatibility Regression — №20.1b-8f; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_MANAGEMENT_PROFILE_IMPLEMENTATION.md` | Trusted Checker: Native v2 Management-host Profile Validator — №20.1b-8e; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_OS_READER_IMPLEMENTATION.md` | Trusted Checker v2: Dormant OS Read-only Backend — №20.1b-8h; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_READBACK_IMPLEMENTATION.md` | Trusted Checker: Native v2 nftables Readback Adapter — №20.1b-8c; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NATIVE_V2_TOPOLOGY_IMPLEMENTATION.md` | Trusted Checker: Native v2 Topology Adapter — №20.1b-8d; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NETWORK_ALTERNATIVES.md` | Trusted Checker: исследование альтернатив NFTRACE — №20.1b-5; входящих ссылок в tracked текстах: 6. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NETWORK_VALIDATION.md` | Trusted Checker: Network Enforcement & Active Validation — №20.1b-3; входящих ссылок в tracked текстах: 7. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_NETWORK_VALIDATION_FIX.md` | Trusted Checker PoC: NetworkID validation fix; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_ORPHAN_RECOVERY.md` | Trusted Checker: create/register race и orphan recovery — задача №19.1; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_PHYSICAL_NETWORK_BACKEND.md` | Trusted Checker: Physical Network Backend — №20.1b-4; входящих ссылок в tracked текстах: 6. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_PREPARE_DIAGNOSTICS.md` | Trusted Checker: prepare diagnostics и остановка каскада — задача №19.1.2; входящих ссылок в tracked текстах: 6. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_RUNTIME_PROVENANCE.md` | Trusted Checker Runtime Architecture & Trusted Target Provenance — №20.1b-1; входящих ссылок в tracked текстах: 8. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_SANDBOX_INTEGRATION_AUDIT.md` | Trusted Checker → Ticket Sandbox: аудит и проект shadow mode; входящих ссылок в tracked текстах: 9. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_SHADOW_FOUNDATION.md` | Trusted Checker Shadow Foundation — №20.1a; входящих ссылок в tracked текстах: 8. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_TEST_STABILITY_FIX.md` | Trusted Checker: стабильность unit suite — задача №19.1.2.1; входящих ссылок в tracked текстах: 6. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_CHECKER_TIMEOUT_CANCELLATION_FIX.md` | Trusted Checker: timeout/cancellation — задача №19.1.1; входящих ссылок в tracked текстах: 5. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `TRUSTED_SANDBOX_CHECKER_AUDIT.md` | Trusted Sandbox Checker Audit — задача №17; входящих ссылок в tracked текстах: 1. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `V2-06a-H1-INDEPENDENT-REREVIEW.md` | Trusted Checker v2: Independent H1 Security Re-review — №20.1b-8k; входящих ссылок в tracked текстах: 6. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `V2-06a-H1-SECURITY-REMEDIATION.md` | Trusted Checker v2: H1 Security Remediation — №20.1b-8j; входящих ссылок в tracked текстах: 6. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `V2-06a-H1-SECURITY-REVIEW.md` | V2-06a-H1 — Independent Security Review; входящих ссылок в tracked текстах: 7. | Оставить: исторические пути в integrity/evidence; отдельный план архива. |
| `docker-compose.local.yml` | Host dev ports, DEBUG=True, внешний legacy PostgreSQL volume. | Оставить в корне. |
| `docker-compose.override.yml` | Автоподключаемый dev override: .env и :8081; исключать в production. | Оставить в корне. |
| `docker-compose.prod.yml` | Production env_file и loopback Gateway :8080; не полный Lite release. | Оставить в корне. |
| `docker-compose.yml` | Базовый project, 6 сервисов, healthchecks, platform network/volumes. | Оставить в корне. |
| `manage.py` | Стандартный Django CLI, используется CI/Docker/management commands. | Оставить в корне. |
| `requirements.txt` | Закреплённые Python dependencies; основной и E2E Docker build. | Оставить в корне. |

## Все корневые директории

| Директория | Файлов в базе | Назначение и решение |
|---|---:|---|
| `.github/` | 4 | 4 workflows: hosted CI, Broker/DNS E2E, Trusted Checker и заблокированный manual CD. Оставить. |
| `achievements/` | 49 | Django achievements: модели/API/evaluators, миграции и тесты. Оставить. |
| `assessment/` | 78 | Django assessment: каталог вопросов, экзамены, результаты и тесты. Оставить. |
| `audit_artifacts/` | 9 | Исторические H1 evidence, integrity manifests и воспроизводящие тесты. Оставить. |
| `config/` | 7 | Django settings/urls/wsgi/asgi и Celery configuration. Оставить. |
| `deploy/` | 30 | Runbooks, nginx/systemd/cron examples, read-only audits, isolated DB rehearsal и тесты. Оставить. |
| `docs/` | 86 | Исторические screenshots и сопроводительная документация. Оставить. |
| `experiments/` | 81 | PoC/lab/evidence; часть Python импортируется runtime и копируется Dockerfile. Оставить. |
| `frontend/` | 101 | React/TypeScript/Vite, npm lock, assets и JS tests; Docker frontend stage. Оставить. |
| `react_frontend/` | 10 | Django bridge React views, templates и integration tests. Оставить. |
| `roadmap/` | 17 | Django roadmap projection, actions и tests; связан с sandbox/traineediary. Оставить. |
| `sandbox/` | 138 | Django Ticket Sandbox, management commands, Celery/Docker services и tests. Оставить. |
| `static/` | 7 | Source static assets; collectstatic использует BASE_DIR/static. Оставить. |
| `templates/` | 9 | Общие Django templates; settings.TEMPLATES и app views. Оставить. |
| `terminal/` | 9 | Broker Lite/runtime/PTY code, Dockerfiles; Docker socket trust boundary. Оставить. |
| `traineediary/` | 87 | Django TraineeDiary, миграции, схемы этапов и tests. Оставить. |
| `training_tasks/` | 119 | Учебные task.json/Dockerfile/files/check.sh; loaders, build_task_images и runtime. Оставить. |
| `trusted_checker_live/` | 21 | Live checker/runtime helpers; offline tests и зависимости других checker packages. Оставить. |
| `trusted_checker_network/` | 77 | Native v2 contracts, readback, installer и kernel fixtures; CI. Оставить. |
| `trusted_checker_physical/` | 23 | Physical collector/backend; связан с network/live/runtime. Оставить. |
| `trusted_checker_poc/` | 34 | Isolated PoC Docker runner/target/lifecycle, compose и tests. Оставить. |
| `trusted_checker_runtime/` | 14 | Execution/attestation/provenance layer; live/network/physical используют его. Оставить. |
| `trusted_checker_shadow/` | 19 | Shadow coordination/state/contracts; связан с sandbox и runtime. Оставить. |

## Локальные элементы исходного checkout вне tracked inventory

Просмотрены только имена через Git/каталог, без чтения содержимого. В worktree
они не копировались; никаких удалений/перезаписей пользовательских файлов нет.

| Локальный путь | Назначение / решение |
|---|---|
| `.git/` | Общие Git metadata; новая ветка изолирована через worktree. Не чистить другие ветки/worktrees. |
| `.DS_Store` | Метаданные macOS; игнорируются, не удалялись. |
| `.env`, `.env.prod` | Private runtime settings, возможные credentials; не открывать/не включать в Git/image. |
| `.venv/` | Локальное Python-окружение; использовался только его interpreter/dependencies для тестов worktree. |
| `.vscode/` | Локальные editor settings; оставить, исключить из Git/build context. |
| `backups/` | Локальные резервные копии; оставить без чтения, игнорировать. |
| `demo-roadmap.sqlite3`, `react_test.sqlite3` | Локальные SQLite артефакты; оставить без чтения, исключить из image. |
| `design-references/` | Локальные reference assets; оставить, явно игнорировать в Git/build context. |
| `logs/` | Локальные журналы; оставить, игнорировать. |
| `staticfiles/` | Сгенерированные collectstatic assets; игнорировать, не переносить source. |
| `frontend/node_modules/`, `static/frontend/`, `**/__pycache__/` | Локальные generated dependencies/assets/cache внутри tracked деревьев; не переносить. |
| `.github/workflows/active-server-diagnostics.yml` | Пользовательский untracked workflow; не читался, не копировался, не менялся. |

## Подтверждённые находки

- Удаляемых tracked временных файлов не установлено: SQLite, logs и private env
  уже не tracked. В исходном пользовательском checkout есть игнорируемые локальные
  артефакты; они не копируются в worktree, не читаются и не удаляются.
- `.dockerignore` исключал env и caches, но не SQLite/dumps/media/локальные ключи:
  Dockerfile и E2E driver выполняют `COPY . .`, поэтому gitignore недостаточен.
- `.gitignore` не закрывал DB dumps, SQLite sidecars, root node_modules, coverage,
  private release env и серверные `docker-compose.release.yml`/`docker-compose.lite-pilot.yml`.
- Активные README/ARCHITECTURE/CONTRIBUTING/STAGING_CHECKLIST устарели в описании
  automatic deploy и обязательного force-recreate Gateway. Исправлять только ops-разделы.
- `.env.prod.example` — пример, не доказательство runtime; его Broker=false
  нельзя использовать для восстановления включённого production Lite.
- Помимо четырёх корневых Compose есть `trusted_checker_poc/compose.isolated.yml`
  (только отдельный dedicated daemon, не merge с platform) и
  `experiments/trusted_checker_mvp/django_integration/enablement.compose.example.yml`
  (lab-only observation flags/mounts). Они не входят в release-набор.
- Совпадающие task Dockerfiles и systemctl shims — самостоятельные build contexts.
  Их дедупликация изменит упаковку/контракты заданий; оставить.
- `experiments/` не является удаляемой песочницей: `terminal/broker_v2.py` импортирует
  `experiments.terminal_broker.terminal_broker.prepare_socket_path`, а
  `terminal/Dockerfile.service` явно COPY этот файл. Sandbox observation services
  импортируют `experiments.trusted_checker_mvp.docker_pilot.*`.
- Trusted Checker root reports участвуют в `audit_artifacts/.../baseline.json` и
  `experiments/trusted_checker_mvp/**/integrity.json`. Не переносить/пересчитывать
  исторические манифесты ради косметики.
- Узкий scan tracked текста по private-key headers, GitHub/AWS token formats не
  выявил совпадений. Это не полное secret scanning всей истории.

## Этап A: план и ограничения для этапа B

| Изменение | Основание / зависимости | Риск |
|---|---|---|
| 6 отчётов → docs/reports/{achievements,roadmap}/ | Нет runtime/CI/Docker/management-command потребителей этих путей и нет integrity keys. Incoming только Markdown. Сами отчёты и screenshots сохраняются. | Низкий; проверить старые/новые link targets, вне репозитория ссылки могут требовать обновления. |
| docs/README.md и актуальные ops-ссылки | Единая навигация и устранение противоречивых deploy-инструкций. | Низкий; только Markdown. |
| Уточнить ignore rules | Защитить build context и Git от локальных DB/env/keys; не удалять tracked evidence. | Низкий; проверить contexts и сохранность task fixtures. |
| Additive release/Lite overlays и образец image pins | Не автоподключаются; base/local/prod файлы не менять. Проверять merge настоящим Compose. | Низкий до ручного принятия; перенос production требует reconciliation серверных overrides. |
| Read-only проверка/план релиза | Фиксированные file order/project/profile; никаких up/stop/pull/migrate в исполняемом tool. | Низкий; тесты команд и конфигурации. |
| Удаление | Доказанного безопасного кандидата нет. | Удалений не планируется. |

Не трогать: `manage.py`, Dockerfile, корневые Compose, config/Django app code,
миграции, urlpatterns, templates/static source, Terminal Broker Lite, TraineeDiary,
training_tasks, trusted_checker packages, experiments и audit evidence. Исключение:
добавляются новые deploy/tests и новые opt-in overlays; существующие runtime файлы
остаются byte-identical. Пользовательский untracked diagnostics workflow и другие
ветки/worktrees не изменять. Push/merge/deploy запрещены без отдельного разрешения.

## Технический долг, который остаётся

Архивация integrity-pinned reports; внешние ссылки на 6 перенесённых документов;
отсутствие полного history secret scan; mutable image tags в исходном Compose;
неизвестные серверные overlays; отсутствие healthcheck Scheduler; разделение
Docker socket trust boundary; устаревшие local/legacy/systemd инструкции и monolithic
ops docs требуют отдельных reviewed изменений. Сами системные роли и security
контракты этим аудитом не пересматриваются.
