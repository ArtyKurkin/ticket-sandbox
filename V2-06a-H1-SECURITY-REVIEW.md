# V2-06a-H1 — Independent Security Review

21 октября 2026 · аудит №20.1b-8i · Git HEAD `4692e09f9cd867a40f3cfeb29355b9d08f2bafde`.

**Решение: `H1 FIXES REQUIRED`.** Подтверждены **7 дефектов: 2 HIGH, 4 MEDIUM, 1 LOW**. Главные проблемы — использование parent-watch после закрытия, потеря ownership handle при частично выполненной регистрации и ложный cleanup status. Дополнительно нарушаются failure latch, bounded cancellation и finalization при interruption; oversized FD transfer не закрывает полученные ресурсы. Успех synthetic lifecycle в отчёте №20.1b-8i недостаточен для статуса без этих оговорок.

Обход native execution или physical gate **не установлен**. Все findings относятся к доступным offline API, fake-модели и их error paths. HIGH означает существенный дефект проверяемого ownership/lifecycle contract, а не доказанное исполнение команд на host. Native entry остаётся закрытым; `OS READY` не присваивается, physical audit остаётся `NOT READY`. Код не исправлялся; H2 не начинался.

## Основание, метод и границы

Полностью изучены семь запрошенных файлов: protocol, identity, runtime, fake, native, test support и 130 существующих H1 tests. Дополнительно проверены участвующие `native_v2_contracts.py`, capture/OS contracts, прежняя executable validation, fixed argv registry, source manifest и `PhysicalProbeGate`. Отчёт №20.1b-8i сопоставлен с фактическими ветками кода. Номера строк ниже относятся к неизменённому состоянию на момент аудита; HEAD сам по себе не идентифицирует прежние untracked H1 files, поэтому сохранён отдельный SHA-256 baseline.

Модель угроз: protocol bytes, fragmentation, received FD metadata и последовательность событий могут быть некорректны; операции driver могут завершаться частичным эффектом и исключением. Trusted setup, Python process и helper остаются TCB. Fault injection в exact fake instance моделирует такие отказы, а не утверждает возможность злоумышленника подменять произвольный Python-код. Реальные Linux effects из этих тестов не выводятся.

Независимые проверки размещены вне production tree: [test_h1_security_review.py](/tmp/h1-security-review/test_h1_security_review.py). Они используют прежний support только для исходного valid fixture, затем отдельно задают faults и проверяют trace, resource accounting и verifier. Более строгая FD-модель в A01 намеренно проверяет свойство, отсутствующее в исходном fake.

Выполнены **30 новых самостоятельных tests**, включая subtests по всем **272 binding bytes**, всем **315 непустым truncated prefixes** одного INVOKE и дополнительные fault matrices. Это 30 tests плюс subtests, без пересчёта mutations в отдельные tests.

| Запуск | Результат | Значение |
|---|---|---|
| Обычный режим harness | 30 tests, OK, 5.827s; exit 0 | 10 tests подтверждают воспроизведение дефектов, 2 исследуют потенциальные риски, 18 проверяют отдельные гарантии |
| `--assert-safe` | 30 tests, **10 failures**, 0 errors, 5.467s; exit 1 | Те же 10 defect scenarios не удовлетворяют явно заданным безопасным ожиданиям |

Оба режима без skips/expected failures. Зелёный первый запуск **не является security pass**: в нём намеренно утверждается наличие ошибочного поведения. Равенство observations JSON двух запусков закрепляет одинаковое поведение, а не результат assertion. Длительности не benchmark и не native timing proof.

Полный прежний набор 1357 tests не запускался заново: среди H1 tests есть непосредственные обращения к native entry/primitive для проверки guard. Условие текущего аудита запрещает такие вызовы даже ради ожидаемого отказа; guards здесь проверены статически. Число 1357 остаётся историческим результатом №20.1b-8i.

## A. Подтверждённые дефекты

| ID | Severity | Дефект | Непосредственный эффект |
|---|---|---|---|
| H1-A01 | HIGH | Parent-watch проверяется после close | Исходный fake даёт success при обращении к закрытому FD; строгая модель отвергает positive |
| H1-A02 | HIGH | Ownership handle теряется при исключении после регистрации | Остаётся running/unreaped/unclosed fake object; cleanup ошибочно `no_dispatch`/`reaped_closed` |
| H1-A03 | MEDIUM | Не все fatal verifier errors latch | Поздний completion/новый frame принимается после предшествовавшего отказа |
| H1-A04 | MEDIUM | Cancel producer не ограничен | Повторный kill накапливает произвольное число frames, в том числе после disabled terminal |
| H1-A05 | MEDIUM | `BaseException` обходит finalization | Нет terminal, registry остаётся active без circuit, control не закрыт |
| H1-A06 | LOW | Не требуется executable execute bit | Coherent fixture с mode 0644 получает synthetic success |
| H1-A07 | MEDIUM | FD-count refusal предшествует close-on-abort accounting | Девять переданных FD оставляют восемь незакрытых при `reaped_closed` |

Общие imports для минимальных reproductions ниже:

```python
from dataclasses import replace
from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_helper_protocol as p
from trusted_checker_network import native_v2_helper_runtime as r
from trusted_checker_network.tests.native_v2_helper_support import HelperFixtureH1
f = HelperFixtureH1.create()
```

