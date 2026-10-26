# Trusted Checker v2: Independent H1 Security Re-review — №20.1b-8k

22 октября 2026 · Git HEAD `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`H1 FIXES REQUIRED`.** Исходные минимальные conditions A01–A07 на исправленном коде дают безопасный outcome. Однако подтверждены **5 нарушений offline invariants: 2 HIGH, 3 MEDIUM**. Обнаружены скрытие independently supplied inherited FD, cleanup чужой активной попытки при cross-registry композиции, late publication success, cancel/dispatch deadlock и замена уже доступного через admission terminal после interruption.

Это не доказанный escape в host, native execution или physical permit. Findings относятся к доступной fake/offline композиции; конкретные preconditions указаны ниже. Отсутствие H2 не классифицировано как новая уязвимость. **`OS READY`, `PHYSICAL READY`, `H2 READY` не присваиваются.** Production, существующие tests/fixtures/reports и physical guards не менялись. Исправления не выполнялись, H2 не начинался.

## 1. Scope и независимость проверки

Проверены актуальные production `native_v2_helper_protocol.py`, `native_v2_helper_runtime.py`, `native_v2_helper_fake.py`, `native_v2_helper_identity.py`, `native_v2_helper_native.py`; связанные capture/OS contracts, old collector/OS reader entry boundaries и physical gate. Затем реализация сопоставлена с [исходным audit](V2-06a-H1-SECURITY-REVIEW.md) и [remediation report](V2-06a-H1-SECURITY-REMEDIATION.md).

До изучения assertions remediation security module создана собственная [матрица invariants/fault points](audit_artifacts/h1_rereview_20261022/invariants.md). Проверки не импортируют и не копируют test expectations из него. Существующий `HelperFixtureH1` используется только как исходный independently supplied synthetic baseline; mutations, scheduling, assertions и accounting проверки написаны заново.

Новый [audit harness](audit_artifacts/h1_rereview_20261022/test_h1_rereview.py) хранится вне production packages, вместе с durable evidence в [audit_artifacts/h1_rereview_20261022/](audit_artifacts/h1_rereview_20261022/README.md). В отличие от прежнего `/tmp` harness, reproductions и baseline сохраняются в workspace. Это самостоятельный повторный анализ в текущей сессии, а не внешняя сертификация другим аудитором или автоматически полученный security sign-off.

Threat/fault model: protocol/received rows/observed records могут отличаться от expected; операции exact fake driver могут иметь partial effect и бросить exception; cancellation/interruption могут возникать в соседних состояниях. Trusted Python memory/fixture setup/helper остаются TCB. Monkeypatch отдельных методов и lock-exit fault имитируют эти состояния только в test process; они не утверждают наличие произвольного Python execution у внешнего attacker. Real Linux guarantees из этого не выводятся.

## 2. Актуальный baseline и hashes

До запуска probes сохранён [baseline.json](audit_artifacts/h1_rereview_20261022/baseline.json): **324 existing artifacts** шести Trusted Checker packages без caches, прежние `TRUSTED_CHECKER*.md` и H1 audit/remediation reports. HEAD не включает прежние untracked H1 modules, поэтому SHA-256 manifest является отдельным обязательным evidence.

**Все 324 hashes совпали после re-review.** Source digest до/после:

`bffce5ec1e43bf1783f2b48a23b3372397c4fd5f8aded93ff3b4e95561efae3a`.

Physical gates/live guard, native helper module, original fixtures/archives/matrices и source manifest implementation сохранены byte-for-byte. Manifest не обновлялся ради green tests; approvals не создавались/не переподписывались. Новые files — только этот report и isolated audit artifacts. Итоговые hashes/checks — [integrity.json](audit_artifacts/h1_rereview_20261022/integrity.json).

## 3. Повторная проверка H1-A01–A07

В колонке «исходный сценарий» речь о конкретном counterexample прежнего audit. Его закрытие не означает, что все соседние combinations безопасны.

| Finding | Исходный сценарий на текущем коде | Независимое resource evidence | Соседняя ветка / итог |
|---|---|---|---|
| A01 | **Закрыт:** last watch fence до close, strict positive проходит | Success и malformed INVOKE abort не читают closed FD; known-owned FD закрываются один раз | Coherent replacement после claim даёт unknown/cleanup_unproven, replacement не закрывается. Нового watch use-after-close не найдено |
| A02 | **Закрыт:** lost return до/после helper/child registration восстановим | Нет running/unreaped/unclosed objects после successful recovery; cleanup status учитывает partial failures | **RR02:** owner isolation не распространяется на общий kernel при разных registries |
| A03 | **Закрыт:** oversized feed и failed finish irreversibly latch | Corrected frame/late completion не восстанавливает decoder/verifier; interruption latch проверен | Все 315 truncated INVOKE prefixes и 272 binding-byte mutations отвергаются в проверенных probes |
| A04 | **Закрыт:** repeated kill coalesces и terminal queue sealed | 10000 parallel kill calls после disabled terminal: queue=0, driver calls=0; historical record на обычном retry/kill сохраняется | **RR04:** nested/concurrent kill на dispatch образует lock cycle; bounded queue не гарантирует завершения cancellation |
| A05 | **Закрыт:** KeyboardInterrupt на poll финализирует resources/registry | Immutable unknown, active=None, circuit=true, 7 owned FD и оба process records закрыты; before/after matrix и retry faults fail closed | **RR05:** interruption после actual terminal assignment заменяет уже admitted record; **RR03:** timing gap у publication |
| A06 | **Закрыт:** no execute bits → refusal | 0000/0600/0644 отказ, 0755 admitted; owner/group/other precedence и actual observed mismatch проверены | Не обнаружен обход predicate через проверенные mode/group/hash/generation mutations; OS ACL/LSM proof не следует |
| A07 | **Закрыт:** nine-transfer/malformed cardinality cleanup не теряет owned FD | 0/6/7/8/9/16 FD accounted, malformed/duplicates/foreign rows не дают чужой close; 17 refused до смены catalog | **RR01:** independent inherited inventory sanitizes до owned set, поэтому completeness/isolation validation всё ещё может получить false positive |

Результаты `OriginalFindingChecks` сохранены в [observations.json](audit_artifacts/h1_rereview_20261022/observations.json). Новые замечания не означают, что исходные 10 reconstructed safe assertions снова падают: эти assertions также проходят в существующей suite. Они не охватывают найденную композицию исправлений.

## 4. B01–B03

**B01 — частично подтверждён.** Cancel между reserve и child commit запрещает exec. Ordinary post-commit cancel приводит к unknown/cleanup. Но global lock order и publication linearization остаются небезопасными в RR04/RR05; delay после последнего clock fence даёт RR03.

**B02 — частично исправлен.** Constructor действительно требует отдельный `FakeObservationsH1`, expected→observed default factory удалён. Coherent executable inode/hash/generation replacement после claim не принимается и не становится foreign cleanup target. Однако fake `identity()` заменяет supplied inherited-FD inventory на transfer catalog, скрывая extra observed FD (RR01). Независимость container constructor не гарантирует сохранения всех его фактов на readback.

**B03 — корректно остаётся unproven.** `native_process_tree="unproven"`, flags false, caller не может передать verified через constructor override. Fake boolean reap не выдаётся за actual helper exit/signal/descendant containment. Отсутствие native process-tree implementation — сохранённый H2 blocker, не новый defect этого re-review.

## 5. Новые подтверждённые findings

| ID | Severity | Нарушение |
|---|---|---|
| H1-RR01 | HIGH | Supplied external inherited FD скрывается fake identity readback, полный fake capture получает success |
| H1-RR02 | HIGH | Rejected attempt с новым registry очищает active resources другого supervisor при общем kernel/invocation |
| H1-RR03 | MEDIUM | После последнего clock fence publication может выйти за bound и сохранить success |
| H1-RR04 | MEDIUM | Reentrant + concurrent cancellation вызывает ABBA deadlock между state/control locks |
| H1-RR05 | MEDIUM | Interrupt после terminal assignment заменяет уже admitted historical result |

HIGH здесь относится к существенному нарушению проверяемого offline ownership/identity contract. Ни один finding не доказывает native privilege escalation или возможность внешнего attacker создавать trusted fixture/registry. Каждый scenario начинается с valid baseline; отдельные fault hooks моделируют разрешённые error/interleaving points.

Общие imports и fixture для минимальных примеров:

```python
from dataclasses import replace
from trusted_checker_network import native_v2_helper_protocol as p
from trusted_checker_network import native_v2_helper_runtime as r
from trusted_checker_network import native_v2_helper_fake as fake
from trusted_checker_network import native_v2_capture_contracts as cap
from trusted_checker_network.tests.native_v2_helper_support import HelperFixtureH1, hd
f = HelperFixtureH1.create()
```

### H1-RR01 — HIGH: supplied inherited-FD observation silently overwritten

**Код:** [fake](trusted_checker_network/native_v2_helper_fake.py), 27–37, 47–50 и **106–110**; [identity validator](trusted_checker_network/native_v2_helper_identity.py), 133. `identity()` подставляет `tuple(sorted(self._transfer_catalog))` вместо `identity_observation.inherited_fds`. Это owned transfer set, а не полный независимо наблюдённый inherited set.

**Условие:** supplied identity содержит дополнительный inherited FD, имеющий согласованный descriptor fact, но не являющийся transferred/owned slot. Все DTO и bounds валидны: 8 facts и 8 inherited numbers, 7 нормальных received slots. Никакой callback не врёт validator и не патчится result.

```python
obs = f.observations
obs = replace(obs,
    descriptor_facts=(*obs.descriptor_facts,
        (999, p.DescriptorIdentityH1('char', 1, 9009, 1, hd('external-held-fd')))),
    identity=replace(obs.identity,
        inherited_fds=(*obs.identity.inherited_fds, 999)))
