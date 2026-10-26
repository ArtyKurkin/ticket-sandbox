# Trusted Checker: Kernel Evidence Compatibility Audit — №20.1b-7b

20 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**Итог: `NOT READY`.** Текущий offline contract нельзя считать совместимым с
native readback Linux 6.8 / nftables 1.0.9 по имеющимся данным. Полученные native
final snapshots выявили расхождения metadata, ct expression и handle identity;
лабораторный рецепт отличается от канонического. Before/after отдельного
контролируемого прогона и packet artifacts отсутствуют. Это не обнаруженный
обход firewall: ограничения закрывают проверку в fail-closed. Ни manual HTTP
200, ни успешные offline tests не принимают physical boundary.

Выполнены только локальные чтение кода, fixtures, tests и документация.
SSH/VDS, Docker, nft/ip/bridge, setns и реальные packet operations не запускались.
Production-файлы, live flags, `physical_network_boundary_not_accepted`,
`PhysicalProbeGate`, application writers и учебные данные не менялись.
Commit/push/rebase/deploy не выполнялись.

## 1. Основание и происхождение данных

В задании сообщён ручной опыт на переустановленной отдельной VDS:
Ubuntu 24.04.5 LTS, `6.8.0-147-generic`, nftables `1.0.9`, JSON schema version `1`;
bridge `tc-br0`; namespaces `tc-br-runner` / `tc-br-target` с
`10.201.1.2` / `10.201.1.3`; ports `tc-br-r-host` / `tc-br-t-host`.
Сообщены HTTP 200 на TCP 8080, блокировки ICMP/TCP 9090/обратного TCP,
наблюдения NEW/ESTABLISHED и реальные counters.

| Подпись правила из задания | packets | bytes |
|---|---:|---:|
| Forward NEW accept | 1 | 60 |
| Forward ESTABLISHED accept | 5 | 338 |
| Reverse ESTABLISHED accept | 6 | 1931 |
| Forward drop | 6 | 428 |
| Reverse drop | 3 | 176 |

Это **cumulative final values**, сверенные с `tc_strict_lab/forward`, rule
handles **4/5/6/7/8** в оригинальном native dump. Они не являются дельтами и не
сопоставляются с 49 counters канонического рецепта. Source frames и времена
отдельных измерений не представлены.

Пользователь предоставил `trusted_checker_kernel_evidence_20261020.zip`, найденный
в Downloads после запроса originals. Пять файлов скопированы byte-for-byte в
[`native/`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native).
SHA-256 архива:
`2437f0c35a0864885a975b77ce34e3bc072cf37cb41b4ef9d22271ba6aa45a7b`.
[`provenance.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/provenance.json)
фиксирует hashes и размеры каждого файла. Проверено точное совпадение каждой
JSON-строки с оригинальным terminal log, без reserialization/reconstruction.
Это проверка сохранности переданных artifacts, не independent host attestation.

| Оригинальный файл | Команда из terminal log | Что фактически есть |
|---|---|---|
| `nft_ruleset_final.json` | `nft -j -a list ruleset` | 15 objects: metainfo, две bridge tables, две chains, десять rules; final cumulative counters |
| `bridge_links_final.json` | `bridge -j link show` | Два bridge ports, master name `tc-br0`, link strings `if6`/`if8` |
| `bridge_tc_br0_final.json` | `ip -j -d link show tc-br0` | **Только bridge**, ifindex 5, MAC `da:86:66:ca:86:59`; float timers; не полный host/peer inventory |
| `raw_terminal_capture.md` | Сохранённый terminal log | Три исходные JSON-строки, namespaces, human-readable host routes/modules/listener |
| `README.txt` | Пользовательское описание artifacts | Явный запрет считать cumulative snapshots evidence одного canonical прогона |

JSON before/after одного controlled attempt пользователь подтвердил как
отсутствующие. Они не восстанавливались из counters или текста. Сводка задания
сохранена с прежними пятью числами в
[`observations.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/observations.json).
Это собственная summary schema, **не native nft JSON**. Происхождение и пределы
использования artifacts описаны в
[`README.md`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/README.md).

Аудит использует локальный код и предоставленное задание. Внешние manual/source
заново не проверялись. Формы полученных dump установлены непосредственно по
artifacts; round trip именно canonical recipe остаётся непроверенным.

## 2. Карта реализации и границ запуска

