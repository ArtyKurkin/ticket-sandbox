# Trusted Checker: Network Enforcement & Active Validation — №20.1b-3

19 октября 2026 · `feature/roadmap-react` · база `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

## 1. Результат и граница готовности

Добавлен `trusted_checker_network`: operator-only installer, независимые readback и collector, проверка packet/capture chains, полная закрытая matrix из 10 групп, durable install/recovery state и дополнительные gates в mock Runtime Authority composition. **Реализованы и проверены алгоритмы на sealed mock host; сетевые пакеты не отправлялись. Network isolation и runtime acceptance не подтверждены.**

Все новые receipts имеют mode `offline_network_mock_v3` и отдельный signing domain `tc-network-mock-v3`. Они не преобразуются в live `EgressValidation`. Реальный backend применения nft, injection/capture/event-stream helper и его authenticated transport в этой задаче не подключаются. Наличие синтетического `PacketEvent(stage="drop")` в тесте не является доказательством kernel drop.

В supported path `TrustedDockerAdapter` теперь отклоняет default physical SDK factory **до daemon witness/socket/client** с `physical_network_boundary_not_accepted`, включая recovery. Старые offline tests используют явно переданный mock factory. Это предохранитель от случайного запуска с mock evidence, а не sandbox против hostile Python code или владельца daemon/ключей. Прямые низкоуровневые utilities предыдущего этапа не являются разрешённой entry point этой задачи.

Изучены [аудит №20.0](TRUSTED_CHECKER_SANDBOX_INTEGRATION_AUDIT.md), [№20.1a](TRUSTED_CHECKER_SHADOW_FOUNDATION.md), [№20.1b-1](TRUSTED_CHECKER_RUNTIME_PROVENANCE.md), [№20.1b-2](TRUSTED_CHECKER_LIVE_RUNTIME_IMPLEMENTATION.md), актуальные contracts, authority, egress, host inventory, composition и тесты. Прежние отчёты, evidence и synthetic/offline policy не изменялись. Нет Django/Celery hooks, metadata DB reader или academic writes.

## 2. Выбранная архитектура и прежняя VDS

**Следующий acceptance следует готовить на новой полностью выделенной VM. Безопасность прежней VDS для этих hooks не установлена; разрешения использовать её нет.** Она не инспектировалась в этой задаче. Из входного контекста известны historical quarantine containers, которые нельзя принимать, перемещать или удалять автоматически. Сосуществование с ними и возможными socket holders не удовлетворяет выбранному isolated-host profile. Даже отдельный второй dockerd на прежнем host не изолирует host netfilter hooks от других Linux bridges.

Рассмотрена локализация по bridge name, iif/oif, physical veth и namespace. Они полезны как bindings, но разные пути требуют разных hooks:

| Путь | Контроль v3 | Почему одного interface name недостаточно |
|---|---|---|
| Same-bridge L2 | Native bridge prerouting/forward, physical veth + exact MAC/IP/endpoint | Пакет может вообще не проходить routed inet FORWARD; имя может быть переиспользовано. |
| Доступ к host/gateway | Bridge input/output default drop | Переключение только forward rules не закрывает local delivery. |
| Routed/cross-network | Inet input/forward/output deny для tcsh0 | Нужен отдельный учёт host/routed path и br_netfilter. |
| Extra attachment | Exact namespace interface set + protected event continuity; любой drift закрывает admission | Это detection/rejection, а не физическая защита от malicious daemon administrator, который добавил альтернативный macvlan/tunnel. |

Сохранены **global bridge default-drop hooks**. Они способны нарушить работу всех bridges host, поэтому установка на shared VDS запрещена. Доказать безопасную локализацию для rename/reuse, local delivery, VLAN, host-generated traffic и кратковременного extra attachment одними Python/mocks нельзя. Решение v3 не заявляет такую гарантию. Dedicated VM, один approved bridge tcsh0, один task/runner pair и отсутствие чужих workloads/socket holders — обязательные условия.

Привязка включает host boot UUID/identity digest/netns inode, daemon endpoint/config/session, full NetworkID, bridge ifindex/MAC, runtime approval/binding/generation и оба exact namespaces: Docker ID/StartedAt/RestartCount/EndpointID/IP/MAC, PID/process start ticks/netns inode, physical veth ifindex и peer ifindex. Approved values поступают от доверенного control plane, не из trainee JSON, labels или имени сети. Фактическая проверка этих values Linux helper остаётся runtime prerequisite.

## 3. Новый ruleset и kernel requirements

Network policy: `dedicated-host-network-v3`, mode `offline_network_mock_v3`, digest:

```text
ea3f6abadfa95dd8d870f6c7f974d673b72ef9c0039ba1655f55de43373fb07c
```

`rules.py` переиспользует pure compiler предыдущего этапа, но создаёт отдельную версию: две таблицы `tc3_<full approval UUID>` в bridge/inet families, explicit EtherType dependencies и bridge priority **0**. Нужны native bridge conntrack, точная kernel/nft JSON совместимость и отсутствие конкурирующих bridge hooks/flow offload. `br_netfilter` должен быть выключен/неактивен; код его не переключает.

Причина изменения priority: в исследованном Linux 6.8 native bridge prereouting conntrack зарегистрирован на `NF_IP_PRI_CONNTRACK`, равном −200. Старый filter на −310 обращался к `ct state` раньше него; этого недостаточно для допуска response как established. Priority 0 помещает новый filter после conntrack. Это вывод из исходников, а не выполненный packet test выбранной VDS: [bridge conntrack implementation](https://raw.githubusercontent.com/torvalds/linux/v6.8/net/bridge/netfilter/nf_conntrack_bridge.c), [priority constants](https://raw.githubusercontent.com/torvalds/linux/v6.8/include/uapi/linux/netfilter_ipv4.h).

Active rules допускают только runner→target TCP8080 и established response, ограниченный ARP для пары; sender/receiver MAC/IP, physical ingress/egress и отсутствие IPv4 fragments проверяются явно. IPv6, VLAN и прочий L2/IPv4 трафик не имеют allow rule. Bootstrap содержит только deny. Inet guards сохраняются на −310. Старые `tc_shadow` templates/receipts и live policy v2 не переписываются и не объявляются совместимыми с этим ruleset.

`transaction_for` рендерит одну nft transaction. Первое создание tables — exclusive `create`, чтобы коллизия имени не позволяла присвоить чужие rules. Последующая замена — delete **двух уже owned tables** + fixed approved add. Нет flush ruleset, wildcard/list-selected delete или удаления чужих tables. Совпадение UUID/name само по себе не ownership. Atomic transaction semantics и parser обязательно проверить отдельно на утверждённом Linux; в этой задаче nft не запускался. Общая модель hooks/transactions описана в [официальном руководстве nftables](https://netfilter.org/projects/nftables/manpage.html).

## 4. Trust boundary и файлы

Новые production-модули:

| Файл | Назначение |
|---|---|
| `trusted_checker_network/__init__.py` | Без runtime bootstrap. |
| `contracts.py` | Frozen policy/approval, host/namespace/generation identities, receipts. |
| `auth.py` | Closed DTO types, отдельные operator/installer/host/capture/validator roles и HMAC keys. |
| `rules.py` | Fixed v3 compiler и ownership-constrained atomic transaction render. |
| `store.py` | Отдельный `*.network.sqlite3`,0600, immutable docs/intents/receipts, circuit и fsynced stop latch. |
| `host.py` | Единственный разрешённый `MockNetworkHost`; independent readback algorithm. |
| `installer.py` | Approval, durable dispatch, exact atomic apply, readback, authenticated historical attestation, quarantine/recovery/rollback. |
| `packets.py` | Конечный план header probes; checksum/L2/IP/TCP flow parsing, padding и TCP options. |
| `collector.py` | Проверка подписанного bounded capture и полного packet evidence chain; typed matrix/unknown. |
| `lifecycle.py` | Supplemental mock Runtime Authority gates, fail-closed abort/rollback, no resume. |
| `timing.py` | Отдельный versioned budget proposal, не execution authority. |

Новые tests: `tests/support.py`, `test_installer.py`, `test_collector.py`, `test_lifecycle.py`, `tests/__init__.py`.

Из existing files изменены только `trusted_checker_live/adapter.py` (physical factory guard) и `composition.py` (explicit optional mock network gates/abort). Это **не** реализация v3 live backend и не изменение authority receipt union. Проверка SHA-256 всех 99 baseline files выявила только эти два изменения; остальные 97, включая предыдущие отчёты, runtime/shadow/PoC исходники и старые tests, сохранены.

TCB: trusted Python composition, OS/journal owner, configured operator, installer, host transaction observer, независимые capture и validator principals. Разные HMAC keys/scopes/roles обязательны, но в тестах процессы не имеют физической независимости. HMAC подтверждает origin supplied receipt; он не аттестует kernel/host. Runner не получает ключей, socket, host mounts или target filesystem access.

## 5. Installer lifecycle

```text
signed operator approval + exact runtime/host/network/rules binding
  → immutable approval + fixed bootstrap/active recipes
  → persisted install intent + dispatched BEFORE host.apply
  → atomic compare-and-apply under exact ownership/generation
  → authenticated host apply acknowledgement persisted BEFORE readback
  → independent complete readback + repeated host/kill/deadline checks
  → immutable activation receipt + separately authenticated attestation

