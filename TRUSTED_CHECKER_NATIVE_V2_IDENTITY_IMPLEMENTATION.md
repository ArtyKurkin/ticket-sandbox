# Trusted Checker: Native v2 Typed Contracts & Scoped Identity — №20.1b-8b

20 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-01 OFFLINE READY`.** Реализованы отдельные immutable contracts v2, scoped
handles, canonical catalog и чистая структурная проверка installation intent/
binding по [утверждённому design](TRUSTED_CHECKER_NATIVE_COMPATIBILITY_V2_DESIGN.md).
**680 tests, failures=0, errors=0, skips=0**. Из них 78 новых offline tests;
прежние 602 сохранены и выполнены заново.

Ни один объект v2 не является verification/ownership authority. Любой binding
этого этапа — **offline candidate с неподтверждённой установкой**, не confirmed
physical installation. Kernel compatibility остаётся непроверенной; итог
[аудита](TRUSTED_CHECKER_KERNEL_COMPATIBILITY_AUDIT.md) `NOT READY` не изменяется.
Shadow-only, `PhysicalProbeGate` и `physical_network_boundary_not_accepted`
сохранены. SSH/VDS, nft/ip/Docker/setns/packet operations, deploy и учебные
изменения не выполнялись. Commit/push/rebase также не выполнялись.

## 1. Новые файлы и независимость от v1

| Файл | Содержание |
|---|---|
| [`native_v2_contracts.py`](trusted_checker_network/native_v2_contracts.py) | Все новые DTO, deterministic canonical ID helpers, pure binding validators |
| [`native_v2_support.py`](trusted_checker_network/tests/native_v2_support.py) | Явный synthetic v2 baseline без v1 compiler/runtime/daemon; отдельные test-only fixture builders |
| [`test_native_v2_contracts.py`](trusted_checker_network/tests/test_native_v2_contracts.py) | 78 offline unittest: positive/mutation, native identity shape, import/AST isolation |
| [`TRUSTED_CHECKER_NATIVE_V2_IDENTITY_IMPLEMENTATION.md`](TRUSTED_CHECKER_NATIVE_V2_IDENTITY_IMPLEMENTATION.md) | Этот отчёт |

Нового package, installer, reader, collector, parser, runtime coordinator или
подключения к Django/Ticket Sandbox нет. Existing `counter_contracts.py`,
`counter_rules.py`, `counter_readback.py`, approvals/bindings/ownership boundaries,
v2 design и все прежние tests/fixtures не редактировались.

Новый production module импортирует **только stdlib**: dataclasses, hashlib,
json для `dumps`, re и UUID validator. Нет зависимости от v1 DTO, runtime
approval, Docker/Django, physical package или OS I/O. `json.loads/load`, native
readback parsing и generation UUID отсутствуют. Публичного dict importer нет.

## 2. Архитектура contracts

Общая frozen/slotted metadata: `tc-native-compatibility-v2`, integer version 2,
method `nft_counter_probe_v2`, domain `tc-nft-counter-probe-v2-offline`, origin
`offline_native_compat_fixture`. Metadata каждого вложенного DTO проверяется
заново при включении в aggregate. Exact types обязательны; subclasses,
lookalike dictionaries и старые approvals не принимаются.

| DTO | Что фиксирует |
|---|---|
| `NamespaceKey2` | Host boot UUID, positive netns inode, reader session UUID, positive namespace binding generation |
| `InstallKey2` | New approval digest/context UUID, binding digest, writer/install epoch UUID, install generation |
| `TableIdentity2` | Namespace/install keys, family/name и table handle |
| `ChainIdentity2` | Exact parent table, chain name/handle/type/hook/priority/policy |
| `RuleIdentity2` | Exact parent chain, handle, canonical rule ID, ordinal и static expression digest |
| `CounterSlot2` | Exact parent rule, canonical counter ID, expression position, purpose и explicit probe ID либо None |
| `CanonicalTableSpec2` / `CanonicalChainSpec2` | Trusted expected parent paths, chain attributes и explicit rule counts |
| `CanonicalRuleSpec2` | Expected path/ID/ordinal, static expression digest, expression count, counter position/purpose/probe |
| `CanonicalRuleCatalog2` | Immutable tuples всех expected specs, recipe digest и полный набор допустимых probe IDs |
| `OfflineApproval2` | Отдельный fixture approval input: approval/context UUID, offline-only scope, recipe/catalog/binding/native/topology profile digests |
| `InstallIntent2` | Exact new approval, namespace/install keys/catalog, transaction UUID, explicit creation-record reference; только `exclusive_create_only` |
| `WitnessReference2` | Неподтверждённая ссылка: intent/install-key/transaction refs и reference digest; **не committed witness** |
| `InstallationBinding2` | Intent/witness/readback reference и полный native identity/counter catalog; только offline structural candidate |

`OfflineApproval2` не подписан, не получен от v1 signer и не удостоверяет, что
operator что-либо разрешил на OS. Он используется только как отдельный trusted
fixture input. `authentication="not_authenticated"` обязательно у всех DTO;
новый domain отделяет типы/content digests, **HMAC service не реализован**.
Profile digests здесь проверяются как точные ссылки, не как принятые native
semantic/topology profiles.

UUID должны быть canonical lowercase strings и non-nil; обязательные UUID
нельзя опустить или заменить автогенерацией. Digests — ровно 64 lowercase hex.
Handles/inodes/generations — exact integers `[1,2**63-1]`; priorities — signed
32-bit integers. Ordinals `[0,127]`, counter positions `[0,63]`, expression count
`[1,64]`. Bool/float/string не приводятся к integer. Tuples ограничены; catalog
содержит не более 128 table+chain+rule objects, probe IDs не более 15.

Изменение полей frozen объектов запрещено, вложенные containers — tuples,
parents — exact frozen DTO. Нет mutable dict/list payload. Стандартная Python
immutability не является защитой от произвольного исполнения кода внутри TCB.

## 3. Точные scope и коллизии

Все identities binding обязаны иметь ровно namespace/install keys его intent.
Поэтому uniqueness проверяется внутри одного exact namespace/install instance:

| Объект | Scope |
|---|---|
| Table handle | family + kind table; также unique `(family,name)` |
| Chain handle | family + parent table + kind chain; также unique chain path |
| Rule handle | family + parent table + kind rule **во всех chains table** |
| Counter | Один exact canonical slot каждого rule; shared/duplicate/missing slot запрещён |

Сохраняется дополнительный conservative design guard: chain/rule handle collision
внутри одной table запрещён, пока нет отдельного identity review. Table handle
не входит в этот chain/rule numeric namespace.

Следовательно table handle **8** и rule handle **8** в этой table допустимы;
chain handle **1** в разных tables допустим. Также допустим одинаковый rule
handle в разных tables одной family. Повтор rule handle в разных chains одной
table — `v2_scope_collision`, даже при различных chain names.

Numeric handle никогда не используется как глобальный lookup key. Тип объекта
задан exact DTO type; family/table/chain/install/namespace входят в ссылки.
Имена/comment/label не заменяют parent identity, ordinal и static digest.

## 4. Catalog, parent/ordinal/epoch и exact mapping

`canonical_rule_id2` детерминированно хеширует новый domain, family/table/chain
path и ordinal. Handles, native global object index, labels и v1 IDs в него
не входят. `canonical_counter_id2` дополнительно связывает rule ID, expression
position, purpose и probe ID. Это content-derived compiler IDs, не случайные
или автоматически подставляемые UUID. UUID inputs по-прежнему обязательны.

Catalog строится из **typed trusted specs**, не из supplied native JSON. При
конструировании проверяются все parent references, unique paths/IDs, отсутствие
конкурирующих `(family,hook,priority)`, rule count и последовательные ordinals
каждой chain в encounter order. Known probe IDs точно соответствуют используемым
ссылкам; unknown/unused IDs отвергаются. Drop-only catalog может явно передать
пустой probe tuple. Никакая missing ссылка не дополняется из expected data.

Placement проверяется структурно: ingress counter — последний statement без
verdict; allow/terminal/guard — предпоследний; fallback counter — позиция 0
при двух statements. Actual expressions/verdict здесь **не разбираются**:
catalog содержит trusted static digest и declared expression count. Проверка
самого AST и semantic recipe остаётся V2-02; набор в 49 rules/15 probes этим
фундаментом не объявляется скомпилированным или проверенным.

Intent independently pins exact recipe/catalog digests новым approval, а также
approval/context/binding refs install key. Binding требует exact counts и
соответствие всех table/chain/rule/counter rows каталогу. Parent должен быть
именно зарегистрированным typed identity, а не объектом с тем же name/number.
Порядок catalog rules и mapping rows не сортируется ради совпадения.

Подмена parent/ordinal со старым canonical ID даёт path mismatch. Согласованная
подмена ID/path/static digest отвергается при сравнении с pinned catalog.
Смена counter position/purpose/probe вместе с пересчитанным ID также не проходит
catalog compare. Old namespace/session/boot/writer/install epoch/generation в
части графа не совпадёт с intent.

Два pure API имеют разные обязательные expected inputs:

- `validate_binding2(binding, expected_intent)` проверяет структуру и соответствие
  **отдельно переданному** current trusted fixture intent. Новый generation,
  epoch, context или reader session отвергает старый binding с `v2_stale_binding`.
- `validate_same_installation2(binding, expected_binding, expected_intent)` также
  сравнивает с отдельно pinned complete installation description. Согласованная
  перезапись всего графа с новыми handles не проходит (`v2_installation_changed`).

Конструирование второго согласованного **unproven offline candidate** с иными
handles допустимо; это не признание continuity прежнего binding. Caller не
должен выбирать expected intent/binding из проверяемого input. Stateful replay
journal, single-use issuance, TTL, clocks и durable fences здесь отсутствуют.
Одинаковые значения под тем же intent проверяются идемпотентно и **не выдают
новое разрешение**. Защита от повторного физического dispatch — будущая V2-06b/c.

## 5. Ownership и witness: что здесь намеренно невозможно

`InstallIntent2` лишь описывает future exclusive creation. Creation-record
digest — **ссылка**, не durable creation proof. Конструирование DTO не выполняет
transaction и не записывает intent в журнал.

`WitnessReference2` требует явных digest/transaction refs, связанных с точным
intent и install key. Но его единственный допустимый status —
`unverified_reference`. Реального trusted committed witness пока нет. Нельзя
передать `confirmed`/`committed`, старый trace/dictionary вместо нового type
либо пропустить witness и получить успешную подтверждённую установку.

`InstallationBinding2.status` всегда
`offline_structure_bound_ownership_unproven`. Все records требуют:

```text
authentication = not_authenticated
ownership_proven = false
physical_probe_permitted = false
continuous_attestation = false
trace_delivery_complete = unproven
```

True, integer 0/1 вместо bool false, иные origins/domains/versions и попытка
пометить fixture authenticated/confirmed отвергаются. Даже если witness reference
digest совпадает с readback hash, ownership остаётся false: hash не превращается
в transaction witness. Raw readback не принимается никаким production API этого
модуля; нет функции синтеза committed witness из него.

Будущим ownership evidence будет отдельно reviewed authenticated committed-
transaction witness, связанный с pre-dispatch durable exclusive-create intent,
writer epoch, exact namespace/install generation и independent readback. Его
issuance/type/domain/OS roles ещё не реализованы и **не могут быть активированы
флагом этого DTO**. Потребуется отдельный новый boundary review.

Table name, handle, recipe/static digest, fixture source label, ordinary content
digest и данный offline approval **не являются ownership evidence**. Root/TCB
reset/recreate/restore между snapshots не исключается identities. Нет adoption,
delete/cleanup authority или kernel continuity claim.

## 6. Сохранённые fail-closed инварианты

Validation поднимает `ContractViolation2` с finite static `v2_*` reason; в сообщении
нет supplied JSON/errors/packet content. Constructor с отсутствующим/неизвестным
полем также отказывает стандартным TypeError, без default recovery.

| Invariant | Реализация и regression |
|---|---|
| I1 | Exact new version/domain/method/origin/type; v1/runtime/network approvals и v1 HMAC domain отвергаются; нет fallback/conversion |
| I5 | Scoped uniqueness и full parent/ordinal/static digest/position/install/namespace matching; pinned same-installation compare |
| I6 | Witness всегда unverified, ownership=false; нет confirmation/dict-import/adoption или dispatch port |
| I7 | Один counter slot на rule, exact position/purpose/probe/canonical ID и parent catalog; missing/shared/extra/reordered rows отвергаются |
| I12 | Все DTO offline-only и unauthenticated, physical/continuous flags false; existing PhysicalProbeGate отвергает новый binding |

Повторные checks вложенных DTO не принимают subclasses или объект старого
domain, даже если у него похожие поля. Pure content digests domain-separated,
но сами по себе не удостоверяют trusted источник catalog; trusted setup
остаётся явной предпосылкой. Внешний untrusted input должен пройти будущий
отдельный authenticated boundary, а не получить authority из type construction.

## 7. Тесты и native fixtures

78 новых tests используют valid synthetic v2 baseline, независимо проверенный
в setUp. Synthetic five-rule catalog проверяет identity foundation и не
называется full canonical recipe. Отдельный drop-only positive проверяет
явно пустой probe set. Mutation tests начинаются с валидного baseline и
отвергают причины соответствующей стадии.

Покрыты scoped reuse/collisions, отсутствующие/extra/неверные parents, coherent
rewrite handles/IDs, ordering, static digest, counter position/purpose/probe,
missing/duplicate slots, epoch/generation/session/context drift и stale binding,
mutable containers, bool/numeric/UUID/digest bounds, domains, authority flags,
unverified witness, dict/subclass mixing, frozen/slots и gate isolation.

Тест реальной формы читает **только оригинальный fixture**
[`nft_ruleset_final.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/nft_ruleset_final.json),
проверяет SHA-256 по provenance и извлекает table handles **6/8**, chain handles
**1/1** и strict rule handle **8**. Только эти observed numbers переносятся в
**отдельный synthetic catalog с двумя разными bridge tables**. Laboratory names,
policies, expressions и cumulative counters не считаются approved recipe или
installation evidence. Оригинальные artifacts не изменены; before/after не
реконструировались.