Каждый сценарий начинается с нового valid synthetic fixture/kernel. Полные assertions и traces находятся в audit harness; production source не патчится.

### H1-A01 — HIGH: parent-watch используется после закрытия

**Файл и строки:** [runtime](trusted_checker_network/native_v2_helper_runtime.py), строки 149–158, 215–222; [fake](trusted_checker_network/native_v2_helper_fake.py), строки 30–32 и 120–123.

**Условие и доказательство.** В успешной ветке `finally` вызывает `close_transferred` для всех slots кроме control. Это включает parent-watch. Затем строка 222 вызывает `fence()`, который обращается к этому parent-watch через `kernel.parent_alive()`. В baseline это FD 36.

```python
k = f.kernel()
original = k.parent_alive
closed_reads = []
def checked(fd, pid, ticks):
    if fd in k.closed_received:
        closed_reads.append(fd)
    return original(fd, pid, ticks)
k.parent_alive = checked
value, _, _ = f.run(k)
# value.result == 'helper_fake_capture_preserved'; closed_reads == [36]
```

Второй probe заменяет тело проверки на `raise OSError(...)`, если FD уже в `closed_received`. Тот же исходно valid lifecycle становится `unknown / evidence_invalid`. Реальный syscall/EBADF не вызывался: доказана ошибка порядка операций, а не испытан Linux runtime.

**Нарушенный invariant и последствие.** Parent-watch должен оставаться owned/open до последнего использования; completion нельзя обосновывать чтением закрытого descriptor. Исходный fake скрывает ошибку: `close_transferred` добавляет FD в set, но `parent_alive` не проверяет этот set. Положительный end-to-end поэтому подтверждает поведение с невозможной для корректного FD lifetime предпосылкой. Перенос такого порядка в native backend может сделать positive path неработоспособным и создать окно reuse; эксплуатация reuse не доказана.

**Ожидаемый безопасный результат.** При valid baseline — успешное fake capture без обращений к закрытым FD. При реальной потере watch — unknown/quarantine. Нельзя получить success за счёт разрешения closed-FD reads.

**Предлагаемое исправление.** Согласовать последнюю parent/deadline/cancel проверку с ownership lifetime: держать watch до неё, затем закрывать с обязательным учётом результата. Усилить fake так, чтобы describe/verify/watch/namespace operations отвергали закрытые или заменённые FD.

**Требуемый regression.** `test_A01_parent_watch_is_read_after_close`, `test_A01_strict_fake_fd_semantics_reject_positive`; строгий lifetime-aware fake должен пройти positive, trace не должен содержать use-after-close. Существующие `test_reap_child_and_helper` (строка 170) и `test_parent_check_uses_transferred_pidfd` (258) проверяют закрытие/аргументы раздельно и этого сочетания не ловят.

### H1-A02 — HIGH: потеря результата регистрации оставляет ресурс без owner handle

**Файл и строки:** runtime 187–188, 215, 349–352, 372–375, 389–392; fake 63–77.

**Условие и доказательство.** Обе операции возвращают единственный handle после side effect: `owned = kernel.register_helper(i)` и `owned = kernel.reserve_child(uuid)`. Если метод успел зарегистрировать объект и затем выбросил исключение, assignment не выполнен. Cleanup зависит от `owned is not None`; recovery по invocation отсутствует.

```python
k = f.kernel()
original = k.reserve_child  # Повторить отдельно с register_helper.
def lost_return(*args):
    original(*args)
    raise RuntimeError('synthetic lost return')
k.reserve_child = lost_return
value, supervisor, k = f.run(k)
orphans = [obj for obj in k._objects.values()
           if obj['running'] or not obj['closed']]
```

Результаты двух отдельных injections:

| Точка потери | Terminal | Cleanup claim | Оставшийся объект |
|---|---|---|---|
| `register_helper` после эффекта | unknown | `no_dispatch` | helper: running=true, reaped=false, closed=false |
| `reserve_child` после эффекта | unknown | **`reaped_closed`** | child: running=true, reaped=false, closed=false |

Это не actual host process leak: fake `_reserve` сразу создаёт running object. Но в определённой им модели orphan и неверный cleanup claim воспроизводятся непосредственно. Не установлено, что будущая native registration будет atomic/no-throw; такой контракт в H1 не закрыт.

**Нарушенный invariant и последствие.** Reserve-before-dispatch должен сохранять recoverable ownership даже при lost response/частичном отказе. `unknown` по evidence не разрешает объявлять resources отсутствующими или закрытыми. Circuit действительно закрывается, но не убирает потерянный resource и не исправляет cleanup status.

**Ожидаемый безопасный результат.** Либо resource гарантированно не создан, либо invocation escrow позволяет найти, terminate/reap/close его. При неопределённом исходе — `cleanup_unproven`, quarantine, без `no_dispatch`/`reaped_closed`.

**Предлагаемое исправление.** Резервировать recoverable invocation/resource identity у supervisor до потенциально частичной операции; определить atomicity/no-effect-on-error либо recovery API driver. Обрабатывать helper и child симметрично. Нельзя восстанавливать ownership по произвольному PID.

**Требуемый regression.** `test_A02_lost_helper_registration_return`, `test_A02_lost_child_reservation_return`: исключение до эффекта, после регистрации, после dispatch и перед возвратом; проверять все objects и cleanup claim. Старые `test_lost_spawn_response` (324) и `test_failed_fd_exec_after_reservation` (329) вводят отказ позже, когда handle уже сохранён, и не покрывают эти окна.

