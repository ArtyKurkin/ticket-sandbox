"""Exact endpoint read-only Docker port. No reuse of the blocked live adapter."""
from trusted_checker_live.transport import ExplicitUnixEndpoint,observe_linux_peer,open_explicit_api
from trusted_checker_runtime.profiles import require


class ReadOnlyDocker:
    def __init__(self,activation,endpoint,*,offline_api=None,offline_witness=None):
        require(type(endpoint) is ExplicitUnixEndpoint,'physical_explicit_endpoint_required')
        require(activation.offline or (offline_api is None and offline_witness is None),'physical_mock_api_forbidden')
        self.activation,self.endpoint=activation,endpoint
        self._api=offline_api;self._witness=offline_witness
    def call(self,operation,budget,identifier=None):
        started=budget.monotonic()
        a=self.activation.check('read')
        require((self.endpoint.reference,self.endpoint.digest)==
                (a.binding.daemon.endpoint_reference,a.binding.daemon.endpoint_config_digest),'physical_endpoint_mismatch')
        known=(a.binding.target.container_id,a.binding.runner.container_id)
        require(operation in ('info','containers','inspect_container','inspect_network') and
                (identifier in known if operation=='inspect_container' else
                 identifier==a.binding.network_id if operation=='inspect_network' else identifier is None),
                'physical_docker_read_not_allowed')
        witness=self._witness if self.activation.offline else observe_linux_peer(self.endpoint)
        require(witness==self.endpoint.witness and witness.boot_uuid==a.binding.host_boot_uuid,'physical_daemon_session_changed')
        if self._api is None:self._api=open_explicit_api(self.endpoint)
        self._api.timeout=budget.remaining()
        if operation=='containers':result=self._api.containers(all=True)
        else:result=getattr(self._api,operation)(identifier) if identifier else getattr(self._api,operation)()
        budget.remaining()
        after=self._witness if self.activation.offline else observe_linux_peer(self.endpoint)
        require(after==witness,'physical_daemon_session_changed')
        if operation=='info':require(result['ID']==a.binding.daemon.daemon_id,'physical_daemon_id_changed')
        budget.record('docker_read_'+operation,started)
        return result
