#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo "Normalizing training_tasks permissions..."

git ls-files -z -- training_tasks |
while IFS= read -r -d '' file; do
    mode="$(git ls-files -s -- "$file" | awk '{print $1}')"

    case "$mode" in
        100644)
            chmod 0644 "$file"
            ;;
        100755)
            chmod 0755 "$file"
            ;;
    esac
done

find training_tasks -type d -exec chmod 0755 {} +

echo "Checking training_tasks permissions..."

bad_files="$(find training_tasks -type f ! -perm -004 -print)"

if [ -n "$bad_files" ]; then
    echo "ERROR: files are not readable:"
    echo "$bad_files"
    exit 1
fi

echo "training_tasks permissions OK"