### H1-A03 — MEDIUM: неполная необратимость failure latch

**Файл и строки:** runtime 54–58 и 93–94; protocol 186–201 и 203–206.

**Условие и доказательство №1.** `HelperTranscriptH1.finish()` проверяет полноту, но при ошибке не устанавливает `_failed`. После отказа `finish()` можно принять недостающий complete и завершиться успешно:

```python
_, supervisor, _ = f.run()
frames = supervisor._channel.frames
v = r.HelperTranscriptH1(f.invocation)
for raw in frames[:-1]:
    v.accept(raw)
try:
    v.finish()  # ContractViolation2: incomplete_output
except c.ContractViolation2:
    pass
v.accept(frames[-1])
v.finish()
assert v.complete  # Позднее восстановление после отказа.
```

**Доказательство №2.** В `HelperStreamDecoderH1.feed` проверка типа/размера chunk стоит до `try`. `feed(b'x' * (MAX_FRAME + 1))` отказывает, но `_failed` остаётся false. Следующий корректный INVOKE принимается; `finish()` проходит. Oversized declaration, обнаруженный внутри `try`, напротив, latch закрывает.

**Нарушенный invariant и последствие.** Заявленный irreversible failure не охватывает все fatal paths. Компонент можно повторно использовать после EOF/incomplete refusal либо oversized feed. Текущий supervisor после ошибки `finish()` не повторяет verifier и возвращает unknown; интегрированный false-success/physical permit этим сценарием **не доказан**. Размер allocation здесь также не обойдён: ошибочный oversized chunk не буферизуется.

**Ожидаемый безопасный результат.** После первого fatal stream/transcript failure любые subsequent accept/feed/finish отказывают. Если ошибки caller API намеренно не fatal, их следует явно отделить от transport failure; нельзя заявлять безусловную latch-гарантию.

**Предлагаемое исправление.** Ввести единый terminal/failed state для `finish` и fatal `feed` paths; согласовать EOF semantics. Отказ не должен быть «исправим» новым completion.

**Требуемый regression.** Оба `test_A03_*` из harness. Существующий `test_missing_complete_refused` (508) не пробует восстановление; `test_failed_transcript_cannot_be_repaired_by_late_completion` (537) проверяет ошибку `accept`, а не `finish`. `test_chunk_input_type_and_bounds` (90) не пробует повторный feed после отказа.

### H1-A04 — MEDIUM: unbounded cancel queue и неидемпотентный kill

**Файл и строки:** runtime 24–42, 328–332, 343–345.

**Условие и доказательство.** `ControlChannelH1.cancel()` без ограничения добавляет новый frame с sequence 1. `kill()` вызывает его каждый раз, пока channel.closed false. Даже default-OFF attempt создаёт channel и оставляет его открытым после terminal:

```python
supervisor, k = f.supervisor(enabled=False)
terminal = supervisor.run_fake()  # unknown / disabled; kernel.calls == []
for _ in range(p.MAX_MESSAGES + 1):
    supervisor.kill()
assert len(supervisor._channel.cancel_frames) == 4097
```

Накоплено **1 163 548 bytes** — 4097 frames по 284 bytes, уже больше protocol message cap 4096. Цикл можно продолжать; queue не имеет верхней границы. Код воспроизводится без kernel dispatch или native call.

**Нарушенный invariant и последствие.** Заявленный bounded per-direction protocol и finite terminal lifecycle не распространяются на cancellation producer. Повторная отмена увеличивает память; duplicate cancels также превращают штатную отмену в sequence error у receiver. Доступ внешнего attacker к `kill()` не установлен; доказан resource-exhaustion path доступного API.

**Ожидаемый безопасный результат.** Kill идемпотентен, очередь содержит не более одного pending cancel; terminal закрывает channel для дальнейшего enqueue. Исторический result остаётся immutable, admission после kill закрыт.

**Предлагаемое исправление.** Coalesce cancel, ограничивать enqueue и закрывать channel на всех terminal paths, включая disabled/early error. Producer обязан соблюдать лимит до allocation/append.

**Требуемый regression.** `test_A04_cancel_queue_grows_after_disabled_terminal`: многократный kill до, во время, после disabled/error/success terminal и при неуспешном control close. Старый `test_duplicate_cancel_rejected` (433) проверяет отказ receiver на двух сообщениях, а не bounded producer или idempotency.

### H1-A05 — MEDIUM: interruption обходит terminal, registry finish и control close

**Файл и строки:** runtime 213–234, 370–392; cleanup 256–288.

**Условие и доказательство.** Защитные обработчики ловят `Exception`, но terminal publication, `registry.finish` и helper control close находятся после соответствующих `finally`. `KeyboardInterrupt` наследует `BaseException` и выходит мимо этих действий.

```python
k = f.kernel()
def interrupt():
    raise KeyboardInterrupt('synthetic; no real signal')
k.on_poll = interrupt
supervisor, k = f.supervisor(k)
try:
    supervisor.run_fake()
except KeyboardInterrupt:
    pass
# supervisor._terminal is None
# supervisor.registry._active is not None
# supervisor.registry._circuit is False
# 35 (control) not in k.closed_received
```

