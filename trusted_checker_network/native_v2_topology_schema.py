"""Closed provisional offline iproute2 registry. No host inspection or discovery."""
from dataclasses import dataclass
import ipaddress
import re
from . import native_v2_contracts as c
from .native_v2_topology_json import ExactDecimal2

SOURCES = ('link', 'address', 'bridge_link', 'vlan', 'fdb', 'route4', 'route6', 'rule4', 'rule6')
COMMANDS = (
    ('link', ('ip', '-j', '-d', 'link', 'show')),
    ('address', ('ip', '-j', 'address', 'show')),
    ('bridge_link', ('bridge', '-j', '-d', 'link', 'show')),
    ('vlan', ('bridge', '-j', 'vlan', 'show')),
    ('fdb', ('bridge', '-j', 'fdb', 'show')),
    ('route4', ('ip', '-j', '-4', 'route', 'show', 'table', 'all')),
    ('route6', ('ip', '-j', '-6', 'route', 'show', 'table', 'all')),
    ('rule4', ('ip', '-j', '-4', 'rule', 'show')),
    ('rule6', ('ip', '-j', '-6', 'rule', 'show')),
    ('link_single', ('ip', '-j', '-d', 'link', 'show', 'tc-br0')),
    ('bridge_link_basic', ('bridge', '-j', 'link', 'show')),
)


@dataclass(frozen=True, slots=True)
class FieldSpec2:
    source: str
    path: tuple[str, ...]
    value_type: str
    required: bool
    disposition: str
    constraint: str
    purpose: str
    evidence_reference: str
    transition: str = 'exact_unchanged'


