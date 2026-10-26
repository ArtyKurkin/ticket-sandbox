# Trusted Checker: Native v2 Management-host Profile Validator — №20.1b-8e

21 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-04 OFFLINE READY`.** Добавлен pure validator
`dedicated-management-host-v2`: независимый immutable policy manifest,
внешний digest pin, проверка conservative invariants и полное сравнение
supplied topology с expected sources. Positive fixture полностью synthetic;
manifest задаётся до rendering/decoding проверяемых captures.

Успех structural comparison представлен отдельно:
`structural_result=profile_structurally_matched`, но terminal
`result=profile_unproven`, `isolation_result=isolation_unproven`.
`management_policy_verified=false`, `isolation_verified=false`,
`physical_probe_permitted=false` без исключений. Ни provisional schema, ни
unauthenticated capture/reference не превращаются в physical proof. Все
обязательные OS surfaces остаются `unobserved`; physical audit `NOT READY`
сохраняется.

Работа только локальная/offline. SSH/VDS, ip/bridge/nft/Docker/setns/packet
operations, изменение host routes/firewall, физические reader/collector/
installer, live checker, Django/Ticket Sandbox/Ledger/Roadmap/достижения и deploy
не выполнялись и не добавлялись. Shadow-only, `PhysicalProbeGate` и
`physical_network_boundary_not_accepted` сохранены. Commit/push/rebase отсутствуют.

## 1. Архитектура и файлы

| Новый файл | Назначение |
|---|---|
| [`native_v2_management.py`](trusted_checker_network/native_v2_management.py) | Immutable profile/policy/requirements, проверка самого manifest, comparison и derived result |
| [`native_v2_management_support.py`](trusted_checker_network/tests/native_v2_management_support.py) | Explicit synthetic trusted policy inputs и отдельный rendering observed fixtures |
| [`test_native_v2_management.py`](trusted_checker_network/tests/test_native_v2_management.py) | 88 новых offline tests |
| Этот отчёт | Формат, invariants, пределы evidence и regression results |

Изучены V2-01 contracts, V2-02 expected/readback comparison, V2-03 schemas,
topology records/joins, fixtures/tests и existing physical preflight/inventory.
Прежние contracts и исходники не изменены. Новый package не создавался.
Production module импортирует только dataclasses и pure V2 modules, без OS I/O,
CLI, environment discovery, signing или v1/runtime conversion.

`validate_management_profile2(topology, expected_profile, pinned_profile_digest)`
принимает exact `TopologyEnvelope2`, exact `ManagementHostProfile2` и отдельно
закреплённый digest. Повторно проверяет typed inputs и вычисляет immutable
`ManagementProfileValidation2`. JSON decoder/OS collector сюда не добавлены.
Неподдерживаемый native JSON отвергает прежняя V2-03 граница; validator не
восстанавливает отброшенные поля и не ослабляет schema ради matching.

Нет production factory topology→trusted profile. Expected source specs не
содержат checked capture descriptor/raw digest, из которых можно автоматически
«одобрить» текущий host. Trusted setup заранее задаёт values и policy refs;
observed captures рендерятся/декодируются отдельно. Result constructor не
принимает override для computed result/reasons/evidence statuses или verification
flags. Malformed inputs дают finite `ContractViolation2` без supplied JSON/errors.

## 2. Точный формат management-host profile

`ManagementHostProfile2` frozen/slotted, profile ID
`dedicated-management-host-v2`, integer policy revision **1**, acceptance
**`provisional_offline_only`**. Унаследованы exact v2 offline domain/version,
`authentication=not_authenticated`, ownership/physical/continuous false.

| Поле / record | Содержание |
|---|---|
| Profile refs | Exact nonnil profile UUID, review reference digest, context UUID, capture approval reference digest и writer epoch UUID |
| `topology_profile` | Exact immutable V2-03 profile с binary references и pinned field/source registries; native approval не заявляется |
| `namespaces` | Ровно host, runner, target в заданном role order. Exact boot/inode/session/generation и namespace reference digest, разные inodes, общий boot/reader session |
| `NamespaceManagementPolicy2.links` | Host: loopback, ровно одна management NIC, один test bridge, runner/target host ports. Runner/target: loopback и один peer |
| `ManagedLinkPolicy2` | Role, full namespace+ifindex reference, exact MAC; для test bridge/ports/peers обязательный creation-record reference digest. Это pointer, не доказательство ownership |
| `NamespaceManagementPolicy2.sources` | Ровно девять `ExpectedTopologySource2`: link/address/bridge_link/vlan/fdb/route4/route6/rule4/rule6. Полные immutable schema-validated rows; mandatory empty source задаётся explicit empty tuple |
| `peer_witnesses` | Ровно две independently supplied offline пары host-port↔peer с reciprocal indices и namespace-scoped NSID refs; не выводятся из bridge `ifN` |
| `table_mappings` | Exact namespace/token/number/reference tuples; неизвестный alias не получает guessed mapping |
| `writers` | Непустой unique bounded tuple principal-reference digests, review ref и fixed exclusive/serialized mode; не OS permission facts |
| Nft expectation | Explicit canonical recipe digest reference; fixed семь host hook/priority/policy requirements, полный nft inventory требуется во всех namespaces |
| `requirements` | Derived immutable mandatory OS evidence requirements; caller не может удалить/пометить их observed |

Source specs сохраняют **все** поддерживаемые fields, row order и optional
presence. Их closed schemas и bounds — прежние V2-03, без новых normalization
aliases. Namespaces ограничены тремя, links — пятью/двумя/двумя, writers ≤16,
table mappings ≤32; source rows ≤1024 с прежними bounded types. Новый parser
или увеличение capture limits/budgets не добавлены.

Content digest покрывает весь profile, sources/addresses/routes/RPDB/options,
identities, creation/review/writer/nft refs и derived requirements. Это
не подпись, не authenticated approval и не host attestation. Внешний
`pinned_profile_digest` должен приходить из trusted setup независимо от tested
snapshot. Подмена manifest, даже вместе с подходящим новым snapshot, не проходит
со старым pin. Если caller намеренно подменит и manifest, и доверенный pin,
эта pure библиотека не может обнаружить компрометацию trusted caller.

Сам manifest проверяется на полную source coverage, внутренние joins и hard
conservative invariants. Нельзя разрешить peer default/gateway/source routing
или test-side IPv6, просто вписав их в expected rows. Boolean `dedicated_vm`,
`allow_any_provider_routes`, `native_approved` или `os_surfaces_verified` API
не принимает.

## 3. Проверяемые сетевые invariants

1. **Management identity.** Exact namespace/ifindex/MAC/name/MTU/flags из
   manifest; имя eth0 не заменяет identity. Management NIC — ether, без
   master, link_index/link_netnsid, linkinfo attachment и MASTER/SLAVE flags.
   Перемещение в peer namespace, превращение в veth/bridge или включение в
   test bridge дают mismatch. Bond/VRF/tunnel/macvlan формы уже unsupported
   в V2-03 и не доходят до policy admission.
2. **Host graph.** Только пять registered links. Test bridge сохраняет
   canonical имя tcsh0; host ports — veth с прежним naming constraint.
   Ровно два members, exact bridge/port fields/options, reciprocal peers,
   MAC/MTU/flags, VLAN ranges/PVID/untagged и FDB tuples. Extra NIC/bridge/veth,
   port, VLAN или чужой FDB MAC не исчезают из inventory.
3. **Addresses.** Полные address rows во всех namespaces, включая empty
   addr_info, flags/lifetimes/IPv4/IPv6/prefix/scopes. Management IPv4/IPv6
   разрешаются только exact manifest rows. Host bridge/ports и peer veth
   не могут иметь IPv6 addresses; такие rows не фильтруются.
4. **IPv6 routes.** На host test bridge/ports и peer veth IPv6 routes запрещены.
   Exact management IPv6 routes и loopback ::1 остаются видимыми. Новый
   link-local candidate — mismatch, не игнорируемый «обычный IPv6 noise».
5. **Runner/target.** Только loopback+peer, без default route, gateway, source
   selector на route и alternative tables. Допустимые routes — kernel
   connected/local с scope link/host в explicit mapped main/local tables.
   RPDB ограничен обычными local/main/default priority/table tuples с src=all;
   дополнительные selectors/reroute не допускаются. Exact rows проверяются
   дополнительно, а не заменяются этими общими constraints.
6. **Host routes/RPDB.** Default route может указывать только на management
   NIC. Все management/provider/connected/local rows сравниваются exact:
   family, table, dst/src/prefsrc, gateway/dev, protocol, metric, type/scope,
   flags/pref и optional presence. Нет wildcard на provider routes. RPDB
   selectors/mark/mask/action/priority/order сохранены. Equal-priority ambiguity
   запрещена в первом profile.
7. **Binding и coverage.** Exact topology profile, namespace refs,
   context/approval/epoch, peer/table witnesses. NSID не может разрешаться
   в два namespaces одной session. Missing source не преобразуется в [];
   diagnostic partial sources не удовлетворяют required full captures.

Expected graph проверяется независимо без создания synthetic capture из
ожидаемого profile. Затем все supplied source rows полностью сравниваются
с manifest; counter/packet evidence здесь не участвует. JSON whitespace/key
order не меняют typed values; arrays/row order не сортируются. Timers/lifetimes/
FDB transitions остаются exact unchanged, как в V2-03.

## 4. Примеры отказов

| Mutation относительно valid synthetic baseline | Результат / finite reason |
|---|---|
| Management NIC enslaved, включая согласованный ip/bridge dump | `profile_mismatch` / `management_link_attachment_forbidden` |
| Третий bridge port, extra host veth или Target NIC | `profile_mismatch` / `link_inventory_mismatch` |
| Неверные MAC/MTU/options или peer link_index | `profile_mismatch` / identity/link policy mismatch; плохой peer join также остаётся unproven в topology |
| Другая VLAN/FDB MAC/state/offload flag | `profile_mismatch` / `vlan_policy_mismatch` либо `fdb_policy_mismatch` |
| Другой management gateway, provider/source route или metric | `profile_mismatch` / `route4_policy_mismatch` или `route6_policy_mismatch` |
| Runner default/gateway/src selector | `profile_mismatch` / `peer_default_route_forbidden`, `peer_gateway_forbidden`, `peer_source_route_forbidden` |
| RPDB priority/selector/order либо удалённый optional selector | `profile_mismatch` / rule policy mismatch; peer selectors дополнительно `peer_policy_routing_forbidden` |
| IPv6 link-local address/route на test-side | `profile_mismatch` / `test_side_ipv6_forbidden` или `test_side_ipv6_route_forbidden` |
| Coherent namespace generation/session replacement | `profile_mismatch` / `namespace_identity_mismatch` |
| Подменённый manifest или digest | `profile_mismatch` / `profile_digest_mismatch` |
| Отсутствующий source, который должен был быть empty | `profile_unproven` / `source_coverage_incomplete`; structural match отсутствует |
| Unknown tunnel kind, field, action/expiry structure | Finite refusal существующего decoder/schema до policy validation |

Конкретные mismatches имеют приоритет над provisional/evidence unknowns:
отсутствие writer proof не скрывает уже видимый неверный gateway или port.
При missing witness сохраняется unknown; supplied **неверный** witness остаётся
mismatch, даже если второй witness отсутствует.

## 5. Structural match, acceptance и реальные artifacts

| Поле result record | Значение |
|---|---|
| `structural_result` | `profile_structurally_matched`, `profile_mismatch` либо `profile_unproven` по observable полям/coverage |
| `result` | `profile_mismatch` при конкретном отклонении; иначе **всегда `profile_unproven`** в этом offline revision |
| `isolation_result` | Всегда `isolation_unproven` |
| Verification / authority | management_policy_verified, isolation_verified, measurement_verified, physical_probe_permitted, ownership_proven, continuous_attestation всегда false |
| Evidence statuses | Только `unobserved`; нет принятого OS proof input или boolean исключения |

Raw topology/schema success, reviewed fixture digest и exact comparison не
проверяют source authenticity, trusted reader, actual namespace FDs, permissions,
continuous control или native host build. Даже synthetic positive не получает
policy verification flag. Result содержит typed references и finite reasons;
это internal DTO, не operator export. Signing/receipt issuance, bounded export,
durability, freshness/deadline/replay/kill integration не реализованы.

Original
[`bridge_tc_br0_final.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/bridge_tc_br0_final.json)
и [`bridge_links_final.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/bridge_links_final.json)
проверены byte-for-byte с
[`provenance.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/provenance.json)
и [`raw_terminal_capture.md`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/raw_terminal_capture.md).
Actual tc-br0/ports/if6/if8 и exact decimal gc_timer=178.16 сохраняются; captures
остаются single-link/basic-ports. Они дают structural/profile unproven, не полный
profile acceptance. Full host/peer data и OS witnesses не реконструировались,
текст terminal log не превращён в недостающие JSON. Cumulative nft values не
используются как measurement или isolation evidence.

