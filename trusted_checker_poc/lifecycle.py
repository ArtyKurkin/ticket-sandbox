"""Cooperative cancellation; durable create ownership outlives technical timeout."""
import threading
import time
from uuid import uuid4

from .contracts import AdapterError, InvalidRequest, Runner, full_id
from .diagnostics import PrepareTrace


class Lifecycle:
    def __init__(self, state, run_id, deadline, daemon_id, integration_id, diagnostic_sink=None):
        self.state, self.run_id, self.deadline = state, run_id, deadline
        self.daemon_id = daemon_id
        self.integration_id = integration_id or str(uuid4())
        self.cancelled = threading.Event()
        self.intent = None
        self.trace = PrepareTrace(run_id, diagnostic_sink)

    def _check_clock(self):
        if time.monotonic() >= self.deadline:
            raise AdapterError('runner_deadline_exceeded', 'timeout')

    def check(self):
        self._check_clock()
        row = self.state.read(self.run_id)
        self._check_clock()  # State/SQLite may have blocked past the deadline.
        if row and row['deadline'] is not None and row['deadline'] <= time.time():
            raise AdapterError('runner_deadline_exceeded', 'timeout')
        # Event also fences terminal closure; it is not proof of user cancellation.
        if self.cancelled.is_set() or not row or row['status'] != 'running':
            raise AdapterError('execution_cancelled', 'unknown_execution')

    def _state_gate(self, operation):
        try:
            return operation()
        except InvalidRequest as error:
            # Only translate known execution gates, not arbitrary validation or
            # storage failures. State checks the persisted deadline under lock.
            if str(error) == 'runner_deadline_exceeded':
                raise AdapterError('runner_deadline_exceeded', 'timeout') from None
            if str(error) == 'execution_cancelled':
                self._check_clock()
                raise AdapterError('execution_cancelled', 'unknown_execution') from None
            raise

    def begin(self, challenge):
        self.check()
        self.intent = self._state_gate(lambda: self.state.create_intent(
            self.run_id, self.daemon_id, self.integration_id, challenge))
        self.trace.intent_persisted = True
        return self.intent

    def received(self, container_id):
        # Deliberately allowed after cancellation: OWNERSHIP ONLY, never start.
        intent = self.intent
        runner = Runner(container_id, intent['image_id'], self.run_id, intent['scope'], False)
        self.trace.has_exact_id = full_id(container_id)
        response_event = self.trace.snapshot('create_response_received')  # Memory only.
        try:
            ownership = self.state.own_runner(self.run_id, runner, daemon_id=self.daemon_id,
                integration_id=self.integration_id, intent_id=intent['intent_id'],
                source={'kind': 'sdk_create_response'})
        except Exception as error:
            self.trace.write(response_event)
            self.trace.fail(error, ownership=True)
            raise
        # Persist exact ID FIRST. Diagnostics can now perform filesystem I/O.
        self.trace.ownership_persisted = True
        self.trace.write(response_event)
        self.trace.emit('ownership_persisted')
        return ownership

    def start(self, callback):
        self.check()
        def guarded():
            # No DB read inside start_once's transaction (SQLite is not reentrant).
            self._check_clock()
            if self.cancelled.is_set():
                raise AdapterError('execution_cancelled', 'unknown_execution')
            self.trace.start_invoked = True
            event = self.trace.snapshot('start_invoked')  # No diagnostic I/O before start.
            try:
                callback()
            finally:
                self.trace.write(event)  # Sink must never reenter SQLite.
        self._state_gate(lambda: self.state.start_once(self.run_id, guarded))
