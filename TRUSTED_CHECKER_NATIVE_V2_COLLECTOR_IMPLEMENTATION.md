# Trusted Checker v2: Fenced Read-only Collector — №20.1b-8g

21 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-06a OFFLINE READY`.** Добавлен отдельный default-OFF capture boundary:
immutable plan/identity/session/artifact/manifest, fixed read-only argv registry,
bounded deterministic fake transport, process-local issuance fences и pure
bridges к прежним V2-02/V2-03/V2-05 decoders. Реального OS backend нет;
constructor runner принимает только exact deterministic fake type.
Полный Trusted Checker run: **1125 tests, OK**, включая **103 новых**.

`capture_preserved_in_mock_model` означает сохранение bytes и согласованность
метаданных **в явно заданной synthetic модели**. OS identity, binary provenance,
permissions, transport attestation и physical timing остаются unproven.
`physical_probe_permitted=false`, `ownership_proven=false`,
`management_policy_verified=false`, `isolation_verified=false`,
`measurement_verified=false`, `continuous_attestation=false`.
Physical audit остаётся **`NOT READY`**, shadow-only сохраняется.

Выполнены только локальные чтения, pure Python/mock tests и документация.
SSH/VDS, реальные nft/ip/bridge/tc/Docker/setns/packet operations и physical
collection даже на локальном host не выполнялись. Application/Django/Ticket
Sandbox/Ledger/Roadmap/достижения, academic writers, host firewall/routes,
physical gates и v1 не изменены. Commit/push/rebase/deploy не выполнялись.

## 1. Архитектура и файлы

| Новый файл | Назначение |
|---|---|
| [`native_v2_capture_contracts.py`](trusted_checker_network/native_v2_capture_contracts.py) | Immutable DTO, registry, manifest coverage, finite reasons и обязательные unobserved requirements |
| [`native_v2_collector.py`](trusted_checker_network/native_v2_collector.py) | Finite fake pull transport, bounded runner и default-OFF one-attempt collector |
| [`native_v2_capture_adapters.py`](trusted_checker_network/native_v2_capture_adapters.py) | Pure parsing bridges с отдельными mock provenance references |
| [`native_v2_collector_support.py`](trusted_checker_network/tests/native_v2_collector_support.py) | Независимые synthetic identities/plans/scripts; команды никогда не исполняются |
| [`test_native_v2_collector.py`](trusted_checker_network/tests/test_native_v2_collector.py) | 103 новых offline tests |
| Этот документ | Review boundaries, проверки и оставшиеся prerequisites |

Новый package не создан. Прежние modules, contracts, decoders, fixture originals,
reports и tests не редактировались. Production imports — dataclasses, hashlib,
datetime для pure UTC formatting, threading.Lock и pure v2 modules. Нет import
physical I/O, subprocess/os/socket, environment discovery, signing или live API.

| Компонент | Контракт |
|---|---|
| `CapturePlan2` | Предварительно заданные ordered requests, independent plan pin и отдельный binary-manifest pin; purpose только `inventory_preflight_only` |
| `ReaderIdentity2` | Раздельные principal refs, boot/session/namespace/PID-generation/FD/peer/NSID refs и writer epoch; basis только `deterministic_mock_only` |
| `CaptureSession2` | Один session UUID, exact plan digest, начальные wall/monotonic значения и абсолютный monotonic fence |
| `ReadOnlyCommandRunner2` | Только fixed operations через exact `DeterministicMockTransport2`; native backend отсутствует |
| `CaptureArtifact2` | Exact bounded stdout/stderr bytes, source/argv/profile/identity/timing refs, hashes, exit и completion description |
| `CaptureManifest2` | Exact ordered coverage всех requests; никаких missing/duplicate/reordered/substituted artifacts |
| `CaptureValidation2` | Immutable terminal: `capture_preserved_in_mock_model` либо `unknown`; OS/physical claims всегда закрыты |

Collector не разбирает JSON, не сравнивает policy и не выдаёт authority. Даже
пустой stdout может быть успешно **прочитан в fake модели**; его JSON validity
проверяет только соответствующий decoder. Valid `[]`, zero bytes, missing
source, nonzero exit и partial stream остаются разными случаями.

## 2. Fixed registry и binary manifest

Registry version: `tc-read-only-argv-v2-offline-1`.
Registry content digest:
`2cb033e374c5c50204030b9cb9982632b286c199c632b0cd72ab2490c171f345`.
Это static frozen tuple, а не input-driven allowlist.

| Source | Exact argv, первый token — absolute executable |
|---|---|
| nft | `/usr/sbin/nft -j -a list ruleset` |
| link | `/usr/sbin/ip -j -d link show` |
| address | `/usr/sbin/ip -j address show` |
| bridge_link | `/usr/sbin/bridge -j -d link show` |
| bridge_vlan | `/usr/sbin/bridge -j vlan show` |
| bridge_fdb | `/usr/sbin/bridge -j fdb show` |
| route4 / route6 | `/usr/sbin/ip -j -4/-6 route show table all`, два разных fixed tuples |
| rule4 / rule6 | `/usr/sbin/ip -j -4/-6 rule show`, два разных fixed tuples |

Все operations применимы к явно заданным host/runner/target roles. Namespace
передаётся **отдельной typed reference**, а не добавляемым аргументом или
`ip netns exec NAME`. Shell, stdin, env/command overrides, namespace names,
arbitrary executables и generic execute API отсутствуют. У registry нет
install/apply/flush/cleanup/send operations. Реальный namespace-entry механизм
потребует отдельного review и здесь не реализован.

`BinaryManifest2` содержит ровно три absolute paths в deterministic order.
Для каждого independently supplied `BinaryReference2` фиксирует binary SHA-256,
explicit build version, source-manifest и protection-review digests. Эти refs
входят в отдельно pinned manifest и plan. Fake сообщает observed binary tuple;
runner сравнивает его целиком. Подмена path/hash/source/version/protection
reference не допускается. Version text сам по себе ничего не подтверждает.

Это **fixture claims**, а не чтение или hashing executable на машине. Нет
проверенных OS binaries, signed build provenance или accepted native source
manifest. Старые version-output hashes V2-05 не переименованы в binary hashes.
Actual binary measurement, symlink/TOCTOU protection и protected execution
environment остаются future OS proof obligations.

## 3. Namespace, reader и роли

`NamespaceReference2` связывает role с существующим immutable `NamespaceKey2`:
host boot UUID, netns inode, reader-session UUID и binding generation. Дополнительно
заданы mock FD-reference UUID/status, namespace reference digest, lookup PID
со start ticks, session-scoped NSID→inode tuples и peer witness references.

`ReaderPeerReference2` сохраняет оба namespace keys/ifindices, оба local NSID
и witness digest. Проверяются разные namespaces одного boot/session, membership
обоих namespaces в reader, согласованность NSID mappings и witness refs, отсутствие
shared endpoint slots. Это проверка внутренней модели; actual reciprocal veth
readback, открытые FD и OS NSID witnesses ею не создаются. Peer set может быть
пустым для ограниченного source plan; capture success при этом не закрывает
обязательный peer/OS proof.

Reader задаёт пять **разных** principal-reference digests: installer, writer,
reader, validator, approval authority. Permissions/configuration review refs
и writer epoch обязательны. Mock drift проверяется перед началом чтения и на
**каждом event**, включая completion после exit: reader principal/session,
PID/start generation, namespace/FD references, NSID/peer mapping, configuration
или writer epoch должны оставаться exact. Lost mock FD закрывает чтение.

Разные digests не означают разные UID, capabilities или OS privilege domains.
`lookup_pid` не используется для действительного proc lookup. Имена из
`ip netns list`, совпадение ifindex, PID без start ticks либо string `ifN` не
являются источниками identity. Legacy native archive не получает выдуманные
FD/inode/boot/session/writer facts.

В future OS role review отдельно нужны minimum namespace-entry privileges и
read permissions, отсутствие write routes/nft/sysctl/offload/packet authority,
protected executable/config/secret/journal paths, проверка inherited/external
FDs, capabilities и независимость от Runner stdin/data. Возможная необходимость
privileged read helper не разрешена данным этапом. Root/daemon admin остаются TCB.

## 4. Artifact, completion и manifest

Каждый artifact содержит exact request с source/decoder profile/capture UUID,
namespace reference, fixed argv через registry, observed binary, session и
полный `InstallKey2`: approval/context/binding/writer epoch/install epoch/generation.
Начало/конец wall UTC и monotonic представлены exact integer microseconds;
UTC string выводится pure formatting, чтения настоящих часов нет.

Stdout/stderr сохраняются как exact internal bytes. Отдельно доступны stdout
SHA-256/count и bounded stderr category `empty`/`bounded_stderr_present`.
Completion description включает session/request digest, invocation ordinal,
оба byte hashes и статус `mock_stream_eofs_exit_and_completion_observed`.
Completed artifact требует exit integer 0, truncated/interrupted/timed_out false.

Fake protocol требует stdout EOF, stderr EOF, exit=0 и explicit completion в
этом порядке после data. Duplicate EOF, data после EOF/exit/completion, отсутствие
любого обязательного события, process death/timeout/interruption/truncation
дают unknown. Supplied JSON `{"complete":true}` — только bytes; он не создаёт
transport event или receipt. Nft decoder затем отвергает такую JSON schema.

Одного coherent DTO или hash недостаточно для parsing bridge. Runner хранит
точные issued artifact objects; collector сохраняет собственные manifest и
terminal. `validate_manifest`/`admit_for_parsing` требуют **тот же** issued object
и тот же collector instance, повторно проверяя contracts. Copy/replace,
forged completion, foreign-instance replay, новый install generation и partial
manifest не принимаются вместо выданного результата.

Это process-local admission fence внутри trusted Python процесса, **не подпись,
не durable replay journal и не защита от произвольной модификации памяти TCB**.
Trusted fixture setup может явно создать новый fake experiment; это не physical
replay acceptance. Completion description навсегда остаётся mock/unattested.

## 5. Bounded transport, deadline и terminal fencing

| Bound | Проверка |
|---|---|
| Pull chunk ≤16384 bytes | Fake возвращает не более запрошенного размера; нарушение отвергается до buffering |
| Nft stdout ≤262144 bytes | До добавления следующего chunk в bytearray |
| Другие stdout ≤1 MiB/source | До добавления следующего chunk |
| Stderr ≤4096 bytes/command | Отдельный cap, без накопления произвольных diagnostics |
| Aggregate stdout+stderr ≤16 MiB | По мере получения, включая уже выданные artifacts |
| Plan/scripts ≤256; events ≤4096/script | Finite fixture/attempt bounds, без бесконечного fake generator |
| Command wall/monotonic elapsed ≤500000 µs | Проверяется на каждом event |
| Session wall/monotonic elapsed ≤2000000 µs | Absolute fence, запрет продления через input |

Перед увеличением буфера проверяются chunk/stream/aggregate caps. Partial buffers
очищаются при выходе; partial stream не возвращается как completed artifact.
При unknown оставшиеся sources не читаются, fake transport закрывается и
terminal/circuit сохраняется. Нет retry, fallback command или автоматического
запуска нового instance. Повторный `capture()` возвращает тот же terminal.

Synthetic script bytes уже выделены test setup **до** вызова runner. Здесь
ограничивается удержание/накопление runner, а не allocation caller или реальная
pipe/socket transport. Bytearray→bytes временно создаёт bounded copy; Python
overhead/RSS не равен raw cap. Реальный bounded-read/cancellation/drain/reaping
механизм не написан и не объявлен проверенным.

Separate nonblocking attempt lock запрещает concurrent entry; отдельный state
lock сериализует kill и publication. Kill до terminal даёт immutable unknown,
late completion не перезаписывает его. Kill после terminal сохраняет выданный
record, но запрещает дальнейший parsing admission. Wall либо monotonic rollback
закрывают attempt. Неизвестные exceptions дают только `evidence_invalid`.

Это **inventory preflight**, не packet measurement и не новый live timing
profile. Строгий mock fence не расширяет прежние 2s. Часы supplied/fake, поэтому
даже полный capture имеет `timing_unproven_for_physical_inventory`. Если future
полный inventory не укладывается, нужен отдельный measured/reviewed preflight
timing profile; длинный inventory нельзя переносить в окно одной probe либо
скрыто расширять measurement budget. Real blocking-read timeout и независимый
trusted monotonic clock требуют OS implementation review.

## 6. Pure integration bridges

| API | Что проверяет / возвращает |
|---|---|
| `decode_collected_nft2` | Issued capture, nft source/profile, exact namespace/install и binary refs; вызывает unchanged `decode_native2` |
| `decode_collected_topology2` | Полный независимо supplied old capture plan, все descriptors/namespace/context/epoch/hash/size/binary refs; unchanged batch topology decoder |
| `decode_collected_native61` | Exact source/profile, independently pinned legacy reference, scope label и bytes/hash/size; unchanged diagnostic native61 decoder |
| `ParsedCaptureReference2` | Отдельные capture/result/decoded digests с basis `mock_capture_reference_only_os_unproven` |

Adapters не создают expected policy из stdout, не нормализуют unknown fields,
не выбирают decoder по input, не меняют handles/order/defaults и не фильтруют
IPv6/foreign objects. Успешное capture допускает parsing, но не его success.
V2-02 сохраняет CT/raw unproven и требует отдельного recipe comparison;
V2-03 получает полный old plan или отказывает на coverage; V2-05 остаётся
diagnostic schema с непринятой native semantics.

Прежний `CaptureDescriptor2.transport` остаётся
`offline_supplied_bytes_no_completeness_attestation`. Legacy
`NativeSourceReference61.exact_argv/timestamps` остаются `unrecorded`, namespace
identity/principal — `unobserved`. Wrapper хранит **отдельную новую mock ссылку**,
не переписывает происхождение оригинального artifact и не заявляет, что старый
archive был собран этим collector. V2-05 version-output refs не заменяют binary
manifest нового boundary.

Recipe/profile/topology/isolation/measurement/ownership validation и permit
issuance не вызываются автоматически. Нет conversion в `EgressValidation`,
authority permit, academic evidence, `MatrixReceipt` или live collector report.
Internal artifacts/result содержат raw bytes; operator export не добавлен и
их нельзя выдавать вместо отдельного bounded/redacted export.

## 7. Неподдерживаемые OS evidence surfaces

Result вычисляет `UnsupportedEvidence2(status=unsupported_unobserved)` для
каждой reader namespace reference и каждого из **18 requirements**: в полном
synthetic fixture три namespaces дают **54 records**. Caller не может пометить
их verified или убрать requirement через constructor override.

Обязательны namespace FD/peer/NSID identity, binary build/source provenance,
authenticated bounded transport, reader permissions/capabilities, namespace-entry
privileges, executable/config/secret/journal protection, exclusive writers,
tc ingress/egress, XDP, flowtables, IPv4/IPv6 forwarding, proxy ARP/ND,
bridge-netfilter, offloads, external/inherited FDs, full namespace inventory
и native host-profile acceptance.

Ни одного actual tc/sysctl/offload/permission source adapter здесь нет. Nft
ruleset capture не закрывает сам по себе flowtable/foreign-hook inventory;
неподдерживаемая nft schema по-прежнему отвергается decoder. Unsupported surface
не становится empty list/none/false и не закрывается успешными 10 командами.
Link-scoped OS requirements, реальные namespace enumeration/attachment facts,
privilege protection и trusted writer control требуют следующего review.

Potential future read effects — child process creation, namespace FD opens/
entry, proc/sys reads, netlink dump traffic и bounded temporary buffers —
описаны как **dormant obligations**. Здесь выполняются только in-memory fake
events, hashing, pure comparisons и локальные synchronization locks. Generic
cleanup, state mutation, packet send и OS resource ownership не входят в API.

## 8. Mock tests и security review

Добавлены **103 самостоятельных tests**, без skips/expected failures. Positive
baseline явно synthetic: три namespace roles, 30 planned sources, независимо
заданные binary/identity/plan refs. Adapter positives отдельно используют
прежние authored nft/topology/native-format fixtures.

Проверяются fixed argv/FD-reference dispatch, default OFF и отсутствие constructor
I/O; wrong binary/hash/source/protection/principal/configuration; namespace
generation, PID/start ticks, lost/replaced FD, NSID и reciprocal peer faults;
epoch drift; nonzero/missing/partial/truncated/oversized stdout/stderr; total cap;
missing/duplicate EOF, late data, forged complete JSON, timeout/interruption/
death, wall/monotonic rollback/jumps; replay, duplicate/partial/substituted
manifest, coherent receipt copy, forged metadata/hash; malicious argv/shell
injection, unsupported operation/native backend; immutable terminal и kill
перед publication. Unknown удерживает circuit без auto retry.

Adversarial cases начинаются с valid baseline своей стадии. Incoherent typed
inputs отвергаются constructor, coherent изменённая identity закрывается при
сравнении с pin. Проверены exact false flags, 54 unobserved records, прежний
`physical_network_boundary_not_accepted`, strict parser refusal после successful
capture и отсутствие legacy provenance upgrade. Extra unknown JSON не удаляется
ради decoder success. Original native fixture bytes остаются без изменений.

AST review запрещает production OS/network/process imports и dynamic execution.
Fresh-import/constructor/capture test запускает только локальный Python test
process с запрещёнными socket/Popen/system/os.open/setns внутри проверяемой
работы. Это не physical subprocess и не реальная network collection.

Первый run 91 tests выявил две неверные ссылки test setup на прежние API и
mutation с преждевременным clock rollback. Исправлены tests, guards не ослаблены.
После review peer/NSID refs, explicit unobserved statuses и publication fencing
финальный standalone run: **103 tests, OK, 7.890s**.

## 9. Полный Trusted Checker regression

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_network/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_physical/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_live/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_runtime/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_shadow/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_poc/tests -t .
```