## 6. Неподтверждённые OS surfaces

В profile обязательны **120 scoped requirements**: 13 namespace-level во всех
трёх namespaces и 9 link-level для всех девяти links. Для каждого создаётся
`EvidenceRequirementStatus2(status=unobserved)`. Требования нельзя удалить через
constructor или заменить на none/false/verified.

Namespace scope: full nft hooks/priorities/approved recipe inventory, flowtables,
IPv4/IPv6 forwarding, proxy ARP/ND, bridge-netfilter, network capabilities и
reviewed host/peer principals, external/inherited FDs и privileged sockets,
writer authority, namespace attachments, authenticated capture provenance,
approved native host profile. Link scope: tc ingress/egress, XDP, offloads,
forwarding, proxy ARP/ND и exact bridge-netfilter configuration.

Host hook expectations — bridge prerouting/input/forward/output priority 0
policy drop; inet input/forward/output priority -310 policy accept с отдельным
canonical recipe reference. Это требования, **не наблюдённые nft rules**.
V2-02 readback/CT/raw proof не импортируется как substitute OS inventory.

Existing `HostPreflight` и `NamespaceInventory` остаются отдельными dormant
physical contracts. Их capability/Docker/proc facts не преобразуются в V2-04
attestation. HMAC keys сами по себе не дают независимых OS principals.
Snapshots разных sources не атомарны и не исключают attach/revert, FD transfer
или rules reset/restore между чтениями. Root/daemon admin остаются TCB.