| Что проверено | Фактический компонент и поведение |
|---|---|
| Канонический рецепт | [`counter_rules.py`](trusted_checker_network/counter_rules.py): `compile_counter_rules`, `sample_plan`; переиспользует `approved_rules` из [`rules.py`](trusted_checker_network/rules.py), далее `compile_rules` из [`egress.py`](trusted_checker_live/egress.py). Отдельные `tcc1_<full UUID>` tables и recipe digest; только renderer, installer не вызывается |
| Approval и identity | [`counter_contracts.py`](trusted_checker_network/counter_contracts.py): `CounterApproval`, `CounterValue`, `ReadbackFixture`. Exact runtime/binding/context, epoch/generation, полный tuple object handles; counter identity включает context/object index/expression position/purpose. Approval сейчас требует глобально уникальных положительных handles во всём списке объектов |
| JSON readback | [`counter_readback.py`](trusted_checker_network/counter_readback.py): `parse_json` и `validate_readback`. Поставленный JSON до 262144 bytes, запрет duplicate keys/floats/nonfinite; точный список и порядок объектов, handle каждого объекта, полный static digest после обнуления только approved numeric counter fields |
| Before/after и дельты | [`counter_evidence.py`](trusted_checker_network/counter_evidence.py): `_sample` проверяет обе полные readbacks, authenticated packet events, monotonic packets/bytes и exact дельты **всех** counters. `finish` требует 15 samples и equality `previous.after == next.before` |
| Correlation и positive path | [`packets.py`](trusted_checker_network/packets.py): finite `plan`, `unpad`, checksum и `classify_reply`; request/send/ingress/target плюс matching SYN-ACK либо RST-ACK и runner receive. HTTP/body не проверяются |
| Topology | [`counter_inventory.py`](trusted_checker_network/counter_inventory.py): `Paths`, `TopologyObservation`, `expected_paths`, `check_topology`. Полное сравнение supplied typed arrays interfaces/routes/RPDB/attachments и binding. **OS collector здесь отсутствует** |
| Trust/source separation | [`counter_auth.py`](trusted_checker_network/counter_auth.py): exact DTO types, роли с разными keys, domain `tc-nft-counter-probe-v1-offline`. HMAC подтверждает источник fixture, не kernel |
| Noise | Любая дополнительная packet/byte delta, включая ARP/allow/guard/fallback, даёт `counter_delta_unexplained`; tolerance, вычитания фона и проверки «хотя бы один drop» нет |
| Fail-closed | `OfflineCounterVerifier` default OFF; один process-local reservation, wall/monotonic deadline ≤2s, epoch/kill, immutable terminal и circuit при unknown. `counter_reset_or_wrap`, `counter_readback_invalid`, `counter_packet_incomplete`, `counter_topology_unproven` и другие finite reasons; неизвестные exceptions закрываются в `counter_evidence_invalid` |
| Physical I/O | [`io.py`](trusted_checker_physical/io.py), [`inventory.py`](trusted_checker_physical/inventory.py), [`installer.py`](trusted_checker_physical/installer.py) относятся к отдельному dormant v4 boundary. `IndependentNftReadback` и `PhysicalNetworkInstaller` проверяют **v4**, а не новый counter recipe |
| Запуск dormant backend | [`authorization.py`](trusted_checker_physical/authorization.py): enabled, Linux, exact signed `PhysicalApproval`, permission, TTL и issued batch; [`preflight.py`](trusted_checker_physical/preflight.py): build/features/config/host/bridge/offloads/hooks; это prerequisites, не network proof |
| Release gate | [`collector.py`](trusted_checker_physical/collector.py): `PhysicalProbeGate.permit` всегда отказывает с `physical_network_boundary_not_accepted`, даже после начальных проверок report. [`adapter.py`](trusted_checker_live/adapter.py) также сохраняет запрет physical API factory. Counter report всегда `physical_probe_permitted=false`; конверсии в live permit нет |

Существующие mock network installer/collector имеют exact-type guards и не
принимают physical подстановку. `ReviewedActivationPath` не является разрешением
запуска counter recipe. Counter verifier не получает durability, ownership или
cleanup authority из существующих journals автоматически.

## 3. Матрица JSON: декодирование, рецепт и native evidence

«Поддерживается» ниже относится к проверенному локально decoding/contract.
Получен полный final laboratory ruleset; native canonical dump и per-probe
measurement отсутствуют.

