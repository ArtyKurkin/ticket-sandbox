"""Review proposal only. Does not alter or authorize the live v2 eight seconds."""
from dataclasses import dataclass,asdict
from trusted_checker_runtime.profiles import require,fixed
from trusted_checker_shadow.policy import digest


@dataclass(frozen=True)
class TimingProposal:
    profile_id: str = 'network-validated-peer-budget-v3-proposal'
    mode: str = 'proposal_not_execution_authority'
    docker_create: float = 3.0
    docker_start: float = 3.0
    live_handshake: float = 1.0
    activation_readback: float = 2.0
    before_probe_matrix: float = 2.0
    http: float = 2.0
    after_probe_matrix: float = 2.0
    publication_matrix: float = 2.0
    finish_final_check: float = 3.0
    bootstrap_restore: float = 2.0
    cleanup: float = 3.0
    scheduling_margin: float = 5.0
    total: float = 30.0

    def __post_init__(self): fixed(self)
    @property
    def digest(self): return digest(asdict(self))
    def fits(self, seconds):
        require(type(seconds) in (int,float) and type(seconds) is not bool and seconds >= self.total,
                'network_budget_insufficient')
        return True


PROPOSAL = TimingProposal()
