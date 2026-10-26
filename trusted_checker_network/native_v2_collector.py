"""Default-OFF, process-local mock read-only capture boundary.

There is deliberately NO subprocess, namespace entry, FD open, proc/sys read,
netlink, clock discovery, signer or native transport implementation. Fake input
is trusted TEST SETUP, never an interface for accepting Runner-provided stdout.
Completion records alone are forgeable descriptions: admission additionally
requires the exact objects issued by this runner and collector instance.
"""
from dataclasses import dataclass, field
import hashlib
from threading import Lock

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as a


@dataclass(frozen=True, slots=True)
class MockReadEvent2:
    kind: str
    at: a.CaptureTime2
    reader: a.ReaderIdentity2
    data: bytes = field(default=b'', repr=False)
    exit_status: int | None = None

    def __post_init__(self):
        c._enum(self.kind, ('stdout', 'stderr', 'stdout_eof', 'stderr_eof', 'exit', 'complete',
                           'truncated', 'timeout', 'interrupted', 'process_died'))
        c._typed(self.at, a.CaptureTime2); c._typed(self.reader, a.ReaderIdentity2)
        a.require(type(self.data) is bytes, 'stream_invalid')
        a.require(self.kind in ('stdout', 'stderr') or self.data == b'', 'stream_invalid')
        if self.kind == 'exit': c._integer(self.exit_status, 0, 255)
        else: a.require(self.exit_status is None, 'stream_invalid')


@dataclass(frozen=True, slots=True)
class MockReadScript2:
    request: a.CaptureRequest2
    observed_binary: a.BinaryReference2
    observed_argv: tuple[str, ...]
    before: a.ReaderIdentity2
    started: a.CaptureTime2
    events: tuple[MockReadEvent2, ...]

    def __post_init__(self):
        for value, cls in ((self.request, a.CaptureRequest2), (self.observed_binary, a.BinaryReference2),
                           (self.before, a.ReaderIdentity2), (self.started, a.CaptureTime2)):
            c._typed(value, cls)
        a.require(type(self.observed_argv) is tuple and len(self.observed_argv) <= 16 and
                  all(type(v) is str and len(v) <= 256 for v in self.observed_argv), 'stream_invalid')
        a.rows(self.events, MockReadEvent2, 0, 4096)


class DeterministicMockTransport2:
    """Finite scripted pull transport; no generic execute/stdin/shell API.

    A future OS stream would implement bounded reads before allocation. Here the
    script bytes already belong to fixture setup. The runner limits retained
    buffers and rejects a fake that returns more than its requested read size.
    This fake does not attest actual binary hashes, principals, FDs or EOFs.
    """
    __slots__ = ('_scripts', '_used', '_active', '_index', '_closed', '_calls')

    def __init__(self, scripts):
        a.rows(scripts, MockReadScript2, 0)
        a.unique([s.request.capture_uuid for s in scripts])
        self._scripts = scripts; self._used = set(); self._active = None
        self._index = 0; self._closed = False; self._calls = []

    @property
    def calls(self): return tuple(self._calls)

    @property
    def closed(self): return self._closed

    def _open(self, request):
        a.require(not self._closed and self._active is None, 'stream_invalid')
        script = next((s for s in self._scripts if s.request == request), None)
        a.require(script is not None, 'missing_source')
        a.require(request.capture_uuid not in self._used, 'source_substitution')
        self._used.add(request.capture_uuid); self._active = script; self._index = 0
        self._calls.append((request.argv, request.namespace.fd_reference_uuid, request.digest))
        return script

    def _pull(self, max_bytes):
        a.require(max_bytes == a.CHUNK_BYTES and self._active is not None and not self._closed,
                  'stream_invalid')
        if self._index == len(self._active.events): return None
        event = self._active.events[self._index]; self._index += 1
        return event

    def _release(self):
        a.require(self._active is not None and self._index == len(self._active.events), 'stream_invalid')
        self._active = None

    def _close(self):
        # Only in-memory cancellation. No kill/FD close/cleanup of OS resources.
        self._active = None; self._closed = True