| Форма / свойство | JSON decoding | Канонический verifier | Результат аудита |
|---|---|---|---|
| `chain.prio` integer, включая `-200`, `10` | Да, знаковые integers сохраняются без преобразования | Bridge требует `0`, inet `-310`; `-200`/`10` отклоняются | **Parser fix не нужен для типа числа**; изменение priority меняет recipe |
| `prio` строка / bool / float | Строка и bool декодируются; floats отвергаются | Не совпадут с typed canonical integer | Coercion не добавлять |
| `ct state` как `match` с `op: "in"` | Да: в native dump шесть matches с scalar `"new"`/`"established"` | Return rules требуют `op: "=="`, `right: "established"`; native `in` не совпадает по static digest | Подтверждено format mismatch. Round trip canonical equality нужен для решения о versioned normalization |
| `accept` / `drop` отдельными объектами `expr` | Да | Да, когда точны null value, позиция и весь prefix | Соответствует renderer; kernel round trip не выполнен |
| Anonymous `counter` непосредственно перед verdict | Да | Да, только точная approved position, packets/bytes integer `[0,2**63-1]` | Наблюдённые пять numeric pairs допустимы как значения; это не подтверждает их rule identity |
| Rule с counter без terminal verdict | Да | Да: **15 ingress classifiers намеренно non-terminal** | Наличие counter без verdict само по себе не ошибка; добавление verdict к такому rule отвергается |
| Missing/extra/moved/shared/named counter | Может быть корректным JSON | Отказ | Без нормализации к «близкому» rule |
| Реальные table/chain/rule handles | Positive integers читаются | Exact approved handle каждого объекта; глобальные duplicates запрещены | **Подтверждена несовместимая assumption**: chain handle 1 в обеих tables; `tc_strict_lab` table handle 8 и rule handle 8. Нужна scoped identity, не удаление handle checks |
| Top-level `metainfo` / schema version | Native dump успешно декодируется: version `1.0.9`, release `Old Doc Yak #3`, schema integer `1` | `validate_readback` требует exact count/list; metadata не поддерживает | Подтверждён обязательный отказ текущего reader при такой metadata. Нужна ограниченная проверяемая metadata schema в versioned adapter |
| Группировка objects по table/chain | Decoder сохраняет list order; native dump группирует table→chain→rules, затем следующую table | Требуется порядок команд renderer после удаления `add`: сначала tables/chains, затем rules | Формы ordering различаются; exact canonical round trip ещё не проверен. Порядок rules внутри chain нельзя ослаблять |
| Разный порядок ключей JSON / whitespace | Да | Допускается: static `digest` canonicalizes keys | Это единственная уже используемая общая нормализация; list/expr order сохраняется |
| Native dependency insertion, raw payload hex/bit widths, VLAN | Laboratory dump декодируется; raw header expressions canonical recipe в нём отсутствуют | Любое отличие expressions отвергается | Требуется parser/serialize/readback round trip на exact builds. Laboratory `ip protocol == tcp` не подменяет canonical `meta l4proto` |
| nft textual output | Нет, это не JSON | Не принимается | Нет text parser или text→JSON equivalence; dump текста сохранять отдельно |
| `ip -j -d link show tc-br0` | Existing pure `physical.io.json_output` успешно читает, включая `gc_timer: 178.16` | У counter path нет adapter; `Paths` требует complete typed topology | Снимок только bridge, нет host veth/peer links. Поля ip **port** master этим файлом не установлены. Не применять запрет nft floats к ip timers |
| `bridge -j link show` | Existing pure `json_output` читает two-port list | Dedicated consumer отсутствует; existing v4 inventory ждёт другую link schema | Подтверждены master **name**, ifindices 7/9, `link: "if6"/"if8"`, нет `link_index`/`linkinfo`. Нельзя подать этот dump вместо ip links |

У legacy `egress.canonical_readback` другие правила: он пропускает `metainfo` и
удаляет `handle/index/position/use`. Counter reader **не вызывает** его. Такой
legacy результат нельзя выдать за counter readback: потеряются identities.
Existing `NamespaceInventory.observe` читает links/addresses и Docker/proc
identities, но не all-table routes/RPDB и не `bridge -j link`. Он не реализует
новый extended inventory.

## 4. Совместимость рецепта: намеренные различия лаборатории

