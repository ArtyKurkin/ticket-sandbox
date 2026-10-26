# Trusted Checker: Physical Network Backend — №20.1b-4

19 октября 2026 · `feature/roadmap-react` · база `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

## 1. Реализованные компоненты и статус

Добавлен самостоятельный `trusted_checker_physical`: dormant Linux nft adapter, independent readback, read-only preflight, bracketed namespace inventory, privileged socket helper, AF_PACKET injection/capture, native kernel NFTRACE decoder/correlation, authenticated **unknown** observation report и default-OFF reviewed activation path. Проверки — только offline/mocks; **495 tests OK**. Никакие реальные Docker/kernel/network/namespace операции не выполнялись.

**Физический collector не выдаёт полный positive matrix receipt.** Исследование native NFTRACE выявило непреодолённый для выбранного механизма continuity gap: kernel notification не имеет непрерывного stream sequence; при ошибке выделения сообщения возможен тихий пропуск. Даже полная наблюдавшаяся цепочка не подтверждает loss-free event continuity. Поэтому итог остаётся `unknown/native_nftrace_continuity_unproven`, `matrix_complete=false`, `probe_permitted=false`. Синтетического success fallback нет.

Это реализованный физический I/O boundary для отдельного review, **не runtime acceptance и не готовый end-to-end Sandbox deployment**. Старый `physical_network_boundary_not_accepted` не изменён. Новый `PhysicalProbeGate` также безусловно запрещает release; он не конвертирует v4 observations в legacy `EgressValidation`/authority token.

Изучены [network validation №20.1b-3](TRUSTED_CHECKER_NETWORK_VALIDATION.md), [live implementation №20.1b-2](TRUSTED_CHECKER_LIVE_RUNTIME_IMPLEMENTATION.md), [runtime provenance №20.1b-1](TRUSTED_CHECKER_RUNTIME_PROVENANCE.md), текущие network/live/runtime исходники и contracts. Новая реализация использует versioned sibling adapter для lifecycle NetworkInstaller; existing `TrustedRulesInstaller` сохраняет exact `MockNetworkHost` boundary. Live injection через duck typing/monkey patch не добавлен.

## 2. Созданные и изменённые файлы

Все файлы ниже новые. **Existing files не изменены**: SHA-256 проверка всех116 baseline artifacts подтвердила их неизменность, включая прежние отчёты, packages/tests и policy v2/v3.

| Файл в `trusted_checker_physical/` | Назначение |
|---|---|
| `__init__.py` | Без bootstrap, открытия client/socket или исполнения программ. |
| `contracts.py` | Physical profile/approval, role-separated HMAC domain, signed transaction trace. |
| `authorization.py` | Explicit enable/permission, absolute+monotonic deadlines, recovery-only reads, one-use issued batches. |
| `activation_path.py` | `ReviewedActivationPath`, OFF по умолчанию; нет CLI/unattended setup. |
| `io.py` | Fixed Linux commands, restricted proc/config reads, bounded Popen streams/timeouts; arbitrary nft bytes отвергаются. |
| `docker_readonly.py` | Только approved endpoint/witness и info/list/exact-ID inspect; без Docker mutation API. |
| `preflight.py` | Kernel/nft/config/modules/capabilities/sysctl/ruleset/bridge/workload/offload/XDP/tc checks. |
| `inventory.py` | Docker/proc/netns/veth/IP identity до/после наблюдения. |
| `rules.py` | Physical v4 recipe: own tables, v3 isolation rules и explicit runner-bound nftrace marker. |
| `journal.py` | Отдельный0600 `*.physical.sqlite3`, immutable docs/receipts/intents, circuit, fsynced stop latch. |
| `installer.py` | Durable dispatch, atomic apply, separate readback, exact ownership, quarantine и trace-gated recovery. |
| `namespace_helper.py` | Изолированный host Python helper: только CLONE_NEWNET + создание/передача bound packet FD + exit. |
| `packet_io.py` | Exact namespace-FD broker, SCM_RIGHTS/credentials, AF_PACKET stats, NFTRACE socket, bounded peer ARP. |
| `trace.py` | Binary native Netlink/NFTRACE parser, source/header/attribute validation. |
| `collector.py` | Fixed finite probes, ingress/delivery/response/drop correlation, unknown report/sealer, closed PROBE gate. |
| `policy_proposal.py` | Отдельный immutable HTTP policy v3 proposal; не принимается authority/Runner. |
| `artifacts.py` | SHA-256 manifest production Python sources physical/network/live/runtime/shadow. |
| `tests/__init__.py`, `tests/support.py` | Explicit fake kernel/Docker/packet fixtures и временные journals. |
| `tests/test_installer.py` | Authorization, apply/readback/lost reply/recovery/concurrency/kill/rollback. |
| `tests/test_preflight_inventory.py` | Kernel/profile/host/namespace/endpoint/attachment negative cases. |
| `tests/test_collector.py` | Packet/drop/NFTRACE/auth/loss/unknown semantics. |
| `tests/test_dormant_io.py` | Mocked syscall/process/helper/FD boundaries, OFF path, policy/timing/isolation. |

Итого23 Python files и этот отчёт `TRUSTED_CHECKER_PHYSICAL_NETWORK_BACKEND.md`. No changes в Django/Sandbox/Celery, CheckRun/Ledger/completion/achievements/платине, training tasks, historical evidence/orphan. Existing untracked `docs/` не затронуты. Git tracked diff пуст; commit/push/rebase/deploy не выполнялись.

## 3. Linux kernel/nftables requirements

Исходный **review profile**, а не список реально испытанных дистрибутивов:

- Новая dedicated Linux VM; один approved daemon/session, bridge tcsh0, только exact known task/runner. Shared host/старую VDS использовать нельзя: global bridge default-drop hooks по-прежнему затрагивают остальные bridges host.
- Kernel series6.8 или6.12; nft1.0.9/1.1.0/1.1.1. Другие версии отвергаются до mutation и требуют отдельного compatibility review. Строка версии не доказывает kernel behavior.
- Config support BRIDGE/VETH/NF_TABLES/NF_TABLES_BRIDGE/NF_CONNTRACK/NF_CONNTRACK_BRIDGE/NFT_CT/PACKET/NETFILTER_NETLINK; для module-backed features соответствующие modules уже загружены. Код не вызывает modprobe и не пытается активировать отсутствующую поддержку проверочной mutation.
- Native bridge conntrack, bridge filter priority0, inet guards−310. `br_netfilter` bridge-nf-call-{iptables,ip6tables,arptables}=0; отсутствующий/нечитаемый sysctl сейчас даёт unknown, не догадку об отключении.
- Полный ruleset не содержит чужих tables/hooks/flowtables; нет чужих Docker containers, включая stopped. Нет XDP, tc ingress/egress filters или bridge VLAN filtering. Offloads в строгом профиле должны быть off; `[fixed] on`/неизвестный feature означает STOP, а не автоматический ethtool -K.
- Python с `os.setns` (Linux Python≥3.12), trusted host binaries по фиксированным paths `/usr/sbin/{nft,ip,tc,ethtool}` и `/usr/bin/{uname,nsenter}`; совместимость конкретных binary paths/JSON следует проверить отдельно.
- Для полного helper path effective CAP_NET_ADMIN/CAP_NET_RAW/CAP_SYS_ADMIN, доступ к approved proc/ns descriptors, достаточные packet buffers, разрешённые setns/raw sockets/SCM_RIGHTS. Текущий strict preflight отвергает active seccomp; минимальный production seccomp/LSM profile не реализован.

Kernel config/module dependencies сверялись с [Linux bridge Kconfig](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/bridge/netfilter/Kconfig) и [Netfilter build definitions](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/netfilter/Makefile). Это source analysis; VM/kernel не inspected. Профиль намеренно может отвергать стандартную VM с fixed offloads/особым JSON. Его совместимость не объявляется подтверждённой.

## 4. Trust boundary

```text
installed operator keys + signed exact physical approval + explicit enable
  → restricted host IO / readonly daemon / dedicated journal
  → installer → kernel nft transaction → independent complete readback
  → exact namespace inventory → isolated host socket helper
  → AF_PACKET observations + direct kernel NFTRACE
  → independent correlation + signed UNKNOWN report
  → closed PhysicalProbeGate (HTTP release unavailable)
