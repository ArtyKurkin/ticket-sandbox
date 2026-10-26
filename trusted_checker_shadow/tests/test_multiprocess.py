"""Actual independent coordinator processes; still only simulated execution."""

import multiprocessing

from trusted_checker_shadow.backend import FakeExecutionBackend
from trusted_checker_shadow.contracts import CandidateMetadata
from trusted_checker_shadow.coordinator import OfflineCoordinator
from trusted_checker_shadow.enrollment import FakeTrustedAuthority
from trusted_checker_shadow.state import ShadowStore
from .support import Clock, ShadowCase


def submit_child(path, fixture, request, barrier, outbox):
    authority = FakeTrustedAuthority("fake-authority", (fixture,))
    enrollment = authority.enroll(CandidateMetadata(fixture.target, "offline_fixture"),
                                 fixture_uuid=fixture.fixture_uuid, operator_id="operator-unit")
    backend = FakeExecutionBackend()
    coordinator = OfflineCoordinator(ShadowStore(path), authority, backend,
                                     operator_id="operator-unit", clock=Clock())
    barrier.wait(timeout=10)
    result = coordinator.submit(request, enrollment)
    outbox.put((result.shadow_run_uuid, result.execution_uuid, backend.issue_calls, backend.simulated_starts))


class ProcessTests(ShadowCase):
    def test_concurrent_processes_use_one_mapping_issue_and_start(self):
        self.enabled()
        ctx = multiprocessing.get_context("spawn")
        barrier, outbox = ctx.Barrier(2), ctx.Queue()
        request = self.request()
        children = [ctx.Process(target=submit_child, args=(self.path, self.fixture, request, barrier, outbox))
                    for _ in range(2)]
        try:
            for child in children:
                child.start()
            results = [outbox.get(timeout=10) for _ in children]
            for child in children:
                child.join(10)
                self.assertFalse(child.is_alive())
                self.assertEqual(child.exitcode, 0)
            self.assertEqual(len({row[0] for row in results}), 1)
            self.assertEqual(len({row[1] for row in results}), 1)
            self.assertEqual(sum(row[2] for row in results), 1)
            self.assertEqual(sum(row[3] for row in results), 1)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                if child.pid is not None:
                    child.join(10)
            outbox.close()
            outbox.join_thread()
