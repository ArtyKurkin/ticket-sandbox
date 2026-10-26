# H1 independent re-review evidence, 2026-10-22

Production and pre-existing tests/fixtures/reports remain read-only.
`baseline.json` pins 324 artifacts before any probes. `invariants.md` was written
after production inspection, before reviewing remediation test expectations.

`test_h1_rereview.py` uses supplied synthetic support only to create a valid
baseline, then independently exercises original and adjacent failure paths.

- Default mode asserts that five defects reproduce: green is NOT a security pass.
- `--assert-safe` uses safe outcomes: five failures are expected on this revision.
- No expected-failure/skip decorators conceal findings.
- RR04 uses two daemon audit threads to observe an actual Python lock cycle.
  They remain blocked within that test process only; interpreter exit discards
  them. No native helper/OS backend/process/namespace/FD-exec/network is launched.
- Run each mode in a separate local Python process, as below. Do not import this
  test as a long-lived application service: the deliberate deadlock is evidence.

From repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning - <<'PY'
import runpy
runpy.run_path('audit_artifacts/h1_rereview_20261022/test_h1_rereview.py', run_name='__main__')
PY
```

Safe mode (expected exit 1 / five failures):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning - <<'PY'
import runpy, sys
sys.argv = ['test_h1_rereview.py', '--assert-safe']
runpy.run_path('audit_artifacts/h1_rereview_20261022/test_h1_rereview.py', run_name='__main__')
PY
```

Existing offline selection (183 tests; four native-entry/OS-backend tests excluded
explicitly, not runtime skips):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -W error::ResourceWarning - <<'PY'
import runpy
runpy.run_path('audit_artifacts/h1_rereview_20261022/run_existing_offline.py', run_name='__main__')
PY
```

Each command writes its JSON result beside its runner. Saved logs were captured
by the audit execution shell. Full report: [V2-06a-H1-INDEPENDENT-REREVIEW.md](../../V2-06a-H1-INDEPENDENT-REREVIEW.md).