ambiguous apply / lost reply / drift / incomplete readback
  → quarantine + admission circuit
  → best-effort exact-owned bootstrap rollback
  → independent recovery/rollback; never automatic active adoption
```

Approval registration проверяет digest **и** равенство recipe fixed compiler, schema2 runtime approval, daemon/network/IP bindings. Даже операторский hash произвольного allow ruleset не подходит. Незнакомые request/rules/owner inputs не становятся Docker/nft commands.

Перед dispatch — короткая SQLite transaction. Host mock mutation вне DB transaction; другой activation видит committed dispatched job и отказывается. Повтор того же request с тем же fingerprint возвращает прежнее состояние/receipt; другой payload конфликтует. Сбой процесса после apply оставляет dispatched intent; повтор ничего не применяет. Отдельный подписанный host transaction trace может восстановить **только ownership**, после чего разрешён лишь rollback к bootstrap. Простое наличие rules по похожему имени или exit0 не считается install success.

Independent readback заново читает полную table/chain/rule structure. Partial/foreign readback, чужой generation/owner, extra rules или error дают quarantine. Если известен точный owned generation, ошибка вызывает restore bootstrap; если outcome неизвестен, ownership/rollback нельзя выдумать. Чужая таблица, host/daemon change либо неразрешимый ownership конфликт требуют остановки и ручного разбирательства.

Rollback допускается после kill/expiry и не требует живого прежнего runner namespace. Exact host/daemon/network anchor и table ownership всё равно обязательны. Rollback failure сохраняет circuit; успешный rollback после ошибки **не** снимает quarantine и не разрешает новый active. Нет автоматического TTL release/force resume.

Первый integrated mock session обслуживает ровно одну approved пару. Session restart/resume и смена binding в том же issued session отвергаются. Одновременное добавление нового approval поверх оставшегося global bootstrap другого owner не поддерживается и не считается разрешённым resample: старый drop hook помешал бы новому allow. Для live нужны отдельные reviewed pre-provision bootstrap ownership и передача/закрытие этого ownership между samples. Нельзя обходить это удалением tables по именам.

## 6. Collector lifecycle и independent evidence

Collector принимает только exact sealed mock host и установленные signer/verifier. В нём нет socket, setns/nsenter, subprocess, Docker SDK, HTTP client или команды из target. Capture provider в tests строит explicit synthetic frames. **Физический namespace injector/capture/netlink/nft trace backend отсутствует**, произвольный Python plugin не принимается как уже проверенная Linux implementation.

Перед matrix проверяются active ownership/rules readback и deadline/stop. Для нового matrix UUID строится deterministic finite plan; UUID+binding digest задают уникальные probe IDs/TCP sequence. Нет произвольных URLs, DNS resolution, адресов/портов из оператора или команд target. Все canary IPs заранее закреплены approval; они должны быть безопасными test destinations на dedicated VM, не реальными production DB.

Capture contract связывает matrix UUID, rules generation/digest, exact namespace tuple до/после, trusted packet sequence, bounded frame bytes и времена. Пределы: **256 events ×128 bytes**, matrix≤2s, observation age≤3s; штатный план —15 probes,47 events. Превышение, gaps, truncation, packet/netlink loss, чужой frame/probe/generation, stale observations, extra interfaces/bridges или изменение PID/start/netns/EndpointID/IP/veth закрывают scope.

Для negative probe обязательна цепочка **send → physical ingress → конкретный hook drop** одного и того же frame с bound sequence/rules generation. Отсутствие ответа не доказательство deny. Для allow probe нужны send → ingress → target ingress → target response → runner receive; MAC/IP, ports, ACK=probe sequence+1, checksums и TCP flags проверяются. Поддержаны bounded TCP options и допустимый Ethernet padding. Arbitrary payload не нужен; parser не использует trainee body.

В будущем physical backend должен независимо связать capture с kernel hook/trace (например, reviewed nft trace/eBPF drop evidence), наблюдать правильный netns и все interfaces, подтверждать injection, loss counters и отсутствие gaps до/после окна. Передача dictionary с `verified=true` запрещена. Где именно получен drop, namespace inode/process start и capture/event sequence нельзя выводить из target stdout. Linux packet capture имеет явные признаки потерь; zero-loss accounting нужно собирать на реальном boundary, а не выводить из пустого pcap. См. [Packet MMAP / statistics](https://www.kernel.org/doc/html/v6.12/networking/packet_mmap.html).

Capture receipt подписывает отдельный capture principal. Validator перепроверяет signature/role/scope, **сам** анализирует packet chain, повторяет rules readback и подписывает `MatrixReceipt`. В durable state попадают только bounded outcomes, refs/digests и reason codes. Raw frames, signatures, API errors, arbitrary stdout/HTTP body, credentials, ownership tokens и trainee answers не архивируются. Wrong/unknown capture не выдаёт positive matrix receipt; safe `matrix_unknown` хранит только allowlisted reason.

## 7. Закрытая negative matrix и verdict semantics

| Группа | Проверяемое evidence в алгоритме |
|---|---|
| allow_target_8080 | SYN доставлен target; подтверждённый SYN-ACK **либо RST-ACK** вернулся runner. |
| deny_other_target_ports | Target8081 и22: ingress + hook drop, отсутствие target delivery. |
| deny_other_ipv4 | Approved other IPv4:443: явный drop. |
| deny_host | Approved gateway443: явный drop. |
| deny_metadata | Fixed169.254.169.254:80: явный drop, не реальный metadata HTTP request. |
| deny_db_redis_django | Approved test canaries5432/6379/8000: все три drops обязательны. |
| deny_dns | UDP53 и TCP53: оба drops; resolver не запускается. |
| deny_ipv6 | Bounded IPv6 TCP header probe: drop. |
| deny_spoofing | Подменённый source IPv4 и tagged L2/VLAN attempt: drops. |
| deny_extra_attachment | Other-IP attempt + exact interface inventory + lossless event continuity; extra interface/bridge запрещает выдачу matrix. |

Эти samples не перебирают все порты/IP/protocols. Полное compare fixed default-deny rules дополняет finite active tests. Extra-attachment criterion подтверждает **admission rejection/event detection в модели**, а не проведение физического hostile attach/detach или защиту от administrator-controlled tunnel. Root target/runner не получают NET_ADMIN/NET_RAW; privileged collector входит в TCB. Невидимая/потерянная мутация или malicious host исключают isolation claim.

| Ситуация | Результат сети / учебный смысл |
|---|---|
| Broken loopback app, target возвращает valid RST | `path_open_rst`: разрешённый путь работает; затем HTTP peer дает scoped failed/refused. Это не network failure. |
| Fixed wildcard app, valid SYN-ACK | `path_open_synack`: только доказательство пути; HTTP200/body отдельно определяет scoped predicate. |
| Нет ответа и нет достоверного drop trace | Unknown; нельзя назвать ни delivered RST, ни успешно заблокированный egress. |
| Allow8080 dropped at firewall | Unknown matrix; PROBE запрещён. |
| Endpoint отсутствует/изменился | Unknown `capture_endpoint_unavailable`/identity drift. |
| Capture loss / collector fault | Раздельные `capture_loss` / `capture_collector_error`, оба unknown. |

Ни network matrix, ни external HTTP match не доказывают loopback, application authenticity, persistence или полный success задания. Platinum и academic evidence недоступны этому пакету.

## 8. Runtime Authority gates, kill и cleanup

Optional **mock-only** `MockNetworkLifecycle` сверяет issued Runtime Authority run/enrollment/ownership, runtime approval/binding/generation и сохранённый runner-live identity. Чужой supplied UUID не является enrollment. Gate sequence сохраняется append-only:

```text
bootstrap installed + independently verified
 → target identity + runner identity verified
 → active installed + readback
 → complete independent matrix → PROBE permitted
 → HTTP/result → after-probe matrix/rules/identity
 → authority before-publication checks + independent matrix
 → FINISH/exit0/exact final config → bootstrap restored
 → immutable authority terminal → exact runner cleanup confirmed separately