# Every field is registered before an input exists. '*' denotes an array row.
def _registry():
    rows = []
    def add(source, path, typ, required=False, disposition='structural', constraint='closed_type'):
        observed = source in ('link_single', 'bridge_link_basic')
        if source=='link_single' and path in ('master','link_index','link_netnsid'): observed=False
        if source=='bridge_link_basic' and path not in ('ifindex','ifname','link','flags','mtu','master','state','priority','cost'): observed=False
        ref = ('native/bridge_tc_br0_final.json' if source == 'link_single' and observed else
               'native/bridge_links_final.json' if observed else 'provisional_offline_specification_v1')
        enums={
            'route_type':'unicast|local|broadcast', 'route_scope':'global|link|host',
            'route_protocol':'kernel|boot|static|ra|dhcp', 'route_pref':'low|medium|high',
            'rule_action':'lookup', 'bridge_state':'disabled|listening|learning|forwarding|blocking',
            'link_flags':'LOOPBACK|BROADCAST|MULTICAST|UP|LOWER_UP|NOARP|POINTOPOINT|DORMANT|PROMISC|ALLMULTI|MASTER|SLAVE',
            'address_flags':'secondary|temporary|dynamic|deprecated|tentative|dadfailed|noprefixroute|mngtmpaddr|permanent|nodad|optimistic|home',
            'vlan_flags':'PVID|Egress_Untagged', 'fdb_flags':'self|master|router|extern_learn|offload|sticky',
            'fdb_state':'permanent|static|dynamic|reachable|stale|noarp|failed|incomplete|delay|probe',
            'route_flags':'onlink|linkdown|offload|trap',
        }
        field_type=None
        if source in ('link','link_single','bridge_link','bridge_link_basic') and path=='flags': field_type='link_flags'
        if source in ('bridge_link','bridge_link_basic') and path=='state': field_type='bridge_state'
        if source=='address' and path=='addr_info.*.flags': field_type='address_flags'
        if source=='vlan' and path=='vlans.*.flags': field_type='vlan_flags'
        if source=='fdb' and path in ('state','flags'): field_type='fdb_'+path
        if source.startswith('route') and path in ('type','scope','protocol','pref','flags'): field_type='route_'+path
        if source.startswith('rule') and path=='action': field_type='rule_action'
        if field_type:
            typ=('flags:' if field_type.endswith('_flags') or field_type=='fdb_state' else 'enum:')+enums[field_type]
            constraint='exact_registered_literals; flags_unique_0..64' if typ.startswith('flags:') else 'exact_registered_literal'
        if constraint=='closed_type':
            constraint={
                'positive':'exact_int_1..2147483647','uint':'exact_int_0..9223372036854775807',
                'prefix':'exact_int_0..128_family_specific','vlan':'exact_int_1..4094',
                'object':'closed_registered_object_128_fields_max','array':'registered_rows_0..1024',
                'strings':'unique_ascii_tokens_0..64_each_1..64_bytes',
                'ifname':'ascii_interface_literal_1..15_bytes','token':'ascii_native_token_1..64_bytes',
                'mac':'lowercase_six_octets','ip':'canonical_ipv4_or_ipv6_literal',
                'network':'canonical_ip_prefix_or_exact_all_default','table':'positive_uint32_or_ascii_alias_1..32',
                'lifetime':'exact_uint32_or_forever','family':'inet_or_inet6','kind':'bridge_or_veth',
                'onoff':'on_or_off','boolean':'exact_bool','hexmark':'lowercase_0x_uint32'
            }[typ]
        rows.append(FieldSpec2(source, tuple(path.split('.')), typ, required, disposition, constraint,
                               'retain_and_validate_' + path, ref))
    for source in ('link', 'link_single'):
        for name, typ, req in (
            ('ifindex','positive',True),('ifname','ifname',True),('flags','strings',True),
            ('mtu','positive',True),('link_type','token',True),('address','mac',True),
            ('broadcast','mac',False),('qdisc','token',False),('operstate','token',False),
            ('linkmode','token',False),('group','token',False),('txqlen','uint',False),
            ('master','positive',False),('link_index','positive',False),('link_netnsid','uint',False),
            ('promiscuity','uint',False),('allmulti','uint',False),('min_mtu','uint',False),
            ('max_mtu','uint',False),('inet6_addr_gen_mode','token',False),
            ('num_tx_queues','positive',False),('num_rx_queues','positive',False),
            ('gso_max_size','uint',False),('gso_max_segs','uint',False),
            ('tso_max_size','uint',False),('tso_max_segs','uint',False),('gro_max_size','uint',False)):
            add(source, name, typ, req, 'identity' if name in ('ifindex','ifname','address','link_index','link_netnsid','master') else 'structural')
        add(source,'linkinfo','object')
        add(source,'linkinfo.info_kind','kind',True)
        add(source,'linkinfo.info_data','object')
        integer_options = '''forward_delay hello_time max_age ageing_time stp_state priority vlan_filtering
            root_port root_path_cost topology_change topology_change_detected vlan_default_pvid
            vlan_stats_enabled vlan_stats_per_port mcast_snooping no_linklocal_learn mcast_vlan_snooping
            mcast_router mcast_query_use_ifaddr mcast_querier mcast_hash_elasticity mcast_hash_max
            mcast_last_member_cnt mcast_startup_query_cnt mcast_last_member_intvl mcast_membership_intvl
            mcast_querier_intvl mcast_query_intvl mcast_query_response_intvl mcast_startup_query_intvl
            mcast_stats_enabled mcast_igmp_version mcast_mld_version nf_call_iptables nf_call_ip6tables
            nf_call_arptables'''.split()
        for name in integer_options:
            add(source,'linkinfo.info_data.'+name,'uint')
        for name in ('vlan_protocol','bridge_id','root_id','group_fwd_mask','group_addr'):
            add(source,'linkinfo.info_data.'+name,'mac' if name == 'group_addr' else 'token')
        for name in ('hello_timer','tcn_timer','topology_change_timer','gc_timer'):
            add(source,'linkinfo.info_data.'+name,'timer',disposition='observed_volatile',constraint='0..86400_seconds_exact_decimal_scale_1..6_or_integer')
    for source in ('bridge_link','bridge_link_basic'):
        for name,typ in (('ifindex','positive'),('ifname','ifname'),('link','ifname'),('flags','strings'),
                         ('mtu','positive'),('master','ifname'),('state','token'),('priority','uint'),('cost','uint')):
            add(source,name,typ,True,'identity' if name in ('ifindex','ifname','master','link') else 'structural')
        # Optional -d options are provisional; every supplied option remains visible.
        for name in ('hairpin','guard','root_block','fastleave','learning','flood','mcast_flood','bcast_flood',
                     'mcast_to_unicast','neigh_suppress','vlan_tunnel','isolated','locked'):
            add(source,name,'onoff')
    for name,typ in (('ifindex','positive'),('ifname','ifname'),('addr_info','array')):
        add('address',name,typ,True,'identity' if name != 'addr_info' else 'structural')
    for name,typ,req in (('family','family',True),('local','ip',True),('prefixlen','prefix',True),
        ('scope','token',True),('broadcast','ip',False),('peer','ip',False),('label','ifname',False),
        ('flags','strings',False),('valid_life_time','lifetime',True),('preferred_life_time','lifetime',True)):
        add('address','addr_info.*.'+name,typ,req,'observed_volatile' if 'life_time' in name else 'structural')
    add('vlan','ifname','ifname',True,'identity'); add('vlan','vlans','array',True)
    for name,typ,req in (('vlan','vlan',True),('vlanEnd','vlan',False),('flags','strings',True)):
        add('vlan','vlans.*.'+name,typ,req)
    for name,typ,req in (('mac','mac',True),('dev','ifname',True),('master','ifname',True),
                         ('vlan','vlan',False),('flags','strings',True),('state','strings',True)):
        add('fdb',name,typ,req)
    for source in ('route4','route6'):
        for name,typ,req in (('dst','network',True),('dev','ifname',True),('table','table',True),
            ('protocol','token',True),('scope','token',True),('type','token',True),('gateway','ip',False),
            ('prefsrc','ip',False),('src','network',False),('metric','uint',False),('flags','strings',False),
            ('pref','token',False)):
            add(source,name,typ,req,'ordered_policy')
    for source in ('rule4','rule6'):
        for name,typ,req in (('priority','uint',True),('src','network',True),('table','table',True),
            ('dst','network',False),('iif','ifname',False),('oif','ifname',False),('fwmark','hexmark',False),
            ('fwmask','hexmark',False),('suppress_prefixlength','prefix',False),('l3mdev','boolean',False),
            ('action','token',False),('protocol','token',False)):
            add(source,name,typ,req,'ordered_policy')
    return tuple(rows)


