"""Trusted launch preflight. Execute SOURCE inside a task without writing files."""
SOURCE = r'''
import os, signal, shutil, subprocess, sys
assert sys.version_info >= (3,9), 'Python 3.9+ required'
assert shutil.which('bash'), 'Bash required'
assert os.path.isdir('/proc/self/fd'), '/proc required'
assert open('/proc/1/stat').read(), '/proc/1 required'
assert int(open('/proc/self/stat').read().rsplit(')',1)[1].split()[19]) > 0
fd=os.pidfd_open(os.getpid())
try: signal.pidfd_send_signal(fd,0)
finally: os.close(fd)
subprocess.run(['bash','--noprofile','--norc','-c','test -n "$BASH_VERSION"'],check=True)
'''
