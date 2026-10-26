"""Separate iproute2 6.1 diagnostic registry revision 2, reviewed from saved bytes.

Never widens the provisional V2-03 registry or supplies missing kernel defaults.
All normalization/OS/temporal meanings outside this shape contract are unproven.
"""
from dataclasses import dataclass
import ipaddress
import re

from . import native_v2_contracts as c
from . import native_v2_topology_schema as old
from .native_v2_topology_json import ExactDecimal2, bounded_topology_json2

ARCHIVE_SHA256 = 'b641f7f27eeac55c72651ab6f76effff034135d01cc35226d19c49a35283e0b5'
PROFILE_ID = 'iproute2-6.1.0-native-topology-v2-diagnostic-2'
SOURCES = ('link','address','bridge_link','bridge_vlan','bridge_fdb','route4','route6','rule4','rule6')
# Nominal source plan only. The supplied archive contains no actual argv log.
NOMINAL_ARGV = (
    ('link',('ip','-j','-d','link','show')),
    ('address',('ip','-j','address','show')),
    ('bridge_link',('bridge','-j','-d','link','show')),
    ('bridge_vlan',('bridge','-j','vlan','show')),
    ('bridge_fdb',('bridge','-j','fdb','show')),
    ('route4',('ip','-j','-4','route','show','table','all')),
    ('route6',('ip','-j','-6','route','show','table','all')),
    ('rule4',('ip','-j','-4','rule','show')),
    ('rule6',('ip','-j','-6','rule','show')),
)


@dataclass(frozen=True, slots=True)
class NativeField61:
    source: str
    path: tuple[str, ...]
    kind: str
    required: bool
    disposition: str
    evidence_reference: str
    transition: str = 'exact_unchanged_meaning_unreviewed'


