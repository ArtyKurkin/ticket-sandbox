#!/usr/bin/env python3
"""Explicitly opted-in, local-only rehearsal from 92a1123 to a pinned revision.

Default mode only prints a plan. Never updates the live application or removes
containers/volumes. stdout/stderr from external commands are never logged.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid

SOURCE = '92a1123486c1e8ca348ce28e8726944532bed63b'
GIB = 1024 ** 3
MIN_MEMORY = 3 * GIB
SOURCE_CONTAINER = 'training-platform-db'
DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']
REQUIRED_TABLES = {
    'sandbox_taskattempt', 'sandbox_checkrun', 'sandbox_aireview',
    'traineediary_traineejourney', 'traineediary_traineestage',
    'traineediary_stagehistory', 'traineediary_weeklymetric',
    'assessment_examassignment', 'assessment_examattempt',
    'assessment_examquestionsnapshot', 'assessment_examanswer',
    'assessment_assessmentresult', 'django_migrations', 'auth_user',
    'django_content_type', 'auth_permission',
}
EXPECTED_MIGRATIONS = {
    ('sandbox', '0031_sandbox_program_completion'),
    ('sandbox', '0032_evidence_ledger'),
    ('sandbox', '0033_ledger_guards'),
    ('sandbox', '0034_http_observation'),
    ('sandbox', '0035_terminal_broker_generation'),
    ('sandbox', '0036_terminal_lite_operation'),
    ('traineediary', '0006_stage_schemes'),
    ('traineediary', '0007_classify_stage_catalog'),
    ('achievements', '0001_initial'),
    ('achievements', '0002_achievementoperation'),
    ('achievements', '0003_catalog_v1'),
    ('achievements', '0004_audit_guards'),
    ('achievements', '0005_notifications'),
    ('achievements', '0006_sandbox_advanced_activation'),
    ('roadmap', '0001_initial'),
}

SOURCE_METADATA = """/* source_metadata */
SELECT json_build_object(
 'bytes', pg_database_size(current_database()),
 'version', current_setting('server_version_num')::int,
 'superuser', (SELECT rolsuper FROM pg_roles WHERE rolname=current_user),
 'can_create', has_schema_privilege(current_user, 'public', 'CREATE'),
 'owns_tables', COALESCE((SELECT bool_and(pg_get_userbyid(c.relowner)=current_user)
   FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname='public' AND c.relkind='r'), false));
"""
TABLES = """/* tables */
SELECT COALESCE(json_object_agg(table_name, cols), '{}'::json)
FROM (SELECT table_name, json_agg(column_name ORDER BY ordinal_position) AS cols
 FROM information_schema.columns WHERE table_schema='public'
 AND table_name IN (SELECT tablename FROM pg_tables WHERE schemaname='public')
 GROUP BY table_name) s;
"""
MIGRATIONS = """/* migrations */
SELECT COALESCE(json_agg(json_build_array(id, app, name) ORDER BY id), '[]'::json)
FROM django_migrations;
"""
CATALOG = """/* catalog */
SELECT json_build_object('program_exists', EXISTS (
 SELECT 1 FROM traineediary_traineestage WHERE slug='training-program'),
 'stage_count', (SELECT count(*) FROM traineediary_traineestage));
"""
SEQUENCES = """/* sequences */
SELECT COALESCE(json_object_agg(sequencename, json_build_object(
 'last_value', last_value, 'increment_by', increment_by, 'cycle', cycle)), '{}'::json)
FROM pg_sequences WHERE schemaname='public';
"""
FRAMEWORK_BOUNDS = """/* framework_bounds */
SELECT json_build_object(
 'django_content_type', (SELECT COALESCE(max(id), 0) FROM django_content_type),
 'auth_permission', (SELECT COALESCE(max(id), 0) FROM auth_permission));
"""
CLONE_OWNER = """/* clone_owner */
SELECT json_build_object(
 'bootstrap', r.oid=10, 'superuser', r.rolsuper,
 'createdb', r.rolcreatedb, 'createrole', r.rolcreaterole,
 'owns_database', d.datdba=r.oid)
