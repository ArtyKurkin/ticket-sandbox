# Trusted Checker v2: Dormant OS Read-only Backend — №20.1b-8h

21 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-06a-OS BLOCKED` для native execution.** Реализованы отдельные immutable
OS policy/FD/principal/process records, orchestration bounded process lifecycle,
descriptor resolver и закрытые concrete Linux FD/clock/pipe/pidfd/wait primitives.
Все доступные execution tests используют **только fake process/FD/clock/kernel
drivers**. Native helper, actual identity acquisition и activation authority не
реализованы как принимаемые boundaries; их отсутствие явно блокирует запуск.
Полный Trusted Checker regression: **1227 tests, OK**, включая **102 новых**.

Это reviewable implementation частичного dormant boundary, **не готовый к запуску
Linux collector**. `capture_os()` всегда отказывает до обращения к driver:
по умолчанию `disabled`, при `enabled=True` — `native_activation_unreviewed`.
Никакой mock approval, environment switch или supplied boolean не открывает
этот путь. Все concrete native methods дополнительно имеют closed guard.

`physical_probe_permitted=false`, `ownership_proven=false`,
`isolation_verified=false`, `management_policy_verified=false`,
`measurement_verified=false`, `continuous_attestation=false`.
Physical audit остаётся **`NOT READY`**; existing gates CLOSED, shadow-only.

Выполнены только локальные чтения source/attachments, pure Python/fake tests и
документация. Реальные backend OS reads, nft/ip/bridge/tc/Docker/setns, запуск
helper, namespace/sysctl/offload/route/firewall operations, packet operations,
SSH/VDS, academic writes и deploy не выполнялись. Django/Ticket Sandbox/Ledger/
Roadmap/achievements не менялись. Commit/push/rebase не выполнялись.

## 1. Архитектура и изменения

| Новый файл | Фактически реализовано |
|---|---|
| [`native_v2_os_contracts.py`](trusted_checker_network/native_v2_os_contracts.py) | OS principal/policy, namespace FD pins, timing proposal, executable/reader/child/helper records и unproven terminal |
| [`native_v2_os_reader.py`](trusted_checker_network/native_v2_os_reader.py) | Отдельный driver port, bounded process orchestration, identity checks, cancellation/reap и closed native entry |
| [`native_v2_os_fake.py`](trusted_checker_network/native_v2_os_fake.py) | Отдельный deterministic fake OS driver; прежний mock transport не заменяется |
| [`native_v2_os_linux.py`](trusted_checker_network/native_v2_os_linux.py) | Secure component resolver и guarded Linux primitives; native helper/identity/manifest composition закрыты |
| [`native_v2_os_reader_support.py`](trusted_checker_network/tests/native_v2_os_reader_support.py) | Независимый synthetic policy/process setup и fake descriptor kernel |
| [`test_native_v2_os_reader.py`](trusted_checker_network/tests/test_native_v2_os_reader.py) | 102 новых offline tests |
| Этот отчёт | Границы реализации, blockers и минимальный план дальнейшей проверки |

Новый package не создан. Прежний V2-06a collector, fake, capture contracts,
adapters, registries, v1, native originals, reports и physical gates не изменены.
Новый native module не импортируется прежним collector и не подключён к live API.
Ошибки старого fake не вызывают OS fallback.

`DormantOSReadOnlyBackend2` принимает independently pinned `OSReadPolicy2` и
binary-manifest digest. Constructor проверяет только supplied immutable values,
создаёт locks/cancellation flag и не вызывает driver. `exercise_fake_driver()`
допускает **exact** новый `FakeOSReadDriver2`; произвольный subclass или Linux
driver на эту ветку не попадают. `capture_os()` — отдельный закрытый entry.

## 2. Fixed sources, environment и structural template

Поддерживается исключительно неизменённый registry V2-06a
`tc-read-only-argv-v2-offline-1`, digest
`2cb033e374c5c50204030b9cb9982632b286c199c632b0cd72ab2490c171f345`.
Sources: nft, link, address, bridge_link, bridge_vlan, bridge_fdb,
route4/route6 и rule4/rule6. Paths — только `/usr/sbin/nft`, `/usr/sbin/ip`,
`/usr/sbin/bridge` с прежними exact fixed argv. Нет generic command, shell,
stdin data, user argv, namespace-name wrapper, PATH search или mutation API.

Environment — ровно `LANG=C`, `LC_ALL=C`. Нет наследования PATH, LD_*, HOME,
PYTHONPATH или произвольных caller env. В fake helper description stdin должен
быть `dev_null`, post-exec inherited descriptors — ровно 0/1/2; наблюдаемый
unexpected descriptor либо inherited stdin закрывает capture.

Existing `CapturePlan2` используется как **offline structural template**:
ordered requests, namespace references, binary/source refs, install/context/
approval/generation refs. Он остаётся `deterministic_mock_only` и не становится
OS permission или physical approval. Новая policy дополнительно фиксирует
helper/command principals, FD pins, config/executable/secret/journal review refs
и unmeasured timing proposal. Один digest не доказывает эти OS facts.

Missing planned source не превращается в `[]`. Успех означает exact coverage
**заданного plan**, не всего OS inventory. В result сохраняются все 18 прежних
`unsupported_surfaces`: tc/XDP/flowtables, forwarding/proxy/bridge-netfilter,
offloads, capabilities/FDs/writer control и другие обязательные proofs остаются
unobserved. Новые backend adapters для этих surfaces не объявляются готовыми.

## 3. Executable resolver и граница TOCTOU

Pure `resolve_executable2(kernel, expected_binary_reference, deadline_us)`
проверен через fake descriptor kernel. Concrete `LinuxDescriptorKernel2`
содержит mapping на `openat`-style `os.open(dir_fd=...)`, `fstat`, bounded read,
xattr, rewind и close. **Каждая concrete операция сначала отказывает closed
guard; ни один такой syscall в этом этапе не выполнен.**

Алгоритм resolver:

1. Открыть root FD и каждый component absolute allowlisted path относительно
   удерживаемого parent FD. Требуются O_NOFOLLOW/O_CLOEXEC, для directories —
   O_DIRECTORY. Нет `realpath` fallback, повторного открытия pathname для hash
   или исполнения через `/proc/self/fd/...` string.
2. На каждом component проверить directory/regular-file kind, root ownership,
   отсутствие group/world write и setid. Для executable дополнительно требуются
   execute bit, link count 1, отсутствие file capabilities, размер 1..64 MiB.
   Symlinked distro layout этим conservative profile не принимается автоматически.
3. Хешировать **тот же held FD** chunks≤65536 bytes с independent deadline и
   size cap, сравнить SHA-256 с independently pinned binary manifest.
   `--version` не вызывается и не заменяет hash/source review.
4. Сверить device/inode/mode/uid/gid/links/size/ctime до/после hashing, rewind FD.
   Закрыть parent FDs; при ошибке закрыть все newly opened owned descriptors.
   Close failure не выдаётся за успешный resolver outcome.

Так устраняется pathname reopen в проверяемой модели, но **не доказаны**
привилегированная in-place запись в held inode, executable/library/config
immutability, dynamic loader/libnftables closure, mount/source protection и
Linux FD-exec semantics на конкретной сборке. Результат имеет только
`descriptor_execution=required_not_native_proven`.

Поэтому native execution блокируется, а не выполняет hash→pathname exec.
`LinuxReadOnlyDriver2.open_executable()` ещё не имеет принимаемой native
manifest/deadline binding. `spawn()` закрыт отдельным namespace-helper blocker;
FD resolver сам не выдаёт право exec. Native syscall mapping не проверялся на
Linux; fake kernel проверяет алгоритм и protocol assumptions, не ядро.

## 4. Namespace FD и reader identity

`NamespaceFdPin2` связывает существующий namespace reference с явно заданными
FD number/generation/device и lookup PID/start ticks. Namespace reference
сохраняет boot UUID, inode, reader session, binding generation, FD-reference
UUID и peer/NSID refs. Pins входят в independently pinned policy.

`ReaderObservation2` требует exact OSPrincipal2, boot/session/epoch, reader
PID/start ticks, inherited FD inventory, namespace pins, отдельно наблюдённые
inode values и fd-open markers. Модель проверяется перед executable open,
перед spawn, во время каждого poll и после complete stream. Generation/PID
reuse, namespace inode/FD loss, session/boot/epoch drift закрывают результат.

Это проверки **supplied fake observations**. Native `observe()` отказывает;
actual boot/proc/namespace FD acquisition, nsfs type validation, PID bracketing,
reciprocal peer/NSID readback и independently authenticated reader session ещё
не реализованы. FD number сам по себе не identity. Нет adoption по namespace
name, PID, `ip netns list` или совпадению inode/ifindex.

Main Python/Django/Trusted Checker process никогда не вызывает setns. Future
helper должен быть отдельным standalone процессом с exclusive invocation,
reviewed namespace FD provenance, bounded control pipe и validated PID/pidfd
ownership. Helper entry, privilege transitions и FD-exec сейчас отсутствуют;
нет скрытого `preexec_fn`, fork/setns/exec или fallback в application process.

`HelperAttestation2` — только fake setup description: session/child/namespace,
held executable FD, command UID/GID/caps, post-exec descriptor set, stdin kind
и environment. Engine проверяет всё это отдельно от supervisor identity.
Статус `fake_helper_setup_only` нельзя переименовать в accepted native proof.
Native control protocol и credential acquisition требуют отдельного review.

## 5. Process lifecycle и bounded transport

`OSReadDriver2` задаёт explicit ports: clock/observe, open/executable-after/close,
spawn, poll, terminate/running/kill, drain/reap/close. Нет произвольных child PID
или command strings. Invocation связывает capture session, ordinal и request
UUID **до** spawn; supervisor обязан зарегистрировать owned child до dispatch.
Потерянный spawn response не отменяет obligation cancel/reap этого invocation.

Capture требует independently observed stdout EOF, stderr EOF, exit=0,
typed helper completion и post-read identity/executable equality. Exit может
предшествовать окончательному drain EOF; сам exit не означает complete output.
Supplied stdout `{"complete":true}` не является control acknowledgement.
Unknown/partial/truncated/oversized output никогда не публикуется как artifact.

| Bound | Проверка |
|---|---|
| Read chunk ≤16384 bytes/stream | До добавления bytes в буфер; превышение port contract отвергается |
| Nft stdout ≤262144 bytes | Прежний cap |
| Остальные stdout ≤1 MiB | Прежний per-source cap |
| Stderr ≤4096 bytes | Отдельный bounded buffer |
| Aggregate stdout+stderr ≤16 MiB | Учитываются все sources, до buffering следующего chunk |
| ≤4096 poll iterations/command | Finite fallback при faulty/frozen fake clock |
| Command ≤500000 µs | Independent supervisor monotonic/wall checks |
| Capture ≤2000000 µs | Absolute session fence, повторная проверка до terminal publication |

После нормального EOF/exit/handshake обязательны reap и pipe/executable close.
При timeout/interruption/kill/reader death/oversize/lost response engine
запрашивает TERM, выполняет bounded drain/grace, затем при необходимости KILL
и обязательную попытку reap. Drain имеет byte cap 65536 и максимум 16 iterations.
Cleanup deadlines proposal: TERM 50000 µs, drain 50000 µs, reap 100000 µs.

Clock/drain/terminate failure всё равно вызывает best-effort kill/reap/close,
но сохраняет `cleanup_unproven` и quarantine. Невозможность reap/close не
компенсируется successful stdout. Только separately proven owned invocation
может быть целью termination; широкого kill/cleanup/prune API нет.

Concrete dormant Linux mapping содержит bounded selector/read, отдельный
bounded control buffer, pidfd-based signals и finite WNOHANG wait/reap logic.
Он недоступен из-за guard, `_children` не заполняется без ещё отсутствующего
reviewed helper. Реальные pipes, pidfds, child registration, exec и descendant/
reader-death supervision **не испытаны и не приняты**. Эти методы нельзя считать
готовым работающим OS transport только по результатам fake driver tests.

Captured buffers очищаются при отказе; result не содержит partial artifacts.
Fake script bytes и fake observations уже выделены trusted test setup; caps
ограничивают accumulation engine, не caller allocation или Python RSS.
Internal artifacts содержат bounded raw bytes и не являются operator export.

## 6. Cancellation, replay и terminal

Отдельный nonblocking attempt lock запрещает concurrent capture. Cancellation
flag проверяется перед dispatch/poll и перед publication; state lock сериализует
kill и publication. Kill до terminal не позволяет поздним bytes/reap превратить
результат в success. После terminal тот же object возвращается без retry;
kill после publication сохраняет historical record, но закрывает admission.

`admit_fake_result` требует точный issued object, тот же backend instance и
exact request order/coverage. Copy/replace, foreign-instance replay и старый
result не принимаются. Это process-local fence, **не durable replay/kill journal**,
подпись или защита от модификации trusted Python memory. Новый fake setup не
создаёт actual OS approval. Неожиданные exceptions дают finite reason без
stdout/stderr/exception text; неизвестный cleanup остаётся quarantine.

## 7. DTO integration и timing proposal

Сохранены существующие immutable `CapturePlan2`, `CaptureRequest2`,
`CaptureSession2`, `CaptureTime2`, `InstallKey2`, binary/namespace references,
argv/byte limits и domain/false flags. Они используются как structural values.

Новые `OSCommandArtifact2`/`OSReadResult2` явно отделены от старого mock
`TransportCompletion2`. У artifact есть start/end, raw hashes через digest,
exact bytes, source/argv/profile refs, reader brackets, helper/child identity,
exit=0, EOF true и truncated/interrupted/timed_out false. Terminal выдаётся
только после full coverage и successful process cleanup. Fake result называется
`capture_preserved_in_fake_os_model`; OS provenance всегда unproven.

Прежние collector/adapters exact types не принимают новый result. Нет conversion
в old-issued receipt, recipe/profile/isolation verification, installation
ownership, EgressValidation, physical permit или academic evidence. Future
native origin/authentication/transport authority требует отдельного reviewed
boundary; новый DTO или hash его не создают.

`InventoryTimingProposal2` имеет acceptance `unmeasured_not_approved`. Это
proposal для preflight inventory, не short packet probe. Для local fake
exercise сохранены conservative 2s capture/500ms command; увеличения budget
через input нет. Cleanup budget не продлевает evidence/publication fence:
поздний reap/close приводит к unknown при final deadline check.

Фактическое время полного Linux inventory неизвестно. После отдельно
разрешённых measurements потребуется новый reviewed **preflight** timing
profile; 2s measurement limit прежнего verifier/live policy остаётся неизменным.
Нельзя объявлять выполнение inventory в этом bound по скорости unit tests.

## 8. Reader permissions и unresolved security review

`OSPrincipal2` сохраняет UID/GID/supplementary groups, exact effective/permitted/
bounding caps, empty ambient caps и требование no-new-privileges. Значения в
positive fixture synthetic: helper UID/GID 1001 с candidate CAP_SYS_ADMIN,
command UID/GID 1002 с candidate CAP_NET_ADMIN. Это **не** выданные permissions,
не accepted minimum capabilities и не конфигурация реального Linux host.

| Область | Review obligation / текущий предел |
|---|---|
| Namespace entry | Определить actual user/net namespace relations, минимальные entry privileges и безопасное снижение полномочий в dedicated helper |
| Nft/netlink reads | Установить exact permissions на approved kernel/build; широкие network-admin privileges потенциально дают writes, хотя argv диагностические |
| Proc/sys/FD acquisition | Закрытая bounded schema, boot/PID/start/nsfs proof, permission protection; native observer сейчас отсутствует |
| Executables и libraries | Independently pinned source/build/dependency closure, immutable/config/mount protection; hash held FD не исключает root in-place writer |
| Credentials | Actual capability/no-new-privileges setup/readback и protected supervisor/helper identities; digests/HMAC этого не заменяют |
| Descriptors/stdin | Only-owned pipes/pidfd, dev-null stdin, no external/inherited sockets, CLOEXEC и закрытие namespace/executable/control FDs до/при exec |
| Secret/config/journals | Защита от reader writes и untrusted search/config paths, review actual owners/modes/ACLs/mounts; pointers не OS facts |
| Child supervision | Lost-response escrow, parent-death/descendant handling, PID/pidfd generation, cancellation/reap/restart; native helper не запущен/не реализован как принимаемый |
| Source coverage | Tc/XDP/sysctl/flowtables/offloads/external FDs/writers не реализованы; десять команд не полное security inventory |

Read-only argv не делают principal read-only. Nft/ip/bridge binaries, libraries,
netlink reads, namespace FD opens и child processes имеют kernel interactions,
временные buffers и возможные зависимости от configuration/plugins. Без review
эти эффекты не объявляются безопасными. Root/daemon admin остаются TCB.

Блокирующие native пробелы: accepted activation authority; helper launch с
namespace/credential/FD-exec guarantees; actual identity observer; binding
independent binary manifest/deadline к native driver; доказанная executable/
dependency write exclusion и authenticated completion protocol. В коде для
этих мест предусмотрен отказ, а не weak fallback.

## 9. Tests и полный Trusted Checker regression

Новые **102 tests** используют только fake process/FD/clock/kernel drivers.
Positive baseline — независимо authored policy, по одному source либо полный
30-source synthetic plan. Native syscall mapping не исполняется.

Проверены default OFF/import/constructor/no-I/O, wrong executable/path/symlink/
hash/source/permissions, parent/path walk и bounded held-FD hash, mutation/close
faults, wrong helper/command UID/caps/groups, inherited FD/stdin/environment,
namespace inode/generation/PID reuse/session/epoch, source/child substitution,
stdout/stderr/aggregate caps, EOF/exit/control completeness, timeout/drain/TERM/
KILL/reap/close, lost spawn response, interruption/reader death, clock rollback/
freeze, kill/replay/concurrency/late publication, closed physical gate и old
collector isolation. Finite reasons не раскрывают arbitrary errors.

AST review проверяет изоляцию syscalls в native module и first closed guard
у его concrete methods. Fresh-import/constructor test выполняет только локальный
Python unittest subprocess с блокировкой os.open/fork/execve/setns/system,
Popen и socket внутри проверяемой работы. Реальных диагностических subprocess,
namespace/helper или network operations нет.

Standalone окончательного кода: **102 tests, OK, 3.369s**. Skipped/expected-failure
tests отсутствуют; отсутствие native execution/proofs не маскируется green
Linux test. Первые 86 tests и промежуточные 100 также прошли; ещё две проверки
закрепили immutable completion flags и wall-time cap.

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
| Network: прежние 699 + новые 102 | 801 | 0 | 0 | 0 | OK, 90.342s |
| Physical | 90 | 0 | 0 | 0 | OK, 9.677s |
| Live | 48 | 0 | 0 | 0 | OK, 9.398s |
| Runtime | 66 | 0 | 0 | 0 | OK, 7.488s |
| Shadow | 56 | 0 | 0 | 0 | OK, 2.073s |
| PoC | 166 | 0 | 0 | 0 | OK, 9.328s |
| **Всего** | **1227** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0. Логи проверены на отсутствие
ResourceWarning, skips, failures и errors. Прежние **1125** tests и новые
**102** прошли; Network теперь **801** tests.

Логи `/tmp/task201b8h-{network,physical,live,runtime,shadow,poc}.log`.
Suites выполнялись отдельно/частично параллельно, offline/mocks; durations не
benchmark и не inventory timing. Это полный Trusted Checker, не Django проекта;
application regressions не запускались, application source/writers не менялись.

## 10. Целостность и source digest

До изменений сохранён `/tmp/task201b8h-baseline.json`: **306 artifacts** шести
Trusted Checker packages без caches и прежних `TRUSTED_CHECKER*.md`. Новые files:
четыре production modules, два test files и этот report, всего **7**. Старые
files и native fixtures/archives/matrices не редактировались. Рабочие БД, .env,
credentials и Docker sockets не читались.

Dynamic physical source manifest включает новые top-level network modules:

- до: `902711ce1fd49b777f5d27884331fe33474f2b2b6813f51317df90ebd29375e1`;
- после: `4e017a364ee55480829eadd1349c677445dcf8a06370b46690bbff4f26318db1`.

Проверено совпадение SHA-256 всех **306 baseline artifacts**, включая прежний
collector/contracts/adapters, tests, native originals/archives/matrices, physical
gates и live adapter. Состав additions — ровно семь перечисленных files.
Проверены syntax/AST, whitespace, local Markdown links, fenced blocks и 12
разделов. Tracked Git diff пуст; прежние untracked files сохранены.

Старые approvals не обновляются, не переподписываются и не переносятся
автоматически. Ни source digest, ни OS policy refs не создают authority.

## 11. Минимальный план первого отдельного read-only испытания

**Ни один шаг не выполнен и разрешение не выдано.** Сначала нужны закрытие
code blockers и отдельный security review; добавление flag или подписи поверх
offline policy не заменяет эту работу.

1. Спроектировать и реализовать separately reviewed standalone helper/supervisor:
   held-FD execution без pathname reopen, namespace/credential acquisition и
   снижение privileges, fixed environment/dev-null stdin, controlled FD allowlist,
   nonce-bound completion, owned-child/pidfd/lost-response/reap/parent-death model.
   Добавить offline driver/helper fault tests до возможности native activation.
2. Принять exact native authority/identity/build/source/config/protection profile
   и code review actual Linux calls. Не выдавать разрешение из нынешних mock DTO.
   Отдельно проверить fs/nsfs/fd-exec/dependency closure и необходимый privilege
   scope на approved kernel/build; не выполнять автоматические fixes.
3. Получить отдельное разрешение exact fresh dedicated VM/boot/source/binaries,
   reader principal/capabilities, namespace FD acquisition, точного одного source,
   stdout/stderr/clock/cancellation caps и protected artifact path. SSH access,
   если нужен, также задаётся отдельно. Management path не изменять.
4. Первый bounded run: один `link` source через заранее approved namespace FD,
   без packet probes, без setup/install/firewall/route/sysctl mutations. Сохранить
   exact executable FD/hash/identity, argv/env, principal/FD/PID-generation checks,
   wall/monotonic intervals, raw stdout/stderr, exit/completion/reap accounting.
   Unknown/truncation/identity drift — stop/quarantine, без retry/fallback.
5. Review original artifacts и фактических privileged effects; только затем
   отдельное разрешение расширенного source plan host/runner/target. Missing
   source не реконструировать, unknown schema не исправлять на host. Провести
   отдельно approved interruption/timeout/reader-death faults на owned helper.
6. Измерить inventory stage/end-to-end timing. Принять отдельный measured
   preflight profile при необходимости, сохраняя 2s packet measurement limit.
   После каждого run проверить только owned helper/FD/process cleanup; отсутствие
   reap не скрывать как success и не выполнять generic host cleanup.

Такой опыт всё равно не устанавливает canonical recipe и не доказывает isolation.
Ownership journal/witness, installer/rollback, CT/raw/byte proofs, canonical
kernel round trip и packet measurements остаются отдельными задачами. Чужие
historical resources не adopt/не удалять. Raw evidence требует protected storage
и отдельного bounded operator export.

## 12. Решение

**`V2-06a-OS BLOCKED`**: offline orchestration, FD resolver и dormant primitives
подготовлены к review, но native executable/namespace/helper/identity authority
composition отсутствует. `LinuxReadOnlyDriver2` нельзя считать готовым работающим
collector или запускать на VDS даже с `enabled=True`. Текущий native entry
отказывает до OS I/O; fake path остаётся явно synthetic.

Никакой snapshot/hash/argv success не заменяет writer control или continuous
attestation. Все existing physical gates, `PhysicalProbeGate`, live adapter и
`physical_network_boundary_not_accepted` сохранены; physical acceptance
**`NOT READY`**. Нет physical permit, ownership/isolation/management verification,
academic evidence, live activation или production sign-off.
