# Trusted Checker PoC: NetworkID validation fix

Ветка `feature/roadmap-react`. Исправлен описанный пользователем случай Docker Engine 29.9.1: после create сетевые operational fields ещё пусты. Локально реальный Docker и VDS не использовались.

## Изменения

- `docker_adapter.py`: общие security invariants вынесены в `_runner_config_valid`; lifecycle-проверки явно вызываются с `pre_start`, `post_start`, `finished`.
- До старта разрешены пустые EndpointID/IPAddress и пустой либо ожидаемый NetworkID только при `Status=created`, `Running=False`, PID0, RestartCount0 и нулевом StartedAt. NetworkMode обязан быть полным approved ID. В mapping допускается ровно одна сеть с ключом approved ID либо именем, полученным через inspect этого ID. Произвольный alias и дополнительная сеть отклоняются.
- Сразу после start и reload обязательны `running`, ненулевой PID, ненулевой StartedAt, точный NetworkID, полноценный EndpointID и RFC1918 IPv4. Затем сохраняется снимок подключения, связанный с container ID и StartedAt.
- После wait сохраняются все security checks, exact NetworkID и тот же запуск. Пустые EndpointID/IPAddress допустимы только для exited после ранее наблюдавшегося live endpoint; пустой/чужой NetworkID отклоняется всегда. Это учитывает cleanup operational fields, описанный в [Moby releaseNetwork/cleanOperationalData](https://github.com/moby/moby/blob/master/daemon/container_operations.go). Этот источник не является проверкой конкретного daemon на VDS.
- `broker.py`: integrity failure снимает отметку `config_verified` в возвращаемом результате. HTTP outcome не принимается; broker закрывает run как unknown и выполняет прежний exact-ID cleanup, сверяя image/role/scope/run. Широкого удаления нет.
- Оба Dockerfile передают `"$PYTHON_BASE"` как аргумент `python -c`, читаемый через `sys.argv[1]`. Проверка требует `@sha256:<64 hex>`, отклоняет whitespace и не зависит от Python assertions/optimization.

Image ID, user, entrypoint/command, readonly rootfs, capabilities, namespaces, mounts/tmpfs, resources, labels и environment продолжают проверяться во всех фазах. Sandbox/Ledger/achievements/production Compose, отчёты №17/18 и PNG не изменены. Платина не включалась.

## Проверки

```sh
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

**50 тестов, OK, 2,223 с**. Лог: `/tmp/task18-network-validation-tests.log`.

Добавлены lifecycle, approved name/ID mapping, неправильная/дополнительная сеть, missing endpoint, повторный запуск и подмена security config; broker+SDK mock test подтверждает unknown и exact-ID cleanup до чтения HTTP outcome при post-start failure. Dockerfile shell checks выполнены настоящим `/bin/sh` с корректными/некорректными аргументами и `PYTHONOPTIMIZE=1`.

Все Docker operations — mocks/fakes. Images не собирались, Docker/VDS runtime не проверялся. Общие imports проекта не менялись, Django/frontend suite не запускались. После успешных тестов проверены whitespace, локальные ссылки и SHA256 исходных файлов.

Ограничение: если runner уже завершился до первого post-start inspect и live endpoint не был наблюдён, результат останется unknown с exact cleanup. Нельзя заменять такое наблюдение пустым NetworkID. Для гарантированного наблюдения очень коротких запусков понадобится отдельный start/validation handshake; он не добавлялся в этот fix.

## Обновление на отдельной VDS

Подготовлен архив `/tmp/trusted-checker-networkid-fix.tar.gz`. Внутри только семь файлов:

```text
trusted_checker_poc/docker_adapter.py
trusted_checker_poc/broker.py
trusted_checker_poc/images/runner/Dockerfile
trusted_checker_poc/images/target/Dockerfile
trusted_checker_poc/tests/test_docker_contract.py
trusted_checker_poc/tests/test_dockerfiles.py
TRUSTED_CHECKER_NETWORK_VALIDATION_FIX.md
```

1. Завершите активные **PoC** runs и остановите только локальный PoC harness/broker. Скопируйте архив на уже проверенную изолированную VDS, сравните SHA256 локального и полученного архива (`shasum -a 256` / `sha256sum`). Registry settings, state SQLite и VDS-specific harness в архив не входят.
2. На VDS задайте `POC_CHECKOUT` — путь к существующему PoC checkout. Сохраните копии заменяемых файлов, проверьте состав архива и распакуйте:

```sh
cd "$POC_CHECKOUT"
POC_FIX_BACKUP=$(mktemp -d /tmp/tc-network-fix-backup.XXXXXX)
cp --parents trusted_checker_poc/docker_adapter.py trusted_checker_poc/broker.py \
  trusted_checker_poc/images/runner/Dockerfile trusted_checker_poc/images/target/Dockerfile \
  trusted_checker_poc/tests/test_docker_contract.py "$POC_FIX_BACKUP/"
# Если test_dockerfiles.py уже существует, сохраните также его перед заменой.
tar -tzf /tmp/trusted-checker-networkid-fix.tar.gz
tar -xzf /tmp/trusted-checker-networkid-fix.tar.gz --no-same-owner -C "$POC_CHECKOUT"
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t . -v
```

3. Для проверки исправленного build ARG пересоберите оба **PoC** images только на dedicated daemon. `POC_DOCKER_CONTEXT` должен указывать на проверенный isolated daemon; `POC_PYTHON_BASE` — ранее одобренный реальный digest-pinned base, не тестовый fake digest:

```sh
POC_FIX_BUILD=$(mktemp -d /tmp/tc-network-fix-build.XXXXXX)
docker --context "$POC_DOCKER_CONTEXT" build \
  --build-arg "PYTHON_BASE=$POC_PYTHON_BASE" \
  --iidfile "$POC_FIX_BUILD/runner.iid" \
  -f trusted_checker_poc/images/runner/Dockerfile trusted_checker_poc/
docker --context "$POC_DOCKER_CONTEXT" build \
  --build-arg "PYTHON_BASE=$POC_PYTHON_BASE" \
  --iidfile "$POC_FIX_BUILD/target.iid" \
  -f trusted_checker_poc/images/target/Dockerfile trusted_checker_poc/
cat "$POC_FIX_BUILD/runner.iid" "$POC_FIX_BUILD/target.iid"
```

4. Укажите полученный runner image ID в trusted configuration существующего VDS harness (`Registry(runner_image_id=...)`), запустите его новым Python-процессом. При пересоздании synthetic target используйте новую generation и enrollment с его полным ID/StartedAt. Production Compose не запускайте.
5. Выдайте **новый run_id**: прежний terminal unknown корректно останется в durable journal и повторно не выполнится. Проверьте localhost-only → failed, исправленный bind → passed; сохраните inspect до/после и результат нового run. Не удаляйте старые receipts и не снимайте вручную неразрешённые leases.

Удалённое обновление/сборка/запуски здесь не выполнялись. Commit, push и deploy не выполнялись.
