"""Fixed dormant host operations. No shell, env discovery or arbitrary commands."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time
import re
from trusted_checker_runtime.profiles import require,Denied
from .contracts import PROFILE
from .authorization import Activation


class LinuxIO:
    def __init__(self,activation):
        require(type(activation) is Activation and not activation.offline,'physical_io_requires_live_origin')
        self.activation=activation

    def read(self,path,budget):
        self.activation.check('read');budget.remaining()
        b=self.activation.approval.binding
        paths={'/proc/modules','/proc/self/status','/proc/sys/kernel/random/boot_id','/etc/machine-id',
               '/proc/sys/net/core/rmem_max','/proc/sys/net/core/rmem_default',
               *('/proc/sys/net/bridge/bridge-nf-call-'+k for k in ('iptables','ip6tables','arptables')),
               *('/proc/'+str(n.pid)+'/stat' for n in (b.target,b.runner))}
        require(type(path) is str and (path in paths or re.fullmatch(r'/boot/config-6\.(?:8|12)\.\d+[-+.a-zA-Z0-9]*',path))
                and '..' not in Path(path).parts,'physical_read_path_invalid')
        with open(path,'rb') as file:raw=file.read(PROFILE.max_output+1)
        require(len(raw)<=PROFILE.max_output,'physical_read_limit');budget.remaining();return raw.decode('ascii')

    def inode(self,path,budget):
        self.activation.check('read');budget.remaining()
        b=self.activation.approval.binding
        require(path in {'/proc/self/ns/net',*('/proc/'+str(n.pid)+'/ns/net' for n in (b.target,b.runner))},
                'physical_namespace_path_invalid')
        value=os.stat(path).st_ino;budget.remaining();return value

    def run(self,operation,budget,*,payload=None,interface=None,namespace=None,recovery=False):
        self.activation.check('mutate' if operation=='nft_apply' else 'read',recovery=recovery)
        commands={'kernel':['/usr/bin/uname','-r'], 'nft_version':['/usr/sbin/nft','--version'],
                  'nft_read':['/usr/sbin/nft','-j','-a','list','ruleset'],
                  'links':['/usr/sbin/ip','-j','-d','link','show'],
                  'addresses':['/usr/sbin/ip','-j','address','show'],
                  'nft_apply':['/usr/sbin/nft','-j','-f','-']}
        if operation in ('offload','tc_ingress','tc_egress'):
            require(type(interface) is str and interface in ('tcsh0',self.activation.approval.binding.target.interface,
                    self.activation.approval.binding.runner.interface),'physical_interface_not_approved')
            argv=['/usr/sbin/ethtool','-k',interface] if operation=='offload' else [
                '/usr/sbin/tc','-j','filter','show','dev',interface,'ingress' if operation=='tc_ingress' else 'egress']
        else:
            require(operation in commands,'physical_command_not_allowed');argv=commands[operation]
        if namespace is not None:
            require(operation in ('links','addresses') and type(namespace) is int and
                    namespace in (self.activation.approval.binding.target.pid,self.activation.approval.binding.runner.pid),
                    'physical_namespace_not_approved')
            argv=['/usr/bin/nsenter','--net=/proc/'+str(namespace)+'/ns/net',*argv]
        require((payload is None) == (operation!='nft_apply'),'physical_input_not_allowed')
        if payload is not None:
            payload=self.activation.consume_batch(payload,budget)
            require(type(payload) is bytes and len(payload)<=PROFILE.max_output,'physical_input_limit')
        # Popen/selector bounds *both* streams while running; communicate() alone
        # would buffer arbitrary stderr/stdout before checking its length.
        started=budget.monotonic();limit=budget.remaining(PROFILE.operation_seconds)
        end=started+limit
        def left():
            remaining=min(budget.remaining(),end-budget.monotonic())
            require(remaining>0,'physical_command_timeout');return remaining
        proc=subprocess.Popen(argv,stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd='/',env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'},
            close_fds=True,start_new_session=True)
        output,errors=bytearray(),bytearray();pending=memoryview(payload or b'')
        recorded=False
        try:
            with selectors.DefaultSelector() as selector:
                for stream,target in ((proc.stdout,output),(proc.stderr,errors)):
                    os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,target)
                if payload is not None:
                    os.set_blocking(proc.stdin.fileno(),False);selector.register(proc.stdin,selectors.EVENT_WRITE,None)
                while selector.get_map():
                    require(budget.monotonic()-started<limit,'physical_command_timeout')
                    for key,_ in selector.select(min(0.05,left())):
                        if key.data is None:
                            count=os.write(key.fd,pending[:8192]) if pending else 0;pending=pending[count:]
                            if not pending:selector.unregister(key.fileobj);key.fileobj.close()
                        else:
                            chunk=os.read(key.fd,8192)
                            if not chunk:selector.unregister(key.fileobj)
                            else:key.data.extend(chunk)
                            require(len(output)+len(errors)<=PROFILE.max_output,'physical_command_output_limit')
            code=proc.wait(timeout=left())
            require(code==0,'physical_command_failed')
            budget.record(operation,started);recorded=True;return bytes(output)
        except Exception:
            raise Denied('physical_command_unknown') from None
        finally:
            if not recorded:budget.observe(operation,started)
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=1)
            for stream in (proc.stdin,proc.stdout,proc.stderr):
                if stream is not None:stream.close()


def json_output(raw):
    require(type(raw) is bytes and len(raw)<=PROFILE.max_output,'physical_json_limit')
    def pairs(items):
        require(len(items)==len(dict(items)),'physical_duplicate_json_key');return dict(items)
    try:return json.loads(raw,object_pairs_hook=pairs)
    except (ValueError,TypeError):raise Denied('physical_json_invalid') from None