## 7. Tests и полный regression run

Новые **88 tests** покрывают complete structural positive, все false flags,
profile version/domain/pin/immutability, manifest self-validation, management
attachments/move, additional NIC/veth/bridge/tunnel, third port, VLAN/FDB,
MAC/MTU/flags/options, provider routes/defaults/source selectors, IPv4/IPv6,
RPDB selectors/priority/order/presence, namespace/session/epoch changes,
missing sources/witnesses, 120 unobserved requirements, native partial artifacts,
exact physical gate denial и import/AST isolation. Mutations начинаются с valid
synthetic baseline своей стадии; unsupported raw formats явно тестируются на
V2-03 refusal, а не объявляются принятыми policy inputs.

Standalone run: **88 tests, OK, 20.908s**. Предыдущий промежуточный run 81 tests
тоже прошёл; дополнительные tests закрепили profile/NSID/selector/evidence scope.
Нет skipped/expected-failure tests вместо отсутствующего physical evidence.

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
| Network: прежние 430 + новые 88 | 518 | 0 | 0 | 0 | OK, 72.427s |
| Physical | 90 | 0 | 0 | 0 | OK, 9.530s |
| Live | 48 | 0 | 0 | 0 | OK, 9.884s |
| Runtime | 66 | 0 | 0 | 0 | OK, 8.186s |
| Shadow | 56 | 0 | 0 | 0 | OK, 2.137s |
| PoC | 166 | 0 | 0 | 0 | OK, 9.726s |
| **Всего** | **944** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0, без ResourceWarning и skips.
Новых tests — **88**, прежних — **856**; в Network теперь **518** tests.

