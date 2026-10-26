"""Pure v2 live contract; v1/offline policy and profile digests are unchanged."""
from dataclasses import asdict, dataclass
from trusted_checker_shadow.policy import digest
from .profiles import TargetProfile, RunnerProfile, fixed


@dataclass(frozen=True)
class LivePolicy:
    policy_id: str = 'service-bind-localhost-live-peer-v2'
    version: int = 2
    schema_version: int = 2
    task: str = 'l1/service-bind-localhost'
    execution_mode: str = 'live_external_peer'
    criteria_scope: str = 'external_ipv4_http_only'
    protocol: str = 'http_ipv4'
    port: int = 8080
    path: str = '/'
    method: str = 'GET'
    status: int = 200
    expected_body: str = 'APP OK: customer service is running'
    max_body_bytes: int = 1024
    max_header_bytes: int = 8192
    normalization: str = 'trailing_lf_only'
    http_seconds: float = 2.0
    api_seconds: float = 3.0
    run_seconds: float = 8.0
    dns: bool = False
    proxy: bool = False
    redirect: bool = False
    egress_validation: str = 'bootstrap_readback_then_active_namespace_matrix_v2'
    runner_lifecycle: str = 'probe_result_finalize_handshake_v2'

    def __post_init__(self):
        fixed(self)

    @property
    def digest(self):
        return digest(asdict(self))


PATH_ENV = 'PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'


@dataclass(frozen=True)
class LiveTargetProfile(TargetProfile):
    profile_id: str = 'service-bind-localhost-target-v2'
    environment: tuple = (PATH_ENV, 'DEBIAN_FRONTEND=noninteractive')


@dataclass(frozen=True)
class LiveRunnerProfile(RunnerProfile):
    profile_id: str = 'service-bind-localhost-runner-v2'
    entrypoint: tuple = ('/usr/bin/python3', '-I', '/checker/service_bind_peer.py')
    environment: tuple = (PATH_ENV,)


LIVE_POLICY = LivePolicy()
LIVE_TARGET = LiveTargetProfile()
LIVE_RUNNER = LiveRunnerProfile()
LIVE_PREFLIGHT_CASES = ('bootstrap_default_deny', 'rules_readback_verified', 'topology_bound')


def live_matrix_digest(network, phase):
    from .profiles import EGRESS_CASES
    preflight = phase.value in ('enrollment', 'before_runner_create', 'before_runner_start')
    return digest({'profile': network.digest, 'method': LIVE_POLICY.egress_validation, 'phase': phase.value,
                   'cases': LIVE_PREFLIGHT_CASES if preflight else EGRESS_CASES,
                   'coverage': 'installed_bootstrap_rules_only' if preflight else 'active_live_namespace'})


def live_environment(approval, runner):
    base = LIVE_RUNNER.environment if runner else LIVE_TARGET.environment
    return tuple(sorted(base + (('TC_TARGET_IPV4='+approval.network.target_ipv4,) if runner else ())))
