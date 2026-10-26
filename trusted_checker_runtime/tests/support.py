from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import hmac
from pathlib import Path
import tempfile
from uuid import uuid4

from trusted_checker_shadow.policy import POLICY, digest
from trusted_checker_runtime.attestation import Attestation, ReceiptVerifier, ROLES, SignerGrant, signing_bytes
from trusted_checker_runtime.authority import RuntimeTargetAuthority
from trusted_checker_runtime.boundary import capture_create_response
from trusted_checker_runtime.contracts import (
    AttemptReference, CleanupConfirmation, DaemonIdentity,
    DaemonObservation, EgressEvidence, EgressValidation, Endpoint, IdentityObservation,
    NetworkEvidence, Phase, ProbeResponse, ProvisionRequest, Resource, RunRequest,
    RunnerObservation, RuntimeApproval, TargetSnapshot, expected_config)
from trusted_checker_runtime.journal import RuntimeJournal, body
from trusted_checker_runtime.profiles import EGRESS_CASES, NetworkProfile, matrix_digest, rules_digest


def uuid():
    return str(uuid4())


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 19, 10, tzinfo=timezone.utc).timestamp()

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds

    def docker(self):
        return datetime.fromtimestamp(self.value, timezone.utc).isoformat().replace('+00:00', 'Z')


