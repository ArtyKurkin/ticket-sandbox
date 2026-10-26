# Trusted Checker: Native Kernel Fixtures & Compatibility Regression — №20.1b-8f

21 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-05 OFFLINE READY`.** Новый реальный capture сохранён byte-for-byte,
проверены внутренние checksums, exit/stderr records и JSON. Отдельный static
native topology profile **diagnostic revision 2** читает все 33 topology JSON,
сохраняя каждый observed field и optional presence. Прежние V2-03/V2-04,
v1/physical contracts и security policy не изменены.

Готовность относится к fixtures, **format decoding и offline regression**.
Новый profile не принят для semantic topology/profile acceptance. Его output
всегда `topology_unproven`; `management_policy_verified=false`,
`isolation_verified=false`, `physical_probe_permitted=false`, ownership unproven.
Лаборатория не является canonical positive: её отличия остаются видимыми.
Shadow-only, `PhysicalProbeGate` и `physical_network_boundary_not_accepted`
сохранены; physical audit остаётся `NOT READY`.

Выполнены только локальное чтение архива/кода, pure Python, unittest и документация.
SSH/VDS, ip/bridge/nft/Docker/setns/packet operations, host/network mutations,
physical collector/installer/authority, academic writes и deploy не выполнялись.
Commit/push/rebase не выполнялись.

## 1. Provenance и состав capture

Архив найден по точному имени в Downloads. Его оригинальные bytes сохранены в
[`tc-native-capture-20261021T082517Z.tar.gz`](trusted_checker_network/tests/fixtures/native_capture_20261021/tc-native-capture-20261021T082517Z.tar.gz).

| Проверка | Результат |
|---|---|
| Archive bytes | **8080** |
| Archive SHA-256 | `b641f7f27eeac55c72651ab6f76effff034135d01cc35226d19c49a35283e0b5` |
| Original files | **108**, суммарно **45139 bytes**, включая SHA256SUMS |
| Embedded SHA256SUMS | **107 unique entries**, все совпали; покрыт каждый другой original file |
| JSON | **34**: 33 topology documents + один host nft ruleset; strict decoding успешно |
| Saved command records | **34 `.exit`**, каждый exact `0\n`; **34 `.err`**, каждый empty |
| Version/inventory text | kernel.txt, nft-version.txt, iproute2.txt, bridge-version.txt, namespaces.txt |

Tar member paths проверены на traversal/absolute/duplicate names и неизвестные
kinds; original files/dirs без links. Все 108 files записаны под
[`native/tc-native-capture-20261021T082517Z/`](trusted_checker_network/tests/fixtures/native_capture_20261021/native/tc-native-capture-20261021T082517Z)
с точным совпадением bytes каждого tar member. Проверка integrity не является
подписью trusted OS reader или независимой host attestation.

Generated artifacts отделены от originals:

- [`provenance.json`](trusted_checker_network/tests/fixtures/native_capture_20261021/provenance.json): archive/file hashes, sizes и missing proof markers;
- [`source_mapping.json`](trusted_checker_network/tests/fixtures/native_capture_20261021/source_mapping.json): source/path/hash/exit/stderr mapping;
- [`observed_matrix.json`](trusted_checker_network/tests/fixtures/native_capture_20261021/observed_matrix.json): exact paths/types/counts/literals, cardinalities, parent/present/absent counts и per-document old decoder outcomes;
- [`FIELD_MATRIX.md`](trusted_checker_network/tests/fixtures/native_capture_20261021/FIELD_MATRIX.md): полная readable матрица **200 field paths** против old/new registries;
- [`README.md`](trusted_checker_network/tests/fixtures/native_capture_20261021/README.md): происхождение и границы использования.

Saved text сообщает Linux `6.8.0-147-generic`, nftables `1.0.9`, iproute2/bridge
`6.1.0` (ip text также libbpf 1.3.0). Это version-output observations, не hashes
самих binaries, approved kernel build/config или authenticated provenance.

**Exact execution argv отсутствует.** В archive нет collection script/argv log,
per-command UTC/monotonic timestamps, transport-completion receipts, OS principals,
boot/inode/FD witnesses или measurement before/after. Mapping использует filename
и source taxonomy; отдельно указан **nominal future source-plan argv**, exact
execution argv и namespace wrapper остаются null/unrecorded. Никакой command не
восстановлен по JSON «как будто выполненный». Archive filename/tar metadata не
превращены в capture intervals. Один запуск скрипта не является atomic snapshot.

## 2. Exact native schema compatibility matrix

Все document/field cardinalities ниже — наблюдения этого corpus, не универсальные
kernel bounds. Полные 200 paths, actual scalar types/values и presence counts
находятся в FIELD_MATRIX/observed_matrix. Unknown fields не отбрасываются.

| Source | Docs / rows | Observed формы | Старая provisional schema |
|---|---:|---|---|
| link | 5 / 13 | Common detailed link fields; min/max MTU могут быть integer 0 на lo; optional altnames, parentbus/parentdev, link_index/link_netnsid; **string master**; bridge info_data и veth info_slave_kind/info_slave_data | Четыре peer documents читаются; host отказ из-за дополнительных fields/string-master/slave shape |
| address | 5 / 13, addr_info 23 | Полные link header attributes; optional altnames/peer/master; per-address dynamic/noprefixroute **bool**, metric integer, numeric lifetimes | Все пять отвергаются: old address schema не описывает full header/new booleans |
| bridge_link | 1 / 2 | Master name/link string; **13 boolean options**, mcast_router integer; exact state/flags/mtu/priority/cost | Old on/off strings и отсутствие mcast_router несовместимы |
| bridge_vlan | 1 / 3 | vlan integer, flags strings `PVID`, **`Egress Untagged`** | Old literal `Egress_Untagged` не совпадает; alias не вводится |
| bridge_fdb | 1 / 23 | **ifname**, scalar state `permanent`, flags self либо []; master optional, vlan optional | Old dev/mandatory master/list state несовместимы |
| route4 | 5 / 35 | dst/dev/protocol/prefsrc/flags; gateway 3 rows, metric 6; table/type отсутствуют в 10 rows, scope отсутствует в 3 | Все пять отвергаются: required fields отсутствуют; host literals без `/32` не совпадают с old prefix-only form |
| route6 | 5 / 30 | dst/dev/protocol/metric/flags/pref; table/type отсутствуют в 9 rows; **scope отсутствует во всех 30**; RA expires + metrics в одной row | Все пять отвергаются: required table/type/scope и unknown expires/metrics/multicast form |
| rule4 | 5 / 15 | priority integer, src `all`, table local/main/default | Все пять проходят format schema; это не подтверждает policy/alias semantics |
| rule6 | 5 / 10 | priority integer, src `all`, table local/main | Все пять проходят format schema |

Итого old registry допускает **14/33** topology documents как формат и
отвергает **19/33**: 10 `field_missing`, 8 `unknown_field`, 1 `field_invalid`.
Он не объявляется «полностью сломанным» и не исправлен на месте.

Подтверждённые специальные формы:

- Host NIC содержит `altnames=[enp0s3,ens3]`, parentbus=virtio, parentdev=virtio0.
  Host veth master=tc-br0 — string; link_index/link_netnsid integers.
- Bridge info_data содержит **45 fields**, включая четыре exact decimal timers.
  `gc_timer` сохранён **`293.28`**, остальные zero tokens **`0.00`**.
  Slave info_data содержит **32 fields**, три дополнительных decimal timers,
  bool options, string id/no/group masks, bridge/root IDs и integer fields.
- FDB: **17 self rows** без master, **6 master rows**, из них **3 VLAN rows**.
  Все 23 state — scalar permanent. Self+master/VLAN сочетания, не наблюдённые
  в corpus, не объявлены универсально поддержанными.
- RA route: integer `expires=1726`, `metrics=[{"hoplimit":64}]` — array ровно
  из одного object. Values, nesting, field presence и source order сохранены.
  Units/expiry transitions не предполагаются.
- Host IP literal destination без prefix (`192.0.2.10`, `::1` и другие)
  остаётся literal, без вставки `/32` или `/128`. Missing table/type/scope
  остаётся missing; default main/unicast/global не добавляются.

## 3. Отдельный static profile/registry revision 2

Добавлены pure modules:

| Файл | Назначение |
|---|---|
| [`native_v2_native61_schema.py`](trusted_checker_network/native_v2_native61_schema.py) | Static 200-path registry, exact scalar/array/branch rules и immutable profile |
| [`native_v2_native61.py`](trusted_checker_network/native_v2_native61.py) | Unattested artifact references, bounded decoding, observational joins/candidates и limited diagnostic policy findings |

Profile ID: **`iproute2-6.1.0-native-topology-v2-diagnostic-2`**, integer schema
revision **2**. Contract остаётся отдельным offline v2, без migration v1/v3/v4.
Acceptance точно `diagnostic_format_only_semantics_unreviewed`. Build references
явные; в native tests это hashes version-output artifacts, **не binary hashes**.

- Field/constraints/literal-pools registry digest:
  `21cc928e1ecb944a0b528b585cc9503c4c18ac24c736ad9d4f50de7d8503b78e`.
- Nominal source-plan/bounds digest:
  `0e70cbdbce38e027a3172ca4f0bb05636504f84c0ae2aa1a7a54c9efc27207de`.

Registry и literal/type-bound pools — immutable tuples/frozen records. Они
заданы в source **до** decoding input, не читаются из matrix/fixtures/runtime
JSON и не расширяются автоматически. Matrix отражает review, но не управляет
production allowlist. Каждый field имеет source/path/type/requiredness,
disposition/evidence reference/transition; route/RPDB — ordered_policy,
expires/lifetimes/timers — observed_volatile. Все transitions exact unchanged с
явно unreviewed meaning. Flags/boolean/numeric types не приводятся друг к другу.

Новый decoder переиспользует unchanged bounded topology scanner: exact bytes,
≤1 MiB/document, ≤16 MiB batch, ≤256 documents, depth≤32, nodes≤65536/document,
arrays/rows≤1024, string≤512 UTF-8 bytes; field-specific scalar/flag limits
строже. Batch caps проверяются до первого parse. Duplicate keys/BOM/bad UTF-8,
NaN/Infinity/exponents, unknown fields/kinds/literals и malformed/null types
дают finite `ContractViolation2`. Decimal остаётся ExactDecimal2 только в
**семи** registered timer paths; int/float/string coercion отсутствует.

Exact native field names сохраняются: нет ifname→dev alias, string master→index
coercion, state string→list conversion, `Egress Untagged`→underscore alias,
удаления protocol dependencies/IPv6/FDB или заполнения route defaults.
New profile поддерживает только observed key/type/literal forms в заявленных
bounds. Well-typed diagnostic variations не получают semantic equivalence или
native policy acceptance.

DTO constructors повторно связывают rows с original text/hash, отдельно
проверяя типы supplied frozen values: Python `True == 1` не обходит integer
checks. Raw text/hash — внутренний artifact, не bounded operator export.
Source descriptor фиксирует argv/timing как **unrecorded**, namespace identity/
principal как **unobserved**; caller не может пометить их проверенными.

Прежние `TopologyProfile2`, `TopologyEnvelope2`, `ManagementHostProfile2` и
`validate_management_profile2` exact types не принимают новые diagnostic DTO.
Conversion/adoption API отсутствует. Для future semantic acceptance потребуется
отдельный reviewed composition, а не переименование этого результата.

## 4. Cross-source checks и границы joins

`NativeSourceReference61` использует **capture scope label**, source/path/hash
и archive reference. Это не NamespaceKey, netns inode, FD или role binding.
`NativeDiagnosticBundle61` сохраняет все пять declared scopes и все 33 sources.
Local duplicate ifindex/ifname, conflicting refs/options, missing membership,
неизвестные route/FDB/VLAN links отмечаются finite uncertainty reasons.

На реальном corpus получено **112 observational local joins**:

- address ifindex/ifname и общие header fields согласованы с supplied link rows;
- host ports 7/9 ссылаются по master name на observed bridge 5 tc-br0;
- bridge options, flags/MTU и общие slave/bridge fields согласованы без
  speculative alias между multicast_router и mcast_router;
- VLAN rows ссылаются на observed bridge/ports, FDB dev-role определяется через
  **ifname**, master/VLAN refs проверяются только при наличии;
- routes dev ссылается на observed interface; RPDB source order/priority/table
  tokens сохраняются. Numeric table mapping не выдумывается.

В FDB **шесть eth0 self entries** сохранены и отдельно классифицированы как
`non_bridge_interface_self_entry`. Они не удалены как «noise», не приписаны
владению bridge и не автоматически разрешены policy. Остальные self/master
entries также сохранены со своими flags/master/VLAN presence.

Найдены **три reciprocal-index candidates**: 6↔7, 8↔9 и старый pair 3↔4 между
tc-runner/tc-target. Это **не trusted namespace joins**. Integer NSID относится
к namespace/capture session; одинаковые числа в разных scopes не объединяются.
Все candidates имеют `unproven_no_namespace_fd_nsid_witness`. При нескольких
совпадениях индексов сохраняется ambiguity; «наиболее подходящий» peer не
выбирается. Из `namespaces.txt (id:N)` trusted FD mapping не строится.

Global topology acceptance заблокирован даже при согласованных local joins:
actual FD/inode/boot/session/NSID witnesses отсутствуют, table/default semantics
не приняты, OS surfaces не наблюдены, captures не атомарны и не имеют trusted
intervals/transport completion. Presence-aware format decode не доказывает
absence of bypass, transient mutation или writer control.

## 5. Positive format и negative policy cases

Real sources успешно проходят **format-positive** новую schema. Отдельный
`NativePolicyReview61` сравнивает только доказуемые несовместимости с независимо
заданным V2-04 policy и внешним digest pin. Это limited diagnostic review,
**не полный V2-04 validator для нового native profile**. Если findings нет,
результат всё равно `profile_unproven`, не structural/native acceptance.

В реальных saved artifacts остаются:

- Host eth0/default/provider routes, другие addresses и FDB rows — видимые
  observed entries, без wildcard разрешения «любых provider routes».
- Bridge **tc-br0**, тогда как canonical policy требует tcsh0; host port names
  также отличаются. Ни один interface не переименован для matching.
- Четыре named namespace captures вместо двух peers; tc-runner/tc-target не
  удалены и не скрыты. Это declared capture scopes, не полный OS namespace
  inventory и не доказанные role identities.
- IPv6 link-local addresses/routes на host test bridge/ports и peer veths;
  diagnostic policy findings `test_side_ipv6_forbidden` и
  `test_side_ipv6_route_forbidden` сохраняются.
- Nft JSON содержит tc_ct_lab/tc_strict_lab, две chains с priorities −200/10,
  laboratory policy, не canonical v2 recipe. Existing pure nft decoder читает
  формат; comparison с independent synthetic recipe отвергает его.

Nft format test использует **явный synthetic offline context только как argument
существующего decoder**. Этот context не описывает VDS, не считается capture
namespace identity и не создаёт real FD/ownership witness. Raw nft bytes не
изменены. CT/raw semantics, 49-counter canonical round trip и byte accounting
не приняты; cumulative counters не стали measurements или reconstructed deltas.

Реальный corpus нигде не маркируется canonical positive installation. Авторский
synthetic fixture задаёт format-positive shapes заранее; expected management
policy берётся из отдельного trusted synthetic setup, не из native snapshot.

## 6. Coverage gaps и следующий read-only collector stage

План diagnostics требует девять source kinds на каждый declared scope. Host
имеет все девять, каждый из четырёх named namespaces — только link/address/
route4/route6/rule4/rule6. Поэтому **12 missing sources**: bridge_link,
bridge_vlan, bridge_fdb в каждом из четырёх namespaces. Это не []/none и не
подтверждение отсутствия bridge objects. Для будущего approved source plan
applicability должна быть явно reviewed; здесь пустые captures не выдуманы.

До physical evidence нужны отдельно разрешённые captures/контракты:

1. Exact source plan/argv, namespace execution wrapper и native bridge/VLAN/FDB
   observations внутри каждого применимого namespace. Сохранять raw stdout,
   stderr, exit status и полную coverage, без фильтрации неудобных rows.
2. Actual host boot/netns inode и открытые trusted namespace FD references;
   bracketed session-scoped NSID/reciprocal peer witnesses. Named labels и PID
   без start-generation не заменяют эту границу. Все namespaces/attachments,
   включая unnamed/FD-held, требуют отдельного inventory/ownership review.
3. Absolute binary paths/build/source hashes, reader OS principal/privileges,
   authenticated descriptor/hash binding, per-command wall/monotonic start/end,
   bounded transport/truncation/completion и writer epoch fences.
4. Tc ingress/egress, XDP, nft hooks/flowtables во всех применимых namespaces,
   offloads, forwarding/proxy ARP/ND/bridge-netfilter, capabilities/permissions,
   network writers, protected config/keys/journals, external/inherited FDs.
   Host nft dump не заменяет эти surfaces или peer nft inventories.
5. Reviewed semantics/versioned normalization для missing route fields,
   table aliases, RA expires/metrics/units, FDB/learning и timer transitions.
   До review — diagnostic data/unproven, без kernel defaults по памяти.
6. Отдельные exact controlled before/after, packet artifacts/byte basis,
   freshness/deadline/kill и continuity. Current archive не содержит измерений;
   его filename/time не становятся measurement window.

Этот список — рекомендации для отдельного V2-06a read-only review/approval,
не выполненные команды и не разрешение подключения. Если native source имеет
новую форму, сохранить artifact и оформить versioned offline review до нового
run. Не исправлять host/flags/sysctl автоматически. Ownership journal/witness,
installer/rollback, canonical round trip и physical experiment требуют своих
отдельных задач/разрешений; archive не даёт adoption/cleanup authority.

## 7. Tests и полный Trusted Checker regression

Добавлены
[`native_v2_native61_support.py`](trusted_checker_network/tests/native_v2_native61_support.py)
и [`test_native_v2_kernel_fixtures.py`](trusted_checker_network/tests/test_native_v2_kernel_fixtures.py):
**78 новых tests**, включая parameterized mutations всех **200 fields** и
removal каждого required path. Это 78 tests плюс subtests, не искусственный
пересчёт каждого field case как отдельного test.

Покрытие: original archive/member preservation, 107 checksums/34 exits/errs/JSON,
exact field/cardinality/presence matrix, 14/19 old schema outcomes, unknown fields,
malformed/null/bool/int/decimal types, source reference/hash/argv integrity,
route optional fields и RA nested metrics, FDB self/master/VLAN/state, native
bridge booleans, IPv6/extra namespaces, local joins/NSID ambiguity, missing
sources, immutable false flags, constructor bool/int confusion, separate policy
pin, limited mismatch/unproven outcomes и existing physical gate denial.
AST/fresh import tests запрещают OS/network/process discovery при import.

На первом новом прогоне два subtest failures обнаружили, что authored fixture
не содержал route6 type/table paths. Добавлен explicit synthetic local IPv6
route; schema не ослаблена. Затем standalone **78 tests, OK, 6.056s**. Финальный
review закрепил dispositions ordered_policy/observed_volatile в новом registry
и соответствие generated matrix; полный прогон ниже — на окончательном коде.

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
| Network: прежние 518 + новые 78 | 596 | 0 | 0 | 0 | OK, 82.708s |
| Physical | 90 | 0 | 0 | 0 | OK, 14.856s |
| Live | 48 | 0 | 0 | 0 | OK, 14.633s |
| Runtime | 66 | 0 | 0 | 0 | OK, 12.846s |
| Shadow | 56 | 0 | 0 | 0 | OK, 3.422s |
| PoC | 166 | 0 | 0 | 0 | OK, 15.010s |
| **Всего** | **1022** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0, без ResourceWarning и skips.
Прежние **944** tests и новые **78** прошли; Network теперь **596** tests.

Это полный Trusted Checker run, offline/mocks, не всех Django приложений.
Django/application regressions не запускались: application source/writers не
менялись. Fresh-import unittest запускает только локальный Python с socket/
Popen/system/setns blockers; physical subprocess отсутствует. Suites отдельными
процессами выполнялись независимо/частично параллельно, durations не benchmark.
Логи `/tmp/task201b8f-{network,physical,live,runtime,shadow,poc}.log`.

## 8. Целостность, новые files и source digest

SHA-256 всех **181 baseline artifacts** шести Trusted Checker packages без caches
и прежних TRUSTED_CHECKER reports сохранены в `/tmp/task201b8f-baseline.json`.
Прежние files, provisional schemas/profiles, contracts/tests/reports/native
originals, gates/live adapter не изменены. Рабочие БД, .env, credentials и Docker
sockets не читались.

Добавлены только:

- два production modules нового diagnostic profile;
- два test files;
- **114 fixture files**: 108 originals, оригинальный tar.gz и пять generated
  review/provenance/matrix/mapping/README artifacts;
- этот report.

Всего **119 новых files**; ни один старый файл не редактировался. Проверены
syntax/AST, whitespace, local Markdown links/fences, registry/matrix consistency,
original hashes и точный состав additions.

Dynamic physical source manifest автоматически включает два новых network modules:

- до: `dc83df5ebc3adbc8cc9777b5bcde3d61d93243cd9e96a78d52add6f72967e660`;
- после: `d319645c9dbe945f58b25ae84566ff9c94440532ab48e44758710f2532da8281`.

Старые approvals не обновлены/не переподписаны и не переносятся автоматически.
Новые fixture/version/archive references не создают authenticated approval.

## 9. Решение и оставшиеся blockers

**`V2-05 OFFLINE READY`**: originals и provenance сохранены, exact native schema
matrix подготовлена, отдельно versioned diagnostic decoder проходит реальный
corpus, local joins/FDB/candidates проанализированы, negative policy facts и
strict regressions закреплены. Старые provisional и physical boundaries
сохранены без изменения security policy.

Открыты native semantic/default/alias/temporal review, complete source coverage,
trusted namespace/FD/NSID/build/principal/timing/transport evidence, OS hooks/
permissions/FDs/writer control, approved canonical host/recipe installation,
ownership/rollback и controlled measurements. Эти blockers не скрыты green
format tests и не заполнены synthetic values. Нужен отдельный read-only
collector review, затем последующие approved stages из
[design V2](TRUSTED_CHECKER_NATIVE_COMPATIBILITY_V2_DESIGN.md).

Shadow-only; **physical gates CLOSED**. Ownership, management policy acceptance
и isolation остаются unproven. Ни один новый результат не может быть converted
в live permit, academic evidence или production sign-off.