Suites выполнялись отдельными процессами независимо/частично параллельно;
durations не benchmark. Это полный Trusted Checker, не всех Django приложений.
Django regressions не запускались: application code/writers не менялись.
Fresh-import test запускает только локальный Python, блокируя socket/Popen/
system/setns внутри проверяемого import. Реальных physical subprocess нет.
Логи `/tmp/task201b8e-{network,physical,live,runtime,shadow,poc}.log`.

## 8. Целостность и source digest

SHA-256 всех **177 baseline artifacts** шести Trusted Checker packages без
caches и прежних `TRUSTED_CHECKER*.md` сохранены в
`/tmp/task201b8e-baseline.json`. Проверено сохранение прежних source/tests,
V2-01/02/03, v1, reports/design, native originals, physical gates и live adapter.
Добавлены только один production module, два test files и этот отчёт.
Рабочие БД, .env, credentials и Docker sockets не читались.

Existing dynamic physical source manifest включает новый top-level network module:

- до: `cbf42c264a4b6fff7943730a4c31e746e2f41f1e9a6a1948d79a03b45b1858ad`;
- после: `dc83df5ebc3adbc8cc9777b5bcde3d61d93243cd9e96a78d52add6f72967e660`.

Старые approvals не обновлялись, не подписывались и не переносятся автоматически.
Policy/review/creation digest references новых fixtures не создают authority.
Проверены syntax/AST, whitespace, Markdown links/fences и состав новых files.