```

Trusted: dedicated host/kernel, installed source/binaries, configured daemon endpoint/session witness, journal owner, operator/observer/collector principals и installation code. Untrusted: task/Runner/app output, names/labels, HTTP content, forwarded JSON claiming kernel origin. Digest/HMAC/PID themselves не являются hardware attestation.

Installer и readback имеют разные IO instances; actual OS/process separation ещё не установлена. HMAC verifier хранит симметричный key material и входит в TCB. `ReadOnlyDocker` ограничивает операции приложения, но Unix daemon credential остаётся административным по природе: это **не** доказанная OS-level readonly Docker role. Runner и task эти credentials не получают.

Keys передаются trusted installation через typed principals, не через env/request/approval, не сохраняются в journal/report и не попадают в Runner. Socket helper запускается отдельным `python -I` process с очищенным env, close_fds и только namespace/control FDs; signing keys в него не передаются. Сам privileged helper/parent и их executable integrity входят в TCB. Host/Python owner способен обойти локальные checks; hostile Python plugins не поддерживаются.

## 5. Installer lifecycle

`PhysicalNetworkInstaller` повторяет правила durable NetworkInstaller, но использует отдельные v4 profile/store/proof domain. Approval фиксирует host/daemon/network/runtime binding/generation, source digest, обе immutable recipes, dedicated VM, permission и expiry≤1h. Root UID не создаёт разрешения.

```text
verified signed approval + fixed compiler/source correspondence
 → full read-only preflight + exact namespace inventory + previous readback
 → committed install intent/dispatched + one-use issued batch
 → fixed atomic nft -j -f - transaction
 → independent full rules readback + exact kernel table handles
 → persisted ownership BEFORE final identity/kill/deadline checks
 → immutable verified_readback receipt (offline_verified in mocks)

