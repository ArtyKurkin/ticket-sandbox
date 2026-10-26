"""Strict native NFTRACE decoder. JSON supplied by an operator is not input."""
from dataclasses import dataclass
import struct
from trusted_checker_runtime.profiles import require


def attrs(raw):
    result={};offset=0
    while offset<len(raw):
        require(offset+4<=len(raw),'physical_netlink_attribute_short')
        size,kind=struct.unpack_from('=HH',raw,offset);kind &= 0x3fff
        require(size>=4 and offset+size<=len(raw) and kind not in result,'physical_netlink_attribute_invalid')
        result[kind]=raw[offset+4:offset+size];offset+=(size+3)&~3
    require(offset==len(raw),'physical_netlink_padding_invalid');return result


def number(attributes,key,size=4,native=False):
    raw=attributes[key];require(len(raw)==size,'physical_netlink_scalar_invalid')
    return int.from_bytes(raw,'little' if native and __import__('sys').byteorder=='little' else 'big')


def text(raw):
    require(raw.endswith(b'\x00') and 1<len(raw)<=64 and b'\x00' not in raw[:-1],'physical_netlink_string_invalid')
    return raw[:-1].decode('ascii')


@dataclass(frozen=True)
class TraceRecord:
    trace_id: int
    table: str
    chain: str
    verdict: int | None
    iif: int | None
    frame: bytes | None
    event_type: int
    # Native nftrace has neither a lossless stream sequence nor notification
    # when nlmsg allocation fails. This is intentionally never true.
    continuity_proven: bool = False


def decode_kernel(raw,peer):
    require(type(raw) is bytes and 20<=len(raw)<=8192 and type(peer) is tuple and peer[0]==0,
            'physical_kernel_event_not_kernel')
    offset=0;events=[]
    while offset<len(raw):
        require(offset+20<=len(raw),'physical_netlink_message_short')
        size,kind,flags,sequence,pid=struct.unpack_from('=IHHII',raw,offset)
        require(20<=size<=len(raw)-offset and kind==0x0a11 and pid==0 and sequence==0 and flags==0,
                'physical_kernel_trace_header_invalid')
        require(raw[offset+16:offset+20]==b'\x07\x00\x00\x00','physical_kernel_trace_family_invalid')
        a=attrs(raw[offset+20:offset+size])
        require(set(a)<={1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17} and {1,2,4,6,15}<=set(a),
                'physical_trace_attribute_set_invalid')
        require(number(a,15)==7,'physical_trace_nfproto_invalid')
        event_type=number(a,4);require(event_type in (1,2,3),'physical_trace_event_type_invalid')
        verdict=number(a,16) if 16 in a else number(attrs(a[5]),1) if 5 in a else None
        frame=a[7]+a[8]+a[9] if {7,8,9}<=set(a) else None
        if frame is not None:require(14<=len(frame)<=128,'physical_trace_frame_invalid')
        events.append(TraceRecord(number(a,6,native=True),text(a[1]),text(a[2]),verdict,
                                  number(a,10) if 10 in a else None,frame,event_type))
        offset+=(size+3)&~3
    require(offset==len(raw),'physical_netlink_message_padding_invalid');return tuple(events)