Child и helper в данном probe получили reap/close через `finally`, data/watch slots закрыты. Поэтому не утверждается утечка всех процессов. Но control slot 35 остался открытым в fake accounting, immutable terminal отсутствует и registry занят незавершённой invocation. Настоящий сигнал/OS process не использовались.

**Нарушенный invariant и последствие.** Interruption не должен обходить учёт ресурсов и перевод attempt в terminal/quarantine. Если окружающий процесс перехватит interruption и продолжит работу, session остаётся с незавершённым accounting. Успех или разрешённый redispatch при этом не обнаружены: active registry блокирует новое резервирование. При реальном завершении process OS может закрыть FD; Linux leakage этим probe не доказывается.

**Ожидаемый безопасный результат.** Даже при распространении interrupt наружу записан unknown/quarantine, control cleanup предпринят, registry finalization выполнена. Не требуется молча поглощать пользовательский interrupt.

**Предлагаемое исправление.** Обеспечить outer `finally` для control/registry/terminal obligations и отдельно определить обработку `BaseException` с последующим re-raise. Не превращать interrupt в успешное завершение и не ограничиваться заменой всех `except` на безусловное подавление исключений.

**Требуемый regression.** `test_A05_keyboard_interrupt_bypasses_terminal_and_registry_finish`, затем injection на reserve/dispatch/poll/reap/close/publication, включая interrupt во время cleanup. Старый `test_unknown_exception_is_redacted` (359) использует обычный `RuntimeError`; этот класс interruption не покрывает.

### H1-A06 — LOW: H1 executable predicate принимает mode 0644

**Файл и строки:** protocol 108–114; fake 46–49 и 79–83. Для сравнения: [прежний OS reader](trusted_checker_network/native_v2_os_reader.py), 147–149, явно требует `mode & 0o111 != 0`.

**Условие и доказательство.** `ExecutableObservation2` — общий observation DTO и не обязан сам проверять executable mode. H1 invocation проверяет regular file/root/no-setid/no-group-write, но пропускает execute bits. Coherent object digest можно пересчитать для нового mode:

```python
i = f.invocation
exe = replace(i.executable, mode=0o100644)
spec = replace(i.descriptors[1], identity=replace(
    i.descriptors[1].identity, object_digest=p.executable_object_digest_h1(exe)))
i = replace(i, executable=exe, descriptors=(i.descriptors[0], spec, *i.descriptors[2:]))
value, _, _ = HelperFixtureH1(i, f.polls).run()
assert value.result == 'helper_fake_capture_preserved'
```

**Нарушенный invariant и последствие.** Positive model принимает файл, который не прошёл бы прежнюю conservative executable admission. Fake FD-exec не моделирует эту precondition, поэтому даёт ложный compatibility positive. Это trusted fixture/input defect; не доказаны native исполнение non-executable файла, privilege escalation или обход binary hash pin.

**Ожидаемый безопасный результат.** Refusal до namespace/credential/exec effects, либо явный unknown по непригодному executable. Success через изменение expected mode недопустим.

**Предлагаемое исправление.** Использовать общий reviewed executable predicate с обязательными execute bits; fake не должен подтверждать FD-exec при нарушении predicate. Проверка bits — необходимое условие, но не полная проверка фактической исполнимости для UID/ACL/mount/LSM.

**Требуемый regression.** `test_A06_non_executable_mode_gets_success`, mode 0000/0644/0600 и отдельные constraints command UID. Старые hash/identity tests (309, 312) и fixture support mode 0755 эту coherent mutation не покрывают.

### H1-A07 — MEDIUM: oversized transfer отказывает до регистрации close-on-abort

**Файл и строки:** runtime 159–163, 215–218, 231–234; fake 120–129.

**Условие и доказательство.** На строке 160 `len(transferred) <= 8` проверяется до `fds = transferred`. Если tuple содержит девять typed received descriptors, исключение оставляет `fds=()`. `finally` закрывает пустой набор; отдельный `close_control()` закрывает только control.

```python
k = f.kernel()
k.received = (*k.received,
    p.ReceivedDescriptorH1('stdout_pipe', 100),
    p.ReceivedDescriptorH1('stderr_pipe', 101))
value, _, k = f.run(k)
# unknown / fd_transfer_invalid, cleanup='reaped_closed'
# closed_received == {35}
# Unclosed: 30, 31, 32, 33, 34, 36, 100, 101.
```

Начальный valid 7-slot fixture расширен двумя owned mock transfers. Доказана потеря accounting на malformed input path, а не реальная SCM_RIGHTS утечка. Receiver native ещё отсутствует и может предусмотреть более ранний cap, но H1 callable такого ресурсо-безопасного отказа сейчас не обеспечивает.

**Нарушенный invariant и последствие.** Все фактически полученные owned descriptors должны иметь close-on-abort независимо от валидности INVOKE/count. Отказ по cardinality не означает отсутствия полученных ресурсов. `reaped_closed` здесь ложен; fake close пустого tuple возвращает true.

**Ожидаемый безопасный результат.** Все newly received owned descriptors закрыты, либо cleanup явно unproven/quarantine. Sender/foreign FD table не затрагивается. Нельзя бесконечно принимать transfer в память ради последующего cleanup: ownership escrow должен существовать уже на bounded receive boundary.

**Предлагаемое исправление.** Сначала установить учёт полученного bounded transfer/escrow, затем проверять count/schema; malformed/ancillary truncation paths обязаны закрывать каждый newly received FD. Отдельно учесть duplicate FD numbers и ошибки validation одного row без double-close/foreign close.

