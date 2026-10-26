# Trusted Checker: Native v2 nftables Readback Adapter — №20.1b-8c

20 октября 2026 · база Git `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`V2-02 OFFLINE READY`.** Добавлены pure bounded JSON decoding, нормализованный
nft graph и полное сравнение с независимо заданными typed expected expressions,
catalog и pinned installation binding. **760 tests, failures=0, errors=0,
skips=0**, включая 80 новых tests и прежние 680.

`recipe_matched` означает только **offline structural match**. При CT/raw даже
точно совпавший graph получает `recipe_unproven`; никакой semantic proof
не предполагается. Measurement/topology/byte accounting/ownership не приняты,
`physical_probe_permitted=false` у всех стадий. Итог physical audit `NOT READY`
не меняется. V1, V2-01 contracts и прежние gates сохранены без изменений.

SSH/VDS, nft/ip/Docker/setns/packet operations, physical subprocess, installer,
collector, deploy, Django/Ticket Sandbox, Ledger/учебные transitions не
выполнялись и не добавлялись. Shadow-only, `PhysicalProbeGate` и
`physical_network_boundary_not_accepted` остаются закрытыми. Commit/push/rebase
не выполнялись.

## 1. Файлы, типы и API

| Новый файл | Назначение |
|---|---|
| [`native_v2_json.py`](trusted_checker_network/native_v2_json.py) | Bounded tokenizer/recursive descent decoder exact bytes → temporary Python JSON values |
| [`native_v2_readback.py`](trusted_checker_network/native_v2_readback.py) | Typed expressions/native objects, profile/context, три стадии, expected AST и full comparison |
| [`native_v2_readback_support.py`](trusted_checker_network/tests/native_v2_readback_support.py) | Независимый synthetic expected AST/catalog и test-only renderer JSON |
| [`test_native_v2_readback.py`](trusted_checker_network/tests/test_native_v2_readback.py) | 80 offline tests parsing/graph/validation/semantics/native fixtures/isolation |
| [`TRUSTED_CHECKER_NATIVE_V2_READBACK_IMPLEMENTATION.md`](TRUSTED_CHECKER_NATIVE_V2_READBACK_IMPLEMENTATION.md) | Этот отчёт |

Новый package не создан. Использованы exact immutable identities, guards и
content-digest domain из
[`native_v2_contracts.py`](trusted_checker_network/native_v2_contracts.py),
сам файл V2-01 не редактировался. Production modules используют только stdlib
и новые offline v2 modules; нет I/O, discovery, signing, live/runtime conversion
или вызовов v1 compiler/parser.

| API / тип | Гарантия |
|---|---|
| `NativeFormatProfile2` | Exact nft `1.0.9`, release `Old Doc Yak #3`, JSON schema integer `1`, profile `nft-1.0.9-json1-v2`; explicit binary digest reference |
| `ReadbackContext2` | Namespace/install keys и profile/binary digest refs; только unauthenticated offline context |
| `decode_native2(raw, profile, context)` → `DecodedNative2` | Bounded JSON/schema/expression decoding; metainfo проверен; source order и numeric rows сохранены; **не** parent graph/recipe match |
| `normalize_rules2(decoded)` → `NormalizedRules2` | Полный table→chain→ordered-rules graph, scoped uniqueness, declared parents и hook ambiguity checks |
| `ExpectedRuleExpressions2`, `ExpectedRecipe2` | Независимый trusted expected AST, связанный с V2-01 catalog/intent/profile; layout/static digests/recipe digest перепроверяются |
| `static_expression_digest2` / `expected_recipe_digest2` | Domain-separated typed AST/recipe content digests; не authenticity или ownership |
| `validate_recipe2(normalized, expected, pinned_binding, expected_intent)` → `ValidatedRecipe2` | Полная structural comparison, отдельно заданный current intent и pinned mapping; result `recipe_matched` либо `recipe_unproven` |

Все DTO frozen/slotted, с inherited offline domain/version/limitations.
`DecodedNative2.metainfo` сохраняет exact проверенные header values через
immutable profile; `objects` содержит policy objects без metadata header.
Raw digest/byte count сохраняются отдельно. Никакие unknown metadata fields
не отбрасываются: они отклоняются до создания decoded DTO.