REGISTRY = _registry()
REGISTRY_DIGEST = c._hash('topology_field_registry_v1', [tuple(getattr(f,k) for k in f.__dataclass_fields__) for f in REGISTRY])
SOURCE_REGISTRY_DIGEST = c._hash('topology_capture_registry_v1', {
    'commands':COMMANDS, 'required_sources_per_namespace':SOURCES,
    'max_document_bytes':1048576, 'max_aggregate_bytes':16777216, 'max_documents':256,
    'max_depth':32, 'max_nodes':65536, 'max_rows':1024, 'max_array':1024,
    'max_string_utf8_bytes':512, 'max_flags':64, 'max_integer_digits':19,
    'decimal_whole_digits':10, 'decimal_fraction_digits':6,
})


@dataclass(frozen=True, slots=True)
class TopologyProfile2(c._Offline2):
    ip_binary_digest: str
    bridge_binary_digest: str
    profile_id: str = 'iproute2-native-topology-v2-provisional-offline-1'
    schema_registry_digest: str = REGISTRY_DIGEST
    source_registry_digest: str = SOURCE_REGISTRY_DIGEST
    acceptance: str = 'provisional_offline_only'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._hex(self.ip_binary_digest); c._hex(self.bridge_binary_digest)
        c._require(self.profile_id == 'iproute2-native-topology-v2-provisional-offline-1' and
                   self.schema_registry_digest == REGISTRY_DIGEST and self.source_registry_digest == SOURCE_REGISTRY_DIGEST and
                   self.acceptance == 'provisional_offline_only',
                   'v2_topology_profile_mismatch')


@dataclass(frozen=True, slots=True)
class FrozenObject2:
    fields: tuple  # Only registered keys, recursively typed values; never an unknown-field bag.

    def get(self, key, default=None):
        return next((v for k,v in self.fields if k == key), default)

    def has(self, key):
        return any(k == key for k,v in self.fields)


def _freeze(value):
    if type(value) is dict:
        return FrozenObject2(tuple((k,_freeze(value[k])) for k in sorted(value)))
    if type(value) is list:
        return tuple(_freeze(v) for v in value)
    return value


def _thaw(value, depth=1, budget=None):
    # Constructors are checked as well as the public byte decoder.
    if budget is None: budget=[0]
    budget[0]+=1
    c._require(depth<=32 and budget[0]<=65536,'v2_topology_field_invalid')
    if type(value) is FrozenObject2:
        c._require(type(value.fields) is tuple and len(value.fields) <= 128, 'v2_topology_field_invalid')
        out = {}
        for item in value.fields:
            c._require(type(item) is tuple and len(item)==2 and type(item[0]) is str and
                       len(item[0])<=512 and item[0] not in out, 'v2_topology_field_invalid')
            out[item[0]] = _thaw(item[1],depth+1,budget)
        return out
    if type(value) is tuple:
        c._require(len(value)<=1024,'v2_topology_field_invalid')
        return [_thaw(v,depth+1,budget) for v in value]
    c._require(type(value) in (str,int,bool,ExactDecimal2), 'v2_topology_field_invalid')
    if type(value) is str: c._require(len(value)<=512,'v2_topology_field_invalid')
    if type(value) is ExactDecimal2: value.__post_init__()
    return value