| Лаборатория из задания | Канонический `nft_counter_probe_v1` |
|---|---|
| `tc_strict_lab`, policy accept и явные запреты для пары interfaces | Две собственные UUID tables в bridge/inet. **Bridge** default drop на prerouting/input/forward/output; **inet** base policy accept с четырьмя exact bridge-related guard drops |
| `tc-br0`, `tc-br-r-host`, `tc-br-t-host`, named namespaces | Binding фиксирует `tcsh0`; ports обязаны соответствовать `veth[a-zA-Z0-9]{1,10}`. Нужны host boot/netns, exact ifindices/peers/MAC, runtime/daemon/container/EndpointID generation; этих данных в сводке нет |
| NEW и ESTABLISHED отдельно в forward направлении | Два TCP request allow rules на prerouting/forward, **без отдельного NEW/ESTABLISHED split**; два return rules с exact established match. Нельзя сопоставить два лабораторных forward counters одному canonical counter |
| HTTP 200 и обычный TCP обмен | Один fixed header SYN; положительный результат — matching SYN-ACK или RST-ACK. HTTP/academic success не следует из этого результата |
| ICMP, TCP 9090, reverse TCP | Существующий план из 15 probes: TCP 8080 positive; 8081/22; other IPv4/host/metadata/DB/Redis/Django; UDP/TCP DNS; IPv6; spoofing, VLAN и extra-attachment destination. ICMP/9090/reverse initiation не заменяют этот finite plan |
| `tc_ct_lab` priority −200: три nonterminal CT counter rules с `3/180`, `15/1014`, `12/3530`; далее `tc_strict_lab` priority 10 | Канонический nonterminal ingress фиксирует конкретный context/header; negative имеет отдельный exact counter+drop. CT observer counter не подтверждает terminal drop |
| Два strict ARP rules разрешают ARP по pair interfaces, без counters | Canonical ARP ограничен sender MAC/IP, peer IP и operation; eight ARP allow counters входят в полный static/delta contract |
| Пять cumulative counters | 49 отдельных rule-local counters: 15 ingress, 14 exact terminal-drop, 12 allow, 4 inet guard, 4 bridge fallback; **58 objects** с table/chain/rule identities. Для каждого sample требуются все before/after values |

Строгий topology profile также описывает только lo, один bridge и veth pair,
connected/local routes, fixed RPDB, отсутствие IPv6 peer address, default route,
host management NIC и attachments. Его нельзя считать снимком обычной VDS.
Даже переименование лабораторных interfaces не обеспечит соответствие profile.
Terminal log дополнительно показывает **четыре** namespaces, включая `tc-target`
и `tc-runner`, host management `eth0`, IPv4 default route, IPv6 default route и
IPv6 link-local routes на bridge/ports. Это прямые расхождения с offline profile;
они не доказывают bypass, но требуют отдельного route/ownership review. Из
`nf_call_*=0` одного bridge нельзя вывести все host sysctl или absence of hooks.
Standalone netns не имеют Docker container/daemon identities: их нельзя
придумывать ради создания `NetworkBinding` или нового «physical» approval.

## 5. Расхождения и критичность

Критичность описывает блокирование доказательства/следующего этапа; это не
обнаруженные уязвимости эксплуатации.

| ID | Уровень | Вывод и необходимое действие |
|---|---|---|
| K1 | Закрыт для final-format audit; measurement gap остаётся | Оригиналы final nft/bridge/bridge-only ip получены и сохранены с hashes. Полного ip host/peer readback, all-table/RPDB и controlled before/after всё ещё нет |
| K2 | Высокий, подтверждён artifacts и tests | Native `metainfo`, table grouping и scalar `ct in` расходятся с новым reader/renderer. Нужен reviewed versioned adapter/contract после canonical round trip; нельзя skip unknown fields |
| K3 | Блокирующий для переноса результата | Policy accept для пары ports, имена/binding и coverage лаборатории отличаются. Исправление parser не превратит эту policy в canonical recipe |
| K4 | Блокирующий | Нет trusted extended OS inventory и совместимого management-host profile. Два supplied snapshots и review fixture не доказывают отсутствие bypass или transient mutation |
| K5 | Высокий, подтверждённая несовместимость identity assumption | Native handles повторяются между tables и object kinds; global uniqueness в `CounterApproval` такой набор отвергает. Нужна versioned scoped identity `(family, table, kind, handle, epoch/generation, position)` с полной validation и запретом collisions внутри scope, без adoption по имени. Raw payload round trip остаётся неизвестным |
| K6 | Блокирующий для measurement | Cumulative значения не дают before/after, correlation или per-probe drops. Нет basis для фактических byte deltas и sequential continuity |
| K7 | Высокий, подтверждённый topology schema gap | `bridge -j link` содержит master name/link string, а existing inventory ждёт ip link_index/linkinfo и integer master. Нужен отдельный bridge adapter и full ip port snapshots; нельзя считать bridge list ip dump или непроверенно приводить имя к индексу. Для ip bridge-only float timers уже читаются `json_output` |
| K8 | Блокирующий для автоматического physical запуска | Counter recipe не подключён к versioned installer/collector/authority; нет нового reviewed ownership/rollback/standalone binding boundary. Существующие физические порты намеренно sealed для другой схемы |

`parse_json` уже поддерживает integer priority, nested match/verdict и указанные
numeric counter values: **исправлений декодера для них не требуется**.
Полученные fixtures показывают необходимые будущие исправления **границы
совместимости**: bounded validated metainfo, scoped handles, корректное
table/chain grouping при сохранении rule order и review `ct in` normalization.
Для topology нужен отдельный reviewed native adapter. Это не разрешение менять
offline v1 contract на месте: native canonical round trip и versioned review
K2/K5/K7 необходимы до implementation. Нельзя приравнять `in`/`==`, убрать все
metadata, сортировать rules, отбрасывать
неизвестные objects или игнорировать handles для получения green result.