## 9. Зависимости V2-05/V2-06 и итог

V2-05 должен закрепить schema/profile review и расширенную regression matrix
на original complete native captures, сохраняя provenance и отдельно authored
synthetic positives. Нужны полные host/peer ip/bridge/address/routes/RPDB/VLAN/FDB
artifacts на exact builds; unsupported shapes — отдельный reviewed profile,
без автоматического widening и без удаления неудобных fields/IPv6 rows.

V2-06a требует независимого trusted read-only collector: fixed source/argv
coverage, bounded authenticated transports, actual namespace/peer/NSID/table
witnesses, principal/permission review, wall/monotonic/session/epoch/freshness
fences и все дополнительные OS surfaces. V2-06b/c отдельно требуют durable
ownership/transaction witness/journal, lost-response quarantine, serialized
installer/rollback и replay/kill review. Никакой из этих boundaries здесь не
создан и не унаследован от v4 автоматически.

Чтобы когда-либо установить management/isolation verification, потребуются
reviewed native host profile, authenticated provenance, actual writer/permission
control, полный topology/hook/config/FD inventory, recipe/CT/raw/byte proofs,
отдельные measurements и security/activation review. Отсутствие default route
в runner и structural match по manifest этого не заменяют. Новый stage не
расширяет v1 measurement window или live policy.

**`V2-04 OFFLINE READY`** для описанного conservative offline comparison.
Физическая изоляция не доказана; `PhysicalProbeGate` и
`physical_network_boundary_not_accepted` закрыты. `profile_unproven` и
`isolation_unproven` сохраняются даже на полном synthetic positive.
