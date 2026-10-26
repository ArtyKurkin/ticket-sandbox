# Trusted Checker: Native v2 Topology Adapter — №20.1b-8d

20 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-03 OFFLINE READY`.** Реализован независимый pure adapter для supplied
iproute2 JSON: bounded decoding, закрытый versioned registry, coverage/provenance
references, immutable source records и namespace-scoped joins. Полный positive
fixture явно synthetic. Все полные schemas имеют статус
`provisional_offline_only`; реальные original artifacts подтверждают только
два частичных native формата. Kernel compatibility и isolation не приняты.

`topology_complete` означает структурную полноту **девяти offline sources**
для host/runner/target и согласованность их ссылок в принятой fixture-модели.
Это не полнота всех OS evidence surfaces: tc/XDP/flowtables/sysctl/offloads/FDs
остаются `unobserved`, происхождение captures и namespace witnesses не
аутентифицировано. `physical_probe_permitted=false` без исключений.
`isolation_verified`, `management_policy_verified` и `measurement_verified`
всегда false. Итог physical audit `NOT READY` сохраняется.

Выполнены только локальные чтение, pure Python, offline tests и документация.
SSH/VDS, ip/bridge/nft/Docker/setns и packet operations не выполнялись.
Collector, installer, authority/physical approval, Django/Ticket Sandbox,
академические transitions и deploy не добавлены. Shadow-only,
`PhysicalProbeGate` и `physical_network_boundary_not_accepted` сохранены.
Commit/push/rebase не выполнялись.

## 1. Архитектура и новые файлы

| Файл | Назначение |
|---|---|
| [`native_v2_topology_json.py`](trusted_checker_network/native_v2_topology_json.py) | Отдельный bounded scanner/parser с exact decimal tokens; nft parser не изменяется |
| [`native_v2_topology_schema.py`](trusted_checker_network/native_v2_topology_schema.py) | Закрытый field registry, source/argv registry, immutable provisional profile и typed field validation |
| [`native_v2_topology.py`](trusted_checker_network/native_v2_topology.py) | Offline descriptors/plan, immutable records, coverage, normalization, joins, envelope и snapshot comparison |
| [`native_v2_topology_support.py`](trusted_checker_network/tests/native_v2_topology_support.py) | Явно synthetic complete host/runner/target, peer/table references и supplied captures |
| [`test_native_v2_topology.py`](trusted_checker_network/tests/test_native_v2_topology.py) | 96 самостоятельных offline tests |
| Этот документ | Реализация, ограничения и результаты |

Использованы неизменённые V2-01 `_Offline2`, `NamespaceKey2`, exact-type guards,
`ContractViolation2` и content-digest domain. V2-02 и v1 не вызываются для
конвертации topology; новый package не создавался. Production imports — только
stdlib и pure v2 modules. Нет OS I/O, discovery, signing, shell или live API.
Таблица argv — данные schema, не исполняемые команды.

| API | Стадия и результат |
|---|---|
| `decode_topology_source2(raw, profile, descriptor)` | `DecodedTopologySource2`, `source_decoded`: bytes/hash/size/profile/schema проверены, но graph ещё не доказан |
| `decode_topology_documents2(documents, profile, plan)` | Проверка batch caps и pinned descriptor membership до parsing; отдельные decoded sources |
| `normalize_topology2(sources, plan)` | `NormalizedTopology2`, `topology_normalized`: раздельные namespace/source records с полной provenance |
| `complete_topology2(normalized)` | `TopologyEnvelope2`: вычисляемые `topology_complete` либо `topology_unproven` с finite reasons и resolved references |
| `compare_topology_snapshots2(candidate, pinned)` | Exact unchanged comparison всех fields, presence и row order; не freshness, continuity или policy proof |

Malformed/unsupported JSON, invalid schema/type/profile и provenance substitution
отвергаются `ContractViolation2` до создания следующей стадии. Недостающие
sources и недоказанные joins представлены `topology_unproven`. Stage/result,
namespace records, joins и resolved references вычисляются; constructor override
этих derived fields запрещён. DTO frozen/slotted. Проверка source constructor
заново связывает immutable rows с исходным UTF-8 text/hash; нельзя заменить
rows при сохранении прежнего descriptor. Raw text — внутренний artifact,
не operator export. Bounded/redacted export этого этапа не реализуется.

## 2. Поддерживаемые schemas и их статус

Все девять полных source profiles — **provisional offline schemas**, проверенные
на synthetic JSON. Это намеренно узкие принимаемые формы, а не утверждение,
что exact Linux/iproute2 build обязательно печатает эти keys или values.
Missing required field отвергается, defaults из kernel/expected graph не
проставляются. Unknown field, nested key, flags literal, unsupported action
или structure отвергаются. Optional field сохраняет точное presence.

| Source / declared argv | Обязательные поля и ограничения |
|---|---|
| `link`: `ip -j -d link show` | ifindex, ifname, flags, mtu, link_type, address. Optional exact registered link attributes; linkinfo kinds bridge/veth. Bridge info_data имеет отдельный закрытый набор options |
| `address`: `ip -j address show` | ifindex, ifname, addr_info. У каждого address: family, local, prefixlen, scope, valid/preferred_life_time; registered optional peer/broadcast/label/flags |
| `bridge_link`: `bridge -j -d link show` | ifindex, ifname, link, flags, mtu, master **name**, state, priority, cost; известные provisional on/off port options |
| `vlan`: `bridge -j vlan show` | ifname, vlans; у row vlan и flags, optional vlanEnd; VLAN 1..4094, range не обратный |
| `fdb`: `bridge -j fdb show` | mac, dev, master, flags, state; optional vlan. В этом profile master обязателен, иная native форма unsupported |
| `route4` / `route6`: `ip -j -4/-6 route show table all` | dst, dev, table, protocol, scope, type; optional gateway/prefsrc/src/metric/flags/pref. Family проверяется. Поддержаны exact unicast/local/broadcast types; multipath/encap/expiry и другие неизвестные fields отвергаются |
| `rule4` / `rule6`: `ip -j -4/-6 rule show` | priority, src, table; optional dst/iif/oif/fwmark/fwmask/suppress_prefixlength/l3mdev/action/protocol. fwmark/fwmask обязательны совместно; action только lookup |

Link и bridge-port схемы разделены: integer `ip master` не заменяется string
`bridge master` и наоборот. Token `default/all`, table alias, marks/masks,
protocol, flags и optional values сохраняются в native форме, без guessed IDs.
Routes требуют explicit table/type/scope в данном provisional profile; если
реальный dump их опускает, это unknown до отдельного schema review.
Unsupported link kinds, route actions и provider attributes не скрываются.

Отдельные diagnostic sources точно отражают имеющиеся команды:
`link_single` = `ip -j -d link show tc-br0`;
`bridge_link_basic` = `bridge -j link show`. Их extent — `single_link` /
`basic_ports`; они никогда не удовлетворяют полному source coverage.
Идентификаторы бинарных сборок — explicit fixture digest references, не
проверенные binaries на host; exact iproute2 build/version acceptance отсутствует.

## 3. Registry, bounds и decimal/volatile fields

`REGISTRY` — immutable tuple из **266 `FieldSpec2`**. Каждый entry содержит
source, exact path (`*` только индекс row), value type, requiredness, constraint,
purpose, evidence reference, disposition и transition. Четыре dispositions:
identity, structural, ordered_policy, observed_volatile. Нет catch-all `extra`.
Immutable `FrozenObject2` хранит только schema-validated keys и typed scalar /
exact decimal / tuple values; неизвестные attributes не получают такой record.
Порядок object keys canonicalized; порядок arrays/rows сохраняется.

`TopologyProfile2` фиксирует profile
`iproute2-native-topology-v2-provisional-offline-1`, binary digest references и
оба registry digests. Input не выбирает profile и не расширяет allowlist.

- Field registry digest:
  `eb52342f871ea66a59cdf0790dbd9f90da7f5f05feedf198a18df44556d3bcbd`.
- Source/argv/required-coverage/bounds registry digest:
  `ab5c7f5a5feb035d5e8115d2ab582ec21def933ac59cbce0042542fddbc2c776`.

| Limit | Enforcement |
|---|---|
| Raw document ≤1 MiB, exact bytes | До UTF-8 decode и parsing; пустой input, invalid UTF-8 и BOM отвергаются |
| Aggregate ≤16 MiB, documents ≤256 | Batch API проверяет весь batch до первого parse; normalization повторно проверяет source totals |
| Depth ≤32 | Проверка child value до container allocation, root depth 1 |
| Nodes ≤65536/document | Values/containers/object keys считаются до добавления следующего node |
| Root/nested arrays ≤1024 | Проверка до parsing следующего element; schema добавляет более узкие field limits |
| String ≤512 decoded UTF-8 bytes | Инкрементально, до сохранения следующего character; field limits обычно 15/32/64 bytes |
| Registered flag arrays ≤64 | Unique exact known literal values; неизвестные flags отвергаются |
| Integer ≤19 digits и signed 64-bit | До int conversion, затем field-specific ranges; bool не является integer |
| Decimal ≤10 whole / ≤6 fractional digits | Exact unsigned fixed-point token; exponent/nonfinite/negative decimal не принимаются |

Только четыре registry paths bridge info_data — hello_timer, tcn_timer,
topology_change_timer, gc_timer — допускают decimal. Временное JSON tree может
содержать typed decimal token в другом месте, но schema отвергает его там.
Нет binary float и int/float/string coercion. `178.16` сохраняется как token
`178.16`, exact millionths `178160000`; `0.00` сохраняет scale. Форматный cap
0..86400 для timer — **provisional bound**, не доказанная единица/operational
норма kernel. Его нельзя использовать как physical threshold.

Все transitions этого profile — **`exact_unchanged`**. Timers, address lifetimes,
FDB state и flags не удаляются. Любое изменение между сравниваемыми complete
snapshots, включая только timer/lifetime или optional presence, даёт refusal.
Никакой допустимый ticking/RA/DHCP/learning transition пока не принят. Такая
строгость может отвергать обычные native изменения; она не заявляет live
практичность. В разных новых envelopes values остаются наблюдениями, не policy.

Scanner ограничивает собственные text/tree allocations; уже выделенные caller
bytes ему не принадлежат. Python object overhead/RSS не равен raw byte cap.
Нет benchmark, live deadline или transport completeness proof. Parsed source
хранит bounded original text; content digest не выдаёт authenticity. Derived
graph digests используют ссылки на sources, без сериализации множества копий
raw JSON в graph digest. Byte/count caps не расширяют v1 2s measurement window.

## 4. Identity, provenance и cross-source joins

`CaptureDescriptor2` связывает namespace key, source/argv/extent, profile/binary
refs, capture UUID, context, approval digest reference, writer epoch, raw hash,
byte count, provenance reference и exit status. Nonzero exit закрывает decoding.
`TopologyCapturePlan2` заранее и независимо закрепляет descriptors, роли,
namespace reference digests, peer witnesses и table mappings. Подмена reference,
namespace, binary/profile, context/approval/epoch или bytes не принимается
вместо pinned capture. Duplicate capture/source identities отвергаются.

Это **offline references**, не signed capture descriptor физического collector.
В нём нет trusted transport-completion receipt, реально открытого netns FD,
OS principal/permission proof или wall/monotonic capture fences. Поле transport
точно фиксирует `offline_supplied_bytes_no_completeness_attestation`.
Caller, который намеренно солжёт обо всём согласованном fixture manifest,
этой pure библиотекой не аттестуется. Точность hash — сохранность supplied bytes.

Records: `TopologyEnvelope2`, `Namespace2`, `Link2`, `Address2`, `BridgePort2`,
`VlanRow2`, `FdbRow2`, `Route2`, `PolicyRule2`, `Attachment2`. Records сохраняют
validated source, ordinal и все known fields. Address/VLAN имеют nested ordinal.
`ResolvedObjectReference2` указывает exact source capture/row и typed
`LinkReference2` либо `RouteTableReference2`; reference не создаётся по догадке.

Проверки joins:

1. Host/runner/target имеют разные exact namespace keys/inodes в одном fixture
   boot/reader session; имя netns не служит identity. Каждый полный namespace
   требует один наблюдённый LOOPBACK и уникальные ifindices/ifnames. Повторение
   index 1 или 2 **в разных namespaces** допустимо.
2. Address dump покрывает exact set ip links, включая rows с пустым addr_info.
   Join проверяет одновременно namespace/ifindex/ifname; duplicate addresses и
   missing rows дают unproven. IPv4/IPv6 family/prefix не смешиваются.
3. Bridge master name разрешается ровно в один bridge того же namespace;
   port index/name и integer ip master association должны совпасть. Набор ports
   равен ip membership, нет missing/duplicate/foreign port. Wrong kind/name/index
   не исправляется переименованием.
4. Veth требует independent **offline** `PeerWitness2`: exact pair namespace /
   ifindex плюс session-scoped NSID references. Оба link_index и link_netnsid
   должны совпасть reciprocal. Missing/wrong witness/index/NSID даёт unproven.
   Bridge string `if6`/`if8` остаётся observed field, не peer proof; из неё не
   конструируются namespace или peer identity.
5. VLAN rows ссылаются на подтверждённый bridge/port; overlapping duplicate
   memberships отвергаются. FDB dev/master должны разрешаться в согласованную
   пару; supplied VLAN должен существовать на dev. MAC/state/flags сохранены.
   Допустимость learned MAC/offload/learning — будущая policy, не V2-03.
6. Routes/RPDB ссылаются на подтверждённые links и independently pinned
   `TableMapping2`. Native alias и numeric ID сохраняются отдельно. Unknown
   table alias не получает default mapping. Route и RPDB encounter order,
   selectors/flags/masks сохранены, equal-priority rows не сортируются.
7. Management NIC, default/provider routes, extra bridge или новый согласованный
   interface остаются видимыми. Их наличие само по себе не является V2-04
   approval или доказательством bypass. Exact comparison с pinned snapshot
   обнаруживает структурное изменение, включая удалённый optional selector.

Missing document, missing mandatory field, empty source и отсутствие object
различаются. Empty `bridge_link` в peer namespace — наблюдённый supplied `[]`;
missing capture не создаёт такой source. Пустой full `link` не подтверждает
полный namespace. Отсутствующий optional field сохраняет `has=false`, не null
и не guessed default. Даже полные равные snapshots не доказывают отсутствия
transient attach/revert, reset/restore или namespace/FD transfer.

## 5. Реальные fixtures и пределы проверки

Исходные artifacts из
[`native/`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native)
не изменены. Проверены hashes из
[`provenance.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/provenance.json)
и exact JSON lines внутри
[`raw_terminal_capture.md`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/raw_terminal_capture.md).