**Требуемый regression.** `test_A07_oversized_transfer_skips_close_on_abort`, cardinalities 0/6/7/8/9, malformed row и fault каждого close; проверять actual closed set и terminal cleanup. Старый `test_unexpected_transferred_fd` (246) добавляет только один FD (всего 8), поэтому проходит строку 160; assert полного cleanup для cardinality 9 отсутствует.

## B. Потенциальные риски: наблюдение есть, доказательства уязвимости недостаточно

### H1-B01 — MEDIUM: не определена точка отмены относительно dispatch

**Код:** runtime 187–188 и 328–331. Если обёртка `reserve_child` резервирует handle, вызывает `supervisor.kill()` и затем возвращает handle, `exec_fd_child` всё равно вызывается. Следующий fence распознаёт cancel; terminal становится `unknown / killed`, cleanup выполнен. Это воспроизведено `test_B01_cancel_between_reservation_and_exec`.

Возможный invariant — «после завершившегося kill новая execution не начинается» — не обеспечен этим порядком. Но contract не определяет dispatch commit point и не обещает атомарность cancel относительно уже начатой регистрации. Поэтому dispatch-after-cancel trace **не объявляется доказанным permit bypass или отдельной подтверждённой уязвимостью**. Сейчас fake выполняет только модель fixed read-only operation.

Требуются явные semantics отмены, check после reserve перед dispatch и, если нужен строгий запрет, сериализация cancellation/dispatch commit. Regression должен отменять до reserve, внутри reserve, перед exec, во время poll, после complete до publication и проверять допустимый набор effects. Старые cancel tests покрывают до dispatch, poll и после success, но эту точку отдельно не фиксируют.

### H1-B02 — LOW: fake executable oracle может не отражать замену metadata

**Код:** fake 34–49; runtime 176 и 211; identity 134. При замене `fd_facts[31]` на record с device/inode=999 и generation=2 во время poll, но с прежним `object_digest`, baseline остаётся `helper_fake_capture_preserved`. Сценарий `test_B02_fake_executable_metadata_fault_is_not_observed` воспроизведён.

Однако изменённые metadata и оставленный digest **внутренне несогласованны**. Это не proof substitution при корректном trusted observer: настоящий observer обязан формировать согласованные facts/hash; compromised TCB вообще может лгать. Проверяемое ограничение состоит в том, что post-exec fake oracle сравнивает supplied digest, а snapshot строит из expected invocation, вместо независимого acquisition metadata.

Возможное последствие — пробел тестов coherent FD replacement/reuse и TOCTOU. Предлагается определить единственный источник live FD facts, повторно проверять полный post-exec identity и enforce closed/generation semantics в fake. Regression должен задавать **согласованную** замену inode/hash/stat/generation и независимо получаемый post-snapshot; нынешние hash/identity toggles не доказывают real acquisition. Native observer отсутствует, поэтому реальная TOCTOU уязвимость этим тестом не подтверждена.

### H1-B03 — MEDIUM: helper reap не описывает exit status и descendants

**Код:** runtime 256–288, 372–375; fake 109–118. `reap_owned()` возвращает bool, а fake автоматически делает helper not-running на reap, если `control_close_ok`. Отдельного typed helper exit/signal status или descendant inventory в H1 port нет.

Нужно уточнить, достаточно ли после verified complete и resource cleanup самого reap или требуется normal helper exit; crash-after-complete и surviving descendant сейчас невозможно независимо описать имеющимися facts. Из кода **не следует**, что реальный crash обязательно будет принят: native driver отсутствует. Это открытый lifecycle contract и недостаток модели, а не выполненная Linux exploit reproduction.

Предлагается в H2 определить helper/child exit, signal, pidfd generation, parent-death и descendant containment records; fail-closed для неподтверждённого process tree. Regression — helper death до/после complete, descendant с удерживаемой pipe, lost wait response и supervisor restart. Старые helper-crash toggles проверяют ранние отказы, а не эти OS outcomes.

## C. Native blockers: synthetic tests принципиально недостаточны

Все пункты ниже — prerequisites, **не новые доказанные уязвимости активного native path**. Их severity показывает значение для возможной активации. Для каждого безопасное текущее поведение — сохранение native refusal; fake success или новый digest не закрывают blocker.

