"""Opt-in PostgreSQL proof using a private local cluster, never Docker or live DBs.

Set TP_REHEARSAL_POSTGRES_BIN to a local PostgreSQL 16 bin directory to run.
No backups, restores or application migrations are executed by these tests.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from deploy import rehearse_database_upgrade as db


@unittest.skipUnless(os.environ.get('TP_REHEARSAL_POSTGRES_BIN'), 'local PostgreSQL opt-in required')
class PostgresOwnerTests(unittest.TestCase):
    def setUp(self):
        self.bin = Path(os.environ['TP_REHEARSAL_POSTGRES_BIN'])
        self.temp = tempfile.TemporaryDirectory(prefix='tp-owner-test-', dir='/private/tmp' if Path('/private/tmp').exists() else None)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.data, self.socket = self.root / 'data', self.root / 'socket'
        self.socket.mkdir(mode=0o700)
        # Ignore caller PGHOST/PGSERVICE/PGOPTIONS; every connection uses our socket.
        env = {k: v for k, v in os.environ.items() if not k.startswith('PG')}
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.checked([str(self.bin / 'initdb'), '-D', str(self.data), '-U', 'rehearsal_admin',
                      '-A', 'trust', '--no-locale'])
        self.checked([str(self.bin / 'pg_ctl'), '-D', str(self.data), '-l', str(self.root / 'postgres.log'),
                      '-o', f"-h '' -k {self.socket}", '-w', 'start'])
        self.addCleanup(self.stop_cluster)
        self.checked(self.psql_args(database='postgres'), input=b'CREATE DATABASE tp_rehearsal;')

    def checked(self, argv, **kwargs):
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, **kwargs)
        self.assertEqual(result.returncode, 0, 'synthetic PostgreSQL command failed')
        return result

    def stop_cluster(self):
        self.checked([str(self.bin / 'pg_ctl'), '-D', str(self.data), '-m', 'fast', '-w', 'stop'])

    def psql_args(self, user='rehearsal_admin', database='tp_rehearsal'):
        return [str(self.bin / 'psql'), '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
                '-v', 'VERBOSITY=sqlstate', '-h', str(self.socket),
                '-U', user, '-d', database]

    def psql(self, sql, user='rehearsal_admin'):
        return self.checked(self.psql_args(user), input=sql.encode()).stdout.decode()

    def test_bootstrap_cannot_be_demoted(self):
        result = subprocess.run(self.psql_args(),
                                input=b'ALTER ROLE rehearsal_admin NOSUPERUSER NOCREATEDB NOCREATEROLE;',
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(db.command_error_category(result.stderr),
                         {'category': 'postgres_feature_not_supported', 'sqlstate': '0A000'})
        self.assertEqual(self.psql("SELECT oid=10 AND rolsuper FROM pg_roles WHERE rolname=current_user;"), 't\n')

    def test_real_owner_setup_uses_a_nonbootstrap_role_with_no_superuser(self):
        run = db.Rehearsal(SimpleNamespace(target_revision='e' * 40))
        run.clone_id = 'c' * 64
        original = run.command

        def local_command(argv, **kwargs):
            self.assertEqual(argv[:3], db.DOCKER)
            self.assertIn(run.clone_id, argv)
            return original(self.psql_args(), **kwargs)

        with patch.object(run, 'command', side_effect=local_command):
            run.prepare_clone_owner(superuser=False)
            self.assertEqual(run.sql(db.CLONE_OWNER),
                             {'bootstrap': False, 'superuser': False, 'createdb': False,
                              'createrole': False, 'owns_database': True})
            run.sql("COMMENT ON DATABASE tp_rehearsal IS 'synthetic-marker';",
                    readonly=False, restore_operation='marker')
        # A schema object can be restored/created by the actual application role.
        self.psql('CREATE TABLE restore_probe (id integer PRIMARY KEY);', user='rehearsal')
        self.assertEqual(self.psql("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname='restore_probe';"),
                         'rehearsal\n')
        self.assertEqual(run.report['checks']['restore']['owner']['status'], 'passed')
        self.assertNotIn(run.password, json.dumps(run.report))
