from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import importlib
import ast
import os
import socket
import subprocess
import array
import struct
from trusted_checker_runtime.profiles import Denied
from trusted_checker_physical.authorization import Activation
from trusted_checker_physical.io import LinuxIO,json_output
from trusted_checker_physical.packet_io import NamespaceSocketBroker,KernelTraceSocket
from trusted_checker_physical import namespace_helper
from trusted_checker_physical.activation_path import ReviewedActivationPath
from .support import Lab


class FakeSelector:
    def __init__(self):self.items={}
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def register(self,file,events,data):self.items[file]=SimpleNamespace(fileobj=file,fd=file.fileno(),data=data)
    def unregister(self,file):del self.items[file]
    def get_map(self):return self.items
    def select(self,timeout):return [(key,1) for key in list(self.items.values())]


class DormantIOTests(unittest.TestCase):
    def setUp(self):self.l=Lab();self.addCleanup(self.l.close)
    def real_context(self):
        l=self.l;a=Activation(l.auth,enabled=True,clock=l.clock,monotonic=l.clock);a.approval=l.approval
        return a,LinuxIO(a)
    def test_bounded_fixed_subprocess_only_under_mocks(self):
        l=self.l;a,io=self.real_context();proc=Mock();proc.stdout.fileno.return_value=10;proc.stderr.fileno.return_value=11
        proc.stdin=None;proc.poll.return_value=0;proc.wait.return_value=0
        reads={10:[b'nftables v1.0.9',b''],11:[b'']}
        with patch('platform.system',return_value='Linux'),patch('subprocess.Popen',return_value=proc) as spawn,\
             patch('selectors.DefaultSelector',FakeSelector),patch('os.set_blocking'),patch('os.read',side_effect=lambda fd,n:reads[fd].pop(0)):
            self.assertEqual(io.run('nft_version',l.budget()),b'nftables v1.0.9')
        argv=spawn.call_args.args[0];self.assertEqual(argv,['/usr/sbin/nft','--version'])
        self.assertTrue(spawn.call_args.kwargs['close_fds']);self.assertNotIn('shell',spawn.call_args.kwargs)
        proc.stdout.close.assert_called_once();proc.stderr.close.assert_called_once()
    def test_command_failure_is_sanitized(self):
        l=self.l;a,io=self.real_context();proc=Mock();proc.stdout.fileno.return_value=10;proc.stderr.fileno.return_value=11
        proc.stdin=None;proc.poll.return_value=1;proc.wait.return_value=1
        with patch('platform.system',return_value='Linux'),patch('subprocess.Popen',return_value=proc),\
             patch('selectors.DefaultSelector',FakeSelector),patch('os.set_blocking'),patch('os.read',return_value=b''):
            with self.assertRaisesRegex(Denied,'physical_command_unknown'):io.run('nft_version',l.budget())
    def test_read_paths_cannot_read_environment_or_credentials(self):
        l=self.l;a,io=self.real_context()
        with patch('platform.system',return_value='Linux'),patch('builtins.open') as opened:
            for path in ('/proc/self/environ','/etc/shadow','/proc/999/stat','/sys/../.env'):
                with self.subTest(path=path),self.assertRaises(Denied):io.read(path,l.budget())
            opened.assert_not_called()
    def test_namespace_broker_off_before_open_or_spawn(self):
        l=self.l;l.activation.enabled=False;broker=NamespaceSocketBroker(l.activation,l.inventory)
        with patch('os.open') as opened,patch('subprocess.Popen') as spawn,patch('socket.socketpair') as pair:
            with self.assertRaises(Denied):broker.open('runner',l.budget())
            opened.assert_not_called();spawn.assert_not_called();pair.assert_not_called()
    def test_kernel_socket_off_before_constructor(self):
        l=self.l;l.activation.enabled=False
        with patch('socket.socket') as factory:
            with self.assertRaises(Denied):KernelTraceSocket(l.activation).open(l.budget())
            factory.assert_not_called()
    def test_kernel_socket_options_no_suppression_of_enobufs(self):
        l=self.l;a,_=self.real_context();sock=Mock()
        with patch('platform.system',return_value='Linux'),patch('socket.AF_NETLINK',16,create=True),patch('socket.socket',return_value=sock) as factory:
            reader=KernelTraceSocket(a).open(l.budget())
            factory.assert_called_once_with(16,socket.SOCK_RAW,12);sock.bind.assert_called_once_with((0,256))
            self.assertEqual(len(sock.setsockopt.call_args_list),1)
            sock.recvmsg.return_value=(b'valid',[],0,(55,256))
            with self.assertRaises(Denied):reader.recv()
            sock.recvmsg.return_value=(b'valid',[],socket.MSG_TRUNC,(0,256))
            with self.assertRaises(Denied):reader.recv()
            reader.close();sock.close.assert_called_once()
    def test_helper_only_enters_network_namespace_under_mocks(self):
        packet,control=Mock(),Mock()
        with patch.object(namespace_helper.os,'setns',create=True) as setns,patch('os.fstat',return_value=SimpleNamespace(st_ino=555)),\
             patch('os.stat',return_value=SimpleNamespace(st_ino=555)),patch('socket.AF_PACKET',17,create=True),\
             patch('socket.socket',side_effect=[control,packet]),patch('socket.if_indextoname',return_value='eth0'),\
             patch('socket.if_nametoindex',return_value=2),patch('os.close'):
            packet.fileno.return_value=88
            namespace_helper.main(['10','11','2','555'])
            setns.assert_called_once_with(10,0x40000000);packet.bind.assert_called_once_with(('eth0',0))
            control.sendmsg.assert_called_once();packet.close.assert_called_once()
    def test_helper_stale_namespace_never_setns(self):
        with patch.object(namespace_helper.os,'setns',create=True) as setns,patch('os.fstat',return_value=SimpleNamespace(st_ino=999)):
            with self.assertRaises(ValueError):namespace_helper.main(['10','11','2','555'])
            setns.assert_not_called()
    def broker_roundtrip(self,wrong_credentials=False):
        l=self.l;a,io=self.real_context()
        from trusted_checker_physical.inventory import NamespaceInventory,InventoryReceipt
        from trusted_checker_physical.docker_readonly import ReadOnlyDocker
        inventory=NamespaceInventory(a,io,ReadOnlyDocker(a,l.endpoint))
        n=l.binding.runner
        receipt=InventoryReceipt(l.binding.digest,'physical_linux',l.clock(),((n.pid,n.netns_inode,n.peer_ifindex,'eth0'),))
        parent,child,packet,process=Mock(),Mock(),Mock(),Mock()
        process.pid=456;process.poll.return_value=0;process.wait.return_value=0
        child.fileno.return_value=12
        credentials=(999 if wrong_credentials else 456,os.geteuid(),1)
        parent.recvmsg.return_value=((str(n.netns_inode)+':'+str(n.peer_ifindex)).encode(),
            [(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[88]).tobytes()),(socket.SOL_SOCKET,2,struct.pack('=3i',*credentials))],0,None)
        packet.getsockopt.side_effect=lambda level,opt:{39:17,socket.SO_TYPE:socket.SOCK_RAW,38:socket.htons(3)}[opt]
        packet.getsockname.return_value=('eth0',3,0)
        with patch('platform.system',return_value='Linux'),patch('socket.AF_PACKET',17,create=True),\
             patch('socket.SO_DOMAIN',39,create=True),patch('socket.SO_PROTOCOL',38,create=True),\
             patch('socket.SO_PASSCRED',16,create=True),patch('socket.SCM_CREDENTIALS',2,create=True),\
             patch.object(inventory,'observe',return_value=receipt),patch.object(io,'read',return_value=l.files['/proc/'+str(n.pid)+'/stat']),\
             patch('os.open',return_value=10),patch('os.fstat',return_value=SimpleNamespace(st_ino=n.netns_inode)),\
             patch('os.close') as close,patch('socket.socketpair',return_value=(parent,child)),\
             patch('socket.socket',return_value=packet) as socket_factory,patch('subprocess.Popen',return_value=process) as spawn:
            broker=NamespaceSocketBroker(a,inventory)
            if wrong_credentials:
                with self.assertRaises(Denied):broker.open('runner',l.budget())
                socket_factory.assert_not_called();self.assertIn(((88,),),[(c.args,) for c in close.call_args_list])
            else:
                self.assertIs(broker.open('runner',l.budget()),packet)
                self.assertEqual(spawn.call_args.kwargs['pass_fds'],(10,12));self.assertIn('-I',spawn.call_args.args[0])
                packet.setblocking.assert_called_once_with(False)
    def test_broker_namespace_fd_and_scm_credentials(self):self.broker_roundtrip()
    def test_broker_wrong_sender_closes_received_fd(self):self.broker_roundtrip(True)
    def test_activation_path_off_without_journal_or_daemon(self):
        l=self.l
        # Use actual time only for expiry arithmetic, never any host operation.
        import time
        approval=replace(l.approval,created_at=time.time()-1,expires_at=time.time()+100)
        path=ReviewedActivationPath(l.auth,l.sign(approval,'approval'),l.runtime,l.endpoint)
        target=Path(l.tmp.name)/'must-not-exist.physical.sqlite3'
        with patch('socket.socket') as sock,patch('subprocess.Popen') as spawn:
            with self.assertRaises(Denied):path.open_installer(target)
            sock.assert_not_called();spawn.assert_not_called()
        self.assertFalse(target.exists())
    def test_closed_json_duplicate_keys(self):
        with self.assertRaises(Denied):json_output(b'{"nftables":[],"nftables":[]}')
    def test_separate_policy_proposal_cannot_activate_v2(self):
        from trusted_checker_physical.policy_proposal import LIVE_V3_PROPOSAL as proposal
        from trusted_checker_runtime.live_contract import LIVE_POLICY
        self.assertFalse(proposal.activatable);self.assertEqual(LIVE_POLICY.run_seconds,8)
        with self.assertRaises(Denied):replace(proposal,activatable=True)
        with self.assertRaises(Denied):replace(self.l.runtime,policy_id=proposal.policy_id,policy_version=3,policy_digest=proposal.digest)
    def test_timing_aggregates_repeated_stages_without_extending_deadline(self):
        l=self.l;b=l.budget(8);start=l.clock();l.clock.advance(1);b.record('nft_read',start)
        start=l.clock();l.clock.advance(1);b.record('nft_read',start)
        self.assertEqual(b.timings['nft_read']['count'],2);self.assertEqual(b.timings['nft_read']['total_seconds'],2)
        self.assertEqual(b.absolute,l.clock()+6)
    def test_fresh_module_reload_has_no_host_calls(self):
        # No DTO reload/type-identity changes in the shared interpreter. Import
        # implementation files already imported; constructors remain dormant.
        with patch('socket.socket',side_effect=AssertionError('socket')),patch('subprocess.Popen',side_effect=AssertionError('process')),\
             patch.object(os,'setns',side_effect=AssertionError('setns'),create=True):
            for module in ('packet_io','activation_path','io','preflight'):
                importlib.import_module('trusted_checker_physical.'+module)
    def test_no_legacy_writers_or_build_commands(self):
        for file in Path(__file__).parents[1].glob('*.py'):
            tree=ast.parse(file.read_text())
            for node in ast.walk(tree):
                names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
                self.assertFalse(any(n.split('.')[0] in ('django','sandbox','achievements','roadmap','traineediary','celery') for n in names),str(file))
