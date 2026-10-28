"""Active lab checks; results never contain passwords, signing keys or tokens."""
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

import docker
from django.conf import settings
from sandbox.models import TaskAttempt
from sandbox.services.terminal_broker import authorization_header, credential, lease_credential
from experiments.terminal_broker.e2e_probe import PROBE


def inspect_boundaries(attempt_id, escaped_pid=None):
    assert settings.TB2_FULLSTACK_TEST
    client = docker.from_env(timeout=10)
    attempt = TaskAttempt.objects.select_related('task', 'task__queue').get(pk=attempt_id)
    other = TaskAttempt.objects.exclude(pk=attempt_id).get()
    terminal = client.containers.get(attempt.terminal_container_name)
    broker = client.containers.get(terminal.name + '-broker')
    target = client.containers.get(attempt.container_id)
    assert target.id == attempt.container_id and target.labels['ticket-sandbox.generation'] == str(attempt.environment_generation)
    assert all(m['Destination'] != '/var/run/docker.sock' for m in terminal.attrs['Mounts'])
    assert all(m['Destination'] != '/var/lib/terminal' for m in terminal.attrs['Mounts'])
    assert all(m['RW'] is False for m in terminal.attrs['Mounts'])
    assert terminal.attrs['HostConfig']['ReadonlyRootfs']
    code, _ = terminal.exec_run(['python3', '-I', '-c', PROBE])
    assert code == 0, 'Actual ttyd isolation protocol probe failed'
    if settings.TB2_MODE == 'host_port':
        direct = f'http://127.0.0.1:{attempt.terminal_port}' + attempt.terminal_url
        web = 'http://127.0.0.1:29190'
    else:
        direct = f'http://{terminal.name}:7681' + attempt.terminal_url
        web = f'http://{settings.TB2_WEB_HOST}:8000'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def status(url, authorization=None, data=None):
        headers = {'Content-Type': 'application/json'}
        if authorization:
            headers['Authorization'] = authorization
        request = urllib.request.Request(url, headers=headers, data=json.dumps(data).encode() if data is not None else None)
        try:
            with opener.open(request, timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code

    assert status(direct) == 401
    assert status(direct, 'Basic d3Jvbmc6d3Jvbmc=') == 401
    assert status(direct, authorization_header(other.pk, other.environment_generation)) == 401
    assert status(direct, authorization_header(attempt.pk, attempt.environment_generation)) == 200
    identity = {'container_id': attempt.container_id, 'attempt': attempt.pk,
        'queue': attempt.task.queue.slug, 'task': attempt.task.slug, 'generation': str(attempt.environment_generation)}
    lease_url = web + '/terminal-broker-auth/'
    bearer = 'Bearer ' + lease_credential(attempt.pk, attempt.environment_generation)
    assert status(lease_url, bearer, identity) == 204
    assert status(lease_url, 'Bearer ' + credential(attempt.pk, attempt.environment_generation), identity) == 403
    for key in identity:
        changed = dict(identity)
        changed[key] = other.pk if key == 'attempt' else 'foreign'
        assert status(lease_url, bearer, changed) == 403
    assert not any(m['Destination'] == '/var/run/docker.sock' for m in client.containers.get(settings.TB2_WEB_HOST).attrs['Mounts'])
    result = {'mode': settings.TB2_MODE, 'authorizationChecksPassed': True,
        'directWithoutBasic': 401, 'wrongOrOtherAttemptBasic': 401, 'correctBasic': 200,
        'basicAsLease': 403, 'validLease': 204, 'changedIdentityLease': 403,
        'dockerSocketAndCLIAbsentInTtyd': True, 'journalNotMountedInTtyd': True,
        'socketMountReadOnly': True, 'webHasNoDockerSocket': True,
        'brokerHasUnrestrictedDockerSocket': True, 'brokerIsHostRootTrustBoundary': True,
        'rootEscapeReproduced': False}
    if escaped_pid is not None:
        assert type(escaped_pid) is int and 1 < escaped_pid < 2**31
        time.sleep(1)
        code, data = target.exec_run(['python3', '-I', '-c',
            'import os,sys; p=int(sys.argv[1]); os.kill(p,0); '
            'assert open("/proc/%s/comm"%p).read().strip()=="sleep"; '
            'assert not any(x.startswith(b"TB_SESSION_TOKEN=") for x in open("/proc/%s/environ"%p,"rb").read().split(b"\\0"))',
            str(escaped_pid)])
        result['rootEscapeReproduced'] = code == 0
        result['rootEscapeStatus'] = 'HIGH: token-cleared child survives browser close' if code == 0 else 'not-reproduced'
    (Path('/lab') / ('security-' + settings.TB2_MODE + '.json')).write_text(json.dumps(result, indent=2))
    return result