k = fake.FakeHelperKernelH1(f.invocation, f.polls, observations=obs)
value, supervisor, k = f.run(k)
# value.result == 'helper_fake_capture_preserved'
# supplied inherited: [30,31,32,33,34,35,36,999]
# validated inherited: [30,31,32,33,34,35,36]
```

**Фактически:** terminal success/`reaped_closed`; FD 999 не закрыт, его fact остаётся в model source. Не закрывать foreign FD — правильно. Ошибка состоит в сокрытии observation и false successful identity validation, а не в отсутствии права удалить чужой FD. `open_transferred_count=0` относится только к семи owned slots и не доказывает полного inherited inventory.

**Invariant/последствие:** independently supplied facts должны оставаться видимыми; expected allowlist обязана отвергнуть extra inherited descriptor. Fake oracle сейчас normalizes observation к заведомо разрешённому owned набору, что ослабляет смысл model-level isolation tests. Real FD/socket/OS escape не выполнялся и не доказан.

**Безопасный результат:** unknown/refusal при сохранении extra observation, cleanup только семи owned FD, без close 999. Можно отвергать противоречивый observations bundle на constructor boundary; нельзя молча исправлять его до matching.

**Предлагаемое исправление:** разделить live observed inherited set и owned-transfer catalog; validate completeness/consistency, не переопределять supplied independent fields по expected/owned data. Также review иных overwritten identity fields, включая executable digest, чтобы inconsistency давала refusal.

**Regression/покрытие:** `test_R01_supplied_external_inherited_fd_is_hidden` в новом harness. В remediation tests строка 249 проверяет helper_start_ticks; old unexpected-inherited-FD test использует post-read `identity_transform`. Они не ловят sanitization supplied `FakeObservationsH1.identity.inherited_fds`.

### H1-RR02 — HIGH: kernel escrow не связан с owner/registry

**Код:** [runtime](trusted_checker_network/native_v2_helper_runtime.py), 401–405, 450–456, **480–492**; [fake](trusted_checker_network/native_v2_helper_fake.py), **139–157**. Registry имеет owner token, но kernel escrow/recovery ключ — только `(invocation.digest, role)`. Constructor не связывает kernel с единственным registry/owner.

**Условие:** два accepted supervisor objects используют один exact fake kernel и одну invocation, но разные valid registries одного session UUID. Первая попытка active; передачи authority/handoff нет. Вторая получает replay при `prepare_owned`, однако её `attempted=True` и unconditional recovery в finally берут resources первой.

```python
first, k = f.supervisor()
i = f.invocation
# Valid prefix первой попытки; пауза сразу после helper dispatch.
first.registry.reserve(i, first)
k.prepare_owned(i, 'helper')
token = k.register_helper(i)
k.dispatch_helper(token, i)
second, _ = f.supervisor(k,
    registry=r.OwnedInvocationRegistryH1(i.session.session_uuid))
