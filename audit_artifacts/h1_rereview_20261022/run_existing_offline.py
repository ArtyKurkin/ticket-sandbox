"""Selected existing H1 suites. Do not invoke native entry or OS backend tests."""
from pathlib import Path
import json
import unittest

EXCLUDE={
 'trusted_checker_network.tests.test_native_v2_helper.LifecycleTests.test_native_entry_closed_for_fake_approval',
 'trusted_checker_network.tests.test_native_v2_helper.LifecycleTests.test_helper_one_invocation_only',
 'trusted_checker_network.tests.test_native_v2_helper.IsolationTests.test_native_calls_guard_before_syscall',
 'trusted_checker_network.tests.test_native_v2_helper.IsolationTests.test_old_os_fake_backend_does_not_accept_new_kernel',
}
def flatten(suite):
 for item in suite:
  if isinstance(item,unittest.TestSuite):yield from flatten(item)
  else:yield item
suite=unittest.defaultTestLoader.loadTestsFromNames([
 'trusted_checker_network.tests.test_native_v2_helper',
 'trusted_checker_network.tests.test_native_v2_helper_security'])
all_tests=list(flatten(suite));selected=[test for test in all_tests if test.id() not in EXCLUDE]
assert len(all_tests)==187 and len(selected)==183
result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
Path(__file__).with_name('existing-results.json').write_text(json.dumps({
 'available':len(all_tests),'selected':len(selected),'excluded':sorted(EXCLUDE),
 'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
 'skips':len(result.skipped)},indent=2)+'\n')
raise SystemExit(0 if result.wasSuccessful() else 1)
