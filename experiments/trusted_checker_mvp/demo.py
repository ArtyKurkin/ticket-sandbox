"""Owned loopback smoke demo, not a container or network-isolation experiment."""
import json

from .local import check
from .test_mvp import fixture, service


def main():
    control, binding = fixture()
    with service(control):
        result = check(control, binding.attempt_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["http"] == "matched" and not result["academic_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
