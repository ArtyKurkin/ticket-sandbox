"""Explicit dedicated-daemon admission and exact-ID resource ownership."""
from dataclasses import dataclass
import re

from ..contracts import full_id

IMAGE = re.compile(r'sha256:[0-9a-f]{64}')
BASE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9._:/-]*@sha256:[0-9a-f]{64}')
ATOM = re.compile(r'[a-zA-Z0-9_.:+/-]{1,160}')


class Denied(ValueError):
    pass


def atom(value):
    return value if isinstance(value, str) and ATOM.fullmatch(value) else 'redacted'


@dataclass(frozen=True)
class Approval:
    endpoint: str
    daemon_id: str
    scope: str
    runner_image: str
    target_image: str
    python_base: str
    approved: bool = False
    execute: bool = False
    network_id: str | None = None

    def validate(self, mutation=False):
        # Unix endpoint on the dedicated VDS only; no plaintext TCP or contexts.
        if (not self.approved or not re.fullmatch(r'[a-zA-Z0-9:-]{1,160}', self.daemon_id) or
                not self.endpoint.startswith('unix:///') or '\n' in self.endpoint or
                not re.fullmatch(r'poc-[a-z0-9-]{1,40}', self.scope) or
                not IMAGE.fullmatch(self.runner_image) or not IMAGE.fullmatch(self.target_image) or
                not BASE.fullmatch(self.python_base) or '://' in self.python_base or
                (self.network_id is not None and not full_id(self.network_id)) or
                (mutation and not self.execute)):
            raise Denied('environment_not_approved')


def connect(approval, mutation=False):
    approval.validate(mutation)  # BEFORE importing/constructing any Docker client.
    import docker
    return docker.DockerClient(base_url=approval.endpoint, timeout=3, version='auto')


def preflight(client, approval):
    approval.validate()
    info, version = client.info(), client.version()
    if info.get('ID') != approval.daemon_id:
        raise Denied('daemon_identity_mismatch')
    if info.get('OSType') != 'linux' or info.get('Architecture') not in ('x86_64', 'amd64'):
        raise Denied('unsupported_platform')
    images = {}
    for role, identity in [('runner', approval.runner_image), ('target', approval.target_image)]:
        attrs = client.images.get(identity).attrs
        if (attrs.get('Id') != identity or attrs.get('Os') != 'linux' or
                attrs.get('Architecture') != 'amd64' or attrs.get('Config', {}).get('Volumes')):
            raise Denied('image_identity_or_platform_mismatch')
        images[role] = identity
    network = None
    if approval.network_id:
        attrs = client.networks.get(approval.network_id).attrs
        if (attrs.get('Id') != approval.network_id or attrs.get('Internal') is not True or
                attrs.get('Driver') != 'bridge' or
                (attrs.get('Labels') or {}).get('tc-poc.scope') != approval.scope):
            raise Denied('network_not_approved')
        network = approval.network_id
    return {'status': 'preflight_passed', 'daemon_id': approval.daemon_id,
            'platform': 'linux/amd64', 'engine_version': atom(version.get('Version')),
            'images': images, 'inspected_network_id': network,
            'python_base_operator_input': approval.python_base,
            'build_correspondence': 'operator_claim_not_attestation'}


def resource_matches(attrs, record, integration_id, scope):
    """No label search/adoption: require an ID durably returned by our create."""
    if not full_id(record.get('id')) or record.get('status') not in ('recorded', 'removed'):
        return False
    labels = attrs.get('Config', {}).get('Labels') if record['kind'] == 'target' else attrs.get('Labels')
    labels = labels or {}
    if (attrs.get('Id') != record['id'] or labels.get('tc-poc.integration') != integration_id or
            labels.get('tc-poc.scope') != scope or labels.get('tc-poc.token') != record['token'] or
            labels.get('tc-poc.role') != record['kind']):
        return False
    if record['kind'] == 'target':
        return (attrs.get('Image') == record['image'] and
                labels.get('tc-poc.generation') == record['generation'])
    return attrs.get('Internal') is True and attrs.get('Driver') == 'bridge'