| Artifact | Фактически проверено |
|---|---|
| [`bridge_links_final.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/bridge_links_final.json) | Ordinary bridge link argv; ports 7/9, master tc-br0, link strings if6/if8, flags/mtu/state/priority/cost |
| [`bridge_tc_br0_final.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/bridge_tc_br0_final.json) | Single bridge argv; ifindex 5, exact MAC/options, nf_call_iptables/ip6tables/arptables=0, vlan_protocol, exact gc_timer 178.16 и timers 0.00 |
| Terminal capture | Byte preservation и происхождение JSON-строк; текст не превращён в недостающие structured captures |

Эти sources вместе дают `topology_unproven`: source coverage missing, partial
capture, bridge membership unproven. Нет полных ip port/peer/addresses/route/
RPDB/VLAN/FDB documents и независимых peer namespace witnesses. Новые registry
paths, отсутствующие даже в этих fragments, явно ссылаются на provisional
specification, а не на якобы наблюдённый native field.

Ни synthetic host, ни table mappings/peer witnesses не восстановлены из этих
данных. Пять cumulative nft pairs не используются для topology measurement,
before/after или packet evidence. `nf_call_iptables=0` одного bridge не
подменяет host sysctl/hook inventory. Старые четыре namespaces и management
routes из terminal text не скрываются и не выдаются за принятый full profile.

