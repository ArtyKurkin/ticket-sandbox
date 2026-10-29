"""Delete one pinned environment. Names locate gateways; IDs authorize deletion."""
from dataclasses import dataclass

import docker


class IdentityError(RuntimeError):
    pass


class TeardownPending(RuntimeError):
    pass


@dataclass(frozen=True)
class LegacyIdentity:
    """Only for retiring a pre-broker environment; never passed to a broker."""
    container_id: str
    attempt: int
    queue: str
    task: str
    terminal_id: str | None
    generation: None = None


def verify(container, identity, kind):
    labels = container.labels
    expected = {"type": kind, "attempt": str(identity.attempt), "queue": identity.queue,
                "task": identity.task, "generation": identity.generation}
    if kind == "task":
        valid = container.id == identity.container_id
    elif isinstance(identity, LegacyIdentity):
        valid = kind == "terminal" and container.id == identity.terminal_id
    else:
        valid = labels.get("ticket-sandbox.target") == identity.container_id
    if not valid or any(labels.get("ticket-sandbox." + k) != v for k, v in expected.items()):
        raise IdentityError("Refusing to delete a foreign environment resource")


def get(client, name):
    try:
        return client.containers.get(name)
    except docker.errors.NotFound:
        return None


def stop_remove(container):
    try:
        container.update(restart_policy={"Name": "no"})
        container.stop(timeout=5)
        container.wait(timeout=10)  # Nonzero exit is allowed; running is not.
        container.reload()
        if container.attrs["State"]["Running"] is not False:
            raise TeardownPending("Container stop not confirmed")
        container.remove()
    except docker.errors.NotFound:
        # SDK Container objects address the immutable ID, never a reused name.
        return


def teardown(client, identity, terminal_name):
    resources = [(get(client, identity.container_id), "task")]
    if terminal_name:
        resources += [(get(client, terminal_name), "terminal"),
                      (get(client, terminal_name + "-broker"), "terminal-broker")]
    for container, kind in resources:
        if container is not None:
            verify(container, identity, kind)
    for container, kind in resources[1:]:
        if container is not None:
            stop_remove(container)
    task = resources[0][0]
    if task is not None:
        try:
            task.remove(force=True)
        except docker.errors.NotFound:
            pass
    if get(client, identity.container_id) is not None:
        raise TeardownPending("Old task deletion not confirmed")
