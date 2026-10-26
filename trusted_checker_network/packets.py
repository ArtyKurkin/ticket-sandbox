"""Finite synthetic header probes. No socket, URL, DNS or target program."""
from dataclasses import dataclass
import hashlib
import ipaddress
import struct
from trusted_checker_runtime.profiles import require
from trusted_checker_runtime.contracts import uid
from .contracts import CASES


def mac(value): return bytes.fromhex(value.replace(':',''))


def unpad(frame):
    """AF_PACKET can include minimum Ethernet padding; never strip payload."""
    require(type(frame) is bytes and 14 <= len(frame) <= 128,'packet_frame_invalid')
    offset,kind = 14,frame[12:14]
    if kind == b'\x81\x00':
        require(len(frame)>=18,'packet_vlan_invalid')
        offset,kind = 18,frame[16:18]
    if kind == b'\x08\x00':
        require(len(frame)>=offset+20,'packet_ipv4_short')
        end=offset+struct.unpack('!H',frame[offset+2:offset+4])[0]
    elif kind == b'\x86\xdd':
        require(len(frame)>=offset+40,'packet_ipv6_short')
        end=offset+40+struct.unpack('!H',frame[offset+4:offset+6])[0]
    else:require(False,'packet_ethertype_invalid')
    require(offset < end <= len(frame) and (len(frame)==end or
            (len(frame)<=60 and frame[end:]==b'\x00'*(len(frame)-end))),'packet_padding_invalid')
    return frame[:end]