def _registry():
    fields=[]
    def add(source,path,kind,required=True,disposition='structural'):
        fields.append(NativeField61(source,tuple(path.split('.')),kind,required,disposition,
                                    ARCHIVE_SHA256+':'+source+'.json'))
    def flat(source,prefix,items,required=True):
        for key,kind in items:
            add(source,prefix+key,kind,required)
    common=(('ifindex','index'),('ifname','ifname'),('flags','linkflags'),('mtu','index'),
        ('qdisc','qdisc'),('operstate','operstate'),('group','group'),('txqlen','uint32'),
        ('link_type','link_type'),('address','mac'),('broadcast','mac'))
    extras=(('altnames','ifnames'),('link_index','index'),('link_netnsid','uint32'),('master','ifname'))
    for source in ('link','address'):
        flat(source,'',common)
        flat(source,'',extras,False)
    flat('link','',(('linkmode','linkmode'),('promiscuity','uint32'),('allmulti','uint32'),
        ('min_mtu','uint32'),('max_mtu','uint32'),('inet6_addr_gen_mode','addrgen'),
        ('num_tx_queues','index'),('num_rx_queues','index'),('gso_max_size','uint32'),
        ('gso_max_segs','uint32'),('tso_max_size','uint32'),('tso_max_segs','uint32'),('gro_max_size','uint32')))
    flat('link','',(('parentbus','parentbus'),('parentdev','parentdev'),('linkinfo','object')),False)
    add('link','linkinfo.info_kind','kind')
    flat('link','linkinfo.',(('info_data','object'),('info_slave_kind','slavekind'),('info_slave_data','object')),False)
    bridge_ints='''forward_delay hello_time max_age ageing_time stp_state priority vlan_filtering
        root_port root_path_cost topology_change topology_change_detected vlan_default_pvid
        vlan_stats_enabled vlan_stats_per_port mcast_snooping no_linklocal_learn mcast_vlan_snooping
        mcast_router mcast_query_use_ifaddr mcast_querier mcast_hash_elasticity mcast_hash_max
        mcast_last_member_cnt mcast_startup_query_cnt mcast_last_member_intvl mcast_membership_intvl
        mcast_querier_intvl mcast_query_intvl mcast_query_response_intvl mcast_startup_query_intvl
        mcast_stats_enabled mcast_igmp_version mcast_mld_version nf_call_iptables nf_call_ip6tables
        nf_call_arptables'''.split()
    flat('link','linkinfo.info_data.',tuple((name,'uint32') for name in bridge_ints))
    flat('link','linkinfo.info_data.',(('vlan_protocol','vlanprotocol'),('bridge_id','bridgeid'),
        ('root_id','bridgeid'),('group_fwd_mask','masktoken'),('group_addr','mac')))
    for name in ('hello_timer','tcn_timer','topology_change_timer','gc_timer'):
        add('link','linkinfo.info_data.'+name,'decimal',disposition='observed_volatile')
    bools='''hairpin guard root_block fastleave learning flood mcast_flood bcast_flood
        mcast_to_unicast neigh_suppress vlan_tunnel isolated locked'''.split()
    for prefix,source in (('linkinfo.info_slave_data.','link'),('','bridge_link')):
        flat(source,prefix,(('state','portstate'),('priority','uint32'),('cost','uint32')))
        flat(source,prefix,tuple((name,'bool') for name in bools))
    flat('bridge_link','',(('ifindex','index'),('link','ifname'),('ifname','ifname'),('flags','linkflags'),
        ('mtu','index'),('master','ifname'),('mcast_router','uint32')))
    flat('link','linkinfo.info_slave_data.',(('id','hextoken'),('no','hextoken'),
        ('designated_port','uint32'),('designated_cost','uint32'),('bridge_id','bridgeid'),('root_id','bridgeid'),
        ('topology_change_ack','uint32'),('config_pending','uint32'),('proxy_arp','bool'),('proxy_arp_wifi','bool'),
        ('multicast_router','uint32'),('group_fwd_mask','masktoken'),('group_fwd_mask_str','hextoken')))
    for name in ('hold_timer','message_age_timer','forward_delay_timer'):
        add('link','linkinfo.info_slave_data.'+name,'decimal',disposition='observed_volatile')
    add('address','addr_info','rows')
    flat('address','addr_info.*.',(('family','family'),('local','ip'),('prefixlen','prefix'),('scope','address_scope')))
    for name in ('valid_life_time','preferred_life_time'):
        add('address','addr_info.*.'+name,'uint32',disposition='observed_volatile')
    flat('address','addr_info.*.',(('label','ifname'),('noprefixroute','bool'),('metric','uint32'),
        ('broadcast','ip'),('dynamic','bool')),False)
    add('bridge_vlan','ifname','ifname');add('bridge_vlan','vlans','rows')
    flat('bridge_vlan','vlans.*.',(('vlan','vlan'),('flags','vlanflags')))
    flat('bridge_fdb','',(('mac','mac'),('ifname','ifname'),('flags','fdbflags'),('state','fdbstate')))
    flat('bridge_fdb','',(('master','ifname'),('vlan','vlan')),False)
    for source in ('route4','route6'):
        flat(source,'',(('dst','routeprefix'),('dev','ifname'),('protocol','protocol'+source[-1]),('flags','emptyflags')))
        flat(source,'',(('type','routetype'+source[-1]),('table','routetable'),('gateway','ip')),False)
    flat('route4','',(('prefsrc','ip'),))
    flat('route4','',(('scope','route_scope'),('metric','uint32')),False)
    flat('route6','',(('metric','uint32'),('pref','pref')))
    add('route6','expires','uint32',False,'observed_volatile')
    add('route6','metrics','metrics',False)
    add('route6','metrics.*.hoplimit','uint8')
    for source in ('rule4','rule6'):
        flat(source,'',(('priority','uint32'),('src','all'),('table','ruletable'+source[-1])))
    # These exact path identities are part of the registry, not inferred from input.
    identities={'ifindex','ifname','address','master','link_index','link_netnsid'}
    return tuple(NativeField61(f.source,f.path,f.kind,f.required,
        'identity' if len(f.path)==1 and f.path[0] in identities else
        'ordered_policy' if f.source.startswith(('route','rule')) and f.disposition!='observed_volatile' else f.disposition,
        f.evidence_reference,f.transition) for f in fields)