def _scalar(value, typ):
    ok = False
    if typ.startswith('enum:'):
        ok=type(value) is str and value in typ[5:].split('|')
    elif typ.startswith('flags:'):
        allowed=typ[6:].split('|')
        ok=type(value) is list and len(value)<=64 and all(type(v) is str and v in allowed for v in value) and len(set(value))==len(value)
    elif typ in ('positive','uint','prefix','vlan'):
        lo,hi = {'positive':(1,2**31-1),'uint':(0,2**63-1),'prefix':(0,128),'vlan':(1,4094)}[typ]
        ok = type(value) is int and lo<=value<=hi
    elif typ == 'timer':
        ok = ((type(value) is int and 0<=value<=86400) or
              (type(value) is ExactDecimal2 and 0<=value.millionths<=86400000000))
    elif typ == 'boolean': ok = type(value) is bool
    elif typ == 'strings':
        ok = type(value) is list and len(value)<=64 and all(type(v) is str and re.fullmatch('[A-Za-z0-9_:-]{1,64}',v) for v in value) and len(set(value))==len(value)
    elif typ == 'lifetime': ok = (type(value) is int and 0<=value<=2**32-1) or value == 'forever' and type(value) is str
    elif typ == 'table': ok = type(value) is int and 1<=value<=2**32-1 or type(value) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_-]{0,31}',value) is not None
    elif type(value) is str:
        if typ == 'ifname': ok = re.fullmatch('[A-Za-z0-9_.:-]{1,15}',value) is not None
        elif typ == 'token': ok = re.fullmatch('[A-Za-z0-9_.: /-]{1,64}',value) is not None
        elif typ == 'mac': ok = re.fullmatch('[0-9a-f]{2}(:[0-9a-f]{2}){5}',value) is not None
        elif typ == 'hexmark': ok = re.fullmatch('0x[0-9a-f]{1,8}',value) is not None
        elif typ == 'family': ok = value in ('inet','inet6')
        elif typ == 'kind': ok = value in ('bridge','veth')
        elif typ == 'onoff': ok = value in ('on','off')
        elif typ in ('ip','network'):
            try:
                ok = value in ('default','all') if typ == 'network' and value in ('default','all') else str(ipaddress.ip_address(value) if typ == 'ip' else ipaddress.ip_network(value,strict=True)) == value
            except ValueError: ok = False
    c._require(bool(ok), 'v2_topology_field_invalid')


def validate_rows2(source, rows):
    c._require(source in dict(COMMANDS) and type(rows) is list and len(rows)<=1024, 'v2_topology_source_invalid')
    specs = {r.path:r for r in REGISTRY if r.source==source}
    def obj(value, prefix=()):
        c._require(type(value) is dict, 'v2_topology_schema_invalid')
        direct = {p[-1]:r for p,r in specs.items() if p[:-1]==prefix}
        c._require(set(value)<=set(direct), 'v2_topology_unknown_field')
        c._require(all(k in value for k,r in direct.items() if r.required), 'v2_topology_field_missing')
        for key,v in value.items():
            r=direct[key]; path=prefix+(key,)
            if r.value_type=='object': obj(v,path)
            elif r.value_type=='array':
                c._require(type(v) is list and len(v)<=1024,'v2_topology_schema_invalid')
                for row in v: obj(row,path+('*',))
            else: _scalar(v,r.value_type)
    for row in rows:
        obj(row)
        if source in ('link','link_single'):
            info=row.get('linkinfo',{})
            c._require(not info.get('info_data') or info.get('info_kind')=='bridge','v2_topology_kind_unproven')
        if source=='address':
            for a in row['addr_info']:
                version=4 if a['family']=='inet' else 6
                c._require(ipaddress.ip_address(a['local']).version==version and a['prefixlen']<=(32 if version==4 else 128),'v2_topology_family_mismatch')
                for key in ('peer','broadcast'):
                    if key in a: c._require(ipaddress.ip_address(a[key]).version==version,'v2_topology_family_mismatch')
        if source.startswith(('route','rule')):
            version=int(source[-1])
            for key in ('dst','src','gateway','prefsrc'):
                if key in row and row[key] not in ('all','default'):
                    actual=ipaddress.ip_network(row[key],strict=False).version
                    c._require(actual==version,'v2_topology_family_mismatch')
            if source.startswith('rule'):
                c._require(('fwmark' in row)==('fwmask' in row),'v2_topology_selector_incomplete')
                if 'suppress_prefixlength' in row: c._require(row['suppress_prefixlength']<=(32 if version==4 else 128),'v2_topology_field_invalid')
        if source=='vlan':
            for v in row['vlans']:
                c._require(v.get('vlanEnd',v['vlan'])>=v['vlan'],'v2_topology_field_invalid')
    return tuple(_freeze(row) for row in rows)


def validate_frozen_rows2(source, rows):
    c._require(type(rows) is tuple and len(rows)<=1024, 'v2_topology_source_invalid')
    return validate_rows2(source,[_thaw(r) for r in rows])
