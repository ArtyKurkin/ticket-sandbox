"""Fail closed on accidental CI/CD coupling. Parses YAML, never runs workflow steps."""
from pathlib import Path
import re
import sys

import yaml


class PolicyError(ValueError):
    pass


class UniqueLoader(yaml.BaseLoader):
    """Keep Actions' `on` as a string; reject duplicate keys instead of hiding jobs."""


def unique_mapping(loader, node):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in mapping:
            raise PolicyError("duplicate_yaml_key")
        mapping[key] = loader.construct_object(value_node)
    return mapping


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load(path):
    with path.open(encoding="utf-8") as stream:
        result = yaml.load(stream, Loader=UniqueLoader)
    if not isinstance(result, dict):
        raise PolicyError("workflow_must_be_mapping")
    return result


def require(condition, message):
    if not condition:
        raise PolicyError(message)


def strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    else:
        yield str(value)


SYNC = "python manage.py migrate --noinput\npython manage.py sync_training_tasks --dry-run --strict"
POLICY_RUNS = {
    "python -m pip install PyYAML==6.0.2",
    "python deploy/ci/workflow_policy.py\npython -m unittest discover -s deploy/ci -p 'test_*.py' -v",
}
TEST_RUNS = {
    "python -m pip install --upgrade pip\npip install -r requirements.txt",
    "npm ci\nnpm test\nnpm run build",
    "python manage.py collectstatic --noinput",
    "python manage.py test react_frontend",
    "python manage.py makemigrations --check --dry-run",
    "python manage.py check",
    "python manage.py check --deploy",
    SYNC,
    "python manage.py test sandbox traineediary assessment",
}
TEST_ENV = {
    "SECRET_KEY": "test-secret-key", "DEBUG": "True", "DB_ENGINE": "django.db.backends.sqlite3",
    "DB_NAME": ":memory:", "TERMINAL_GATEWAY_ENABLED": "true", "CHECK_TASK_TIMEOUT_SECONDS": "60",
}
DEPLOY_CHECK_ENV = {
    "SECRET_KEY": "ci-deploy-check-secret-key-with-enough-length-and-variety-2026", "DEBUG": "False",
    "ALLOWED_HOSTS": "example.com", "CSRF_TRUSTED_ORIGINS": "https://example.com",
    "DB_ENGINE": "django.db.backends.sqlite3", "DB_NAME": ":memory:", "TERMINAL_GATEWAY_ENABLED": "true",
    "CHECK_TASK_TIMEOUT_SECONDS": "60",
}
MANUAL_ONLY = "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
MANUAL_ENABLED = MANUAL_ONLY + " && vars.MANUAL_STAGING_DEPLOY_ENABLED == 'true'"
STOP = 'echo "::error::Deployment is disabled until a Lite-compatible procedure is reviewed and tested."\nexit 1'


def automatic_boundary(workflow):
    events = workflow.get("on", {})
    require(isinstance(events, dict), "explicit_event_map_required")
    require(set(events) <= {"push", "pull_request", "workflow_dispatch"}, "unreviewed_workflow_trigger")
    if not set(events) & {"push", "pull_request"}:
        return
    require(not any(re.search(r"\bsecrets\s*[.\[]", s) for s in strings(workflow)), "automatic_workflow_must_not_access_secrets")
    require("DOCKER_HOST" not in set(strings(workflow)), "remote_docker_environment_forbidden")
    for job in workflow.get("jobs", {}).values():
        require(job.get("runs-on") == "ubuntu-latest", "automatic_jobs_must_use_hosted_test_runners")
        require(not set(job) & {"environment", "secrets", "uses"}, "automatic_deployment_or_reusable_job_forbidden")
        for step in job.get("steps", []):
            if "uses" in step:
                require(step["uses"].split("@")[0] in {
                    "actions/checkout", "actions/setup-python", "actions/setup-node", "actions/upload-artifact",
                }, "unreviewed_automatic_action")
            command = step.get("run", "")
            require(not re.search(r"\b(?:ssh|scp|sftp|ssh-keyscan)\b|DOCKER_HOST|docker\s+(?:-H|--host|context\s+use)", command), "remote_server_command_forbidden")
            require(not re.search(r"docker\s+compose\b", command), "automatic_compose_forbidden")
            if re.search(r"manage\.py\s+migrate\b", command):
                require(command.strip() == SYNC and step.get("env") == {
                    "DB_ENGINE": "django.db.backends.sqlite3", "DB_NAME": "ci-sync-check.sqlite3",
                }, "only_isolated_sqlite_fixture_migration_allowed")
        require("DOCKER_HOST" not in set(job.get("env", {})), "remote_docker_environment_forbidden")


