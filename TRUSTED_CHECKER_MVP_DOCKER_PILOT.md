# Trusted Checker MVP — Observation-only Docker Pilot

22 октября 2026 · Git HEAD `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`MVP DOCKER ADAPTER OFFLINE READY`. `DOCKER PILOT NOT EXECUTED`.**
Реализован default-OFF adapter для одного `l1/service-bind-localhost`: host-owned
execution → full-ID Docker inspect → одноразовый verifier → одна fixed HTTP
проба → scoped runtime recheck/cleanup → bounded frozen observation/artifact.
**25 offline tests прошли**; реальный daemon, image build и containers не запускались.
Пользователь явно выбрал «Только offline adapter и fake SDK tests».

`MVP DOCKER PILOT READY` не присваивается. `bind`, `process`, `network_isolation`
остаются `unverified`; `academic_pass=false`, task verdict только unknown/failed.
H1/H2, RR01–RR05 и physical gates неизменны. Production Django writers не подключены.

## 1. Реализованные файлы и scope

| Файл | Что реализовано |
|---|---|
| [adapter.py](experiments/trusted_checker_mvp/docker_pilot/adapter.py) | Policy/Execution/Observation, real Docker SDK calls, metadata fences, attach bounds, scoped worker removal, protected artifact |
| [worker.py](experiments/trusted_checker_mvp/docker_pilot/worker.py) | Fixed one-shot image entry, bounded strict request/result, вызов прежнего HTTP probe |
| [Dockerfile](experiments/trusted_checker_mvp/docker_pilot/Dockerfile) | Non-root verifier image recipe, без Django/SDK/check.sh и installation hooks |
| [network-profile.json](experiments/trusted_checker_mvp/docker_pilot/network-profile.json) | Template отдельной internal isolated bridge, не platform network |
| [test_pilot.py](experiments/trusted_checker_mvp/docker_pilot/test_pilot.py) | 25 fake SDK/transport tests, real SDK HostConfig serialization, fake TCP через настоящий HTTP parser |
| [README.md](experiments/trusted_checker_mvp/docker_pilot/README.md) | Usage/activation prerequisites, ownership/replay scope и network lifecycle |
| [tests.txt](experiments/trusted_checker_mvp/docker_pilot/tests.txt), [fake-observation.json](experiments/trusted_checker_mvp/docker_pilot/fake-observation.json), [integrity.json](experiments/trusted_checker_mvp/docker_pilot/integrity.json) | Offline evidence, явный execution mode, pre/post hashes |
| Этот report | Implemented boundary, ограничения, следующий Django integration slice |

Прежние [verifier.py](experiments/trusted_checker_mvp/verifier.py), local PoC,
его 13 tests/evidence и [simplification report](TRUSTED_CHECKER_MVP_SIMPLIFICATION.md)
сохранены byte-for-byte. Worker переиспользует именно `verifier.probe`;
нет копии task checker или новой registry произвольных заданий.

Adapter использует установленный Docker SDK **7.1.0**. Его real low-level calls:
`info`, `inspect_container`, `inspect_network`, `inspect_image`,
`create_host_config`, `create_container`, `attach_socket`, `start`, `wait`,
`remove_container`. Low-level API не делает здесь автоматический pull/build.
Clients не создаются автоматически, `from_env`, context discovery и SSH отсутствуют.
[Docker SDK API](https://docker-py.readthedocs.io/en/stable/api.html).

Три простых frozen records — Policy, Execution, Observation. Нет новой authority,
FD escrow, helper bootstrap, signing или собственного IPC protocol. Attach reader
понимает **стандартные Docker 8-byte stdout/stderr headers** только для cap до
allocation body. Это transport Docker, не продолжение H1.

## 2. Вход от доверенного orchestrator

`DockerPilot(api, policy, read_attempt, artifact_dir, enabled=False)` ничего
не запускает в constructor. Disabled `observe` не вызывает source, Docker или
artifact I/O. `enabled` задаёт host code, не trainee HTTP request.

Единственный метод запуска: `observe(attempt_id)`. Он не принимает IP/URL/port,
image, command, script, stdout или готовый result. Требуется exact positive int.

`read_attempt(attempt_id)` — **trusted bounded read port**, а не принимаемый JSON.
Его обязанность: авторизовать user/task ownership, выбрать текущую environment
и именно pending execution из существующего Django execution lifecycle.
Возвращаемый frozen `Execution` содержит:

- `attempt_id`, `user_id`, `environment_uuid`;
- настоящий `TechnicalCheckExecution.run_id` и `ordinal`;
- full 64-hex `container_id`, exact `daemon_id`;
- `started_at`, `restart_count`, Docker `pid`;
- full `network_id`, `endpoint_id`, numeric IPv4.

В этом этапе **нет Django source implementation/DB reads**. В tests source
явно synthetic. Нельзя считать DTO, supplied boolean или echoed UUID доказательством
authorization; это контракт зависимости orchestrator. В production источник должен
повторно читать актуальные данные, а не всегда возвращать старый captured object.
Конкретный read adapter к существующим models — следующий маленький integration step.

Policy задаётся оператором: daemon ID, network ID, scope UUID, узкая RFC1918
subnet (не более 64 addresses), immutable target/verifier image IDs
`sha256:<64 hex>`. Это **local Docker image IDs**, не выдуманные registry manifest
digests. Dockerfile отдельно требует approved base по registry digest; его
build/source approval и полученный image ID должны быть закреплены до real pilot.
Ни один настоящий image digest в этом offline run не измерялся.

## 3. Порядок одной проверки и container identity

1. Прочитать authorised current Execution; проверить types, UUID/full IDs,
   policy daemon/network/subnet binding. Создать fresh `execution_uuid` на host.
2. До Docker effects создать private `<run_id>.json` через `O_EXCL|O_NOFOLLOW`,
   mode 0600; записать in-progress unknown и execution metadata. Existing file
   даёт replay, без подключения к worker другой попытки.
3. Сравнить `api.info().ID` с pinned daemon. Target всегда inspect по **full ID**.
   Проверить approved image ID, Running/Status, StartedAt/RestartCount/Pid,
   отсутствие paused/restarting/dead/OOM state и safety profile.
4. Проверить host-only target labels: task/queue/attempt, scope, environment.
   У target должна быть ровно одна network; её full ID, endpoint ID и IP должны
   совпасть с Execution и network inspect. Старое повторяемое Docker имя не
   используется для выбора target.
5. Inspect approved verifier image; отвергнуть declared volumes и loader/Python
   environment overrides. Создать verifier с fixed profile; проверить фактический
   inspect config, exact returned ID, labels/name/image/env до запуска.
6. Перечитать execution. Подключить **owned stdout/stderr attach до start**,
   запустить worker по full ID. Worker делает один GET `/` на inspected IP:8080.
7. Прочитать bounded frames до EOF, потребовать empty stderr, wait status 0 и
   inspected exited/ExitCode 0; повторно проверить worker ID/profile. Exit 0 сам
   по себе ничего не засчитывает. Проверить complete JSON, full echoed request,
   fresh UUID и допустимую пару http/reason.
8. Повторить target/network/daemon и execution checks; закрыть attach и удалить
   **только own verifier**; подтвердить отсутствие worker по тому же full ID.
9. Для validated binding ещё раз проверить target/network/daemon/source после
   cleanup, deadline, записать bounded observation. Если artifact write уводит за
   budget, сохранить/вернуть unknown timeout. Результат — frozen object.

`binding` присутствует только после успешного metadata round trip, и очищается
при stale/final cleanup failure. Это independent **Docker control-plane metadata**,
не nsfs/PID/OS attestation и не доказательство real packet isolation.

Любая смена Start/PID/restart, environment UUID, run/ordinal, target ID,
network/endpoint/IP или daemon даёт unknown. Target NotFound не превращается
в поиск по старому имени, empty list или подтверждённый отрицательный service state.
Прозрачной замены endpoint, второго target и fallback exec нет.

## 4. Точный verifier launch profile

| Поле | Значение |
|---|---|
| Image | Только configured immutable `sha256:<64 hex>`; inspect Id обязан совпасть |
| Entrypoint | `/usr/local/bin/python -I -S -B /checker/worker.py` |
| Command / stdin / tty | `[]`, closed stdin, false tty |
| User | `65532:65532` |
| Root filesystem | read-only; никаких volumes/binds/tmpfs/secrets/host proc mounts |
| Capabilities / security | cap_drop ALL, cap_add [], privileged false, no-new-privileges |
| PID / IPC | Private/default PID namespace, private IPC; нет host PID/net/UTS mode |
| Network | Только configured dedicated network ID; нет published ports/PublishAllPorts |
| Resources | RAM 64 MiB, PIDs 16, NanoCpus 250000000 (0.25 CPU) |
| Restart / cleanup | restart=no, auto_remove=false; adapter inspect/wait/remove own ID |
| Logging | Docker log driver `none`; данные только через private attach |
| Environment | Approved image env + LANG=C, LC_ALL=C, TC_MVP_REQUEST; без наследования host env. LD_/DYLD_/PYTHONPATH/PYTHONHOME overrides отвергаются |

Image содержит только fixed worker и неизменённый stdlib HTTP probe. Worker
проверяет request schema, вызывает тот же `verifier.probe(ip, 8080)` и возвращает
JSON. Никакого curl/ip/ss, `/task/check.sh`, shell, `exec_run`, user argv или
произвольного пути. Request env читается только этим worker; target его не получает.

Expected body: `APP OK: customer service is running\n`, status 200, path `/`.
Проба raw TCP, без DNS/proxy/redirects. Сохраняется fixed Host header Stage 1
`127.0.0.1:8080`; для данного app он не влияет на routing. Это не универсальный
virtual-host verifier. Target response — untrusted HTTP, не verifier result.

Target тоже должен удовлетворять pilot profile: approved image, cap_drop ALL,
NNP, без mounts/socket/privileged/host namespaces/published ports, одной network.
Обычный production Sandbox launch этому профилю **пока не соответствует** и
автоматически не принимается. Adapter не «исправляет» его capabilities или network.

## 5. Сеть и lifecycle

Требуется заранее подготовленная **отдельная network одного disposable attempt**:
bridge, internal=true, IPv6 OFF, `gateway_mode_ipv4=isolated`, exact scope labels,
имя `tc-mvp-<scope UUID>`, approved nonoverlapping subnet. Template расположен в
[network-profile.json](experiments/trusted_checker_mvp/docker_pilot/network-profile.json).
Его placeholder/subnet — operator template, не выполненная конфигурация.

Adapter inspect проверяет network ID/name/options/labels/IPAM и actual membership.
До запуска допустим только pinned target; во время проверки — target и собственный
worker; после cleanup — снова target. DB/Redis/terminal/another attempt/worker
другого check в этой сети приводят к unknown. Platform network не используется.

`isolated` выбран потому, что обычная internal bridge может иметь host bridge
address. Docker документирует отсутствие адреса на bridge в isolated mode;
нужна поддерживающая его Engine build. Это уменьшает доступную поверхность, но
**не является пройденным negative isolation test**.
[Docker gateway modes](https://docs.docker.com/engine/network/port-publishing/#gateway-modes).

Lifecycle разделён просто:

1. Только отдельно разрешённый orchestrator/operator создаёт dedicated network,
   сохраняет full ID и scope; target provisioned в ней по своей отдельной authority.
   Нельзя adopt существующую platform/v2/lab network по похожему имени.
2. Adapter создаёт/удаляет только собственный краткоживущий verifier. Network
   provisioning, target install/reset и получение чужих ресурсов не его API.
3. После закрытия pilot operator сначала завершает свою disposable target среду,
   проверяет matching scope и пустоту сети, затем удаляет **точный созданный ID**.
   Никаких prune, cleanup all или изменения host firewall/route/sysctl командами.

Эти lifecycle operations **не выполнялись**. Docker network creation сама имеет
обычные host networking effects; она потребует отдельного разрешённого run.

Worker code выполняет только исходящий probe к fixed target:8080 и не слушает
control port. Между двумя endpoints нет отдельной kernel ACL «только TCP 8080»;
не заявляется confinement compromised verifier code. Approved worker image,
orchestrator и Docker daemon — TCB. Реальные task → host/control/DB/terminal
denials пока не измерены; `network_isolation=unverified` сохраняется без override.

## 6. Bound, completion и owned cleanup

| Bound | Проверка |
|---|---|
| Worker request | ≤4096 bytes, exact schema/types/UUIDs, duplicate JSON keys denied |
| HTTP | Существующие 4096 header / 256 body bytes, одна проба, общий deadline 0.6s |
| stdout / stderr | 4096 / 1024 bytes aggregate, до buffering следующего Docker frame; stderr должен быть empty |
| Attach | Не более 64 Docker frames, read chunks ≤512 bytes, malformed header/partial frame/EOF/invalid stream → unknown |
| Capture | Nominal absolute monotonic fence 5s; API socket timeout min(1s, remaining); attach select использует remaining budget |
| Cleanup | Отдельные nominal 2s для inspect/remove/absence check; не расширяют evidence deadline |
| Diagnostic artifact | ≤8192 bytes final JSON, mode 0600, private owner-only directory; no raw HTTP/stderr/exception text |

Проверена source SDK 7.1.0: обычный streaming logs helper отключает socket timeout.
Поэтому здесь **не используется** блокирующий logs generator; `attach_socket` даёт
стандартный selectable Unix socket-like transport, reader проверяет length header
до allocation и требует EOF/exit отдельно.
[SDK attach_socket](https://docker-py.readthedocs.io/en/stable/api.html#docker.api.container.ContainerApiMixin.attach_socket).

Create response может потеряться. Name `tc-mvp-check-<run_id>` разрешён **только
для recovery собственной попытки create**: найденный object должен иметь exact
fresh execution UUID/run/scope/role, имя и image; затем используется full ID.
Сходство имени или один run ID не дают права удалить foreign worker.
Полученный ID никогда не может быть target ID. При уже известном worker ID
inspect response обязан возвращать тот же ID.

При timeout/error cleanup выполняется стандартным force-remove own verifier,
`v=false`, затем inspect NotFound. Target/network не удаляются. Неизвестный
cleanup → unknown cleanup_unknown, binding не выдаётся. Lost create + NotFound
не выдаётся за proof отсутствия позднего create; нет retry/adoption. Чужие labels
или другой ID закрывают cleanup authority, оставшийся runtime требует operator review.

Bounds не являются hard real-time гарантиями Python scheduler, Unix connect,
trusted read callback, SDK metadata JSON allocation или fsync. API timeout —
стандартный requests/SDK bound, не доказательство process death при любом OS
stall. Caller обязан ограничивать DB reads и job runtime стандартными средствами.
Supervisor crash/daemon failure/descendants не аттестованы fake tests; автоматический
restart/recovery framework здесь не создан. Непрерывное состояние не заявляется.

## 7. Replay, concurrency и protected observation storage

Private artifact directory должен принадлежать orchestrator UID, иметь mode
0700 и доверенные ancestors, не быть mounted в trainee/verifier. Все instances
pilot используют **один configured directory**. Filename — canonical Ledger run
UUID, create — O_EXCL/O_NOFOLLOW, mode 0600. Claim записывается до Docker effects.

Второй instance для того же run получает replay до SDK calls и не очищает active
worker первого. Concurrent entry одного instance получает busy. На новый
execution нужен действительно новый pending Ledger run от orchestrator; adapter
сам его не создаёт и не заканчивает. После unknown нет автоматического нового run.

После process interruption in-progress/partial file остаётся conservative claim;
он не становится valid result. Simple file claim не заменяет Django transaction,
не покрывает другой artifact_dir, удаление файла trusted admin, storage loss или
power-failure durability. Для real Django integration single-use claim должен
опираться на existing DB execution identity/unique constraint. Это один обычный
job artifact, не новый H1 journal/IPC/ownership framework.

Final diagnostic JSON публикуется через private tempfile/fsync/atomic replace.
Ошибка записи сохраняет in-progress unknown claim; частично записанный match
не подменяет claim. Tmp-файлы после crash не принимаются как results.

Result channel — owned Docker attach. Echoed request и UUID проверяют correlation,
**не IPC authentication или identity из самого JSON**. Pure decoder способен
разобрать структурно правильный JSON; в adapter нет API submit/import-result,
принимающего его от trainee. Metadata/env/code/result transport защищает trusted
orchestrator/daemon. Их compromise находится за границей этого MVP.

Observation — frozen dataclass с deeply immutable Execution и primitive fields.
`bind/process/network_isolation` derived init=False unverified;
`academic_pass` derived init=False false; verdict derived unknown либо failed.
Нет перехода в CheckRun/PASSED, technical_passed_at, Ledger finish, achievements,
Roadmap или mentor review. Artifact — protected diagnostic, **не академическое evidence**.

## 8. Offline tests и HTTP evidence

Финальный run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest experiments.trusted_checker_mvp.docker_pilot.test_pilot -v
```