```

Первоначальное target/runner provisioning пока проверяется старой mock boundary. Supplemental gate начинается после authority `record_runner_live`; он **не** заявляет установку v3 bootstrap до первого реального target create. Для физического rollout нужен отдельный setup approval/ownership stage до provisioning и versioned transport integration, а не заранее выдуманные будущие PIDs/inodes. Текущий физический SDK guard запрещает такой неполный rollout.

До/после matrix повторяются full host identity и active readback; authority сохраняет собственные guards на всех старых фазах. Drift/deadline/kill/incomplete validation → unknown без нового create/start или PROBE retry. Ошибка decoder/adapter после activation также вызывает network abort/restore bootstrap. Повтор команды возвращает старый run, session resume запрещён. Финальный terminal immutable; recovery/cleanup не повышают unknown в passed.

`stop()` сохраняет fsynced0600 latch вне SQLite mutation lock. Kill во время activation/capture запрещает выпуск PROBE; уже начавшуюся host mutation он не отменяет задним числом. Rollback остаётся доступным после stop, но не снимает circuit и не удаляет tables других owners. Ошибка rollback учитывается как unresolved, не маскируется success.

Exact container cleanup остаётся в существующем `ExactCleanup`: только known owned runner ID/daemon/session/image/receipt, durable remove intent и confirmed204; targets/history/orphans не выбираются по labels/name. Network gate operationally complete только после authority `cleanup=confirmed`. Terminal verdict с pending cleanup сохраняется; это не завершённая операция. Fault не вызывает компенсирующих учебных writes.

## 9. Timing budget: отдельное предложение

Действующие `LIVE_POLICY`, limits и Runner сохраняют **8s**. Это достаточность не доказана. Уже два API calls на create/start с лимитом3s и HTTP2s исчерпывают8s без inspect, rules, matrix, finalize и cleanup. Нижеследующее — **планируемые caps**, не измеренные timings/SLA и не разрешение увеличить deadline.

| Этап | Proposal cap, s |
|---|---:|
| Create | 3 |
| Start | 3 |
| Live handshake | 1 |
| Activation + readback | 2 |
| Before-probe matrix | 2 |
| HTTP | 2 |
| After-probe matrix | 2 |
| Publication matrix | 2 |
| FINISH + final config/output | 3 |
| Restore bootstrap | 2 |
| Exact cleanup | 3 |
| Scheduling/lock margin | 5 |
| **Итого** | **30** |

`network-validated-peer-budget-v3-proposal`, digest `8640f6ea2099bd74d6dc8a9e478a3c9db89cf2b8b2dabf90f4f30e87eeadffef`. `fits(8)` отвергается; `fits(30)` проверяет только арифметику contract. Proposal не принимается RuntimeApproval и не меняет runner timer. До live нужны измерения всех дополнительных inspect/witness calls и суммарных stage caps; при нехватке бюджета новая versioned policy/artifact/approval обсуждается отдельно.

В mocks15 windows×0.1s=1.5s на matrix; проверки используют supplied wall deadline и process-local monotonic fence. Реальные syscall/capture/SDK timeouts этими fake timings не доказываются. Overrun/clock uncertainty не продлевают deadline и не дают поздний pass. Cleanup/recovery после terminal имеет отдельный lifecycle и может оставаться pending за пределами run budget.

## 10. Offline проверки

Команды из project root:

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_network/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_live/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_runtime/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_shadow/tests -t .
.venv/bin/python -m unittest discover -s trusted_checker_poc/tests -t .
```

