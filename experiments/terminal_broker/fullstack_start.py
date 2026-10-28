"""Opt-in real PostgreSQL/Redis/Celery test stack. Retains all state; no pruning."""
import argparse
import json
from pathlib import Path
import secrets
import time

import docker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host-source', required=True)
    parser.add_argument('--host-state', required=True)
    parser.add_argument('--prefix', default='tc-tb2-20261028-pg')
    parser.add_argument('--app-image', default='tc-e2e-django:lab')
    parser.add_argument('--broker-image', default='ticket-sandbox-terminal-broker:review')
    parser.add_argument('--ttyd-image', default='ticket-sandbox-ttyd:broker-review')
    args = parser.parse_args()
    if not args.prefix.startswith('tc-tb2-') or not args.prefix.replace('-', '').isalnum():
        parser.error('Dedicated lab prefix required')
    client = docker.from_env(timeout=600)
    root = Path('/lab')
    if (root / 'stack.json').exists():
        raise RuntimeError('Refusing to reuse an existing fixture DB/state')
    network = args.prefix + '-network'
    labels = {'terminal-broker.fullstack': args.prefix}
    client.networks.create(network, labels=labels)
    password = secrets.token_hex(24)
    secret = secrets.token_hex(32)
    db = client.containers.run('postgres:16', name=args.prefix + '-postgres', detach=True,
        network=network, labels=labels, mem_limit='256m',
        environment={'POSTGRES_USER': 'tb2', 'POSTGRES_PASSWORD': password, 'POSTGRES_DB': 'tb2'},
        volumes={args.prefix + '-pgdata': {'bind': '/var/lib/postgresql/data', 'mode': 'rw'}})
    client.containers.run('redis:7-alpine', name=args.prefix + '-redis', detach=True,
        command=['redis-server', '--appendonly', 'yes'], network=network, labels=labels,
        mem_limit='64m', volumes={args.prefix + '-redisdata': {'bind': '/data', 'mode': 'rw'}})
    for _ in range(120):
        # The image first starts a temporary Unix-only server during initdb.
        # Wait for final TCP service, otherwise CREATE DATABASE races shutdown.
        code, _ = db.exec_run(['pg_isready', '-h', '127.0.0.1', '-U', 'tb2'])
        if code == 0:
            break
        time.sleep(.5)
    else:
        raise RuntimeError('PostgreSQL not ready')
    modes = []
    for index, mode in enumerate(('host_port', 'docker_network')):
        database = 'tb2_' + mode
        code, _ = db.exec_run(['psql', '-U', 'tb2', '-d', 'postgres', '-c', f'CREATE DATABASE {database}'])
        if code:
            raise RuntimeError('Failed to create private fixture DB')
        name = args.prefix + '-' + mode
        web_host = args.prefix + '-' + mode.replace('_', '-') + '-web'
        web_port, gateway_port = ((29190, 29192) if mode == 'host_port' else (29191, 29193))
        env = {'DJANGO_SETTINGS_MODULE': 'experiments.terminal_broker.fullstack_settings',
            'TB2_MODE': mode, 'TB2_PREFIX': args.prefix, 'TB2_WEB_HOST': web_host, 'TB2_CONTROL_TOKEN': secrets.token_hex(32),
            'DEBUG': 'True', 'SECRET_KEY': secret, 'DB_ENGINE': 'django.db.backends.postgresql',
            'DB_NAME': database, 'DB_USER': 'tb2', 'DB_PASSWORD': password, 'DB_HOST': db.name, 'DB_PORT': '5432',
            'CELERY_BROKER_URL': f'redis://{args.prefix}-redis:6379/{index}',
            'ALLOWED_HOSTS': 'localhost,127.0.0.1,' + web_host,
            'TERMINAL_GATEWAY_ENABLED': 'true', 'TERMINAL_BROKER_ENABLED': 'true',
            'TERMINAL_DOCKER_NETWORK': network,
            'TERMINAL_BROKER_IMAGE': args.broker_image,
            'TERMINAL_BROKER_TTYD_IMAGE': args.ttyd_image,
            'TERMINAL_BROKER_AUTHORIZATION_URL': f'http://{web_host}:8000/terminal-broker-auth/'}
        volumes = {args.host_source: {'bind': '/app', 'mode': 'ro'}, args.host_state: {'bind': '/lab', 'mode': 'rw'}}
        bootstrap = client.containers.run(args.app_image, ['python', '-m', 'experiments.terminal_broker.fullstack_setup'],
            name=name + '-bootstrap', detach=True, user='0', network=network, labels=labels,
            environment=env, volumes=volumes, working_dir='/app')
        code = bootstrap.wait(timeout=120)['StatusCode']
        if code:
            raise RuntimeError('Bootstrap failed: ' + bootstrap.logs().decode()[-4000:])
        client.containers.run(args.app_image, ['gunicorn', 'config.wsgi:application', '--bind', '0.0.0.0:8000',
            '--workers', '2', '--threads', '2', '--access-logfile', '/dev/null'],
            name=web_host, detach=True, user='0', network=network, labels=labels,
            ports={'8000/tcp': ('127.0.0.1', web_port)}, environment=env, volumes=volumes, working_dir='/app',
            mem_limit='256m', pids_limit=128, cap_drop=['ALL'], security_opt=['no-new-privileges:true'])
        worker_volumes = {**volumes, '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'}}
        # host_port is the supported host-local topology; docker_network uses DNS.
        worker_env = dict(env)
        if mode == 'host_port':
            db.reload()
            worker_env['DB_HOST'] = db.attrs['NetworkSettings']['Networks'][network]['IPAddress']
            redis = client.containers.get(args.prefix + '-redis')
            worker_env['CELERY_BROKER_URL'] = f"redis://{redis.attrs['NetworkSettings']['Networks'][network]['IPAddress']}:6379/{index}"
        client.containers.run(args.app_image,
            ['celery', '-A', 'config', 'worker', '--loglevel=INFO', '--concurrency=2', '-Q', name, '--hostname', name],
            name=name + '-worker', detach=True, user='0', network_mode='host' if mode == 'host_port' else network,
            labels=labels, environment=worker_env, volumes=worker_volumes, working_dir='/app', mem_limit='384m')
        client.containers.run(args.app_image,
            ['celery', '-A', 'config', 'beat', '--loglevel=INFO', '--schedule=/tmp/terminal-beat'],
            name=name + '-scheduler', detach=True, user='0', network=network, labels=labels,
            environment=env, volumes=volumes, working_dir='/app', mem_limit='128m')
        # Exercise the existing nginx files, changing only lab addresses/ports.
        if mode == 'host_port':
            config = Path('deploy/nginx/ticket-sandbox-local.conf').read_text()
            config = config.replace('listen 8081;', 'listen 29192;').replace('127.0.0.1:8000', '127.0.0.1:29190')
            for suffix in ('error.log', 'access.log', 'pid'):
                config = config.replace('logs/nginx-' + suffix, '/tmp/nginx-' + suffix)
            config = config.replace('logs/nginx.pid', '/tmp/nginx.pid')
            dest = '/etc/nginx/nginx.conf'
        else:
            config = Path('deploy/nginx/docker/default.conf').read_text().replace('http://web:8000', f'http://{web_host}:8000')
            dest = '/etc/nginx/conf.d/default.conf'
        (root / (mode + '.conf')).write_text(config)
        kwargs = {'network_mode': 'host'} if mode == 'host_port' else {
            'network': network, 'ports': {'80/tcp': ('127.0.0.1', gateway_port)}}
        client.containers.run('nginx:1.28-alpine', name=name + '-gateway', detach=True, labels=labels,
            volumes={args.host_state + '/' + mode + '.conf': {'bind': dest, 'mode': 'ro'}}, **kwargs)
        data = json.loads((root / (mode + '.json')).read_text())
        data.update({'webOrigin': f'http://127.0.0.1:{web_port}', 'gatewayOrigin': f'http://127.0.0.1:{gateway_port}'})
        (root / (mode + '.json')).write_text(json.dumps(data))
        (root / (mode + '.json')).chmod(0o600)
        modes.append(data)
    (root / 'stack.json').write_text(json.dumps(modes))
    (root / 'stack.json').chmod(0o600)
    print('Real PostgreSQL/Redis/Celery fixture ready', flush=True)


if __name__ == '__main__':
    main()