| ID / severity | Boundary и evidence в коде | Что требуется до H2/native acceptance |
|---|---|---|
| H1-C01 / HIGH | Native bootstrap/IPC отсутствует. `native_guard_h1` (native:15) безусловно отказывает; native entry:109. Protocol binding — public deterministic bytes; phase commitments — hash expected input | Отдельные launch authority и protected control channel; actual SCM_RIGHTS ownership/count/MSG_CTRUNC handling, SO_PEERCRED/peer protection, nonce generation/lifetime, malformed ancillary cleanup. Не считать digest MAC или доказательством IPC provenance |
| H1-C02 / HIGH | Namespace probe (native:55–60) не выдаёт nsfs proof; identity validation (120–137) сравнивает supplied records | Reviewed nsfs/net namespace ABI, boot/PID/start brackets, held FD lifetime/generation, pidfd target, session-scoped NSID/peer acquisition; реальные FD-open и namespace-entry effects. Номер FD, имя netns и stat inode по отдельности недостаточны |
| H1-C03 / HIGH | Native credential drop (89–93) намеренно не реализован. Fixture capability mapping в identity:53–83 synthetic | UID/GID/groups/userns/capset/prctl/securebits ordering и независимый readback, minimal privileges, protected reader/helper/command separation. Read-only argv не ограничивает весь набор прав principal |
| H1-C04 / HIGH | Native hash (62–74) и FD-exec (95–100) за guard; protection refs (76–79) не OS attestation | Held inode write exclusion; source/build/loader/library/plugin/config/mount closure, actual FD-exec ABI на exact kernel/Python/build. Hash до/после не исключает все privileged writers и transient modifications |
| H1-C05 / HIGH | Registry process-local (runtime:291–316), cleanup fake-only, real launch/driver отсутствует | Only-owned child/pidfd registration и recovery на всех partial effects, parent-death/descendant containment, interruption/reaping, supervisor crash/restart, durable replay/kill/quarantine. Нельзя наследовать гарантии persistent journal из этого set/lock |
| H1-C06 / MEDIUM | Fake clock (fake:25–28), fixed inventory proposal, unsupported OS surfaces остаются непринятыми | Independent monotonic/wall acquisition и bounded syscall/cancellation behavior, measured preflight timing, protected evidence storage/export; полный tc/XDP/flowtable/sysctl/offload/FD/writer inventory. Fake durations не native benchmark; 2s packet budget не расширяется |

Offline fault tests должны проверять отказ при missing/unreviewed facts, но не могут доказать actual OS identity, privilege isolation, IPC authenticity, FD-exec semantics или host isolation. Для C01–C06 нужны отдельно reviewed implementation, exact build/security profile и **отдельно разрешённый** эксперимент. В этом аудите ни такие operations, ни разрешение не создавались. Existing physical gate также не заменяет устранение offline A-findings перед будущим переносом кода.

## D. Подтверждённые гарантии и их практический предел

Гарантии ниже проверены независимо и с указанием scopes; это не доказательство безопасности всех combinations или OS compatibility.

| ID / проверка | Evidence | Что установлено |
|---|---|---|
| H1-D01 / fixed widths | `test_D01_fixed_width_and_unknown_headers`; protocol:18–22, 149–176 | Header 12, binding 272, max frame 4380, INVOKE 316 bytes. Unknown magic/version/kind отвергаются; exact per-kind tail sizes проверяются |
| H1-D02 / binding integrity | `test_D02_each_binding_byte_is_checked` | Flip каждого из 272 bytes отвергается относительно independently pinned invocation. Это equality/integrity в trusted process, не authentication |
| H1-D03 / truncation bounds | `test_D03_all_nonempty_truncated_prefixes_fail_finish` | Все 315 непустых prefixes одного valid INVOKE дают отказ на finish; накопление ограничено одним frame. Это не закрывает A03 для oversized caller chunk |
| H1-D04 / accept latch | `test_D04_malformed_accept_latch_does_work`; runtime:54–58 | После malformed `accept` corrected frame не принимается. Ограничение: `finish` latch нарушен в A03 |
| H1-D05 / ordinary unknown | `test_D05_unknown_causes_latched_circuit_without_redispatch` | Nonzero child exit даёт immutable unknown, circuit закрыт, повторный run возвращает тот же object без новых kernel calls. Ограничения: A02/A05 |
| H1-D06 / replay | `test_D06_replay_nonce_and_concurrent_registry`; runtime:297–309 | Active invocation запрещает второе reserve; тот же nonce запрещён и при другом invocation UUID после успешного finish. Scope — один registry/process |
| H1-D07 / identity negatives | `test_D07_wrong_identity_and_source_bounds` | Подмена namespace inode, helper PID generation и principal отвергается; size/mask error status parser не принимается |
| H1-D08 / reap refusal | `test_D08_reap_failure_is_not_success` | `reap_ok=False` даёт unknown/cleanup_unproven без output. Не подтверждает cleanup на всех иных путях, см. A02/A07 |
| H1-D09 / owned targets | `test_D09_no_raw_pid_kill` | Fake kill не принимает произвольный numeric PID; opaque reference проверяется в собственном object catalog |
| H1-D10 / authority | `test_D10_flags_and_physical_gate`; contracts:105–125, physical collector:240–246 | Все шесть verification/physical/ownership flags false, forbidden flag replacement отказывает; `PhysicalProbeGate.permit` даёт `physical_network_boundary_not_accepted` |
| H1-D11 / closed native | `test_D11_native_guards_static_only_never_invoked`; native:15, runtime:326 | AST подтверждает unconditional guard до concrete native method bodies; native entry не вызывается. Нет установленного обхода к OS calls из проверенного fake route |
| H1-D12 / non-authentication | `test_D12_coherent_transcript_is_not_os_attestation` | Transcript можно полностью составить из expected hashes/phase commitments без запуска helper/kernel; pure verifier его структурно принимает. Это документированное свойство, не уязвимость authenticated channel: такой channel ещё отсутствует |
| H1-D13 / fault matrix | `test_D13_clock_eof_crash_and_cleanup_fault_matrix` | Frozen/rollback/jump clock, incomplete stderr EOF, helper crash, lost dispatch response, parent death, close failure не дают success; frozen poll конечен, ≤4080. Причины могут стать cleanup_unproven при вторичном cleanup timeout |
| H1-D14 / caps | `test_D14_stream_and_output_bounds` | 4097-й stream frame отвергается; nft stdout >262144 и stderr >4096 отвергаются; registry не debit сверх 16 MiB. Cancel producer является отдельным исключением A04 |
| H1-D15 / order/completion | `test_D15_phase_order_and_completion_fault_matrix` | Reordered/duplicate phase, early/late complete, forged hash отвергаются. Отказ не означает authenticated origin или actual reap |
| H1-D16 / FD matching | `test_D16_fd_renumber_and_substitution_matrix` | Receiver FD renumbering допускается; initial device/inode/generation/kind substitution отвергается. Post-exec acquisition limitations — B02/C02 |
| H1-D17 / dispatch/admission | `test_D17_admission_cancellation_lock_and_owned_dispatch` | Нормальный reserve предшествует dispatch/exec; copied result не проходит admission; kill после publication закрывает admission, historical terminal сохраняется; повторный entry при занятом lock отвергается |
| H1-D18 / unknown identity | `test_D18_unreviewed_identity_and_fd_inventory_refused` | Unreviewed namespace_fs, unexpected inherited FD, неверные NSID/config/journal refs не принимаются |