value = second.run_fake()
# second: unknown / replay / reaped_closed
# k._objects[token]: running=False, reaped=True, closed=True
# first.registry.active_for(i, first) is still True
```

**Фактически:** rejected second attempt TERM/reap/close-ит helper и закрывает known transferred FD первого owner. Его registry всё ещё active. Это не cleanup чужого namespace/PID или иной canonical invocation: **invocation здесь та же**, чужая именно active попытка другого supervisor. Precondition shared kernel + fresh registry существенен; при одном общем registry проверенный owner fence работает.

**Invariant/последствие:** отказ replay не должен давать cleanup authority над active resources другой попытки. Fresh registry в одном живом процессе — отдельная композиция API, а не native restart/durability experiment. В source нет обязательного handoff/lease или rejection такого binding до effects; нельзя считать его проверенным только потому, что каждый registry отдельно имеет lock.

**Безопасный результат:** отклонить second binding/attempt без изменения первой resource catalog либо требовать явный reviewed ownership transfer с завершением прежнего owner. Непроверенный конфликт — quarantine, но не автоматический cleanup по общему digest.

**Предлагаемое исправление:** закрепить kernel/escrow/recovery к точному owner/lease, либо enforce единственный registry/owner на driver instance до attempts. Cleanup после failed prepare должен восстанавливать только resources, authority на которые получила эта попытка. Не искать по raw PID и не считать совпадение invocation достаточным handoff.

**Regression/покрытие:** `test_R02_fresh_registry_can_clean_active_other_owner`. Remediation `test_other_supervisor_cannot_finalize_active_owner` (406) использует общий registry и разные kernels; этот сценарий проверен и здесь проходит. Cross-registry reuse одного живого kernel там не покрыт.

### H1-RR03 — MEDIUM: deadline check precedes the publication critical section

**Код:** runtime **497–509**, `_publish` 430–442; `InventoryTimingProposal2` в [OS contracts](trusted_checker_network/native_v2_os_contracts.py), 72–89. Clock fence выполняется до `_state`/candidate construction, а `_publish` clock больше не читает.

**Условие:** после успешного final clock read до publication проходит время. В test это ordinary monotonic/wall advancement на boundary `_publish`, без изменения deadline, binding, output или cleanup facts:

```python
s, k = f.supervisor()
start = k.now
publish = s._publish