## 6. Tests и локальная регрессия

Новые **96 tests** проверяют все четыре стадии, complete synthetic positive,
exact native fragments, bounds/encoding/duplicate keys/types/decimal paths,
registry pinning, missing/partial sources, namespace/provenance substitution,
неоднозначные links/master/addresses, peer/NSID faults, VLAN/FDB consistency,
route/table links, IPv6, selectors и row order, extra NIC/bridge, optional presence,
volatile refusal, constructor integrity и immutable false physical flags.
Отдельно проверен отказ existing `PhysicalProbeGate` с точным
`physical_network_boundary_not_accepted`. AST/fresh import checks запрещают
production I/O imports и socket/Popen/system при import; локальный Python
subprocess теста не является physical subprocess или collector.

Mutation tests используют valid baseline своей стадии. Extra согласованный
link или gateway change может остаться structurally complete, но сохраняется
в graph, не получает policy approval и отказывает при exact snapshot compare.
Реальные partial fixtures используются для format-positive / completeness-negative,
не для synthetic полного positive. Нет skips или expected failures вместо
недостающих kernel доказательств.

Первый новый run: 86 tests, две ошибки test setup (повторный capture UUID и
ожидание ValueError вместо TypeError для init=False override). Guards не
ослаблялись. Затем 94 tests прошли отдельно. Финальный review добавил ещё две
проверки empty-link/loopback и удалённого optional selector; полный прогон ниже
выполнен на окончательном коде.

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
| Network: прежние 334 + новые 96 | 430 | 0 | 0 | 0 | OK, 48.912s |
| Physical | 90 | 0 | 0 | 0 | OK, 10.451s |
| Live | 48 | 0 | 0 | 0 | OK, 10.502s |
| Runtime | 66 | 0 | 0 | 0 | OK, 9.317s |
| Shadow | 56 | 0 | 0 | 0 | OK, 2.348s |
| PoC | 166 | 0 | 0 | 0 | OK, 10.795s |
| **Всего** | **856** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0, без ResourceWarning. Новых tests —
**96**, прежних — **760**; в Network теперь **430** tests.