**25 tests, OK, 0.086s, 0 failures/errors/skips, exit 0; ResourceWarning отсутствуют.**
Лог: [tests.txt](experiments/trusted_checker_mvp/docker_pilot/tests.txt).
Часть cases параметризована; subcases не пересчитаны в самостоятельные tests.

| Группа | Подтверждённое offline поведение |
|---|---|
| Default OFF / authorization | Нет source/SDK/artifact effects при disabled; отсутствующая authorised record блокирует Docker |
| Fixed HTTP positive/body/status | Worker вызывает именно прежний probe на pinned IP:8080; fake TCP через реальный HTTP parser даёт match на 200+exact body, mismatch на 503/wrong body/готовый result JSON |
| Script/tools spoof | Fake trainee check.sh/curl/ip не читаются/не запускаются; fake worker mismatch остаётся mismatch. Это не выполненная модификация реального container |
| Target unavailable / timeout | NotFound не запускает worker; request/stream timeout даёт unknown и owned cleanup |
| Restart/reset/runtime | RestartCount/StartedAt/Pid/endpoint/IP changes отбрасывают valid worker reply |
| Execution identity | Изменения run/ordinal/environment/container и попытка second attempt adopt target не принимаются |
| Network/profile | Platform name, noninternal/options drift, extra peer, socket mount, NET_ADMIN отвергаются до launch |
| Replay/concurrency | Persistent same-run claim запрещает redispatch; concurrent same-instance busy; другой instance не касается active worker первого |
| Verifier output | Malformed/truncated/oversized Docker stream, stderr, forged fresh UUID не дают match |
| Cleanup/final fence | Lost create response scoped recovery; foreign labels/ID не удаляются; remove failure unknown; restart during cleanup и late artifact write не публикуют match; fsync failure сохраняет unknown claim |
| Interruption | Modeled KeyboardInterrupt на start предпринимает owned cleanup, closes artifact и re-raises; claim блокирует новое выполнение |
| Writers | Нет imports Django/Sandbox/native v2, exec_run/from_env; immutable academic flag нельзя заменить через dataclass replace |

