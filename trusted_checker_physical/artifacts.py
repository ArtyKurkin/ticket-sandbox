"""Review/build identity only; no build or deployment implementation."""
import hashlib
from pathlib import Path
from trusted_checker_shadow.policy import digest


def source_digest():
    root=Path(__file__).parent
    packages=(root,*(root.parent/name for name in ('trusted_checker_network','trusted_checker_live',
                                                  'trusted_checker_runtime','trusted_checker_shadow')))
    return digest({str(p.relative_to(root.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for package in packages for p in sorted(package.glob('*.py'))})
