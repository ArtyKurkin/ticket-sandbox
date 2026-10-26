"""Explicit Linux Unix transport. All I/O is dormant until explicit construction/use."""
from dataclasses import asdict, dataclass
import os
from pathlib import Path
import socket
import stat
import struct
from trusted_checker_runtime.contracts import atom, uid
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest


@dataclass(frozen=True)
class DaemonWitness:
    boot_uuid: str
    peer_pid: int
    peer_uid: int
    process_start_ticks: int
    socket_device: int
    socket_inode: int

    def __post_init__(self):
        uid(self.boot_uuid)
        require(all(type(n) is int and n >= 0 for n in (self.peer_pid, self.peer_uid, self.process_start_ticks,
                self.socket_device, self.socket_inode)) and self.peer_pid > 1 and self.process_start_ticks > 0,
                'daemon_witness_invalid')


@dataclass(frozen=True)
class ExplicitUnixEndpoint:
    reference: str
    socket_path: str
    witness: DaemonWitness
    api_version: str = '1.45'
    api_seconds: float = 3.0

    def __post_init__(self):
        atom(self.reference, 'endpoint:')
        require(type(self.socket_path) is str and self.socket_path.startswith('/run/tc-shadow/') and
                '..' not in Path(self.socket_path).parts and len(self.socket_path) < 100 and
                type(self.witness) is DaemonWitness and self.api_version == '1.45' and
                type(self.api_seconds) is float and self.api_seconds == 3.0, 'explicit_endpoint_invalid')
        self.witness.__post_init__()

    @property
    def digest(self):
        return digest(asdict(self))


def observe_linux_peer(endpoint):
    """Independent peer/process incarnation; no Docker ID inferred from pathname."""
    info = os.stat(endpoint.socket_path, follow_symlinks=False)
    require(stat.S_ISSOCK(info.st_mode), 'endpoint_not_unix_socket')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(endpoint.api_seconds)
        sock.connect(endpoint.socket_path)
        pid, user, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    finally:
        sock.close()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    raw = Path('/proc')/str(pid)/'stat'
    # comm can contain spaces/parentheses; field22 is offset19 after last ')'.
    fields = raw.read_text().rsplit(')', 1)[1].split()
    return DaemonWitness(boot, pid, user, int(fields[19]), info.st_dev, info.st_ino)


def open_explicit_api(endpoint):
    """No from_env, auto version, Docker config/credentials, proxy or retries.

    SDK7.1's ordinary APIClient initializer reads ~/.docker/config. This narrow
    subclass initializes only the audited requests Unix adapter and fixed API.
    No socket is opened by import. This function is called only after admission.
    """
    require(type(endpoint) is ExplicitUnixEndpoint, 'explicit_endpoint_required')
    import docker
    import requests
    from docker.auth import AuthConfig
    from docker.transport.unixconn import UnixHTTPAdapter
    from docker.utils.proxy import ProxyConfig
    require(docker.__version__ == '7.1.0', 'sdk_version_unreviewed')

    class ExplicitAPI(docker.APIClient):
        def __init__(self):
            requests.Session.__init__(self)
            self.trust_env = False
            self.timeout = endpoint.api_seconds
            self._version = endpoint.api_version
            self._general_configs = {}
            self._proxy_configs = ProxyConfig.from_dict({})
            self._auth_configs = AuthConfig({})
            self.credstore_env = {}
            self.base_url = 'http+docker://localhost'
            self.headers['User-Agent'] = 'trusted-checker-live-v2'
            self._custom_adapter = UnixHTTPAdapter('http+unix://'+endpoint.socket_path, endpoint.api_seconds,
                                                   pool_connections=1, max_pool_size=1)
            self.mount('http+docker://', self._custom_adapter)
            self.adapters.pop('http://', None)
            self.adapters.pop('https://', None)

        def remove_owned_raw(self, container_id):
            from trusted_checker_runtime.contracts import full_id
            full_id(container_id)
            response = self._delete(self._url('/containers/{0}', container_id), params={'force': 1, 'v': 0})
            require(response.status_code == 204, 'exact_remove_not_acknowledged')
            return 204
    return ExplicitAPI()