Все процессы — offline/mocks, отдельные suites выполнялись независимо/частично
параллельно. Durations не benchmark. Это полный Trusted Checker run, не всех
Django приложений; application source/writers не менялись, Django regressions
не запускались. Логи `/tmp/task201b8d-{network,physical,live,runtime,shadow,poc}.log`.

## 7. Целостность и source digest

SHA-256 всех **171 baseline artifacts** шести Trusted Checker packages без
caches и прежних `TRUSTED_CHECKER*.md` сохранены в
`/tmp/task201b8d-baseline.json`; все совпали после реализации. Включены v1,
V2-01/V2-02, native originals, designs/reports, прежние tests/gates/live adapter.
Ни один прежний файл не изменён. Добавлены три production modules, два test
files и этот отчёт. Проверены syntax/AST, whitespace и local Markdown links.
Рабочие БД, .env, credentials и Docker sockets не читались.

Новые network modules автоматически включаются existing physical source manifest:

- до: `ec6acc10217d87fe68fffc396d86fd10ecdd2de77531ff9b54955d8c33f534a8`;
- после: `cbf42c264a4b6fff7943730a4c31e746e2f41f1e9a6a1948d79a03b45b1858ad`.

Старые approvals не обновлялись/не переподписывались и автоматически не
переносятся. Hash references новых fixture plans не являются runtime approvals.