FROM pg_roles r CROSS JOIN pg_database d
WHERE r.rolname='rehearsal' AND d.datname=current_database();
"""
PROGRESS = """/* progress: aggregates only */
WITH evidence AS (
 SELECT a.id, a.user_id, a.task_id, a.status, a.attempt_number,
        (a.technical_passed_at IS NOT NULL OR EXISTS (
          SELECT 1 FROM sandbox_checkrun c WHERE c.attempt_id=a.id
          AND c.result='passed' AND c.exit_code=0)) AS new_passed,
        (q.is_active AND t.is_active AND q.slug='l1') AS eligible
 FROM sandbox_taskattempt a JOIN sandbox_task t ON t.id=a.task_id
 JOIN sandbox_queue q ON q.id=t.queue_id
), pairs AS (
 SELECT user_id, task_id,
        (array_agg(status='passed' ORDER BY id DESC))[1] AS old_passed,
        bool_or(new_passed) AS new_passed
 FROM evidence WHERE attempt_number=1 AND eligible GROUP BY user_id, task_id
)
SELECT json_build_object(
 'historical_attempts', (SELECT count(*) FROM evidence),
 'closed_without_evidence', (SELECT count(*) FROM evidence
   WHERE status='passed' AND NOT new_passed),
 'lost_credit_pairs', (SELECT count(*) FROM pairs WHERE old_passed AND NOT new_passed),
 'gained_credit_pairs', (SELECT count(*) FROM pairs WHERE NOT old_passed AND new_passed),
 'affected_users', (SELECT count(DISTINCT user_id) FROM pairs
   WHERE old_passed <> new_passed));