Fake API моделирует SDK responses/transport, selector заменён in-memory ready
function; fake TCP не открывает socket. Использован настоящий SDK `HostConfig`
serializer, **не реальные create/attach/start/remove**. Positive stream fake SDK
является synthetic worker output. Отдельный worker test действительно выполняет
прежний HTTP parser/probe с fake socket bytes; это software integration, не
packet artifact с Docker network.

[fake-observation.json](experiments/trusted_checker_mvp/docker_pilot/fake-observation.json)
явно маркирует `fake_sdk_only`, `DOCKER PILOT NOT EXECUTED`, actual HTTP not executed.
IP, Docker IDs, daemon, user/attempt/Ledger IDs в нём synthetic; hashes images
не являются измеренными images. Локальный настоящий HTTP из этапа 1 остаётся
историческим evidence этапа 1, не переименован в Docker measurement.

Начальный run обнаружил, что fake inspect не materialized `AutoRemove=false`
(SDK serializer опускает default); исправлен fake Engine snapshot. Ещё один
assertion различал ValueError/TypeError dataclasses между Python versions;
теперь требует refusal обоих типов. Model worker-ID test уточнён как inconsistent
inspect reply, не невозможное изменение Docker ID объекта in-place. Production
guards ради этих fake fixtures не ослаблялись.