## 8. Неустранённые unknowns

1. Нет native full host/runner/target capture set на exact iproute2 builds.
   Provisional required fields/flags/options могут отличаться от реальной
   serialization; несовместимость даёт отказ до reviewed versioned расширения.
2. Namespace/NSID/table mapping references здесь explicit offline inputs,
   без OS attestation, actual namespace FDs или authenticated reader. Формат
   descriptor не реализует trusted collector transport/timing/freshness fences.
3. Tc/XDP/flowtables/nft hooks/offloads/sysctl/external FDs представлены только
   `Attachment2(status=unobserved)`. Нет adapter для этих surfaces и вывода,
   что они пусты. Full security topology acceptance закрыт.
4. Timers/lifetimes/FDB transitions допускают только exact unchanged. Нет
   принятой RA/DHCP/dynamic learning semantics; cap — форматный, не live policy.
5. Нет management-host policy, permissions/exclusive writers, durable fencing,
   installation ownership/rollback или replay/kill integration. Root остаётся
   TCB; snapshots не дают continuous attestation.
6. Нет CT/raw/byte proof, kernel canonical round trip, packet collector и 15
   controlled measurements. Успех topology-only ничего из этого не заменяет.

## 9. Зависимости V2-04 и итог

Для offline V2-04 теперь есть immutable graph с source coverage, namespace-scoped
links, explicit resolved references, сохранёнными management routes и selectors.
Нужен отдельно reviewed exact host policy manifest: допустимые NIC/bridges/ports,
addresses/routes/RPDB и все presence/volatile transition constraints. Необходимо
отдельно закрыть unsupported source schemas/attachments и полный native capture
registry, peer/namespace/OS permissions и management separation proof. Простое
`topology_complete` или отсутствие default route в runner не заменяет policy.

Дальнейшие physical collector, ownership witness/journal, installer/rollback,
calibration и experiments — отдельные задачи и разрешения из
[design V2](TRUSTED_CHECKER_NATIVE_COMPATIBILITY_V2_DESIGN.md). Этот adapter
не подключён к этим boundaries и не выдаёт conversion в live permit.

**`V2-03 OFFLINE READY`** в описанных provisional/structural границах. Physical
acceptance остаётся `NOT READY`, isolation не доказана. Все physical gates
закрыты, `physical_probe_permitted=false`, `continuous_attestation=false`,
`trace_delivery_complete=unproven`.