class Lab:
    """Trusted TEST setup, never a live adapter or existing target locator."""
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.scope = 'test-shadow-unit'
        self.grants = tuple(SignerGrant(role+':unit', role, (self.scope,), bytes([index])*32)
                            for index, role in enumerate(('operator', 'adapter', 'egress', 'validator', 'recovery'), 1))
        self.verifier = ReceiptVerifier(self.grants)
        self.daemon = DaemonIdentity('daemon-unit', 'endpoint:unit', '1'*64, uuid())
        self.network = NetworkProfile('c'*64, 'tc-shadow-pilot-unit', '172.30.0.0/24',
                                      '172.30.0.2', '172.30.0.3', 'egress:unit')
        self.approval = RuntimeApproval(uuid(), 'operator:unit', self.scope, self.daemon,
            'sha256:'+'a'*64, 'sha256:'+'b'*64, '2'*64, self.network, self.clock(), self.clock()+3600)
        self.attempt = AttemptReference('test-instance', 41, 7)
        self.journal = RuntimeJournal(Path(self.tmp.name)/'unit.runtime.sqlite3')
        self.authority = self.new_authority()
        self.authority.register_approval(self.sign(self.approval))
        self.creates = self.starts = 0
        self.target_id, self.runner_id = 'd'*64, 'e'*64
        self.target_endpoint = Endpoint(self.target_id, self.network.network_id, 'f'*64, self.network.target_ipv4)
        self.runner_endpoint = Endpoint(self.runner_id, self.network.network_id, '9'*64, self.network.runner_ipv4)

    def close(self):
        self.tmp.cleanup()

    def new_authority(self, daemon=None):
        return RuntimeTargetAuthority(self.journal, self.verifier, operator_principal='operator:unit',
                                      approved_daemon=daemon or self.daemon, clock=self.clock)

    def sign(self, payload):
        role = ROLES[type(payload)]
        grant = next(g for g in self.grants if g.role == role)
        return Attestation(payload, grant.principal,
                           hmac.new(grant.key, signing_bytes(payload, grant.principal), hashlib.sha256).hexdigest())

    def common(self, context):
        return dict(receipt_uuid=uuid(), context_uuid=context, scope=self.scope, observed_at=self.clock())

    def daemon_receipt(self, context, **changes):
        return self.sign(DaemonObservation(**self.common(context), daemon=replace(self.daemon, **changes)))

    def provision(self):
        self.authority.set_enabled(True)
        self.request = ProvisionRequest(uuid(), self.approval.approval_uuid, self.attempt)
        self.intent = self.authority.provision(self.request)
        return self.intent

    def dispatch(self, intent):
        permit = self.authority.begin_create(intent, self.daemon_receipt(intent.intent_uuid))
        with self.authority.create_fence(permit) as issued:
            assert issued == intent
            self.creates += 1
        return permit

    def response(self, intent, permit):
        return self.sign(capture_create_response(intent, permit,
            {'Id': self.target_id if intent.resource == Resource.TARGET else self.runner_id, 'Warnings': []},
            daemon=self.daemon, receipt_uuid=uuid(), observed_at=self.clock()))

    def owned_target(self):
        intent = self.provision()
        self.target_permit = self.dispatch(intent)
        self.target_response = self.response(intent, self.target_permit)
        self.authority.record_create_response(self.target_permit, self.target_response)
        with self.authority.target_start_fence(intent.intent_uuid, self.daemon_receipt(intent.intent_uuid)):
            self.starts += 1
        self.target = TargetSnapshot(self.attempt, intent.runtime_binding_uuid, intent.generation_uuid,
            self.daemon, self.target_id, intent.image_id, self.clock.docker(), 0, True, False, False, False,
            (self.target_endpoint,), expected_config(self.approval, Resource.TARGET), POLICY.digest)
        return intent

    def bundle(self, context, phase, target=None, runner_endpoint=None):
        target = target or self.target
        identity = self.sign(IdentityObservation(**self.common(context), phase=phase, target=target))
        network = self.sign(NetworkEvidence(**self.common(context), phase=phase, daemon=self.daemon,
            network_profile_digest=self.network.digest, internal=True, driver='bridge',
            endpoints=target.endpoints+((runner_endpoint,) if runner_endpoint is not None else ())))
        egress = self.sign(EgressEvidence(**self.common(context), phase=phase, target_digest=digest(body(target)),
            runner_id=None if phase in (Phase.ENROLL, Phase.BEFORE_CREATE) else self.runner_id,
            daemon=self.daemon, network_profile_digest=self.network.digest,
            enforcement_reference=self.network.enforcement_reference, rules_digest=rules_digest(self.network),
            validation_digest='3'*64, default_deny=True, only_target_8080=True,
            denies_host_metadata_platform=True, anti_spoofing=True))
        validation = self.sign(EgressValidation(**self.common(context), phase=phase,
            enforcement_receipt_digest=egress.digest, matrix_digest=matrix_digest(self.network), passed_cases=EGRESS_CASES))
        return identity, network, egress, validation

    def enrolled(self):
        intent = self.owned_target()
        self.authority.verify_provision(intent.intent_uuid, *self.bundle(intent.intent_uuid, Phase.ENROLL))
        self.enrollment = self.authority.enroll(intent.intent_uuid)
        return self.enrollment

    def reserve(self, ordinary=None):
        self.run_request = RunRequest(uuid(), self.enrollment.enrollment_uuid, self.attempt, uuid(), ordinary)
        self.run = self.authority.reserve_run(self.run_request, self.enrollment)
        return self.run

    def run_intent(self):
        return self.authority.runner_create_intent(self.run)

    def owned_runner(self):
        self.reserve()
        self.authority.check_target(self.run, Phase.BEFORE_CREATE, *self.bundle(self.run, Phase.BEFORE_CREATE))
        intent = self.run_intent()
        self.runner_permit = self.dispatch(intent)
        self.runner_response = self.response(intent, self.runner_permit)
        self.authority.record_create_response(self.runner_permit, self.runner_response)
        return self.run

    def runner(self, state='created', **changes):
        value = RunnerObservation(**self.common(self.run), daemon=self.daemon, container_id=self.runner_id,
            image_id=self.approval.runner_image_id, config=expected_config(self.approval, Resource.RUNNER),
            state=state, started_at=None if state == 'created' else self.runner_started_at,
            restart_count=0, endpoint=None if state == 'created' else self.runner_endpoint)
        return self.sign(replace(value, **changes))

    def start_ready(self):
        self.owned_runner()
        self.authority.check_target(self.run, Phase.BEFORE_START, *self.bundle(self.run, Phase.BEFORE_START), runner=self.runner())
        self.start_permit = self.authority.authorize_start(self.run)
        return self.start_permit

    def running(self):
        self.start_ready()
        with self.authority.start_fence(self.start_permit):
            self.starts += 1
        self.runner_started_at = self.clock.docker()
        self.authority.record_runner_live(self.run, self.runner('running'))
        return self.run

    def probe(self, **changes):
        value = ProbeResponse(**self.common(self.run), runner_id=self.runner_id,
            runner_image_id=self.approval.runner_image_id, checker_source_digest=self.approval.checker_source_digest,
            target_digest=digest(body(self.target)), policy_digest=POLICY.digest, status=200,
            body=b'APP OK: customer service is running\n')
        return self.sign(replace(value, **changes))

    def finish(self, **changes):
        self.authority.record_probe(self.run, self.probe(**changes))
        for phase in (Phase.AFTER_PROBE, Phase.BEFORE_PUBLISH):
            self.authority.check_target(self.run, phase, *self.bundle(self.run, phase, runner_endpoint=self.runner_endpoint),
                                        runner=self.runner('running'))
        return self.authority.publish(self.run)

    def cleanup(self, resource=Resource.RUNNER):
        context = self.run if resource == Resource.RUNNER else self.intent.intent_uuid
        with self.journal.transaction() as db:
            owned = self.authority._ownership(db, resource, context)
        return self.sign(CleanupConfirmation(**self.common(context), resource=resource, daemon=self.daemon,
            container_id=owned['receipt']['container_id'], ownership_digest=owned['attestation_digest'],
            removal_evidence_digest='4'*64, outcome='removed_confirmed'))