| Suite | Результат |
|---|---|
| Новый network | **69 tests, OK**,4.984s |
| Existing live | **48 tests, OK**,9.710s |
| Existing runtime | **66 tests, OK**,8.263s |
| Existing shadow | **56 tests, OK**,2.060s |
| Existing PoC | **166 tests, OK**,9.872s |
| **Итого** | **405 tests, OK**, без skips |

Логи: `/tmp/task201b3-network.log`, `/tmp/task201b3-live.log`, `/tmp/task201b3-runtime.log`, `/tmp/task201b3-shadow.log`, `/tmp/task201b3-poc.log`. Existing suites выполнены параллельно независимыми Python processes; timings не performance benchmark. Test DBs только TemporaryDirectory, threads синхронизируются Events с watchdog/join, а не sleeps. Проверены две Runtime Authority HTTP branches: RST→scoped failed и SYN-ACK+HTTP200→scoped passed, отдельные finalization/cleanup gates.

Негативные cases: install error/lost response/SystemExit crash, persisted restart replay, чужой/partial readback, name collision/foreign writer, unapproved recipe, forged signer/trace/capture, PID/start/netns/veth/endpoint/generation change, extra topology, kernel profile mismatch, stale/lost/truncated capture, packet sequence/ACK/checksum/L2 mismatch, missing negative/drop trace, allow firewall drop против delivered RST, unknown collector/endpoint, concurrent activation, kill activation/capture/rollback, rollback failure, wall/monotonic deadline, missing before/after/publication validation, decoder error rollback, session resume forbidden и cleanup pending.