Profile/context binary digest — явные fixture references, **не проверка файла
binary на host**. Совпадение с metainfo не доказывает build provenance. Capturing
real stdout, signatures, observation timestamps/freshness и OS principals здесь
не реализованы; принадлежность source остаётся за future collector review.

## 2. Bounded decoding и точный предел защиты

Input — exact `bytes`, не str/bytearray/stream. `0 < size <= 262144` проверяется
**до** UTF-8 decode; BOM и invalid UTF-8 отвергаются. В памяти уже может
находиться input caller: adapter не управляет allocation до своего вызова.

Вместо `json.loads` реализован собственный bounded decoder. Он сканирует
переданный ограниченный buffer и проверяет limits по мере разбора:

| Limit | Enforcement |
|---|---|
| Depth ≤32 | Корневое value имеет depth 1; child value проверяется до его container allocation. Object keys не добавляют уровень вложенности |
| Nodes ≤32768 | Каждый value/container и object key расходует node; проверка до разбора/добавления следующего node |
| Nft objects ≤128 | Все элементы root `nftables`, включая metainfo; проверка до разбора следующего элемента |
| Expressions/rule ≤64 | `expr` array ограничен до разбора следующего statement |
| String ≤256 decoded UTF-8 bytes | Escapes/surrogate pairs проверяются по мере сканирования, limit до удержания следующего decoded character; нет неограниченного string accumulator |
| Integer token | Не более 19 decimal digits до `int()`, затем signed 64-bit range; field-specific bounds после decoding |

Temporary UTF-8 text ограничен input cap, tree — bytes/nodes/depth/string bounds.
Python object overhead/пиковый RSS не объявляются равными 262144 bytes. Нет
заявления о stream-level transport limits, atomic snapshot или live deadline.
Parser CPU/memory ограничены фиксированными input/tree bounds; resource benchmark
и kernel timing этим этапом не выполнялись.

Duplicate keys обнаруживаются после decoding keys, включая escaped-equivalent
имена. Floats, exponent notation, NaN/Infinity, oversized integers, leading-zero
numbers и malformed/trailing input отвергаются. В закрытой nft grammar нет
boolean-valued fields, поэтому `true/false` отвергаются целиком; bool-as-int
невозможен. JSON null принимается только как значение, а schema допускает его
для verdict. Unicode surrogate pairs поддерживаются, unpaired surrogates и
invalid/control characters отвергаются.

Generic bounded JSON tree — внутренняя стадия, не schema acceptance. Например
неизвестный root field сначала ограниченно разбирается, затем отвергается;
tree construction при этом всё равно ограничено aggregate/node/depth limits.
Это не универсальный RFC JSON decoder: bool и floating point намеренно вне
данного профиля.

## 3. Exact native object grammar

Root: ровно `{"nftables": [...]}`. Ровно один `metainfo`, только первый.
Metadata keys — ровно `version/release_name/json_schema_version` с exact profile
values. Нет semantic version ranges или profile discovery из input.

| Native object | Exact keys |
|---|---|
| table | `family,name,handle` |
| base chain | `family,table,name,handle,type,hook,prio,policy` |
| rule | `family,table,chain,handle,expr` |

Family только bridge/inet; names по V2-01 ASCII name validator. Handles integers
`[1,2**63-1]`; chain type filter, supported hooks prerouting/input/forward/output,
signed 32-bit priority, policy accept/drop. Типы native object разрешают
laboratory priorities/policy **для format audit**; canonical comparison
обязана отвергнуть их, если они не совпадают с expected.

Unknown keys/kinds, extra metadata, transaction wrappers `add/create/delete`,
sets/maps/flowtables, arbitrary objects, supplied `validated/recipe_digest/
expected_rules` не принимаются. Нет ignored metadata, index/position/use fields
или dynamic schema widening ради конкретного dump.

## 4. Typed expression grammar