LITERAL_VALUES61=tuple({
    'qdisc':('noqueue','fq_codel'),'operstate':('UNKNOWN','UP'),'group':('default',),
    'link_type':('loopback','ether'),'linkmode':('DEFAULT',),'addrgen':('eui64',),
    'parentbus':('virtio',),'parentdev':('virtio0',),'kind':('bridge','veth'),
    'slavekind':('bridge',),'portstate':('forwarding',),'vlanprotocol':('802.1Q',),
    'masktoken':('0',),'family':('inet','inet6'),'address_scope':('host','global','link'),
    'fdbstate':('permanent',),'protocol4':('kernel','dhcp'),'protocol6':('kernel','ra'),
    'routetype4':('local','broadcast'),'routetype6':('local','multicast'),
    'routetable':('local',),'route_scope':('link','host'),'pref':('medium',),
    'all':('all',),'ruletable4':('local','main','default'),'ruletable6':('local','main'),
}.items())
FLAG_VALUES61=tuple({
    'linkflags':('LOOPBACK','UP','LOWER_UP','BROADCAST','MULTICAST'),
    'vlanflags':('PVID','Egress Untagged'),'fdbflags':('self',),'emptyflags':(),
}.items())

INTEGER_BOUNDS61=(('index',(1,2**31-1)),('uint32',(0,2**32-1)),
    ('uint8',(0,255)),('vlan',(1,4094)),('prefix',(0,128)))


REGISTRY61 = _registry()
REGISTRY_DIGEST61 = c._hash('native61_registry_revision2',(
    tuple(tuple(getattr(f,k) for k in f.__dataclass_fields__) for f in REGISTRY61),
    LITERAL_VALUES61,FLAG_VALUES61,INTEGER_BOUNDS61,'decimal_exact_10_6_no_unit_claim',
))
SOURCE_DIGEST61 = c._hash('native61_source_registry_revision2',(
    NOMINAL_ARGV,'actual_argv_not_recorded',1048576,16777216,256,32,65536,1024,512,
))


@dataclass(frozen=True, slots=True)
class NativeTopologyProfile61(c._Offline2):
    ip_build_reference_digest: str
    bridge_build_reference_digest: str
    profile_id: str = PROFILE_ID
    schema_revision: int = 2
    iproute2_version: str = '6.1.0'
    bridge_version: str = '6.1.0'
    field_registry_digest: str = REGISTRY_DIGEST61
    source_registry_digest: str = SOURCE_DIGEST61
    acceptance: str = 'diagnostic_format_only_semantics_unreviewed'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._hex(self.ip_build_reference_digest);c._hex(self.bridge_build_reference_digest)
        for actual,expected in ((self.profile_id,PROFILE_ID),(self.iproute2_version,'6.1.0'),
                (self.bridge_version,'6.1.0'),(self.field_registry_digest,REGISTRY_DIGEST61),
                (self.source_registry_digest,SOURCE_DIGEST61),
                (self.acceptance,'diagnostic_format_only_semantics_unreviewed')):
            c._require(type(actual) is str and actual==expected,'v2_native61_profile_mismatch')
        c._require(type(self.schema_revision) is int and self.schema_revision==2,'v2_native61_profile_mismatch')