def checksum(raw):
    if len(raw) % 2: raw += b'\x00'
    total = sum(struct.unpack('!%dH' % (len(raw)//2),raw))
    while total >> 16: total = (total & 65535)+(total >> 16)
    return (~total)&65535


def ipv4_frame(source_mac, destination_mac, source_ip, destination_ip, port, sequence, *, udp=False, flags=2, reverse=False):
    src,dst = ipaddress.IPv4Address(source_ip).packed,ipaddress.IPv4Address(destination_ip).packed
    sport,dport = (port,49152) if reverse else (49152,port)
    protocol = 17 if udp else 6
    if udp:
        segment = struct.pack('!HHHH',sport,dport,8,0)
    else:
        segment = struct.pack('!HHIIBBHHH',sport,dport,0 if reverse else sequence,
                              sequence+1 if reverse else 0,80,flags,1024,0,0)
    pseudo = src+dst+struct.pack('!BBH',0,protocol,len(segment))
    offset = 6 if udp else 16
    segment = segment[:offset]+struct.pack('!H',checksum(pseudo+segment))+segment[offset+2:]
    header = struct.pack('!BBHHHBBH4s4s',69,0,20+len(segment),sequence&65535,16384,64,protocol,0,src,dst)
    header = header[:10]+struct.pack('!H',checksum(header))+header[12:]
    return mac(destination_mac)+mac(source_mac)+b'\x08\x00'+header+segment


@dataclass(frozen=True)
class Probe:
    case: str
    probe_id: str
    frame: bytes
    destination_ip: str
    port: int
    sequence: int
    response_required: bool

    def __post_init__(self):
        require(self.case in CASES and type(self.frame) is bytes and 14 <= len(self.frame) <= 128 and
                type(self.probe_id) is str and len(self.probe_id) == 64 and type(self.port) is int and
                0 <= self.port <= 65535 and type(self.sequence) is int and 0 <= self.sequence < 2**31 and
                type(self.response_required) is bool, 'probe_contract_invalid')


def plan(binding, matrix_uuid):
    """Operator cannot substitute a destination. Platform canaries are approved IPs."""
    uid(matrix_uuid)
    r,t = binding.runner,binding.target
    specifications = (
        ('allow_target_8080',t.ipv4,8080,False),
        ('deny_other_target_ports',t.ipv4,8081,False),
        ('deny_other_target_ports',t.ipv4,22,False),
        ('deny_other_ipv4',binding.other_ipv4,443,False),
        ('deny_host',binding.gateway_ipv4,443,False),
        ('deny_metadata','169.254.169.254',80,False),
        ('deny_db_redis_django',binding.db_ipv4,5432,False),
        ('deny_db_redis_django',binding.redis_ipv4,6379,False),
        ('deny_db_redis_django',binding.django_ipv4,8000,False),
        ('deny_dns',binding.gateway_ipv4,53,True),
        ('deny_dns',binding.gateway_ipv4,53,False),
        ('deny_ipv6','fe80::1',8080,False),
        ('deny_spoofing',t.ipv4,8080,False),
        ('deny_spoofing',t.ipv4,8080,True),
        ('deny_extra_attachment',binding.other_ipv4,8080,False),
    )
    probes = []
    for index,(case,ip,port,udp) in enumerate(specifications):
        ident = hashlib.sha256((matrix_uuid+':'+str(index)+':'+binding.digest).encode()).hexdigest()
        seq = int(ident[:7],16)
        destination_mac = t.mac if ip == t.ipv4 else binding.bridge_mac
        src = '172.31.255.254' if case == 'deny_spoofing' else r.ipv4
        if case == 'deny_ipv6':
            # IPv6 SYN with a proper pseudo-header checksum; no name resolution.
            s6,d6 = ipaddress.IPv6Address('fe80::2').packed,ipaddress.IPv6Address(ip).packed
            tcp = struct.pack('!HHIIBBHHH',49152,port,seq,0,80,2,1024,0,0)
            check = checksum(s6+d6+struct.pack('!I3xB',20,6)+tcp)
            tcp = tcp[:16]+struct.pack('!H',check)+tcp[18:]
            frame = mac(destination_mac)+mac(r.mac)+b'\x86\xdd'+struct.pack('!IHBB',6<<28,20,6,64)+s6+d6+tcp
        else:
            frame = ipv4_frame(r.mac,destination_mac,src,ip,port,seq,udp=udp)
            if case == 'deny_spoofing' and udp:
                # VLAN-tagged IPv4 bypass attempt (not a DNS packet).
                frame = frame[:12]+b'\x81\x00\x00\x01'+frame[12:]
        probes.append(Probe(case,ident,frame,ip,port,seq,case == 'allow_target_8080'))
    return tuple(probes)


def classify_reply(probe, binding, frame):
    """Only a matching SYN-ACK or RST-ACK proves this exact TCP exchange."""
    r,t = binding.runner,binding.target
    frame=unpad(frame)
    require(len(frame) >= 54 and frame[:14] == mac(r.mac)+mac(t.mac)+b'\x08\x00',
            'reply_l2_invalid')
    ip,tcp = frame[14:34],frame[34:]
    require(ip[0] == 69 and ip[9] == 6 and checksum(ip) == 0 and
            ip[12:16] == ipaddress.IPv4Address(t.ipv4).packed and
            ip[16:20] == ipaddress.IPv4Address(r.ipv4).packed and
            struct.unpack('!H',ip[2:4])[0] == len(frame)-14 and struct.unpack('!H',ip[6:8])[0] & 16383 == 0,
            'reply_ipv4_invalid')
    pseudo = ip[12:20]+struct.pack('!BBH',0,6,len(tcp))
    sport,dport,_,ack = struct.unpack('!HHII',tcp[:12])
    require(sport == 8080 and dport == 49152 and ack == probe.sequence+1 and
            20 <= (tcp[12]>>4)*4 == len(tcp) <= 60 and tcp[12] & 15 == 0 and
            checksum(pseudo+tcp) == 0 and tcp[13] in (18,20), 'reply_flow_invalid')
    pos=20
    while pos<len(tcp):
        option=tcp[pos]
        if option==0:
            require(not any(tcp[pos:]),'reply_option_invalid');break
        if option==1:pos+=1;continue
        require(pos+1<len(tcp) and tcp[pos+1]>=2 and pos+tcp[pos+1]<=len(tcp),'reply_option_invalid')
        pos+=tcp[pos+1]
    return 'path_open_rst' if tcp[13] == 20 else 'path_open_synack'