| Node | Поддерживаемая форма |
|---|---|
| `Match2` | Exact `match` keys left/op/right; op `==`, для `Ct2` также `in`; scalar right строго по reference type |
| `Meta2` | key iif/oif → positive integer; iifname/oifname → ASCII interface literal ≤15 chars; l4proto → tcp/udp/icmp/ipv6-icmp |
| `Payload2` ether | type → ip/arp/ip6; saddr/daddr → exact lowercase MAC |
| `Payload2` ip | saddr/daddr → canonical IPv4 string; protocol → tcp/udp/icmp; frag-off → uint16 |
| `Payload2` tcp/udp | sport/dport → uint16; canonical port restrictions проверяются expected AST, не scalar parser |
| `Payload2` arp | operation → request/reply; saddr ether → lowercase MAC; saddr ip/daddr ip → canonical IPv4 |
| `Ct2` | Exact key state; scalar new/established; нет set/list/mask/related/negation aliases |
| `FragmentMask2` | Exact `&` list из двух элементов: ip frag-off reference + uint16 mask, match right uint16 |
| `AnonymousCounter2` + `CounterNumbers2` | Exact counter packets/bytes integers `[0,2**63-1]`; numeric rows отдельно от static counter node |
| `Verdict2` | Отдельный `accept:null` либо `drop:null`; единственный verdict только последним statement |
| `RawPayload2` diagnostic | Exact payload base/offset/len, base ll, integer offset≥0, length 1..128, lowercase `0x` literal 2..254 hex digits; **без утверждения units/width/endian compatibility** |

Нужные current recipe reference types поддержаны, но native normalized форму
каждого поля на kernel этот этап не доказывает. Unsupported operator/reference/
literal, nested unknown field и duplicate/named counter дают finite refusal.
Число anonymous counters в format rule — 0 или 1: native ARP rules без counters
декодируются, но catalog, требующий counter на каждом rule, не сможет их принять.

Nonterminal counter rule разрешён как формат. При recipe validation он должен
точно совпасть с independently declared ingress catalog entry. Counter перед
match сохраняет свою позицию и не совпадёт с expected layout; counter после
verdict отвергается уже на decoding. Никакой counter сам по себе не drop proof.

Raw branch — constrained **syntactic diagnostic**, не approved kernel semantic
representation. Unknown base/shape/literal даёт
`v2_raw_payload_representation_unproven` либо finite type/bounds error.
Даже accepted raw shape при exact structural match возвращает `recipe_unproven`.
Leading zeros/hex integer/bit widths/offsets не приводятся к другой форме.

## 5. Нормализация и scoped identities

Normalizer требует table declaration до chain и chain до rule. Поддержаны
table→chain→rules native grouping и все table/chain declarations перед rules.
Dangling references, duplicate declarations и competing `(family,hook,priority)`
дают отказ. Все объекты учитываются, включая extra/empty tables/chains.

Для deterministic graph representation сортируются **только table/chain map
keys** после проверки uniqueness/полного inventory. Source rule sequences внутри
каждой chain и expression arrays не сортируются, не коммутируются и не
дедуплицируются. Ordinal выводится из per-chain encounter order. Global serialized
object index identity не образует. `NormalizedRules2` повторно строит graph из
decoded input при проверке constructor, поэтому нельзя молча удалить table из
предоставленного normalized tuple.

Использованы V2-01 `NamespaceKey2`, `InstallKey2`, `TableIdentity2`,
`ChainIdentity2`, `RuleIdentity2` и pinned `CounterSlot2` catalog. Uniqueness:
table handles в family; chain handles в parent table; rule handles **во всех
chains одной table**. Дополнительно сохранён conservative chain/rule collision
guard внутри table. Table handle 8/rule handle 8 допустимы; chain 1 в разных
tables допустим; same-family duplicate table/rule scope — отказ.

Native paths/ordinals создают candidate canonical path IDs, но это не admission
в canonical recipe: IDs/parents/handles/static expressions сравниваются с
независимыми catalog и pinned binding. Namespace/session/epoch/generation из
explicit offline context должны точно совпасть с expected intent. Readback не
создаёт новый `InstallationBinding2` и не выдаёт ownership по name/handle.

## 6. Независимый expected recipe и полное сравнение

Expected AST строится trusted fixture setup **до** renderer/input parsing.
Production API преобразования native input в trusted expected не добавлен.
`ExpectedRecipe2` перепроверяет:

- exact intent/profile refs, rule IDs/count/order и declared expression counts;
- static digest из полного typed expected AST;
- единственный counter на точной позиции из catalog;
- ingress без verdict, allow с accept, terminal/guard/fallback с drop;
- recomputed semantic recipe content digest из table/chain/rule specs, probe
  refs и **всех expected expressions**, без native handles или numeric values.

