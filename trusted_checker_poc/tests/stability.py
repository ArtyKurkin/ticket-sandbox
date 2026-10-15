"""Offline repeat/order audit: python -m trusted_checker_poc.tests.stability."""
import argparse
import json
import multiprocessing
from pathlib import Path
import random
import sys
import threading
import time
import unittest

from trusted_checker_poc.broker import Broker
from trusted_checker_poc import recovery


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item.id()


class AuditedResult(unittest.TextTestResult):
    def startTest(self, test):
        self.before_threads = set(threading.enumerate())
        self.before_children = set(multiprocessing.active_children())
        super().startTest(test)

    def stopTest(self, test):
        try:
            dangling = set(threading.enumerate()) - self.before_threads
            children = set(multiprocessing.active_children()) - self.before_children
            if dangling or children:
                raise AssertionError('dangling test thread/process after cleanups')
            if Broker._threads._value != 4 or recovery._EVENTS._value != 2:
                raise AssertionError('broker/audit capacity not restored after test')
        except AssertionError:
            self.addFailure(test, sys.exc_info())
        super().stopTest(test)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats',type=int,default=3,choices=range(1,21))
    parser.add_argument('--orders',nargs='+',choices=('normal','reverse','shuffle'),default=['normal','reverse','shuffle'])
    parser.add_argument('--seed',type=int,default=19121)
    parser.add_argument('--output',help='optional NEW JSON result file, outside existing VDS evidence')
    args = parser.parse_args(argv)
    ids = list(flatten(unittest.defaultTestLoader.discover('trusted_checker_poc/tests',top_level_dir='.')))
    if len(ids) != len(set(ids)):
        raise AssertionError('duplicate test IDs')
    rows, escaped, unraisable = [], [], []
    old_thread_hook, old_unraisable_hook = threading.excepthook, sys.unraisablehook
    threading.excepthook = lambda event: escaped.append(event.exc_type.__name__)
    sys.unraisablehook = lambda event: unraisable.append(type(event.exc_value).__name__)
    try:
        for order in args.orders:
            for iteration in range(args.repeats):
                selected = list(ids)
                seed = args.seed + iteration
                if order == 'reverse': selected.reverse()
                if order == 'shuffle': random.Random(seed).shuffle(selected)
                before_threads = set(threading.enumerate())
                started = time.monotonic()
                suite = unittest.defaultTestLoader.loadTestsFromNames(selected)
                result = unittest.TextTestRunner(verbosity=1,resultclass=AuditedResult).run(suite)
                row = {'order':order,'iteration':iteration+1,'seed':seed if order=='shuffle' else None,
                    'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                    'skipped':len(result.skipped),'seconds':round(time.monotonic()-started,3),
                    'dangling_threads':len(set(threading.enumerate())-before_threads),
                    'active_children':len(multiprocessing.active_children()),
                    'escaped_thread_exceptions':len(escaped),'unraisable_exceptions':len(unraisable)}
                rows.append(row)
                print(json.dumps(row),flush=True)
                if not result.wasSuccessful() or any(row[key] for key in
                    ('dangling_threads','active_children','escaped_thread_exceptions','unraisable_exceptions')):
                    return 1
    finally:
        threading.excepthook, sys.unraisablehook = old_thread_hook, old_unraisable_hook
        if args.output:
            with Path(args.output).open('x') as stream:
                json.dump(rows,stream,indent=2)
                stream.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
