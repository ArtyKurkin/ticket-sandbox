"""Deterministic deadline/cancellation regression tests; no Docker operations."""
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from trusted_checker_poc.broker import Broker
from trusted_checker_poc.contracts import AdapterError, InvalidRequest
from trusted_checker_poc.lifecycle import Lifecycle
from trusted_checker_poc.registry import Registry, POLICY_ID
from trusted_checker_poc.state import State
from .fakes import IMAGE, FakeAdapter, fixture_target
from . import support
from contextlib import contextmanager


class LifecycleReasonTests(unittest.TestCase):
    def setUp(self):
        self.clock = SimpleNamespace(monotonic=Mock(return_value=100),time=Mock(return_value=200))
        patcher = patch('trusted_checker_poc.lifecycle.time',self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = Mock()
        self.state.read.return_value = {'status':'running','deadline':201}
        self.lifecycle = Lifecycle(self.state,'test-run',101,'fake-daemon',None)

    def assert_reason(self, callback, reason, failure):
        with self.assertRaises(AdapterError) as caught:
            callback()
        self.assertEqual(caught.exception.reason,reason)
        self.assertEqual(caught.exception.failure_class,failure)

    def test_local_deadline_is_timeout_including_exact_boundary(self):
        self.clock.monotonic.return_value = 101
        self.assert_reason(self.lifecycle.check,'runner_deadline_exceeded','timeout')
        self.state.read.assert_not_called()

    def test_persisted_deadline_expires_before_later_local_wait_deadline(self):
        self.clock.time.return_value = 201
        self.assert_reason(self.lifecycle.check,'runner_deadline_exceeded','timeout')

    def test_time_spent_reading_state_is_included(self):
        self.clock.monotonic.side_effect = [100,101]
        self.assert_reason(self.lifecycle.check,'runner_deadline_exceeded','timeout')
        self.state.read.assert_called_once()

    def test_cancellation_before_deadlines_is_distinct(self):
        self.lifecycle.cancelled.set()
        self.assert_reason(self.lifecycle.check,'execution_cancelled','unknown_execution')

    def test_closed_execution_before_deadline_is_not_a_timeout(self):
        self.state.read.return_value['status'] = 'finished'
        self.assert_reason(self.lifecycle.check,'execution_cancelled','unknown_execution')

    def test_expired_deadline_is_not_hidden_by_generic_cancellation_event(self):
        self.lifecycle.cancelled.set()
        self.clock.time.return_value = 201
        self.assert_reason(self.lifecycle.check,'runner_deadline_exceeded','timeout')

    def test_expiry_inside_create_intent_state_gate_preserves_timeout(self):
        self.state.create_intent.side_effect = InvalidRequest('runner_deadline_exceeded')
        self.assert_reason(lambda:self.lifecycle.begin('a'*64),'runner_deadline_exceeded','timeout')

    def test_cancelled_create_intent_state_gate_preserves_cancellation(self):
        self.state.create_intent.side_effect = InvalidRequest('execution_cancelled')
        self.assert_reason(lambda:self.lifecycle.begin('a'*64),'execution_cancelled','unknown_execution')

    def test_expiry_inside_start_state_gate_never_calls_sdk_start(self):
        self.state.start_once.side_effect = InvalidRequest('runner_deadline_exceeded')
        sdk_start = Mock()
        self.assert_reason(lambda:self.lifecycle.start(sdk_start),'runner_deadline_exceeded','timeout')
        sdk_start.assert_not_called()

    def test_local_deadline_rechecked_inside_start_fence(self):
        def locked_gate(run_id, callback):
            self.clock.monotonic.return_value = 101
            callback()
        self.state.start_once.side_effect = locked_gate
        sdk_start = Mock()
        self.assert_reason(lambda:self.lifecycle.start(sdk_start),'runner_deadline_exceeded','timeout')
        sdk_start.assert_not_called()

    def test_cancellation_rechecked_inside_start_fence(self):
        def locked_gate(run_id, callback):
            self.lifecycle.cancelled.set()
            callback()
        self.state.start_once.side_effect = locked_gate
        sdk_start = Mock()
        self.assert_reason(lambda:self.lifecycle.start(sdk_start),'execution_cancelled','unknown_execution')
        sdk_start.assert_not_called()

    def test_unrelated_validation_and_storage_errors_are_not_cancellation(self):
        self.state.create_intent.side_effect = InvalidRequest('create_already_requested')
        with self.assertRaisesRegex(InvalidRequest,'create_already_requested'):
            self.lifecycle.begin('a'*64)
        self.state.read.side_effect = sqlite3.OperationalError('storage unavailable')
        with self.assertRaises(sqlite3.OperationalError):
            self.lifecycle.check()


class BrokerDeadlineTests(support.WorkerTestCase):
    def setUp(self):
        super().setUp()
        self.state = State(Path(self.temp.name)/'state.sqlite')
        self.target = fixture_target()
        self.state.enroll(self.target)
        self.adapter = FakeAdapter(self.target)
        self.registry = Registry(runner_image_id=IMAGE,timeout=5)
        self.broker = Broker(self.state,self.registry,self.adapter,scope=self.target.scope)
        self.request = self.broker.issue(self.target.container_id,self.target.owner,POLICY_ID)
        self.wall = time.time()
        self.clock = SimpleNamespace(monotonic=lambda:100,time=lambda:self.wall)

    @contextmanager
    def clocks(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for module in ('broker','state','lifecycle'):
                stack.enter_context(patch('trusted_checker_poc.'+module+'.time',self.clock))
            try:
                yield
            finally:
                self.workers.join()

    def test_worker_persisted_deadline_timeout_arrives_before_coordinator_timer(self):
        inspect_target = self.adapter.inspect_target
        def slow_admission_path(identity):
            self.wall += 6  # Persisted admission budget elapsed; monotonic wait still future.
            return inspect_target(identity)
        with self.clocks(), patch.object(self.adapter,'inspect_target',side_effect=slow_admission_path):
            result = self.broker.execute(self.request,owner=self.target.owner)
        self.assertEqual((result['result'],result['reason'],result['failure_class']),
                         ('unknown','runner_deadline_exceeded','timeout'))
        self.assertEqual(self.adapter.prepares,0)
        self.assertEqual(self.adapter.physical_runs,0)
        self.assertEqual(self.broker.execute(self.request,owner=self.target.owner),result)

    def test_explicit_cancellation_before_deadline_is_unknown_not_failed(self):
        original_prepare = self.adapter.prepare
        def cancel_after_create(plan):
            runner = original_prepare(plan)
            plan.lifecycle.cancelled.set()
            return runner
        with self.clocks(), patch.object(self.adapter,'prepare',side_effect=cancel_after_create):
            result = self.broker.execute(self.request,owner=self.target.owner)
        self.assertEqual((result['result'],result['reason'],result['failure_class']),
                         ('unknown','execution_cancelled','unknown_execution'))
        self.assertEqual(self.adapter.physical_runs,0)

    def test_state_deadline_gates_do_not_invoke_create_or_start(self):
        with self.clocks():
            self.state.admit(self.request,self.target.owner,2,self.wall+1)
            self.wall += 1
            with self.assertRaisesRegex(InvalidRequest,'runner_deadline_exceeded'):
                self.state.create_intent(self.request.run_id,'fake-daemon','fake-session','a'*64)
            sdk_start = Mock()
            with self.assertRaisesRegex(InvalidRequest,'runner_deadline_exceeded'):
                self.state.start_once(self.request.run_id,sdk_start)
            sdk_start.assert_not_called()
            self.assertIsNone(self.state.receipt('create_intents',self.request.run_id))
            with self.state.db() as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM runner_starts').fetchone()[0],0)

    def test_state_closure_before_deadline_is_distinct(self):
        with self.clocks():
            self.state.admit(self.request,self.target.owner,2,self.wall+5)
            self.state.finish(self.request.run_id,{'result':'unknown','reason':'execution_cancelled'})
            with self.assertRaisesRegex(InvalidRequest,'execution_cancelled'):
                self.state.create_intent(self.request.run_id,'fake-daemon','fake-session','a'*64)
            sdk_start = Mock()
            with self.assertRaisesRegex(InvalidRequest,'execution_cancelled'):
                self.state.start_once(self.request.run_id,sdk_start)
            sdk_start.assert_not_called()

    def test_infrastructure_failure_stays_unknown(self):
        with patch.object(self.adapter,'inspect_target',side_effect=sqlite3.OperationalError('private path')):
            result = self.broker.execute(self.request,owner=self.target.owner)
            self.workers.join()
        self.assertEqual((result['result'],result['failure_class']),('unknown','infrastructure'))
        self.assertNotIn('private path',str(result))
        self.assertEqual(self.adapter.physical_runs,0)

    def test_existing_terminal_receipt_is_returned_without_reclassification(self):
        self.state.admit(self.request,self.target.owner,2,self.scope.clock.time()-1)
        row = self.state.read(self.request.run_id)
        saved = self.broker._result(row,self.registry.get(POLICY_ID),'execution_cancelled',failure='unknown_execution')
        self.state.finish(self.request.run_id,saved)
        self.assertEqual(self.broker.execute(self.request,owner=self.target.owner),saved)
        self.assertEqual(self.adapter.prepares,0)
        self.assertEqual(self.adapter.physical_runs,0)