any ambiguous apply/readback/identity/deadline
 → quarantined + stop latch + circuit
 → no retry/re-apply
 → separate ownership recovery and/or explicit exact-owned bootstrap rollback
```

Первые tables создаются exclusive `create`; name collision не принимается за ownership. Subsequent replace удаляет только две **proven owned kernel table handles** и добавляет fixed approved rules в одной batch. Замена таблицы на same-name/different-handle отвергается readback/transaction. Нет flush ruleset, wildcard deletion, prune или универсального nft API. Semantics atomic JSON batch/handles сверяются с [официальной nftables документацией](https://netfilter.org/projects/nftables/manpage.html); настоящий parser/kernel в этой задаче не запускался.

Exit0 недостаточен: независимый reader получает полный ruleset, сравнивает table/chain/rule structure и только затем фиксируются ownership/receipt. Lost response не разрешает adopt по нынешнему readback или повтор mutation. Dispatch переживает SystemExit/crash; duplicate того же payload возвращает прежнее состояние/receipt, conflict отвергается. Несовпадение preflight/readback также закрывает circuit до mutation.

Recovery требует отдельного observer-signed `TransactionTrace`: issued intent/request/transaction digest, original host/daemon binding, generation, exact handles и commit window. Он перепроверяется текущим independent readback и preflight. Recovery восстанавливает **только ownership**, переводит незавершённую operation в quarantine и разрешает лишь отдельный rollback; не active adoption/PROBE/verdict. Producer независимого committed transaction trace ещё не реализован. nft monitor echo, exit0, labels и operator boolean не заменяют его; при его отсутствии outcome остаётся unknown.

Rollback — новый explicitly requested bootstrap operation с доказанными handles, текущими host/daemon/network facts и отдельным deadline. Он доступен после stop/approval expiry и выхода runner; privileged recovery reads не разрешают обычные launches. Ошибка rollback остаётся unresolved. Успешный rollback после ошибки не снимает latch/circuit. Generic delete API для закрытия всех firewall resources не добавлен.

## 6. Collector architecture

`BoundedPhysicalCollector` сначала требует issued active state/readback и exact inventory. Прямой physical composition принимает только actual Linux ports, а injected fake socket/provider допустим исключительно с `offline_simulation`; такие journals не открываются как physical. Он не использует existing mock `Capture`/`MatrixReceipt` как физическое evidence.

`NamespaceSocketBroker` открывает **approved proc namespace FD**, проверяет inode/start и запускает локальный manifest-pinned helper. Child делает только `setns(fd, CLONE_NEWNET)`, разрешает interface по exact ifindex, создаёт bound AF_PACKET socket, передаёт его SCM_RIGHTS и завершается. Parent проверяет SCM_CREDENTIALS sender PID/UID, reply inode/ifindex, FD domain/type/protocol/interface и заново inventory. Неверный sender/truncation/extra FDs закрываются без injection. Target mount/PID/user namespace не присоединяются; target filesystem/binaries и Docker exec не используются.

Три packet observation points: runner namespace, target namespace и host runner-veth. Отдельный host AF_NETLINK/NETLINK_NETFILTER socket подписывается только на NFTRACE group9. Нет shell/URL/DNS resolver или proxy. Fixed peer ARP priming решает ARP learning для synthetic TCP SYN; только одобренная пара MAC/IP и один bounded request, без соседнего discovery.

15 header probes покрывают прежние10 групп. Physical v4 добавляет96-bit correlation token для UDP в bounded transport dump и явный source-MAC/VLAN spoof probe; TCP использует context-bound sequence/ACK. Templates нельзя задавать через операторский HTTP/JSON request. Priming и probes — будущие **mutating** packet operations, требующие отдельного разрешения.

Capture ограничен256 events,128-byte frames,2s packet window и общим absolute deadline. AF_PACKET statistics проверяются до/после (с учётом reset-on-read), counters сравниваются с прочитанными events. MSG_TRUNC, unread packets, drops, losing/checksum/VLAN offload flags, Netlink overrun/error либо unknown framing не дают положительного результата. Ancillary data и raw errors не экспортируются.

## 7. Namespace identity checks

Inventory использует только exact known container IDs и approved endpoint. Read-only list всех containers нужен лишь для обнаружения чужих workloads, **не** для adoption/deletion. Daemon witness сравнивает original boot/socket/process identity и info.ID до/после API observations.

Для обоих namespaces проверяются:

- Full Docker ID, PID, running/status и paused/restarting/dead flags, Docker StartedAt/RestartCount0.
- `/proc/PID/stat` field22 с корректным разбором comm и namespace inode до/после; PID/name совпадение без ticks/inode недостаточно.
- Единственная non-loopback interface, её ifindex, MAC, approved IP, reciprocal host iflink/link_index и veth type.
- Exact host veth name **вместе с** ifindex/peer binding и bridge master; лишние bridge ports/networks запрещены.
- Exact NetworkID/EndpointID/IP/MAC из container inspect и network membership read; дополнительный attachment отвергается.
- Полное равенство Docker State/NetworkSettings/RestartCount и host link observations до/после.

Host netns/boot и source manifest также закреплены. Native observations остаются **bracket evidence**, не непрерывной аттестацией. Short attach/detach между samples требует защищённого event stream; такого completeness proof здесь нет. Администратора daemon/host inventory не изолирует.

## 8. Packet/drop evidence и честный unknown

Native binary parser проверяет kernel sender address pid0, Netlink header pid/seq/type/family, nested attribute lengths/types/duplicates, approved table/chain и runner ingress ifindex. Он не принимает JSON из оператора или stdout приложения. NFTRACE не содержит отдельного hook number: chain→hook связь подтверждается полным independent rules readback. Первое packet-bearing событие связывается с exact probe; subsequent policy-drop должен иметь тот же trace ID. Foreign/stale packet, trace-ID collision или пропущенная связь отвергаются.

| Путь | Необходимые observations |
|---|---|
| Allowed8080 | send → host physical ingress → target namespace delivery → matching SYN-ACK/RST-ACK → runner receive. Проверяются MAC/IP/ports/sequence/ACK/checksum. |
| Denied destination/port | send → physical ingress → **kernel base-chain policy drop**, с cached exact packet и approved rules/ifindex provenance. Silence не считается drop. |
| Broken loopback app | Valid delivered RST даёт `path_open_rst`: сетевой путь работает, приложение снаружи не слушает. Это не network isolation failure. |
| Fixed app | Valid SYN-ACK даёт только `path_open_synack`; HTTP200/body/full task success из него не следуют. |
| Timeout/missing drop/capture loss | Unknown с finite reason; не guessed failed/pass. |

Порядок чтения независимых AF_PACKET/Netlink queues не принимается за wire order: связь проверяется по конкретному frame/nonce/ACK и observation point, а не по порядку select callbacks.

**Почему full matrix запрещена даже при15 observations:** в исследованном [Linux NFTRACE implementation](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/netfilter/nf_tables_trace.c) notifications формируются с sequence0, а отказ allocation может завершить notify без сообщения. Это не исправляется локальным счётчиком Python или отсутствием ENOBUFS. Все bounded AF_PACKET counters не доказывают полноту kernel trace stream. Поэтому `CollectionReport` допускает только unknown и false completeness/release flags; `PhysicalProbeGate` закрыт даже для вручную сконструированного report. Требуется другой reviewed loss-accounted mechanism либо отдельно согласованная более слабая semantics; её здесь не вводили.

AF_PACKET privilege/statistics semantics изучены по [Linux Packet MMAP documentation](https://www.kernel.org/doc/html/v6.12/networking/packet_mmap.html); trace attributes/group — по [NF_TABLES UAPI](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/netfilter/nf_tables.h) и [NFNETLINK UAPI](https://raw.githubusercontent.com/torvalds/linux/master/include/uapi/linux/netfilter/nfnetlink.h). Эти источники не заменяют испытание kernel выбранной VM.

## 9. Authorization, transport и сохранённые invariants

`ReviewedActivationPath(..., enabled=False)` не открывает host socket/process/journal. Для future use нужны одновременно explicit enable, Linux, approved dedicated VM/binding, role-authenticated document, current expiry/permission, matching fixed recipes/source и проверенный host. Есть permissions review_only/readonly/install_and_collect; root/capabilities не заменяют их. Schema/domain v4 не принимают mock v3 approval/receipts или synthetic approval.

Physical IO не принимает raw nft payload: только one-use batch, выделенный installer **после** durable dispatch и связанный с тем же absolute deadline. Finite command allowlist не включает exec/build/run/pull/prune/network mutations/sysctl/modprobe. Proc reads не допускают environ, произвольные PIDs/credentials/target files. Private Python methods не являются sandbox против privileged caller.

Collector unknown report можно запечатать collector-principal HMAC только при совпадении с exact persisted issued report/origin/scope. Role/key разделение operator/observer/validator/collector проверяется; no signature/key/raw frame хранится в public report. Helper transport — local socketpair + kernel SCM credentials/FDs; external RPC/TLS service и actual role deployment ещё отсутствуют. Keys должны оставаться в защищённой installation/service memory с OS ACL, вне helper/target/Runner; key file loader не добавлен.

Ни физический observer, ни installer не создают CheckRun/TechnicalCheckExecution или учебный verdict. Runtime Authority fences, durable container ownership, immutable terminal CAS, kill/circuit и exact cleanup не изменялись. Approved HTTP scope остаётся external-only; loopback/application authenticity/persistence и platinum не доказываются. Старый live adapter guard не обходится даже новым enable.

## 10. Deadline и timing budget

Текущие live v2 policy/Runner сохраняют8s и digest `5f1c67299d60026999d7a6484d83c01d2bab3c3c04470466af50391095d9e527`.

Добавлен отдельный `service-bind-localhost-physical-peer-v3-proposal`, version3, mode proposal_only_do_not_execute, activatable=false, digest:

```text
2afa21c9be3e5ae7237eb9180672e8c1619d569acbb0cf0a19c0f427b57d7e83
```

Он сохраняет GET numeric IPv4:8080 `/`,200/body≤1024/trailing-LF-only, external scope, HTTP2s и ссылается на прежний30s proposal. Cleanup отмечен отдельной стадией3s. Это **не утверждённый live budget**; ни RuntimeApproval, ни Runner его не принимают. Physical review profile digest: `71e1307b62c9354abed89469244fa34179d82bf8fa37599ccbe210a3455c9ec1`.

8s не покрывают worst-case create/start3+3 и HTTP2 плюс остальные стадии.30s тоже пока не доказаны: current conservative adapter повторяет preflight/inventory и несколько external reads, каждый с cap3s. Сумма их worst-case caps больше30s; подготовка socket/helper и trace overhead не измерены. До новой live policy нужны реальные measurements, review размещения stable preflight вне critical run и сохранение обязательных свежих per-run identity/readback checks. Нельзя выдать успешно выполненные fake1.5s windows за SLA.

`Deadline` фиксирует absolute wall и monotonic end один раз, проверяет rollback clock/expiry и не продлевается retry. Popen bounded по обоим streams и local≤3s, capture window≤2s; cleanup/recovery имеет новый отдельный **операционный** budget и не возобновляет runner. Timings агрегируют count/total/max для повторных stages (nft reads/apply, daemon reads, preflight/inventory/socket setup/injection/collector); nested totals не складывают в run duration. Истечение deadline запрещает late receipt/PROBE. Already-sent kernel operation нельзя отменить задним числом; kill/timeout может оставить unknown ownership. Hard realtime не заявляется.

## 11. Offline tests и проверка источников

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_physical/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_network/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_live/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_runtime/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_shadow/tests -t .
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t .
```