Validation затем независимо сравнивает полный graph: exact table/chain sets,
полные parent identities с family/hook/priority/policy/handles, per-chain rule
ordinals/IDs, **все ordered typed expressions**, static digests и counter slots.
Один supplied digest или installer `verified=true` не заменяет AST comparison.
Пинning recipe и handles берётся из отдельных arguments, не из tested JSON.

Catalog этого synthetic positive fixture содержит пять rules; проверяются
**все** его objects/expressions/slots. Он не выдаётся за будущий production
49-counter/15-probe recipe compiler или approved real installation. Полный
kernel round trip канонического рецепта по-прежнему отсутствует.

`==` и `in` остаются разными CT operators. Смена operator отвергается как AST
mismatch. Если CT AST совпадает целиком, всё равно `recipe_unproven` /
`ct_semantics_unproven`: accepted proof registry отсутствует для обоих operators.
Raw match аналогично unproven; если есть оба blockers, primary reason raw, CT
при этом также не получает semantic acceptance. Никакие proof booleans или
исключения для green result не добавлены.

## 7. Стадии результата и границы evidence

| Стадия | Что установлено | Что не установлено |
|---|---|---|
| `format_decoded` | Поддерживаемая exact JSON/schema/typed expression form | Parent graph, canonical policy, kernel facts |
| `graph_normalized` | Полный well-formed graph, scoped identities, source ordering | Соответствие expected recipe или ownership |
| `recipe_matched` | Полное offline structural match без CT/raw blockers в supplied recipe | Установка на kernel, OS isolation, topology, bytes или packet delivery |
| `recipe_unproven` | Structural части совпали, CT/raw semantics не приняты | Semantic recipe verification и любой physical permit |
| Measurement verified | **Не реализована ни на одной ветке** | Cumulative rows не дают before/after или positive/deny evidence |

У `ValidatedRecipe2` нельзя передать `result="recipe_matched"` как constructor
override; result/reason вычисляются повторной pure comparison. Все стадии
unauthenticated/offline, ownership/physical/continuous flags false; финальный
record дополнительно фиксирует `measurement_verified=false`,
`topology_verified=false`, `byte_accounting=unproven`,
`installation_witness=unverified_reference`. Ни actual raw SHA-256, ни equality
graph не превращаются в committed transaction witness.

Отказы — static `ContractViolation2` codes (`v2_json_*`, schema/profile,
expression/layout, scope/parent/identity/graph/recipe/generation mismatch).
Нет arbitrary exception/stdout/packet content в result. Signature verification,
durability, freshness/replay или one-shot authority не заявляются.

## 8. Native fixtures и tests