Bytes в verifier равны длине **unpadded fixed Ethernet frame**. В существующей
synthetic positive fixture это 54 bytes request; лабораторные `1/60` не задают
тот же packet/hook. Ни «ошибка на 6 bytes», ни L2/L3 accounting, ни padding basis
из этой пары не выводятся. TCP options, padding, VLAN, actual skb accounting,
per-CPU aggregation и неатомарность dump нескольких counters требуют отдельных
измерений. Подгонка допусков под 60/338/1931/428/176 запрещена.

## 6. Локальные изменения и regression tests

Production parser, recipe, contracts и gates **не исправлялись**: имеющиеся
laboratory snapshots определяют расхождения, но не новый approved canonical
normalization/identity contract. Добавлены только:

- этот отчёт;
- summary fixture с точными пятью observed pairs и признаками отсутствующих before/after;
- пять original archive files без изменения bytes, provenance manifest и README;
- [`test_kernel_compatibility.py`](trusted_checker_network/tests/test_kernel_compatibility.py):
  **27 новых tests**, использующих существующий synthetic `CounterLab` и mock
  physical `Lab` без host operations;
- [`test_kernel_native_formats.py`](trusted_checker_network/tests/test_kernel_native_formats.py):
  **16 новых tests** на оригинальных final snapshots. Всего **43 новых tests**.

Новые tests проверяют numeric parsing всех пяти реальных пар в **явно synthetic**
canonical counter; значения не связаны с laboratory rule handles. Подтверждено,
что ненулевая cumulative baseline допустима, если отдельно доказаны все deltas.
Подмена отдельной probe delta любой из пяти cumulative пар закрывается в
`counter_delta_unexplained`; summary/single snapshot не принимаются как measurement.

Дополнительно закреплены integer `-200`/`10` versus approved priorities,
`ct in` versus exact recipe, отдельные verdict elements и nonterminal ingress,
missing rule, перестановка/изменение expressions, priority/policy/interface drift,
metadata/object regrouping, packets/bytes reset, excess drop, ARP background,
traffic между samples, topology bridge drift и невозможность открыть physical
gate даже с offline verified. Mock string-master проверяет текущую границу
inventory; он не объявляется захваченным iproute2 output.

Native tests проверяют byte preservation/exact extraction из terminal log,
полное JSON decoding, реальные priorities/metainfo/ct scalar matches,
пять strict и три CT cumulative pairs, verdict positions, uncounted ARP и
nonterminal CT rules, scoped handle reuse, bridge master/link schema, bridge-only
ip float timers, extra namespaces/default routes, обязательный отказ принять
final dump как canonical readback/measurement, пересадку actual metadata/CT
expression в synthetic canonical readback и отказ raw topology вместо typed
complete observation. Source JSON не нормализован ради green tests.

Доступные **native-format fixture tests выполнены**. Невыполнимой по этим данным
частью остаётся controlled canonical measurement, а не parsing final snapshots.
Ни один skipped/expected-failure test не подменяет недостающее evidence. Green
suite не доказывает physical compatibility и не меняет итог `NOT READY`.

## 7. Полный локальный прогон Trusted Checker

Прогон охватывает все tests шести packages Trusted Checker, включая прежние
counter tests и новую suite. Каждый package запускался отдельным процессом:

```sh
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_network/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_physical/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_live/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_runtime/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_shadow/tests -t .
.venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_poc/tests -t .
```

| Suite | Результат |
|---|---|
| Network: existing 69 + counter 64 + audit 43 | **176 tests, OK**, 30.440s |
| Physical | **90 tests, OK**, 9.216s |
| Live | **48 tests, OK**, 9.732s |
| Runtime | **66 tests, OK**, 8.396s |
| Shadow | **56 tests, OK**, 2.089s |
| PoC | **166 tests, OK**, 9.690s |
| **Всего** | **602 tests, OK**, без skips/ResourceWarning |

Отдельный запуск обеих новых suites: 43 tests, OK, 7.384s. Все шесть полных
suite processes завершились с exit code 0. Их логи не содержат skips,
ResourceWarning, failures или errors.

Это полный прогон **Trusted Checker**, не всех Django приложений проекта.
Django regressions не запускались; application source/writers не менялись.
Все проверки выполняются offline/mocks; реальные Linux/nft/Docker tests не
заявляются. Логи: `/tmp/task201b7b-{network,physical,live,runtime,shadow,poc}.log`.
Параллельные durations не являются performance measurements.