AST test нового production module подтверждает stdlib-only imports и отсутствие
parser/I/O/UUID generation calls. Fresh Python import запрещает socket/Popen/
setns и проверяет отсутствие v1/runtime/Docker/Django imports. Этот subprocess
запускает только локальный Python, без daemon/network operations.

На первом запуске один negative test ожидал parent mismatch, но его mutation
раньше создавал scope collision и получал корректный отказ. Test изменён так,
чтобы отдельно проверять parent identity mismatch. Security guards не ослаблены.
Финальный полный прогон включает дополнительные shared-counter и drop-only tests.

## 8. Полный прогон Trusted Checker

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
| Network: прежние 176 + новые 78 | 254 | 0 | 0 | 0 | OK, 37.195s |
| Physical | 90 | 0 | 0 | 0 | OK, 13.362s |
| Live | 48 | 0 | 0 | 0 | OK, 13.788s |
| Runtime | 66 | 0 | 0 | 0 | OK, 11.825s |
| Shadow | 56 | 0 | 0 | 0 | OK, 2.860s |
| PoC | 166 | 0 | 0 | 0 | OK, 14.159s |
| **Всего** | **680** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0, без ResourceWarning. Логи:
`/tmp/task201b8b-{network,physical,live,runtime,shadow,poc}.log`.
Suites выполнялись независимо/частично параллельно; timings не benchmark.
Это полный Trusted Checker run, не полный прогон Django приложений.
Django regressions не запускались, application writers не менялись.