## 9. Реальные negative tests: не выполнены

По явному ограничению пользователя **к daemon не подключались**. Наличие Docker
CLI в PATH и SDK 7.1.0 не говорит о доступности/разрешении конкретного daemon.
Не измерены ни image/build compatibility, ни реальная HTTP-проба из verifier.

| Требуемый real case | Статус |
|---|---|
| Root заменяет check.sh на exit0 и curl/ip в disposable task | NOT EXECUTED; только fake dispatch independence |
| Root меняет body, bind, port; stop/restart server/container | NOT EXECUTED; только fake HTTP/runtime faults |
| Вторая attempt/reset/restart/IP reuse | NOT EXECUTED; только source/SDK metadata tests |
| Нет Docker socket в task/verifier, нет доступа к control/DB/terminal | NOT EXECUTED; profile refusal работает offline, native denial не доказан |
| Trainee присылает prepared JSON/пытается писать result channel | NOT EXECUTED в container; fake HTTP JSON mismatch / forged binding refusal проверены |
| Runtime caps, actual attach fragmentation/wait/remove and crash | NOT EXECUTED; только SDK serializer и fake lifecycle |

Все эти cases требуют отдельно разрешённой disposable среды и approved images;
production/VDS не являются fallback. Изменение manual host firewall/routes/sysctl
не предусмотрено. `network_isolation=unverified` нельзя повысить по этому report.

