"""Manual, disposable-host lab runner. No Django identity or automatic provisioning.

pin/audit only inspect Docker. observe requires an explicit scope confirmation
and delegates all verifier effects/cleanup to the unchanged DockerPilot.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import stat
import time
from uuid import uuid4

import docker
from docker.errors import NotFound

from .adapter import DockerPilot, Execution, Policy, Refused, RUN_SECONDS
from .worker import decode, full_id, uuid

SCHEMA = "tc-mvp-disposable-lab-v1"
LIMIT = 16384


class LabRefusal(Exception):
    pass


def require(value, reason="lab_scope_refused"):
    if not value:
        raise LabRefusal(reason)


def private_directory(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_mode & 0o077 == 0, "private_storage_required")


def read_private(path):
    path = Path(path)
    private_directory(path.parent)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as source:
        info = os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and info.st_mode & 0o077 == 0 and info.st_size <= LIMIT, "private_storage_required")
        return decode(source.read(LIMIT + 1), LIMIT)


def write_record(path, record):
    path = Path(path)
    private_directory(path.parent)
    encoded = json.dumps(record, sort_keys=True).encode()
    require(len(encoded) <= LIMIT, "record_bounds")
    # Never overwrite/re-pin an existing execution, including a failed one.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())


def configuration(path):
    config = read_private(path)
    require(type(config) is dict and set(config) == {
        "api_socket", "artifact_dir", "environment_uuid", "target_id", "policy"}, "configuration_schema")
    policy = Policy(**config["policy"])
    uuid(config["environment_uuid"])
    require(full_id(config["target_id"]), "configuration_schema")
    for key in ("api_socket", "artifact_dir"):
        require(type(config[key]) is str and Path(config[key]).is_absolute() and "\0" not in config[key], "configuration_schema")
    private_directory(config["artifact_dir"])
    return config, policy


def live_execution(api, config, policy, *, run_id=None):
    require(api.info()["ID"] == policy.daemon_id)
    actual = api.inspect_container(config["target_id"])
    require(actual["Id"] == config["target_id"] and len(actual["NetworkSettings"]["Networks"]) == 1)
    endpoint = next(iter(actual["NetworkSettings"]["Networks"].values()))
    # These three integers/UUIDs are lab correlation only, NEVER Django evidence.
    return Execution(1, 1, config["environment_uuid"], run_id or str(uuid4()), 1,
                     actual["Id"], policy.daemon_id, actual["State"]["StartedAt"],
                     actual["RestartCount"], actual["State"]["Pid"], endpoint["NetworkID"],
                     endpoint["EndpointID"], endpoint["IPAddress"])


def inventory(api, config, policy):
    rows = api.containers(all=True)
    require(type(rows) is list)
    require(all(full_id(row["Id"]) for row in rows))
    scoped = [row for row in rows if (row.get("Labels") or {}).get("tc-mvp.scope") == policy.scope]
    return {
        "scoped_ids": sorted(row["Id"] for row in scoped),
        "scoped_verifier_ids": sorted(row["Id"] for row in scoped
                                      if (row.get("Labels") or {}).get("tc-mvp.role") == "verifier"),
        # Foreign resources are compared, NEVER stopped or removed by this runner.
        "foreign": {row["Id"]: row["State"] for row in rows if row["Id"] != config["target_id"]
                    and (row.get("Labels") or {}).get("tc-mvp.scope") != policy.scope},
    }


def preflight(api, config, policy, *, run_id=None):
    require(api.base_url == "http+docker://localhost")
    actual = live_execution(api, config, policy, run_id=run_id)
    checker = DockerPilot(api, policy, lambda _: actual, config["artifact_dir"])
    checker.deadline = time.monotonic() + RUN_SECONDS
    # Reuse the exact existing predicates; never relax profile/identity checks.
    checker._target(actual)
    checker._network(actual)
    before = inventory(api, config, policy)
    require(before["scoped_ids"] == [config["target_id"]], "scope_not_quiescent")
    return actual, before


def read_record(path, config, policy):
    value = read_private(path)
    require(type(value) is dict and set(value) == {"schema", "lab_only", "policy", "execution"}, "record_schema")
    require(value["schema"] == SCHEMA and value["lab_only"] is True
            and value["policy"] == asdict(policy), "record_schema")
    execution = Execution(**value["execution"])
    require((execution.attempt_id, execution.user_id, execution.ordinal) == (1, 1, 1)
            and execution.container_id == config["target_id"]
            and execution.environment_uuid == config["environment_uuid"]
            and execution.daemon_id == policy.daemon_id and execution.network_id == policy.network_id, "record_schema")
    return execution


def run(api, config, policy, command, record_path):
    if command == "observe":
        execution = read_record(record_path, config, policy)
        # Check CURRENT ownership/profile before any verifier effects. A changed
        # start/PID is not adopted: observe still receives the OLD pinned record.
        _, before = preflight(api, config, policy, run_id=execution.run_id)

        def source(attempt_id):
            require(attempt_id == 1)
            current = read_record(record_path, config, policy)
            require(current == execution, "record_changed")
            return current

        observation = DockerPilot(api, policy, source, config["artifact_dir"], enabled=True).observe(1)
        result = asdict(observation)
        after = inventory(api, config, policy)
        result["inventory"] = {
            "scope_empty_except_target": after["scoped_ids"] == [config["target_id"]],
            "remaining_scope_verifier_ids": after["scoped_verifier_ids"],
            "foreign_inventory_unchanged": before["foreign"] == after["foreign"],
        }
        clean = result["inventory"]["scope_empty_except_target"] and result["inventory"]["foreign_inventory_unchanged"]
        result.update(lab_only=True, real_pilot_passed=False)
        return result, 0 if clean and observation.http != "unknown" else 2

    execution, before = preflight(api, config, policy)
    version = api.version()
    try:
        image = api.inspect_image(policy.verifier_image)
        require(image["Id"] == policy.verifier_image)
        verifier_available = True
        environment = dict(item.split("=", 1) for item in image["Config"].get("Env", []))
        image_compatible = not image["Config"].get("Volumes") and not any(
            key.startswith(("LD_", "DYLD_")) or key in ("PYTHONPATH", "PYTHONHOME") for key in environment)
    except NotFound:
        verifier_available = False  # Supports explicit unavailable-image fault.
        image_compatible = False
    if command == "pin":
        write_record(record_path, {"schema": SCHEMA, "lab_only": True,
                                   "policy": asdict(policy), "execution": asdict(execution)})
    return {
        "lab_only": True, "academic_pass": False, "real_pilot_passed": False,
        "execution": asdict(execution), "verifier_image_available": verifier_available,
        "verifier_image_config_compatible": image_compatible,
        "engine": {key: version.get(key) for key in ("Version", "ApiVersion")},
        "scope_quiescent": before["scoped_ids"] == [config["target_id"]],
        "target_profile": "checked_by_existing_adapter", "network_isolation": "unverified",
    }, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "pin", "observe"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--record", help="Private execution file; pin creates it exclusively")
    parser.add_argument("--allow-verifier-effects", metavar="SCOPE_UUID",
                        help="Explicitly authorize this scope's verifier create/start/remove only")
    args = parser.parse_args(argv)
    if args.command != "audit" and not args.record:
        parser.error("--record is required for pin/observe")
    api = None
    try:
        config, policy = configuration(args.config)
        if args.command == "observe":
            require(args.allow_verifier_effects == policy.scope, "operator_permission_required")
        api = docker.APIClient(base_url="unix://" + config["api_socket"], version="1.45", timeout=1)
        result, code = run(api, config, policy, args.command, args.record)
    except (LabRefusal, Refused) as error:
        result, code = denial(str(error)), 2
    except Exception:
        result, code = denial("lab_unavailable_or_invalid"), 2
    finally:
        if api is not None:
            api.close()
    print(json.dumps(result, sort_keys=True, indent=2))
    return code


def denial(reason):
    return {"lab_only": True, "http": "unknown", "reason": reason, "binding": None,
            "task_verdict": "unknown", "academic_pass": False, "real_pilot_passed": False}


if __name__ == "__main__":
    raise SystemExit(main())
