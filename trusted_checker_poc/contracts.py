from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import re
from uuid import UUID


class InvalidRequest(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def full_id(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


@dataclass(frozen=True)
class Request:
    run_id: str
    policy_id: str
    target_id: str
    generation: str
    synthetic_task_id: str
    schema_version: int = 1

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise InvalidRequest('request_fields_invalid')
        if any(type(data[k]) is not str or not 0 < len(data[k]) <= 100 for k in data if k != 'schema_version'):
            raise InvalidRequest('request_types_invalid')
        if type(data['schema_version']) is not int or data['schema_version'] != 1:
            raise InvalidRequest('schema_unsupported')
        try:
            if str(UUID(data['run_id'])) != data['run_id']:
                raise ValueError
        except (ValueError, AttributeError):
            raise InvalidRequest('run_id_invalid') from None
        if not full_id(data['target_id']):
            raise InvalidRequest('target_id_invalid')
        return cls(**data)


@dataclass(frozen=True)
class Target:
    container_id: str
    generation: str
    owner: str
    synthetic_task_id: str
    network_id: str
    ipv4: str
    started_at: str
    restart_count: int
    image_id: str
    scope: str

    def validate(self):
        if not full_id(self.container_id) or not full_id(self.network_id):
            raise InvalidRequest('identity_invalid')
        address = ipaddress.IPv4Address(self.ipv4)
        if not any(address in ipaddress.IPv4Network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
            raise InvalidRequest('endpoint_invalid')
        if not self.generation or not self.owner or not self.started_at or not self.scope:
            raise InvalidRequest('identity_incomplete')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', self.image_id):
            raise InvalidRequest('image_identity_invalid')


@dataclass(frozen=True)
class Runner:
    container_id: str
    image_id: str
    run_id: str
    scope: str
    config_verified: bool


@dataclass(frozen=True)
class Outcome:
    result: str
    reason: str
    evidence: dict


@dataclass(frozen=True)
class Result:
    run_id: str
    checker_id: str
    checker_version: str
    adapter_id: str
    adapter_version: str
    requested_target: dict
    observed_target: dict | None
    runner_identity: dict | None
    requested_at: str
    started_at: str | None
    finished_at: str
    result: str
    failure_class: str
    integrity: dict
    evidence_digest: str
    reason: str
    cleanup: str
    policy_identity: dict
    schema_version: int = 1

    def to_dict(self):
        return asdict(self)


class AdapterError(Exception):
    def __init__(self, reason, failure_class='infrastructure'):
        self.reason = reason
        self.failure_class = failure_class
        super().__init__(reason)