def delayed(*args):
    k.now = cap.CaptureTime2(start.wall_utc_us + 600000,
                           start.monotonic_us + 600000)
    return publish(*args)
s._publish = delayed
value = s.run_fake()
# success; current monotonic=1600000, deadline=1500000
```

**Фактически:** `helper_fake_capture_preserved / reaped_closed` при 600000 µs elapsed и command bound 500000 µs. Все resources очищены; новых commands после deadline нет. Нарушение — timing admission позднего terminal, не false cleanup и не реальное Linux measurement.

**Invariant/последствие:** заявленный publication fence не должен трактовать заранее проверенное время как гарантию времени будущего commit. Delay/lock wait/candidate cost между ними не учтены. Этот probe моделирует latency, а не утверждает, что fake tests измерили реальный CPU scheduling.

**Безопасный результат:** unknown/timeout для late publication в принятой модели либо отдельно определённый контракт завершения capture и publication с явными timestamp/budget semantics. Нельзя скрыто расширять deadline или выдавать preflight timing proposal за native benchmark.

**Предлагаемое исправление:** проверять timing в publication critical section как можно ближе к commit, bound candidate work, явно определить, к какому событию относится deadline. Новый clock check сам по себе не доказывает hard real-time атомарность Python/OS scheduling; такое обещание требует отдельной модели.

**Regression/покрытие:** `test_R03_clock_advancement_after_fence_before_publication`. Existing late-completion tests двигают время до final clock fence, поэтому отказывают, но не закрывают это окно.

### H1-RR04 — MEDIUM: cancellation lock cycle

**Код:** runtime **36–57**, **415–418**, callback dispatch 213–214. Порядок kill — `_state → channel._control`. Dispatch удерживает `_control` во время callback; reentrant kill из callback требует `_state`.

**Условие:** cancel из fake exec callback после commit, как уже разрешённый test fault, совпадает с внешним concurrent kill. Новый harness синхронизирует только события, не меняет lock implementations:

```text
Primary:  channel.dispatch holds _control
          exec callback waits until external cancel entered