"""

# Runs only inside a disposable container sharing the network-none clone's
# namespace. No application server, Celery worker or production env file.
APP_COMMAND = r'''
import importlib, io, json, os
from pathlib import Path
def require(condition):
    if not condition:
        raise RuntimeError('rehearsal_guard_failed')
require(not Path('/app/.env').exists() and not Path('/app/.env.prod').exists())
require(os.environ['TERMINAL_BROKER_ENABLED'] == 'false')
require(os.environ['DB_HOST'] == '127.0.0.1')
require(os.environ['DB_NAME'] == 'tp_rehearsal')
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
with connection.cursor() as c:
    c.execute("SELECT current_database(), shobj_description(oid, 'pg_database') "
              "FROM pg_database WHERE datname=current_database()")
    name, marker = c.fetchone()
require(name == 'tp_rehearsal' and marker == os.environ['REHEARSAL_MARKER'])
executor = MigrationExecutor(connection)
contract = importlib.import_module('traineediary.migrations.0007_classify_stage_catalog')
phase = os.environ['REHEARSAL_PHASE']
if phase == 'preflight':
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    actual = {(m.app_label, m.name) for m, backwards in plan if not backwards}
    expected = {tuple(x) for x in json.loads(os.environ['EXPECTED_MIGRATIONS'])}
    require(not any(backwards for m, backwards in plan) and actual == expected)
    apps = executor.loader.project_state([
        ('traineediary', '0005_traineejourney_completed_at_and_more')]).apps
elif phase == 'migrate':
    # Repeat the exact plan guard immediately before executing DDL.
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    expected = {tuple(x) for x in json.loads(os.environ['EXPECTED_MIGRATIONS'])}
    require(not any(b for m, b in plan))
    require({(m.app_label, m.name) for m, b in plan} == expected)
    from django.core.management import call_command
    # Match deployment, including Django's post_migrate metadata creation.
    call_command('migrate', interactive=False, verbosity=0,
                 stdout=io.StringIO(), stderr=io.StringIO())
    print(json.dumps({'migration_count': len(expected)}))
    raise SystemExit(0)
else:
    require(phase == 'postflight')
    require(not executor.migration_plan(executor.loader.graph.leaf_nodes()))
    apps = executor.loader.project_state(executor.loader.graph.leaf_nodes()).apps
Stage = apps.get_model('traineediary', 'TraineeStage')
Journey = apps.get_model('traineediary', 'TraineeJourney')
History = apps.get_model('traineediary', 'StageHistory')
issues = contract.catalog_issues(Stage, Journey, History, 'default',
                                classified=phase == 'postflight')
result = {'catalog_issues': len(issues)}
if phase == 'postflight':
    result['nonlegacy_journeys'] = Journey.objects.exclude(stage_scheme='legacy').count()
    result['user_awards'] = apps.get_model('achievements', 'UserAchievement').objects.count()
    result['award_events'] = apps.get_model('achievements', 'AchievementEvent').objects.count()
    bounds = json.loads(os.environ['FRAMEWORK_BOUNDS'])
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')
    models = {(m._meta.app_label, m._meta.model_name): m for m in apps.get_models()}
    new_types = list(ContentType.objects.filter(pk__gt=bounds['django_content_type']))
    new_permissions = list(Permission.objects.filter(
        pk__gt=bounds['auth_permission']).select_related('content_type'))
    invalid = sum((c.app_label, c.model) not in models for c in new_types)
    for permission in new_permissions:
        ct = permission.content_type
        model = models.get((ct.app_label, ct.model))
        allowed = set() if model is None else {
            action + '_' + model._meta.model_name for action in model._meta.default_permissions
        } | {codename for codename, name in model._meta.permissions}
        invalid += permission.codename not in allowed
    result['invalid_framework_metadata'] = invalid
    result['new_content_types'] = len(new_types)
    result['new_permissions'] = len(new_permissions)
print(json.dumps(result))
'''


class RehearsalError(Exception):
    """Only fixed technical codes; never wrap raw subprocess/SQL exceptions."""


def command_error_category(stderr):
    """Only allowlisted SQLSTATE values leave memory; never return error text."""
    states = {
        '0A000': 'postgres_feature_not_supported',
        '42501': 'postgres_insufficient_privilege',
        '28P01': 'postgres_authentication_failed',
        '28000': 'postgres_authentication_failed',
        '3D000': 'postgres_database_missing',
        '42710': 'postgres_duplicate_object',
        '42601': 'postgres_syntax_error',
        '23503': 'postgres_foreign_key_violation',
        '23505': 'postgres_unique_violation',
        '25006': 'postgres_read_only_transaction',
        '57014': 'postgres_statement_cancelled',
        '55P03': 'postgres_lock_unavailable',
        '53100': 'postgres_disk_full',
        '53200': 'postgres_out_of_memory',
    }
    message = (stderr or b'').decode('utf-8', errors='replace')
    for state in re.findall(r'\b(?:ERROR|FATAL):\s+([0-9A-Z]{5})\b', message):
        if state in states:
            return {'category': states[state], 'sqlstate': state}
    return {'category': 'process_failed'}


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def fingerprint_sql(table, columns, where=''):
    projection = ', '.join(quote(c) for c in columns)
    return f"""/* fingerprint:{table} */
    WITH hashes AS (SELECT encode(sha256(convert_to(to_jsonb(r)::text, 'UTF8')), 'hex') h
      FROM (SELECT {projection} FROM public.{quote(table)} {where}) r)
    SELECT json_build_object('rows', count(*), 'digest',
      encode(sha256(convert_to(COALESCE(string_agg(h, '' ORDER BY h), ''), 'UTF8')), 'hex'))
    FROM hashes;"""


def available_memory():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) * 1024
    raise RehearsalError('memory_unavailable')


def check_resources(backup_root, docker_root, db_bytes):
    memory = available_memory()
    backup_need, docker_need = 2 * db_bytes + GIB, 3 * db_bytes + 2 * GIB
    same_disk = backup_root.stat().st_dev == docker_root.stat().st_dev
    backup_free = shutil.disk_usage(backup_root).free
    docker_free = shutil.disk_usage(docker_root).free
    stats = {'memory_available': memory, 'memory_required': MIN_MEMORY,
             'backup_free': backup_free, 'docker_free': docker_free,
             'backup_required': backup_need, 'docker_required': docker_need,
             'shared_filesystem': same_disk}
    ok = memory >= MIN_MEMORY and (
        backup_free >= backup_need + docker_need if same_disk
        else backup_free >= backup_need and docker_free >= docker_need)
    return ok, stats


def compare_snapshots(before, after):
    changed = [table for table in before if before[table] != after.get(table)]
    return {'tables_checked': len(before), 'tables_changed': len(changed),
            'changed_tables': sorted(changed)}


def compare_sequences(before, after):
    changed = []
    for name, old in before.items():
        new = after.get(name)
        if (new is None or new['increment_by'] != old['increment_by'] or new['cycle'] != old['cycle']
            or (old['last_value'] is not None and
                (new['last_value'] is None or new['last_value'] < old['last_value']))):
            changed.append(name)
    return {'sequences_checked': len(before), 'sequences_regressed': len(changed)}


def process_environment(extra=None):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')
    for key in ('DOCKER_CONTEXT', 'DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        env.pop(key, None)
    env.update(extra or {})
    return env


class Rehearsal:
    def __init__(self, args):
        self.args = args
        self.run_id = uuid.uuid4().hex
        self.clone_name = 'tp-db-rehearsal-' + self.run_id
        self.volume_name = self.clone_name + '-data'
        self.clone_id = None
        self.password = secrets.token_hex(32)
        self.source_id = None
        self.directory = None
        self.framework_bounds = {}
        self.target_revision = args.target_revision
        self.report = {'status': 'not_started', 'source_revision': SOURCE,
                       'target_revision': self.target_revision, 'live_update_performed': False,
                       'run_id': self.run_id,
                       'checks': {'backup': {'valid': False, 'toc_checked': False}}}
        self.step = 'prepare'

    def record_restore_command(self, operation, *, result=None, category=None):
        if operation is None:
            return
        if operation not in {'owner', 'toc', 'data', 'marker', 'role_check'}:
            raise RehearsalError('invalid_restore_operation')
        summary = {'status': 'failed'}
        if result is not None:
            summary['returncode'] = result.returncode
            if result.returncode == 0:
                summary['status'] = 'passed'
            else:
                summary.update(command_error_category(result.stderr))
        else:
            summary['category'] = category
        self.report['checks'].setdefault('restore', {})[operation] = summary
        self.persist()

    def command(self, args, *, data=None, output=None, extra_env=None, timeout=600,
                restore_operation=None):
        try:
            result = subprocess.run(args, input=data, stdout=output if output else subprocess.PIPE,
                                    stderr=subprocess.PIPE if restore_operation else subprocess.DEVNULL,
                                    env=process_environment(extra_env), timeout=timeout)
        except subprocess.TimeoutExpired:
            self.record_restore_command(restore_operation, category='timeout')
            raise RehearsalError('command_unavailable') from None
        except OSError:
            self.record_restore_command(restore_operation, category='process_unavailable')
            raise RehearsalError('command_unavailable') from None
        self.record_restore_command(restore_operation, result=result)
        if result.returncode:
            raise RehearsalError('command_failed')
        return (result.stdout or b'').decode('utf-8') if output is None else ''

    def docker(self, *args, **kwargs):
        return self.command(DOCKER + list(args), **kwargs)

    def inspect(self, kind, reference):
        # Raw inspection is held only in memory and is never included in reports.
        return json.loads(self.docker(kind, 'inspect', reference))[0]

    def persist(self):
        if self.directory is None:
            return
        temp = self.directory / 'report.json.tmp'
        try:
            with temp.open('w', encoding='utf-8') as handle:
                json.dump(self.report, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            temp.chmod(0o600)
            temp.replace(self.directory / 'report.json')
        except OSError:
            raise RehearsalError('report_write_failed') from None

    def sql(self, statement, *, source=False, readonly=True, restore_operation=None):
        container = self.source_id if source else self.clone_id
        if not container or (not source and container == self.source_id):
            raise RehearsalError('invalid_database_target')
        if source and not readonly:
            raise RehearsalError('source_write_forbidden')
        options = ('-c statement_timeout=' + ('10000' if source else '60000')
                   + ' -c lock_timeout=1000 -c timezone=UTC')
        if readonly:
            options += ' -c default_transaction_read_only=on'
            statement = 'BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n' + statement + '\nROLLBACK;'
        raw = self.docker('exec', '-i', '-e', 'PGOPTIONS=' + options, container,
                          'sh', '-c', 'exec psql -X -qAt -v ON_ERROR_STOP=1 -v VERBOSITY=sqlstate '
                          '-U "$POSTGRES_USER" -d "$POSTGRES_DB"', data=statement.encode(),
                          restore_operation=restore_operation)
        return json.loads(raw) if readonly else None

    def backup(self):
        partial = self.directory / 'database.dump.partial'
        with partial.open('xb') as handle:
            self.docker('exec', self.source_id, 'sh', '-c',
                        'exec timeout --signal=TERM --kill-after=5s 540s '
                        'pg_dump -Fc --lock-wait-timeout=5s '
                        '-U "$POSTGRES_USER" -d "$POSTGRES_DB"', output=handle)
            handle.flush()
            os.fsync(handle.fileno())
        with partial.open('rb') as handle:
            header = handle.read(5)
        if partial.stat().st_size < 1024 or header != b'PGDMP':
            raise RehearsalError('archive_empty_or_invalid')
        # Feed the local archive to the matching PostgreSQL tools, without mounts.
        with partial.open('rb') as handle:
            listing = self.command_stream(DOCKER + ['exec', '-i', self.source_id,
                'pg_restore', '--list'], handle)
        for table in ('sandbox_taskattempt', 'traineediary_traineejourney', 'assessment_examattempt'):
            if not re.search(r'\bTABLE DATA public ' + table + r'\b', listing):
                raise RehearsalError('archive_required_table_missing')
        archive = self.directory / 'database.dump'
        partial.rename(archive)
        with archive.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        (self.directory / 'database.dump.sha256').write_text(digest + '\n')
        self.report['checks']['backup'] = {'valid': True, 'bytes': archive.stat().st_size,
                                           'sha256': digest, 'toc_checked': True}
        self.persist()
        return archive

    def reuse_backup(self):
        """Authenticate an existing snapshot locally; never contact its source DB."""
        report_path = self.args.reuse_backup_report.resolve(strict=True)
        archive = report_path.parent / 'database.dump'
        for path in (report_path.parent, report_path, archive):
            info = path.lstat()
            if (path.is_symlink() or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077
                or (path != report_path.parent and not stat.S_ISREG(info.st_mode))):
                raise RehearsalError('reused_backup_not_private')
        if any((p / '.git').exists() for p in (report_path.parent, *report_path.parents)):
            raise RehearsalError('reused_backup_inside_git')
        original = json.loads(report_path.read_text())
        backup = original.get('checks', {}).get('backup', {})
        resources = original.get('checks', {}).get('resources', {})
        reserve = resources.get('backup_required')
        if (original.get('source_revision') != SOURCE
            or original.get('live_update_performed') is not False
            or backup.get('valid') is not True or backup.get('toc_checked') is not True
            or type(backup.get('bytes')) is not int or backup['bytes'] < 1024
            or backup['bytes'] != archive.stat().st_size
            or not re.fullmatch(r'[0-9a-f]{64}', str(backup.get('sha256', '')))
            or type(reserve) is not int or reserve <= GIB or (reserve - GIB) % 2):
            raise RehearsalError('reused_backup_provenance_invalid')
        with archive.open('rb') as handle:
            if handle.read(5) != b'PGDMP':
                raise RehearsalError('archive_empty_or_invalid')
            handle.seek(0)
            if hashlib.file_digest(handle, 'sha256').hexdigest() != backup['sha256']:
                raise RehearsalError('archive_checksum_changed')
        self.report['checks']['backup'] = {
            key: backup[key] for key in ('valid', 'toc_checked', 'bytes', 'sha256')
        }
        self.report.update(snapshot_reused=True, readiness_scope='historical_snapshot_only',
                           source_database_contacted=False)
        self.persist()
        return archive, (reserve - GIB) // 2

    def command_stream(self, args, handle, *, restore_operation=None):
        try:
            result = subprocess.run(args, stdin=handle, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE if restore_operation else subprocess.DEVNULL,
                                    env=process_environment(), timeout=600)
        except subprocess.TimeoutExpired:
            self.record_restore_command(restore_operation, category='timeout')
            raise RehearsalError('archive_command_unavailable') from None
        except OSError:
            self.record_restore_command(restore_operation, category='process_unavailable')
            raise RehearsalError('archive_command_unavailable') from None
        self.record_restore_command(restore_operation, result=result)
        if result.returncode:
            raise RehearsalError('archive_command_failed')
        return result.stdout.decode('utf-8')

    def prepare_clone_owner(self, *, superuser):
        # initdb's bootstrap role (OID 10) must retain SUPERUSER. Use a
        # separate owner/login for restored objects and application migrations.
        privilege = 'SUPERUSER' if superuser else 'NOSUPERUSER'
        self.sql("CREATE ROLE rehearsal LOGIN " + privilege
                 + " NOCREATEDB NOCREATEROLE PASSWORD '" + self.password + "';\n"
                 + 'ALTER DATABASE tp_rehearsal OWNER TO rehearsal;',
                 readonly=False, restore_operation='owner')

    def verify_clone(self):
        item = self.inspect('container', self.clone_id)
        mounts = item.get('Mounts', [])
        if (item['Id'] == self.source_id or item['Name'].lstrip('/') != self.clone_name
            or item['Config'].get('Labels', {}).get('training-platform.rehearsal') != self.run_id
            or item['HostConfig']['NetworkMode'] != 'none'
            or item['HostConfig'].get('Privileged')
            or item['HostConfig'].get('PortBindings')
            or len(mounts) != 1 or mounts[0].get('Name') != self.volume_name
            or mounts[0].get('Destination') != '/var/lib/postgresql/data'):
            raise RehearsalError('clone_isolation_failed')

    def create_clone(self, postgres_image):
        self.report['resources'] = {'container': self.clone_name, 'volume': self.volume_name,
                                    'volume_verified': False, 'container_verified': False}
        self.persist()
        if (self.docker('container', 'ls', '--all', '--quiet', '--filter', 'name=' + self.clone_name).strip()
            or self.docker('volume', 'ls', '--quiet', '--filter', 'name=' + self.volume_name).strip()):
            raise RehearsalError('resource_name_collision')
        self.docker('volume', 'create', '--label', 'training-platform.rehearsal=' + self.run_id,
                    self.volume_name)
        volume = self.inspect('volume', self.volume_name)
        if (volume.get('Labels', {}).get('training-platform.rehearsal') != self.run_id
            or volume.get('Driver') != 'local' or volume.get('Options')):
            raise RehearsalError('volume_ownership_failed')
        self.report['resources']['volume_verified'] = True
        self.persist()
        self.clone_id = self.docker('run', '-d', '--pull=never', '--name', self.clone_name,
            '--label', 'training-platform.rehearsal=' + self.run_id,
            '--network', 'none', '--memory=768m', '--cpus=1',
            '--mount', 'type=volume,source=' + self.volume_name + ',target=/var/lib/postgresql/data',
            '-e', 'POSTGRES_USER=rehearsal_admin', '-e', 'POSTGRES_DB=tp_rehearsal',
            '-e', 'POSTGRES_PASSWORD', postgres_image,
            extra_env={'POSTGRES_PASSWORD': self.password}).strip()
        if not re.fullmatch(r'[0-9a-f]{64}', self.clone_id) or self.clone_id == self.source_id:
            raise RehearsalError('invalid_clone_id')
        self.verify_clone()
        self.report['resources']['container_verified'] = True
        self.persist()
        deadline = time.monotonic() + 60
        while True:
            try:
                self.docker('exec', self.clone_id, 'pg_isready', '-h', '127.0.0.1',
                            '-U', 'rehearsal', '-d', 'tp_rehearsal', timeout=5)
                break
            except RehearsalError:
                if time.monotonic() >= deadline:
                    raise RehearsalError('clone_not_ready') from None
                time.sleep(1)

    def application(self, phase):
        self.verify_clone()
        settings = {
            'DB_ENGINE': 'django.db.backends.postgresql', 'DB_HOST': '127.0.0.1',
            'DB_PORT': '5432', 'DB_NAME': 'tp_rehearsal', 'DB_USER': 'rehearsal',
            'DB_PASSWORD': self.password, 'SECRET_KEY': 'rehearsal-only',
            'DJANGO_SETTINGS_MODULE': 'config.settings',
            'DEBUG': 'False', 'SENTRY_DSN': '', 'TERMINAL_BROKER_ENABLED': 'false',
            'SANDBOX_HTTP_OBSERVATION_ENABLED': 'false',
            'CELERY_BROKER_URL': 'redis://127.0.0.1:6379/0',
            'REHEARSAL_PHASE': phase, 'REHEARSAL_MARKER': self.run_id,
            'EXPECTED_MIGRATIONS': json.dumps(sorted(EXPECTED_MIGRATIONS)),
            'FRAMEWORK_BOUNDS': json.dumps(self.framework_bounds),
        }
        if phase != 'migrate':
            settings['PGOPTIONS'] = '-c default_transaction_read_only=on -c statement_timeout=60000'
        args = ['run', '--rm', '--pull=never', '--name', self.clone_name + '-' + phase,
                '--label', 'training-platform.rehearsal=' + self.run_id,
                '--network', 'container:' + self.clone_id, '--user', '10001:10001',
                '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
                '--memory=512m', '--cpus=1', '--tmpfs', '/tmp:rw,nosuid,size=64m',
                '--entrypoint', 'python']
        for key in settings:
            args += ['-e', key]
        raw = self.docker(*args, self.args.target_image, '-B', '-c', APP_COMMAND, extra_env=settings)
        result = json.loads(raw)
        # Never persist unvalidated application output or catalog exception text.
        allowed = {'catalog_issues', 'nonlegacy_journeys', 'user_awards', 'award_events',
                   'migration_count', 'invalid_framework_metadata', 'new_content_types', 'new_permissions'}
        if not isinstance(result, dict) or set(result) - allowed or any(type(v) is not int or v < 0 for v in result.values()):
            raise RehearsalError('invalid_application_summary')
        required = {'migration_count'} if phase == 'migrate' else {'catalog_issues'}
        if phase == 'postflight':
            required |= {'nonlegacy_journeys', 'user_awards', 'award_events',
                         'invalid_framework_metadata', 'new_content_types', 'new_permissions'}
        if set(result) != required:
            raise RehearsalError('incomplete_application_summary')
        self.report['checks'][phase] = result
        self.persist()
        if phase == 'migrate':
            if result != {'migration_count': len(EXPECTED_MIGRATIONS)}:
                raise RehearsalError('unexpected_migration_count')
        elif result.get('catalog_issues') != 0 or any(result.get(k, 0) for k in
                ('nonlegacy_journeys', 'user_awards', 'award_events', 'invalid_framework_metadata')):
            raise RehearsalError('catalog_or_history_check_failed')

    def snapshot(self, tables, migrations, *, exclude_new_program=False):
        result = {}
        for table, columns in sorted(tables.items()):
            where = ''
            if table == 'django_migrations':
                where = 'WHERE id IN (' + ','.join(str(int(row[0])) for row in migrations) + ')'
            elif table in self.framework_bounds:
                where = 'WHERE id <= ' + str(self.framework_bounds[table])
            elif table == 'traineediary_traineestage' and exclude_new_program:
                where = "WHERE slug <> 'training-program'"
            result[table] = self.sql(fingerprint_sql(table, columns, where))
            value = result[table]
            if (type(value.get('rows')) is not int or value['rows'] < 0
                or not re.fullmatch(r'[0-9a-f]{64}', value.get('digest', ''))):
                raise RehearsalError('invalid_fingerprint')
        return result

    def prepare_directory(self):
        root = self.args.backup_root.resolve(strict=True)
        if (not root.is_dir() or root.stat().st_uid != os.geteuid()
            or stat.S_IMODE(root.stat().st_mode) & 0o077
            or any((parent / '.git').exists() for parent in (root, *root.parents))):
            raise RehearsalError('backup_root_not_private_or_inside_git')
        self.directory = Path(tempfile.mkdtemp(prefix='db-rehearsal-', dir=root))
        self.persist()
        return root

    def run(self):
        os.umask(0o077)
        try:
            root = self.prepare_directory()
            self.step = 'source_and_target'
            image = self.inspect('image', self.args.target_image)
            if image['Config'].get('Labels', {}).get('org.opencontainers.image.revision') != self.target_revision:
                raise RehearsalError('target_image_revision_not_verified')
            reused = getattr(self.args, 'reuse_backup_report', None) is not None
            if reused:
                self.step = 'archive_provenance'
                archive, db_bytes = self.reuse_backup()
                postgres_image = self.args.postgres_image
                postgres = self.inspect('image', postgres_image)
                if 'PG_MAJOR=16' not in postgres['Config'].get('Env', []):
                    raise RehearsalError('reused_backup_postgres_version_not_supported')
                # A stricter owner-only role avoids assuming the old source's privileges.
                meta = {'bytes': db_bytes, 'superuser': False}
            else:
                revision = self.command(['git', '-c', 'safe.directory=' + str(self.args.app_dir),
                    '-C', str(self.args.app_dir), 'rev-parse', '--verify', 'HEAD']).strip()
                if revision != SOURCE:
                    raise RehearsalError('unexpected_source_revision')
                source = self.inspect('container', SOURCE_CONTAINER)
                self.source_id = source['Id']
                if (source['Config'].get('Labels', {}).get('com.docker.compose.project') != 'training-platform'
                    or source['Config']['Labels'].get('com.docker.compose.service') != 'db'
                    or not source['State']['Running'] or source['State'].get('Health', {}).get('Status') != 'healthy'):
                    raise RehearsalError('source_database_not_healthy_platform_service')
                web = self.inspect('container', 'training-platform-web')
                web_env = dict(item.split('=', 1) for item in web['Config'].get('Env', []) if '=' in item)
                db_env = dict(item.split('=', 1) for item in source['Config'].get('Env', []) if '=' in item)
                if (web['Config'].get('Labels', {}).get('com.docker.compose.project') != 'training-platform'
                    or web['Config']['Labels'].get('com.docker.compose.service') != 'web'
                    or web_env.get('DB_HOST') != 'db' or web_env.get('DB_PORT') != '5432'
                    or not db_env.get('POSTGRES_DB') or not db_env.get('POSTGRES_USER')
                    or web_env.get('DB_NAME') != db_env['POSTGRES_DB']
                    or web_env.get('DB_USER') != db_env['POSTGRES_USER']
                    or not (set(web.get('NetworkSettings', {}).get('Networks', {}))
                            & set(source.get('NetworkSettings', {}).get('Networks', {})))):
                    raise RehearsalError('source_application_database_mapping_unverified')
                meta = self.sql(SOURCE_METADATA, source=True)
                if (type(meta.get('bytes')) is not int or meta['bytes'] <= 0
                    or meta['version'] // 10000 != 16 or not meta['can_create']
                    or not (meta['superuser'] or meta['owns_tables'])):
                    raise RehearsalError('source_version_or_role_not_supported')
                postgres_image = source['Image']
            self.step = 'resources'
            docker_root = Path(json.loads(self.docker('info', '--format', '{{json .DockerRootDir}}')))
            ok, stats = check_resources(root, docker_root, meta['bytes'])
            self.report['checks']['resources'] = stats
            self.persist()
            if not ok:
                raise RehearsalError('insufficient_memory_or_disk')
            if not reused:
                self.step = 'backup'
                archive = self.backup()
            self.step = 'clone'
            ok, _ = check_resources(root, docker_root, meta['bytes'])
            if not ok:
                raise RehearsalError('resources_changed_after_backup')
            self.create_clone(postgres_image)
            self.step = 'restore_owner'
            self.prepare_clone_owner(superuser=meta['superuser'])
            self.step = 'restore'
            with archive.open('rb') as handle:
                if hashlib.file_digest(handle, 'sha256').hexdigest() != self.report['checks']['backup']['sha256']:
                    raise RehearsalError('archive_checksum_changed')
                handle.seek(0)
                if reused:
                    listing = self.command_stream(DOCKER + ['exec', '-i', self.clone_id,
                        'pg_restore', '--list'], handle, restore_operation='toc')
                    for table in ('sandbox_taskattempt', 'traineediary_traineejourney', 'assessment_examattempt'):
                        if not re.search(r'\bTABLE DATA public ' + table + r'\b', listing):
                            raise RehearsalError('archive_required_table_missing')
                    handle.seek(0)
                self.command_stream(DOCKER + ['exec', '-i', self.clone_id, 'pg_restore',
                    '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges',
                    '-U', 'rehearsal', '-d', 'tp_rehearsal'], handle, restore_operation='data')
            self.step = 'restore_marker'
            self.sql("COMMENT ON DATABASE tp_rehearsal IS '" + self.run_id + "';",
                     readonly=False, restore_operation='marker')
            self.step = 'restore_role_check'
            owner = self.sql(CLONE_OWNER, restore_operation='role_check')
            if owner != {'bootstrap': False, 'superuser': meta['superuser'],
                         'createdb': False, 'createrole': False, 'owns_database': True}:
                raise RehearsalError('clone_owner_privileges_invalid')
            self.step = 'baseline'
            tables = self.sql(TABLES)
            if not REQUIRED_TABLES <= tables.keys():
                raise RehearsalError('restored_schema_missing_required_tables')
            migrations = self.sql(MIGRATIONS)
            catalog = self.sql(CATALOG)
            sequences = self.sql(SEQUENCES)
            self.framework_bounds = self.sql(FRAMEWORK_BOUNDS)
            if (set(self.framework_bounds) != {'django_content_type', 'auth_permission'}
                or any(type(v) is not int or v < 0 for v in self.framework_bounds.values())):
                raise RehearsalError('invalid_framework_metadata_bounds')
            progress = self.sql(PROGRESS)
            self.report['checks']['progress'] = progress
            self.persist()
            if progress['lost_credit_pairs'] or progress['closed_without_evidence']:
                raise RehearsalError('historical_technical_credit_loss')
            before = self.snapshot(tables, migrations)
            self.report['checks']['baseline'] = before
            self.persist()
            self.step = 'preflight'
            self.application('preflight')
            self.step = 'migrations_on_copy'
            self.application('migrate')
            self.step = 'postflight'
            self.application('postflight')
            after = self.snapshot(tables, migrations, exclude_new_program=not catalog['program_exists'])
            self.report['checks']['after'] = after
            comparison = compare_snapshots(before, after)
            self.report['checks']['historical_data'] = comparison
            sequence_check = compare_sequences(sequences, self.sql(SEQUENCES))
            self.report['checks']['sequences'] = sequence_check
            if sequence_check['sequences_regressed']:
                raise RehearsalError('historical_sequences_regressed')
            current_catalog = self.sql(CATALOG)
            if (comparison['tables_changed'] or current_catalog['stage_count'] !=
                catalog['stage_count'] + int(not catalog['program_exists'])):
                raise RehearsalError('historical_data_changed')
            if self.sql(PROGRESS) != progress:
                raise RehearsalError('progress_changed_during_migrations')
            new_keys = {(row[1], row[2]) for row in self.sql(MIGRATIONS)}
            old_keys = {(row[1], row[2]) for row in migrations}
            if new_keys - old_keys != EXPECTED_MIGRATIONS or not old_keys <= new_keys:
                raise RehearsalError('unexpected_applied_migrations')
            self.report.update(status='passed', ready_for_review=True)
        except (Exception, KeyboardInterrupt) as error:
            code = str(error) if isinstance(error, RehearsalError) else 'diagnostics_failed'
            self.report.update(status='failed', ready_for_review=False, failed_step=self.step, error=code)
        finally:
            try:
                self.persist()
            except RehearsalError:
                self.report.update(status='failed', ready_for_review=False, error='report_write_failed')
        return self.report['status'] == 'passed'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-image', required=True, help='Local immutable sha256 image ID, labelled with target revision')
    parser.add_argument('--target-revision', required=True, help='Full commit SHA of the target image source')
    parser.add_argument('--backup-root', type=Path, required=True, help='Existing owner-only directory outside Git; use encrypted storage')
    parser.add_argument('--reuse-backup-report', type=Path, help='Reuse database.dump beside this private prior report; never contact the source DB')
    parser.add_argument('--postgres-image', help='Local immutable PostgreSQL 16 image ID; required for backup reuse')
    parser.add_argument('--app-dir', type=Path, default=Path('/opt/training-platform-compose/app'))
    parser.add_argument('--execute', action='store_true', help='Actually create backup and isolated rehearsal resources')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.target_image):
        parser.error('--target-image must be an immutable local sha256 image ID')
    if not re.fullmatch(r'[0-9a-f]{40}', args.target_revision):
        parser.error('--target-revision must be a full commit SHA')
    if args.reuse_backup_report:
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', args.postgres_image or ''):
            parser.error('--reuse-backup-report requires an immutable --postgres-image')
    elif args.postgres_image:
        parser.error('--postgres-image requires --reuse-backup-report')
    if not args.execute:
        print(json.dumps({'mode': 'plan_only', 'source_revision': SOURCE, 'target_revision': args.target_revision,
                          'snapshot_reused': bool(args.reuse_backup_report),
                          'live_update_performed': False, 'requires_execute': True}))
        return 0
    if sys.platform != 'linux':
        parser.error('Execution is supported only on the local Linux Docker host')
    run = Rehearsal(args)
    passed = run.run()
    print(json.dumps({'status': run.report['status'], 'ready_for_review': passed,
                      'report_directory': str(run.directory) if run.directory else None,
                      'failed_step': run.report.get('failed_step'), 'error': run.report.get('error'),
                      'live_update_performed': False}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