class ReadOnlyCommandRunner2:
    """Only an exact explicitly supplied fake can be bound in this revision.

    The fixed registry is the only command source. Native backend activation
    requires a separately reviewed implementation, not a boolean constructor.
    """
    __slots__ = ('_transport', '_session', '_issued', '_last', '_total')

    def __init__(self, transport):
        a.require(type(transport) is DeterministicMockTransport2, 'os_backend_dormant')
        self._transport = transport; self._session = None; self._issued = []
        self._last = None; self._total = 0

    def _bind(self, session):
        c._typed(session, a.CaptureSession2)
        a.require(self._session is None, 'replay_rejected')
        self._session = session; self._last = session.started

    def _identity(self, reader):
        if any(n.fd_state != 'open_in_mock_model' for n in reader.namespaces):
            raise c.ContractViolation2('v2_capture_namespace_fd_lost')
        a.require(reader == self._session.reader, 'identity_changed')

    def _time(self, at, started):
        a.require(at.monotonic_us >= self._last.monotonic_us and
                  at.wall_utc_us >= self._last.wall_utc_us, 'clock_rollback')
        a.require(at.monotonic_us <= self._session.deadline_monotonic_us and
                  at.wall_utc_us-self._session.started.wall_utc_us <= a.MAX_WINDOW_US,
                  'timing_unproven')
        a.require(at.monotonic_us-started.monotonic_us <= a.operation2(self._current_source).duration_us and
                  at.wall_utc_us-started.wall_utc_us <= a.operation2(self._current_source).duration_us,
                  'timeout')
        self._last = at

    @property
    def _current_source(self):
        return self._transport._active.request.source

    def _run(self, request, plan):
        c._typed(request, a.CaptureRequest2)
        a.require(self._session is not None and self._session.plan_digest == plan.digest and
                  len(self._issued) < len(plan.requests) and request == plan.requests[len(self._issued)],
                  'source_substitution')
        script = self._transport._open(request)
        self._identity(script.before)
        op = a.operation2(request.source)
        a.require(script.observed_argv == op.argv and
                  script.observed_binary == plan.binaries.binary(op.binary), 'binary_mismatch')
        self._time(script.started, script.started)
        stdout = bytearray(); stderr = bytearray(); eof = set(); exited = False; completed = False
        try:
            while True:
                event = self._transport._pull(a.CHUNK_BYTES)
                if event is None: break
                a.require(not completed, 'stream_invalid')
                self._identity(event.reader); self._time(event.at, script.started)
                kind = event.kind
                if kind in ('stdout', 'stderr'):
                    a.require(kind not in eof and not exited and len(event.data) <= a.CHUNK_BYTES,
                              'stream_invalid')
                    buffer = stdout if kind == 'stdout' else stderr
                    cap = op.stdout_cap if kind == 'stdout' else op.stderr_cap
                    a.require(len(buffer) + len(event.data) <= cap, kind + '_limit')
                    a.require(self._total + len(event.data) <= a.MAX_AGGREGATE, 'aggregate_limit')
                    self._total += len(event.data)
                    buffer.extend(event.data)
                elif kind in ('stdout_eof', 'stderr_eof'):
                    stream = kind[:-4]
                    a.require(stream not in eof and not exited, 'stream_invalid'); eof.add(stream)
                elif kind == 'exit':
                    a.require(not exited and eof == {'stdout', 'stderr'}, 'transport_incomplete')
                    a.require(event.exit_status == 0, 'nonzero_exit'); exited = True
                elif kind == 'complete':
                    a.require(exited and eof == {'stdout', 'stderr'}, 'transport_incomplete')
                    completed = True
                elif kind == 'truncated': raise c.ContractViolation2('v2_capture_transport_incomplete')
                else: raise c.ContractViolation2('v2_capture_' + kind)
            a.require(completed, 'transport_incomplete')
            raw, err = bytes(stdout), bytes(stderr)
            receipt = a.TransportCompletion2(self._session.session_uuid, request.digest, len(self._issued),
                                             hashlib.sha256(raw).hexdigest(), hashlib.sha256(err).hexdigest())
            artifact = a.CaptureArtifact2(self._session, request, script.observed_binary,
                         script.started, self._last, raw, err, receipt)
            self._issued.append(artifact); self._transport._release()
            return artifact
        finally:
            # Partial output is never returned as a completed artifact.
            stdout.clear(); stderr.clear()

    def _owns(self, artifacts):
        return len(artifacts) == len(self._issued) and all(x is y for x, y in zip(artifacts, self._issued))

    def _close(self): self._transport._close()


