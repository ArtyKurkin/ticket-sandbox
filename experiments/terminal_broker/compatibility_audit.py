"""Build/probe every task Dockerfile in an isolated image namespace. No image pruning."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

import docker

PROBE = r'''
import json,os,signal,shutil,sys
fd=os.pidfd_open(os.getpid())
signal.pidfd_send_signal(fd,0)
os.close(fd)
assert shutil.which('bash')
assert os.path.isdir('/proc/self/fd')
assert open('/proc/1/stat').read()
assert open('/proc/self/environ','rb').read() is not None
print(json.dumps({'python':sys.version.split()[0], 'pidfd':True, 'bash':True, 'proc':True, 'kernel':os.uname().release}))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--prefix', default='tc-tb2-20261028-audit')
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--require-compatible', action='store_true')
    args = parser.parse_args()
    if not args.prefix.startswith('tc-tb2-') or not args.prefix.replace('-', '').isalnum():
        parser.error('Dedicated tc-tb2- prefix required')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(Path('training_tasks').glob('*/*/Dockerfile'))

    def audit(path):
        client = docker.from_env(timeout=600)
        queue, task = path.parts[1:3]
        key = queue + '-' + task
        record = {'queue': queue, 'task': task, 'dockerfile': str(path),
                  'dockerfile_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'python_explicit': 'python3' in path.read_text(), 'compatible': False}
        container = None
        try:
            tag = f'{args.prefix}-{key}:audit'
            image, events = client.images.build(path=str(path.parent), tag=tag, rm=True)
            with (output / (key + '.build.log')).open('w') as log:
                for event in events:
                    log.write(event.get('stream', json.dumps(event)))
            record['image_id'] = image.id
            container = client.containers.run(image.id, ['sleep', 'infinity'],
                name=f'{args.prefix}-{key}', detach=True, init=True, mem_limit='128m', pids_limit=64,
                labels={'terminal-broker.audit': args.prefix}, security_opt=['no-new-privileges:true'],
                cap_drop=['AUDIT_WRITE', 'MKNOD'])
            code, data = container.exec_run(['bash', '-c', 'test -r /proc/self/stat && command -v bash'])
            record['bash_proc'] = code == 0
            code, data = container.exec_run(['python3', '-I', '-c', PROBE])
            record['probe_exit'] = code
            if code == 0:
                record['runtime'] = json.loads(data)
                record['compatible'] = record['bash_proc']
            else:
                record['reason'] = data.decode(errors='replace')[:1000]
        except (docker.errors.DockerException, ValueError) as exc:
            record['reason'] = str(exc)[:1000]
            record['build_or_probe_failed'] = True
        finally:
            if container is not None:
                container.reload()
                if container.labels.get('terminal-broker.audit') != args.prefix:
                    raise RuntimeError('Foreign audit container; refusing removal')
                container.remove(force=True)
            client.close()
        (output / (key + '.json')).write_text(json.dumps(record, indent=2) + '\n')
        print(key + ': ' + ('PASS' if record['compatible'] else 'INCOMPATIBLE'), flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        records = list(pool.map(audit, files))
    (output / 'compatibility.json').write_text(json.dumps(records, indent=2) + '\n')
    print(f"Audited {len(records)} Dockerfiles; compatible={sum(r['compatible'] for r in records)}", flush=True)
    if args.require_compatible and (not records or not all(r['compatible'] for r in records)):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