def check_ci(ci):
    require(set(ci) == {"name", "on", "permissions", "jobs"}, "unreviewed_ci_root_option")
    require(set(ci["on"]) == {"push", "pull_request"}, "ci_must_remain_push_and_pr_only")
    require(all(v in ("", None) for v in ci["on"].values()), "ci_trigger_filters_changed")
    require(ci["permissions"] == {"contents": "read"}, "ci_token_must_be_readonly")
    require(set(ci["jobs"]) == {"tests", "workflow-policy"}, "ci_job_allowlist_changed")
    require(ci["jobs"]["tests"].get("needs") == "workflow-policy", "tests_must_wait_for_policy")
    require("needs" not in ci["jobs"]["workflow-policy"], "policy_must_run_unconditionally")
    require(not any("${{" in s for s in strings(ci)), "ci_must_not_import_dynamic_server_inputs")
    for name, job in ci["jobs"].items():
        require(set(job) <= {"name", "runs-on", "needs", "steps", "env"}, "unreviewed_ci_job_option")
        require(job.get("env", {}) == (TEST_ENV if name == "tests" else {}), "ci_database_or_environment_changed")
        runs = []
        actions = []
        for step in job["steps"]:
            require(set(step) <= {"name", "uses", "with", "run", "env", "working-directory"}, "unreviewed_ci_step_option")
            require(("run" in step) != ("uses" in step), "step_must_run_or_use_one_action")
            if "uses" in step:
                action = step["uses"]
                actions.append(action)
                expected_with = {
                    "actions/checkout@v4": {"persist-credentials": "false"} if name == "workflow-policy" else {},
                    "actions/setup-python@v5": {"python-version": "3.13"},
                    "actions/setup-node@v4": {"node-version": "22", "cache": "npm", "cache-dependency-path": "frontend/package-lock.json"},
                }
                require(action in expected_with and step.get("with", {}) == expected_with[action], "ci_action_or_options_changed")
                require(not set(step) & {"env", "working-directory"}, "ci_action_environment_changed")
                continue
            command = step["run"].strip()
            runs.append(command)
            expected_env = ({"DB_ENGINE": "django.db.backends.sqlite3", "DB_NAME": "ci-sync-check.sqlite3"} if command == SYNC else
                            DEPLOY_CHECK_ENV if command == "python manage.py check --deploy" else
                            {"DEBUG": "False"} if command == "python manage.py collectstatic --noinput" else {})
            require(step.get("env", {}) == expected_env, "ci_step_database_or_environment_changed")
            require(step.get("working-directory") == ("frontend" if command.startswith("npm ci\n") else None), "ci_step_directory_changed")
        expected_runs = TEST_RUNS if name == "tests" else POLICY_RUNS
        require(set(runs) == expected_runs and len(runs) == len(expected_runs), "ci_command_allowlist_changed")
        expected_actions = ["actions/checkout@v4", "actions/setup-python@v5"]
        if name == "tests":
            expected_actions.append("actions/setup-node@v4")
        require(actions == expected_actions, "ci_setup_actions_changed")


def condition(text):
    return "".join(text.split())


