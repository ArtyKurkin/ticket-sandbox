"""One immutable policy; no caller-selected URLs, ports or command parameters."""

from dataclasses import asdict, dataclass
import hashlib
import json


TASK = "l1/service-bind-localhost"
POLICY_ID = "service-bind-localhost-peer-v1"
CRITERIA_SCOPE = "external_ipv4_http_only"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class PeerPolicy:
    policy_id: str = POLICY_ID
    version: int = 1
    schema_version: int = 1
    task: str = TASK
    protocol: str = "http_ipv4"
    port: int = 8080
    path: str = "/"
    status: int = 200
    expected_body: str = "APP OK: customer service is running"
    max_body_bytes: int = 1024
    normalization: str = "trailing_lf_only"
    http_timeout_seconds: float = 2.0
    run_timeout_seconds: float = 8.0
    criteria_scope: str = CRITERIA_SCOPE
    local_access: str = "unverified"
    application_authenticity: str = "unproven"
    persistence: str = "unverified"
    execution_mode: str = "offline_fake_only"

    def __post_init__(self):
        expected = {name: field.default for name, field in self.__dataclass_fields__.items()}
        if any(type(value) is not type(expected[name]) or value != expected[name]
               for name, value in asdict(self).items()):
            raise ValueError("policy_immutable")

    @property
    def digest(self):
        return digest(asdict(self))


POLICY = PeerPolicy()


def validate_policy(policy):
    if type(policy) is not PeerPolicy or asdict(policy) != asdict(POLICY):
        raise ValueError("policy_mismatch")
    policy.__post_init__()
