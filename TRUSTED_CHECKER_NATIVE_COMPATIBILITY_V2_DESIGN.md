# Trusted Checker: Native Compatibility Contract v2 — №20.1b-8a

20 октября 2026 · design revision 1 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`DESIGN READY FOR REVIEW`.** Ниже задан отдельный proposed v2 contract с
закрытой схемой, scoped identities и независимым topology adapter. Это готовность
спецификации к review, не принятие kernel compatibility, реализация v2 или
разрешение физического опыта. Итог [№20.1b-7b](TRUSTED_CHECKER_KERNEL_COMPATIBILITY_AUDIT.md)
`NOT READY` остаётся в силе. Непроверенные kernel representations дают unknown;
раздел 12 перечисляет artifacts, без которых physical acceptance невозможен.

Изменение этого этапа — **только этот документ**. V1, production contracts,
runtime, tests, native fixtures, gates и прежние отчёты не изменяются. Нет SSH,
VDS, Docker/nft/ip/setns/packet operations, deploy, Django/Ticket Sandbox,
Ledger/достижений или учебных transitions. Shadow-only сохраняется;
`PhysicalProbeGate` и `physical_network_boundary_not_accepted` закрыты.

## 1. Основание и статус утверждений

Основание — текущие
[`counter_contracts.py`](trusted_checker_network/counter_contracts.py),
[`counter_rules.py`](trusted_checker_network/counter_rules.py),
[`counter_readback.py`](trusted_checker_network/counter_readback.py),
[`counter_inventory.py`](trusted_checker_network/counter_inventory.py),
[`counter_evidence.py`](trusted_checker_network/counter_evidence.py), v4
[`inventory.py`](trusted_checker_physical/inventory.py) и результаты аудита.
Число **602 tests, OK** относится к предыдущему этапу; оно не является новым
прогоном этого design или проверкой ещё не реализованного v2.