## 10. Непроверенные свойства задания и следующий Django slice

Одна HTTP 200/expected body доказывает только endpoint behavior в момент ответа.
Она не подтверждает wildcard/localhost bind, локальную доступность внутри target,
named customer-app state/original binary, persistence fix, отсутствие proxy или
continuous correctness. Root может запустить другой HTTP server с тем же body;
это не принимает ни process, ни bind property. Даже real Docker HTTP match
оставит **task verdict unknown**, пока все обязательные свойства не закрыты
или task policy явно не сужена отдельным решением.

Минимальный следующий integration plan — **не применён**:

1. Реализовать один read-only orchestrator source для current owner/task/attempt,
   pending `TechnicalCheckExecution.run_id`/ordinal. Не вызывать ordinary
   `@checked` success writer для observations и не создавать новый Ledger run
   как side effect checker. Read calls должны иметь DB timeouts.
2. Закреплять environment UUID и exact Docker snapshot при создании/reset среды
   в host-controlled mapping; текущие models не дают UUID автоматически.
   Повторно читать binding перед/после probe и перед будущим consume; row lock
   только на короткий claim/compare, не на network wait.
3. Перевести single-use claim в existing DB execution transaction/constraint,
   оставить отдельный bounded TechnicalObservation storage/diagnostic reader,
   который `technical_evidence.py` не считает success. Этот этап не добавляет
   migration и не пишет в существующий Ledger.