Статически дополнительно подтверждены fixed 10-source argv registry, exact fake type checks, отсутствие shell/user argv/namespace-name dispatch и native fallback. Environment pinned `LANG=C`, `LC_ALL=C`. Native `os.execve(fd, ...)` расположен за unconditional guard и не имеет pathname fallback в проверенном source; **исполняемость этого native mapping не проверялась**.

### Покрытие требований аудита и error paths

| Область | Итог review |
|---|---|
| Fixed schema, malformed/truncated/oversized, sequence | Закрытые widths/types и bounded frame decoding подтверждены; A03 нарушает часть latch contract |
| Replay/nonce/binding/forged completion | Process-local replay и structural tamper checks работают в проверенных probes; B/C отделяют hashes от authenticated IPC |
| Все семь FD slots | Initial catalog/slot/kind/identity checks есть, renumbering допустим; A01/A07 нарушают lifetime/close-on-abort, B02 ограничивает post-check evidence |
| Executable до/после | Два вызова verify и final identity есть; execute-bit omission A06, native TOCTOU/write-exclusion C04 не закрыты |
| Reserve/lost spawn | Нормальный порядок и lost **dispatch** response проверены; потеря **registration** response A02 не обработана |
| Parent/child/helper death | Обычные modeled death дают unknown; B03/C05 требуют настоящих process/descendant facts; A05 открывает interruption gap |
| TERM/grace/drain/KILL/reap/close | В коде finite cleanup, only-owned target, clock/byte/iteration bounds; safe failure matrix проходит. Все ошибки гарантированно не сведены к successful cleanup: контрпримеры A02/A07 |
| Deadline/frozen/rollback | Poll конечен, final publication fence существует; native blocking/clock proof отсутствует. Cleanup deadline не разрешает evidence success после command deadline |
| Concurrency/circuit/immutable terminal | Registry/attempt/state locks и issued-object admission подтверждены в указанных scopes; A04/A05 нарушают terminal resource obligations. Durable restart/replay не реализован |
| Memory/output/message limits | Обычные buffers/frames/output bounded, caller allocations и RSS не заявляются ограниченными raw cap. Cancel queue — подтверждённый unbounded producer |

Проверенные negative matrices не являются исчерпывающим перебором всех interleavings. В частности, Linux FD/PID reuse, actual parent death и TOCTOU не переводятся в «проверены» по supplied fake observations.

## Расхождения с отчётом №20.1b-8i и существующим покрытием

| Заявление №20.1b-8i | Что подтверждает audit |
|---|---|
| «Parent-watch ... до завершения», positive full lifecycle | Final fence использует уже закрытый parent-watch; green fake не моделирует его недоступность (A01) |
| Lost-response ownership, reserve-before-dispatch | Проверена только потеря ответа после сохранения owner handle; registration-return окна теряют handle (A02) |
| «Verifier ... необратимо закрывается при первой ошибке» | Верно для accept error, неверно для failed finish и части decoder feed errors (A03) |
| «На direction ≤4096 messages», bounded accumulation | Не верно для cancel enqueue; повторный kill накапливает frames без cap (A04) |
| Interruption → bounded cleanup/immutable terminal | `BaseException` обходит control/registry/terminal finalization (A05) |
| Wrong executable identity/permissions | Mode без execute bits сохраняет positive; прежний OS reader имел отдельный bit check (A06) |
| Close-on-abort перед проверкой INVOKE, включая extra FD | Для nine-descriptor tuple учёт не установлен до cardinality refusal (A07) |
| Native identity/IPC/privileges unreviewed, hashes не MAC | Подтверждено. Документация корректно удерживает эти native blockers; review не объявляет их закрытыми |

Ни 130 H1 tests, ни исторические 1357 aggregate tests не исключили перечисленные контрпримеры. Существующее покрытие полезно для обычных faults, но исходный fake местами повторяет expected facts и допускает несовместимые FD lifetime. Подмена fail assertions на unknown без проверки cleanup set/owner catalog не решит эти проблемы.

## Воспроизводимость и целостность

Полный harness и evidence находятся только в изолированной временной директории:

