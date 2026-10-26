"""Standalone privileged helper: netns FD -> one bound packet FD -> exit.

No keys, request JSON, target binaries/mount/PID namespace, Docker or commands.
Invoked only by the dormant trusted parent with already opened namespace FDs.
"""
import array
import os
import socket
import sys


def main(argv):
    if len(argv)!=4 or any(not value.isdecimal() for value in argv):raise ValueError('helper_contract')
    namespace_fd,control_fd,ifindex,inode=map(int,argv)
    if min(namespace_fd,control_fd)<3 or ifindex<1 or os.fstat(namespace_fd).st_ino!=inode:raise ValueError('helper_identity')
    control=socket.socket(fileno=control_fd)
    packet=None
    try:
        control.settimeout(1)
        os.setns(namespace_fd,0x40000000) # CLONE_NEWNET only, in this short-lived process.
        if os.stat('/proc/self/ns/net').st_ino!=inode:raise ValueError('helper_namespace')
        interface=socket.if_indextoname(ifindex)
        packet=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3)) # ETH_P_ALL
        packet.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,131072)
        packet.setsockopt(263,8,1) # SOL_PACKET / PACKET_AUXDATA
        packet.bind((interface,0))
        if socket.if_nametoindex(interface)!=ifindex:raise ValueError('helper_interface')
        raw=(str(inode)+':'+str(ifindex)).encode('ascii')
        control.sendmsg([raw],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[packet.fileno()]))])
    finally:
        if packet is not None:packet.close()
        control.close();os.close(namespace_fd)


if __name__=='__main__':
    try:main(sys.argv[1:])
    except Exception:sys.exit(70) # No raw exception/stdout leak.
