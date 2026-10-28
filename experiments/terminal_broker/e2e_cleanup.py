"""Explicit container cleanup after approval; never removes volumes/images/DBs."""
import json
import os
import re

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

import docker
from sandbox.services.docker_service import remove_terminal_container


def main():
    prefix = os.environ.get("TB_E2E_PREFIX", "tc-tb2-20261028-")
    if not re.fullmatch(r"tc-tb2-[a-zA-Z0-9_-]+-", prefix):
        raise ValueError("Unsafe cleanup prefix")
    client = docker.from_env()
    removed = []
    for mode in ("host_port", "docker_network"):
        # Exercise the actual Django revoke/stop/reconcile path before deletion.
        name = prefix + mode + "-terminal"
        remove_terminal_container(name)
        removed.extend([name + "-broker", name])
        target = client.containers.get(prefix + mode + "-target")
        if target.labels.get("terminal-broker.e2e") != prefix:
            raise RuntimeError("Refusing to remove a foreign target")
        target.remove(force=True)
        removed.append(target.name)
    print(json.dumps({"gracefulDjangoRevocation": True, "removed": removed,
                      "volumesImagesAndDatabasesRemoved": False}, indent=2))


if __name__ == "__main__":
    main()