class FencedReadOnlyCollector2:
    """One process-local attempt. No journal, signatures, retry or OS authority.

    The caller supplies trusted offline plan/digest pins independently of fake
    stdout. A terminal result cannot be replaced by later reads or a new caller.
    Process restart/replay across instances needs future durable composition.
    """
    __slots__ = ('_plan', '_runner', '_session', '_enabled', '_terminal', '_manifest', '_killed', '_lock', '_state_lock')

    def __init__(self, plan, pinned_plan_digest, pinned_binary_manifest_digest, runner,
                 session_uuid, started, *, enabled=False):
        c._typed(plan, a.CapturePlan2)
        a.require(plan.digest == pinned_plan_digest and plan.binaries.digest == pinned_binary_manifest_digest,
                  'pin_mismatch')
        a.require(type(runner) is ReadOnlyCommandRunner2 and type(enabled) is bool, 'boundary_invalid')
        c._typed(started, a.CaptureTime2)
        self._plan = plan; self._runner = runner; self._enabled = enabled
        self._session = a.CaptureSession2(session_uuid, plan.digest, plan.reader, started,
                                         started.monotonic_us + a.MAX_WINDOW_US)
        self._terminal = None; self._manifest = None; self._killed = False
        self._lock = Lock()
        self._state_lock = Lock()

    @property
    def session(self): return self._session

    def kill(self):
        with self._state_lock:
            self._killed = True
            if self._terminal is None:
                self._terminal = a.CaptureValidation2(self._session, None, 'killed')
        self._runner._close()
        return self._terminal

    def capture(self):
        a.require(self._lock.acquire(blocking=False), 'capture_busy')
        try: return self._capture_once()
        finally: self._lock.release()

    def _capture_once(self):
        if self._terminal is not None: return self._terminal
        reason = 'evidence_invalid'
        try:
            if not self._enabled: reason = 'disabled'
            elif self._killed: reason = 'killed'
            else:
                self._runner._bind(self._session)
                artifacts = tuple(self._runner._run(request, self._plan) for request in self._plan.requests)
                manifest = a.CaptureManifest2(self._plan, self._session, artifacts)
                a.require(self._runner._owns(artifacts), 'receipt_unissued')
                with self._state_lock:
                    a.require(not self._killed and self._terminal is None, 'killed')
                    self._manifest = manifest
                    self._terminal = a.CaptureValidation2(self._session, manifest, 'mock_capture_preserved_os_unproven')
                return self._terminal
        except c.ContractViolation2 as error:
            code = str(error).removeprefix('v2_capture_')
            reason = code if code in a.REASONS else 'evidence_invalid'
        except Exception:
            # No exception text, stdout or stderr is exported through reason.
            reason = 'evidence_invalid'
        finally:
            self._runner._close()
        with self._state_lock:
            if self._terminal is None:
                self._terminal = a.CaptureValidation2(self._session, None, reason)
        return self._terminal

    def validate_manifest(self, candidate):
        c._typed(candidate, a.CaptureManifest2)
        a.require(self._manifest is not None and candidate is self._manifest and
                  self._runner._owns(candidate.artifacts), 'receipt_unissued')
        return self._terminal

    def admit_for_parsing(self, result):
        c._typed(result, a.CaptureValidation2)
        a.require(result is self._terminal and result.manifest is not None and not self._killed,
                  'result_unissued')
        self.validate_manifest(result.manifest)
        return result.manifest
