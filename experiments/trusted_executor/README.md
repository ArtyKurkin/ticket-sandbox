# Trusted Executor — laboratory prototype

Status: experimental, not production-ready.

The lab directory preserves the executor components tested on
an isolated VDS:

- executor_protocol.py: signed request protocol
- trusted_executor.py: socket-free Celery forwarder
- executor_gateway.py: privileged HTTP gateway
- recover_observations.py: abandoned observation inspection/recovery

These scripts retain laboratory imports, settings, network names
and secret mount paths. They are not independently deployable
from this directory.

Confirmed:
- Real Django/Redis/Celery/DockerPilot HTTP observation E2E
- Failure to reach gateway -> finished/unknown
- Replay of a finished run leaves its result unchanged
- Stale running observation detected without automatic replay
- No academic pass or achievement changes

Not confirmed:
- Gateway crash during active Docker execution
- Lost HTTP response and concurrent delivery races
- Durable recovery after gateway restart
- Production-grade Docker API isolation
- Secure replacement of the ttyd Docker socket

Do not deploy or enable for trainees.