SHA-256 всех **150 существовавших до аудита artifacts** в шести packages
(без caches) и прежних `TRUSTED_CHECKER*.md` совпали с локальным manifest
`/tmp/task201b7b-baseline.json`. Ни один прежний файл не изменён.
Production source digest из `trusted_checker_physical.artifacts.source_digest()`
до/после: `497c06dc4901e5a4b871ac4f28c3d7de92e087a20a7ded46ab6d5862e59cc2cc`.
Новые файлы находятся в tests и документации и не меняют этот production manifest.

## 8. Отсутствующие доказательства

1. Native **canonical** JSON round trip и normalization raw expressions; полный
   ip host/peer link/address readback. Laboratory final metadata/CT/handles и
   bridge schemas уже сохранены, повторно их запрашивать не требуется.
2. Round trip **всего канонического рецепта** на exact kernel/nft builds, включая
   bootstrap, raw payload expressions, всех 49 counters и все hooks. Версия
   поддерживаемой kernel series сама по себе не доказывает совместимость.
3. Все 15 fresh context-bound probes, полные before/after, bounded packet
   observations, real deltas packets/bytes, positive reply и continuity gaps.
4. Actual route tables/RPDB IPv4+IPv6, addresses, bridge ports/FDB/VLAN,
   offloads, tc/XDP/flowtable/hooks и все namespace identities; reviewed
   отсутствие пути к SSH/management NIC/host services/alternate routes.
5. Реальные OS permission/writer facts, отдельный reader principal, protected
   binary/config/keys/journals и отсутствие inherited external network FDs.
   `ControlModel` сейчас имеет basis `offline_review_fixture_only`.
6. Durable ownership до первого apply, exact install epoch/generation, journal
   committed transaction outcome при потерянном ответе, безопасный only-owned
   rollback и quarantine. Counter values не дают delete/adoption authority.
7. Reset/replacement faults, background/noise, deadline/kill/read interruption,
   stage timings, loss/truncation и повторяемость результата на approved build.

Два одинаковых snapshots не исключают attach/revert, reset/restore либо
replacement с восстановлением identities между чтениями. Это предел
trusted-writer model; такой fault нельзя объявить обнаруженным, если evidence
его фактически не обнаруживает. NFTRACE completeness не является обязательным
условием counter experiment и не заменяет эти доказательства.

## 9. Следующий физический эксперимент: `tc-counter-kernel-compat-v1`

**Draft protocol v1, не выполнен, не является разрешением запуска.** Цель —
измерить canonical recipe/serialization/path/accounting на exact отдельно
одобренной dedicated VM. Результат — experimental compatibility report, без
live release и учебных эффектов. Final-format часть K1 закрыта; сначала провести
review K2/K4/K5/K7/K8 и получить недостающие полные topology artifacts;
при изменении schema/profile создать новую версию protocol и artifacts.

### 9.1. Manifest и отдельное разрешение

Зафиксировать approval для exact fresh host/boot/kernel/nft/iproute2 builds,
source digests, roles, topology profile, names/tuples, commands, caps/deadlines,
mutations, fault cases и rollback. Не использовать старые orphans и не переносить
старые approvals автоматически. Проверить package/binary/kernel configuration и
loaded features read-only; никакого automatic modprobe/sysctl/offload fix.

Полученные **сохранённые** artifacts уже проверены локально, без SSH. Reviewed
offline adapter должен впоследствии принимать approved native canonical fixtures
и отвергать mutations. Native parser test/full measurement — разные этапы.
Если native output отличается от schema, остановиться и принять versioned
изменение на основании artifacts до следующего measurement.

Standalone namespaces допускаются только с separately reviewed lab identity/
ownership profile: нельзя подделывать Docker IDs или выдавать synthetic binding
за real runtime. Этот аудит такой профиль/collector не реализует. Live Docker
Runner и настоящие Sandbox attempts в опыте не использовать.

### 9.2. Исходная topology и сохранение SSH

1. До mutations получить host/namespace identities, links/addresses и reciprocal
   veth peers, bridge ports/FDB/VLAN state, **все** route tables и RPDB для IPv4
   и IPv6 во всех namespaces. Снять все nft hook/priority objects, tc/XDP,
   flowtables, forwarding/br_netfilter, offloads и доступные external FDs.
2. Зафиксировать SSH management interface/IP/route и out-of-band console либо
   provider recovery. Management NIC не включать в test bridge и не переносить
   между namespaces. Не добавлять management accept в canonical test tables
   ради совместимости: это изменит recipe.