| Suite | Tests | Failures | Errors | Skips | Результат |
|---|---:|---:|---:|---:|---|
| Network: прежние 596 + новые 103 | 699 | 0 | 0 | 0 | OK, 87.576s |
| Physical | 90 | 0 | 0 | 0 | OK, 13.629s |
| Live | 48 | 0 | 0 | 0 | OK, 12.966s |
| Runtime | 66 | 0 | 0 | 0 | OK, 11.229s |
| Shadow | 56 | 0 | 0 | 0 | OK, 3.323s |
| PoC | 166 | 0 | 0 | 0 | OK, 13.649s |
| **Всего** | **1125** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0. Проверены отсутствие skips,
ResourceWarning, failures и errors в логах. Прежние **1022** tests и новые
**103** прошли; Network теперь **699** tests.

Логи: `/tmp/task201b8g-{network,physical,live,runtime,shadow,poc}.log`.
Suites выполнялись отдельными offline/mock processes независимо/частично
параллельно; durations не benchmark. Это полный Trusted Checker, не всех
Django приложений проекта. Application source/writers не менялись, Django
regressions не запускались.

## 10. Целостность и source digest

До изменений сохранён manifest `/tmp/task201b8g-baseline.json`: **300 artifacts**
шести Trusted Checker packages без caches и прежних `TRUSTED_CHECKER*.md`.
Новые files — три production modules, два test files и этот отчёт, всего **6**.
Native originals/generated matrices/archives не дополнялись и не переписывались.
Рабочие БД, .env, credentials и Docker sockets не читались.

