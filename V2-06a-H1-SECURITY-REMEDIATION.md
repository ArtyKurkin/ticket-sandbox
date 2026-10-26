# Trusted Checker v2: H1 Security Remediation — №20.1b-8j

22 октября 2026 · Git HEAD `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**`H1 REMEDIATED — READY FOR INDEPENDENT RE-REVIEW`.** Исправлены все семь H1-A01–A07 из [независимого security review](V2-06a-H1-SECURITY-REVIEW.md). Финальный полный Trusted Checker regression: **1414 tests, OK**, включая 57 новых; восстановленные 10 audit safe assertions проходят. Это remediation offline H1, без начала H2 или реализации native IPC/bootstrap/helper.

Native execution остаётся закрытым. `physical_probe_permitted`, `ownership_proven`, `isolation_verified`, `management_policy_verified`, `measurement_verified`, `continuous_attestation` остаются false. `OS READY`/`PHYSICAL READY` не присваиваются; physical audit — `NOT READY`, shadow-only сохраняется. Read-only argv, hashes и fake observations не создают OS authority.

## 1. Изменения и совместимость

| Файл | Изменение |
|---|---|
| [native_v2_helper_protocol.py](trusted_checker_network/native_v2_helper_protocol.py) | Conservative executable admission для command principal; irreversible stream failure и sealed EOF |
| [native_v2_helper_runtime.py](trusted_checker_network/native_v2_helper_runtime.py) | FD lifetime/finalization, scoped ownership recovery, interruption cleanup, cancellation commit/seal, owner-aware registry и безопасная publication |
| [native_v2_helper_fake.py](trusted_checker_network/native_v2_helper_fake.py) | Strict FD lifetime/generation, bounded owned-transfer receipt, отдельно заданные observations, invocation/role escrow/recovery |
| [native_v2_helper_support.py](trusted_checker_network/tests/native_v2_helper_support.py) | Отдельно authored synthetic `FakeObservationsH1`; expected invocation не служит production factory observed facts |
| [test_native_v2_helper.py](trusted_checker_network/tests/test_native_v2_helper.py) | Только прежний duplicate-cancel test заменён на проверку требуемого coalescing; число старых tests сохранено |
| [test_native_v2_helper_security.py](trusted_checker_network/tests/test_native_v2_helper_security.py) | 57 новых постоянных offline tests, включая 10 восстановленных safe expectations независимого аудита |
| Этот документ | Remediation, faults, regression, hashes и остающиеся blockers |

Изменены пять baseline files, добавлены два files. Ни v1, ни physical gates/activation authority, прежние collectors/adapters, native helper module, identity parser, contracts, original fixtures/archives/matrices или предыдущие reports не редактировались. H1 wire version 1, compatibility contract version 2, exact fixed argv registry, environment, stdout/stderr/aggregate caps и command/session timing limits сохранены.

`FakeHelperKernelH1(invocation, polls, *, observations=...)` теперь требует exact `FakeObservationsH1`. Нет default expected→observed fallback. Fixture, вручную создаваемый с иной invocation, должен также явно предоставить свои independently supplied observed facts; молчаливого принятия нового expected input нет. Это изменение fake API, не native receiver/observer interface.

Registry `reserve`/`finish` получили optional process-local owner argument; прежнее direct использование сохраняет default ownership за invocation object. Supervisor использует свой owner identity, поэтому другой supervisor с тем же invocation object не может завершить или очистить его active attempt. Это memory fence, не durable journal/OS principal.

## 2. H1-A01: parent-watch lifetime

**Root cause:** последний `fence()` выполнялся после `close_transferred`, а прежний fake не замечал использование закрытого watch FD.

**Исправлено:** `StandaloneHelperH1.run_fake` выполняет последний FD-dependent parent/deadline/cancel fence после child cleanup, но **до закрытия любого transferred FD**. Затем закрываются data/namespace/executable/watch slots; control закрывается после protocol completion. Supervisor отдельно требует process/FD cleanup и final timing fence перед publication.

`FakeHelperKernelH1._open_fd` проверяет owned catalog, open state и pinned full descriptor facts. Describe, parent-watch, identity, namespace entry, executable verification и child setup/exec используют эту проверку. Closed/replaced FD больше не является допустимым observation.

**Инвариант:** ни одна FD-dependent операция не использует закрытый/заменённый объект. `channel.closed` означает закрытый enqueue; successful cleanup отдельно определяется driver outcomes и sticky failure state. Ошибка close не компенсируется wire complete.

**Regression:** оба `test_A01_*` в `AuditSafeExpectations`, `test_closed_fd_operations_refuse`, `test_each_owned_fd_close_failure_is_quarantine`, прежний positive end-to-end. Проверены trace без closed reads, strict positive, zero remaining owned FDs и отсутствие duplicate closes.

**Ограничение:** это lifetime в fake-модели. Actual Linux pidfd/read/close/reuse semantics и parent-death containment не проверялись.

## 3. H1-A02: recoverable ownership до partial effects

**Root cause:** единственный handle сохранялся assignment после возврата registration/reservation; исключение после создания ресурса оставляло `owned=None` и обходило cleanup.

**Исправлено:** `prepare_owned(invocation, role)` закрепляет точный invocation-digest/role escrow до `register_helper` или `reserve_child`. Fake ограничен одной invocation и двумя roles; повторное создание по escrow запрещено. `recover_owned` возвращает только owned resource этой invocation/role либо подтверждённое отсутствие в данной finite catalog. Нет поиска по произвольному PID.

Helper всегда восстанавливает child ownership; supervisor дополнительно восстанавливает child/helper при потере ответа либо interruption helper. Неполный recovery, reap или close устанавливает sticky cleanup failure. Даже если последующая best-effort попытка удалась, terminal сохраняет `cleanup_unproven` и unknown/circuit quarantine. `no_dispatch` допустим лишь когда отсутствие созданных процессов подтверждено, а FD cleanup завершён; непроверенные resources не получают `reaped_closed`.

**Инвариант:** возврат handle больше не является единственным источником ownership. Все ошибки resolve/cleanup имеют fail-closed outcome.

**Regression:** оба `test_A02_*`; `test_registration_all_partial_effect_windows` проверяет before/after exceptions на helper registration, child reservation, helper dispatch и FD-exec; `test_escrow_exists_before_helper_and_child_effect`, `test_failure_to_recover_is_quarantine`, `test_recovery_cannot_target_foreign_invocation_or_role`. Для successful recovery проверяется каждый resource catalog record (`running=false`, `reaped=true`, `closed=true`), zero open transfers и корректный cleanup status. При permanent recovery failure orphan явно видим и cleanup unproven.

**Ограничение:** escrow находится в памяти exact fake instance. Durable restart recovery, actual PID/pidfd ownership и native registration atomicity не приняты и не реализованы как H2 boundary.

## 4. H1-A07: FD close-on-abort до semantic validation

**Root cause:** cardinality refusal мог произойти до записи полученных FD в cleanup accounting; malformed rows также не являлись надёжным ownership source.

**Исправлено:** actual owned-transfer catalog отделён от переданной helper projection. `transfer_receipt(invocation)` закрепляет bounded receipt до проверки INVOKE и supplied rows. Helper принимает ровно семь semantic slots, но cleanup использует **driver-owned receipt**, включая extra FD. При malformed projection прежний known-owned catalog не удаляется.

Fake receiver допускает максимум **16** owned descriptors, проверяя cap до создания/удержания нового catalog. Semantic acceptance по-прежнему требует ровно 7; лимит 16 нужен только для bounded отказа и cleanup malformed transfers. Произвольный oversized набор не создаёт unbounded escrow. Catalog заменяется только до claim; duplicate local FD numbers закрываются один раз. Foreign row number не даёт close authority. Изменённый после claim descriptor не закрывается как прежний owned object: outcome unproven/quarantine.

Control закрывается отдельно на всех helper exits; supervisor делает bounded fallback cleanup оставшихся known-owned transfers. Ошибка любого close сохраняется в итоговом cleanup даже при успешном fallback.

**Инвариант:** refusal count/schema не теряет actual owned transfers; close targets берутся из bounded owned catalog, не из untrusted slot/number. Неизвестный replacement не становится cleanup target.

**Regression:** `test_A07_*`, cardinalities **0/6/7/8/9**, malformed None/object/tuple/integer rows, duplicate transfers, arbitrary foreign number 999, cap overflow 17, каждый из семи owned FD close faults. Для 9 FD результат unknown/fd_transfer_invalid, закрыты все 9, нет orphan/double-close; при transient close failure cleanup остаётся unproven даже после полного освобождения.

**Ограничение:** native SCM_RIGHTS/MSG_CTRUNC receiver отсутствует. Ownership новых дескрипторов на actual OS receive boundary и cleanup ancillary errors требуют H2; fake catalog не является FD attestation.

## 5. H1-A03: irreversible failure latch

**Root cause:** failed transcript `finish()` не устанавливал `_failed`; initial type/size validation `feed()` находилась вне latch handler.

**Исправлено:** все fatal `feed` paths находятся под latch, включая type/size/header/decode failure и interruption. Ошибка очищает bounded stream buffer, устанавливает `_failed` и распространяется наружу. Successful EOF помечается `_finished`; новые chunks после EOF отказывают. Failed transcript `finish` latch запрещает поздний complete; `accept` также latch при interruption без подавления исходного исключения.

**Инвариант:** corrected frame/late completion не может восстановить отказавший decoder/verifier. Повторные calls сохраняют failed state и не продвигают sequence/stage/output.

**Regression:** оба `test_A03_*`, `test_decoder_all_fatal_inputs_latch`, `test_decoder_incomplete_eof_and_successful_eof_are_sealed`, все 315 непустых truncated INVOKE prefixes, `test_transcript_failed_state_is_stable`, `test_parser_interrupts_latch_without_suppression`. Существующие malformed/order/forged-completion tests сохранены.

**Ограничение:** structural verifier остаётся pure equality/hash/order validator. Он не удостоверяет происхождение IPC или реальные OS effects.

## 6. H1-A04: bounded/idempotent cancellation

**Root cause:** каждый kill добавлял cancel frame; terminal disabled/error paths могли оставлять enqueue открытым.

**Исправлено:** `ControlChannelH1.cancel` сериализован RLock, coalesces cancellation и создаёт не более одного pending frame. Проверка producer state предшествует encode/append. Cancellation latch сохраняется после consumption. `seal` закрывает enqueue и очищает queue на каждом terminal path, включая disabled/early error/cleanup failure. Kill после publication устанавливает admission fence без изменения historical immutable result и не enqueue ничего.

**Инвариант:** repeated cancellation не увеличивает очередь и не превращает обычную повторную отмену в sequence error. Ошибочные wire frames остаются malformed input, но штатный producer их не генерирует.

**Regression:** `test_A04_*`, 10000 cancel calls до и после consumption, 5000 kill calls для disabled/success/failure/close-failure terminal, concurrent four-thread producer, прежний post-success admission denial.

Прежний `test_duplicate_cancel_rejected` изменён на `test_duplicate_cancel_coalesced`: новое требование прямо задаёт idempotency. Убрано ожидание ошибки от двух штатных cancel вызовов; добавлены assertions очереди и consumption. Другие прежние test assertions не переписаны ради green result.

## 7. H1-A05: interruption finalization

**Root cause:** control close, terminal publication и registry finish находились после `finally`; `KeyboardInterrupt`/`BaseException` выходили мимо них.

**Исправлено:** helper/supervisor записывают interruption, предпринимают bounded cleanup и распространяют исходный `BaseException` после finalization. Cleanup не поглощает interrupts: remembers first interruption, выполняет independent best-effort KILL/reap/close при ошибках clock/TERM/drain и сохраняет fault status.

Control закрывается в helper finalization; supervisor восстанавливает scoped resources и заканчивает remaining transfer cleanup. Registry finish/abort учитывает частично применившийся reserve/finish и process-local owner. Другой active owner не очищается. Failed attempt получает immutable unknown; повторный run не dispatch ничего.

Перед effects подготовлен immutable emergency unknown/cleanup_unproven record. `_publish` создаёт candidate и финализирует registry **до** выдачи terminal; interruption до publication commit приводит к fallback и quarantine. После commit driver operations больше нет. Это устраняет ложный success при сбое создания candidate/finish/publication в моделируемых fault points.

**Инвариант:** interrupt не становится успешным результатом и не обходит cleanup accounting. Successful fallback не стирает ранее неизвестный cleanup. Исторический уже опубликованный result остаётся immutable, kill закрывает admission.

**Regression:** `test_A05_*`; before/after injections на prepare/registration/reservation/dispatch/exec/poll; KeyboardInterrupt на TERM, running check, drain, KILL, reap, owned close, transferred close, control close; faults registry reserve/finish, partial reserve before active assignment, publication before/after candidate, cleanup clock failure и иной subclass BaseException. Проверяются terminal, circuit/active owner, exact closed set, отсутствие orphan и redispatch. Permanent reap/close failures остаются явно unproven, а не замаскированы зелёным stdout.

**Ограничение:** конечные synthetic one-shot и permanent driver faults не доказывают crash resilience interpreter/OS. Повторные asynchronous signals, supervisor process death и durable recovery требуют отдельной H2/native operational модели; arbitrary memory corruption TCB не входит в guarantee.

## 8. H1-A06: conservative executable admission

**Root cause:** H1 predicate пропускал execute-bit check, имевшийся в прежнем OS reader; fake FD-exec принимал несовместимый positive.

**Исправлено:** общий внутри H1 `validate_executable_h1` применяется к expected invocation и фактически supplied executable observation. Требуются regular file, root ownership, link count 1, protected/no-symlink/no-file-capabilities references, отсутствие setid/group/world write и execute bits. Для supported fake principal выбирается owner/group/other execute permission с owner/group precedence; uid 0 всё равно требует хотя бы один execute bit.

**Инвариант:** coherent изменение expected digest не разрешает non-executable файл. Нужны подходящие observed facts и executable permission для command principal; FD-exec повторно проверяет actual live fake descriptor.

**Regression:** `test_A06_*`, modes **0000/0600/0644 — refusal**, **0755 — positive**, group 0750 с/без membership, owner/group precedence, root без execute bits, setid/write/nonregular/owner/link/protection faults и несовпадающие observed permissions.

**Ограничение:** POSIX bits в conservative fake-модели не являются ACL/LSM/mount/userns/actual capability proof. Никакой реальный executable не читался и не исполнялся.

## 9. B01–B03 и native blockers

**B01 — commit semantics определены в offline H1.** До helper dispatch commit действует supervisor state lock, общий с kill. После child reserve выполняется fence; `ControlChannelH1.dispatch` проверяет cancellation и устанавливает `dispatch_committed` под тем же lock, который защищает cancel. Cancel до commit запрещает exec; cancel после commit переводит attempt к stop/cleanup, но не «отменяет прошлую execution». Tests проверяют cancel внутри helper registration/child reserve и непосредственно после child commit. Дополнительный concurrent registry test не позволяет secondary supervisor завершить primary attempt с тем же invocation object.

**B02 — fake observations отделены от expected input.** `FakeObservationsH1` задаётся явно trusted synthetic setup: bounded received/facts tuple, executable observation и identity snapshot. Production fake не создаёт эти facts из expected invocation ни при constructor fallback, ни при readback. Test support separately authors expected и observed records с общими явными fixture constants/profile references. Это не независимые OS witnesses, но подмена expected input теперь не меняет observed source автоматически.

Live fake state и pinned receipt сравниваются полностью, включая kind/device/inode/generation/object digest. Coherent inode/hash/generation replacement и прежняя inconsistent metadata mutation дают unknown, cleanup_unproven, без закрытия нового foreign object. Native acquisition/write exclusion/TOCTOU остаются unreviewed.

**B03 — явно unproven.** `HelperResultH1.native_process_tree="unproven"` — derived init=False status, caller не может заменить его verified. Fake reap подтверждает только direct-child lifecycle его finite model; real helper exit/signal status, surviving descendants, inherited pipes и parent-death containment не объявляются принятыми. Новый native wait/IPC interface не добавлялся. Это конкретный H2 blocker.

C01–C06 из исходного review сохраняются: actual launch authority/authenticated IPC/SCM_RIGHTS, nsfs/PID/pidfd/FD/NSID acquisition, credentials/userns/capabilities, FD-exec/loader/dependency closure/write exclusion, durable replay/restart/descendant recovery, real clocks/timing/full OS surface inventory. Ни один fake success не закрывает их; root/approved helper остаются TCB. Guarded native source и physical activation authority не изменены.

## 10. Safe expectations независимого аудита и regression

К началу этой задачи `/tmp/h1-security-review/test_h1_security_review.py` уже отсутствовал. Поэтому **исходный harness не запускался**, а его фактический SHA-256 не мог быть повторно проверен/сохранён. В неизменённом audit report осталась ссылка на исторический SHA-256:

`dcb91ac4395aa55fb14ec82bcc09d7a2f68e7317c71abcdef574909bf89ebc6e`.

Этот hash не приписывается новому тестовому файлу. SHA-256 постоянного remediation test module: `d1815d8ebee5f23b1c5342f3b43445f2a9b7b6c744e20e9c1170f305ef015e3b`. В repository восстановлены **10 исходных safe conditions** по report reproductions в классе `AuditSafeExpectations`; добавлены более строгие resource assertions. Нельзя утверждать byte-for-byte эквивалентность отсутствующему harness или новый запуск всех его 30 tests.

Сохранён смысл исходных safe expectations: no closed-watch reads + strict positive; no orphan/false cleanup при двух lost-return случаях; irreversible transcript/decoder failure; bounded kill; finalization до повторного interrupt; non-executable refusal; полный cleanup девяти transfers. Обычный defect-reproduction режим, намеренно ожидавший ошибки, не используется как критерий успеха. B01/B02 bad-trace assertions старого harness тоже не должны оставаться зелёными после исправлений; новые tests требуют безопасный outcome.

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning \
  -m trusted_checker_network.tests.test_native_v2_helper_security --assert-safe
```

