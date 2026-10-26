"""Separate HTTP policy proposal; neither authority nor runner accepts it."""
from dataclasses import dataclass,asdict
from trusted_checker_runtime.profiles import fixed
from trusted_checker_shadow.policy import digest
from trusted_checker_network.timing import PROPOSAL
from .contracts import PROFILE


@dataclass(frozen=True)
class LiveV3Proposal:
    policy_id: str = 'service-bind-localhost-physical-peer-v3-proposal'
    version: int = 3
    mode: str = 'proposal_only_do_not_execute'
    criteria_scope: str = 'external_ipv4_http_only'
    port: int = 8080
    path: str = '/'
    status: int = 200
    body: str = 'APP OK: customer service is running'
    normalization: str = 'trailing_lf_only'
    body_limit: int = 1024
    http_seconds: float = 2.0
    proposed_run_seconds: float = 30.0
    cleanup_stage_seconds: float = 3.0
    cleanup_separate: bool = True
    timing_reference: str = PROPOSAL.digest
    physical_profile: str = PROFILE.digest
    activatable: bool = False
    def __post_init__(self):fixed(self)
    @property
    def digest(self):return digest(asdict(self))


LIVE_V3_PROPOSAL=LiveV3Proposal()
