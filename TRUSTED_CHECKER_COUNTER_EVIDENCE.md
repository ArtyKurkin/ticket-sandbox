# Trusted Checker: nftables Counter Evidence Foundation — №20.1b-6

19 октября 2026 · `feature/roadmap-react` · база `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

Реализован **offline foundation** метода `nft_counter_probe_v1`, выбранного в [№20.1b-5](TRUSTED_CHECKER_NETWORK_ALTERNATIVES.md). Новые компоненты находятся внутри существующего `trusted_checker_network`. Новый package, runtime coordinator, installer backend или физический transport не создавались. Прежние recipes, tests, policies, authority/ownership/cleanup и gates сохранены без изменений.

Результат `verified` означает успешную проверку **явных synthetic fixtures в заданной модели**, не установленную network isolation на Linux. `physical_probe_permitted=false` без исключений. Реальные Docker/kernel/nft/netns/packet операции, VDS, deploy и commit/push/rebase не выполнялись.

## 1. Новый evidence contract

Отдельный typed contract и authentication domain: `tc-nft-counter-probe-v1-offline`. Нет преобразования в v3 `MatrixReceipt`, v4 `CollectionReport`, live `EgressValidation` или authority permit. Verifier принимает только точные новые DTO types и authenticated fixture envelopes. Старые v3/v4 receipts отвергаются до проверки их содержимого как новых observations.

| Поле / объект | Содержание |
|---|---|
| `method/version/origin` | `nft_counter_probe_v1` / integer1 / `offline_counter_fixture` |
| `verification_scope` | `runner_external_ipv4_tcp_target_8080_with_peer_arp`: разрешённый external first-hop путь, bounded ARP пары отдельно |
| `CounterApproval.runtime` | Полный immutable существующий `RuntimeApproval`: exact UUID/digest, daemon/endpoint/session, images, policy и limits |
| `CounterApproval.binding` | Переиспользуемый `NetworkBinding`: host boot/identity/netns, daemon, NetworkID, target/runner FullID/StartedAt/RestartCount/PID/start ticks/netns/veth/EndpointID/IP/MAC, binding/generation UUID |
| Rules и identities | Fixed recipe digest; `install_epoch_uuid/install_generation`; exact handles всех table/chain/rule objects; отдельная identity каждого rule-local counter и его expression position |
| Sample plan | Фиксированные15 header probes из существующего finite plan, привязанные к context/binding; export содержит probe ID/case/frame digest, не raw packet |
| Before/after | Typed packets/bytes всех49 counters для каждого sample, плюс times; полный static compare каждого supplied readback |
| Observation window | Reservation и absolute deadline≤2s, отдельный monotonic fence; topology before/after digest и sample windows; `finalized_at` отражает время оформления terminal |
| `result/reason` | `verified/offline_counter_model_verified` либо immutable `unknown` с finite reason |
| Topology assumptions | Approved `ControlModel` review digest, writer epoch, exact writers и обязательные permission requirements; не операторский boolean |
| Обязательные ограничения | `continuous_attestation=false`, `trace_delivery_complete=unproven`, `physical_probe_permitted=false`, `byte_accounting=offline_frame_bytes_not_kernel_verified` |

`CounterEvidence` — frozen DTO. Operator export≤65536 bytes содержит один counter identity catalog и индексированные before/after numeric rows. Он сохраняет exact approval, scope, plan, topology refs и terminal reason. Raw nft JSON, frames, HMAC signatures/keys, stdout/errors, arbitrary HTTP body или trainee data в export не попадают. Внутренний evidence object содержит полные typed values; его не следует выдавать вместо компактного export.

Keys задаются только trusted fixture setup, без defaults/env/discovery; роли operator/reader/packet/observer/validator имеют различные keys. Signer находится в tests helper. HMAC подтверждает источник fixture, а не состояние kernel. `issued_report` дополнительно требует совпадения с terminal, выданным данным verifier: даже корректно подписанный чужой report нельзя импортировать как собственный результат.

## 2. Созданные файлы и переиспользование

Все перечисленные файлы новые; существующие исходники и tests не редактировались.

| Файл | Назначение |
|---|---|
| [`counter_contracts.py`](trusted_checker_network/counter_contracts.py) | Approval/readback/packet/evidence DTO, result constraints и bounded operator export |
| [`counter_auth.py`](trusted_checker_network/counter_auth.py) | Closed receipt union, role/key/scope separation и fixture HMAC verification |
| [`counter_rules.py`](trusted_checker_network/counter_rules.py) | Отдельный pure compiler, fixed sample plan, anonymous counters и immutable recipe digest |
| [`counter_readback.py`](trusted_checker_network/counter_readback.py) | Strict bounded JSON parsing, full static compare, exact handles и typed numeric extraction |
| [`counter_inventory.py`](trusted_checker_network/counter_inventory.py) | Extended read-only inventory **data contract**, fixed path layout и control-model requirements |
| [`counter_evidence.py`](trusted_checker_network/counter_evidence.py) | Pure delta/packet verification; default-OFF process-local reservation/epoch/kill/terminal/circuit |
| [`tests/counter_support.py`](trusted_checker_network/tests/counter_support.py) | Явные synthetic approvals/readbacks/packets/topology и fixture signing |
| [`tests/test_counter_evidence.py`](trusted_checker_network/tests/test_counter_evidence.py) | Новые security/contract/isolation tests |
| [`TRUSTED_CHECKER_COUNTER_EVIDENCE.md`](TRUSTED_CHECKER_COUNTER_EVIDENCE.md) | Этот отчёт и план последующего опыта |

Переиспользованы `RuntimeApproval`, `NetworkBinding/NamespaceIdentity`, v3 pure `approved_rules`, finite `packets.plan`, checksum/unpad/classify_reply и `PacketEvent`. Новая recipe строится на deep copy; historical v2/v3/v4 rules не меняются. Tests переиспользуют существующий mock `NetworkLab` и его temporary setup; daemon отсутствует.

Existing physical installer/readback/helper/inventory не подключены к новой recipe: их exact-type/domain/source guards остаются прежними. Новый parser работает с **поставленным JSON**, новый inventory — с поставленными typed data. Это foundation для их будущего reviewed versioned boundary, а не обход sealed mock/physical ports. Source manifest прежнего physical package динамически включает новые network Python modules; его вычисляемый digest поэтому изменится, хотя baseline files неизменны. Старые approvals с предыдущим source digest нельзя переносить автоматически.

## 3. Правила nftables и counter placement

Recipe имеет собственные tables `tcc1_<full approval UUID>`, собственный digest и context. Caller передаёт только typed runtime/binding/UUID и active/bootstrap selector; generic rules/URL/commands не принимаются.

1. Существующие bridge default-drop chains, priorities0, inet guards−310 и все allow matches сохраняются. Новых accept paths нет. Request TCP target8080, established return и bounded pair ARP остаются теми же разрешениями.
2. В каждое существующее allow/guard rule перед terminal verdict добавлен rule-local anonymous counter. Purpose различает `allow` и `guard_drop`; counter перед accept никогда не считается drop evidence.
3. Перед обычными bridge rules добавлены exact per-probe classifiers, связанные с physical runner ingress ifindex и полным фиксированным header frame. Positive sample имеет non-terminal ingress counter. Каждый negative sample имеет отдельный ingress counter, затем отдельное правило **match → counter → drop**. Counter identities не разделяются между samples.
4. В конце каждой bridge chain добавлен final counter+drop, при сохранённой base policy drop. Любой неожиданный fallthrough increment будет unexplained delta, не положительным результатом.

Active recipe содержит49 counters:15 ingress,14 exact terminal-drop,12 прежних allow rules,4 inet guard drops и4 bridge fallback drops. Bootstrap не имеет accept rules. Positive sample ожидает ingress count и четыре TCP allow increments — request/return в prerouting и forward. ARP priming не включается в окно delta; увеличение ARP counters внутри окна будет background/unknown.

TCP использует context-derived sequence, UDP дополнен96-bit token. Exact header comparisons генерируются из trusted fixed plan chunk-ами≤128 bits raw link-layer payload; operator не задаёт bytes. Внешний raw payload синтаксис/битовые offsets сверялись с [официальным nft manual, RAW PAYLOAD EXPRESSION](https://netfilter.org/projects/nftables/manpage.html). **Настоящий nft parser не запускался.** Kernel register/serialization/VLAN handling и wire compatibility этой recipe ещё не приняты; текущие JSON fixtures не заменяют native normalization test.

Counter statement оценивается в своём месте, а terminal drop прекращает evaluation. Эти свойства описаны в [официальной странице Counters](https://wiki.nftables.org/wiki-nftables/index.php?title=Counters&oldid=1092) и [nft verdict semantics](https://netfilter.org/projects/nftables/manpage.html). Здесь они используются как design basis; тестовый рост counter не объявляется реально наблюдавшимся drop.

## 4. Readback validation

`validate_readback` самостоятельно строит ожидаемую recipe из exact approval. Он не принимает supplied `verified=true`, supplied static rules или digest от installer как замену сравнения.

- Ограничение input262144 bytes; duplicate JSON keys, nonfinite/float numbers и malformed/deep JSON отвергаются.
- Проверяются весь object list и его порядок, exact family/table/chain/type/hook/priority/policy, количество rules и все expressions. Unknown object/expression/field, partial dump и metadata в неподдерживаемой форме дают отказ. Это намеренно узкая schema, не универсальный nft parser.
- Table/chain/rule handles должны совпасть с explicit fixture installation binding; bool вместо integer не принимается. Коллизии/duplicate handles в approval запрещены. Имя table/counter не создаёт ownership.
- Только `packets/bytes` в **точном approved anonymous counter expression** могут отличаться. Они должны быть integers в `[0,2**63−1]`. Все остальные поля, counter presence/position и verdict сравниваются строго. Перемещение counter к accept, перед match, после verdict, shared/named counter или второй counter не проходят.
- Каждое чтение связано с approval/context/install epoch/generation. Замена handle/epoch/generation не продолжается как прежняя baseline; уменьшение values либо выход за numeric range дают unknown/reset-or-wrap.

У parser нет shell/nft/SDK clients и возможности reset/update counters. Strict order/handle schema пока проверена только на собственных fixtures. Если native dump использует иной порядок группировки, metadata или нормализацию raw payload, текущий reader должен отказать; compatibility требует отдельного versioned review, а не добавления игнорируемых полей на месте.

## 5. Delta verification и lifecycle

Для всех15 samples последовательно проверяется:

```text
signed topology before + approved offline control model
  → signed full baseline readback
  → signed bounded exact send/ingress observations
  → для allow: target delivery + matching response + runner receive
  → signed full final readback
  → exact expected deltas ВСЕХ counters
  → unchanged counter rows перед следующим sample
  → signed topology after + fresh epoch/deadline gates
  → immutable offline verified/unknown; physical release=false