**Финальный safe run:** `10 tests, OK, 2.442s; exit 0, failures=0, errors=0, skips=0`. Это reconstructed audit safe assertions, не подмена отсутствующего original archive. Полный постоянный security module содержит **57 tests плюс subtests**; Fault matrices не пересчитывались как отдельные tests. Прежние 130 H1 + новые 57 отдельно прошли: **187 tests, OK, 27.360s**.

Новые tests проверяют не только reason: actual bounded transfer catalog/open count, каждый process record, отсутствие orphan/double-close/foreign close, sticky unknown cleanup, pending cancel count, registry owner/active/circuit, late refusal, immutable terminal и отсутствие новых dispatch после terminal. Есть expected negative unproven outcomes; skips/expected failures не используются для недостающих native proofs.

Финальный полный Trusted Checker run:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_network/tests -t .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_physical/tests -t .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_live/tests -t .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_runtime/tests -t .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_shadow/tests -t .
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning -m unittest discover -s trusted_checker_poc/tests -t .
```

| Suite | Tests | Failures | Errors | Skips | Результат |
|---|---:|---:|---:|---:|---|
| Network | 988 | 0 | 0 | 0 | OK, 112.207s |
| Physical | 90 | 0 | 0 | 0 | OK, 9.367s |
| Live | 48 | 0 | 0 | 0 | OK, 9.101s |
| Runtime | 66 | 0 | 0 | 0 | OK, 7.192s |
| Shadow | 56 | 0 | 0 | 0 | OK, 1.836s |
| Poc | 166 | 0 | 0 | 0 | OK, 8.892s |
| **Всего** | **1414** | **0** | **0** | **0** | **OK** |

Все шесть процессов завершились exit code 0, без failures/errors/skips/ResourceWarning. Финальные **988 Network tests = прежние 931 + новые 57**, полный итог **1414 = прежние 1357 + новые 57**. Финальный run выполнен после explicit-observations refinement, на окончательном source.

Финальные логи: `/tmp/task201b8j-final-{network,physical,live,runtime,shadow,poc}.log`, `/tmp/task201b8j-final-independent-safe.log`. Первый полный промежуточный run до final explicit-observations refinement тоже прошёл (1412 tests); он не подменяет финальный результат на окончательном source. Начальный H1 run выявил только ожидаемую несовместимость duplicate-cancel assertion с новым требованием; contract не ослаблялся ради других tests.

Suites — offline/mocks, отдельно и частично параллельно. Guard-denial tests прежних suites могут непосредственно вызвать guarded native function и получить немедленный refusal; **реальных native helper processes/syscalls/FD-exec/setns не выполнялось**. Fresh-import tests запускают только локальный Python с I/O blockers. Durations не native benchmark. Это полный Trusted Checker, не всех Django приложений: application/writers не менялись.

## 11. Целостность, source digest и отсутствие activation

До изменений сохранён `/tmp/task201b8j-baseline.json`: **322 baseline artifacts**, шесть Trusted Checker packages без caches, прежние `TRUSTED_CHECKER*.md` и исходный security review. Копии H1 originals — `/tmp/task201b8j-originals/` для точного diff untracked files.

SHA-256 **317 неизменённых baseline artifacts** совпали. Пять ожидаемо изменённых baseline files перечислены в разделе 1; их pre/post hashes сохранены в `/tmp/task201b8j-integrity.json`. Нельзя заявлять сохранение hashes исправленных production files. Original native fixtures/archives/matrices, не затронутые fixes v1/capture/OS contracts, gates/native/identity modules и audit report сохранены byte-for-byte. Добавлены только постоянный security test module и этот report.

Dynamic physical source digest:

- до: `5cafe53a289b9ddf8800d91be5b03c13ca8218d138bd62726883060f1e6a8de0`;
- после: `bffce5ec1e43bf1783f2b48a23b3372397c4fd5f8aded93ff3b4e95561efae3a`.

Старые approvals не обновлялись, не переподписывались и не переносятся автоматически. Исторический security review не редактировался и не превращён в повторное независимое одобрение исправлений.

Review source/AST и hashes подтверждает: production fixes не добавляют OS/network/process imports или I/O; effectful native module не изменён, его guard остаётся unconditional. Registry/fake methods работают только с in-memory records/locks и exact fake types. Поля authority остаются false; existing `PhysicalProbeGate`/live guard/`physical_network_boundary_not_accepted` сохранены.

Реальных nft/ip/bridge/tc/Docker/setns/FD-exec/packet operations, SSH/VDS/helper launch, firewall/routes/sysctl mutations не было. Django/Ticket Sandbox/Ledger/Roadmap/achievements, academic results, БД, .env/credentials не читались/не менялись в этой задаче. Commit/push/rebase/deploy не выполнялись. Проверены syntax, whitespace и local Markdown links/fences; tracked Git diff пуст, прежние unrelated untracked files сохранены.

## 12. Решение и следующий шаг

**`H1 REMEDIATED — READY FOR INDEPENDENT RE-REVIEW`.** Все семь подтверждённых findings исправлены в offline boundary; постоянные regressions и восстановленные audit safe expectations проходят. Неподтверждённые native facts сохраняют статус unproven.

Повторному независимому review доступны точные fixes, постоянные safe regressions, scoped fault outcomes и неизменённый исходный audit. Это remediation author's validation, а не автоматически присвоенный `H1 REVIEW PASSED`.

H2 не начинался. Его отдельные задачи по actual native IPC/identity/credentials/FD-exec, durable ownership/recovery, descendant containment и measured timing остаются prerequisites будущего review/разрешения. До их закрытия native execution, ownership authority, isolation/management verification и все physical gates остаются закрытыми; physical acceptance — `NOT READY`.