Оригинальные artifacts сохранены в
[`native/`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native),
их hashes — в
[`provenance.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/provenance.json).
Они подтверждают следующие формы, но не canonical round trip:

| Подтверждено artifacts | Не следует из artifacts |
|---|---|
| nft `1.0.9`, release `Old Doc Yak #3`, JSON schema integer `1`; один `metainfo` | Что schema version проверяет compiler/binary/source или полноту dump |
| Table→chain→rules grouping; priorities −200 и 10 | Что лабораторные hooks/priorities соответствуют approved recipe |
| Scalar `ct state in "new"/"established"` | Эквивалентность с v1 `==`; семантика всех masks/sets/операторов |
| Counter перед отдельным accept/drop; три nonterminal CT rules | Что nonterminal CT counter доказывает drop |
| Table handle 8 и rule handle 8; chain handle 1 в двух tables | Глобальная уникальность numeric handle или право на adoption |
| Bridge-port `master: "tc-br0"`, `link: "if6"/"if8"` | Peer namespace identity или формат `master` в полном **ip port** dump |
| Bridge-only ip JSON, включая `gc_timer: 178.16` | Полный host/peer inventory, отсутствие routes/attachments или snapshot continuity |

Пять strict cumulative pairs `1/60`, `5/338`, `6/1931`, `6/428`, `3/176`
сохраняют статус final observations. Ни delta, ни before/after из них не строятся.
Внешние manual/source в этом этапе не исследуются; неподтверждённая семантика
не включается в allowlist преобразований.

## 2. Версии, trust domains и границы результата

Все имена в следующей таблице — **предлагаемые идентификаторы**, не существующие
DTO/API и не новые разрешённые execution paths.

| Поле / artifact | Предлагаемое значение и правило |
|---|---|
| Contract | `tc-native-compatibility-v2`, integer `contract_version=2`; design revision не подменяет protocol version |
| Будущий method | `nft_counter_probe_v2`; ни alias, ни in-place upgrade `nft_counter_probe_v1` |
| Native format profile | `nft-1.0.9-json1-v2`; точные версии и binary/build/source digests в immutable profile manifest |
| Topology format profile | `iproute2-native-topology-v2`; exact ip/bridge versions/builds ещё не зафиксированы, поэтому native topology acceptance сейчас закрыт |
| Host policy profile | `dedicated-management-host-v2`; отдельный signed manifest, не boolean `dedicated_vm` |
| Offline origin/domain | `offline_native_compat_fixture` / `tc-nft-counter-probe-v2-offline`; exact new types и раздельные role keys |
| Physical origin/domain | **Не определены как принимаемые** этим design; будут отдельным versioned collector/ownership review. Offline signatures нельзя переименовать в physical |
| Recipe, binding, installation | Разные `canonical_recipe_digest`, `native_profile_digest`, `topology_profile_digest`, `binding_digest`, `installation_binding_digest` |
| Counters/bytes | Integers `[0, 2**63-1]`; byte basis имеет отдельные id, build/hook scope и proof reference. `offline_frame_bytes` не становится kernel basis |
| Release | Любой локальный результат содержит `physical_probe_permitted=false`, `continuous_attestation=false`, `trace_delivery_complete="unproven"` |

Версии сравниваются exact, не semver range. Нет auto-upgrade по schema=1,
fallback на v1/v3/v4 или импорта их receipt как v2. Все registry/profile digests
утверждаются **до** чтения проверяемого input. Input не выбирает удобный decoder
по собственной версии. Смена build/profile/registry требует нового approval.

Предлагаемые отдельные типы: `DecodedNative2` → `NormalizedRules2` →
`ValidatedRecipe2`; независимо `TopologyObservation2`; отдельно terminal
measurement evidence. Decoding success не конструирует validated type.
`format_decoded`, `recipe_matched` и `measurement_verified` — разные стадии:
первые две не доказывают прохождение пробы. Статус terminal verifier сохраняет
fail-closed `unknown` при любой незакрытой обязательной стадии. Никакой тип этого
design не конвертируется в live `EgressValidation` или authority permit.

### 2.1. Capture descriptor

Каждый raw artifact связан с immutable descriptor:

```text
capture_uuid, contract/profile ids+digests, approval_uuid+digest, context_uuid,
origin/auth_domain, collector_principal, host_boot_uuid, reader_session_uuid,
namespace_identity, argv_profile_id+argv_digest,
wall_started/finished, monotonic_started/finished,
raw_sha256, raw_byte_count, exit_status, transport_completion_receipt,
writer_epoch_uuid, install_epoch_uuid, install_generation
```

`namespace_identity` содержит host boot, netns inode, открытый trusted namespace
reference и capture session; PID при использовании дополняется start ticks и
проверяется до/после. Только имя netns или локальный NSID identity не образуют.
Один `reader_session_uuid` и namespace binding действуют для installation
binding и всего measurement; это не новый UUID на каждый файл. Перезапуск
читателя/смена session закрывает measurement и требует нового reviewed binding,
не возобновления прежней baseline. `capture_uuid` у каждого файла свой.
Raw bytes/hash сохраняются отдельно от canonical digest. Подпись покрывает
descriptor и hash; stdout completeness выводится из bounded trusted capture,
а не supplied `complete=true`. Nonzero exit, timeout, truncation, потеря binding,
clock rollback или несовпадение principal/profile дают unknown. Подпись fixture
остаётся утверждением fixture principal, не независимой OS attestation.

## 3. Native nft schema и три независимые проверки

### 3.1. JSON decoding

Предлагаемый профиль сохраняет nft cap **262144 bytes**, UTF-8 без BOM, запрет
duplicate keys, floats/nonfinite и bool-as-int. Дополнительные parser bounds:
depth≤32, nodes≤32768, objects≤128, expressions/rule≤64, string≤256 UTF-8 bytes.
Превышение — отказ, без truncation. Bounds проверяются при разборе, а не после
неограниченного выделения памяти. Nft profile не используется для ip JSON.

Root — ровно `{"nftables": [...]}`. В полном readback каждый элемент — ровно
один из `metainfo`, `table`, `chain`, `rule`; transaction wrappers
`add/create/delete`, sets/maps/flowtables/objects и неизвестные kinds отвергаются.
Другие формы могут разбираться только как отдельный diagnostic artifact,
который не удовлетворяет readback contract.

| Object | Точные keys в первом nft profile |
|---|---|
| `metainfo` | `version`, `release_name`, `json_schema_version` |
| `table` | `family`, `name`, `handle` |
| Base `chain` | `family`, `table`, `name`, `handle`, `type`, `hook`, `prio`, `policy` |
| `rule` | `family`, `table`, `chain`, `handle`, `expr` |

Нет optional unknown fields. `metainfo` — ровно один, первый object;
`version="1.0.9"`, `release_name="Old Doc Yak #3"`, schema **integer** `1`.
Значения exact bound к approved format profile и capture binary witness.
Отсутствие/дублирование header, лишний field или несовместимая версия — unknown.
Header валидируется и сохраняется; его исключение из **policy** digest не
означает игнорирование и не исключает его из profile/capture digest.

Family для validated recipe только `bridge`/`inet`; имена и scalar types exact
с expected recipe. `handle` — integer в консервативном диапазоне
`[1, 2**63-1]`; `prio` — integer, не строковое symbolic priority. Unsupported
native range остаётся unknown до нового profile review.

Expression grammar закрыта: только ordered nodes, которые отдельно описаны
compiler/profile manifest и ожидаются в конкретном rule. Это exact `match`
(`op,left,right`), named payload/meta/ct references, approved bitwise fragment
match, raw payload match, anonymous `counter` и verdict. Нет arbitrary AST
passthrough. Unknown keys/operators/protocol fields дают unknown, даже если rule
в конце drop. Для raw payload дополнительные ограничения заданы в разделе 6.

### 3.2. Native normalization: topology объектов nft

Normalizer строит keyed table/chain graph и **ordered** rule sequences:

```text
Ruleset2 = metadata + tables[(family, table_name)]
Table2   = exact table attributes + chains[chain_name]
Chain2   = exact base-chain attributes + rules[encounter_order]
Rule2    = scoped native identity + ordered typed expressions + counter rows
```

Глобальный индекс serialized object перестаёт быть identity. Table/chain
declarations обязаны быть уникальны; table объявлена до её chain, chain до её
rules. Каждая ссылка разрешается ровно в один parent. Разрешены как native
table→chain→rules grouping, так и объявление всех headers до rules. Interleaving
разных chains не меняет их последовательностей: encounter order вычисляется
**отдельно для каждой `(family,table,chain)`**. Rule order никогда не сортируется
по handle, match, digest или verdict и не восстанавливается из expected recipe.

Maps tables/chains могут получать детерминированный key order только при
сериализации digest. Это допустимо при полном inventory всех hooks и отсутствии
неразрешённой execution-order ambiguity: каждый `(family,hook,priority)` в
approved boundary уникален. Чужая chain, одинаковая priority конкурирующих base
chains или неизвестный hook — unknown, а не повод стереть порядок tables.
Не утверждается эквивалентность произвольных rulesets при перегруппировке.

### 3.3. Canonical recipe validation

Expected graph независимо строится из exact new approval/binding и immutable
compiler/profile. Supplied installer rules/digest/`verified=true` не заменяют
его. Сравниваются полный набор tables/chains, все static attributes и ordered
rules/expressions. Для active recipe сохраняется целевой invariant: **2 tables,
7 chains, 49 rules, 49 anonymous counters**, то есть 58 policy objects плюс
один metadata header. Bootstrap компилируется и проверяется отдельно, без accept.

Bridge priorities **0**, policies **drop**, hooks prerouting/input/forward/output;
inet priorities **−310**, base policies accept и четыре прежних exact guard
drops. Allowlists TCP/ARP, physical ingress identity и finite 15-probe plan не
расширяются native adapter. Laboratory −200/10 и policy accept не нормализуются
к canonical значениям. Конкретные rules/frames по-прежнему определяет approved
compiler, а не generic caller-provided policy.

Full host ruleset читается целиком. В первом management-host profile допускаются
только зарегистрированные canonical tables; existing UFW/foreign nft table
вызывает unknown/STOP. Не фильтровать её из input и не делать automatic flush.
Если потребуется coexistence, это отдельный полный policy/hook profile review.

## 4. Canonicalization выражений и CT semantics

### 4.1. Разрешённые и запрещённые преобразования

| Разрешено с проверкой | Почему не теряется security evidence |
|---|---|
| JSON whitespace/key ordering и обычное декодирование string escapes | Значения и scalar types сохраняются; raw hash фиксирует исходные bytes |
| Grouping tables/chains по validated parent keys | Все объекты учтены, rule encounter order и hook/priority identities сохранены |
| Counter numbers отделены в value rows | Counter node/position, scope, handles и numeric types сохраняются в catalog; static сравнение не игнорирует counter |
| `metainfo` хранится отдельно от policy graph | Exact metadata/profile/binary checks обязательны до matched result |
| Known native CT node получает explicit typed tag с тем же operator/literal | Никакой alias между equality и membership не вводится |

Запрещены: сортировка/дедупликация rules или expressions; commutation matches;
перемещение counter/verdict; удаление protocol dependencies; замена `ip protocol`
на `meta l4proto`; снятие VLAN/fragment constraints; coercion bool/string/float
к integer; пропуск unknown keys/fields/objects; named/shared counter вместо
anonymous; merge/split counters; table rename, interface rename или проставление
missing fields из expected recipe. Нет «best effort» static compare.

Digest использует domain-separated canonical typed representation с
детерминированными keys, сохранённым array order и точными types. Отдельны
semantic recipe digest, normalized static digest, installed identity digest,
counter row digest и raw artifact digest. Сравнение hash не отменяет независимое
построение expected values и валидацию всего graph.

### 4.2. `ct state in` без недоказанного `==` alias

Первый decoder распознаёт observed форму ровно:

```text
match(op="in", left=ct(key="state"), right=scalar "new" | "established")
  → NativeCtStateIn(literal), с сохранением original operator/position
```

Integer masks, arrays, anonymous sets, `related`, negation, other CT keys и
расширенные expressions этим profile не принимаются. Поддержка `"new"` в
**format decoder** не добавляет NEW allow rule: canonical validator требует
точный ожидаемый predicate на своей позиции и отвергает лишнее.

V1 `match(op="==", ... "established")` и native `in "established"` — разные
AST nodes. **В первой версии registry alias между ними пуст.** Отсутствие proof
даёт `ct_semantics_unproven`, не автоматическую эквивалентность.

Предлагаемый semantic predicate v2 для двух return allow rules —
`HAS_ESTABLISHED`: CT state удовлетворяет approved established membership
predicate; новые/invalid/related-only состояния сами по себе допуска не дают.
Точные mask encoding, membership truth table, дополнительные state bits и
hook availability должны быть закреплены в immutable `CtSemanticsProof`:
exact builds/source references, compiler input, native readback, evaluated
state cases и reviewed truth table. Никаких guessed numeric bits.

До этого proof `NativeCtStateIn` пригоден для format audit, но не даёт canonical
semantic match. Если native compiler v2 должен явно emit `in`, это отдельное
одобрение semantic recipe v2 с новым digest. Оно не наследует v1 approval.
Чтобы объявить alias `==`↔`in`, proof должен установить их эквивалентность на
**всём approved state domain**, а не только HTTP happy path. Если она неверна,
alias остаётся запрещён; изменение predicate требует policy review, а не
«normalization fix». Так design не обещает сохранить неизвестную семантику v1.

## 5. Scoped handle identity и installation ownership

### 5.1. Locator, identity и counter slot

```text
NamespaceKey = (host_boot_uuid, netns_inode, reader_session_uuid,
                namespace_binding_generation)
InstallKey   = (approval_digest, binding_digest, writer_epoch_uuid,
                install_epoch_uuid, positive_integer install_generation)

TableIdentity = (NamespaceKey, InstallKey, family, kind="table", name, handle)
ChainIdentity = (parent TableIdentity, kind="chain", name, handle,
                 type, hook, priority, policy)
RuleIdentity  = (parent ChainIdentity, kind="rule", handle,
                 canonical_rule_id, chain_ordinal)
CounterSlot   = (RuleIdentity, expression_position, kind="anonymous_counter",
                 canonical_counter_id, purpose, probe_id_or_none)
```

Ordinal/position — zero-based integers; negative index запрещён. Stable
`canonical_rule_id` берётся из compiler catalog, не из supplied comment/name.
Compiler IDs привязаны к canonical family/table/chain path и rule ordinal,
а не к global serialized object index native dump.
Catalog содержит static match/verdict digest; одинаковые labels не являются
identity. Rule handle, parent chain и ordinal проверяются одновременно.
Normalization не может менять число или позиции expression statements.

### 5.2. Уникальность и обязательные отказы

| Объект | Область numeric handle uniqueness первого profile |
|---|---|
| Table | `(NamespaceKey, family, kind=table)`; также unique `(family,name)` |
| Chain | `(NamespaceKey, family, parent table identity, kind=chain)`; unique chain name в table |
| Rule | `(NamespaceKey, family, parent table identity, kind=rule)` **во всех chains table**, а не отдельно в каждой chain |
| Counter | Exact `CounterSlot`, один counter на approved rule; shared slot между probes запрещён |

Одинаковое число table handle и rule handle допускается: native table 8/rule 8
не collide. Chain handle 1 в разных tables также не collide. Для первого profile
дополнительно консервативно запрещён одинаковый chain/rule handle **внутри одной
table**, пока такой reuse не подтверждён новым native identity review. Это не
глобальная уникальность и не отвергает имеющиеся laboratory examples.

Same rule handle в разных chains одной table — отказ, даже если full tuple
с chain name получился бы разным. Иначе перенос rule можно было бы скрыть
неверно выбранной областью uniqueness. Замена parent table/chain, ordinal,
handle, epoch/generation или static digest закрывает baseline. Полное before/
after counter catalog equality обязательно; строки нельзя zip-сопоставить
после удаления/перестановки объекта.

### 5.3. Откуда берётся binding handles

До установки handles неизвестны. Поэтому вместо угадывания approval numbers
нужны два разных immutable artifacts:

1. `InstallIntent2`: pre-approved recipe/binding/profile digests, namespace,
   newly owned names/resources, exclusive-create transaction UUID, writer epoch
   и разрешение **отдельного** опыта. Journal intent durable до dispatch.
2. `InstallationBinding2`: committed-transaction witness, independent readback
   reference и validated mapping canonical IDs→scoped native identities. Только
   после подтверждённого exclusive creation в serialized writer epoch.

Measurement approval связывает оба digest. Independent reader не получает
ownership из table name, handle или совпадения rules. Installer сам не может
подменить reader/transaction witness. Readback чужого объекта не создаёт новый
binding. Reboot, writer/session drift, replacement или новая generation требуют
нового intent/binding и полной повторной валидации, без automatic adoption.

При lost apply response нет blind retry, reapply или adoption по dump. Если
trusted committed witness не устанавливает исход, состояние quarantine; cleanup
разрешён только для отдельно доказанно owned identities. Этот документ не
реализует journal, transaction observer или rollback controller и не меняет v4.

Смена numeric handle обнаруживается. Privileged delete/recreate с восстановлением
всех видимых значений/handles между snapshots **не исключается**: scope не
создаёт kernel continuity proof. Для этого остаются trusted writer control,
epoch invalidation и отдельная durable operational composition.

### 5.4. Почему изменение scope не ослабляет attribution

При реализации **всех** проверок выше модель даёт следующие условные гарантии:

| Попытка подмены | Независимые основания для отказа |
|---|---|
| Совпадение numeric rule handle в другом объекте | Сверяются family, kind, parent table/chain identities; число само по себе не lookup key |
| Перенос rule/counter при прежнем handle | Parent chain, ordinal, ordered static expressions, counter slot/position и purpose должны совпасть с catalog одновременно |
| Чужой table с правильным именем/содержимым | Нет связи с pre-dispatch intent, committed creation witness и выданным installation binding; readback equality не выдаёт ownership |
| Старый snapshot/receipt в новой установке | Exact approval/context/session/install epoch/generation и capture interval входят в проверку и authenticated refs; baseline catalog должен совпасть целиком |

Это аргумент о contract invariants, не результаты ещё не написанных тестов и не
защита от компрометации trusted principals. Same-visible-state replacement
привилегированным writer между snapshots остаётся ограничением раздела 8.2.

## 6. Counter placement, raw payload и byte accounting

В normalized graph anonymous counter — statement на exact index с ровно
`packets` и `bytes`. Numbers не участвуют в static recipe digest, но находятся
в authenticated rows. Counter count/presence/position обязательны. Accepted
patterns задаются compiler catalog, а не эвристикой «counter перед drop»:

- ingress: exact matches → counter → конец rule, **без verdict**;
- negative terminal: exact matches → counter → drop;
- allow: approved matches → counter → accept;
- guard/fallback: их exact approved matches → counter → drop.

Nonterminal counter не является deny evidence; base policy drop без нужной
delta также не подтверждает отдельную negative пробу. Сохраняются exact deltas
всех 49 counters, 15 sequential samples, send/ingress correlation, matching
positive SYN-ACK/RST-ACK и отсутствие unexplained changes между samples.
Reset/decrease/overflow, extra counts, missing events, background ARP/response/
retransmit или byte mismatch дают unknown. Нет tolerance и subtract-noise.

Raw-payload expression можно сравнивать exact только при утверждённом
representation profile для `(base, offset unit, length unit, byte order,
right literal width/value, VLAN context)` и сохранённых dependencies. Вход
compiler фиксирует bits и исходный frame digest. Native hex/string/integer
normalization не выводится из визуально одинаковой hex записи. Неизвестные
leading-zero rules, register widths, implicit extraction или VLAN offsets —
`raw_payload_representation_unproven`. Ни один преобразователь не включён
только потому, что он нужен для green round trip.

`ByteAccountingProof` привязан к exact kernel/build/hook/family, frame form,
padding/VLAN/offload profile, request/reply и наблюдаемым aggregation constraints.
До него accounting status — `unproven`; format/recipe match допускается как
diagnostic stage, physical measurement verification — нет. Нельзя считать 60
native bytes эквивалентом synthetic 54 по постоянной поправке или считать
глобальный dump атомарным. Любая смена basis — новый approved accounting id и
review, без переноса v1 `offline_frame_bytes_not_kernel_verified` в kernel proof.

## 7. Независимый native topology adapter

Collector выполняет только exact отдельно разрешённые captures; adapter — pure
функция supplied bytes+descriptors+approved schema/profile. Разные principals/
binaries/config для installer, reader и validator обязательны в future physical
review. Разные HMAC keys сами по себе не обеспечивают разделения OS privileges.
Отсутствие любой обязательной поверхности — unknown, а не пустой массив.

### 7.1. Источники и закрытая field registry

| Источник в **каждом применимом namespace** | Что связывается и проверяется |
|---|---|
| `ip -j -d link` | Exact ifindex/name/kind/MAC/MTU/flags/master/link attributes; bridge options, tunnels/VLAN/VRF/macvlan и неизвестные kinds |
| `ip -j address` | ifindex join, все IPv4/IPv6 addresses/prefixes/scopes/flags/lifetimes; отсутствие скрытых secondary/link-local addresses |
| `bridge -j link` | Отдельная port schema: master name, port ifindex/name/state/flags, link string; не заменяет ip link data |
| Bridge VLAN/FDB dumps | Membership/PVID/untagged, self/master/local/static/dynamic entries и привязка MAC/VLAN→owned port |
| IPv4 и IPv6 routes `table all` | Все tables, type/prefix/device/gateway/source/protocol/metric/scope, multipath/encap/flags при поддержке exact schema |
| IPv4 и IPv6 RPDB | Ordered priorities, family, selectors, table/action, marks/masks, interface selectors и suppress/l3mdev attributes |
| Namespace identity/peer facts | Trusted namespace FDs/inodes, process start ticks при PID, namespace-scoped NSID resolution, creation/ownership references |
| Hooks/attachments/config | Full nft inventory, tc ingress/egress, XDP, flowtable/offload, forwarding, bridge-netfilter, proxy ARP/ND, доступные external FDs |

Для каждого source kind schema registry содержит **каждый** допустимый JSON
path, type/range/cardinality, meaning, evidence artifact reference и disposition:
`identity`, `structural`, `ordered_policy` или `observed_volatile`. Неизвестное
поле не попадает в catch-all `extra` и не пропускается. Реестр включён в profile
digest; его нельзя динамически расширить по проверяемому dump.

`observed_volatile` не означает игнорирование: поле typed, bounded, сохранено в
observation/raw hash и проверяется по отдельному допустимому transition rule.
Например bridge `hello_timer/tcn_timer/topology_change_timer/gc_timer` могут иметь
decimal representation; proposed decoder сохраняет exact finite decimal value
без binary-float округления. Это разрешение типа **только на этих registry
paths**, не разрешение floats для nft counters, handles или priorities. Timer
пока не имеет reviewed meaning/bounds — unknown; `gc_timer:178.16` из artifact
является test input, не универсальным operational threshold.

Expiry timers DHCP/RA, address lifetimes и dynamic FDB нельзя просто удалить из
сравнения. Для них нужны отдельные reviewed temporal bounds/monotonic rules;
изменение gateway/prefix/interface/flags не volatile. До registry/proof отсутствие
поддержки означает unknown, даже если такой traffic обычен на VDS.

Parser bounds первого proposed topology envelope: ≤1 MiB на raw document,
≤16 MiB aggregate, ≤256 documents, depth≤32; превышение — unknown. Более узкие
row/cardinality/field bounds задаёт signed source registry до parsing. Эти
лимиты — memory limits, **не** live time budget. Registry для полного ip/route/
RPDB/FDB пока не заполнен из artifacts; поэтому profile ещё не executable.

### 7.2. Нормализованный topology envelope

Обязательные records нового типа перечислены ниже. Все records typed и
immutable; `null`, пустой список и «источник отсутствует» — разные состояния.
Unobserved обязательное поле делает envelope incomplete и не даёт validated
`TopologyObservation2`. Dictionary произвольных неизвестных native attributes
не допускается: дополнительные **известные** attributes перечисляет exact
source registry и сохраняет с typed field IDs/provenance.

| Record | Обязательное содержание |
|---|---|
| `TopologyEnvelope2` | contract/profile/binding/context/epoch refs; capture descriptors; ordered namespace records; source coverage; graph digest; start/end fences; все uncertainty statuses |
| `Namespace2` | `NamespaceKey`, role host/runner/target, ownership reference, exact trusted peer/NSID mapping refs, полный links/addresses/routes/RPDB/bridge/attachments/config/FD inventory |
| `Link2` | namespace key, ifindex, ifname, kind, MAC/link type, MTU, flags/state, source presence markers; parent/master identity или **наблюдённое отсутствие**; peer identity+proof ref для veth; known typed options |
| `Address2` | parent link identity, family, literal address, prefix length, scope/flags, known lifetimes/broadcast/peer fields и их source refs |
| `BridgePort2` | parent bridge identity, port link identity, native master/name/index/link fields, flags/state/options и соответствующие ip/bridge capture refs |
| `VlanRow2` / `FdbRow2` | exact parent bridge/link, VLAN identity/range/PVID/untagged либо MAC/destination/flags/state/type; known typed attributes и reviewed transition id |
| `Route2` | namespace, family, table identity, source ordinal, type/prefix, output link/gateway/source/metric/protocol/scope/flags и **все присутствующие** supported selectors/nexthops/encap/expiry attributes; explicit presence для optional полей |
| `PolicyRule2` | namespace, family, source ordinal, priority, action/table, **все присутствующие** supported from/to/iif/oif/mark/mask/suppress/l3mdev selectors и presence flags |
| `Attachment2` | parent namespace/link/hook, kind, object/program identity, direction/priority, flags/offload state и trusted source ref; unsupported kind запрещён |

Links/addresses индексируются только после uniqueness checks. Routes/RPDB
сохраняют source order; сортировка ради equality запрещена. Для route order,
expiry или optional-field normalization нужны отдельные доказанные registry
rules; отсутствие поля не восполняется kernel default «по памяти». Табличные
имена, `default` prefix и named protocol values сохраняются native tokens до
отдельно approved token mapping, а не превращаются автоматически в guessed IDs.

Source coverage задаёт exact перечень обязательных captures для каждой роли,
включая host-only bridge/config sources и per-link attachment facts. Счётчик
успешных команд или supplied `complete=true` не заменяет совпадение этого перечня
с validated descriptor set. Raw bytes и per-field provenance позволяют проверить,
что normalized graph не скрывает реальные objects или selectors.

### 7.3. Алгоритм join без догадок

1. Зафиксировать namespace references и writer epoch; bracket captures identity
   checks до/после. Не считать `ip netns list` полным перечнем namespaces:
   unnamed process/FD-held netns требуют approved ownership/OS inventory.
2. Проверить complete capture set по manifest, schemas и raw hashes. Все links
   namespace индексируются по ifindex; ifname уникален внутри namespace.
3. Addresses join только по проверенному ifindex. Имя, MAC или единственный
   подходящий объект не заменяют отсутствующий индекс/namespace witness.
4. В bridge-port schema `master` name разрешается в **ровно один** bridge того
   же namespace из полного ip dump. Сверяются own port index/name и validated
   ip master association. Missing/ambiguous/conflicting references — unknown.
   `link:"if6"` нельзя преобразовать в доказанную peer identity простым parse.
5. Для veth сверить kind, reciprocal indices и exact peer namespace. Local NSID
   разрешается через capture-session mapping к trusted namespace FD. При
   отсутствии NSID требуется separately reviewed equivalent peer witness;
   запрещено угадывать namespace по совпадению MAC/ifindex или брать его из
   expected topology без readback.
6. Все VLAN/FDB rows привязать к существующим links/ports. Неизвестный MAC,
   неожиданный external port, offload flag или unsupported learning transition —
   unknown. Разрешённые dynamic rows описываются exact endpoint MAC/VLAN/port
   tuples и переходами, не wildcard «любой learned entry».
7. Routes сохраняют все значимые fields; RPDB сохраняет encounter order при
   одинаковой priority. Первый host profile запрещает ambiguous equal-priority
   rules. Table-name↔number resolution только через approved captured mapping;
   unknown alias, multipath/encap/action — unknown. Нет потери selectors в
   упрощённой tuple `(family,priority,table)`.
8. Собрать полный namespace/link/bridge/route/RPDB/attachment graph, сравнить с
   approved host profile и peer bindings. Extra objects остаются видимыми и
   вызывают refusal. Затем проверить freshness/epoch и только тогда выпустить
   typed `TopologyObservation2`.

Неполный bridge-only ip dump не становится полным graph добавлением полей из
fixture. Missing attachment/FD/config read не означает `none`/`false`.
Смена session/inode/ifindex/process generation запрещает продолжить baseline.

## 8. Профиль `dedicated-management-host-v2`

Это новый policy profile, не изменение текущего `expected_paths`. Desired
минимальный host graph: lo + **одна management NIC** + test bridge + два owned
host veth; runner/target — lo + один owned peer каждый. Exact names/indices/MAC/
addresses/namespace ownership в manifest, без hardcoded принятия `eth0` по имени.
Canonical bridge/port naming constraints сохраняются до отдельного binding
review. Extra interfaces/bridges/veth/netns из лаборатории не adopt и не скрывать.

| Область | Требование профиля |
|---|---|
| Management NIC | Exact role/identity; не bridge member, не test peer, не namespace-moved; нет bond/team/VRF/tunnel/macvlan/patch path к test bridge |
| Host routes | IPv4/IPv6 default/provider routes допускаются **только** как exact approved management entries с device/gateway/table/protocol/metric/source; не общий allow на любую host route |
| Host IPv6/RA | Все addresses/link-local/default routes видимы. Exact structural entries и reviewed expiry transitions; unsupported RA changes закрывают epoch, не пропускаются как noise |
| Test bridge/ports | Только two owned members, exact VLAN/FDB options и endpoint identities, никаких management/foreign ports, tc/XDP/flowtable/unknown offload |
| Runner/target routes | Нет default/external gateway/policy reroute; только утверждённые connected/local routes и RPDB. IPv6 peer addresses запрещены, кроме loopback, пока новый reviewed case не принят |
| Host test-side IPv6 | Первый proposed profile запрещает addresses/link-local routes на test bridge/host veth; допустимый набор здесь пуст. Наблюдённый laboratory layout этому условию не соответствует. Поддержка exact host-side IPv6 потребует отдельного profile revision с доказанным guard coverage; никаких automatic address changes или удаления rows |
| Forwarding/relays | Host IPv4/IPv6 forwarding и proxy ARP/ND отключены по approved per-host/per-interface config; bridge-netfilter profile exact; task/peers без network caps, daemon/host mounts/sockets и inherited external FDs |
| Firewall | Canonical bridge default-drop и прежние inet guards сохраняются. Management accept rule или новый target allow ради matching не добавляются |
| Другие writers | Только reviewed serialized installer/daemon/setup principals; config/sysctl/offload/roles или writer drift аннулируют epoch до publication |

### 8.1. Проверяемое разделение management/test paths

Одного отсутствия default route в runner недостаточно. Profile требует совместно:
exact L2 graph без management port; полную L3/RPDB graph без alternative paths;
bridge input/output/forward/prerouting default-drop и exact allow matches;
inet input/forward/output bridge-related guards; отсутствие routing/proxy/BPF/
offload/foreign hooks; ограниченные peer privileges и отсутствие inherited
sockets/privileged helpers. Совпадение IP/MAC не заменяет physical ingress port.

Management TCP/SSH проходит через существующий management path хоста и не
добавляется к test allowlist. Его безопасность/доступность проверяется отдельно
до mutations с out-of-band recovery. Никакое profile matching не разрешает
использовать management NIC для negative probes или менять её configuration.
Неизвестный provider/service route — unknown; адрес не обходится wildcard
правилом. Отсутствие runner→management path подтверждается моделью hooks/graph
и отдельно одобренными probes, а не одним successful SSH session.

### 8.2. Границы periodic snapshots

Полный graph доказывает только наблюдённое состояние в интервалах captures.
Он не исключает временные attach/revert, reset/restore, замену rules с возвратом
handles, FD transfer, краткую смену route/RPDB или privileged writer между ними.
Открытый namespace FD уменьшает PID/inode reuse ambiguity, но не аттестует
отсутствие mutations. Sequential dumps разных sources/counters не атомарны.

Для future claim необходимы OS permission facts, protected binaries/keys/config,
serialized writers и durable fencing до publication; root/daemon admin остаётся
TCB. Потеря контроля — unknown и epoch invalidation. TTL/DB lease/HMAC и две
равные observations этого условия не заменяют. `continuous_attestation=false`
и отсутствие lossless NFTRACE requirement сохраняются.

Standalone experiment использует отдельный typed `DedicatedLabBinding2` с real
namespace/port creation identities и **не имеет** Docker runtime authority.
Нельзя заполнять отсутствующие container/EndpointID/daemon fields фиктивными
значениями. Runtime binding потребует отдельного последующего composition review;
lab compatibility не доказывает isolation настоящего Docker Runner.

## 9. Точный compatibility round trip и terminal решения

1. Выбрать заранее approved contract/profile/compiler/semantic registry и
   canonical recipe v2. Независимо получить его graph, ordered rule catalog,
   expected counters/positions, sample plan и digests. Никакого v1 digest reuse.
2. Validate actual namespace binding и management-host preflight, полную source
   coverage, absence of foreign resources/hooks и наличие approved rollback.
   Неизвестная CT/raw representation остаётся pending proof, не assumption.
3. Compile exact native transaction. Только **отдельно approved experiment**
   допускает parser/check и exclusive installation owned bootstrap/active
   recipe. Durable intent до dispatch; rollback controller вне test namespaces.
   Без такого approval алгоритм заканчивается offline design/fixture stage.
4. Получить committed outcome/witness, independent full native JSON и complete
   topology captures. Lost/ambiguous apply — quarantine, без retry/adopt.
5. Decode nft с bounds/exact metadata/version checks. Построить полный keyed
   graph, сохранить per-chain encounter order и typed native expressions;
   counters вынести в rows без потери slots.
6. Применить только approved normalization registry. Для CT/raw требуется
   соответствующий reviewed proof; неизвестная representation даёт unknown и
   сохраняемый diagnostic artifact, не fallback comparison по тексту.
7. Проверить scoped uniqueness, ownership-derived installation binding, все
   epoch/generation refs, static graph equality, exact counter positions и
   full topology/profile match. Поля/objects не исчезают между этими стадиями.
8. Повторно проверить read interval/freshness/session/epoch/deadline/kill и
   integrity capture chain. Выпустить **только** `recipe_matched` diagnostic,
   либо immutable unknown с finite reason. Даже match не подтверждает bytes.
9. Только последующий separately approved measurement stage с accepted byte
   basis собирает все fresh before/events/after. Exact deltas/correlation/noise/
   terminal fences проверяются отдельно; late positive terminal не изменяет.

Lab JSON может пройти shape decoding и demonstrate scoped reuse, но
`tc_ct_lab/tc_strict_lab`, priorities −200/10, policy accept и неполная topology
обязаны отказать на canonical/profile стадии. Не использовать mutation tests
на исходно invalid lab policy как доказательство чувствительности validator:
нужен отдельно известный valid synthetic v2 baseline и впоследствии real
canonical round-trip fixture.

Предлагаемый terminal record содержит stage/result/reason, все approved digest
refs, raw/normalized/identity/catalog references, intervals и обязательные
limitations. Export≤65536 bytes, allowlist полей; нет raw packets/nft/stdout,
HMAC keys/signatures, arbitrary errors или trainee data. Overflow — отказ,
не truncation. Structured evidence и operator export — разные типы. Перенос
полного DTO вместо bounded export не является compatibility shortcut.

## 10. Инварианты, риски и finite fail-closed reasons

Все следующие reason names — **предлагаемые для нового v2 domain**. V1 finite
reasons не редактируются. Неизвестная ошибка закрывается в `evidence_invalid`,
без экспорта exception/stdout. На unknown circuit удерживается, новый instance
не импортирует чужой issued result как собственный.

| ID | Сохраняемый invariant / риск | Отказ v2 и критерий проверки |
|---|---|---|
| I1 | Exact versions/types/domains, отсутствие silent migration | `profile_mismatch`, `domain_rejected`; wrong version/schema/build, old receipt и bool-as-int не проходят |
| I2 | Full supplied data, bounded strict parsing | `readback_invalid`, `capture_incomplete`; unknown key/object, partial/duplicate/oversize input отвергаются |
| I3 | Exact static recipe и execution order | `recipe_mismatch`, `hook_order_unproven`; missing/extra/reordered rule, changed match/interface/priority/policy не принимаются |
| I4 | Никакого недоказанного semantic alias | `ct_semantics_unproven`, `raw_payload_representation_unproven`; другой operator/mask/VLAN/width требует review |
| I5 | Scoped handles + parent/position/generation | `identity_mismatch`, `generation_changed`; safe cross-scope reuse допускается, same-scope duplicate/перенос/replacement отвергаются |
| I6 | Ownership не следует из readback | `ownership_unproven`, `apply_outcome_unknown`; чужое имя/handle/digest не даёт adoption или cleanup |
| I7 | Counter-local attribution | `counter_layout_invalid`; moved/missing/shared/duplicate counter, counter-after-verdict и неверный nonterminal/terminal rule отвергаются |
| I8 | Exact monotonic all-counter deltas и fresh events | `counter_reset_or_wrap`, `delta_unexplained`, `packet_incomplete`; cumulative-only, noise, timeout или missing reply не становятся success |
| I9 | Real byte basis отдельно от fixture | `byte_accounting_unproven`; observed 60 не заменяет expected frame basis, numeric tolerance запрещён |
| I10 | Complete topology + management separation | `topology_unproven`, `management_path_unproven`; missing source, peer ambiguity, extra route/bridge/NIC/attachment/FD закрывают claim |
| I11 | Bounded measurement, irreversible terminal | `deadline`, `clock_rollback`, `killed`, `epoch_changed`; late/concurrent/replayed evidence не меняет выданный terminal |
| I12 | Нет snapshot→continuity/authority leap | `writer_control_unproven`; root/TCB assumptions явны, release=false даже при matched/fixture verified |

V2 не увеличивает молча v1 **2s** measurement window и не меняет live budgets.
Until new approved timing profile, measurement candidate сохраняет этот bound;
если полный capture не укладывается, результат unknown. Любое предложение иного
budget — отдельная измеренная policy revision. Journal/durable replay/kill
интеграция не наследуется от process-local verifier и требует отдельной задачи.

## 11. Малые этапы реализации и сценарии приёмки

Это предложения отдельных reviewable задач, **не реализация №20.1b-8a**.
Каждая задача сохраняет старые suites/gates; отсутствие нужных artifacts
закрывает соответствующий acceptance path, а не всю возможность offline work.

| Задача | Зависимости | Критерий приёмки | Причина fail-closed / что не входит |
|---|---|---|---|
| V2-01: typed schemas и scoped identity | Review разделов 2–5 | Новые exact types/domain; installation catalog; table8/rule8 и cross-table chain1 допускаются, duplicate rule handle между chains одной table/parent drift/epoch mismatch отвергаются | Нет v1 migration, installer или OS I/O; unknown parent/ownership не заполняется |
| V2-02: pure nft readback adapter | V2-01; immutable field/semantic registry | Native metainfo и grouping читаются; valid synthetic canonical graph сравнивается полностью; rules/expr order/positions сохраняются; unknown fields/operator/версии отказ | CT/raw без proof остаются unproven; это не kernel compatibility pass |
| V2-03: pure topology decoders и joins | Registry design; дополнительные real ip/route/RPDB/VLAN/FDB fixtures | Раздельные ip/bridge schema; decimal paths; deterministic complete graph, reciprocal namespace proof, source coverage и ambiguity tests | Missing source/peer field, unknown selector/expiry semantics — unknown. Collector не входит |
| V2-04: management-host profile validator | V2-03; exact proposed host manifest | Management NIC/defaults видимы и bounded; rogue bridge/port/veth/route/RPDB/attachment отвергаются; без новых allow rules | Real host profile ещё требует review; нельзя принять snapshot отсутствующего NIC или скрыть row |
| V2-05: offline regression fixtures | Для каждой части V2-01..04 после её schema review | Original hashes/provenance сохранены; valid synthetic v2 baseline явно отделён; mutation matrix ниже исполняется локально | Нет reconstructed before/after, data-driven schema widening или automatic physical tests |
| V2-06a: trusted read-only collector | V2-01..05, reader OS role/permission review | Fixed argv/source coverage, bounded transports, namespace/session/freshness checks; отдельный reader principal и malformed/partial-output tests | Нет installer или packet-send surface; неподтверждённый источник не становится empty inventory |
| V2-06b: installation ownership journal/witness | V2-01/05, serialized-writer review; independent captures V2-06a | Durable intent/dispatch/commit/unknown states, binding issuance только после committed ownership proof, restart/replay/kill/lost-response tests | Нет adoption по readback; unresolved commit остаётся quarantine. Не наследовать автоматически v4 journal semantics |
| V2-06c: dormant fenced installer/rollback boundary | V2-02..04, V2-06a/b; отдельный OS mutation-role review | Exclusive only-owned bootstrap/active transitions, exact batch/identity fences и serialized rollback/controller contract; offline fault tests | Новый versioned physical boundary, default OFF; lost response не retry. Нет Runner/Django composition |
| V2-07: native canonical round-trip experiment | V2-06a/b/c; exact отдельное VM/setup/mutation/rollback approval | Full canonical native snapshots, exact object/identity/position comparison, CT/raw normalization artifacts и stage timings | Lab final dump не подходит. Если native form неизвестна, STOP→review V2-02→новый approved run, не auto-fix |
| V2-07b: bounded fixed-packet collector/helper | V2-01/03/05/06a и успешный recipe review V2-07; packet-role review | Только compiled finite frames/owned namespace/interface; complete bounded send/ingress/reply events; checksums/context/loss/truncation и helper interruption tests | Нет arbitrary frames/URL/commands, caps/FD leakage или доступа к management path; physical send всё ещё требует отдельного approval |
| V2-08: byte accounting calibration review | V2-07/07b; отдельные approved frame/hook cases | Proof exact padding/VLAN/options/request/reply/skb basis и consistency limits; immutable accounting id | Difference с offline basis — unknown/new review, без tolerance и production sign-off |
| V2-09: controlled before/after measurements | V2-07/08, full topology/ownership/collector reviews | 15 fixed context probes, all-counter deltas, fresh packet events, noise/reset/extra-path/deadline faults, safe only-owned teardown/quarantine | Не входит live authority composition или снятие `PhysicalProbeGate`; они требуют отдельного будущего решения |

V2-03 может проектироваться независимо от V2-02; новые native fixtures добавляются
по мере получения, но acceptance не переходит через незакрытый prerequisite.
V2-07 — сбор доказательств в разрешённом эксперименте, поэтому несовместимый raw
AST не исправляется автоматически. Цикл artifact→offline schema review→new
explicit run ожидаем; successful canonical round trip не является prerequisite
для честного diagnostic failure первого такого опыта.

### 11.1. Обязательная offline mutation matrix будущих задач

| Группа | Positive fixture | Обязательные negative cases |
|---|---|---|
| Metadata/encoding | Exact native header, JSON keys/whitespace variants | Missing/duplicate/extra metadata, wrong build/schema/release, duplicate JSON keys, bool/float/overflow, size/depth limits |
| Object graph | Две допустимые группировки одного synthetic canonical graph с тем же per-chain order | Missing/extra table/chain/rule, dangling parent, competing hook priority, reordered **rules** или expressions |
| CT/raw | Observed `in` decode; separately approved predicate representation | `==` alias без proof, new вместо established, set/list/mask/related/negation; raw width/base/offset/endian/dependency/VLAN drift |
| Identity | Native cross-scope numeric reuse, stable generation/catalog | Same-scope duplicates, rule moved to other chain, table recreated/epoch drift, wrong expression index, forged ownership binding |
| Counters | Anonymous counter before exact verdict; nonterminal ingress | Counter before match/after verdict, named/shared/extra/missing slot; accept counter выдан за drop |
| Topology | Complete synthetic management profile и подтверждённые native schema fragments | Name/index ambiguity, wrong netns/peer, bridge-only вместо full links, unknown field, missing FDB/route/RPDB/tc/FD source, decimal outside approved path |
| Management | Exact visible NIC/default/provider routes с approved transitions | NIC enslaved to bridge, rogue veth/default route, altered gateway/table/mark, IPv6 bypass, XDP/tc/flowtable, hidden or unaccounted namespace |
| Measurement/lifecycle | Nonzero baseline + отдельно доказанные deltas; RST/SYN-ACK | Cumulative-only snapshot, fabricated before/after, background/extra bytes/counts, missing send/reply, reset/wrap, deadline/kill/replay, lost apply/read interruption |

Synthetic positives не маркируются native; native lab fixtures не маркируются
canonical. Real canonical positive fixture появится только после V2-07. Каждая
negative mutation должна отказать относительно valid baseline своей стадии,
а не пройти из-за уже invalid input на предыдущей стадии.

## 12. Открытые kernel вопросы и решение review

| Вопрос | Нужный artifact / проверка | До ответа |
|---|---|---|
| Как native round trip сериализует full canonical raw payload/dependencies? | Exact compiler transaction и kernel parser/readback на approved builds, frame/VLAN variants | `raw_payload_representation_unproven` |
| Как именно `in`/`==` оценивают CT state в required hooks? | Reviewed source/build semantics, masks/truth table и bounded positive/negative state cases, не только HTTP | No alias, `ct_semantics_unproven`; semantic recipe v2 требует нового approval |
| Какие handle scopes/allocators фактически используются для всех canonical objects? | Full two-table/multi-chain canonical dump, create/replace generation observations и reviewed source model | Консервативные scoped checks раздела 5; unsupported reuse — unknown |
| Есть ли дополнительные metadata/table/chain/rule fields и grouping? | Full canonical bootstrap/active dump без фильтрации, exact capture argv | Unknown field/order ambiguity — отказ, не registry auto-extension |
| Как выглядят все ip port/peer/NSID/address/route/RPDB/VLAN/FDB fields? | Full host/runner/target captures на exact iproute2 builds и независимые namespace/peer references | Topology profile не executable; bridge-only snapshot недостаточен |
| Какие DHCP/RA/FDB/timer изменения допустимы без structural drift? | Последовательные raw no-send captures, build-specific units и reviewed transition bounds | Не удалять fields; unsupported transition — unknown |
| Как обеспечить management path и exclusive writer/FD control на dedicated VM? | Full host OS/permissions/setup manifest, namespace/FD/attachment inventory, rollback/recovery review | Нет physical acceptance, даже при равных graphs |
| Как учитываются bytes и насколько согласованы dumps counters? | Controlled per-hook before/after и packet captures с padding/options/VLAN/offloads; reset/noise faults | `byte_accounting_unproven`, не переносить cumulative totals |
| Выполним ли capture в существующем bound? | Stage и end-to-end monotonic timings отдельно approved run | Deadline unknown, без скрытого budget increase |
| Как доказать commit/ownership после потерянного apply response? | Separately reviewed durable transaction witness и faults | Quarantine; readback не даёт adoption |

Эти вопросы блокируют соответствующие implementation/physical acceptance stages,
но не review спецификации: для каждого неизвестного случая здесь определён
отказ и источник будущего proof. Реальные сборки, schemas и semantics не
объявлены принятыми. Любой новый профиль проходит отдельный versioned review.

### 12.1. Проверка документа и завершение №20.1b-8a

Выполнен локальный review разделения стадий, отсутствия CT alias без proof,
scope/parent/ordinal/epoch checks, запрета adoption и completeness topology.
Проверены 12 invariants с finite refusal reasons и 12 отдельных задач с
dependencies/acceptance; для native unknowns явно определены proof obligations.
Полнота спецификации не означает принятие ещё не заполненных source registries.

Проверены Markdown links, fenced blocks, нумерация 12 разделов и whitespace.
SHA-256 **161 существовавшего artifact** шести packages Trusted Checker
(без caches) и прежних `TRUSTED_CHECKER*.md` совпали с manifest
`/tmp/task201b8a-baseline.json`; все пять original native files также сохранили
hashes из provenance. Добавлен только этот design. Tests в №20.1b-8a не
создавались и не запускались: production/test code не менялся. Предыдущие 602
tests остаются результатом №20.1b-7b, а не validation v2 implementation.

**`DESIGN READY FOR REVIEW`**: определены версии и стадии, exact schema и пределы
нормализации, scoped identity/ownership, full topology/management profile,
invariants/reasons, независимые задачи и открытые proof obligations. Это не
`READY FOR PHYSICAL TEST`, не live activation и не security sign-off. Ни один
physical gate или runtime guard этим документом не изменён.