```

Negative sample требует ровно один ingress increment и ровно один increment своего terminal-drop counter с точными expected bytes. Все остальные deltas должны быть нулевыми. Extra count, фон на fallback/ARP/allow, неверная byte delta, packet loss/truncation или отсутствующий send/ingress дают unknown. Timeout без подтверждённой drop delta не принимается как deny.

Allowed sample требует того же fixed request на send/host ingress/target ingress и matching SYN-ACK **либо RST-ACK**, проверенного существующим checksum/flow/ACK/MAC/IP parser. Оба response observations должны совпасть. Firewall-drop или silent timeout не подтверждают доступность. `path_open_rst` означает работающий network path к loopback-only/stopped listener; `path_open_synack` — TCP path. Ни один не утверждает HTTP200/body или учебный success.

Окно всех measurements≤2s — constraint offline contract, не live timing/SLA. Wall и monotonic deadline фиксируются один раз; detected rollback, exact deadline boundary, kill или смена control epoch закрывают measurement в unknown. `finalized_at` сохраняет фактическое supplied clock time; `finished_at` ограничивает observation window deadline и не означает, что оформление terminal закончилось в срок. Поздний positive не меняет terminal.

`OfflineCounterVerifier` OFF по умолчанию. `begin` резервирует единственный context; concurrent begin rejected, concurrent finish возвращает один и тот же terminal. Unknown удерживает circuit; disable→enable не оживляет reservation. Не существует cleanup/delete/start/PROBE methods. Existing runtime durable CAS, mutation fences, cleanup/circuit и irreversible stop latches не затронуты.

**Граница нового state:** reservation/epoch/terminal/circuit этого pure fixture verifier process-local. Это не durable coordinator и не cross-process lease. Новый экземпляр не импортирует предыдущий result как собственный issued report и не возобновляет measurement. Persistent replay/kill integration для реальных operations остаётся у existing journals и требует отдельной versioned composition. Нельзя использовать этот объект как runtime scheduler или защиту от другого privileged процесса.

## 6. Trust assumptions и extended inventory

`TopologyObservation` содержит полные canonical arrays interfaces, routes **всех tables**, IPv4/IPv6 policy rules и attachments для host/target/runner namespaces. Сохранены exact binding/endpoints/veth/bridge identities. Полное equality с generated strict layout обнаруживает extra interface/route/table/rule, IPv6 policy drift, XDP/tc/flowtable attachment, иной netns, unaccounted writer или inherited external network FD.

Generated layout намеренно ограничен: lo + один tcsh0/veth pair, один peer interface, connected/local routes, fixed default RPDB rules; нет default route, host management NIC, IPv6 peer address, tunnels/macvlan или foreign attachments. Это **offline inventory profile**, не readback текущей VM. Нельзя заявлять, что existing `NamespaceInventory.observe` уже читает routes/RPDB или что этот layout совместим с реальным Docker provisioner. Host с management NIC потребует отдельного profile review с доказанным отсутствием path к ней.

Поле `ControlModel` — явная одобренная **модель fixtures**, не proof permissions. Вместо `exclusive_control_plane=true` фиксируются review digest, writer epoch, exact writers и обязательный набор требований. Для настоящей dedicated VM необходимы проверяемые operational facts:

| Требование | Что должно обеспечиваться deployment/OS |
|---|---|
| Exclusive writers | Только reviewed daemon/installer principals имеют network mutation authority; все их изменения serialized до publication. Других agents/admin automation с этими полномочиями нет в принятой модели |
| Недоверенные task/Runner | DropALL/nnp, отсутствие NET_ADMIN/NET_RAW, host/daemon sockets, dangerous mounts и inherited external sockets; нет пути к привилегированному setns/helper/userns escalation |
| Independent reader/validator | Отдельный principal/защищённый binary/config и read-only API surface, доступный только к approved objects. HMAC key separation сама не разделяет OS процессы |
| Host TCB | Protected source/keys/journals, approved boot/kernel/daemon session; root/daemon administrator остаётся доверенным и способен обойти локальную policy |
| Invalidation | Reboot/session/config/roles/sysctl/offload/hooks/interfaces/routes или потеря контроля над writers аннулируют review epoch; TTL и DB lease не заменяют это условие |

В этом этапе ни один OS fact не inspected. Две одинаковые topology observations доказывают лишь совпадение snapshots. Они не доказывают отсутствие краткого attach/revert, counter reset/restore или rules replacement между ними. Signed fixture сообщает, какой principal утверждал observation; не превращает assumption в independent host attestation.

## 7. Limitations и недоступные доказательства

1. **Нет физического результата.** Kernel/nft parser, hooks/native CT, offloads/VLAN/checksums, namespace permissions и packet delivery не проверены. Реальный host collector/read-only routes adapter для нового contract не реализован.
2. **Нет trace completeness claim.** Новый verifier не читает NFTRACE и не зависит от его notifications. Старый `unknown/native_nftrace_continuity_unproven` остаётся неизменным; прежний collector не стал positive.
3. **Counters — агрегаты.** Уменьшение/смена identity обнаруживаются, но reset с восстановлением values до/выше прежних и transient replacement с восстановлением handles нельзя исключить по двум snapshots. Это остаётся пределом trusted-writer assumption; при неподтверждённом control plane physical claim запрещён.
4. **Bytes пока fixture model.** Expected delta использует `len(unpadded fixed frame)`. Реальный nft `skb->len` на выбранном bridge hook может учитывать bytes иначе. [Linux6.8 counter source](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/netfilter/nft_counter.c) также показывает per-CPU accounting/dump aggregation; чтение нескольких counters не является одним global atomic snapshot. До measurements нельзя переносить эту byte basis в live evidence или вводить погрешность ради success.
5. **Strict bounded noise model.** ARP/response/retransmit вне fixed plan и любое необъяснимое изменение counters дают unknown. Практическая quiescence, Ethernet padding/VLAN normalization и точная correlation должны быть проверены на approved kernel. Finite probes не перебирают все destinations; general deny выводится только в рамках утверждённой hook/topology модели.
6. **Нет durable runtime orchestration.** New pure verifier имеет process-local fences; existing installer/authority journals не принимают новую scheme. Host-only pre-provision bootstrap ownership, generation transfer и committed transaction observer при lost nft response остаются прежними prerequisites. Counters не дают adoption/cleanup authority.
7. **Нет новой live policy.** V2 digest/8s,30s proposals, Runner и external HTTP predicate не менялись.2s fixture window не является тайным расширением общего budget. Любой будущий live profile/timing требует измерений и нового approval.
8. **Нет application/academic evidence.** Network verified не доказывает HTTP, loopback, authenticity или persistence; нет Django/Sandbox/Celery hooks, CheckRun/Ledger writes, grants/completion/AI/mentor/Roadmap transitions. Platinum и existing guards сохранены.

## 8. Test results

Запуски только локальные, без daemon и network operations. New counter fixtures используют managed clock, supplied JSON/frames и временный existing mock setup. Fresh import test запрещает socket constructor/Popen/setns и подтверждает отсутствие Docker/Django import. AST test новых production modules запрещает legacy writers и непосредственные socket/process/OS I/O imports.

```sh
.venv/bin/python -W error::ResourceWarning -m unittest trusted_checker_network.tests.test_counter_evidence
.venv/bin/python -W error::ResourceWarning -m unittest \
  trusted_checker_network.tests.test_installer \
  trusted_checker_network.tests.test_collector \
  trusted_checker_network.tests.test_lifecycle
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_physical/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_live/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_runtime/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_shadow/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_poc/tests -t .
```

| Suite | Результат |
|---|---|
| Новый counter foundation | **64 tests, OK**, без skips/ResourceWarning |
| Existing network | 69 tests, OK |
| Existing physical | 90 tests, OK |
| Existing live | 48 tests, OK |
| Existing runtime | 66 tests, OK |
| Existing shadow | 56 tests, OK |
| Existing PoC | 166 tests, OK |
| Existing total | **495 tests, OK**, без skips |
| **Всего** | **559 tests, OK**; только offline/mocks |

Покрытие новых tests: terminal drop и RST/SYN-ACK, counter перед accept/неверным match/после verdict, wrong handle/generation/epoch, reset/wrap/numeric types, duplicate/shared counters, фон/excess/byte delta, partial/unknown/duplicate-key JSON, missing send/ingress/reply, silent timeout, extra interface/route/RPDB/attachments, unaccounted writer/FD, forged signatures/roles/reports, old v3/v4 domain, concurrent begin/finish, defaultOFF, kill/epoch/wall+monotonic deadline/rollback, immutable late result, source/recipe/import isolation и bounded redaction.

На первом прогоне57 tests один test некорректно искал substring `key` в JSON, включая static permission requirement `...keys...`; дополнительно полный internal DTO был слишком велик для выбранного export limit. Исправлены key-aware redaction assertion и компактный operator export с общим identity catalog. Production identity/delta guards не ослаблялись. Новые дополнительные tests закрепляют approval/report constraints и lifecycle boundaries.

Логи `/tmp/task201b6-{counter,network,physical,live,runtime,shadow,poc}.log`. Old suites выполнялись независимо/частично параллельно; их timings не являются benchmark. Django application regressions заново не запускались: integration/writers не менялись, прежние Django results не объявляются новыми проверками этого этапа.

Финальный counter run:64 tests за15.682s, OK. SHA-256 всех141 baseline artifacts совпали, включая `PhysicalProbeGate`, live adapter guard, прежние reports и tests. Добавлены8 Python files и этот отчёт; tracked Git diff пуст. Проверены syntax/AST,9 разделов, local links, fenced blocks и whitespace. Рабочие БД, `.env`, credentials, Docker sockets и historical resources не читались. Никаких Django/Sandbox/Celery, training task, live policy или runtime изменений; commit/push/rebase/deploy не выполнялись.

## 9. План минимального эксперимента на новой dedicated VM

**Ни один шаг ниже не выполнен.** Нужны отдельный review и явное разрешение exact fresh VM/host/kernel/source/roles/setup/mutations/rollback. Старую VDS и historical orphans не использовать.

1. Зафиксировать counter schema и trusted-writer assumption; выбрать kernel/nft builds и проверить source/artifacts. Сначала отдельно разрешённый read-only preflight без automatic fix/modprobe/sysctl/offload changes.
2. Спроектировать host-only bootstrap ownership и безопасное management/rollback: только newly owned tables/resources, никакой adoption по table name/readback. При lost apply ответе сохранить quarantine и не повторять mutation.
3. После отдельного setup approval создать только standalone test namespaces/veth/bridge. Не использовать настоящие Sandbox attempts и не запускать live Docker Runner. Получить real tuples и дополнить reviewed inventory profile, если host layout отличается от fixtures.
4. Испытать native nft parser/normalization, raw header expressions/bit widths/VLAN и exact handle readback. Любая несовместимость — STOP/new review; не игнорировать unknown fields. Проверить весь hook/path inventory, включая all route tables/RPDB/IPv6/attachments.
5. Установить approved recipe через separately approved mechanism. Независимый reader снимает baseline/final; bounded fixed probes проверяют ingress/terminal-drop counters и positive SYN-ACK/RST. Измерить реальные packet/byte semantics на каждом hook, ARP/retransmit/noise и quiescence; не переносить `offline_frame_bytes` как доказанный kernel accounting.
6. Отдельно разрешённые faults: missing/duplicate send, фон, counter reset/replacement, extra route/interface, kill/deadline/read interruption. Unknown должен сохраняться, временное изменение между snapshots не выдавать за обнаруженное, если фактически не обнаружено.
7. Измерить стадийные caps и end-to-end budget, сохранить filtered evidence и exact ownership accounting, подтвердить only-owned bootstrap restore/teardown либо quarantine. No generic flush/prune/reset/adopt и никаких historical resources.
8. По результатам отдельный report/review: только затем проектировать versioned collector/installer/authority composition, durable state/receipt integration и live timing/artifact approval. До этого existing `PhysicalProbeGate` и `physical_network_boundary_not_accepted` не меняются.

После №20.1b-6 — остановка. Новая evidence scheme не подключена к настоящему Docker Runner; runtime acceptance и security sign-off не заявляются.
