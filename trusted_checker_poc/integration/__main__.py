"""Run on the separately approved VDS. Default behavior denies Docker execution."""
import argparse
import json
from importlib.metadata import version

from ..contracts import timestamp

from .evidence import Journal, exclusive
from .runtime import Runtime
from .safety import Approval, Denied, connect, preflight, atom
from .scenarios import Scenarios
from ..recovery import reconcile


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='command', required=True)
    for command in ('preflight', 'run', 'cleanup', 'report', 'reconcile'):
        child = commands.add_parser(command)
        if command != 'preflight':
            child.add_argument('--directory', required=True, help='private run directory; run requires NEW path')
        if command == 'report':
            continue
        child.add_argument('--endpoint', required=True, help='explicit unix:/// socket on approved dedicated VDS')
        child.add_argument('--approved-daemon-id', required=True)
        child.add_argument('--approve-isolated-daemon', action='store_true')
        child.add_argument('--scope', required=True, help='poc- lowercase unique operator scope')
        child.add_argument('--runner-image', required=True, help='sha256:full image ID')
        child.add_argument('--target-image', required=True, help='sha256:full image ID')
        child.add_argument('--python-base', required=True, help='operator-recorded digest-pinned build input')
        child.add_argument('--network-id', help='optional existing network inspected read-only; NEVER reused by run')
        if command in ('run', 'cleanup', 'reconcile'):
            child.add_argument('--allow-execution', action='store_true')
        if command == 'reconcile':
            child.add_argument('--run-id', required=True)
            child.add_argument('--runner-id', required=True)
            child.add_argument('--apply', action='store_true', help='append audited cleanup-only ownership; default dry-run')
        if command == 'run':
            child.add_argument('--scenario', choices=('prepare','full'), default='prepare',
                               help='default: one prepare diagnostic; full suite requires explicit selection')
            child.add_argument('--repetitions', type=int, default=10, choices=range(1, 51), metavar='1..50')
    return result


def main(argv=None, *, connector=connect):
    args = parser().parse_args(argv)
    client = None
    try:
        if args.command == 'report':
            # Offline regeneration after an interrupted run: SQLite mode=ro,
            # no Docker SDK calls and no writable State construction.
            with exclusive(args.directory):
                journal = Journal(args.directory)
                journal.report()
                body = journal.body
            print(json.dumps({'integration_id': body['integration_id'], 'status': body['status'],
                              'cleanup_status': body.get('cleanup_status'), 'scenarios': body['scenarios']}, indent=2))
            return 0
        approval = Approval(args.endpoint, args.approved_daemon_id, args.scope, args.runner_image,
                            args.target_image, args.python_base, args.approve_isolated_daemon,
                            getattr(args, 'allow_execution', False), args.network_id)
        mutation = args.command in ('run','cleanup') or (args.command == 'reconcile' and args.apply)
        approval.validate(mutation)
        client = connector(approval, mutation)
        environment = preflight(client, approval)
        environment['docker_sdk_version'] = atom(version('docker'))
        if args.command == 'preflight':
            print(json.dumps(environment, indent=2))
            return 0
        if args.command in ('cleanup', 'reconcile'):
            with exclusive(args.directory):
                journal = Journal(args.directory)
                old = journal.body['environment']
                if (old['daemon_id'] != approval.daemon_id or old['images'] != environment['images'] or
                        journal.body['scope'] != approval.scope + '-' + journal.body['integration_id'][:8]):
                    raise Denied('journal_environment_mismatch')
                if args.command == 'reconcile':
                    outcome = reconcile(client, approval, journal, args.run_id, args.runner_id, apply=args.apply)
                    if args.apply:
                        journal.report()
                    print(json.dumps(outcome, indent=2))
                    return 4 if outcome['status'] == 'quarantine' else 0
                runtime = Runtime(client, approval, journal)
                complete = runtime.cleanup()
                print(json.dumps({'status': 'cleanup_complete' if complete else 'cleanup_incomplete'}))
                return 0 if complete else 4
        journal = Journal(args.directory, create=True, approval=approval, environment=environment)
        journal.body['mode'] = args.scenario
        with exclusive(args.directory):
            runtime = Runtime(client, approval, journal)
            try:
                runtime.provision()
                scenarios = Scenarios(runtime, args.repetitions)
                if args.scenario == 'prepare':
                    scenarios.run_diagnostic()
                else:
                    scenarios.run()
            except (Exception, KeyboardInterrupt):
                journal.body['status'] = 'test_inconclusive'
                journal.body['unverified'].append('integration_interrupted_or_provisioning_unknown')
            finally:
                if journal.body['finished_at'] is None:
                    journal.body['finished_at'] = timestamp()
                try:
                    complete = runtime.cleanup()
                except Exception:
                    complete = False
                    journal.body['cleanup_status'] = 'cleanup_incomplete'
                journal.report()
            print(json.dumps({'integration_id': journal.body['integration_id'], 'status': journal.body['status'],
                              'cleanup_status': journal.body['cleanup_status']}))
            if not complete:
                return 4
            return {'test_passed': 0, 'test_failed': 2, 'test_inconclusive': 3}[journal.body['status']]
    except Denied as error:
        print(json.dumps({'status': 'environment_not_approved', 'reason': str(error)}))
        return 5
    except Exception:
        print(json.dumps({'status': 'test_inconclusive', 'reason': 'operation_unconfirmed'}))
        return 3
    finally:
        if client is not None:
            client.close()


if __name__ == '__main__':
    raise SystemExit(main())
