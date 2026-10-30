"""Offline tests. Docker, PostgreSQL, pg_dump and migrations are always faked."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from deploy import rehearse_database_upgrade as db


class FakeCommands:
    source_id = 'a' * 64
    clone_id = 'c' * 64

    def __init__(self, run, docker_root):
        self.run = run
        self.docker_root = docker_root
        self.calls = []
        self.migrated = False
        self.dump_failure = False
        self.dump_content = b'PGDMP' + b'\0' * 4096
        self.toc_failure = False
        self.toc_missing_table = False
        self.collision = False
        self.bad_revision = False
        self.bad_mapping = False
        self.bad_target = False
        self.bad_network = False
        self.bad_volume = False
        self.catalog_issues = 0
        self.lost_credits = 0
        self.closed_without_evidence = 0
        self.changed_table = None
        self.fail_phase = None
        self.already_has_program = False
        self.alter_archive = False
        self.superuser = True
        self.regressed_sequence = False
        self.post_nonlegacy = 0
        self.post_awards = 0
        self.invalid_metadata = 0
        self.restore_failure = False
        self.fail_restore_operation = None
        self.restore_stderr = b'PRIVATE_SENTINEL'
        self.owner_superuser = None
        self.bad_owner = False

    def __call__(self, args, **kw):
        self.calls.append((args, kw))
        self.assert_no_removal(args)
        rc, output, stderr = 0, '', b'PRIVATE_SENTINEL'
        if args[0] == 'git':
            output = '0' * 40 if self.bad_revision else db.SOURCE
        else:
            assert args[:3] == db.DOCKER
            cmd = args[3:]
            if cmd[:2] == ['container', 'inspect']:
                ref = cmd[2]
                labels = {'com.docker.compose.project': 'training-platform'}
                env = []
                if ref == db.SOURCE_CONTAINER:
                    labels['com.docker.compose.service'] = 'db'
                    env = ['POSTGRES_USER=PRIVATE_SENTINEL', 'POSTGRES_DB=PRIVATE_SENTINEL']
                    item = {'Id': self.source_id, 'Image': 'sha256:' + 'd' * 64}
                elif ref == 'training-platform-web':
                    labels['com.docker.compose.service'] = 'web'
                    env = ['DB_HOST=db', 'DB_PORT=5432', 'DB_USER=PRIVATE_SENTINEL',
                           'DB_NAME=' + ('different' if self.bad_mapping else 'PRIVATE_SENTINEL')]
                    item = {'Id': 'b' * 64}
                else:
                    assert ref == self.clone_id
                    labels = {'training-platform.rehearsal': self.run.run_id}
                    item = {'Id': self.clone_id, 'Name': '/' + self.run.clone_name,
                            'HostConfig': {'NetworkMode': 'bridge' if self.bad_network else 'none',
                                           'Privileged': False, 'PortBindings': {}},
                            'Mounts': [{'Name': self.run.volume_name,
                                        'Destination': '/var/lib/postgresql/data'}]}
                item.update(Config={'Labels': labels, 'Env': env},
                            State={'Running': True, 'Health': {'Status': 'healthy'}},
                            NetworkSettings={'Networks': {'training-platform-runtime': {}}})
                output = json.dumps([item])
            elif cmd[:2] == ['image', 'inspect']:
                output = json.dumps([{'Config': {'Env': ['PG_MAJOR=16'], 'Labels': {'org.opencontainers.image.revision':
                    'wrong' if self.bad_target else self.run.target_revision}}}])
            elif cmd[:2] == ['volume', 'inspect']:
                output = json.dumps([{'Labels': {'training-platform.rehearsal': self.run.run_id},
                                      'Driver': 'nfs' if self.bad_volume else 'local', 'Options': None}])
            elif cmd[0] == 'info':
                output = json.dumps(str(self.docker_root))
            elif cmd[:2] == ['container', 'ls'] or cmd[:2] == ['volume', 'ls']:
                output = 'existing-resource' if self.collision else ''
            elif cmd[:2] == ['volume', 'create']:
                output = self.run.volume_name
            elif cmd[:2] == ['run', '-d']:
                assert 'POSTGRES_USER=rehearsal_admin' in cmd
                output = self.clone_id
                if self.alter_archive:
                    with (self.run.directory / 'database.dump').open('ab') as handle:
                        handle.write(b'corruption')
            elif cmd[0] == 'run':
                assert '--rm' in cmd and '--mount' not in cmd and '--env-file' not in cmd
                assert cmd[cmd.index('--network') + 1] == 'container:' + self.clone_id
                assert '--privileged' not in cmd and '/var/run/docker.sock' not in cmd
                env = kw['env']
                assert env['DB_HOST'] == '127.0.0.1' and env['DB_NAME'] == 'tp_rehearsal'
                assert env['DB_USER'] == 'rehearsal'
                assert env['TERMINAL_BROKER_ENABLED'] == 'false'
                phase = env['REHEARSAL_PHASE']
                if phase == self.fail_phase:
                    rc, output = 1, 'PRIVATE_SENTINEL'
                elif phase == 'migrate':
                    self.migrated = True
                    output = json.dumps({'migration_count': 15})
                elif phase == 'preflight':
                    output = json.dumps({'catalog_issues': self.catalog_issues})
                else:
                    output = json.dumps({'catalog_issues': 0, 'nonlegacy_journeys': self.post_nonlegacy,
                                         'user_awards': self.post_awards, 'award_events': 0,
                                         'invalid_framework_metadata': self.invalid_metadata,
                                         'new_content_types': 3, 'new_permissions': 12})
            elif cmd[0] == 'exec':
                if 'pg_dump' in cmd[-1]:
                    assert cmd[1] == self.source_id
                    kw['stdout'].write(self.dump_content)
                    rc = int(self.dump_failure)
                elif 'pg_restore' in cmd:
                    if '--list' in cmd:
                        assert self.run.clone_id is None or cmd[2] == self.clone_id
                        rc = int(self.toc_failure)
                        output = '\n'.join('1; 0 0 TABLE DATA public ' + name + ' PRIVATE_SENTINEL'
                            for name in ('sandbox_taskattempt', 'traineediary_traineejourney',
                                         'assessment_examattempt'))
                        if self.toc_missing_table:
                            output = output.replace('sandbox_taskattempt', 'not_the_table')
                    else:
                        assert self.clone_id in cmd and self.source_id not in cmd
                        assert '--single-transaction' in cmd and '--exit-on-error' in cmd
                        assert cmd[cmd.index('-U') + 1] == 'rehearsal'
                        rc = int(self.restore_failure)
                        stderr = self.restore_stderr
                elif 'pg_isready' in cmd:
                    output = 'accepting connections'
                else:
                    sql = kw['input'].decode()
                    if self.source_id in cmd:
                        assert 'default_transaction_read_only=on' in cmd[cmd.index('-e') + 1]
                        assert 'READ ONLY;' in sql and '/* source_metadata */' in sql
                    if '/* source_metadata */' in sql:
                        value = {'bytes': 10 * 1024 ** 2, 'version': 160011,
                                 'superuser': self.superuser, 'can_create': True, 'owns_tables': True}
                    elif '/* tables */' in sql:
                        value = {name: ['id', 'payload'] for name in db.REQUIRED_TABLES}
                    elif '/* migrations */' in sql:
                        value = [[1, 'sandbox', '0030_base'], [2, 'traineediary', '0005_base']]
                        if self.migrated:
                            value += [[i + 3, app, name] for i, (app, name) in
                                      enumerate(sorted(db.EXPECTED_MIGRATIONS))]
                    elif '/* catalog */' in sql:
                        value = {'program_exists': self.already_has_program or self.migrated,
                                 'stage_count': 11 if self.already_has_program or self.migrated else 10}
                    elif '/* progress:' in sql:
                        value = {'historical_attempts': 100, 'closed_without_evidence': self.closed_without_evidence,
                                 'lost_credit_pairs': self.lost_credits, 'gained_credit_pairs': 2,
                                 'affected_users': 2}
                    elif '/* sequences */' in sql:
                        value = {'sandbox_taskattempt_id_seq': {
                            'last_value': 99 if self.migrated and self.regressed_sequence else 100,
                            'increment_by': 1, 'cycle': False}}
                    elif '/* framework_bounds */' in sql:
                        value = {'django_content_type': 20, 'auth_permission': 80}
                    elif '/* clone_owner */' in sql:
                        value = {'bootstrap': self.bad_owner, 'superuser': self.owner_superuser,
                                 'createdb': False, 'createrole': False, 'owns_database': True}
                    elif '/* fingerprint:' in sql:
                        table = sql.split('/* fingerprint:', 1)[1].split(' */', 1)[0]
                        suffix = 'changed' if self.migrated and self.changed_table == table else 'same'
                        value = {'rows': 100, 'digest': hashlib.sha256((table + suffix).encode()).hexdigest()}
                    else:
                        assert self.clone_id in cmd and ('COMMENT ON DATABASE' in sql or 'CREATE ROLE' in sql)
                        if 'CREATE ROLE' in sql:
                            assert 'ALTER DATABASE tp_rehearsal OWNER TO rehearsal' in sql
                            self.owner_superuser = ' LOGIN SUPERUSER ' in sql
                        value = None
                    output = json.dumps(value) if value is not None else ''
                    operation = ('owner' if 'CREATE ROLE' in sql else
                                 'marker' if 'COMMENT ON DATABASE' in sql else
                                 'role_check' if '/* clone_owner */' in sql else None)
                    if operation and operation == self.fail_restore_operation:
                        assert 'VERBOSITY=sqlstate' in cmd[-1]
                        rc, output, stderr = 3, '', self.restore_stderr
            else:
                raise AssertionError('Unapproved Docker command')
        return subprocess.CompletedProcess(args, rc, output.encode(), stderr)

    @staticmethod
    def assert_no_removal(args):
        assert not any(word in args for word in ('rm', 'prune', 'down', 'restart', 'build', 'push'))


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        self.previous_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.previous_umask)
        self.temp = tempfile.TemporaryDirectory(prefix='tp-rehearsal-test-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.backups, self.docker_root = root / 'backups', root / 'docker'
        self.backups.mkdir(mode=0o700)
        self.docker_root.mkdir()
        args = SimpleNamespace(backup_root=self.backups, app_dir=root / 'app',
                               target_revision='e' * 40,
                               target_image='sha256:' + 'f' * 64)
        self.run = db.Rehearsal(args)
        self.fake = FakeCommands(self.run, self.docker_root)
        for p in (patch.object(db.subprocess, 'run', side_effect=self.fake),
                  patch.object(db, 'available_memory', return_value=8 * db.GIB),
                  patch.object(db.shutil, 'disk_usage', return_value=SimpleNamespace(free=100 * db.GIB))):
            p.start()
            self.addCleanup(p.stop)

    def report(self):
        return json.loads((self.run.directory / 'report.json').read_text())

    def assert_failed(self, code):
        self.assertFalse(self.run.run())
        report = self.report()
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['error'], code)
        self.assertFalse(report['live_update_performed'])
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))
        self.assertNotIn(self.run.password, json.dumps(report))

    def test_complete_rehearsal_preserves_original_columns_without_real_commands(self):
        self.assertTrue(self.run.run())
        report = self.report()
        self.assertEqual(report['checks']['historical_data']['tables_changed'], 0)
        self.assertTrue(report['checks']['backup']['toc_checked'])
        self.assertEqual(report['checks']['migrate']['migration_count'], 15)
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(report))
        self.assertNotIn(self.run.password, json.dumps(report))
        self.assertEqual(self.run.directory.stat().st_mode & 0o777, 0o700)
        for path in self.run.directory.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        fingerprints = [kw['input'].decode() for args, kw in self.fake.calls
                        if kw.get('input') and b'/* fingerprint:' in kw['input']]
        self.assertTrue(any("WHERE slug <> 'training-program'" in sql for sql in fingerprints))
        self.assertTrue(any('WHERE id IN (1,2)' in sql for sql in fingerprints))
        self.assertTrue(all('"payload"' in sql for sql in fingerprints))

    def test_existing_training_program_is_compared_instead_of_ignored(self):
        self.fake.already_has_program = True
        self.assertTrue(self.run.run())
        statements = [kw['input'] for args, kw in self.fake.calls if kw.get('input')]
        self.assertFalse(any(b"WHERE slug <> 'training-program'" in sql for sql in statements))

    def test_insufficient_memory_stops_before_dump(self):
        with patch.object(db, 'available_memory', return_value=db.GIB):
            self.assert_failed('insufficient_memory_or_disk')
        self.assertFalse(any('pg_dump' in str(args) for args, kw in self.fake.calls))

    def test_disk_reserve_includes_both_backup_and_clone_on_shared_disk(self):
        with patch.object(db.shutil, 'disk_usage', return_value=SimpleNamespace(free=3 * db.GIB)):
            self.assert_failed('insufficient_memory_or_disk')
        self.assertFalse((self.run.directory / 'database.dump.partial').exists())

    def test_failed_pg_dump_never_publishes_archive_or_creates_clone(self):
        self.fake.dump_failure = True
        self.assert_failed('command_failed')
        self.assertTrue((self.run.directory / 'database.dump.partial').exists())
        self.assertFalse((self.run.directory / 'database.dump').exists())
        self.assertIsNone(self.run.clone_id)

    def test_empty_archive_is_rejected(self):
        self.fake.dump_content = b''
        self.assert_failed('archive_empty_or_invalid')
        self.assertIsNone(self.run.clone_id)

    def test_wrong_archive_header_is_rejected(self):
        self.fake.dump_content = b'notpg' + b'\0' * 4096
        self.assert_failed('archive_empty_or_invalid')

    def test_pg_restore_list_failure_is_fatal(self):
        self.fake.toc_failure = True
        self.assert_failed('archive_command_failed')
        self.assertFalse((self.run.directory / 'database.dump').exists())

    def test_schema_only_or_wrong_database_archive_is_rejected(self):
        self.fake.toc_missing_table = True
        self.assert_failed('archive_required_table_missing')

    def test_archive_checksum_is_rechecked_before_restore(self):
        self.fake.alter_archive = True
        self.assert_failed('archive_checksum_changed')
        self.assertFalse(self.fake.migrated)

    def test_resource_collision_does_not_adopt_or_remove_existing_resources(self):
        self.fake.collision = True
        self.assert_failed('resource_name_collision')
        self.assertFalse(any('create' in args for args, kw in self.fake.calls))

    def test_networked_clone_is_rejected_before_restore(self):
        self.fake.bad_network = True
        self.assert_failed('clone_isolation_failed')
        self.assertFalse(self.fake.migrated)

    def test_external_volume_driver_is_rejected(self):
        self.fake.bad_volume = True
        self.assert_failed('volume_ownership_failed')

    def test_catalog_mismatch_stops_before_migrations(self):
        self.fake.catalog_issues = 2
        self.assert_failed('catalog_or_history_check_failed')
        self.assertEqual(self.report()['checks']['preflight']['catalog_issues'], 2)
        self.assertFalse(self.fake.migrated)

    def test_credit_loss_stops_before_migrations(self):
        self.fake.lost_credits = 1
        self.assert_failed('historical_technical_credit_loss')
        self.assertFalse(self.fake.migrated)

    def test_historical_pass_outside_l1_without_evidence_also_stops(self):
        self.fake.closed_without_evidence = 1
        self.assert_failed('historical_technical_credit_loss')
        self.assertFalse(self.fake.migrated)

    def test_original_data_mutation_is_detected_even_when_row_count_is_unchanged(self):
        self.fake.changed_table = 'assessment_examanswer'
        self.assert_failed('historical_data_changed')
        self.assertEqual(self.report()['checks']['historical_data']['changed_tables'],
                         ['assessment_examanswer'])

    def test_migration_failure_saves_only_safe_report_and_does_not_continue(self):
        self.fake.fail_phase = 'migrate'
        self.assert_failed('command_failed')
        self.assertEqual(self.report()['failed_step'], 'migrations_on_copy')
        self.assertNotIn('postflight', self.report()['checks'])

    def test_unexpected_source_revision_is_rejected_before_backup(self):
        self.fake.bad_revision = True
        self.assert_failed('unexpected_source_revision')
        self.assertFalse(any('pg_dump' in str(args) for args, kw in self.fake.calls))

    def test_wrong_application_database_is_rejected_without_exposing_names(self):
        self.fake.bad_mapping = True
        self.assert_failed('source_application_database_mapping_unverified')

    def test_unverified_target_image_is_rejected(self):
        self.fake.bad_target = True
        self.assert_failed('target_image_revision_not_verified')

    def test_clone_role_does_not_keep_superuser_if_source_role_lacks_it(self):
        self.fake.superuser = False
        self.assertTrue(self.run.run())
        commands = [(args, kw) for args, kw in self.fake.calls
                    if b'CREATE ROLE rehearsal LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE' in (kw.get('input') or b'')]
        self.assertEqual(len(commands), 1)
        self.assertIn(self.fake.clone_id, commands[0][0])

    def test_plan_mode_has_no_external_commands_or_output_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(db.main(['--target-image', 'sha256:' + 'f' * 64,
                                      '--target-revision', 'e' * 40,
                                      '--backup-root', str(self.backups)]), 0)
        self.assertEqual(json.loads(out.getvalue())['mode'], 'plan_only')
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(list(self.backups.iterdir()), [])

    def prepare_reused_backup(self):
        previous = self.backups / 'previous'
        previous.mkdir(mode=0o700)
        archive = previous / 'database.dump'
        archive.write_bytes(self.fake.dump_content)
        report = {
            'source_revision': db.SOURCE, 'live_update_performed': False,
            'checks': {
                'backup': {'valid': True, 'toc_checked': True,
                           'bytes': archive.stat().st_size,
                           'sha256': hashlib.sha256(self.fake.dump_content).hexdigest()},
                'resources': {'backup_required': 2 * 10 * 1024 ** 2 + db.GIB},
            },
        }
        path = previous / 'report.json'
        path.write_text(json.dumps(report))
        self.run.args.reuse_backup_report = path
        self.run.args.postgres_image = 'sha256:' + 'd' * 64
        return path, archive

    def test_reused_backup_never_contacts_source_or_dumps_and_preserves_snapshot(self):
        report_path, archive = self.prepare_reused_backup()
        original = (report_path.read_bytes(), archive.read_bytes())
        self.assertTrue(self.run.run())
        report = self.report()
        self.assertEqual(report['readiness_scope'], 'historical_snapshot_only')
        self.assertFalse(report['source_database_contacted'])
        self.assertTrue(report['snapshot_reused'])
        self.assertEqual(original, (report_path.read_bytes(), archive.read_bytes()))
        self.assertIsNone(self.run.source_id)
        for args, kw in self.fake.calls:
            self.assertNotEqual(args[0], 'git')
            self.assertNotIn(db.SOURCE_CONTAINER, args)
            self.assertNotIn('training-platform-web', args)
            self.assertNotIn(self.fake.source_id, args)
            self.assertNotIn('pg_dump', str(args))
        self.assertTrue(any('CREATE ROLE rehearsal LOGIN NOSUPERUSER' in str(kw.get('input'))
                            for args, kw in self.fake.calls))
        self.assertFalse(any('ALTER ROLE' in str(kw.get('input')) for args, kw in self.fake.calls))

    def test_restore_archive_failure_is_fatal_and_never_sets_marker_or_migrates(self):
        self.prepare_reused_backup()
        self.fake.restore_failure = True
        self.fake.restore_stderr = b'pg_restore: error: PRIVATE_SENTINEL'
        self.assert_failed('archive_command_failed')
        report = self.report()
        self.assertEqual(report['failed_step'], 'restore')
        self.assertEqual(report['checks']['restore']['data'],
                         {'status': 'failed', 'returncode': 1, 'category': 'process_failed'})
        self.assertNotIn('marker', report['checks']['restore'])
        self.assertNotIn('baseline', report['checks'])
        self.assertFalse(self.fake.migrated)

    def test_post_restore_marker_failure_has_its_own_step_and_safe_sqlstate(self):
        self.prepare_reused_backup()
        self.fake.fail_restore_operation = 'marker'
        self.fake.restore_stderr = b'psql:<stdin>:1: ERROR: 42501\nPRIVATE_SENTINEL'
        self.assert_failed('command_failed')
        report = self.report()
        self.assertEqual(report['failed_step'], 'restore_marker')
        self.assertEqual(report['checks']['restore']['data']['status'], 'passed')
        self.assertEqual(report['checks']['restore']['marker'],
                         {'status': 'failed', 'returncode': 3,
                          'category': 'postgres_insufficient_privilege', 'sqlstate': '42501'})
        self.assertFalse(self.fake.migrated)

    def test_owner_setup_failure_does_not_start_restore(self):
        self.prepare_reused_backup()
        self.fake.fail_restore_operation = 'owner'
        self.fake.restore_stderr = b'ERROR: 0A000\nPRIVATE_SENTINEL'
        self.assert_failed('command_failed')
        report = self.report()
        self.assertEqual(report['failed_step'], 'restore_owner')
        self.assertEqual(report['checks']['restore']['owner']['sqlstate'], '0A000')
        self.assertNotIn('data', report['checks']['restore'])
        self.assertFalse(self.fake.migrated)

    def test_bootstrap_owner_is_rejected_after_successful_restore(self):
        self.prepare_reused_backup()
        self.fake.bad_owner = True
        self.assert_failed('clone_owner_privileges_invalid')
        self.assertEqual(self.report()['failed_step'], 'restore_role_check')
        self.assertFalse(self.fake.migrated)

    def test_restore_timeout_diagnostic_cannot_leak_exception_output(self):
        self.prepare_reused_backup()
        def timeout_on_restore(args, **kw):
            if 'pg_restore' in args and '--single-transaction' in args:
                raise subprocess.TimeoutExpired(args, 600, output=b'PRIVATE_SENTINEL',
                                                stderr=b'PRIVATE_SENTINEL')
            return self.fake(args, **kw)
        with patch.object(db.subprocess, 'run', side_effect=timeout_on_restore):
            self.assert_failed('archive_command_unavailable')
        self.assertEqual(self.report()['checks']['restore']['data'],
                         {'status': 'failed', 'category': 'timeout'})
        self.assertFalse(self.fake.migrated)

    def test_only_allowlisted_error_codes_are_reported(self):
        self.assertEqual(db.command_error_category(b'ERROR: TOKEN\nPRIVATE_SENTINEL'),
                         {'category': 'process_failed'})
        self.assertEqual(db.command_error_category(b'FATAL: 28P01\nPRIVATE_SENTINEL'),
                         {'category': 'postgres_authentication_failed', 'sqlstate': '28P01'})

    def test_reused_backup_corruption_stops_before_clone(self):
        _, archive = self.prepare_reused_backup()
        archive.write_bytes(self.fake.dump_content[:-1] + b'x')
        self.assert_failed('archive_checksum_changed')
        self.assertIsNone(self.run.clone_id)

    def test_reused_backup_requires_matching_source_and_valid_backup_report(self):
        path, _ = self.prepare_reused_backup()
        report = json.loads(path.read_text())
        report['source_revision'] = '0' * 40
        path.write_text(json.dumps(report))
        self.assert_failed('reused_backup_provenance_invalid')
        self.assertIsNone(self.run.clone_id)

    def test_reused_backup_requires_private_files(self):
        _, archive = self.prepare_reused_backup()
        archive.chmod(0o644)
        self.assert_failed('reused_backup_not_private')

    def test_reused_backup_checks_toc_again_on_clone(self):
        self.prepare_reused_backup()
        self.fake.toc_missing_table = True
        self.assert_failed('archive_required_table_missing')
        self.assertFalse(self.fake.migrated)

    def test_reused_backup_still_enforces_catalog_and_data_guards(self):
        self.prepare_reused_backup()
        self.fake.catalog_issues = 1
        self.assert_failed('catalog_or_history_check_failed')
        self.assertFalse(self.fake.migrated)

    def test_runs_have_unique_resource_names(self):
        other = db.Rehearsal(self.run.args)
        self.assertNotEqual(self.run.clone_name, other.clone_name)
        self.assertNotEqual(self.run.volume_name, other.volume_name)

    def test_archive_fingerprints_do_not_hide_id_or_relation_changes(self):
        sql = db.fingerprint_sql('test_table', ['id', 'user_id', 'status', 'answer'])
        self.assertIn('"id", "user_id", "status", "answer"', sql)
        self.assertIn('sha256', sql)
        self.assertIn('ORDER BY h', sql)

    def test_old_sequence_cannot_move_backwards(self):
        self.fake.regressed_sequence = True
        self.assert_failed('historical_sequences_regressed')

    def test_docker_environment_cannot_redirect_commands_to_remote_daemon(self):
        with patch.dict(os.environ, {'DOCKER_HOST': 'tcp://example.invalid', 'DOCKER_CONTEXT': 'other'}):
            self.assertTrue(self.run.run())
        for args, kw in self.fake.calls:
            self.assertNotIn('DOCKER_CONTEXT', kw['env'])
            self.assertNotIn('DOCKER_HOST', kw['env'])

    def test_report_write_failure_can_never_return_success(self):
        with patch.object(self.run, 'persist', side_effect=db.RehearsalError('report_write_failed')):
            self.assertFalse(self.run.run())
        self.assertEqual(self.run.report['status'], 'failed')

    def test_new_scheme_for_historical_journey_blocks_success(self):
        self.fake.post_nonlegacy = 1
        self.assert_failed('catalog_or_history_check_failed')

    def test_unexpected_user_awards_block_success(self):
        self.fake.post_awards = 1
        self.assert_failed('catalog_or_history_check_failed')

    def test_separate_filesystems_each_need_their_own_disk_reserve(self):
        backup = MagicMock()
        docker = MagicMock()
        backup.stat.return_value.st_dev = 1
        docker.stat.return_value.st_dev = 2
        with patch.object(db.shutil, 'disk_usage', side_effect=[
                SimpleNamespace(free=100 * db.GIB), SimpleNamespace(free=db.GIB)]):
            ok, stats = db.check_resources(backup, docker, 100)
        self.assertFalse(ok)
        self.assertFalse(stats['shared_filesystem'])

    def test_unknown_framework_metadata_blocks_success(self):
        self.fake.invalid_metadata = 1
        self.assert_failed('catalog_or_history_check_failed')

    def test_framework_metadata_preserves_original_ids_and_reports_additions(self):
        self.assertTrue(self.run.run())
        self.assertEqual(self.report()['checks']['postflight']['new_permissions'], 12)
        queries = [(kw.get('input') or b'').decode() for args, kw in self.fake.calls]
        self.assertTrue(any('fingerprint:auth_permission' in sql and 'WHERE id <= 80' in sql
                            for sql in queries))
        self.assertTrue(any('fingerprint:django_content_type' in sql and 'WHERE id <= 20' in sql
                            for sql in queries))


class ApplicationGuardTests(unittest.TestCase):
    """Execute only the embedded guard, against fake Django/DB modules."""

    def setUp(self):
        self.executor = MagicMock()
        self.call_command = MagicMock()
        self.contract = MagicMock()
        self.contract.catalog_issues.return_value = []
        self.cursor = MagicMock()
        self.cursor.fetchone.return_value = ('tp_rehearsal', 'rehearsal-marker')
        self.connection = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        model = MagicMock()
        model.objects.exclude.return_value.count.return_value = 0
        model.objects.count.return_value = 0
        self.executor.loader.project_state.return_value.apps.get_model.return_value = model
        self.apps = self.executor.loader.project_state.return_value.apps
        django = ModuleType('django')
        django.setup = MagicMock()
        database = ModuleType('django.db')
        database.connection = self.connection
        executor_module = ModuleType('django.db.migrations.executor')
        executor_module.MigrationExecutor = MagicMock(return_value=self.executor)
        management = ModuleType('django.core.management')
        management.call_command = self.call_command
        self.modules = {'django': django, 'django.db': database,
                        'django.core': ModuleType('django.core'),
                        'django.core.management': management,
                        'django.db.migrations': ModuleType('django.db.migrations'),
                        'django.db.migrations.executor': executor_module}

    def execute(self, phase, override=None, plan=None, optimize=0):
        self.executor.migration_plan.return_value = (
            [] if phase == 'postflight' else
            [(SimpleNamespace(app_label=app, name=name), False)
             for app, name in sorted(db.EXPECTED_MIGRATIONS)]) if plan is None else plan
        env = {'DB_HOST': '127.0.0.1', 'DB_NAME': 'tp_rehearsal',
               'TERMINAL_BROKER_ENABLED': 'false', 'REHEARSAL_PHASE': phase,
               'REHEARSAL_MARKER': 'rehearsal-marker',
               'FRAMEWORK_BOUNDS': json.dumps({'django_content_type': 20, 'auth_permission': 80}),
               'EXPECTED_MIGRATIONS': json.dumps(sorted(db.EXPECTED_MIGRATIONS))}
        env.update(override or {})
        out = io.StringIO()
        with patch.dict('sys.modules', self.modules), patch.dict(os.environ, env, clear=True), \
             patch.object(Path, 'exists', return_value=False), \
             patch('importlib.import_module', return_value=self.contract) as importer, \
             contextlib.redirect_stdout(out):
            self.contract_import = importer
            try:
                exec(compile(db.APP_COMMAND, '<isolated-migration-guard>', 'exec', optimize=optimize), {})
            except SystemExit as exc:
                self.assertEqual(phase, 'migrate')
                self.assertEqual(exc.code, 0)
        return json.loads(out.getvalue())

    def test_marker_mismatch_prevents_migration(self):
        self.cursor.fetchone.return_value = ('tp_rehearsal', 'wrong-marker')
        with self.assertRaises(RuntimeError):
            self.execute('migrate')
        self.call_command.assert_not_called()

    def test_wrong_database_prevents_migration(self):
        self.cursor.fetchone.return_value = ('actual-live-database', 'rehearsal-marker')
        with self.assertRaises(RuntimeError):
            self.execute('migrate')
        self.call_command.assert_not_called()

    def test_enabled_broker_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.execute('migrate', {'TERMINAL_BROKER_ENABLED': 'true'})
        self.call_command.assert_not_called()

    def test_unexpected_migration_plan_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.execute('migrate', plan=[(SimpleNamespace(app_label='other', name='0001'), False)])
        self.call_command.assert_not_called()

    def test_backwards_plan_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.execute('migrate', plan=[(SimpleNamespace(app_label='sandbox', name='0036'), True)])
        self.call_command.assert_not_called()

    def test_only_matching_marker_and_exact_plan_authorize_copy_migrations(self):
        self.assertEqual(self.execute('migrate'), {'migration_count': 15})
        self.call_command.assert_called_once()
        self.assertEqual(self.call_command.call_args.args, ('migrate',))
        self.assertFalse(self.call_command.call_args.kwargs['interactive'])

    def test_catalog_issue_text_is_not_printed(self):
        self.contract.catalog_issues.return_value = ['PRIVATE_SENTINEL']
        self.assertEqual(self.execute('preflight'), {'catalog_issues': 1})
        self.call_command.assert_not_called()

    def test_postflight_uses_classified_catalog_contract(self):
        result = self.execute('postflight')
        self.assertEqual(result['nonlegacy_journeys'], 0)
        self.assertTrue(self.contract.catalog_issues.call_args.kwargs['classified'])
        self.call_command.assert_not_called()

    def test_preflight_uses_the_migrations_catalog_validator(self):
        self.assertEqual(self.execute('preflight'), {'catalog_issues': 0})
        self.contract_import.assert_called_once_with(
            'traineediary.migrations.0007_classify_stage_catalog')
        self.contract.catalog_issues.assert_called_once()
        self.assertFalse(self.contract.catalog_issues.call_args.kwargs['classified'])
        self.call_command.assert_not_called()

    def test_postflight_rejects_unregistered_metadata(self):
        content_type = SimpleNamespace(app_label='unknown', model='unexpected')
        types = MagicMock()
        types.objects.filter.return_value = [content_type]
        permissions = MagicMock()
        permissions.objects.filter.return_value.select_related.return_value = []
        original = self.apps.get_model.return_value
        self.apps.get_model.side_effect = lambda app, name: (
            types if (app, name) == ('contenttypes', 'ContentType') else
            permissions if (app, name) == ('auth', 'Permission') else original)
        self.apps.get_models.return_value = []
        self.assertEqual(self.execute('postflight')['invalid_framework_metadata'], 1)

    def test_postflight_accepts_only_registered_permission_codenames(self):
        content_type = SimpleNamespace(app_label='roadmap', model='entry')
        types = MagicMock()
        types.objects.filter.return_value = [content_type]
        permissions = MagicMock()
        permissions.objects.filter.return_value.select_related.return_value = [
            SimpleNamespace(content_type=content_type, codename='add_entry'),
            SimpleNamespace(content_type=content_type, codename='unapproved_entry')]
        original = self.apps.get_model.return_value
        self.apps.get_model.side_effect = lambda app, name: (
            types if (app, name) == ('contenttypes', 'ContentType') else
            permissions if (app, name) == ('auth', 'Permission') else original)
        self.apps.get_models.return_value = [SimpleNamespace(_meta=SimpleNamespace(
            app_label='roadmap', model_name='entry', default_permissions=('add',), permissions=()))]
        result = self.execute('postflight')
        self.assertEqual(result['invalid_framework_metadata'], 1)
        self.assertEqual(result['new_permissions'], 2)

    def test_optimized_python_cannot_remove_database_guard(self):
        self.cursor.fetchone.return_value = ('wrong-db', 'wrong-marker')
        with self.assertRaises(RuntimeError):
            self.execute('migrate', optimize=2)
        self.call_command.assert_not_called()

    def test_expected_plan_matches_the_fifteen_checked_in_migrations(self):
        root = Path(__file__).resolve().parents[2]
        limits = {'sandbox': 30, 'traineediary': 5, 'roadmap': 0, 'achievements': 0}
        expected = {(app, p.stem) for app, limit in limits.items()
                    for p in (root / app / 'migrations').glob('[0-9]*.py')
                    if int(p.name.split('_', 1)[0]) > limit}
        self.assertEqual(db.EXPECTED_MIGRATIONS, expected)


if __name__ == '__main__':
    unittest.main()
