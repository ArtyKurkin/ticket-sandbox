# Trusted Checker: исследование альтернатив NFTRACE — №20.1b-5

19 октября 2026 · `feature/roadmap-react` · база `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

Статус: **исследование и предложение для согласования**. Единственный новый артефакт — этот документ. Реализация альтернативного механизма не начата. Код, tests, policies, gates и предыдущие отчёты не изменены; runtime не использовался. Указанные ниже будущие условия не являются текущими гарантиями проекта.

## 1. Executive summary

**Рекомендация: вариант B — сохранить nftables default-deny на новой выделенной VM, добавить независимо читаемые counters у терминальных drop rules и проверять их дельты вместе с exact topology и bounded active probes.** Выделенная topology остаётся обязательной предпосылкой B; новый eBPF datapath и переход на собственный netns provisioner для первого эксперимента не нужны.

Доставка каждого NFTRACE notification **не является необходимым условием enforcement**. Она необходима прежнему контракту, который выводит completeness из полного потока trace/capture events. NFTRACE нельзя объявить lossless. Вместо этого предлагается отдельно согласовать другой versioned evidence contract: утверждение об установленном запрете в проверенной модели kernel paths, дополненное положительным свидетельством kernel drop для конкретных проб через counters. Это не замена неизвестного результата на passed и не доказательство непрерывного наблюдения всех пакетов.

Главное условие нового подхода — **исключительное управление network configuration в течение окна проверки**: доверенные daemon/installer не меняют interfaces, routes, hooks или rules; task/Runner не имеют полномочий их менять. Before/after inventory проверяет состояние, но сам по себе не доказывает этот запрет. Если исключительный control plane нельзя обосновать либо требуется обнаруживать любую краткую мутацию независимо от доверенных writers, B недостаточен: до отдельного continuity mechanism результат остаётся unknown.

Минимальный следующий этап после review — offline counter-evidence contract, compiler/readback design и negative tests без открытия существующих live gates. Затем отдельно разрешённый kernel experiment на новой VM, сначала без HTTP/Docker integration. Старый `unknown/native_nftrace_continuity_unproven` остаётся исторически верным; `PhysicalProbeGate` и `physical_network_boundary_not_accepted` остаются закрытыми.

Основа исследования: [№20.1b-3](TRUSTED_CHECKER_NETWORK_VALIDATION.md), [№20.1b-4](TRUSTED_CHECKER_PHYSICAL_NETWORK_BACKEND.md), packages `trusted_checker_network/`, `trusted_checker_physical/`, live egress/runtime contracts и их tests. Первичные Linux/netfilter/libbpf sources перечислены в §12. **Факт источника**, **вывод исследования** и **предлагаемое условие** ниже разделены явно. Совместимость конкретной VM не проверялась.

## 2. Почему NFTRACE не подходит для текущей strict matrix

### 2.1. Что делает kernel

**Факты Linux 6.8:** `nft_trace_notify` формирует `NFT_MSG_TRACE` для rule/return/base-chain policy, с table/chain, verdict/policy, trace ID и частичным packet/device context. Packet headers не повторяются во всех notifications. Сообщение создаётся лишь при наличии listeners. `nlmsg_new(..., GFP_ATOMIC)` может вернуть NULL; функция тогда просто возвращается. Ошибка упаковки attributes также не создаёт полноценное notification. `nfnl_msg_put(..., 0, 0, ...)` задаёт sequence0; trace ID вычисляется из packet-related данных и не является порядковым номером stream. См. [`nf_tables_trace.c`, v6.8](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/netfilter/nf_tables_trace.c).

**Дополнительная проверка версии:** в [Linux 6.12, том же файле](https://github.com/torvalds/linux/blob/v6.12/net/netfilter/nf_tables_trace.c) также присутствуют ранний return при allocation failure и sequence0. Это проверка исходников двух tags, не аттестация vendor kernel или всех его backports.

**Факт транспорта:** kernel→userspace Netlink допускает потерю при переполнении socket buffer; `ENOBUFS` позволяет обнаружить такую рассинхронизацию. ACK запроса не делает multicast notifications полным журналом. Отсутствие `ENOBUFS` не учитывает notification, которое не удалось создать до отправки. Последнее — вывод из сочетания API и реализации выше. См. [netlink(7), Linux man-pages 6.19](https://man7.org/linux/man-pages/man7/netlink.7.html).

### 2.2. Доступные сигналы и пределы

| Свидетельство | Что можно заключить | Что нельзя заключить |
|---|---|---|
| Authenticated kernel-origin event + точный packet/context/rules binding | Наблюдался конкретный evaluation/verdict в указанной цепочке | Наблюдались все evaluations других пакетов/цепочек |
| `ENOBUFS`, overrun, truncation, malformed framing, пропущенная ожидаемая связь | Evidence неполно; измерение unknown | Firewall обязательно пропустил запрещённый пакет |
| Нет сообщения о drop | Нет достаточного evidence drop | Пакет заблокирован; пакет доставлен; trace loss отсутствует |
| AF_PACKET statistics без drops | В пределах semantics проверенных packet sockets потери не зарегистрированы | NFTRACE notification allocation и весь Netlink stream были lossless |
| Совпали before/after topology | Совпали наблюдаемые snapshots | Между ними не было detach/rejoin или временного rules replacement |

NFTRACE пригоден для диагностики маршрута evaluation и положительного свидетельства конкретного verdict. Его нельзя использовать как complete ledger всех сетевых решений. **Утрата наблюдаемости и нарушение enforcement — разные события:** при утрате notification kernel drop мог состояться; при успешно записанном drop другая interface могла иметь обходной путь. Это вывод исследования, не дополнительная гарантия NFTRACE.

### 2.3. Почему текущий код правильно возвращает unknown

В [`collector.py`](trusted_checker_physical/collector.py) `measure` сопоставляет send/physical ingress/target delivery/ответ и native policy drop. Даже полный набор наблюдавшихся проб завершается `native_nftrace_continuity_unproven`. `CollectionReport` допускает только unknown, `matrix_complete=false`, `probe_permitted=false`; `PhysicalProbeGate` безусловно закрыт. [`trace.py`](trusted_checker_physical/trace.py) проверяет native framing и sequence0, но не может восстановить отсутствующий kernel stream counter.

Тест `test_rst_and_full_observations_still_no_continuity_success` закрепляет именно этот предел; `test_timeout_not_a_drop`, `test_missing_kernel_drop_trace` и negative cases в [`network/tests/test_collector.py`](trusted_checker_network/tests/test_collector.py) запрещают превращать silence в deny. Это чтение существующих tests, не новый прогон.

Непрерывное или эквивалентное completeness evidence нужно для утверждений «зарегистрирован каждый packet/verdict» и «не было ни одной временной topology/rules mutation», если предотвращение таких mutations не обеспечено принятой моделью управления. Для проверки установленного immutable default-deny и конкретного доставленного drop sample полный packet-event stream логически не обязателен. **Изменение именно этого требования требует согласования §9.**

## 3. Сравнение трёх архитектур

### A — eBPF observer либо enforcer

**Observer:** BPF на TC ingress/egress может учитывать прохождение пакетов, сохраняя nftables как enforcer. Тогда корректность attach point и видимость конкретного path обязательны; отсутствие BPF event не доказывает drop. Нужны отдельные correlations с реальным enforcement decision. Простая замена NFTRACE на ring buffer переносит проблему доставки.

**Enforcer:** TC direct-action program может сам вернуть drop; это уже новый default-deny datapath. В [Linux 6.12 `cls_bpf.c`](https://raw.githubusercontent.com/torvalds/linux/v6.12/net/sched/cls_bpf.c) direct-action обрабатывает, среди прочего, `TC_ACT_SHOT`. Проектно потребовались бы host-side runner-veth ingress, проверенный return path и строгий разбор L2/IPv4/IPv6/VLAN/fragments; прочие interfaces и redirect paths надо исключить. Одного cgroup connect hook недостаточно для утверждения обо всём L2/packet traffic. XDP ingress не заменяет автоматически egress/host-path policy. Выбор иных hooks — отдельная версия архитектуры, а не совместимая подстановка observer.

**Counters отдельно от событий.** [BPF array/per-CPU array, Linux 6.12](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/bpf/map_array.rst) допускают заранее выделенные entries; per-CPU значения читаются userspace по всем CPU. Предлагаемый enforcer мог бы считать решения в такой map независимо от экспорта событий, с корректной синхронизацией shared values и проверкой epoch/map identity. Сумма reads не становится автоматически единым atomic snapshot всех CPU/maps. Ошибка lookup/update должна иметь заданную fail-closed semantics; program, который вообще не был вызван из-за detach/bypass, не посчитает собственное отсутствие.

**Ring/perf не lossless.** В [ringbuf documentation v6.12](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/bpf/ringbuf.rst) reserve не блокирует и может не состояться при заполнении; в NMI возможен также отказ lock acquisition. Отказ нужно считать отдельной map до потери diagnostic event. [libbpf 1.6 API](https://libbpf.readthedocs.io/en/v1.6.0/api.html) предоставляет perf-buffer lost callback; это сигнал потерь records, а не доказательство полного исполнения enforcer. Неудачный event export не обязан отменять kernel drop, но полная audit history тогда не подтверждена.

**Identity и защита.** Проверять следует netns/device generation, attach type/direction/order, весь список attached programs/links, program ID/tag и reviewed artifact correspondence, map IDs/types/sizes и policy contents. Pinning продлевает lifetime, но не защищает от privileged detach/update: [TCX v6.8](https://raw.githubusercontent.com/torvalds/linux/v6.8/kernel/bpf/tcx.c) имеет link query/update/detach paths. Нужны защищённые FDs/bpffs/OS principals, запрет сторонних writers и invalidation при detach/device replacement. ID/tag не является подписью исходников или доказательством отсутствия временной замены.

`BPF_MAP_FREEZE` может закрыть userspace modification policy map; mutable counters следует держать отдельно. Это не универсальное запрещение writes из BPF и не запрет замены всей map/program. Системные capability checks зависят от program type: в [Linux 6.12 `syscall.c`](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/bpf/syscall.c) SCHED_CLS требует соответствующие BPF/network privileges, tracing types — perf privileges. Нельзя обещать запуск под одним непривилегированным UID.

[Verifier v6.12](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/bpf/verifier.rst) проверяет допустимость accesses, pointer bounds и другие условия безопасности программы. Из этого не следует правильность разрешённого IP/port или полнота hook coverage. Понадобятся reviewed ELF/build toolchain, подходящие BPF/TC kernel configs, loader и independent reader; BTF/libbpf/CO-RE — возможный способ сопровождения, не обязательное свойство всякой BPF-программы. Для первого опыта это дополнительная подсистема, не устранение topology/ownership задач.

### B — nftables + readback + counters + probes

Сохраняется текущий default-deny bridge/inet design. Добавляются versioned счётчики в заранее reviewed recipe: ingress accounting, разрешённые направления и конкретные terminal drops. **Факт nftables:** counter считает packets/bytes в месте statement, а statements проверяются слева направо; неправильное положение counter меняет то, что он учитывает. Named counters могут разделяться правилами, поэтому для evidence нельзя считать имя достаточным уникальным binding. См. [официальную страницу Counters, revision1092](https://wiki.nftables.org/wiki-nftables/index.php?title=Counters&oldid=1092).

Отрицательное evidence предлагается строить по `точный probe → подтверждённый ingress → delta конкретного counter непосредственно перед unconditional drop`. Такой счётчик — сохранённое kernel state, не поток notifications. Срабатывание counter перед произвольным `accept` либо в незавершающем правиле не доказывает нужный исход. По [официальному nft manual, evaluation/verdict semantics](https://netfilter.org/projects/nftables/manpage.html) drop завершает evaluation, а accept может быть отменён последующей chain. Поэтому terminal drop placement и отсутствие обхода важнее количества diagnostic events.

Это потенциально достаточно для **scoped claim в принятой модели §4**, но не для безусловной continuous attestation. Counter — агрегат: без isolated window, exact matches и generation binding он не доказывает принадлежность конкретному probe. Большая delta не означает «всё хорошо»: её мог создать фон. Отсутствие delta может означать несостоявшийся send или другой path. Пробы не перебирают все IP/ports; полнота запрета выводится из полного approved default-deny и охвата paths, а не из конечного списка samples.

### C — topology / namespace isolation

Предлагаемая минимальная topology: отдельный runner netns, ровно один veth к target path, отсутствие uplink/default route, отсутствие L3 services host на этом пути; dedicated host и запрет дополнительных attachments. Network namespaces действительно разделяют devices, protocol stacks, routing tables и firewall, но veth соединяет namespaces. См. [network_namespaces(7), man-pages6.19](https://man7.org/linux/man-pages/man7/network_namespaces.7.html).

**Отсутствие default route недостаточно.** Сохраняются connected/link routes к peer/subnet, local/broadcast paths; [ip-route(8)](https://man7.org/linux/man-pages/man8/ip-route.8.html) отдельно описывает local table и link/broadcast destinations. Policy routing использует несколько tables/rules, а не только main/default: [ip-rule(8)](https://man7.org/linux/man-pages/man8/ip-rule.8.html). IPv6 link-local/multicast и L2 ARP не исчезают из-за отсутствия IPv4 default. Даже прямой veth без IP у host допускает обращения к **другим портам target**. Для ограничения ровно8080 всё равно нужен packet/socket enforcer; topology сама этого не выражает.

Capability separation сокращает возможности недоверенных peers: `CAP_NET_ADMIN` управляет interfaces/routes/firewall, `CAP_NET_RAW` разрешает RAW/PACKET sockets. Это documented scope [capabilities(7), man-pages6.19](https://man7.org/linux/man-pages/man7/capabilities.7.html). DropALL/nnp и отсутствие socket/host mounts сохраняются; privileged collector остаётся TCB. Namespace FD не запрещает daemon administrator подключить другой device или передать заранее открытый socket. Read-only inventory обнаруживает состояние в момент чтения, не запрещает будущую mutation.

Полный переход с Docker bridge на собственный point-to-point provisioner меняет текущие NetworkID/EndpointID/profile/ownership assumptions. Он может уменьшить surface host paths, но потребует новой authority integration и всё равно port filtering. Поэтому C полезен как defense in depth, но не является минимальной самостоятельной заменой текущей подсистемы.

### Сравнительная матрица

Оценки ниже — **проектные выводы относительно текущего кода**, не benchmark и не ranking продуктов вообще.

| Критерий | A: BPF enforcer + maps | B: nft + readback/counters/probes | C: topology как главный барьер |
|---|---|---|---|
| Enforcement | Прямой kernel drop, если программа установлена на каждом нужном path; observer-only этого не даёт | Уже выбранный default-deny; требуется доказать reachability hooks и отсутствие bypass | Удаляет внешние paths, но не ограничивает peer port; нужен дополнительный filter |
| Independent verification | Отдельное чтение links/programs/maps и probes; loader claims недостаточны | Полный rules/attachment readback отдельным reader, exact counters и probes | Links/routes/netns/caps inventory; не подтверждает port restriction |
| Negative evidence | Drop counter в enforcer + exact probe; потерянный ring event не нужен для этого счётчика | Exact delta перед terminal drop + ingress; silence не используется как deny | Route rejection может подтвердить конкретный L3 отказ, но не отсутствие L2/IPv6/peer access |
| Потери events | Map state не зависит от ring delivery; detach/invocation gap остаётся | Counter state не зависит от NFTRACE; reset/replacement/read ambiguity дают unknown | Event stream не нужен для устойчивой topology в модели запрета mutations; transient changes snapshots не исключают |
| Kernel prerequisites | BPF/TC и выбранный attach API, map/verifier compatibility, возможный BTF/toolchain | Уже рассматриваемые nft/native bridge CT; counters/parser semantics надо испытать | NET_NS/VETH и privileges provisioning; фильтр8080 добавляет свои требования |
| Реализация | Новый parser/policy datapath, loader, reader, maps/epoch и attach lifecycle | Изменение recipe, counter-aware readback и validator; большая часть lifecycle сохраняется | Новый provisioning/profile, routes и ownership; filter всё равно остаётся |
| Сопровождение | Kernel/helper/attach/toolchain matrix и semantic review каждого ELF | Kernel/nft JSON/hooks/counter normalization; меньше новых механизмов относительно baseline | Согласование Docker/netns lifetimes, routes/IPv6 и capability policy плюс filter |
| Дополнительные privileges | BPF/network; perf при выбранном tracing path; current helper privileges остаются | NET_ADMIN для nft; existing privileged namespace/packet helper остаётся | NET_ADMIN/SYS_ADMIN для topology/setns; NET_RAW для выбранных diagnostics |
| Deadline | Maps reads могут заменить stream processing; attach/readback/probes всё равно стоят времени | Можно убрать NFTRACE collection/correlation; точные counter reads и probes остаются | Меньше routed paths, но provisioning/inventory/filter checks не бесплатны |
| Host risk | Ошибка attach/drop на host veth может оборвать сеть; новый privileged loader | Сохраняется риск global bridge drop на всём host; только dedicated VM | Ошибка namespace/route ownership способна связать host с недоверенным peer |
| Совместимость | Authority/Runner сохраняются, network enforcer и contracts меняются существенно | Наиболее близок к existing installer/inventory/rules design | Меняет Docker network assumptions и generation evidence |
| Новая чистая VM | Возможен отдельный опыт после BPF compatibility/privilege review | Подходит для первого изолированного опыта с текущими prerequisites | Возможен, но потребует отдельного topology provisioner до полного Checker |

## 4. Enforcement vs verification vs evidence

**Ответ: нет, доставка каждого kernel trace event не обязательна для разрешения HTTP PROBE при другом явно утверждённом evidence contract.** Сейчас такой contract не принят и live release по-прежнему запрещён.

Предлагаемое значение `network_isolation_verified` — не самостоятельный boolean от installer. Это результат независимого validator, связанный с authority-issued run, фиксированным verification method/version, policy/rules digest, точной generation и bounded observation window. Пример имени метода для обсуждения: `nft_counter_probe_v1`; имя не зарезервировано в коде и ничего не активирует.

### 4.1. Предлагаемые обязательные критерии

1. **Установленная модель доверия.** Новая dedicated VM, approved kernel/binaries/source, exact daemon/session и immutable images. Только известный task/Runner; отсутствие чужих socket holders. Все разрешённые writers network/rules входят в один trusted control plane и исключают mutations от начала validation до final publication. Lease сериализует разрешённые операции; сам lease не защищает от root вне этого control plane. Неподтверждённая модель — unknown.
2. **Actual enforcement.** Bootstrap действует до появления недоверенных endpoints. Active rules устанавливаются только для реально полученных bindings; full independent readback подтверждает families/base chains/hooks/priorities, immutable matches/verdicts и table ownership. Fixed policy допускает runner→target IPv4 TCP8080 и responses, плюс ровно необходимый ARP пары. Остальное external traffic запрещено, включая host/routed/IPv6/VLAN/fragments. Локальный loopback Runner и control stdin не включаются в утверждение об external egress.
3. **Path coverage.** Exact netns/PID/start/veth/EndpointID/MAC/IP до/после и на execution gates; ровно ожидаемые devices/ports. Дополнительно нужны all-table IPv4/IPv6 routes и policy rules, host addresses/forwarding facts, проверка tunnels/macvlan/redirects и отсутствия inherited external network FDs. XDP/tc/flowtables/offload bypass исключены. Один `Internal=true` или `ip link` недостаточен.
4. **Counter provenance.** Independent reader получает полный static ruleset и отдельно typed counter values. Counter связан с rule handle/позициями statements, family/table/chain, exact counter identity, rules generation и context. Значения нельзя принимать из enforcer JSON или target. Новый generation/reset/replacement/read failure не продолжает старую baseline.
5. **Отрицательные samples с положительным evidence drop.** Для каждого обязательного forbidden class подтверждены exact bounded send и ingress, затем согласованная delta соответствующего terminal-drop counter; expected accept counters не увеличились для этого sample. Пробы последовательно разделены, без concurrent HTTP и постороннего traffic. Ни timeout, ни отсутствие target frame сами по себе не являются deny.
6. **Положительный path sample.** Exact SYN достиг target, matching SYN-ACK либо RST-ACK вернулся Runner. RST от loopback-only task подтверждает разрешённый network path; он не является успехом приложения. Firewall-drop разрешённого8080 и silent timeout — unknown сети, не успешная isolation matrix.
7. **Freshness и lifecycle.** Перед PROBE, после него и перед publication — свежие rules/topology checks, current approval/epoch/kill/deadline и issued enrollment. Обнаруженный drift, conflicting hooks, незавершённый apply/ownership/cleanup или ambiguous counters закрывают admission. Network evidence не отменяет runner final output/exit/config validation.
8. **Durable проверяемое evidence.** Сохраняются method/version, scope, assumption profile, run/binding/generation, окно времени, source/kernel/config/rules refs, exact own handles, typed before/after counters и plan/result refs. Validator подписывает собственное заключение после чтения, а не counters claim installer. Report не содержит raw packets, секреты или arbitrary HTTP body. Evidence publication bounded; ошибка хранения — unknown, не новый запуск.

В этом предложении полнота означает **все обязательные cases выбранного counter/probe method**, а не полноту packet trace stream. Нельзя переиспользовать прежнее `matrix_complete` без версии и нового определения. NFTRACE может остаться optional diagnostic, но его absence/loss не используется как доказательство drop. Потеря обязательного bounded packet sample, ambiguity counter read или topology assumption по-прежнему делает конкретное measurement unknown.

### 4.2. Три уровня утверждений

| Уровень | Допустимое содержание |
|---|---|
| Наблюдаемое | Readback показал конкретные rules/attachments; прочитаны exact counter values; конкретный probe имел ingress/drop delta либо возврат SYN-ACK/RST; snapshots совпали |
| Доказанное **в рамках принятой модели** | Если kernel корректно исполняет проверенные hooks, paths полностью охвачены и configuration не меняется в окне, все неразрешённые external packets должны завершаться drop; finite probes проверяют работу выбранных классов |
| Недоказанное | Lossless NFTRACE, каждый packet event, непрерывное отсутствие скрытых mutations независимо от TCB, защита от host/daemon/kernel compromise, отсутствие любого kernel bug, приложение/HTTP success, application authenticity, loopback criterion и persistence |

Предлагаемые явные report поля: `verification_basis=nft_counter_probe_v1`, `topology_continuity_basis=trusted_exclusive_control_plane`, `continuous_attestation=false`, `trace_delivery_complete=unproven`. Нельзя представлять последнее как `true` или как уже существующий DTO. Утверждение «только target8080» относится к external first-hop traffic выбранного Runner; разрешённый endpoint остаётся каналом данных и не доказывает, что отвечающий процесс подлинный.

## 5. Матрица угроз и гарантий

| Угроза / ошибка | Необходимая проверка B | Честный результат / предел |
|---|---|---|
| Тишина из-за неотправленной пробы | Подтверждённые send+ingress и exact drop delta | Нет ingress/delta — unknown; отсутствие ответа недостаточно |
| Background traffic создаёт drop delta | Exact per-case matches/token/flow, сериализация и контроль остальных counters | Необъяснимая/лишняя delta — unknown, не «не менее одного значит success» |
| Counter растёт до eventual accept | Counter должен стоять непосредственно перед terminal drop; полный static compare | Просто packet count не доказывает deny |
| Потерян NFTRACE record | Решение опирается на counter state; trace только diagnostic | Полнота trace unproven; конкретный drop может быть подтверждён иначе |
| Counter reset/recreate/wrap либо torn collection | Проверка epoch/identity/монотонности и bounded согласованное окно | Не объединять значения разных generations; ambiguous read — unknown |
| Ранний redirect / XDP / flow offload | Full host attachment inventory, запрет чужих hooks/programs/flowtables | Непроверенный bypass исключает isolation claim |
| Extra NIC, policy route, IPv6/link-local | Полный devices/routes/rules inventory и capabilities/control-plane exclusion | Два снимка не доказывают отсутствие временного attach/detach |
| Подмена IP/MAC, VLAN, fragments | Physical veth binding, строгие allow matches, terminal drops и соответствующие probes | Утверждение ограничено проверенной topology; один IP не identity |
| Доступ к host/metadata/DB | Bridge local paths и inet guards + безопасные fixed test canaries | Не обращаться к настоящим production/metadata services для negative test |
| Broken app принимает за firewall failure | Доставленный RST отличается от drop/timeout | Network path может быть verified, HTTP затем scoped failed |
| Malicious root / Docker socket holder | Dedicated host, исключение чужих holders, доверенные writers | Не защищаем от администратора TCB; без этой предпосылки — unknown |
| Пропала nft apply response | Durable dispatch и exact ownership recovery protocol | Counter/readback не восстанавливает original ownership; quarantine сохраняется |
| Spoofed validator / stale receipt | Role-separated auth, issued run/epoch/binding/deadline | Boolean/HMAC без независимых reads не доказательство состояния kernel |
| Сетевой pass превращают в зачёт | Отдельный admission evidence и shadow store | Никаких CheckRun/Ledger/completion/achievement writes; платина недоступна |

**Источник для bypass, не гипотеза:** Linux flowtable fastpath может обходить последующие Netfilter hooks; counters classic forwarding path тогда не учитывают offloaded packets. Поэтому отсутствие flowtables/offloads — содержательная предпосылка, а не косметический preflight. См. [Linux 6.12 flowtable documentation](https://www.kernel.org/doc/html/v6.12/networking/nf_flowtable.html).

## 6. Рекомендуемый вариант

Выбрать **B с текущей dedicated topology как предпосылкой**. Он сохраняет kernel enforcer и большую часть проверенного lifecycle, а отказывается от неподтверждаемой зависимости «каждый NFTRACE event должен прийти». A заменил бы одновременно datapath, loader и evidence; C потребовал бы нового provisioning и всё равно filter8080. Ни один из них автоматически не решает transient topology или compromised administrator.

### 6.1. Как именно должны работать counters

Это **проект для следующего этапа**, не готовый ruleset:

- Заранее reviewed recipe содержит ingress accounting и отдельные классификаторы для fixed negative probe cases. Классификатор учитывает physical ingress и exact case/flow context и заканчивается `counter; drop`. Он не добавляет allow exceptions. Остальной forbidden traffic попадает в final `counter; drop`, при сохранённой base policy drop как safety net.
- Counter матчится до terminal verdict и после нужных match expressions. Spoofed source не должен исчезать из accounting из-за предварительного trusted-source match. TCP sequence/ports и fixed bounded UDP token можно рассмотреть для связи с context; точные nft expressions/JSON совместимость надо отдельно проверить. Нельзя считать совпадение одного общего drop counter доказательством конкретного nonce.
- Baseline и final values читаются без `reset`. Для пробы заранее задаются N injections, ожидаемый набор counters и delta; на уровне packet/byte accounting надо учитывать выбранный skb path, headers/padding и offloads. Это устанавливается kernel experiment, не арифметикой mock frames. Все priming/ARP и ожидаемые responses учитываются отдельно.
- Нужен закрытый, ограниченный по времени interval без фоновых writers/traffic, с quiescence для чтения after. Не совпавшая точная delta, невозможность отделить фон или задержавшийся packet дают unknown. Увеличивать окно/retry бесконечно нельзя. Повтор measurement — новый sample, старый unknown immutable.

**Ограничение counters по исходникам:** [Linux 6.8 `nft_counter.c`](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/netfilter/nft_counter.c) увеличивает per-CPU packets/bytes и при dump суммирует CPU values с sequence checks. Это не единый атомарный снимок всех rules/counters в один момент. Предлагаемый reader должен обрабатывать ограниченные временные brackets и монотонность, а не объявлять один JSON dump глобальной транзакцией наблюдения. При неоднозначности — unknown; никакого `reset counters` как якобы read-only операции.

Для минимального дизайна предпочтительны rule-local anonymous counters: меньше разделяемых объектов и проще связь с exact rule. Если kernel/parser experiment потребует named counters, это отдельная reviewed schema с проверкой всех references и запретом sharing между cases. Мутирующие counter reset/update APIs не нужны ни validator, ни report reader.

### 6.2. Чего этот выбор не решает

Counters не предотвращают detach, не защищают таблицы от privileged replacement и не доказывают прошлую topology. Статическое readback не доказывает, что ранее неизвестный packet прошёл именно эти hooks. Поэтому полное path review и operational exclusion writers обязательны. Если требуется сильнее — например, доказать отсутствие любого transient extra attachment при независимых writers — потребуется отдельный защищённый lifecycle mechanism; с B в предложенном объёме это не заявляется.

NFTRACE optional diagnostics не должны стать скрытой второй обязательной lossless системой. Вместе с тем packet captures, используемые для конкретного positive path sample или send/ingress correlation, сохраняют собственные loss/truncation checks. Исключение NFTRACE completeness не разрешает принимать повреждённые обязательные observations.

## 7. Минимальный набор компонентов для реализации

Следующий этап **только после review этого отчёта**; suggested scope — counter-evidence foundation, без runtime activation.

| Компонент | Минимальное содержание | Проверяемая граница |
|---|---|---|
| Versioned evidence/assumption contract | Exact scope, method, case set, counter schema, trusted-writer model, freshness/unknown reasons | Старые v3/v4 receipts не принимаются как новые; boolean не даёт release |
| Fixed counter recipe/compiler | Rule-local counters, terminal-drop classification, default-deny unchanged по разрешённым paths | Нет raw nft/URL/command input, диагностических allow exceptions или reset |
| Independent counter-aware reader | Static AST compare отдельно от typed dynamic values; full object allowlist/handles | Разрешить только packets/bytes в утверждённых местах, не игнорировать unknown expressions/objects |
| Counter/probe verifier | Issued plan/context, exact deltas, accounting, quiescence/deadline, safe evidence | Missing/extra/reset/replaced/stale/foreign counters и silence не дают verified |
| Дополнение inventory/model | Routes всех tables, policy rules/IPv6, control-plane exclusion/invalidation и external-FD review | Нет утверждения topology continuity по двум snapshots |
| Offline test plan | Forged/mixed generation receipts, counter перед accept, неверный match/order, фон, wrap/reset, interrupted dump, bypass, transient writer, kill | Существующие positive gates остаются закрытыми; никаких syscall/kernel actions |
| Reviewable VM experiment plan | Exact fresh VM/kernel/nft/source, bootstrap ownership, roles, permissions и rollback | До разрешения нельзя создавать namespaces/rules или отправлять probes |

Первый пакет реализации не должен одновременно делать новый runtime coordinator, eBPF backend и Sandbox integration. Формат API/files согласовать после review; таблица не утверждает, что перечисленные компоненты уже созданы.

## 8. Какие существующие компоненты сохраняются

| Компонент | Сохраняется | Будущее точечное изменение / gap |
|---|---|---|
| Runtime Authority | Approval/enrollment, exact identity phases, durable fences, epoch/deadline, terminal CAS | Новый evidence method принимается только отдельной versioned integration после review |
| Trusted Docker Adapter | Raw-create ownership до inspect, отдельные starts, explicit daemon/session, bounded API | `physical_network_boundary_not_accepted` сейчас не трогать; runtime release отдельный gate |
| HTTP Runner / predicate | Numeric IPv4:8080 `/`,200/body≤1024/trailing LF, no DNS/proxy/redirect, PROBE/RESULT/FINISH | Семантику HTTP сохранять; timer/artifact binding потребуют нового approval, если меняется общий budget |
| Durable ownership / exact cleanup | Known IDs/domains, remove receipt, immutable history, pending cleanup circuit | Counter evidence не разрешает adoption, повтор create/remove или восстановление неизвестного ID |
| Shadow stores | Отдельные protected journals, sanitized report, no academic writers | Новый receipt/store version при несовместимом schema; без переинтерпретации старых unknown |
| Physical installer | OFF/auth, durable dispatch, exact owned handles, atomic replace, независимый readback, quarantine | Новый approved recipe digest; initial host-only bootstrap/передача ownership всё ещё prerequisite |
| Namespace inventory/helper | Exact PID/start/netns/veth/MAC/IP/EndpointID; host helper вне task filesystem | Сейчас `inventory.py` читает link/address, **не routes/RPDB**. Это надо дополнить; approved known-pair scope не выдавать за setup пустой VM |
| Network Lifecycle | Bootstrap→active→before-probe→after-probe→pre-publication→FINISH→bootstrap/cleanup gates | Mock lifecycle не runtime-ready. Новый validator port/typed receipts и explicit composition; не duck typing прежних sealed mocks |
| Physical collector / trace parser | Исторический unknown и diagnostic value | Новый counter measurement — sibling/versioned method; старый collector не объявлять positive |
| Live policy / scope | Сейчас v2 digest и8s неизменны, external-only scope | Сохранить HTTP predicate; изменённые network evidence/timing должны получить новый approved artifact/digest, старый proposal не активировать автоматически |

Особый кодовый gap: [`canonical_readback`](trusted_checker_live/egress.py) допускает только table/chain/rule и сравнивает expressions; произвольные counter values сейчас не отделены от static structure. Просто «удалить все counters из compare» опасно: тогда исчезнет проверка их расположения и provenance. Новый reader должен исключать только typed числовые значения в exact approved counter expressions, сохраняя их presence/order/references и reject неизвестных полей.

Другой незакрытый gap — независимый producer committed nft transaction trace для lost response recovery. Его нет в №20.1b-4; counters не заменяют этот producer. Минимальная первая VM session может оставлять любой ambiguous apply в quarantine и прекращаться без автоматического recovery. Безопасный способ закрыть такие ресурсы должен быть согласован заранее; current readback не делает их owned.

## 9. Какие security invariants требуют отдельного согласования

| Изменение предлагаемого контракта | Что надо явно принять |
|---|---|
| Event completeness → enforcement/readback/counter evidence | Доставка каждого NFTRACE event не требуется новому method; historical full matrix остаётся unknown |
| Transient topology guarantee | Принимается trusted exclusive control-plane assumption на всё окно либо требуется отдельный continuity mechanism. Молчаливо ослаблять `deny_extra_attachment` нельзя |
| Meaning `network_isolation_verified` | Model-scoped admission evidence с указанными предпосылками; не continuous attestation и не academic verdict |
| Counter recipe | Новые match/counter/terminal-drop statements и evidence schema являются immutable approval content, а не runtime instrumentation без review |
| Trust/roles | Кто реально может менять daemon/netns/routes/nft/tc/XDP/maps, как исключены другие writers, как validator независимо читает kernel |
| Timing/cache | Новый измеренный budget и правила host-epoch invalidation;8s не повышается env override,30s proposal не становится SLA |
| Kernel/platform | Exact VM/kernel/vendor patches/nft JSON, native bridge CT, offload/IPv6/br_netfilter compatibility; no unsupported fallback |
| Setup/recovery | Host-only bootstrap до provisioning, ownership между generations, случай lost apply и отдельные rollback permissions |

**Не предлагается ослаблять:** default-OFF; authenticated exact approvals; dedicated VM; no raw user Docker/nft/URL inputs; exact daemon/image/container/netns/network generation; no target exec/check.sh trust; runner hardening; no silence-as-drop; unknown на uncertainty; immutable terminal; durable one-use mutation intent; exact ownership cleanup; unresolved circuit/kill; separate shadow evidence; отсутствие любого влияния на Sandbox progress, completion, achievements/платину, mentor/AI, Roadmap и адаптацию.

В этой задаче ни одно изменение invariant не утверждено и не реализовано. Одобрение документа само по себе не разрешает VM access или mutations; последующий scope определяется отдельным заданием пользователя.

## 10. Timing и deployment implications

Текущие live v2 **8s недостаточны для worst-case полной последовательности**: caps create3s + start3s + HTTP2s уже исчерпывают бюджет без identity/readback/probes/finalize. Это арифметический вывод из текущих constraints, не runtime benchmark. [30s proposal](trusted_checker_network/timing.py) и [physical proposal](trusted_checker_physical/policy_proposal.py) не являются live policy/SLA. Physical path повторяет множество inventory/preflight reads с индивидуальным cap3s; их worst-case сумма не доказана≤30s.

| Вне per-run critical path, под approved host epoch | Свежие проверки каждого run/gate |
|---|---|
| Kernel/config/package/source manifest, reviewed binaries и их версия | Boot/daemon/session/transport witness; действующие approval/epoch/kill/deadline |
| Reviewed dedicated-host setup и bootstrap ownership establishment | Current exact own table identity, full rules/attachment state и отсутствие чужих paths |
| Compatibility nft JSON/counter semantics, pre-approved rules compiler | Target/Runner PID/start/netns/veth/EndpointID/generation, device/route/rule state |
| Статический privilege/role deployment review | Передача exclusive control-plane lease и отсутствие разрешённых concurrent writers |
| Подготовка immutable artifacts и fixed probe definitions | Baseline/deltas, bounded probes, live endpoint, before/after/publication validation, FINISH/exit |

Cache разрешён только при определённом host epoch и ясных invalidation conditions. Reboot/daemon restart, source/config/module/sysctl/offload/LSM/role changes, foreign hook/interface/workload, потеря контроля над writers или неподтверждённый state transition аннулируют host acceptance. TTL сам по себе не доказывает актуальность. Проверки mutable facts нельзя вынести из run только потому, что они медленные; способ их дешёвого безопасного чтения сначала проектируют и измеряют.

B потенциально устраняет NFTRACE socket/stream decode/correlation и часть capture overhead, но добавляет counter reads и quiescence. Это гипотеза экономии операций. A может быстро читать maps, но добавляет attach/identity/loader checks; C уменьшает paths, но меняет provisioning. Ни для одного варианта конкретное время не установлено. Снимать per-stage wall/monotonic count/total/max, полную duration и worst-case behavior нужно на реальной approved VM; nested times не складывать дважды.

Deadline остаётся абсолютным с monotonic fence, без продления retries. Недостаточно времени на обязательную свежую проверку — unknown/STOP. Cleanup/recovery имеет отдельный operational budget и не открывает повторный PROBE. Будущий новый timing contract утверждать после измерения стадий, включая after-probe/pre-publication; нельзя сократить их до одного начального readback ради8s.

Deployment сохраняет dedicated-host requirement: текущие global bridge default-drop hooks могут затронуть все bridges. Ни readback, ни counters не делают их безопасными для shared VDS. Прежняя VDS, historical orphans и их evidence исключены. Linux VM/provider suitability, usable privileges/offloads и безопасный management channel необходимо установить отдельно; локальная macOS environment этого не подтверждает.

## 11. План первого реального эксперимента

**Не выполнялся и не разрешён этой задачей.** Перед ним — review §9 и offline counter foundation. Цель первого опыта — подтвердить kernel counter evidence method, а не сразу получить green end-to-end Sandbox run.

1. Согласовать новую disposable dedicated VM, exact kernel/nft versions/builds, host/source identities, OS roles, доступ и перечень разрешённых mutations. Сохранить management/recovery path вне экспериментальных bridge hooks. Подготовить ownership/setup journal и bounded rollback plan до создания resources; не использовать будущие fabricated PID/inode.
2. Отдельно разрешённый read-only preflight: modules уже присутствуют, nft/native bridge CT, sysctl/offloads/LSM/capabilities, отсутствие foreign hooks/XDP/tc/flowtables/bridges/workloads. STOP на unsupported facts; не чинить host автоматически. Не использовать старую VDS даже как convenience endpoint.
3. После explicit setup approval создать только test namespaces/veth/bridge для опыта без platform DB/Redis/Django и без настоящих Sandbox attempts. Если выбран standalone netns harness, его opaque refs остаются test refs и не превращаются в RuntimeEnrollment. Все newly created resources учитываются отдельно. Перед untrusted traffic установить owned bootstrap deny.
4. Установить одну reviewed active counter recipe для полученных реальных tuples. Независимо прочитать целый ruleset и own handles, counter identities, routes/RPDB/links и attachments. Проверить nft parser/atomicity/normalization. Exit0 или snapshot шаблона от installer недостаточны.
5. Снять baseline, выполнить fixed positive path sample с test listener, затем serial negative cases: other target ports, other IPv4, host, metadata-shaped address, test DB/Redis/Django ports, DNS TCP/UDP, IPv6, source/VLAN spoof. Это header probes только к утверждённым test destinations, не доступ к реальным services. Для drop нужны ingress и exact terminal counter delta; для allow — доставленный matching response.
6. Повторить с отсутствующим/loopback-only listener: доставленный RST должен отличаться от firewall drop и silence. Проверить background/дубли/неполную injection, counter reset/replacement и read interruptions. Эти fault mutations требуют отдельного разрешения. Ambiguity не «допускать с погрешностью», а фиксировать unknown.
7. Проверить отказ на лишнюю route/interface/hook и смену generation, kill/deadline. Controlled transient attach/revert **не считать обнаруженным**, если два снимка его пропустили: опыт должен зафиксировать предел snapshots и проверить выбранный запрет writers. Если нужен continuity независимо от модели, остановиться и расширить design, а не записывать success.
8. Измерить стадии и accounting на нескольких bounded samples: реальные packets/bytes delta, noise/ARP, read latency и budget exhaustion. Сверить captures/statistics для используемых sample observations; потеря обязательного sample — unknown. Полноту NFTRACE не заявлять и не использовать как acceptance criterion нового method.
9. Подтвердить only-owned bootstrap restore и учёт ресурсов; exact teardown — по отдельному setup ownership и разрешению. Lost apply response ведёт в quarantine, без повторного apply/adopt по имени. Без согласованного способа безопасного closure ambiguous resources опыт нельзя начинать. Evidence/keys/recovery state сохранить раздельно.
10. Выпустить filtered experiment report: выполненные cases, actual kernel/rules/counters/identity refs, timing, unknown/gaps и closure. Лишь после review результатов проектировать physical→authority integration, новую policy/artifact/timer binding и отдельный Docker pilot. Existing closed gates до этого не менять.

Успех первого опыта означает «механизм пригоден для дальнейшей интеграции при таких-то предпосылках», а не runtime acceptance, security sign-off, отсутствие всех bypass или учебный зачёт. Если точную counter correlation нельзя получить без неуправляемого фона/несовместимого kernel behavior, рекомендацию нужно пересмотреть по фактам опыта; положительный receipt не выдавать.

## 12. Источники

Источники открыты при исследовании 19 октября 2026. Kernel tags фиксируют исследованный upstream код; они не подтверждают vendor builds. Версии web manuals указаны по страницам; где release не закреплён, это явно отмечено. Технические выводы проекта сверх прямого содержания источника помечены как предложение/вывод в соответствующих разделах.

| Первичный источник | Версия / используемый факт |
|---|---|
| [Linux NFTRACE source](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/netfilter/nf_tables_trace.c) | v6.8: event construction, allocation failure, seq0, packet context |
| [Linux NFTRACE source](https://github.com/torvalds/linux/blob/v6.12/net/netfilter/nf_tables_trace.c) | v6.12: повторная проверка allocation return и seq0 |
| [Netlink manual](https://man7.org/linux/man-pages/man7/netlink.7.html) | Linux man-pages6.19: ненадёжность kernel→userspace, ENOBUFS |
| [nft counter implementation](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/netfilter/nft_counter.c) | v6.8: per-CPU accounting, dump aggregation; не глобальный snapshot всех counters |
| [nftables Counters](https://wiki.nftables.org/wiki-nftables/index.php?title=Counters&oldid=1092) | Project wiki revision1092,27.08.2023: explicit counter placement, named/anonymous, чтение/reset |
| [nftables manual](https://netfilter.org/projects/nftables/manpage.html) | Текущая project web edition, без закреплённого release: terminal drop и non-final accept; синтаксис конкретного установленного nft ещё проверять |
| [Configuring chains](https://wiki.nftables.org/wiki-nftables/index.php/Configuring_chains) | Project wiki web edition: base-chain attachments, priorities и policy; не acceptance выбранной VM |
| [Bridge conntrack source](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/bridge/netfilter/nf_conntrack_bridge.c) | v6.8: подтверждает зависимость текущего design от native bridge CT; текущий profile/filter priority описан в №20.1b-3 |
| [Flowtable infrastructure](https://www.kernel.org/doc/html/v6.12/networking/nf_flowtable.html) | v6.12: fastpath bypass и counters classic path |
| [BPF TC classifier](https://raw.githubusercontent.com/torvalds/linux/v6.12/net/sched/cls_bpf.c) | v6.12: direct-action result, включая TC_ACT_SHOT |
| [TCX source](https://raw.githubusercontent.com/torvalds/linux/v6.8/kernel/bpf/tcx.c) | v6.8: link identity/query/update/detach; наличие API не защита от privileged modification |
| [BPF array maps](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/bpf/map_array.rst) | v6.12: preallocated arrays и per-CPU values |
| [BPF ring buffer](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/bpf/ringbuf.rst) | v6.12: reserve failure и границы event delivery |
| [BPF verifier](https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/bpf/verifier.rst) | v6.12: access/pointer/reference checks; не semantic proof network policy |
| [BPF syscall implementation](https://raw.githubusercontent.com/torvalds/linux/v6.12/kernel/bpf/syscall.c) | v6.12: map freeze и capability/type checks |
| [libbpf API](https://libbpf.readthedocs.io/en/v1.6.0/api.html) | 1.6.0: TCX attach, pin lifetime, perf lost callback |
| [Network namespaces](https://man7.org/linux/man-pages/man7/network_namespaces.7.html) | Linux man-pages6.19: namespace resources и связь через veth |
| [Capabilities](https://man7.org/linux/man-pages/man7/capabilities.7.html) | Linux man-pages6.19: NET_ADMIN/NET_RAW/BPF/PERFMON scopes |
| [ip-route](https://man7.org/linux/man-pages/man8/ip-route.8.html), [ip-rule](https://man7.org/linux/man-pages/man8/ip-rule.8.html) | iproute2 project manuals, web editions без pinned package release: local/link routes и policy routing |

Project evidence: [`physical/collector.py`](trusted_checker_physical/collector.py), [`trace.py`](trusted_checker_physical/trace.py), [`rules.py`](trusted_checker_physical/rules.py), [`installer.py`](trusted_checker_physical/installer.py), [`preflight.py`](trusted_checker_physical/preflight.py), [`inventory.py`](trusted_checker_physical/inventory.py), [`network/contracts.py`](trusted_checker_network/contracts.py), [`network/lifecycle.py`](trusted_checker_network/lifecycle.py), [`network/rules.py`](trusted_checker_network/rules.py), [`live/egress.py`](trusted_checker_live/egress.py), [`live/adapter.py`](trusted_checker_live/adapter.py), runtime contracts/authority и соответствующие existing tests. **495 tests OK — результат предыдущего этапа по входному контексту; в №20.1b-5 тесты не запускались.**

## 13. Нерешённые вопросы

1. Принимается ли model-scoped evidence без complete trace stream и без независимого доказательства любой transient topology mutation? Если нет, B в предложенном минимальном объёме не удовлетворяет требованиям; gate остаётся закрытым.
2. Кто обеспечивает exclusive control plane на новой VM, какие daemon/background writers существуют и как блокируются либо инвалидируют host epoch? Обычный DB lease или отсутствие operator команды этого не доказывает.
3. Какие точные packet fields/nonce expressions и counter placement дадут однозначную корреляцию на approved kernel/nft? Как безопасно ограничить ARP/background traffic и получить согласованные reads без reset? Ответ требует отдельного kernel experiment.
4. Какой реальный kernel/vendor build/nft/virtual NIC соответствует profile, включая fixed offloads, br_netfilter и native CT? Строка версии и495 unit tests этого не устанавливают.
5. Как оформить host-only bootstrap ownership до появления pair и безопасно передавать его между generations без stacked global drop tables? Как закрывать ambiguous first apply без присвоения чужих handles?
6. Какие роли/privileges/FDs реально разделены между installer, reader, packet helper и validator; как исключить inherited network sockets и изменение namespace через другой holder?
7. Какой измеренный budget и policy/artifact version принять после стабилизации method? Какой immutable host acceptance можно переиспользовать и какими фактами доказывается его invalidation?
8. Нужен ли independent committed transaction observer для автоматического recovery первого pilot либо допускается остановка с manual quarantine? Counters/readback этого решения не заменяют.

Проверка артефакта:13 требуемых разделов, ссылки на существующие project files, парность fenced blocks и whitespace проверены локально. SHA-256 всех140 сохранённых baseline artifacts совпали; tracked Git diff пуст. Создан только этот отчёт. Docker/daemon/kernel/network/namespaces/firewall/eBPF, VDS и historical resources не использовались; production-код, tests и live policy не менялись. Commit/push/rebase/deploy не выполнялись.

**Итоговая рекомендация одна: согласовать вариант B — существующий nftables default-deny + independent full readback + exact topology + terminal-drop counter deltas + bounded probes на новой dedicated VM, с явно принятым trusted exclusive-control-plane assumption. Сначала отдельный offline counter-evidence foundation; затем отдельно разрешённый kernel experiment. До review реализацию не начинать, прежние gates не открывать.**
