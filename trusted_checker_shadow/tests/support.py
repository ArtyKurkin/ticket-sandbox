from pathlib import Path
import tempfile
import threading
import unittest
from uuid import uuid4

from trusted_checker_shadow.backend import FakeExecutionBackend
from trusted_checker_shadow.contracts import (CandidateMetadata, CreationProvenance,
                                             OperatorRequest, TargetIdentity)
from trusted_checker_shadow.coordinator import OfflineCoordinator
from trusted_checker_shadow.enrollment import FakeTrustedAuthority, ProvenanceFixture
from trusted_checker_shadow.policy import TASK, digest
from trusted_checker_shadow.state import ShadowStore


class Clock:
    def __init__(self):
        self.now = 2_000_000_000.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.now

    def advance(self, seconds=9):
        with self.lock:
            self.now += seconds


def fixture(attempt_id=1):
    target = TargetIdentity("fake-platform", attempt_id, 17, TASK, "fake-daemon", "a" * 64,
                            "sha256:" + "b" * 64, str(uuid4()), str(uuid4()),
                            "2026-10-19T10:00:00+00:00", 0, "c" * 64, "d" * 64,
                            "172.29.1.2", "offline-unit")
    return ProvenanceFixture(str(uuid4()), target,
                             CreationProvenance("fixture:created-target", digest({"fixture": attempt_id})),
                             "operator-unit")


class ShadowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.fixture = fixture()
        self.authority = FakeTrustedAuthority("fake-authority", (self.fixture,))
        self.enrollment = self.authority.enroll(CandidateMetadata(self.fixture.target, "offline_fixture"),
            fixture_uuid=self.fixture.fixture_uuid, operator_id="operator-unit")
        self.path = Path(self.tmp.name) / "state.shadow.sqlite3"
        self.store = ShadowStore(self.path)
        self.backend = FakeExecutionBackend()
        self.coordinator = self.make_coordinator()

    def make_coordinator(self, backend=None, authority=None, store=None, operator_id="operator-unit"):
        return OfflineCoordinator(store or self.store, authority or self.authority, backend or self.backend,
                                  operator_id=operator_id, clock=self.clock)

    def request(self, **kwargs):
        return OperatorRequest(str(uuid4()), self.enrollment.enrollment_uuid, self.fixture.target.attempt_id,
                               self.fixture.target.owner_id, self.fixture.target.scope,
                               str(uuid4()), self.clock() + 8, **kwargs)

    def enabled(self):
        self.coordinator.set_enabled(True)
        return self.coordinator

    def run_scenario(self, scenario, **request_kwargs):
        self.backend = FakeExecutionBackend(scenario)
        self.coordinator = self.make_coordinator()
        self.enabled()
        return self.coordinator.submit(self.request(**request_kwargs), self.enrollment)