External: kill holds _state
          channel.cancel waits _control
Primary:  exec callback calls kill
          waits _state
```

**Доказательство:** две original Python RLock блокируются. Сохранённые stacks: primary в `kill:416`, далее callback → `dispatch:57`; external в `cancel:37`, вызванном `kill:418`. Оба audit threads остаются blocked, `_cancel` уже set, `dispatch_committed=true`, terminal отсутствует, registry active/circuit=false, оба fake process records running, 7 owned FD unresolved. Это deadlock source lock order, не ожидание native I/O.

Harness использует два изолированных daemon **audit threads**, finite joins по 0.25s и stack snapshot. Они не являются native helpers. Завершение Python audit process убирает эти test threads; generic host process cleanup/kill не выполняется. Независимые tests остальных scenarios используют отдельные objects.

**Invariant/последствие:** bounded cancellation/finalization может навсегда не достигнуть cleanup. RLock допускает reentrancy одного thread, но не устраняет ABBA между двумя. Queue cap и finite poll count не помогают: primary ещё не вернулся из dispatch callback к poll/fence.

**Безопасный результат:** оба вызова конечны; attempt становится killed/unknown, делает bounded owned cleanup. Ни success, ни hanging active attempt не допустимы в этом interleaving.

**Предлагаемое исправление:** единый lock order или разделение signal/enqueue так, чтобы kill не ожидал control lock при удерживаемом state lock; не выполнять callbacks, способные reenter state, под обратным lock order. Сохранить bounded queue и ясный dispatch commit.

**Regression/покрытие:** `test_R04_reentrant_and_concurrent_cancel_lock_cycle`. Remediation `test_cancel_after_commit_is_cleanup_not_reversal` (509) проверяет reentrant cancel без concurrent external kill; `test_concurrent_kill_queue_does_not_grow` (518) не включает dispatch callback. Их композиция отсутствует.

### H1-RR05 — MEDIUM: already admitted terminal replaced after publication interruption

**Код:** runtime **506–515**, `admit` **519–523**. После `_terminal=terminal` внутри with состояние уже доступно admission. Если interruption возникает на выходе из critical section, except безусловно заменяет `_terminal` на fallback.

**Условие:** однократный `KeyboardInterrupt` после actual assignment, не после возврата только candidate. Audit lock-exit monitor делегирует original RLock, фиксирует появление `_terminal`, вызывает настоящий `admit` и затем имитирует interrupt на outer context exit:

```python
# Полный ExitInterrupt context manager — в test_R05_* нового harness.
# На outer __exit__, после s._terminal assignment:
issued = s._terminal
assert s.admit(issued) is issued
# После release original RLock: raise KeyboardInterrupt(...)
# Catch в _run: s._terminal = s._fallback
```

**Фактически:** до interrupt `issued.result=helper_fake_capture_preserved`, admission успешен. После него `s._terminal.result=unknown`, `issued is not s._terminal`; повторный run возвращает другой object и registry circuit закрыт. Frozen bytes старого record не изменены, **заменена identity исторического terminal у issuer**. Все model resources закрыты; это не ранний success до reap.

**Invariant/последствие:** нельзя одновременно считать assignment publication commit и затем менять уже admitted historical terminal как будто result ещё не выдавался. Current `admit()` не ждёт окончания state critical section, поэтому узкое окно наблюдаемо. Signal/interrupt point моделируется только offline; actual signal handler/OS experiment не выполнялся.

**Безопасный результат:** либо admission до завершённого commit невозможен и interruption даёт единственный unknown, либо после commit existing issued record сохраняется, а interruption/kill лишь запрещает дальнейшую admission. Требуется явно выбрать semantics, а не только frozen dataclass.

**Предлагаемое исправление:** согласовать candidate/commit/admit state и обработчик post-commit interruption; fallback не должен безусловно overwrite уже issued terminal. Нельзя лечить это подавлением всех BaseException.

**Regression/покрытие:** `test_R05_interrupt_after_terminal_assignment_changes_issued_record`. Remediation tests строк 342 и 531 прерывают после `_publish()` candidate, когда `_terminal is None`; actual assignment/lock-exit window ими не покрывается.

## 6. Resource/FD/child/registry invariants: проверено и предел доказательства

| Invariant | Независимое evidence | Результат и scope |
|---|---|---|
| Normal complete capture | `test_positive_complete_resource_catalog` | Два model processes: not-running/reaped/closed; 7 transferred FD закрыты один раз; active=None, circuit=false |
| Scoped repeated recovery | `test_recovery_is_idempotent_after_verified_cleanup` | После verified close оба role recovery возвращают None; другая invocation и arbitrary PID отказываются. Не закрывает RR02 same-invocation/other-owner alias |
| Before/after effects | `test_before_after_every_effectful_boundary` | **44 subcases**: 11 methods × before/after × RuntimeError/KeyboardInterrupt; во всех terminal unknown, no redispatch; неполное cleanup не называется clean |
| Retry с новой cleanup error | `test_two_faults_in_fallback_cleanup_preserve_unknown` | RuntimeError drain + два KeyboardInterrupt reap; последующий cleanup завершает оба model processes и 7 FD, но terminal остаётся cleanup_unproven/circuit=true |
| Sticky close failure | `test_owned_close_failure_cannot_be_erased_by_recovery` | Successful fallback освобождает остаток, предшествующая ошибка остаётся unproven |
| Initial and stale FD matching | A01/A07 checks и `test_coherent_generation_hash_replacement_is_quarantined` | Initial fields matching strict; coherent live replacement FD31 не принимается/не закрывается, остается **1 unresolved catalog slot**, unknown/cleanup_unproven |
| Closed FD access | `test_closed_operations_reject_without_double_close` | Describe/watch/namespace/executable/identity после close отказываются; repeated cleanup не делает второй close |
| Transfer cardinality/cap | A07 + `test_receiver_cap_and_malformed_metadata` | 0/6/7/8/9/16 accounted; 17 rejected before new catalog; malformed projection не стирает known-owned set |
| Shared registry owner | `test_common_registry_preserves_active_owner` | Два supervisor, одна invocation, общий registry: secondary без driver calls, primary active/не quarantined и затем success. Другие registry/kernel composition требует RR02 |
| Cancel до commit | `test_cancel_before_child_commit_blocks_execution` | Exec не вызывается, killed terminal, owned cleanup complete |
| Normal terminal immutability | `test_terminal_identity_immutable_on_normal_retry_and_kill` | Copy не admitted, retry возвращает тот же record, kill запрещает дальнейший admit. Не закрывает post-assignment interruption RR05 |
| Wire binding/order | `test_all_binding_bytes_and_late_sequence_fail` | 272 independently mutated binding bytes отвергаются; late complete/reaped/first phase после complete latch failure |
| Truncated/failed EOF | `test_truncated_frames_all_prefixes_and_no_repair` | 315 непустых INVOKE prefixes: finish отказ, остаток frame не восстанавливает stream |
| Output/frame/aggregate cap | `test_stream_output_and_registry_caps` | 4097-й frame, nft stdout >262144, stderr >4096 и registry >16 MiB отвергаются; ordinary cleanup проходит |
| Clock/no EOF | `test_clock_rollback_frozen_and_incomplete_eof` | Rollback, frozen finite polls ≤4080 и missing EOF дают unknown. Publication delay — отдельный RR03 |
| Native/process-tree claims | `test_process_tree_and_authority_stay_unproven`, static guard inspection | Process tree unproven, все 6 authority/verification flags false, PhysicalProbeGate denied; native/helper/OS backend entry не исполнялся |

Число open transfers относится к отдельно ограниченному **owned catalog**, не к полному реальному process FD table. Поэтому zero count в RR01 не опровергает extra inherited observation. Unresolved replacement slot в модели не объявляется доказанной утечкой original inode на Linux.

Проверки не являются исчерпывающим перебором всех schedules/partial effects. Подозрения, не повышенные до confirmed findings:

- Fake identity также переписывает `executable_object_digest` из другого observation; дополнительная согласованная exploit chain сверх RR01 отдельно не доказана. Стоит проверить consistency всех independently supplied sources; mere inconsistent digest не называется native FD substitution.
- Partial mutation внутри registry finish/abort и повторные asynchronous interrupts требуют ясного commit contract. Проверены method-boundary faults и RR05; crash-proof атомарность каждого Python bytecode не заявляется.
- Блокирующий сторонний callback как таковой не является новым finding: RR04 основан именно на source lock cycle двух штатных cancellation calls, а не на бесконечном sleep в driver.

## 7. Независимый audit harness: результаты и воспроизводимость

Новый harness содержит **31 самостоятельный test плюс subtests**: 19 invariant checks, 5 новых defect reproductions и 7 групп исходных A01–A07. Production functions импортируются read-only; имитация faults существует только в памяти test process. Существующие assertions/fixtures не редактируются.

| Запуск | Tests | Failures | Errors | Skips | Значение |
|---|---:|---:|---:|---:|---|
| Default observations | 31 | 0 | 0 | 0 | OK, 18.660s, exit 0. **Пять tests намеренно утверждают ошибочное поведение** |
| `--assert-safe` | 31 | **5** | 0 | 0 | 18.574s, exit 1. Нарушены safe expectations RR01–RR05; остальные 26 checks проходят |

Ни default green, ни passing subset не являются security pass. Safe-mode failures — действующие контрпримеры, без expected-failure decorators. У original A01–A07 counterexamples безопасный outcome подтверждён; итог `FIXES REQUIRED` обусловлен соседними и составными сценариями, а не автоматически перенесённым старым verdict.

Evidence: [observations.json](audit_artifacts/h1_rereview_20261022/observations.json), [observations.log](audit_artifacts/h1_rereview_20261022/observations.log), [safe.json](audit_artifacts/h1_rereview_20261022/safe.json), [safe.log](audit_artifacts/h1_rereview_20261022/safe.log). Для RR04 JSON содержит source stack locations и resource snapshot, а не arbitrary process dumps или packet data.

Из repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning - <<'PY'
import runpy
runpy.run_path('audit_artifacts/h1_rereview_20261022/test_h1_rereview.py', run_name='__main__')
PY
```

