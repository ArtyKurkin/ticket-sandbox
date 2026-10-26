"""Closed in-process simulation. No Docker adapter or real HTTP transport.

Counters are simulated operations, never evidence of physical runtime starts.
"""

from dataclasses import dataclass, field
from enum import StrEnum
import threading

from .contracts import RuntimeObservation, TargetIdentity, identity, require, uuid_value
from .predicate import FakeTransport, HTTPResponse


@dataclass(frozen=True)
class ExecutionTicket:
    run_uuid: str
    execution_uuid: str
    enrollment_digest: str
    policy_digest: str
    target: TargetIdentity

    def __post_init__(self):
        uuid_value(self.run_uuid)
        uuid_value(self.execution_uuid)
        identity(self.enrollment_digest)
        identity(self.policy_digest)
        require(type(self.target) is TargetIdentity, "ticket_invalid")


class IssueFault(StrEnum):
    NONE = "none"
    LOST_RESPONSE = "lost_response"
    WRONG_RECEIPT = "wrong_receipt"


class SimulatedUncertainty(Exception):
    pass


@dataclass(frozen=True)
class FakeScenario:
    transport: FakeTransport = field(default_factory=lambda: FakeTransport(
        HTTPResponse(200, b"APP OK: customer service is running\n")))
    before: RuntimeObservation | None = None
    after: RuntimeObservation | None = None
    issue_fault: IssueFault = IssueFault.NONE
    lose_start_response: bool = False
    cleanup_confirmed: bool = True

    def __post_init__(self):
        require(type(self.transport) is FakeTransport and type(self.issue_fault) is IssueFault,
                "fake_scenario_invalid")
        require(all(obs is None or type(obs) is RuntimeObservation for obs in (self.before, self.after)),
                "fake_observation_invalid")
        require(type(self.lose_start_response) is bool and type(self.cleanup_confirmed) is bool,
                "fake_scenario_invalid")


@dataclass(frozen=True)
class IssueReceipt:
    ticket: ExecutionTicket


@dataclass(frozen=True)
class ExecutionReceipt:
    ticket: ExecutionTicket
    before: RuntimeObservation
    after: RuntimeObservation
    transport: FakeTransport
    cleanup_confirmed: bool


@dataclass(frozen=True)
class CleanupReceipt:
    ticket: ExecutionTicket
    confirmed: bool


class FakeExecutionBackend:
    def __init__(self, scenario=None):
        self.scenario = scenario if scenario is not None else FakeScenario()
        require(type(self.scenario) is FakeScenario, "fake_backend_required")
        self.scenario.__post_init__()
        self._lock = threading.Lock()
        self._issued = {}
        self._started = set()
        self.issue_calls = 0
        self.simulated_creates = 0
        self.simulated_starts = 0
        # Test synchronization only: evaluate can be held without sleeping.
        self.observation_ready = threading.Event()
        self.observation_release = None

    def issue(self, ticket):
        require(type(ticket) is ExecutionTicket, "ticket_invalid")
        with self._lock:
            self.issue_calls += 1
            require(ticket.execution_uuid not in self._issued, "duplicate_backend_issue")
            self._issued[ticket.execution_uuid] = ticket
        if self.scenario.issue_fault == IssueFault.LOST_RESPONSE:
            raise SimulatedUncertainty()
        if self.scenario.issue_fault == IssueFault.WRONG_RECEIPT:
            from dataclasses import replace
            from uuid import uuid4
            return IssueReceipt(replace(ticket, execution_uuid=str(uuid4())))
        return IssueReceipt(ticket)

    def start(self, ticket):
        # Deliberately bounded: no callback, wait, transport or filesystem I/O.
        with self._lock:
            require(self._issued.get(ticket.execution_uuid) == ticket, "unissued_execution")
            require(ticket.execution_uuid not in self._started, "duplicate_backend_start")
            self._started.add(ticket.execution_uuid)
            self.simulated_creates += 1
            self.simulated_starts += 1
        if self.scenario.lose_start_response:
            raise SimulatedUncertainty()

    def observe(self, ticket):
        with self._lock:
            require(self._issued.get(ticket.execution_uuid) == ticket and
                    ticket.execution_uuid in self._started, "execution_missing")
        self.observation_ready.set()
        if self.observation_release is not None:
            require(self.observation_release.wait(10), "fake_test_gate_expired")
        return ExecutionReceipt(ticket, self.scenario.before or RuntimeObservation(ticket.target),
                                self.scenario.after or RuntimeObservation(ticket.target),
                                self.scenario.transport, self.scenario.cleanup_confirmed)

    def cleanup_receipt(self, ticket):
        # A read of a known exact simulated execution, never adoption/discovery.
        with self._lock:
            known = self._issued.get(ticket.execution_uuid) == ticket and ticket.execution_uuid in self._started
        return CleanupReceipt(ticket, known and self.scenario.cleanup_confirmed)
