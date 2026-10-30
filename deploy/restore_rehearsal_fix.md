# Исправление постобработки restore

## Причина остановки

В первоначальном helper шаг restore включал pg_restore, COMMENT ON DATABASE и
ALTER ROLE rehearsal NOSUPERUSER NOCREATEDB NOCREATEROLE. Ошибка pg_restore
обозначалась archive_command_failed; command_failed возникал в последующих psql.

POSTGRES_USER=rehearsal создавал bootstrap-роль кластера с OID 10. PostgreSQL 16
запрещает снимать с неё SUPERUSER: psql exit code 3, SQLSTATE 0A000, DETAIL:
The bootstrap user must have the SUPERUSER attribute. Дефект воспроизведён
на отдельном локальном кластере без backup и прикладных миграций.

stderr направлялся в DEVNULL, stdout удерживался в памяти и не логировался.
restore.log никогда не создавался; исходный текст серверной ошибки утрачен.
Совпадение количеств строк само по себе успешность restore не доказывает.

## Исправление

- initdb создаёт rehearsal_admin. Отдельная rehearsal получает владение
  tp_rehearsal до restore. В режиме reuse она сразу NOSUPERUSER NOCREATEDB
  NOCREATEROLE. pg_restore и приложение используют rehearsal, не bootstrap.
- Проверяются отсутствие bootstrap identity, владение БД и ожидаемые атрибуты.
  Для режима нового backup сохраняется соответствие SUPERUSER исходной роли;
  в режиме reuse у rehearsal он всегда выключен.
- Сохранены --exit-on-error, --single-transaction, --no-owner и --no-privileges.
  Ненулевой код pg_restore блокирует marker, baseline и миграции.
- checks.restore сохраняет status и returncode для owner/toc/data/marker/role_check.
  При ошибке добавляется безопасная category и разрешённый SQLSTATE. psql работает
  с VERBOSITY=sqlstate; сырые stdout/stderr, SQL и пароли в отчёт не попадают.
  restore.log по-прежнему не создаётся.

Исправлен внешний helper. Миграция 0007 и APP_COMMAND сохранены. При подготовке
повторной репетиции использовался уже проверенный образ приложения с исправленным
каталогом; helper передавался отдельно, без перезаписи прежнего пакета.

## Регрессионные проверки

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover \
  -s deploy/tests -p test_database_rehearsal.py

TP_REHEARSAL_POSTGRES_BIN="$(pg_config --bindir)" \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest \
  deploy.tests.test_rehearsal_roles_postgres -v
```

Первая команда выполняет 58 тестов с подставными внешними командами. Вторая —
2 opt-in теста на новых локальных PostgreSQL 16-кластерах через приватные Unix
sockets без TCP: запрет снятия SUPERUSER с bootstrap и успешное выполнение
реального prepare_clone_owner с созданием объекта от обычного владельца.
Без opt-in PostgreSQL-тесты пропускаются. Backup, restore архивов и прикладные
миграции эти тесты не запускают.

## Повторная репетиция и результат

Параметры и границы: [общая инструкция](database_rehearsal.md). Используется
существующий backup с исходным приватным report.json и новая изолированная копия.
Старый контейнер не исправляется и не переиспользуется; при необходимости из его
metadata берётся только immutable ID образа PostgreSQL. Основная PostgreSQL,
предыдущие backup/report и действующие web/worker не изменяются.

На Docker 29 manifest digest и config digest могут различаться. После docker load
используется реально доступный ID из docker image inspect --format '{{.Id}}',
с проверкой OCI revision и платформы. Подмена label старого образа не допускается.

30.10.2026 администратор подтвердил успешную повторную репетицию. Все пять restore
checks прошли; [согласованная сводка](database_rehearsal_2026-10-30.md) не содержит
приватных отчётов, путей пакетов или сведений о пользователях.