| Suite | Результат |
|---|---|
| Новый physical | **90 tests OK**,4.109s |
| Existing network | **69 tests OK**,13.089s |
| Existing live | **48 tests OK**,14.074s |
| Existing runtime | **66 tests OK**,12.460s |
| Existing shadow | **56 tests OK**,3.004s |
| Existing PoC | **166 tests OK**,14.609s |
| **Итого** | **495 tests OK**, без skips |

Existing405 suites выполнялись параллельно; это не performance benchmark. Логи `/tmp/task201b4-{physical,network,live,runtime,shadow,poc}.log`. Последний physical прогон — после завершения code changes; прежние packages во всех116 baseline files byte-identical.

Покрыты unsupported kernel/nft/modules, conflicting/foreign hooks/tables, offload/XDP/capabilities, foreign workload, PID/netns/start/veth/MAC/IP/EndpointID/restart/extra-attachment drift; failed/lost atomic apply, immutable duplicate/crash, exact handles/trace recovery и rollback failure; forged native events/credentials/capture signatures, stale packet/sequence, missing drop, RST/SYN-ACK против timeout, capture loss/truncation, UDP nonce/source spoof/ARP whitelist, kill/deadline, expiry-only rollback и no positive from mock.

Physical boundaries тестируются **с заменой syscalls/process/socket/daemon operations**, включая host Popen streams, helper setns, SCM_RIGHTS sender/FD cleanup и NFTRACE receive. Реальные nft parser/netlink/nsenter/setns/packet sockets не вызывались. Fresh отдельный Python import всех новых модулей под запретом socket constructor/Popen/setns прошёл; Docker/Django даже не импортированы. AST/syntax и baseline hash checks выполнены. Django regression tests заново не запускались: integration/writers не менялись, старые результаты не приписываются этому этапу.

