from dataclasses import replace

from trusted_checker_shadow.backend import FakeScenario
from trusted_checker_shadow.contracts import ProbeResult, Reason, Rejected, RuntimeObservation, Verdict
from trusted_checker_shadow.predicate import (FakeTransport, HTTPResponse, TransportFault,
                                             evaluate_response, probe)
from .support import ShadowCase


BODY = b"APP OK: customer service is running"


class PredicateTests(ShadowCase):
    def test_only_trailing_lf_are_removed(self):
        for body in (BODY, BODY+b"\n", BODY+b"\n\n", BODY+b"\n"*(1024-len(BODY))):
            with self.subTest(length=len(body)):
                self.assertEqual(evaluate_response(HTTPResponse(200, body)).result, Verdict.PASSED)
        for body in (b" "+BODY, BODY+b" ", BODY+b"\r\n", BODY+b"\t", b"\n"+BODY, BODY+b"\x00", b"\xff"):
            with self.subTest(body=body):
                self.assertEqual(evaluate_response(HTTPResponse(200, body)).reason, Reason.BODY)

    def test_status_strictly_200_and_redirect_not_followed(self):
        for status in (201, 204, 301, 302, 307, 308, 400, 500):
            with self.subTest(status=status):
                result = evaluate_response(HTTPResponse(status, BODY))
                self.assertEqual(result.result, Verdict.FAILED)
                self.assertEqual(result.reason, Reason.REDIRECT if 300 <= status < 400 else Reason.STATUS)

    def test_oversize_bounded_diagnostics_no_body_or_digest(self):
        result = evaluate_response(HTTPResponse(200, b"user secret" * 200))
        self.assertEqual(result.reason, Reason.OVERSIZED)
        self.assertEqual(result.response_bytes, 1025)
        self.assertIsNone(result.response_digest)

    def test_malformed_or_incomplete_protocol_is_unknown(self):
        for response in (None, {"status": 200, "body": BODY}, HTTPResponse(True, BODY),
                         HTTPResponse(600, BODY), HTTPResponse(200, "text"), HTTPResponse(200, BODY, False)):
            with self.subTest(response=response):
                self.assertEqual(evaluate_response(response).result, Verdict.UNKNOWN)

    def test_transport_timeout_protocol_and_infrastructure_uncertain(self):
        target = self.fixture.target
        observed = RuntimeObservation(target)
        for fault in (TransportFault.TIMEOUT, TransportFault.TRANSPORT, TransportFault.PROTOCOL,
                      TransportFault.INFRASTRUCTURE):
            with self.subTest(fault=fault):
                result = probe(target, observed, observed, FakeTransport(HTTPResponse(200, BODY), fault))
                self.assertEqual(result.result, Verdict.UNKNOWN)
        for elapsed in (2.0, 3.0):
            self.assertEqual(probe(target, observed, observed, FakeTransport(
                HTTPResponse(200, BODY), elapsed_seconds=elapsed)).reason, Reason.TIMEOUT)

    def test_unverified_target_can_never_return_pass_or_technical_fail(self):
        target = self.fixture.target
        for changed in (replace(target, daemon_id="fake-other"), replace(target, image_id="sha256:"+"f"*64),
                        replace(target, generation=self.request().sample_slot),
                        replace(target, network_id="e"*64), replace(target, ipv4="172.29.1.3")):
            for response in (HTTPResponse(200, BODY), HTTPResponse(500, b"bad")):
                with self.subTest(changed=changed, response=response):
                    self.assertEqual(probe(target, RuntimeObservation(target), RuntimeObservation(changed),
                                           FakeTransport(response)).reason, Reason.IDENTITY)
        for flags in ({"running": False}, {"paused": True}, {"restarting": True}, {"dead": True}):
            self.assertEqual(probe(target, RuntimeObservation(target, **flags), RuntimeObservation(target),
                FakeTransport(HTTPResponse(200, BODY))).result, Verdict.UNKNOWN)

    def test_result_reason_pair_cannot_promote_unknown(self):
        for reason in (Reason.TIMEOUT, Reason.IDENTITY, Reason.ISSUE, Reason.PROTOCOL, Reason.DEADLINE):
            with self.subTest(reason=reason), self.assertRaises(Rejected):
                ProbeResult(Verdict.PASSED, reason)

    def test_coordinator_applies_identity_bracket_and_fake_body_does_not_attest_app(self):
        report = self.run_scenario(FakeScenario(after=RuntimeObservation(replace(
            self.fixture.target, endpoint_id="e"*64))))
        self.assertEqual(report.verdict.reason, Reason.IDENTITY)
        report = self.run_scenario(FakeScenario())
        self.assertEqual(report.verdict.result, Verdict.PASSED)
        self.assertEqual(report.application_authenticity, "unproven")