3. Bridge default-drop hooks потенциально затрагивают другие bridges. При любом
   foreign bridge/неясном management path — STOP до apply. Отдельный reviewed
   management-host inventory profile должен доказать отсутствие пути из runner
   к management NIC; не скрывать её из dump ради strict fixture layout.
4. Создавать только новые зарегистрированные namespaces/veth/bridge. Принадлежность
   определяется durable creation record, exact netns inode, ifindex/peer/MAC и
   generation, не именем или адресом. Связать stage artifacts с manifest.

Для **отдельно разрешённого read-only capture** следующий список задаёт точные
выводы, которых не хватает. Команды здесь только специфицированы, не выполнены.
`APPROVED_NETNS` означает по очереди exact reviewed runner/target namespace;
не подставлять автоматически старые namespaces из terminal log.

```sh
uname -r
nft --version
ip -Version
bridge -Version
nft -j -a list ruleset
ip -j -d link show
ip -j address show
bridge -j -d link show
bridge -j vlan show
bridge -j fdb show
ip -j -4 route show table all
ip -j -6 route show table all
ip -j -4 rule show
ip -j -6 rule show
ip netns list
ip netns exec APPROVED_NETNS ip -j -d link show
ip netns exec APPROVED_NETNS ip -j address show
ip netns exec APPROVED_NETNS ip -j -4 route show table all
ip netns exec APPROVED_NETNS ip -j -6 route show table all
ip netns exec APPROVED_NETNS ip -j -4 rule show
ip netns exec APPROVED_NETNS ip -j -6 rule show
```

Перед запуском зафиксировать exact binary paths/build hashes, kernel config,
boot/netns identities и privileges читателя в manifest. Отдельно получить tc
ingress/egress, XDP/flowtable/offloads/FD facts для **всех approved interfaces**;
список выше сам по себе не полный bypass inventory. Отсутствующая поддержка
JSON/options в approved build означает сохранить exit status/error и unknown,
не исправлять host и не заменять данные reconstruction.

Артефакты сохранить в `preflight/{host,runner,target}/` с exact stdout bytes,
command argv, exit status, UTC/monotonic start/end и SHA-256 каждого файла.
Не объединять вывод разных команд в псевдо-JSON. Human-readable `nft -a list
ruleset` при необходимости сохранить отдельно только для анализа normalization.
Для sample `00..14` каталог должен содержать `before.nft.json`, `events`,
`after.nft.json`, timing/epoch/approval refs; topology до/после хранить отдельно.
Обе nft snapshots собираются **тем же argv** `nft -j -a list ruleset` вокруг
одной exact fixed probe reviewed helper. Пока helper/ownership/profile не
приняты, разрешён только отдельно approved read-only preflight, не этот send.
Missing snapshot не восполнять previous totals или dump текста.

### 9.3. Bootstrap, parser round trip и rollback

1. Перед первой mutation зарегистрировать новый install intent и ownership
   transaction с exclusive create semantics; collisions означают STOP, не adopt.
   Подготовить trusted rollback controller вне test namespaces и заранее
   проверенный out-of-band recovery. Controller сериализуется с installer.
2. Под отдельным approval проверить native parse/check канонического JSON и
   serialized readback на test topology. Снять полный dump, metainfo, handles,
   ordering и normalization. Любой mismatch — STOP/unknown/new review, без
   удаления неизвестных полей и без изменения canonical allow paths.
3. Установить drop-only bootstrap, проверить exact handles/readback, затем
   approved active recipe одной reviewed transaction. Подтвердить ownership
   каждой generation до новых операций. Native dump не означает adoption.
4. Потерянный apply response закрывает measurement и circuit; не повторять
   apply наугад. Только reviewed committed-transaction witness устанавливает
   исход; без него quarantine. При подтверждённом ownership rollback восстанавливает
   approved bootstrap/удаляет только созданные ресурсы по exact identity.
   Не выполнять generic flush/prune/reset и не откатывать чужой host ruleset.
5. По окончании/abort сравнить management path и host baseline, учесть все owned
   resources. Если identity потеряна или cleanup outcome неизвестен — quarantine
   и operator recovery по отдельной процедуре, не broad cleanup.

### 9.4. Измерение fixed probes и byte basis

ARP priming и настройку controlled listener выполнить **до** baseline; дождаться
проверяемой quiescence. Снять несколько no-send baselines для оценки фона.
Ненулевой фон не вычитать и не считать успешным deny; выделить отдельный noise
diagnostic run. Не менять counters/reset для получения удобного нуля.