4. Подготовить approved pinned images и один отдельный isolated network profile,
   проверить capabilities/HostConfig/attach compatibility в **разрешённом** lab.
   Production target default bridge/caps не adopt и не менять автоматически.
5. Выполнить real negative table из раздела 9; отдельно решить missing task
   properties и провести короткий security review Docker/source/transport.
   Только затем рассматривать observation-only enablement для одного task.

Включение academic/technical pass остаётся отдельной задачей. Текущая production
ветка `check.sh → exit0 → CheckRun` **не изменена**, её root-spoof риск этим
offline adapter не объявляется устранённым на работающем сервисе.

## 11. Целостность и решение

Перед изменениями закреплены SHA-256 **483 existing files**, включая Sandbox,
шесть прежних Trusted Checker packages, H1/H2/re-review artifacts/reports,
native fixtures, Compose/settings и все файлы local MVP этапа 1. Все 483 hashes
совпали. [integrity.json](experiments/trusted_checker_mvp/docker_pilot/integrity.json)
хранит baseline и hashes новых files. Старый physical source digest остаётся
`bffce5ec1e43bf1783f2b48a23b3372397c4fd5f8aded93ff3b4e95561efae3a`.

Добавлены только отдельный docker_pilot каталог и этот report. Production source,
academic writers, старые tests/fixtures/reports/gates и прежний MVP не менялись.
Полный Trusted Checker/Django regression здесь не запускался: исполняемые изменения
изолированы, прежние modules не импортируются. Проверены syntax/whitespace/local
links, synthetic regressions и old-file integrity; это не production certification.

Ни APIClient к daemon, ни Docker build/pull/create/start/network operations,
SSH/VDS, host firewall/routes/sysctl, native helper/OS reader/setns/FD-exec,
physical probes, deploy/commit/push/rebase не выполнялись. Рабочие БД, .env и
credentials не читались. Local filesystem artifacts и fake threads не являются
kernel/network experiments.

**`MVP DOCKER ADAPTER OFFLINE READY`. `DOCKER PILOT NOT EXECUTED`.**
Один fixed task/worker/probe/observation реализован через стандартный Docker SDK,
без академических writes и расширения H1/H2. Реальный runtime/network acceptance
остаётся следующей отдельно разрешаемой проверкой, а не выводом из 25 green tests.
