"""Validate a manual request only. No server, Docker, DB or deployment access."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class RequestError(ValueError):
    pass


def validate_request(*, event, workflow_ref, target, revision, confirmation, root):
    if event != "workflow_dispatch" or workflow_ref != "refs/heads/main":
        raise RequestError("manual_dispatch_from_main_required")
    if target != "staging":
        raise RequestError("only_isolated_staging_supported")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise RequestError("full_lowercase_commit_sha_required")
    if confirmation != f"DEPLOY STAGING {revision}":
        raise RequestError("explicit_revision_confirmation_required")
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if commit.returncode or commit.stdout.strip() != revision:
        raise RequestError("revision_is_not_an_available_commit")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", revision, "origin/main"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if ancestry.returncode:
        raise RequestError("revision_must_be_reachable_from_main")
    return {"status": "validated_deployment_disabled", "target": target, "revision": revision}


def main():
    try:
        result = validate_request(
            event=os.getenv("ACTION_EVENT_NAME", ""), workflow_ref=os.getenv("ACTION_WORKFLOW_REF", ""),
            target=os.getenv("REQUESTED_ENVIRONMENT", ""), revision=os.getenv("REQUESTED_REVISION", ""),
            confirmation=os.getenv("REQUEST_CONFIRMATION", ""), root=Path(__file__).resolve().parents[2],
        )
    except RequestError as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 1
    except (OSError, subprocess.SubprocessError):
        print(json.dumps({"status": "rejected", "reason": "local_revision_validation_failed"}))
        return 1
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"revision={result['revision']}\n")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(f"Validated staging request for `{result['revision']}`.\n\n"
                         "Deployment remains disabled: no server procedure is implemented.\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