Для каждого из 15 samples собрать independently read full before → exact
send/host ingress → для positive target ingress/response/runner receive → full
after. У каждого чтения собственные start/end, UTC/monotonic fence, context,
approval, epoch/generation, topology refs и full numeric rows. Сохранить raw
artifacts защищённо; operator report — bounded/redacted. Проверить отсутствие
изменений между final предыдущего sample и baseline следующего.

Positive SYN требует matching SYN-ACK либо RST-ACK с checksum/ACK/flow/MAC/IP;
HTTP 200 можно измерить отдельно, но его full TCP flow даст дополнительные
counters и не включается в fixed SYN window. При остановленном listener ожидаем
`path_open_rst`, без утверждения application success.

Для каждого negative нужны ровно один ingress и свой terminal-drop increment;
остальные counters нулевой delta. Timeout без этих increments — unknown.
Сверить full static readback до/после, counter position и exact handles.

Отдельно измерить на **каждом задействованном hook** frames с/без padding,
TCP options, IPv4/IPv6 и VLAN, request/reply sizes, ARP/retransmits и counters
read consistency. Сопоставить реальные packet captures с packet/byte deltas.
Если byte basis отличается от `offline_frame_bytes`, текущий verifier не может
дать accepted physical результат: оформить mismatch и versioned contract review,
не вводить tolerance ради pass. Измерить stage caps и end-to-end; превышение
offline 2s не компенсировать незаявленным расширением budget.

### 9.5. Дополнительные пути и faults

В отдельных заранее одобренных diagnostic windows проверить IPv4 other ports/
destinations, ICMP, TCP 9090, reverse TCP initiation, host→peer и peer→host,
runner↔target, gateway/metadata/служебные адреса и отсутствие external egress;
IPv6 link-local/multicast/ND, tagged VLAN/spoofed identities и alternative
interfaces/routes/RPDB. ARP пары проверять как отдельное bounded разрешение;
ARP к чужой паре/broadcast и неожиданные peer addresses не считать разрешёнными.
Эти diagnostics не расширяют существующий finite plan молча: сохранить
отдельные case IDs/expected outcomes и не выдавать их за `SampleResult` v1.

Отсутствие обхода подтверждать route/policy/hook/attachment/FD inventory и
approved writer control совместно с пробами. Finite probes сами не доказывают
универсальный deny. Новый extra interface/route, flowtable, tc/XDP, tunnel,
macvlan либо inherited socket закрывает review epoch до нового approval.

Fault windows: missing/duplicate send, background/ARP/retransmit, decrease/reset,
rule/counter replacement, extra route/interface, reader interruption, kill,
wall rollback и monotonic deadline. Не делать faults на management path.
Зафиксировать, что каждый измеримый fault даёт unknown/fail, а transient
restore между snapshots может остаться ненаблюдаемым. Root остаётся TCB.

### 9.6. Точные terminal criteria

| Итог experiment report | Критерий |
|---|---|
| `PASS` | Reviewed native schema/identity/topology profile принят; полный canonical round trip точен; все 15 fresh samples имеют required packet events, approved byte accounting и exact deltas **всех** counters; continuity/deadlines/writer controls соблюдены; дополнительные diagnostics соответствуют manifest; rollback/ownership и management path подтверждены |
| `FAIL` | Получено положительное доказательство несовместимости/нарушения: canonical JSON не принимается parser, native static structure отличается, запрещённая доставка или bypass подтверждены, management затронут либо отдельно заданный diagnostic нарушен. Зафиксировать artifact и остановиться |
| `UNKNOWN` | Нет полного/достоверного readback или packet observation, только timeout/cumulative totals, шум/unexplained delta, reset/replacement, identity/control drift, interruption/kill/deadline, неясный apply/rollback либо неизвестная byte basis. Не повторять автоматически и не выпускать permit |

Это vocabulary **внешнего experiment report**. Текущий verifier по-прежнему
имеет только `verified/offline_counter_model_verified` или `unknown`; явный
native mismatch не добавляет ему новый result `FAIL`. Даже experiment `PASS`
не открывает `PhysicalProbeGate`: затем нужны отдельные security review,
versioned collector/installer/authority composition, durable replay/kill
integration, approval live timing/artifacts и отдельное разрешение активации.

## 10. Решение

**`NOT READY`** для запуска канонического counter verification по текущему
contract на VDS: native final fixtures получены и format tests выполнены, но
подтверждены metadata/CT/identity несовместимости; нет canonical round trip,
controlled before/after, real extended inventory/management profile и reviewed
execution/rollback boundary. Локальная регрессионная база и draft protocol
подготовлены. Нужны versioned compatibility review и отдельный сбор недостающих
artifacts по сценарию выше, затем exact physical-test approval. Этот отчёт сам
по себе такого разрешения не даёт; live activation и production sign-off
отсутствуют.