- [test_h1_security_review.py](/tmp/h1-security-review/test_h1_security_review.py): SHA-256 `dcb91ac4395aa55fb14ec82bcc09d7a2f68e7317c71abcdef574909bf89ebc6e`;
- [observations.json](/tmp/h1-security-review/observations.json): SHA-256 `3b53aba434194021a8966c29bd4baa7e56914abf25517230236cf3145b09ad96`;
- [observations.log](/tmp/h1-security-review/observations.log), [safe.log](/tmp/h1-security-review/safe.log), [safe.json](/tmp/h1-security-review/safe.json), [integrity.json](/tmp/h1-security-review/integrity.json).

`/tmp` не является durable evidence storage; минимальные сценарии и фактические outcomes поэтому также включены в этот отчёт. Для повторения из repository root без import-path ambiguity:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import runpy
runpy.run_path('/tmp/h1-security-review/test_h1_security_review.py', run_name='__main__')
PY
```

Для безопасных ожиданий, которые **должны сейчас упасть** на 10 assertions:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import runpy, sys
sys.argv = ['test_h1_security_review.py', '--assert-safe']
runpy.run_path('/tmp/h1-security-review/test_h1_security_review.py', run_name='__main__')
PY
```

До аудита сохранён `/tmp/h1-security-review-baseline.json`, **321 artifact** шести Trusted Checker packages без caches и прежних `TRUSTED_CHECKER*.md`. SHA-256 всех 321 совпали после проверок. Dynamic source digest до/после одинаков:

`5cafe53a289b9ddf8800d91be5b03c13ca8218d138bd62726883060f1e6a8de0`.

В repository добавлен только этот отчёт. Production/tests/support/guards/native fixtures и прежние reports не редактировались; текущие findings не исправлялись. Tracked Git diff пуст, прежние untracked files сохранены. Предыдущие approvals не обновлялись и не переподписывались.

Native entry/primitive/helper не вызывались; их bodies изучены как source/AST. Harness исполнял in-memory fake/protocol code и denied physical gate; реальных diagnostic subprocess, namespace/FD-exec/network operations, SSH/VDS, deploy/commit/push/rebase не было. Файловые чтения source и запись отчёта/harness — обычные локальные audit operations; backend OS observer не запускался. Django/Ticket Sandbox/Ledger/Roadmap/achievements, БД, credentials и environment configuration не затрагивались.

## Приоритет исправлений и задачи H2

**P0 — восстановить ownership/lifetime перед дальнейшим расширением boundary.** Исправить A01 и A02, затем A07: watch lifetime, recoverable ownership при каждом partial effect, close-on-abort на transfer refusal. Критерий: strict fake positive без closed-FD reads; exhaustive resource accounting после failures; каждый непроверенный исход сохраняет cleanup_unproven/quarantine. Не переносить нынешний happy path в native helper.

**P1 — закрыть state/error/resource contract.** Исправить A03/A04/A05: latch на terminal parse errors, bounded/idempotent cancellation, finalization при interruption. Определить cancellation commit semantics B01. Проверять отсутствие новых dispatch, late repair и накопления памяти после terminal, не только result.reason.

**P2 — согласовать validation и независимый oracle.** Исправить A06, усилить lifetime/stat/generation observations fake согласно B02, определить helper exit/descendant semantics B03. Не выводить observations из expected input там, где тест обещает independent acquisition. Внести findings в documentation и повторить отдельный независимый review исправлений; затем подходящие offline regressions. Эти действия ещё не выполнены.

Предлагаемые отдельно scoped H2 задачи:

1. **H2 ownership/IPC design:** typed owned-resource escrow, partial-transfer cleanup, protected launch/control bootstrap, SCM_RIGHTS ancillary error accounting и authenticated peer/provenance contract. Не выдавать activation на основании H1 invocation/hash.
2. **H2 identity acquisition:** actual boot/PID/start/pidfd/nsfs/FD/NSID acquisition и pre/post fences, источник coherent stat/hash observations, проверка protected config/journal и inherited FD inventory. Добавить независимые fake fault cases до native implementation acceptance.
3. **H2 credentials/executable review:** exact kernel/build privilege-drop ordering, minimum privileges, FD-exec ABI, immutable loader/dependency/config closure и write exclusion. Не включать current guarded methods флагом.
4. **H2 lifecycle/recovery:** helper exit/signal и descendant containment, supervisor/reader crash, restart/durable replay/cancellation/quarantine, bounded terminate/drain/reap/close на всех registered и partially registered invocations.
5. **H2 evidence/timing:** bounded authenticated acquisition/export/storage и отдельный measured inventory/preflight timing profile. Full OS surfaces, ownership journal/installer/rollback, canonical recipe/CT/raw/byte proof и packet measurement остаются отдельными prerequisites/stages.
6. **Следующий review/run:** сначала устранить A-findings и провести review нового native composition; лишь затем рассматривать отдельное точное разрешение одного fixed read-only case на approved VM/build/namespace. Этот аудит не выдаёт такого разрешения и не начинает эксперимент.

**Итог: `H1 FIXES REQUIRED`.** Offline counterexamples достаточны для этого решения; native безопасность и физическая изоляция дополнительно остаются недоказанными. `V2-06a-OS BLOCKED`, `PhysicalProbeGate`, `physical_network_boundary_not_accepted` и false verification/physical flags сохраняются. Ни H2 implementation, ни автоматические исправления не начаты.
