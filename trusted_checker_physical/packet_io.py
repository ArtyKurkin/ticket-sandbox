"""Dormant fixed namespace socket broker and bounded packet/kernel readers."""
import array
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
from trusted_checker_runtime.profiles import require,Denied
from .contracts import PROFILE
from .inventory import start_ticks
from trusted_checker_network.packets import mac
import ipaddress


def peer_arp_request(binding):
    r,t=binding.runner,binding.target
    return mac(t.mac)+mac(r.mac)+b'\x08\x06'+b'\x00\x01\x08\x00\x06\x04\x00\x01'+mac(r.mac)+\
        ipaddress.IPv4Address(r.ipv4).packed+b'\x00'*6+ipaddress.IPv4Address(t.ipv4).packed


def approved_peer_arp(raw,binding):
    if len(raw)<14 or raw[12:14]!=b'\x08\x06':return False
    require(len(raw)>=42 and (len(raw)==42 or (len(raw)<=60 and not any(raw[42:]))),'physical_arp_padding_invalid')
    a=raw[14:42]
    require(a[:6]==b'\x00\x01\x08\x00\x06\x04' and a[6:8] in (b'\x00\x01',b'\x00\x02'),
            'physical_arp_template_invalid')
    for src,dst in ((binding.runner,binding.target),(binding.target,binding.runner)):
        if a[8:14]==mac(src.mac) and a[14:18]==ipaddress.IPv4Address(src.ipv4).packed:
            require(a[24:28]==ipaddress.IPv4Address(dst.ipv4).packed and raw[6:12]==mac(src.mac) and
                    raw[:6] in (mac(dst.mac),b'\xff'*6) and a[18:24] in (mac(dst.mac),b'\x00'*6),
                    'physical_foreign_arp')
            return True
    require(False,'physical_foreign_arp')


class NamespaceSocketBroker:
    def __init__(self,activation,inventory):
        from .inventory import NamespaceInventory
        require(type(inventory) is NamespaceInventory and inventory.activation is activation,'physical_socket_inventory_required')
        self.activation,self.inventory=activation,inventory
    def open(self,which,budget):
        a=self.activation.check('mutate')
        require(not self.activation.offline,'physical_namespace_socket_simulation_forbidden')
        require(which in ('runner','target','host_runner'),'physical_socket_role_invalid')
        b=a.binding
        n=b.runner if which in ('runner','host_runner') else b.target
        pid='self' if which=='host_runner' else str(n.pid)
        inode=b.host_netns_inode if which=='host_runner' else n.netns_inode
        ifindex=n.ifindex if which=='host_runner' else n.peer_ifindex
        inventory=self.inventory.observe(budget)
        require(inventory.origin==self.activation.origin,'physical_socket_inventory_origin_mismatch')
        expected_name=n.interface if which=='host_runner' else next(p[3] for p in inventory.namespace_peers if p[0]==n.pid)
        if pid!='self':
            require(start_ticks(self.inventory.io.read('/proc/'+pid+'/stat',budget))==n.process_start_ticks,
                    'physical_socket_pid_reused')
        fd=os.open('/proc/'+pid+'/ns/net',os.O_RDONLY|os.O_CLOEXEC)
        parent=child=process=packet=None
        received=[]
        try:
            require(os.fstat(fd).st_ino==inode,'physical_socket_namespace_reused')
            parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
            parent.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
            helper=Path(__file__).with_name('namespace_helper.py')
            # Manifest pinned by signed approval at installer registration;
            # re-check immediately before executing the local trusted helper.
            from .artifacts import source_digest
            require(source_digest()==a.source_digest,'physical_helper_source_changed')
            process=subprocess.Popen([sys.executable,'-I',str(helper),str(fd),str(child.fileno()),str(ifindex),str(inode)],
                pass_fds=(fd,child.fileno()),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                cwd='/',env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LC_ALL':'C'},close_fds=True)
            child.close();parent.settimeout(budget.remaining(1))
            raw,ancillary,flags,_=parent.recvmsg(128,socket.CMSG_SPACE(array.array('i').itemsize*4)+socket.CMSG_SPACE(12))
            credentials=[];unknown=False
            for level,kind,data in ancillary:
                if (level,kind)==(socket.SOL_SOCKET,socket.SCM_RIGHTS):
                    values=array.array('i');values.frombytes(data);received.extend(values)
                elif (level,kind)==(socket.SOL_SOCKET,socket.SCM_CREDENTIALS) and len(data)==12:
                    credentials.append(struct.unpack('=3i',data))
                else:unknown=True
            require(not flags and not unknown and raw==(str(inode)+':'+str(ifindex)).encode() and
                    len(credentials)==1 and credentials[0][:2]==(process.pid,os.geteuid()),'physical_helper_reply_invalid')
            require(len(received)==1 and process.wait(timeout=budget.remaining(1))==0,'physical_helper_failed')
            packet=socket.socket(fileno=received.pop())
            require(packet.getsockopt(socket.SOL_SOCKET,socket.SO_DOMAIN)==socket.AF_PACKET and
                    packet.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)==socket.SOCK_RAW and
                    packet.getsockopt(socket.SOL_SOCKET,socket.SO_PROTOCOL)==socket.htons(3) and
                    packet.getsockname()[0]==expected_name,'physical_packet_fd_invalid')
            self.inventory.observe(budget)
            packet.setblocking(False)
            return packet
        except Exception:
            if packet is not None:packet.close()
            raise Denied('physical_namespace_socket_unknown') from None
        finally:
            for item in received:os.close(item)
            os.close(fd)
            if parent is not None:parent.close()
            if child is not None:child.close()
            if process is not None:
                if process.poll() is None:process.kill()
                process.wait(timeout=1)


class KernelTraceSocket:
    def __init__(self,activation):self.activation=activation;self.socket=None
    def open(self,budget):
        self.activation.check('mutate');require(not self.activation.offline,'physical_kernel_socket_simulation_forbidden')
        budget.remaining()
        sock=socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,12) # NETLINK_NETFILTER
        try:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,131072)
            # Do NOT set NETLINK_NO_ENOBUFS: ENOBUFS must remain visible.
            sock.bind((0,1<<8));sock.setblocking(False) # NFNLGRP_NFTRACE=9
            self.socket=sock;return self
        except BaseException:sock.close();raise
    def recv(self):
        raw,anc,flags,peer=self.socket.recvmsg(8192,256)
        require(not flags and len(raw)<=8192 and not anc and peer[0]==0,'physical_kernel_event_not_kernel')
        return raw,peer
    def close(self):
        if self.socket is not None:self.socket.close()


def packet_read(sock):
    raw,ancillary,flags,address=sock.recvmsg(PROFILE.frame_limit+1,256)
    require(not flags and len(raw)<=PROFILE.frame_limit,'physical_packet_truncated')
    for level,kind,data in ancillary:
        require((level,kind)==(263,8) and len(data)>=20,'physical_packet_auxdata_invalid')
        status,length,snaplen=struct.unpack_from('=III',data)
        require(not status & (4|8|16) and length==snaplen==len(raw),'physical_packet_loss_or_offload')
    return raw,address


def packet_statistics(sock):
    raw=sock.getsockopt(263,6,8) # PACKET_STATISTICS resets counters on read.
    require(len(raw)==8,'physical_packet_statistics_invalid')
    received,dropped=struct.unpack('=II',raw)
    require(dropped==0,'physical_packet_capture_loss')
    return received
