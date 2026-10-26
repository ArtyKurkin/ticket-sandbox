"""Host-only pilot settings. Disabled lookup never opens a config or Docker."""
from pathlib import Path

from django.conf import settings

TASK = ("l1", "service-bind-localhost")


def selected(queue_slug, task_slug, attempt_id):
    if not settings.SANDBOX_HTTP_OBSERVATION_ENABLED or (queue_slug, task_slug) != TASK:
        return False
    try:
        allowed = int(settings.SANDBOX_HTTP_OBSERVATION_ATTEMPT_ID)
    except (TypeError, ValueError):
        allowed = 0
    # Misconfigured enabled pilot blocks legacy for this task, never falls back.
    return allowed <= 0 or attempt_id == allowed


def enabled_for(attempt):
    return selected(attempt.task.queue.slug, attempt.task.slug, attempt.pk)


def load_config():
    from experiments.trusted_checker_mvp.docker_pilot.adapter import Policy, Refused
    from experiments.trusted_checker_mvp.docker_pilot.worker import decode
    if not settings.SANDBOX_HTTP_OBSERVATION_ENABLED or int(settings.SANDBOX_HTTP_OBSERVATION_ATTEMPT_ID) <= 0:
        raise ValueError("observation_disabled_or_unconfigured")
    with Path(settings.SANDBOX_HTTP_OBSERVATION_CONFIG).open("rb") as file:
        data = decode(file.read(8193), 8192)
    keys = {"daemon_id", "network_id", "scope", "subnet", "target_image", "verifier_image", "api_socket", "artifact_dir"}
    if type(data) is not dict or set(data) != keys:
        raise ValueError("configuration_schema")
    for key in ("api_socket", "artifact_dir"):
        if type(data[key]) is not str or not Path(data[key]).is_absolute() or "\0" in data[key]:
            raise ValueError("configuration_path")
    try:
        policy = Policy(**{key: data[key] for key in keys - {"api_socket", "artifact_dir"}})
    except (Refused, TypeError, ValueError):
        raise ValueError("configuration_policy") from None
    return data, policy


def pilot_launch(client, attempt_id):
    """Normal explicit environment start/reset only; no call from observation."""
    from sandbox.models import SandboxEnvironmentEvent
    from experiments.trusted_checker_mvp.docker_pilot.adapter import NETWORK_OPTIONS
    data, policy = load_config()
    event = SandboxEnvironmentEvent.objects.filter(attempt_id=attempt_id, phase="requested").order_by("-pk").first()
    if event is None or event.kind not in ("start", "reset"):
        raise ValueError("environment_generation_missing")
    if client.info()["ID"] != policy.daemon_id:
        raise ValueError("daemon_mismatch")
    network = client.api.inspect_network(policy.network_id)
    if not (network["Id"] == policy.network_id and network["Name"] == "tc-mvp-" + policy.scope
            and network["Driver"] == "bridge" and network["Internal"] is True
            and network.get("EnableIPv6") is False and network["Options"] == NETWORK_OPTIONS
            and network["Labels"].get("tc-mvp.scope") == policy.scope
            and network["Labels"].get("tc-mvp.role") == "data" and not network.get("Containers")
            and network["IPAM"]["Config"][0]["Subnet"] == policy.subnet):
        raise ValueError("pilot_network_not_empty_or_unapproved")
    client.images.get(policy.target_image)  # Never build or pull for enabled pilot.
    return policy.target_image, {
        "network": policy.network_id,
        "labels": {"tc-mvp.scope": policy.scope, "tc-mvp.role": "target", "tc-mvp.environment": str(event.operation_id)},
    }


def capture_runtime(attempt, container):
    """Readback during explicit environment creation, before marking it READY."""
    from sandbox.models import SandboxEnvironmentEvent
    from experiments.trusted_checker_mvp.docker_pilot.adapter import Execution
    if not enabled_for(attempt):
        return None
    _, policy = load_config()
    event = SandboxEnvironmentEvent.objects.filter(attempt_id=attempt.pk, phase="requested").order_by("-pk").first()
    if event is None or event.kind not in ("start", "reset"):
        raise ValueError("environment_generation_missing")
    container.reload()
    actual = container.attrs
    if (actual["Id"] != container.id or actual["State"]["Running"] is not True
            or len(actual["NetworkSettings"]["Networks"]) != 1
            or actual["Config"]["Labels"].get("tc-mvp.environment") != str(event.operation_id)):
        raise ValueError("runtime_mapping_invalid")
    endpoint = next(iter(actual["NetworkSettings"]["Networks"].values()))
    runtime = {
        "environment_uuid": str(event.operation_id), "container_id": actual["Id"],
        "daemon_id": policy.daemon_id, "started_at": actual["State"]["StartedAt"],
        "restart_count": actual["RestartCount"], "pid": actual["State"]["Pid"],
        "network_id": endpoint["NetworkID"], "endpoint_id": endpoint["EndpointID"], "ip": endpoint["IPAddress"],
    }
    Execution(attempt_id=attempt.pk, user_id=attempt.user_id,
              run_id="00000000-0000-0000-0000-000000000001", ordinal=1, **runtime)
    if runtime["network_id"] != policy.network_id:
        raise ValueError("runtime_network_mismatch")
    return runtime
