"""Regression tests for the test harness itself; never import a live SDK client."""
from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from trusted_checker_poc import broker, lifecycle, state
from . import support


class FixtureLifecycleTests(unittest.TestCase):
    def test_clock_moves_only_when_explicitly_advanced(self):
        clock = support.Clock()
        before = clock.time(), clock.monotonic()
        with patch.object(support.time, 'time', return_value=before[0]+1000):
            self.assertEqual((clock.time(),clock.monotonic()),before)
        clock.advance(2)
        self.assertEqual((clock.time(),clock.monotonic()),(before[0]+2,before[1]+2))

    def test_deadline_wakeup_is_separate_from_watchdog_failure(self):
        clock = support.Clock()
        inbox = clock.inbox()
        clock.advance()
        with self.assertRaises(queue.Empty):
            inbox.get(timeout=0.12)
        with patch.object(support, 'WATCHDOG', 0), self.assertRaises(AssertionError):
            support.Inbox().get(timeout=0.12)

    def test_advancing_clock_before_deadline_does_not_fake_timeout(self):
        clock = support.Clock()
        inbox = clock.inbox()
        clock.advance(2)
        inbox.put('worker result')
        self.assertEqual(inbox.get(timeout=5),'worker result')

    def test_scope_drains_final_writer_before_removing_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'last-write'
            with support.RuntimeScope() as scope:
                entered = threading.Event()
                gate = scope.workers.gate()
                def write():
                    entered.set()
                    gate.wait()
                    path.write_text('finished')
                worker = broker.threading.Thread(target=write,daemon=True)
                worker.start()
                self.assertTrue(entered.wait(support.WATCHDOG))
            self.assertFalse(worker.is_alive())
            self.assertEqual(path.read_text(),'finished')
        self.assertFalse(path.exists())

    def test_unhandled_worker_exception_is_a_test_failure(self):
        workers = support.Threads()
        hook = Mock()
        def crash():
            raise RuntimeError('fixture worker failed')
        with patch.object(threading, 'excepthook', hook):
            worker = workers.thread(target=crash)
            worker.start()
            with self.assertRaisesRegex(AssertionError,'unhandled test worker exception') as caught:
                workers.close()
        self.assertIsInstance(caught.exception.__cause__,RuntimeError)
        self.assertFalse(worker.is_alive())
        hook.assert_not_called()

    def test_simulated_crash_must_be_explicitly_expected(self):
        workers = support.Threads()
        workers.expected.append(SystemExit)
        worker = workers.thread(target=lambda: (_ for _ in ()).throw(SystemExit('simulated')))
        worker.start()
        workers.close()
        self.assertFalse(workers.expected)
        self.assertFalse(worker.is_alive())

    def test_patches_are_restored_after_join_failure(self):
        originals = broker.time, lifecycle.time, state.time, broker.threading
        def crash():
            raise RuntimeError('fixture')
        with self.assertRaises(AssertionError):
            with support.RuntimeScope() as scope:
                scope.workers.thread(target=crash).start()
        self.assertEqual((broker.time,lifecycle.time,state.time,broker.threading), originals)

    def test_assertion_failure_still_drains_workers_before_rmtree(self):
        observed = {}
        class FailingCase(support.WorkerTestCase):
            def runTest(case):
                observed['path'] = Path(case.temp.name)
                entered = threading.Event()
                gate = case.workers.gate()
                def write():
                    entered.set()
                    gate.wait()
                    (observed['path']/'late').write_text('last write')
                    observed['finished'] = True
                case.workers.thread(target=write).start()
                case.wait_for(entered)
                case.fail('deliberate fixture assertion')
        result = unittest.TestResult()
        FailingCase().run(result)
        self.assertEqual(len(result.failures),1)
        self.assertFalse(result.errors)
        self.assertTrue(observed['finished'])
        self.assertFalse(observed['path'].exists())

    def test_each_case_has_its_own_directory_clock_and_thread_group(self):
        observed = []
        class Case(support.WorkerTestCase):
            def runTest(case):
                observed.append((case.temp.name,case.clock,case.workers))
        result = unittest.TestResult()
        Case().run(result)
        Case().run(result)
        self.assertTrue(result.wasSuccessful())
        self.assertNotEqual(observed[0][0],observed[1][0])
        self.assertIsNot(observed[0][1],observed[1][1])
        self.assertIsNot(observed[0][2],observed[1][2])
