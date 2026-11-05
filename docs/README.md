# Документация Training Platform

Актуальные входные точки остаются в корне: [README](../README.md),
[архитектура](../ARCHITECTURE.md), [разработка](../CONTRIBUTING.md),
[staging checklist](../STAGING_CHECKLIST.md), [changelog](../CHANGELOG.md).

## Эксплуатация и релизы

- [Ручной релиз по сервисам и фиксированный Compose-набор](../deploy/manual_releases.md).
- [Границы CI/CD; автоматический deploy отключён](../deploy/ci_cd.md).
- [Gateway DNS, in-place nginx update и откат](../deploy/nginx/web_dns_rollout.md).
- [Репетиция обновления БД на отдельной копии](../deploy/database_rehearsal.md).
- [Аудит корня, зависимости и план cleanup](repository-audit.md).
- [Итог cleanup и выполненные проверки](repository-cleanup-report.md).

## Исторические отчёты

Отчёты отражают дату/ревизию своего эксперимента, а не текущую production-конфигурацию.
Пути в inline code и командах понимаются от корня репозитория; Markdown-ссылки
разрешаются относительно файла отчёта.

| Область | Отчёты |
|---|---|
| Roadmap | [Backend](reports/roadmap/ROADMAP_BACKEND_FOUNDATION.md), [React](reports/roadmap/ROADMAP_REACT_INTEGRATION.md), [Actions/navigation](reports/roadmap/ROADMAP_ACTIONS_NAVIGATION.md) |
| Achievements | [Аудит](reports/achievements/ACHIEVEMENT_SYSTEM_AUDIT.md), [Backend](reports/achievements/ACHIEVEMENT_BACKEND_FOUNDATION.md), [Trophy Room](reports/achievements/TROPHY_ROOM_REACT_INTEGRATION.md) |
| Terminal | [Lite](../TERMINAL_BROKER_LITE.md), [v2](../TERMINAL_BROKER_V2.md) — сохранены на прежних путях |
| TraineeDiary | [Схемы этапов](../TRAINEEDIARY_STAGE_SCHEMES.md), [Управление достижениями](../TRAINEEDIARY_ACHIEVEMENT_MANAGEMENT.md) — сохранены |
| Trusted Checker | Root `TRUSTED_CHECKER_*.md`, `TRUSTED_SANDBOX_CHECKER_AUDIT.md`, `V2-06a-H1-*.md` — пути закреплены историческими integrity manifests; см. полный [перечень](repository-audit.md) |

Директории screenshots и evidence не перемещены. Внешние ссылки на шесть прежних
root report URLs нужно обновлять отдельно; старая версия доступна по Git commit.
