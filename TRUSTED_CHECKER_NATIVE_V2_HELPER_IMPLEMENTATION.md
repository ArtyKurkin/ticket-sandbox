# Trusted Checker v2: Standalone Helper Protocol & Identity Boundary — №20.1b-8i

21 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-06a-H1 OFFLINE READY`.** Реализованы bounded binary codec, incremental
decoder, независимый transcript verifier, standalone helper state machine,
owned-invocation supervisor и строгая offline identity/FD boundary. Synthetic
end-to-end проходит supervisor → protocol → helper → fake FD-exec child → bounded
capture → child reap/close → completion → helper reap/close. Это исполняемый
код протокола/lifecycle, не только архитектурная спецификация.
Полный Trusted Checker regression: **1357 tests, OK**, включая **130 новых**.

**OS READY не присваивается.** Native helper/observer/credential/FD-exec entry
points закрыты до отдельного Linux security review. Итог предыдущего OS этапа
`V2-06a-OS BLOCKED` и physical audit `NOT READY` сохраняются. Ни один mock тест
или invocation digest не открывает native execution.

`physical_probe_permitted=false`, `ownership_proven=false`,
`isolation_verified=false`, `management_policy_verified=false`,
`measurement_verified=false`, `continuous_attestation=false`.
Shadow-only; existing physical gates CLOSED.

Выполнены только локальные чтения source/attachments, pure Python/fake tests и
документация. Реальный helper не запускался ни локально, ни на VDS. Нет SSH,
nft/ip/bridge/tc/Docker/setns/packet операций, host mutations, academic writes,
Django/Ticket Sandbox/Ledger/Roadmap/achievements changes, commit/push/rebase/deploy.

## 1. Файлы и API

| Новый файл | Реализованный код |
|---|---|
| [`native_v2_helper_protocol.py`](trusted_checker_network/native_v2_helper_protocol.py) | Immutable invocation/FD catalog, fixed binary message schema, codec и bounded stream decoder |
| [`native_v2_helper_identity.py`](trusted_checker_network/native_v2_helper_identity.py) | Bounded source parsers, phase-specific identity validation, native-unreviewed status |
| [`native_v2_helper_runtime.py`](trusted_checker_network/native_v2_helper_runtime.py) | Standalone helper, transcript verifier, session registry, supervisor, bounded cleanup и immutable result |
| [`native_v2_helper_fake.py`](trusted_checker_network/native_v2_helper_fake.py) | Отдельный fake FD/kernel/process/clock driver, без OS effects |
| [`native_v2_helper_native.py`](trusted_checker_network/native_v2_helper_native.py) | Explicit helper entry, isolated guarded native source/namespace/FD-exec primitives |
| [`native_v2_helper_support.py`](trusted_checker_network/tests/native_v2_helper_support.py) | Независимые synthetic invocation/FD/identity/process inputs |
| [`test_native_v2_helper.py`](trusted_checker_network/tests/test_native_v2_helper.py) | 130 новых offline tests и mutation subtests |
| Этот отчёт | Schema, lifecycle, assumptions, regression и оставшиеся prerequisites |

Новый package не создан. Все прежние source/contracts/tests/reports, v1,
collectors/adapters, Linux guards, fixtures/archives и physical gates сохранены.
Основное приложение не импортирует/не запускает новый helper автоматически.
Native module имеет explicit standalone entry; выполнение его native entry
немедленно даёт `native_identity_unreviewed` до OS I/O. В этом этапе такой
process entry не запускался.

| API | Boundary |
|---|---|
| `HelperInvocationH1` | Independently pinned immutable request/policy/session/nonce/FD/identity/deadline record |
| `HelperCodecH1`, `HelperStreamDecoderH1` | Exact binary encode/decode и bounded fragmentation handling |
| `standalone_helper_entry_h1`, `StandaloneHelperH1.run_fake` | Explicit in-process offline exercise; только exact fake kernel и owned fake channel |
| `HelperTranscriptH1` | Отдельная проверка stage/sequence/bytes/hash/completion; ошибка необратима |
| `OwnedInvocationRegistryH1` | Session-bound reserve-before-dispatch, replay/circuit/concurrency и aggregate accounting |
| `HelperSupervisorH1.run_fake` | Default-OFF orchestration, child/helper cleanup, immutable terminal |
| `capture_native`, `native_helper_entry_h1` | Всегда закрыты до native identity/authority review |

## 2. Invocation и fixed operations

Invocation включает existing `OSReadPolicy2`, `CaptureSession2`, exact
`CaptureRequest2`, отдельный invocation UUID, explicit nonzero 256-bit nonce,
namespace FD pin, executable identity, семь typed descriptor slots, helper и
parent PID/start ticks, initial namespace inode и absolute monotonic deadline.
Invocation digest закрепляется независимо от проверяемого wire input.

Поддерживается только прежний fixed registry V2-06a: nft, link, address,
bridge_link, bridge_vlan, bridge_fdb, route4/route6, rule4/rule6 с exact absolute
executables и argv. Policy/session/request/namespace/binary/source refs должны
совпасть. Deadline нельзя расширить сверх command 500ms/session 2s bounds.

Нет caller argv, shell, commands из stdin, namespace names, arbitrary paths,
environment discovery, PATH execution или pathname fallback. Environment только
`LANG=C`, `LC_ALL=C`. Existing offline/mock policy остаётся structural template;
он не превращён в OS activation approval. Nonce в tests задаётся явно synthetic
trusted setup. Для будущего native supervisor нужны отдельно reviewed generation,
secrecy/lifetime/channel facts; nonce из Runner input неприемлем.

## 3. Binary protocol H1

Wire magic `TCH1`, integer wire version **1**. Это версия helper protocol,
не изменение existing native compatibility contract integer 2.

Header network byte order: `!4sBBHI`, **12 bytes**:
magic[4], version[1], message-kind[1], sequence[2], body-length[4].
Sequence допускается 0..4095; неизвестные magic/version/kind или лишние bytes
отвергаются. Root body имеет обязательный binding prefix **272 bytes**:

| Поле | Bytes |
|---|---:|
| Capture session UUID, invocation UUID | 16 + 16 |
| Nonce, exact request digest | 32 + 32 |
| Namespace reference digest, executable object digest | 32 + 32 |
| Expected command principal digest | 32 |
| Writer epoch, install epoch UUID | 16 + 16 |
| Install generation, absolute monotonic deadline | 8 + 8 |
| Полный immutable invocation digest | 32 |

Every message сравнивается с independently pinned binding целиком. UUID,
integer и digest fields имеют fixed widths; никакого JSON, optional `extra`,
supplied `complete=true` либо decoder selection по input нет.

| Message kind | Exact tail после binding |
|---|---|
| invoke | 32-byte FD catalog digest |
| ready / entered / credentials / exec | 32-byte independently computable phase commitment |
| stdout / stderr | 1..4096 bytes, только data |
| stdout_eof / stderr_eof | 0 bytes |
| exit | 2-byte status, range 0..255; success требует 0 |
| reaped | 32-byte child-cleanup reference |
| complete | stdout hash[32], stderr hash[32], counts[8+8], exact cleanup reference[32] |
| error | finite reason index[2], cleanup-status[1] строго 0/1 |
| cancel | 0 bytes; supervisor direction, sequence 1 после invoke sequence 0 |

У helper direction свой sequence с 0. Successful order:
ready → entered → credentials → exec → ordered data/EOF → exit → reaped → complete.
EOF каждого stream единственный; late data/duplicate EOF/reap/completion и
messages после terminal отвергаются. `error` имеет только finite code; произвольные
exception/stdout strings в error record не помещаются.

Максимальный body **4368 bytes**, frame **4380 bytes**. Incremental decoder
держит не более одного bounded frame; oversize declaration отвергается уже на
header. На direction ≤4096 messages. Partial/truncated input фиксирует failed
stream; поздними bytes его нельзя «починить». Verifier также необратимо
закрывается при первой ошибке и не принимает subsequent corrected completion.

Digests/phase commitments — **не MAC и не OS attestation**. Они связывают exact
model/request/sequence; compromised trusted helper способен лгать. Native control
FD требует отдельной проверки ownership/peer credentials/transport integrity.
Результат голого codec decode не принимает канал и не выдаёт permit. Admission
готового result требует точный object issuing supervisor instance.

## 4. FD transfer и namespace identity

Catalog имеет ровно семь slots в fixed order:

| Slot | Required kind / смысл |
|---|---|
| namespace | Held netns FD, namespace device/inode/generation/reference |
| executable | Regular held FD, device/inode/content/stat identity |
| stdin_null | Independently pinned character-device identity |
| stdout_pipe / stderr_pipe | Два разных owned write-pipe identities |
| control | Owned unix-control descriptor identity |
| parent_watch | pidfd identity, binding boot+parent PID+start ticks |

`ReceivedDescriptorH1` содержит slot и **локальный** FD number. Тип и actual
object identity поступают отдельно от kernel port и сравниваются с pinned
catalog. Missing/extra/duplicate slot/FD, wrong kind/device/inode/generation/hash
дают отказ. Receiver FD number разрешено перенумеровать; он не сравнивается с
sender FD number как proof. Executable object digest намеренно не включает
числовой FD, но включает device/inode/size/ctime/mode/owners/link count/hash/source.

Namespace pin связывает boot/netns inode, reader session/generation, namespace
lookup PID/start ticks и session-scoped NSID/reciprocal-peer refs. Phase-specific
snapshot проверяет все эти refs и nsfs-net marker, helper/parent PID generation,
principal, actual inherited descriptor set, executable и protected config/journal
references. Parent-death check использует **переданный parent-watch slot** с
expected PID/start generation; PID не служит самостоятельной authority.

Это model kernel observations. Реальные SCM_RIGHTS receive/MSG_CTRUNC semantics,
SO_PEERCRED/control peer ownership, nsfs/NS_GET_NSTYPE/fstatfs ABI, pidfd identity
и реальный FD-generation witness ещё не приняты. Нет привязки к namespace name
или adoption по PID/FD number. Future native receiver должен закрывать только
вновь полученные owned descriptors при любой ошибке, включая malformed invoke;
sender/foreign FD tables не являются cleanup target.

## 5. Standalone helper: действительная offline последовательность

Helper — single invocation state machine, не автоматически исполняемый import.
Весь эффект идёт через exact `FakeHelperKernelH1`; native path отдельно закрыт.

1. Получить bounded INVOKE и typed received descriptor records. Установить
   close-on-abort accounting до проверки INVOKE, чтобы malformed request не
   оставлял переданные owned FDs без cleanup.
2. Проверить wire binding/catalog, descriptor count/kinds/identities. Снять
   initial identity, проверить parent-watch/deadline/cancellation, отправить ready.
3. Проверить held executable FD; только затем выполнить model namespace entry
   через namespace slot. Снять/проверить entered identity и отправить entered.
4. Выполнить credential-drop operation и независимо сравнить post-drop UID/GID/
   groups/caps/no-new-privileges с policy. Failed operation либо drift дают unknown,
   не successful phase commitment.
5. Подготовить **child-only** stdio mapping 0/1/2, убрать остальные child FDs и
   fixed environment. Helper сохраняет только свои reviewed control/watch
   references до завершения. Не происходит setns основного Django/Checker process.
6. Зарегистрировать owned child **до** dispatch FD-exec. Исполнить через held FD
   fixed executable/argv. Нет `preexec_fn`, shell или `/proc/self/fd/N` string.
7. Poll bounded output с independent clock/parent/cancel fences. Дождаться обоих
   EOF и exit=0; exit может наблюдаться раньше окончательного drain EOF, но не
   считается completion. Проверить final identity и executable повторно.
8. Обязательно reap/close child, закрыть transferred data FDs. Только после этого
   отправить reaped и complete с exact byte hashes/counts/cleanup reference.
9. Закрыть control. Supervisor независимо требует helper close/reap и final
   deadline до publication. Close failure после wire complete всё равно не
   становится successful terminal.

Производственный native privilege-drop пока не реализован как принимаемый:
capset/prctl/securebits/userns ordering и capability readback требуют review.
Изолированный guarded FD-exec mapping использует `os.execve(fd, fixed_argv,
fixed_env)` при поддержке descriptor execution; pathname fallback отсутствует.
Kernel/build, Python FD-exec и loader/dependency/write-exclusion proofs отсутствуют,
поэтому concrete native calls и весь native entry остаются закрытыми.

## 6. Supervisor ownership, cancellation и bounded cleanup

`OwnedInvocationRegistryH1` закреплён к одному capture session. До dispatch
резервируются invocation UUID и nonce, регистрируется owned helper. Lost spawn
response всё равно оставляет known invocation для terminate/reap. Kill принимает
только opaque owned-process reference, не произвольный PID. Сначала helper
отвечает за child, затем supervisor — за сам helper.

Registry ограничен 256 entries, проверяет replay/nonce reuse и одну active
invocation. Unknown удерживает circuit; новый nonce не означает automatic retry.
Aggregate accounting stdout+stderr во всём registry ≤16 MiB; debit происходит
перед buffering data в parent transcript verifier. Concurrent supervisor entry
защищён отдельным nonblocking lock. State lock сериализует kill/publication.

При timeout, parent death, helper crash, interruption/failed FD-exec, missing
EOF/exit/completion либо cancellation выполняются TERM → bounded grace/drain →
KILL при необходимости → обязательная попытка reap → close. Cleanup имеет
finite iteration и byte bounds; ошибка clock/TERM/drain/reap/close сохраняется
как `cleanup_unproven`, даже если subsequent best-effort действие удалось.
Успешный stdout не скрывает неизвестный process/resource outcome.

| Ограничение | H1 enforcement |
|---|---|
| Data chunk | ≤4096 bytes |
| Stdout | Nft ≤262144, остальные sources ≤1 MiB |
| Stderr | ≤4096 bytes |
| Session aggregate data | ≤16 MiB до parent accumulation |
| Control transcript retention | ≤16 MiB + 2 MiB framing allowance, ≤4096 frames |
| Child polling | ≤4080 iterations, включая faulty frozen fake clock |
| Cleanup drain | ≤65536 bytes, ≤16 iterations |
| TERM/drain/reap proposal | 50000/50000/100000 µs, с rollback/overrun refusal |
| Capture timing | Existing 2s session и ≤500ms command, без hidden extension |

Helpers/driver script bytes предварительно созданы test setup. Ограничения
управляют accumulation данного boundary, не arbitrary caller allocation/RSS.
Sequential snapshots не атомарны; ephemeral attach/revert или privileged writer
между проверками не исключаются. Root/daemon/approved helper остаются TCB.

Повторный `run_fake()` возвращает тот же immutable terminal без нового dispatch.
Late completion не меняет отказ; kill после publication сохраняет historical
record, но закрывает admission. Registry и issued-object checks process-local:
durable restart/replay fencing/journal здесь не реализованы и не наследуются.

## 7. Identity adapter и Linux-specific предел

`IdentitySnapshotH1` и validator разделены с source acquisition. Snapshot — typed
offline observation, не native attestation. Native adapter всегда возвращает
`native_identity_unreviewed`; supplied JSON или synthetic observer не могут
переключить этот статус.

| Whitelisted source | Raw cap / применение |
|---|---|
| boot | 64 bytes; exact canonical UUID + newline parser |
| helper_stat / parent_stat / namespace_stat | 4096 bytes; independently expected PID/start ticks, bounded comm parsing |
| helper_status | 16384 bytes; strict bounded fixture projection UID/GID/groups/caps/NoNewPrivs |
| inherited_fds | 4096 bytes / ≤256 rows; unique numeric set, no guessed absent FDs |
| protected_references | 4096 proposed cap; native filesystem/ACL source profile не реализован |

Native module содержит guarded fixed proc source mapping, bounded reads,
bounded FD enumeration, FD stat/hash, namespace and FD-exec syscall mappings.
Paths строятся только из whitelisted source и independently pinned numeric
PID records. Arbitrary paths/environ/cmdline/secret input не принимаются.

Namespace fstat **не** выдаётся за nsfs/net namespace proof. Искомые ioctl/ABI
constants не угадываются; incompatible/unreviewed namespace probe отказывает.
FD enumeration может включать observer-owned temporary descriptor — отдельный
review acquisition protocol пока отсутствует. Protected config/journal pointers
не превращаются в observed permissions.

Capability bit mapping в pure status parser задаётся отдельно synthetic fixture
profile. Test bits 0/1 **не объявляются Linux CAP_NET_ADMIN/CAP_SYS_ADMIN bits**.
Full native `/proc/status` schema не принята: unknown/missing/duplicate projection
fields и unknown masks дают unreviewed. Не делается вывод, что synthetic projection
уже совместима с полным Linux source. Native guard срабатывает до любого OS read.

## 8. Security assumptions и фактически устранённые blockers

Устранены offline gaps №20.1b-8h: отсутствовавший bounded wire codec, versioned
message schema, nonce/request/epoch binding, per-direction ordering и irreversible
transcript failure; transfer slot/object identity вместо доверия FD number;
standalone helper credential/namespace sequence с independent post-check;
полный synthetic supervisor/helper/child lifecycle с reserve-before-dispatch,
parent-watch, cleanup/reap и late-publication refusal.

Остались native blockers:

- Actual Linux helper launch/bootstrap identity, SCM_RIGHTS/control FD peer
  protection и authenticated completion provenance. Hash/nonce не разделяют
  OS principals и не аттестуют protected IPC.
- UID/GID/userns/capability drop и минимальные privileges. Fixture helper/command
  principals из предыдущего OS model не назначаются на host. Candidate network/
  namespace-admin capabilities потенциально разрешают mutations; read-only argv
  не делают такую роль read-only.
- Trusted boot/nsfs/PID/start/FD/pidfd/NSID acquisition, protected binaries/config/
  journals/secrets, no inherited external sockets, capability/no-new-privileges
  kernel readback. Native proof не получается из supplied DTO или JSON.
- Held inode write exclusion и immutable dynamic loader/libraries/plugins/config
  closure; native FD-exec/build compatibility. Сравнение hash до/после не защищает
  от всех root writers. Broad privileges/Root остаются unresolved TCB.
- Native parent-death/descendant containment, lost-response supervision после
  reader/supervisor crash/restart, durable replay/kill integration. Fake reap не
  является Linux crash-recovery proof.
- Full tc/XDP/flowtable/sysctl/offload/external-FD/writer inventory, native timing,
  byte accounting, canonical round trip и controlled measurements.

Runner не получает helper/namespace/executable/control FDs, capabilities или
generic command surface. Сам Runner не считается trusted source invocation,
nonce, binary profile, identity или control transcript. Реальный запуск требует
отдельной authority boundary; ни `enabled=True`, ни old mock collector её не дают.

## 9. Offline tests

Добавлены **130 самостоятельных tests**, включая mutation subtests по каждому
из **272 binding bytes**. Это 130 tests плюс subtests, не пересчёт каждого byte
mutation в отдельный test. Positive baseline independently authored synthetic;
нативные lab artifacts не реконструировались и не помечались helper captures.

Покрыты binary fixed sizes/types/version/unknown kind/extra/truncated input,
fragmentation/stream failure latch, wrong nonce/phase/sequence/hash/counts,
duplicate/forged/late completion, fd catalog/kind/identity/substitution/renumbering,
boot/nsfs/PID reuse/NSID/config/journal/credential drift, failed privilege drop,
unexpected inherited/child FD, wrong executable, helper death/lost spawn/failed
FD-exec, timeout/incomplete stdout/stderr, TERM/drain/KILL/reap/close, parent death,
clock rollback/freeze, cancellation/concurrency/replay/circuit, immutable false
flags и exact denial existing PhysicalProbeGate.

Проверен explicit standalone positive end-to-end, child и helper reap, закрытие
owned transfer/control slots, независимая transcript validation, aggregate cap
и отсутствие native fallback. AST review ограничивает syscalls изолированным
guarded module. Fresh-import/constructor/explicit fake entry test запускает только
локальный Python unittest subprocess с os.open/fork/execve/setns/system/socket/
Popen blockers внутри проверяемой работы. Native helper process не создаётся.

Standalone run окончательного кода: **130 tests, OK, 9.413s**. Предыдущие 116
и 128 также прошли; review добавил parent-pidfd binding, failure latch, bounded
identity parsers, cleanup clock и session aggregate cases. Нет skips или
expected failures, подменяющих отсутствующие Linux proofs.

## 10. Полный Trusted Checker regression

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
| Network: прежние 801 + новые 130 | 931 | 0 | 0 | 0 | OK, 91.237s |
| Physical | 90 | 0 | 0 | 0 | OK, 9.581s |
| Live | 48 | 0 | 0 | 0 | OK, 9.107s |
| Runtime | 66 | 0 | 0 | 0 | OK, 7.944s |
| Shadow | 56 | 0 | 0 | 0 | OK, 2.103s |
| PoC | 166 | 0 | 0 | 0 | OK, 9.071s |
| **Всего** | **1357** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0. Логи проверены на отсутствие
ResourceWarning, skips, failures и errors. Прежние **1227** tests и новые
**130** прошли; Network теперь **931** tests.

Логи `/tmp/task201b8i-{network,physical,live,runtime,shadow,poc}.log`.
Suites запускались отдельными offline/mock processes независимо/частично
параллельно; durations не benchmark. Это полный Trusted Checker, не всех Django
приложений. Application regressions не запускались: application/writers не менялись.

## 11. Целостность и source digest

До изменений сохранён manifest `/tmp/task201b8i-baseline.json`: **313 artifacts**
шести Trusted Checker packages без caches и прежних `TRUSTED_CHECKER*.md`.
Добавлены пять production modules, два test files и report, всего **8 files**.
Прежние source/tests/reports/gates и native original artifacts/archives/matrices
не изменялись. Рабочие БД, .env, credentials и Docker sockets не читались.

Dynamic physical source manifest автоматически включает новые network modules:

- до: `4e017a364ee55480829eadd1349c677445dcf8a06370b46690bbff4f26318db1`;
- после: `5cafe53a289b9ddf8800d91be5b03c13ca8218d138bd62726883060f1e6a8de0`.

Проверено совпадение SHA-256 всех **313 baseline artifacts**, включая прежний
OS backend/collector/contracts/adapters, tests/reports, native originals/archives/
matrices, physical gates и live adapter. Добавлены ровно восемь перечисленных
files. Проверены syntax/AST, whitespace, local Markdown links, fenced blocks
и нумерация 12 разделов. Tracked Git diff пуст; прежние untracked files сохранены.

Старые approvals не обновляются/не переподписываются и автоматически не
переносятся. Новые reference digests не создают physical authority.

## 12. Следующий native review и решение

До первого **отдельно разрешённого** read-only experiment нужны:

1. Review native helper bootstrap/FD transfer/control peer, Linux identity/nsfs/
   PID generation/pidfd facts, capability-drop ordering и FD-exec ABI на exact
   builds. Подготовить native acquisition/setup реализацию и новые isolated fake
   driver tests без изменения старых guards ради activation.
2. Reviewed exact source/build/dependency/config/protection profile, protected
   reader/helper principals и namespace references. Закрыть broad privilege,
   external-FD, parent-death/descendant и durable operational obligations.
3. Новая отдельно reviewed activation authority, не conversion нынешнего
   invocation/result. Разрешение exact fresh dedicated VM/boot/binaries/source,
   roles, namespaces/FD acquisition, команды/лимиты/timing и artifact storage;
   SSH, если нужен, также задаётся отдельно. Данный report такого разрешения не даёт.
4. Первый bounded read-only case — один fixed link source на approved namespace
   FD, без install/setup/network mutations/packet sends. Сохранить raw stdout/
   stderr/protocol и independent identity/timing/ownership/reap accounting.
   Unknown требует stop/quarantine, без retry/adoption/host fixes.
5. Отдельный review originals/side effects и измеренного preflight timing перед
   расширением source plan/fault cases. Measurement 2s и existing physical gates
   сохраняются. Ownership journal/installer/rollback, canonical recipe/CT/raw/byte
   proofs и controlled probes остаются самостоятельными задачами.

**`V2-06a-H1 OFFLINE READY`**: protocol и полный synthetic lifecycle работают.
Native identity/privileges/IPC/execution не приняты; **OS READY отсутствует**.
`V2-06a-OS BLOCKED`, `physical_network_boundary_not_accepted`, `PhysicalProbeGate`
и live guard сохранены. Ownership/isolation/management/academic verification,
physical permit и security/production sign-off не выдаются.
