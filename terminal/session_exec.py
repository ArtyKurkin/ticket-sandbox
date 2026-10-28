"""Lite session bootstrap and exact-process cleanup (task-root is not trusted containment)."""

BOOTSTRAP = r'''
import json,os,select,termios,tty
saved=termios.tcgetattr(0)
tty.setraw(0)
try:
    start=int(open('/proc/self/stat').read().rsplit(')',1)[1].split()[19])
    os.write(1,b'TB2 '+json.dumps({'pid':os.getpid(),'start':start}).encode()+b'\n')
    # The broker must fsync our exact identity before allowing user code.
    if not select.select([0],[],[],5)[0] or os.read(0,1)!=b'G':
        raise SystemExit(1)
finally:
    termios.tcsetattr(0,termios.TCSANOW,saved)
os.execv('/bin/bash',['bash','-i'])
'''

CLEANUP = r'''
import os,select,signal,sys,time
pid,start=map(int,sys.argv[1:])
assert pid>1 and start>0
try:
    fd=os.pidfd_open(pid)
except ProcessLookupError:
    sys.exit(0)
try:
    try:
        actual=int(open('/proc/%s/stat'%pid).read().rsplit(')',1)[1].split()[19])
    except FileNotFoundError:
        sys.exit(0)
    if actual!=start:
        sys.exit(0)  # The recorded process exited; NEVER signal its replacement.
    for sig in (signal.SIGHUP,signal.SIGKILL):
        if select.select([fd],[],[],0)[0]: sys.exit(0)
        try: signal.pidfd_send_signal(fd,sig)
        except ProcessLookupError: sys.exit(0)
        if select.select([fd],[],[],.5)[0]: sys.exit(0)
    sys.exit(1)
finally:
    os.close(fd)
'''
