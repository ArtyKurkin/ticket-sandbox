# Завершение Terminal Broker 2.0 Lite

План для настоящего staging после отдельного разрешения. Лабораторная VDS
`ticket-sandbox-lab` staging не является. Флаг до разрешения — `false`.

## Принятая модель

Root стажёра ограничен task-контейнером. Защита от намеренно враждебного root
внутри задания не требуется. Worker и Broker — доверенные компоненты с доступом
к Docker daemon; общий daemon допустим в этой модели.

Task не получает Docker socket, host bind mounts или privileged. Новый ttyd
получает только отдельный socket volume Broker в режиме read-only. Его rootfs
read-only, capabilities сброшены. У task сохраняются необходимые заданиям
capabilities, writable rootfs, существующие memory/PID limits и init.
Не применять к task универсальные `cap_drop: ALL` или read-only rootfs:
это может сломать службы, права файлов и диагностику учебных задач.

## Минимальная конфигурация

- Использовать `docker-compose.yml` вместе с `docker-compose.prod.yml`;
  не подключать local override с опубликованными PostgreSQL/Redis/Django.
- `DEBUG=False`, `TERMINAL_GATEWAY_ENABLED=true`,
  `TERMINAL_NETWORK_MODE=docker_network`,
  `TERMINAL_DOCKER_NETWORK=training-platform-runtime`,
  `SANDBOX_HTTP_OBSERVATION_ENABLED=false` для штатного зачёта задач.
- `TERMINAL_BROKER_ENABLED=false` у web, worker и terminal_scheduler
  до согласованного переключения. Флаг глобальный, cohort allowlist отсутствует.
- Docker API доступен только доверенным операторам, worker и Broker.
  Не публиковать незащищённый TCP Docker API; `DOCKER_GID` соответствует socket.
- Внешний доступ — через HTTPS nginx; Compose gateway остаётся на
  `127.0.0.1:8080`. Не публиковать порты task, ttyd, Django, Redis и PostgreSQL.
- Обе nginx-конфигурации блокируют публичные `/terminal-auth/` и
  `/terminal-broker-auth/`. Не выдавать браузеру внутренние auth headers.
- Broker обращается напрямую к
  `http://web:8000/terminal-broker-auth/`; имя `web` добавить в `ALLOWED_HOSTS`.
  Исключение HTTPS redirect действует только для этого bearer-authenticated
  endpoint в приватной Docker-сети. Остальной сайт сохраняет HTTPS redirect.
- На daemon должны быть подготовлены образы из `terminal/Dockerfile.service`
  и `terminal/Dockerfile.broker`, а также актуальные 20 task images.
  Фиксировать image ID перед пилотом. Одних `build web worker` недостаточно.
- Запустить ровно один `terminal_scheduler` из профиля `terminal-broker`.
  Текущий staging workflow автоматически его не запускает и образы Broker
  не собирает; подготовить их отдельным разрешённым шагом перед включением.

## Пилот

1. Подтвердить настоящий staging, версии Linux/Docker, backup БД и исходные
   image ID. Подготовить текущий код и аддитивные миграции 0035/0036 с флагом
   `false`. Существующие task-контейнеры не пересоздавать.
2. Выделить 2–3 новых тестовых попытки. На окно пилота организационно ограничить
   новые start/reset этими попытками: переключатель глобальный. Дождаться
   завершения уже выполняющихся start/reset/check и проверить незавершённые
   requested start/reset в ledger; не смешивать разные версии
   кода и значения флага у web/worker/scheduler.
3. После явного разрешения согласованно включить флаг у трёх сервисов.
   Переключение само не пересоздаёт старые задания. Старые legacy-терминалы
   сохраняют прежний режим; переход конкретной старой попытки в Lite возможен
   при явном restart, который по смыслу удаляет её прежнее окружение.
4. Для `candidate/single-file-permission`, `l1/service-bind-localhost` и
   `l1/nginx-upstream-wrong-port`: исходный check не проходит; терминал позволяет
   исправить проблему; итоговый check проходит штатным Django lifecycle.
5. До итогового зачёта проверить две вкладки, resize и Ctrl+C. Закрытие одной
   вкладки завершает её интерактивный Exec; другая вкладка и фоновые службы
   задания продолжают работать. Переподключение сохраняет исправления.
6. На отдельной незачтённой попытке сделать restart: старый доступ отозван,
   старый task удалён, опубликованы новые ID/generation и исходная неисправность.
   Затем исправить и пройти проверку. После отправки ответа проверить cleanup,
   историческую попытку и повторное прохождение без потери прежнего зачёта.
7. Проверить отсутствие зависших операций, успешное reconciliation и сохранение
   фоновых служб после обычного переподключения. Остановить расширение пилота
   при невыполненном cleanup или повторяющихся ошибках lease/readiness.
   Crash/duplicate-delivery уже покрываются автоматическими тестами;
   дополнительные инъекции сбоев на staging для этого пилота не нужны.

## Откат

1. Закрыть новые start/reset и дождаться текущих операций/проверок. Для срочного
   отзыва сессий согласованно вернуть флаг `false`; это не удаляет ресурсы.
2. Сохранённым кодом Lite выполнить `cleanup_attempt_environment` только для
   явного списка пилотных attempt ID. При pending cleanup дождаться повторов
   и вручную инициировать штатное reconciliation при необходимости: после
   выключения флага расписание beat пустое. Проверить удаление старых task,
   ttyd и Broker по их ID; не очищать все задания по возрасту или префиксу.
3. Сохранить ledger, PostgreSQL и state volumes. Миграции назад не откатывать.
   Прежний образ приложения возвращать только после cleanup и проверки его
   совместимости со схемой. Никаких `down -v` и глобального `prune`.
4. Не запускать очищенную Lite-попытку через legacy-код и не обнулять вручную
   generation/checkpoint. Откат флага — пауза Lite, а не преобразование его
   окружений обратно в legacy. Legacy создаёт ttyd с Docker socket; новые
   терминальные окружения при выключенном флаге не запускать в принятой модели.

Остаточные риски: доверенные worker/Broker имеют полный Docker socket, общий
daemon и ядро; task-root не является защитной границей от целевых атак; отказ
Django lease закрывает терминалы; отсоединённые фоновые службы намеренно
сохраняются до restart/cleanup; state volumes сохраняются и требуют последующей
адресной очистки. Отдельные
VM, новые cgroup-механизмы и переписывание Broker для этого пилота не требуются.
