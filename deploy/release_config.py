"""Read-only Compose validation and command planning. Never performs a deployment."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FILES = ("docker-compose.yml", "docker-compose.prod.yml",
         "deploy/compose/release.yml", "deploy/compose/lite.yml")
IMAGES = {"web": "WEB_IMAGE", "worker": "WORKER_IMAGE",
          "terminal_scheduler": "SCHEDULER_IMAGE", "gateway": "GATEWAY_IMAGE",
          "db": "POSTGRES_IMAGE", "redis": "REDIS_IMAGE"}
KEYS = set(IMAGES.values()) | {"BROKER_IMAGE", "TTYD_IMAGE", "BROKER_AUTHORIZATION_URL"}
IMAGE = re.compile(r"(?:[^\s@$]+@)?sha256:[0-9a-f]{64}\Z")
UPDATABLE = ("web", "worker", "terminal_scheduler", "gateway")


class ReleaseError(ValueError):
    pass


def load_pins(path):
    pins = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in KEYS or key in pins:
            raise ReleaseError("Release file requires unique, known KEY=value entries only")
        pins[key] = value
    if set(pins) != KEYS or any(not value for value in pins.values()):
        raise ReleaseError("Release file must fill every entry in images.env.example")
    if any(not IMAGE.fullmatch(value) for key, value in pins.items()
           if key != "BROKER_AUTHORIZATION_URL"):
        raise ReleaseError("Image references must use an immutable sha256 digest or local image ID")
    if pins["BROKER_AUTHORIZATION_URL"] != "http://web:8000/terminal-broker-auth/":
        raise ReleaseError("This topology requires the private Web broker callback URL")
    return pins


def compose_command(root, runtime, release):
    command = ["docker", "compose", "--project-directory", str(root), "-p", "training-platform",
               "--env-file", str(runtime), "--env-file", str(release)]
    for filename in FILES:
        command.extend(["-f", str(root / filename)])
    return command + ["--profile", "terminal-broker"]


def interpolation_variables(root):
    interpolation = set()
    for filename in FILES:
        interpolation.update(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)", (root / filename).read_text()))
    return interpolation


def compose_environment(root, runtime, pins):
    # Shell image/DB variables must not silently override either reviewed env file.
    interpolation = interpolation_variables(root)
    environment = {key: value for key, value in os.environ.items()
                   if key not in interpolation and not key.startswith("COMPOSE_")}
    environment.update(pins)
    environment.update(TP_RUNTIME_ENV_FILE=str(runtime), COMPOSE_DISABLE_ENV_FILE="true")
    return environment


def validate(root, runtime, release, pins):
    environment = compose_environment(root, runtime, pins)
    command = compose_command(root, runtime, release)
    result = subprocess.run(command + ["config", "--format", "json"],
                            env=environment, text=True, capture_output=True, timeout=60)
    if result.returncode:
        # A rendered config / Compose stderr can contain private environment data.
        raise ReleaseError("Compose validation failed; inspect configuration privately")
    services = json.loads(result.stdout)["services"]
    if set(services) != set(IMAGES):
        raise ReleaseError("Unexpected service set in release configuration")
    for name, key in IMAGES.items():
        if services[name]["image"] != pins[key] or services[name].get("build"):
            raise ReleaseError("Release image mismatch or source build remains enabled")
    for name in ("web", "worker", "terminal_scheduler"):
        env = services[name]["environment"]
        if (env.get("TERMINAL_BROKER_ENABLED") != "true"
                or env.get("TERMINAL_BROKER_IMAGE") != pins["BROKER_IMAGE"]
                or env.get("TERMINAL_BROKER_TTYD_IMAGE") != pins["TTYD_IMAGE"]
                or env.get("TERMINAL_BROKER_AUTHORIZATION_URL") != pins["BROKER_AUTHORIZATION_URL"]):
            raise ReleaseError("Lite settings differ between Web, Worker and Scheduler")
    return command


def planned_commands(command, service):
    if service not in UPDATABLE:
        raise ReleaseError("Only application roles and Gateway may be planned")
    commands = []
    if service == "terminal_scheduler":
        commands.append(command + ["stop", "--timeout", "60", service])
    timeout = "600" if service == "worker" else "120"
    commands.append(command + ["up", "-d", "--no-deps", "--no-build", "--pull", "never",
                               "--timeout", timeout, service])
    return commands


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--runtime-env", type=Path, required=True)
    parser.add_argument("--release-env", type=Path, required=True)
    parser.add_argument("action", choices=("validate", "plan"))
    parser.add_argument("service", nargs="?", choices=UPDATABLE)
    args = parser.parse_args(argv)
    if (args.action == "plan") != bool(args.service):
        parser.error("plan requires one service; validate does not accept a service")
    try:
        root, runtime, release = (path.resolve(strict=True) for path in
                                  (args.root, args.runtime_env, args.release_env))
        pins = load_pins(release)
        command = validate(root, runtime, release, pins)
        print("Compose release configuration OK; no containers changed.")
        if args.action == "plan":
            print("# REVIEW ONLY. Reconcile server overrides and authorize before execution.")
            # Preserve the same interpolation inputs when copying the reviewed plan.
            clear = (interpolation_variables(root) - KEYS - {"TP_RUNTIME_ENV_FILE"}) | {
                "COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME", "COMPOSE_ENV_FILES",
            }
            prefix = ["env"]
            for key in sorted(clear):
                prefix += ["-u", key]
            prefix += [f"{key}={pins[key]}" for key in sorted(pins)]
            prefix += [f"TP_RUNTIME_ENV_FILE={runtime}", "COMPOSE_DISABLE_ENV_FILE=true"]
            for planned in planned_commands(command, args.service):
                print(shlex.join(prefix + planned))
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        print("Release validation failed. Check private env files, immutable pins and Compose >= 2.24.4.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
