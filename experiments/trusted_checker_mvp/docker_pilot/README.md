# Observation-only Docker adapter

**Default OFF. DOCKER PILOT NOT EXECUTED.** В этой задаче пользователь разрешил
только offline adapter и fake SDK tests. Не запускать Dockerfile/network profile
как разрешение изменять текущий Docker host.

Из repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest experiments.trusted_checker_mvp.docker_pilot.test_pilot -v
```

25 tests используют in-memory FakeAPI/FakeAttach/FakeTCP. Установленный Docker
SDK 7.1.0 используется для `HostConfig` serialization без подключения к daemon.
Ни Docker CLI, ни APIClient constructor, ни `docker.from_env()` tests не вызывают.

`DockerPilot(api, policy, read_attempt, artifact_dir, enabled=False)` принимает:

- выделенный, явно созданный доверенным orchestrator **local Unix** Docker
  APIClient с timeout; никакого discovery/default socket/SSH/TCP fallback;
- `Policy` с exact daemon/network IDs, scope UUID, узкой RFC1918 subnet и
  immutable local image IDs вида `sha256:<64 hex>` для target и verifier;
- `read_attempt(attempt_id)`: bounded доверенное чтение авторизованного текущего
  pending execution. Возвращает `Execution` с user/attempt/environment UUID,
  настоящим `TechnicalCheckExecution.run_id`/ordinal и runtime snapshot.
  DTO сам по себе не удостоверяет authorization. Django source здесь не подключён;
- private host artifact directory, owned текущим UID, mode 0700, с доверенными
  ancestors, не доступный trainee/verifier. Один и тот же каталог для всех
  adapter instances этого pilot. Результат не импортируется обратно из файла.

Метод `observe(attempt_id)` не принимает URL, port, image или command. HTTP:
fixed GET `/`, numeric inspected target IP, **8080**, status 200, exact body
из Stage 1 verifier. `worker.py` загружается из pinned read-only image и
переиспользует неизменённый `verifier.probe`.

`Dockerfile` требует approved `BASE_IMAGE` по registry digest; build context —
`experiments/trusted_checker_mvp`. Он копирует только worker.py и verifier.py,
не устанавливает SDK в verifier. После отдельно разрешённого build его local
image ID закрепляется в Policy. Build/pull/create/start этой задачей не выполнялись.

`network-profile.json` — **Engine API template**, не SDK kwargs. Scope UUID и
непересекающаяся subnet выбираются оператором. Требуются supported `isolated`
gateway mode, internal bridge, IPv6 OFF, точные labels и один task на network.
Platform network не подходит. Provision/retirement — отдельно разрешённые
операции orchestrator: записать full созданный network ID, удалить свою target
среду по её отдельной authority, проверить пустоту своей сети, затем удалить
только этот exact network ID. Adapter удаляет только собственный verifier,
не target/network и не делает prune/adoption.

`<run_id>.json` атомарно создаётся с O_EXCL до Docker effects. Существующий file
(даже in-progress/partial после crash) запрещает повторный dispatch этого run.
Это простой protected diagnostic artifact/job claim, не новый подписанный
receipt или crash-recovery framework. Не удалять claim для auto retry. Другой
artifact directory/удаление файла/потеря storage не покрываются этим replay fence;
для Django integration нужен existing DB execution claim/unique constraint.
Final JSON записывается через private tempfile/fsync/replace: storage failure
сохраняет исходный unknown claim, а не частично опубликованный match.

Результат — frozen `Observation`, только `http=matched|mismatch|unknown` и finite
reason. Binding присутствует после проверенного metadata round trip, это Docker
control-plane identity, не OS attestation. `bind/process/network_isolation` всегда
unverified, task verdict unknown либо failed, academic_pass всегда false.
Нет Django imports, CheckRun/Ledger/completion/achievement writes, target exec,
native v2/H1/H2 integration. Historical observation не доказывает будущее состояние.

[Отчёт](../../../TRUSTED_CHECKER_MVP_DOCKER_PILOT.md),
[tests.txt](tests.txt), [fake-observation.json](fake-observation.json),
[integrity.json](integrity.json).