Dynamic physical source manifest включает новые top-level network modules:

- до: `d319645c9dbe945f58b25ae84566ff9c94440532ab48e44758710f2532da8281`;
- после: `902711ce1fd49b777f5d27884331fe33474f2b2b6813f51317df90ebd29375e1`.

Проверено точное совпадение SHA-256 всех **300 baseline artifacts**, включая
physical gate/live adapter, прежние suites и native originals/archives/matrices.
Состав additions — ровно шесть перечисленных files. Проверены syntax/AST,
whitespace, local Markdown links, fenced blocks и нумерация 12 разделов.
Tracked Git diff пуст; прежние untracked files сохранены.

Старые approvals не обновляются/не переподписываются и не наследуются
автоматически. Review/config/identity/content digests не создают authenticated
physical approval.

## 11. До первого отдельно разрешённого read-only VDS run

1. Принять отдельную versioned OS reader implementation и review всех её I/O
   paths. Сейчас такой implementation нет: включение `enabled=True` выбирает
   исключительно fake. Нужны fixed executable execution без shell/stdin,
   protected environment, bounded streaming/cancellation/reaping и no write API.
2. Получить exact отдельное разрешение host/boot/kernel/builds/source digests,
   roles, reader binaries/config, namespace FD acquisition/entry, source/argv/
   applicability/caps и timing. Этот report не разрешает даже read-only SSH.