## 12. Ограничения реализации

1. Native NFTRACE continuity blocker описан выше; positive independent matrix и HTTP release недоступны. Не реализованы BPF/NFLOG loss-accounted replacement и защищённый continuous topology stream.
2. Independent committed-transaction trace producer не реализован. Lost nft outcome без такого evidence остаётся quarantine; generic readback не восстанавливает original ownership.
3. Physical backend не проверен на Linux. Реальные nft JSON normalization/exclusive create/delete-by-handle/atomicity, packet checksums/offloads, ARP/TCP noise, kernel hook ordering, capabilities/LSM/exec inheritance и actual namespace-FD semantics — runtime pending.
4. Initial **host-only bootstrap setup approval/ownership до provisioning** и безопасная передача между generations остаются отдельным prerequisite. Текущий per-pair physical approval уже содержит known running namespace tuples. Их нельзя выдумать заранее для empty VM или объявить готовым complete provisioning path. Coexisting old global bootstrap tables/new approval не принимаются автоматически.
5. Нет unattended installer, remote service/role isolation, key lifecycle/HA/backup/retention или generic teardown. Manifest покрывает reviewed Python sources, но не аттестует kernel/packages/host. Current source manifest: `789994f22b6d2a1967e72712af20b483779c7ccc17bd81a8a1626606d3bdf423`; изменение source требует нового approval.
6. Нет genuine Sandbox attempt/ordinary-generation provenance или automatic post-check integration. Supplied IDs и scoped network observations не меняют academic history, full task success или достижения.