def check_manual(manual):
    require(set(manual) == {"name", "on", "permissions", "concurrency", "jobs"}, "unreviewed_manual_root_option")
    require(set(manual["on"]) == {"workflow_dispatch"}, "deployment_must_be_manual_only")
    require(manual.get("permissions") == {"contents": "read"}, "manual_token_must_be_readonly")
    require(manual.get("concurrency") == {"group": "manual-staging-deployment", "cancel-in-progress": "false"}, "manual_deploys_must_not_overlap_or_cancel")
    inputs = manual["on"]["workflow_dispatch"]["inputs"]
    require(set(inputs) == {"revision", "target_environment", "confirmation"}, "manual_inputs_changed")
    require(all(v.get("required") == "true" and "default" not in v for v in inputs.values()), "explicit_inputs_required")
    require(inputs["target_environment"].get("options") == ["staging"], "production_target_forbidden")
    require(inputs["revision"]["type"] == inputs["confirmation"]["type"] == "string", "revision_and_confirmation_must_be_strings")
    require(inputs["target_environment"]["type"] == "choice", "staging_must_be_a_fixed_choice")
    require(set(manual["jobs"]) == {"validate-request", "deploy-staging"}, "unreviewed_manual_job")
    validate, gate = manual["jobs"]["validate-request"], manual["jobs"]["deploy-staging"]
    require(set(validate) == {"if", "runs-on", "outputs", "steps"}, "unreviewed_request_job_option")
    require(set(gate) == {"name", "needs", "if", "runs-on", "environment", "steps"}, "unreviewed_gate_job_option")
    require(validate["outputs"] == {"revision": "${{ steps.request.outputs.revision }}"}, "validated_revision_output_required")
    require(condition(validate.get("if", "")) == condition(MANUAL_ONLY), "manual_request_requires_main_dispatch")
    require(condition(gate.get("if", "")) == condition(MANUAL_ENABLED), "manual_gate_requires_explicit_enablement")
    require(gate.get("environment") == "manual-staging" and gate.get("needs") == "validate-request", "protected_staging_environment_required")
    require(all(job.get("runs-on") == "ubuntu-latest" for job in (validate, gate)), "manual_scaffold_must_not_use_live_runners")
    require(not any(re.search(r"\bsecrets\s*[.\[]", s) for s in strings(manual)), "disabled_scaffold_must_not_access_secrets")
    require(len(validate.get("steps", [])) == 3, "unreviewed_validation_step")
    checkout, python, request = validate["steps"]
    require(set(checkout) == set(python) == {"name", "uses", "with"}, "unreviewed_setup_step_option")
    require(set(request) == {"name", "id", "env", "run"}, "unreviewed_request_step_option")
    require(checkout.get("uses") == "actions/checkout@v4" and checkout.get("with") == {
        "ref": "${{ github.sha }}", "fetch-depth": "0", "persist-credentials": "false",
    }, "request_must_checkout_trusted_workflow_revision")
    require(python.get("uses") == "actions/setup-python@v5" and python.get("with") == {"python-version": "3.13"}, "manual_python_setup_changed")
    require(request.get("run") == "python deploy/ci/manual_deploy_request.py" and request.get("id") == "request", "manual_validation_must_not_run_target_code")
    require(request.get("env") == {
        "ACTION_EVENT_NAME": "${{ github.event_name }}", "ACTION_WORKFLOW_REF": "${{ github.ref }}",
        "REQUESTED_REVISION": "${{ inputs.revision }}", "REQUESTED_ENVIRONMENT": "${{ inputs.target_environment }}",
        "REQUEST_CONFIRMATION": "${{ inputs.confirmation }}",
    }, "inputs_must_only_enter_validator_via_environment")
    require(len(gate.get("steps", [])) == 1 and gate["steps"][0].get("run", "").strip() == STOP,
            "deployment_must_remain_hard_blocked_until_a_reviewed_procedure_exists")
    require(set(gate["steps"][0]) == {"name", "run"}, "unreviewed_stop_step_option")


def check_repository(root):
    paths = sorted((root / ".github/workflows").glob("*.yml")) + sorted((root / ".github/workflows").glob("*.yaml"))
    workflows = {path.name: load(path) for path in paths}
    for workflow in workflows.values():
        automatic_boundary(workflow)
    check_ci(workflows["ci.yml"])
    check_manual(workflows["manual-deploy.yml"])


def main():
    try:
        check_repository(Path(__file__).resolve().parents[2])
    except (PolicyError, yaml.YAMLError, KeyError, TypeError, ValueError):
        print("Workflow policy failed; review CI/CD boundary changes.", file=sys.stderr)
        return 1
    print("Workflow policy OK: hosted CI only; manual staging deployment hard-blocked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