## 9. Целостность прежних artifacts и source manifest

SHA-256 всех **162** существовавших до задачи artifacts шести Trusted Checker
packages (без caches) и прежних `TRUSTED_CHECKER*.md` совпали с baseline
`/tmp/task201b8b-baseline.json`. Включая v1 code/tests, design, native fixtures,
physical gates, live adapter и прежние reports. Добавлены только три Python
файла и этот отчёт. Проверены syntax/AST, Markdown links, fences и whitespace.

Вычисляемый physical source manifest включает все top-level network Python
modules, поэтому **новый файл меняет digest**, хотя прежние файлы неизменны:

- до: `497c06dc4901e5a4b871ac4f28c3d7de92e087a20a7ded46ab6d5862e59cc2cc`;
- после: `2c0097c13fdfef03700729f21cfc1a37593fa7dcdcfd7c006afe7618ab6a5cad`.

Никакие old physical approvals не обновлялись и не переносятся автоматически.
Protected manifest/gates не редактировались для прохождения checks. Рабочие
БД, `.env`, credentials и Docker sockets не читались и не менялись.

## 10. Ограничения и следующий V2-02

V2-01 проверяет **typed structure и consistency доверенных fixture inputs**.
Он не подтверждает schema/recipe semantics или фактическую установку. Labels
`trusted_offline_specification`/`OfflineApproval2` — не signatures и не proof
OS permissions. Static expression digests supplied trusted specs не сверяются
с native AST на этом этапе. Full 49-counter/15-probe recipe compiler отсутствует.

Для V2-02 нужны отдельные pure native decoding/normalization/recipe-validation
types и tests: strict metadata/version/schema, grouping с сохранением per-chain
rule order, полный static compare и использование **pinned** scoped identities
этого foundation. Unknown fields/representations должны давать отказ; CT `in`
и raw payload не получают equivalence proof от данного DTO.

Topology/management profile, authenticated collector, trusted committed witness,
durable ownership/replay/kill, native canonical round trip, real byte accounting
и controlled before/after остаются отдельными задачами. Ни stateless validator,
ни одинаковые content hashes не заменяют их.

**`V2-01 OFFLINE READY`** не означает physical compatibility, разрешение VDS
операций или live activation. Все physical gates остаются закрытыми.
