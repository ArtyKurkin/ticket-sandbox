"""Test-only clocks and owned threads; no changes to broker/runtime contracts."""
from concurrent.futures import Future
from contextlib import ExitStack
import queue
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from trusted_checker_poc import broker, lifecycle, recovery, state

# Failure watchdog only. It never advances a tested deadline or returns a pass.
WATCHDOG = 30


class Clock:
    def __init__(self):
        self.wall = time.time()
        self.offset = 0
        self.lock = threading.Lock()
        self.inboxes = []

    def time(self):
        with self.lock:
            return self.wall + self.offset

    def monotonic(self):
        with self.lock:
            return 100 + self.offset

    def advance(self, seconds=60):
        with self.lock:
            self.offset += seconds
            inboxes = list(self.inboxes)
        for inbox in inboxes:
            inbox.expire()

    def inbox(self, **kwargs):
        result = Inbox(self)
        with self.lock:
            self.inboxes.append(result)
        return result


class Inbox:
    EXPIRED = object()

    def __init__(self, clock=None):
        self.items = queue.Queue()
        self.clock = clock or Clock()
        self.created = self.clock.monotonic()

    def put(self, item):
        self.items.put(item)

    def expire(self):
        self.items.put(self.EXPIRED)

    def get(self, timeout=None):
        deadline = self.created + timeout if timeout is not None else None
        while True:
            try:
                item = self.items.get(timeout=WATCHDOG)
            except queue.Empty:
                raise AssertionError('worker did not produce a result or controlled expiry') from None
            if item is not self.EXPIRED:
                return item
            if deadline is not None and self.clock.monotonic() >= deadline:
                raise queue.Empty


class Threads:
    def __init__(self):
        self.threads = []
        self.gates = []
        self.errors = []
        self.expected = []
        self.lock = threading.Lock()

    def thread(self, *, target, args=(), kwargs=None, **options):
        def checked():
            try:
                target(*args, **(kwargs or {}))
            except BaseException as error:
                with self.lock:
                    self.errors.append(error)
        result = threading.Thread(target=checked, **options)
        with self.lock:
            self.threads.append(result)
        return result

    def gate(self):
        gate = threading.Event()
        self.gates.append(gate)
        return gate

    def submit(self, callback, *args, **kwargs):
        future = Future()
        def invoke():
            try:
                future.set_result(callback(*args, **kwargs))
            except BaseException as error:
                future.set_exception(error)
                raise
        self.thread(target=invoke, daemon=True).start()
        return future

    def join(self):
        deadline = time.monotonic() + WATCHDOG
        # A worker may spawn a bounded audit reader before it finishes.
        index = 0
        while index < len(self.threads):
            thread = self.threads[index]
            thread.join(max(0, deadline - time.monotonic()))
            if thread.is_alive():
                raise AssertionError('test-owned thread did not finish; temporary files must be retained')
            index += 1
        errors, self.errors = self.errors, []
        for error in errors:
            matching = next((i for i, kind in enumerate(self.expected) if isinstance(error, kind)), None)
            if matching is None:
                raise AssertionError('unhandled test worker exception') from error
            self.expected.pop(matching)

    def close(self):
        for gate in self.gates:
            gate.set()
        self.join()
        if self.expected:
            raise AssertionError('expected worker exception did not occur')


class RuntimeScope:
    """Patch only module references, never global threading/time or Docker."""
    def __init__(self):
        self.clock = Clock()
        self.workers = Threads()
        self.stack = ExitStack()

    def __enter__(self):
        for module in (broker, lifecycle, state):
            self.stack.enter_context(patch.object(module, 'time', self.clock))
        for module in (broker, recovery):
            self.stack.enter_context(patch.object(module, 'threading', SimpleNamespace(Thread=self.workers.thread)))
        self.stack.enter_context(patch.object(broker, 'queue',
            SimpleNamespace(Queue=self.clock.inbox, Empty=queue.Empty)))
        return self

    def __exit__(self, *exc):
        try:
            self.workers.close()
        finally:
            self.stack.close()


class WorkerTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.scope = RuntimeScope().__enter__()
        self.clock, self.workers = self.scope.clock, self.scope.workers
        self.addCleanup(self.finish_resources)

    def finish_resources(self):
        try:
            self.scope.__exit__(None, None, None)
        finally:
            if any(thread.is_alive() for thread in self.workers.threads):
                # A failed watchdog must not race rmtree against a live writer.
                self.temp._finalizer.detach()
            else:
                self.temp.cleanup()

    def wait_for(self, event):
        self.assertTrue(event.wait(WATCHDOG), 'worker did not reach synchronization point')