Эти gaps не закрываются495 unit tests или совпадением HMAC. Работа остановлена на review физического boundary, не на заявлении работающей network isolation.

## 13. Точный план read-only preflight новой VM

**Ниже команды не выполнялись.** Они предназначены только для новой VM после отдельного согласования read access, exact host/endpoint и способа безопасного хранения output. Не запускать на старой VDS. Нет auto-context/DOCKER_HOST discovery. Вне согласованных checks не печатать полный inspect/env/credentials.

Этап A — host facts без namespace entry/injection/mutation. Предварительно одобренный оператор сопоставляет результаты с configuration/asset inventory; placeholders ниже заменяются **только заранее approved IDs**, не trainee input.

```sh
/usr/bin/uname -r
/usr/sbin/nft --version
cat /proc/sys/kernel/random/boot_id
cat /proc/modules
cat /proc/self/status
cat /proc/sys/net/core/rmem_max
cat /proc/sys/net/core/rmem_default
# Читать exact /boot/config-<полученная и проверенная kernel version>.
# Host machine-id сопоставлять приватно по digest, не публиковать raw value.
/usr/sbin/ip -j -d link show
/usr/sbin/nft -j -a list ruleset
```

До nft netlink read подтвердить наличие required already-loaded/builtin support, чтобы не рассчитывать на autoload. Если необходимых modules нет, остановиться: preflight не загружает их. На empty VM ожидается отсутствие чужих workloads/bridges/rules; это **не** разрешение создать tcsh0 или исправить конфигурацию.

