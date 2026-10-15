"""Trusted deployment configuration, never constructed from a run request."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

POLICY_ID = 'synthetic-ipv4-v1'


@dataclass(frozen=True)
class Policy:
    policy_id: str = POLICY_ID
    checker_id: str = 'synthetic-ipv4'
    checker_version: str = '1'
    adapter_id: str = 'independent-http-peer'
    adapter_version: str = '1'
    execution_mode: str = 'separate-container-ipv4'
    schema_version: int = 1
    timeout: float = 5.0
    cpu_nanos: int = 250_000_000
    memory_bytes: int = 64 * 1024 * 1024
    pids: int = 32
    output_limit: int = 4096
    runner_image_id: str | None = None
    source_digest: str = ''

    def __post_init__(self):
        if (self.policy_id != POLICY_ID or self.schema_version != 1 or
                (self.checker_id,self.checker_version,self.adapter_id,self.adapter_version,self.execution_mode) !=
                ('synthetic-ipv4','1','independent-http-peer','1','separate-container-ipv4') or
                not 0 < self.timeout <= 30 or self.cpu_nanos != 250_000_000 or
                self.memory_bytes != 64 * 1024 * 1024 or self.pids != 32 or self.output_limit != 4096):
            raise ValueError('unsupported_policy_configuration')
        if self.runner_image_id is not None and not re.fullmatch('sha256:[0-9a-f]{64}', self.runner_image_id):
            raise ValueError('immutable_image_identity_required')


class Registry:
    def __init__(self, *, runner_image_id=None, timeout=5.0):
        source = hashlib.sha256(Path(__file__).with_name('runner.py').read_bytes()).hexdigest()
        self._policy = Policy(runner_image_id=runner_image_id, timeout=timeout, source_digest=source)

    def get(self, policy_id):
        return self._policy if policy_id == POLICY_ID else None