3. Предоставить actual binary/build/source/protection attestation и минимальные
   OS permissions/capabilities. Review отделяет installer/writer/reader/validator/
   approval authority и защищает secret/config/journal paths; refs/HMAC одних
   privileges не разделяют. Runner stdout/stdin не становится independent source.
4. Получить trusted namespace FD/inode/boot/session/binding generations, bracketed
   PID/start ticks и real reciprocal peers/session-scoped NSID mappings. Отдельно
   учесть named/unnamed/FD-held namespaces, management identity и external FDs.
   Не переносить четыре lab scope labels в identity без witnesses.
5. Зафиксировать полный source plan во всех применимых namespaces, включая
   bridge/VLAN/FDB captures и все unsupported OS surfaces из раздела 7. Missing
   sources не восстанавливать и не считать пустыми. Unknown native field требует
   отдельного offline schema review, без automatic host/schema fixes.
6. Подписывать bounded trusted descriptors/hash/completion с actual reader
   principal, wall/monotonic intervals, transport integrity/truncation, context,
   writer/install epochs. Проверить independent clock, pre/post identity fences,
   lost read, kill/restart/replay и non-atomic sequential dump limitations.
7. Отдельно измерить inventory timing; если 2s недостаточно, принять отдельный
   preflight timing profile до нового run. Не менять packet measurement budget
   и не объявлять archive name/time trusted capture interval.

Такой read-only run не устанавливает canonical tables и не создаёт installation
ownership. Durable journal/committed witness, installer/rollback, canonical
kernel round trip, CT/raw proofs, byte calibration, packet collector и controlled
15-probe measurements остаются отдельными V2-06b/c–V2-09 задачами/разрешениями.
Raw captures требуют protected storage и отдельного bounded operator export.

## 12. Решение

**`V2-06a OFFLINE READY`** для разработанного mock boundary и pure parsing
integration. OS backend намеренно отсутствует; real reader identity, permissions,
FD/NSID/build/transport/timing proofs и full OS source coverage не приняты.
Успех fake не доказывает kernel compatibility, management isolation, ownership
или network boundary. Snapshot equality не исключает transient attach/revert,
reset/restore или writer mutation; `continuous_attestation=false` сохраняется.

`PhysicalProbeGate`, live adapter и `physical_network_boundary_not_accepted`
сохранены. Physical acceptance остаётся **`NOT READY`**. Ни один новый record
не разрешает physical probe, live activation или academic transition.