Этап A2 — только отдельно одобренный exact daemon. На новой пустой VM первый workload list должен быть пуст; позднее допускаются только два exact newly owned IDs. Read-only SDK provider дополнительно проверяет Unix peer/witness; CLI output этого не заменяет.

```sh
docker --host unix:///run/tc-shadow/docker.sock info --format '{{.ID}}'
docker --host unix:///run/tc-shadow/docker.sock ps -a --no-trunc --format '{{.ID}}'
```

Этап B — после отдельно разрешённого setup/provisioning и выдачи настоящего typed binding, а не fabricated future PIDs. Все команды только читают; **сам namespace entry требует отдельного разрешения**. `APPROVED_PID/ID/VETH` — значения из authenticated exact enrollment, без fallback поиска по name/labels.

```sh
docker --host unix:///run/tc-shadow/docker.sock inspect --format '{{.Id}} {{.State.Pid}} {{.State.StartedAt}} {{.RestartCount}}' APPROVED_FULL_ID
docker --host unix:///run/tc-shadow/docker.sock inspect --format '{{json .NetworkSettings.Networks}}' APPROVED_FULL_ID
cat /proc/APPROVED_PID/stat
stat -L -c '%i' /proc/APPROVED_PID/ns/net
/usr/bin/nsenter --net=/proc/APPROVED_PID/ns/net /usr/sbin/ip -j -d link show
/usr/bin/nsenter --net=/proc/APPROVED_PID/ns/net /usr/sbin/ip -j address show
/usr/sbin/ethtool -k tcsh0
/usr/sbin/ethtool -k APPROVED_VETH
/usr/sbin/tc -j filter show dev APPROVED_VETH ingress
/usr/sbin/tc -j filter show dev APPROVED_VETH egress
cat /proc/sys/net/bridge/bridge-nf-call-iptables
cat /proc/sys/net/bridge/bridge-nf-call-ip6tables
cat /proc/sys/net/bridge/bridge-nf-call-arptables
```