На первом прогоне исправлены test fixtures: HTTP packet должен явно иметь transport=none/complete=true; имя budget field — run_seconds. Устранён unclosed SQLite test connection. Final ResourceWarning-as-error прогон не дал warnings. Это исправления fixtures, не ослабление production guards.

Дополнительно выполнен fresh import всех новых модулей под запретом socket constructor и subprocess.run: без обращений. Python AST/syntax, whitespace,11 разделов отчёта и парность fenced blocks проверены. Git diff checks и SHA-256 baseline дополняют тесты; native nft parser и Mermaid renderer не запускались.

Docker sockets/daemon/API, network sockets, packet injection, namespaces, nft/iptables/sysctl и приложения не запускались. `.env`, credentials и рабочие БД не читались. Public Linux sources изучались через web только как документация; это не remote VDS access. Tracked Git diff пуст, новые/untracked прежние artifacts не принимались за часть tracked baseline. Django regression suite заново не запускался: новых writers/integration нет; предыдущие academic regression results не выдаются за новые доказательства этого пакета.

## 11. Runtime plan, rollback и оставшиеся blockers

Этот план **не исполняется** в №20.1b-3.

1. Review отдельной network v3 policy, isolated-host TCB, packet/drop/event evidence sources, бюджета и версии transport. Выделить новую disposable VM; не использовать старые synthetic approvals или historical VDS quarantine.
2. Отдельно одобрить конкретные host/daemon/session/images/network и bootstrap setup ownership **до target create**, без fabricated future PID/inode. Проверить отсутствие чужих bridges/workloads/socket holders/offload/hook conflicts. Dedicated dockerd на shared host недостаточен.
3. Реализовать/review physical host ports: exclusive atomic nft apply, independent full readback, protected host transaction trace, generation-bound namespace inventory и bounded injector/capture/netlink/kernel drop trace. Проверить kernel modules, native conntrack priority, br_netfilter state, JSON parser/readback normalization, Ethernet offload/checksum effects. Mock providers в этот path не импортировать.
4. Проверить negative host/profile/permission admission без mutation. Затем **отдельно разрешить** setup/bootstrap/install, signed real captures и контролируемые network mutations. На неполной matrix — STOP, не подменять receipts fixtures.
5. Только новые authority-owned targets/runners, exact raw IDs/ownership/start/live evidence. Под dedicated bootstrap получить реальные namespaces/veth; выполнить reviewed atomic activation и полный independent matrix **до** PROBE. Allow-RST должен доказывать путь даже на broken loopback app.
6. Broken/fixed cases с физическими observations, затем approved wrong-port/body/endpoint/extra attachment/spoofing, capture loss/unknown activation, kill/rollback и cleanup faults. Extra attachment допускается только контролируемой тестовой mutation на новой VM; event detection не выдавать за неизменяемость сети. Для каждого sample нужен reviewed bootstrap ownership transition; текущая one-pair mock session не разрешает overlapping global tables или автоматический resample.
7. Измерить все стадии, в том числе active negative matrix/trace/readback/FINISH/cleanup. До утверждения нового live artifact действует8s; fake 1.5s не даёт разрешения повысить его. Невыполнимый budget означает unknown/STOP, не увеличение таймера на месте.
8. Safe rollback: latch stop → запрет launches/PROBE → учёт exact late transaction/create responses → verified owned bootstrap restore → exact container cleanup/recovery либо quarantine. При lost install response восстановить ownership только по независимому contemporaneous transaction trace, не по совпадению rules/name. Foreign/ambiguous host tables не удалять.
9. Закрытие scope: учесть каждый owned container/network/table, сохранить state/keys для unresolved recovery. Удаление собственных firewall tables допустимо только отдельным reviewed closing protocol после closure всех endpoints; **такого generic delete API в пакете нет**. Не flush host firewall и не трогать historical orphan/evidence. Не объявлять cleanup complete при pending resources.
10. Сохранить filtered evidence, physical starts/packets/drop traces, actual timings и gaps. Только затем runtime acceptance/security review. Production, Django/Sandbox integration, full-task verdict и platinum остаются отдельными задачами.

Главные remaining blockers — physical installer/capture/trace backend и его независимая установка/privilege separation; initial bootstrap ownership и его переход между generations; versioned live protocol/approval для v3 receipts и, при необходимости, нового timing profile; реальные kernel/nft/namespace/isolation measurements. Эти свойства не подтверждаются HMAC, Python type checks, process-local clocks или успешными405 unit tests.

**Остановка для review. Реальные Docker/firewall/namespace действия, deploy, academic writes, historical evidence/orphan changes, commit/push/rebase не выполнялись.**