def _scalar(value,kind):
    literals=dict(LITERAL_VALUES61);flag_literals=dict(FLAG_VALUES61)
    if kind in literals:
        c._require(type(value) is str and value in literals[kind],'v2_native61_literal_invalid')
    elif kind in flag_literals:
        c._require(type(value) is list and len(value)<=64 and
            all(type(v) is str and v in flag_literals[kind] for v in value) and
            len(set(value))==len(value),'v2_native61_flags_invalid')
    elif kind=='ifnames':
        c._require(type(value) is list and len(value)<=64,'v2_native61_field_invalid')
        for v in value: old._scalar(v,'ifname')
        c._require(len(set(value))==len(value),'v2_native61_field_invalid')
    elif kind in ('index','uint32','uint8','vlan','prefix'):
        minimum,maximum=dict(INTEGER_BOUNDS61)[kind]
        c._require(type(value) is int and minimum<=value<=maximum,'v2_native61_integer_invalid')
    elif kind=='bool':
        c._require(type(value) is bool,'v2_native61_bool_invalid')
    elif kind=='decimal':
        c._require(type(value) is ExactDecimal2,'v2_native61_decimal_invalid')
        value.__post_init__()  # No int/float coercion; units/meaning remain unreviewed.
    elif kind=='hextoken':
        c._require(type(value) is str and re.fullmatch('0x[0-9a-f]{1,8}',value) is not None,'v2_native61_field_invalid')
    elif kind=='bridgeid':
        c._require(type(value) is str and re.fullmatch('[0-9a-f]{4}\\.[0-9a-f]{2}(:[0-9a-f]{2}){5}',value) is not None,'v2_native61_field_invalid')
    elif kind in ('ifname','ip','mac'):
        old._scalar(value,kind)
    elif kind=='routeprefix':
        c._require(type(value) is str,'v2_native61_field_invalid')
        try:
            valid=value=='default' or str(ipaddress.ip_network(value,strict=True) if '/' in value else ipaddress.ip_address(value))==value
        except ValueError: valid=False
        c._require(valid,'v2_native61_field_invalid')
    else:
        raise c.ContractViolation2('v2_native61_registry_invalid')


def validate_native61_rows(source,rows):
    c._enum(source,SOURCES)
    c._require(type(rows) is list and len(rows)<=1024,'v2_native61_rows_invalid')
    specs={r.path:r for r in REGISTRY61 if r.source==source}
    def obj(value,prefix=()):
        c._require(type(value) is dict,'v2_native61_object_invalid')
        direct={p[-1]:r for p,r in specs.items() if p[:-1]==prefix}
        c._require(set(value)<=set(direct),'v2_native61_unknown_field')
        c._require(all(k in value for k,r in direct.items() if r.required),'v2_native61_field_missing')
        for k,v in value.items():
            r=direct[k]
            if r.kind=='object': obj(v,prefix+(k,))
            elif r.kind in ('rows','metrics'):
                c._require(type(v) is list and len(v)<=1024 and
                    (r.kind!='metrics' or len(v)==1),'v2_native61_array_invalid')
                for row in v: obj(row,prefix+(k,'*'))
            else: _scalar(v,r.kind)
    for row in rows:
        obj(row)
        if source=='link':
            info=row.get('linkinfo',{})
            c._require(('parentbus' in row)==('parentdev' in row),'v2_native61_parent_incomplete')
            if info.get('info_kind')=='bridge':
                c._require('info_data' in info and 'info_slave_data' not in info and 'info_slave_kind' not in info,'v2_native61_link_shape_invalid')
            else:
                c._require('info_data' not in info,'v2_native61_link_shape_invalid')
            if 'master' in row:
                c._require(info.get('info_kind')=='veth' and info.get('info_slave_kind')=='bridge' and
                    'info_slave_data' in info,'v2_native61_link_shape_invalid')
            else:
                c._require('info_slave_kind' not in info and 'info_slave_data' not in info,'v2_native61_link_shape_invalid')
            if info.get('info_kind')=='veth':
                c._require('link_index' in row and 'link_netnsid' in row,'v2_native61_peer_fields_missing')
        if source=='address':
            for a in row['addr_info']:
                version=4 if a['family']=='inet' else 6
                c._require(ipaddress.ip_address(a['local']).version==version and
                    a['prefixlen']<=(32 if version==4 else 128),'v2_native61_family_invalid')
                if 'broadcast' in a: c._require(ipaddress.ip_address(a['broadcast']).version==version,'v2_native61_family_invalid')
        if source=='bridge_fdb':
            c._require((row['flags']==['self'] and 'master' not in row and 'vlan' not in row) or
                (row['flags']==[] and 'master' in row),'v2_native61_fdb_shape_unreviewed')
        if source.startswith('route'):
            version=int(source[-1])
            for key in ('dst','gateway','prefsrc'):
                if key in row and row[key]!='default':
                    actual=ipaddress.ip_network(row[key],strict=False).version
                    c._require(actual==version,'v2_native61_family_invalid')
    return tuple(old._freeze(row) for row in rows)


def decode_native61_rows(raw,source):
    return validate_native61_rows(source,bounded_topology_json2(raw))