Повторить для target/runner и host links **до/после**; проверить reciprocal ifindex/iflink/master, MAC/IP, NetworkID/EndpointID, exact network membership и отсутствие extra interfaces/bridges. В library выполняются также full own-rules comparison, host netns/boot/witness и source/profile checks. Прочитанные PIDs/inodes/version не являются admission/изоляцией сами по себе.

## 14. Разрешения на mutations, acceptance prerequisites и STOP

Следующие действия требуют **нового явного разрешения**; ни code review, ни root/capabilities, ни успешный preflight этого разрешения не дают:

| Операция | Возможный эффект |
|---|---|
| Image build/pull/load, daemon/network create/connect/disconnect/delete, target/runner create/start/exec/stop/remove | Docker/host/container state. В этом пакете mutation Docker API отсутствует. |
| Bootstrap/active/rollback nft transaction | Меняет host firewall, включая global bridge paths. Только newly proven owned tables/handles. |
| sysctl, modprobe, offload/XDP/tc/bridge configuration | Меняет kernel/network state. Автоматических implementations нет. |
| nsenter/setns/helper launch, raw/Netlink capture | Privileged namespace/process/socket effects; нужны exact scope/principal approval даже для чтения. |
| Fixed ARP/TCP/UDP/IPv6/spoof probes | Реальная packet injection и peer neighbor/TCP state; finite diagnostic scope не означает отсутствие mutation. |
| Fault injections/reset/kill/rollback/recovery apply и resource teardown | Требуют отдельного ownership accounting и плана восстановления. |
| Deploy/VDS acceptance/production или historical cleanup | Не разрешены этой задачей; old VDS/orphans/evidence исключены. |

До acceptance: утвердить новую dedicated VM/daemon/session/source/images/topology и OS roles; реализовать host-only bootstrap authority; проверить strict kernel/offload/binary compatibility; предоставить loss-accounted drop/topology mechanism и независимый transaction observer; отдельно review versioned physical→authority activation и timing contract. Existing live guard и новый closed gate нельзя удалять/подменять fixtures ради зелёного результата.

STOP при missing/foreign approval, unsupported versions/modules/capabilities, extra workload/bridge/interface/hook/offload, daemon/PID/netns/veth/endpoint/source drift, stale/forged/missing trace, loss/truncation, unknown apply/remove, clock/deadline/kill failure или unresolved rollback/ownership. Запретить новые operations, сохранить exact intents/receipts/state/credentials для recovery, не повторять apply/start и не освобождать lease по времени. Confirmed restore bootstrap не отменяет quarantine. Никаких compensating academic writes, удаления чужих tables/containers или historical orphan.

**№20.1b-4: код и offline review artifacts подготовлены. Физический runtime выключен; реальная network isolation, end-to-end acceptance и security sign-off не заявляются. После review — остановка, VDS acceptance не начинать.**
