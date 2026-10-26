"""Local source manifest only; no build, client discovery or image lookup."""
import hashlib
from pathlib import Path
import re
from trusted_checker_runtime.live_contract import LIVE_POLICY
from trusted_checker_runtime.profiles import require


def source_manifest():
    root = Path(__file__).parent
    return {'policy_id': LIVE_POLICY.policy_id, 'policy_version': LIVE_POLICY.version,
            'policy_digest': LIVE_POLICY.digest,
            'files': {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                      for name in ('runner.py', 'Runner.Dockerfile')}}


def target_build_recipe(ubuntu_digest):
    """Return a pinned build-only copy. Never edits the educational Dockerfile."""
    require(type(ubuntu_digest) is str and re.fullmatch(r'ubuntu:22\.04@sha256:[0-9a-f]{64}', ubuntu_digest),
            'pinned_task_base_required')
    source = Path(__file__).resolve().parent.parent/'training_tasks/l1/service-bind-localhost/Dockerfile'
    text = source.read_text()
    require(text.startswith('FROM ubuntu:22.04\n'), 'task_recipe_changed_review_required')
    return 'FROM '+ubuntu_digest+'\n'+text.split('\n', 1)[1]