Оригинальный
[`nft_ruleset_final.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/nft_ruleset_final.json)
читается byte-for-byte с проверкой
[`provenance.json`](trusted_checker_network/tests/fixtures/kernel_6_8_nft_1_0_9/native/provenance.json).
15 raw objects → 14 typed policy objects + exact metadata. Две bridge tables,
chain handles 1/1, priorities −200/10, per-chain order и table8/rule8 reuse
успешно нормализуются. Распознаны шесть scalar CT `in`, nonterminal CT counters,
ARP без counters и separate terminal verdicts.

Точные native numeric pairs сохранены: CT `3/180`, `15/1014`, `12/3530`;
strict `1/60`, `5/338`, `6/1931`, `6/428`, `3/176`. Они cumulative, не дельты.
`tc_ct_lab`/`tc_strict_lab` обязательно отвергаются против independent expected
recipe v2. Исходные fixtures не изменены и не нормализованы на диске.

80 новых tests охватывают:

- все parser limits, UTF-8/BOM/escapes/surrogates, duplicate keys, bool/float/
  nonfinite/big integer и malformed input;
- exact/extra/missing/duplicate metadata, wrong versions/schema/binary refs,
  unknown object/field/wrapper и отсутствие supplied validation shortcuts;
- обе grouping формы, source ordering, missing/extra/duplicate/dangling objects,
  scoped collisions/reuse и конкурирующие hooks;
- rules/expressions/counter/verdict reorder/mutation, nonterminal ingress,
  interface/IP/port/policy changes, parent/handle/ordinal/epoch replacements;
- typed ARP fields, static digest и expected AST consistency, complete positive
  без physical permit, numeric rows без measurement claim;
- CT operator isolation, unsupported sets/masks/related, raw shape/hex refusal
  и explicit `recipe_unproven`;
- native original artifacts, immutable stages, AST/import isolation и refusal
  existing PhysicalProbeGate даже для `recipe_matched`.

Mutation tests используют исходно valid synthetic baseline для своей стадии;
format-positive ARP/CT/raw tests не объявляются canonical policy positives.
Expected data не пересобирается из mutated JSON ради успеха. Первые 76 новых
tests прошли отдельным запуском; ещё четыре scope/ARP/ordinal checks включены в
финальный полный прогон.

## 9. Полный прогон Trusted Checker

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
| Network: прежние 254 + новые 80 | 334 | 0 | 0 | 0 | OK, 45.398s |
| Physical | 90 | 0 | 0 | 0 | OK, 14.706s |
| Live | 48 | 0 | 0 | 0 | OK, 15.187s |
| Runtime | 66 | 0 | 0 | 0 | OK, 13.070s |
| Shadow | 56 | 0 | 0 | 0 | OK, 3.394s |
| PoC | 166 | 0 | 0 | 0 | OK, 15.605s |
| **Всего** | **760** | **0** | **0** | **0** | **OK** |

Все процессы завершились exit code 0, без ResourceWarning. Логи:
`/tmp/task201b8c-{network,physical,live,runtime,shadow,poc}.log`.
Suites выполнялись независимо/частично параллельно; durations не benchmark.
Это полный Trusted Checker run, не всех Django приложений. Django regressions
не запускались: application code/writers не менялись. Fresh-import tests
запускают только локальный Python с запрещёнными socket/Popen/setns внутри
проверяемого import; subprocess nftables отсутствует.

## 10. Целостность и source digest

SHA-256 всех **166** baseline artifacts шести Trusted Checker packages без
caches и прежних `TRUSTED_CHECKER*.md` совпали с
`/tmp/task201b8c-baseline.json`. Включены v1/V2-01 source/tests, designs/reports,
physical gates, live adapter и все пять native original files. Добавлены четыре
Python-файла и этот отчёт; прежние files не изменены. Проверены syntax/AST,
local links, fenced blocks и whitespace. Рабочие БД, `.env`, credentials и
Docker sockets не читались.

Новые top-level network modules автоматически входят в existing physical
source manifest, поэтому digest изменился без редактирования старых files:

- до: `2c0097c13fdfef03700729f21cfc1a37593fa7dcdcfd7c006afe7618ab6a5cad`;
- после: `ec6acc10217d87fe68fffc396d86fd10ecdd2de77531ff9b54955d8c33f534a8`.

Старые approvals не обновлялись, не re-sign и не переносятся автоматически.
Никакой source/gate guard ради прохождения регрессий не ослаблен.

## 11. Оставшиеся blockers

1. **CT semantics:** exact masks/truth table/hook behavior и `==`↔`in` equivalence
   требуют отдельных approved proof artifacts; acceptance API proof здесь нет.
2. **Raw payload:** native parser/readback round trip, units/width/register/
   endianness/dependencies/VLAN ещё не приняты. Diagnostic syntax не compatibility
   proof. Unknown representation остаётся отказом/unproven.
3. **Topology/management:** полного native host/peer graph adapter/profile и
   разрешения management paths этот этап не добавляет.
4. **Ownership/collector:** authenticated capture provenance, committed witness,
   durable installation journal/rollback/replay/kill ещё не реализованы.
   `WitnessReference2` остаётся unverified.
5. **Byte accounting/measurements:** cumulative rows не baseline/delta evidence;
   skb/frame/padding/offload semantics, consistency/noise и 15 controlled probes
   отсутствуют. `measurement_verified=false` без исключений.
6. **Canonical kernel round trip:** full 49-counter recipe не исполнялся на
   approved kernel/nft builds. Shape compatibility лаборатории не заменяет его.

**`V2-02 OFFLINE READY`** означает готовность offline adapter в этих границах.
Physical compatibility, runtime acceptance и live activation не объявляются;
все physical gates остаются закрытыми.
