"""Pure, bounded external-peer predicate. No network implementation is provided."""

from dataclasses import dataclass
from enum import StrEnum
import hashlib

from .contracts import ProbeResult, Reason, RuntimeObservation, Verdict
from .policy import POLICY, validate_policy


class TransportFault(StrEnum):
    NONE = "none"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    PROTOCOL = "protocol"
    INFRASTRUCTURE = "infrastructure"


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: bytes
    complete: bool = True


@dataclass(frozen=True)
class FakeTransport:
    response: HTTPResponse | None = None
    fault: TransportFault = TransportFault.NONE
    elapsed_seconds: float = 0.0


def evaluate_response(response, policy=POLICY):
    validate_policy(policy)
    if (type(response) is not HTTPResponse or type(response.status) is not int or
            not 100 <= response.status <= 599 or type(response.body) is not bytes or
            response.complete is not True):
        return ProbeResult(Verdict.UNKNOWN, Reason.PROTOCOL)
    status = response.status
    if len(response.body) > policy.max_body_bytes:
        return ProbeResult(Verdict.FAILED, Reason.OVERSIZED, status, policy.max_body_bytes + 1)
    length = len(response.body)
    # Hash only policy-matching bytes; never archive arbitrary target content.
    if 300 <= status < 400:
        return ProbeResult(Verdict.FAILED, Reason.REDIRECT, status, length)
    if status != policy.status:
        return ProbeResult(Verdict.FAILED, Reason.STATUS, status, length)
    if response.body.rstrip(b"\n") != policy.expected_body.encode("ascii"):
        return ProbeResult(Verdict.FAILED, Reason.BODY, status, length)
    return ProbeResult(Verdict.PASSED, Reason.HTTP_OBSERVED, status, length,
                       hashlib.sha256(response.body).hexdigest())


def probe(target, before, after, transport, policy=POLICY):
    """Fake response is evidence only after matching both identity observations."""
    validate_policy(policy)
    if (type(before) is not RuntimeObservation or type(after) is not RuntimeObservation or
            not before.matches(target) or not after.matches(target)):
        return ProbeResult(Verdict.UNKNOWN, Reason.IDENTITY)
    if type(transport) is not FakeTransport or type(transport.fault) is not TransportFault:
        return ProbeResult(Verdict.UNKNOWN, Reason.PROTOCOL)
    from math import isfinite
    if (type(transport.elapsed_seconds) not in (float, int) or
            not isfinite(transport.elapsed_seconds) or transport.elapsed_seconds < 0):
        return ProbeResult(Verdict.UNKNOWN, Reason.PROTOCOL)
    if transport.fault == TransportFault.TIMEOUT or transport.elapsed_seconds >= policy.http_timeout_seconds:
        return ProbeResult(Verdict.UNKNOWN, Reason.TIMEOUT)
    reasons = {TransportFault.TRANSPORT: Reason.TRANSPORT,
               TransportFault.PROTOCOL: Reason.PROTOCOL,
               TransportFault.INFRASTRUCTURE: Reason.INFRASTRUCTURE}
    if transport.fault != TransportFault.NONE:
        return ProbeResult(Verdict.UNKNOWN, reasons[transport.fault])
    return evaluate_response(transport.response, policy)