Safe expectations, которые на текущем source **должны завершиться 5 failures**:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning - <<'PY'
import runpy, sys
sys.argv = ['test_h1_rereview.py', '--assert-safe']
runpy.run_path('audit_artifacts/h1_rereview_20261022/test_h1_rereview.py', run_name='__main__')
PY
```

README предупреждает о daemon audit threads в RR04 и о том, что default mode проверяет reproductions. Это не запуск native helper, команды nft/ip/bridge/setns/FD-exec, или OS reader; test process после записи evidence завершается. Protected/internal records остаются synthetic; настоящие credentials/FDs не собираются.

## 8. Существующий regression

Выполнен [отдельный runner](audit_artifacts/h1_rereview_20261022/run_existing_offline.py) для текущих H1 + remediation security suites:

- **183 tests, OK, 30.898s; exit 0, failures=0, errors=0, skips=0, ResourceWarning отсутствуют**;
- включены все **57** remediation security tests, в том числе 10 reconstructed safe assertions;
- из 130 старых H1 tests выбраны **126**; четыре заранее исключены из selection, а не скрыты unittest skips.

Точный список exclusions сохранён в [existing-results.json](audit_artifacts/h1_rereview_20261022/existing-results.json):

1. `LifecycleTests.test_native_entry_closed_for_fake_approval`;
2. `LifecycleTests.test_helper_one_invocation_only`;
3. `IsolationTests.test_native_calls_guard_before_syscall`;
4. `IsolationTests.test_old_os_fake_backend_does_not_accept_new_kernel`.

Это консервативное ограничение re-review: native-entry-named/direct primitive invocations и old OS backend construction не нужны для нового fake harness. Guard bodies проверены статически и по неизменности hashes. Pure source-path/status/AST/import tests не являются actual native acquisition; fresh-import test создаёт лишь local Python test process с I/O blockers.

[existing.log](audit_artifacts/h1_rereview_20261022/existing.log) подтверждает green existing subset, который **не обнаруживает RR01–RR05**. Причины gaps для каждого finding указаны в разделе 5; ни один существующий test не переписан под audit result.

Полный Trusted Checker regression в этом re-review **не запускался**: пункт 5 задания требует его при отсутствии обнаруженных дефектов, а здесь воспроизведены пять. Число **1414 tests, OK** остаётся историческим результатом remediation, не новым результатом аудита. Это сознательное соблюдение условия задания, а не неполученное доказательство для PASS.

## 9. Native blockers и сохранённые закрытые boundaries

Повторно проверено source/AST:

- `native_guard_h1` — unconditional raise до concrete native method bodies; native helper entry не вызывался;
- `HelperSupervisorH1.capture_native` остаётся unconditional refusal;
- `DormantOSReadOnlyBackend2.capture_os` default disabled и unconditional `native_activation_unreviewed` для enabled path до driver calls;
- old collector/fake transport не превращают H1 result в authenticated capture/ownership/physical permit;
- existing `PhysicalProbeGate` возвращает `physical_network_boundary_not_accepted`; actual physical/network operation не вызывается даже у fake success.

Actual SCM_RIGHTS/IPC peer authentication, nsfs/PID/start/pidfd/FD/NSID acquisition, privilege drop, held-inode write exclusion, FD-exec/dependency closure, durable crash/replay/restart recovery, descendants, native timing и полный OS inventory остаются unproven. Они не закрываются synthetic тестами и не являются новыми активными уязвимостями только из-за отсутствия H2.

Выполнялись source/artifact reads, запись отдельного audit harness/report и local Python/threaded offline tests. Не было VDS/SSH, native helper/OS backend run, nft/ip/bridge/tc/Docker/setns/FD-exec/packet/network операций, изменения routes/firewall/sysctl, Django/Ticket Sandbox/academic writes, чтения БД/.env/credentials, deploy/commit/push/rebase. API/fake methods с названиями exec/namespace выполняли только in-memory model effects.

Все 324 baseline artifacts сохранены; production/source manifest/physical guards не изменены. New audit artifacts не являются source approval и не подключены к runtime/live checker.

## 10. Финальное решение

**`H1 FIXES REQUIRED`.** Прямые A01–A07 remediation scenarios подтверждены, но исходный `READY FOR INDEPENDENT RE-REVIEW` не превращается в независимый PASS: RR01–RR05 воспроизводимо нарушают H1 offline identity/ownership/lifecycle/timing invariants.

Приоритет для отдельной remediation задачи:

1. **RR01/RR02:** сохранять полный independent inherited inventory и связать resource escrow/recovery с точным active owner/lease, включая registry/kernel aliasing.
2. **RR04:** устранить lock-order cycle без потери bounded/idempotent cancellation и ясного dispatch commit.
3. **RR05/RR03:** согласовать candidate/terminal/admission/interrupt commit и timing event, затем протестировать actual assignment boundary и delay после final clock fence.
4. Повторить независимые safe expectations и resource accounting, затем отдельный re-review. Не заменять их assertions проверкой одного reason или green existing suite.

Эти исправления не выполнены. H2 не начинался. Native execution, ownership authority, management/isolation verification и physical gates остаются закрытыми; `OS READY`/`PHYSICAL READY`/`H2 READY` не присвоены.
