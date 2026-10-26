"""Pure offline topology stages. No OS collector, policy acceptance or authority."""
from dataclasses import dataclass, field
import hashlib
from . import native_v2_contracts as c
from . import native_v2_topology_schema as s
from .native_v2_topology_json import bounded_topology_json2

MAX_DOCUMENTS = 256
MAX_AGGREGATE_BYTES = 16 * 1048576


def _tuple(value, cls, maximum=256):
    c._require(type(value) is tuple and len(value)<=maximum,'v2_topology_collection_invalid')
    for row in value: c._typed(row,cls)


def _unique(values):
    c._require(len(values)==len(set(values)),'v2_topology_identity_collision')


@dataclass(frozen=True, slots=True)
class NamespaceRole2(c._Offline2):
    role: str
    key: c.NamespaceKey2
    namespace_reference_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._enum(self.role,('host','runner','target'))
        c._typed(self.key,c.NamespaceKey2); c._hex(self.namespace_reference_digest)


@dataclass(frozen=True, slots=True)
class CaptureDescriptor2(c._Offline2):
    namespace: c.NamespaceKey2
    source: str
    profile_digest: str
    binary_digest: str
    capture_uuid: str
    context_uuid: str
    approval_digest: str
    writer_epoch_uuid: str
    raw_sha256: str
    raw_byte_count: int
    provenance_reference_digest: str
    exit_status: int = 0
    transport: str = 'offline_supplied_bytes_no_completeness_attestation'

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.namespace,c.NamespaceKey2)
        c._enum(self.source,tuple(dict(s.COMMANDS)))
        for value in (self.profile_digest,self.binary_digest,self.approval_digest,self.raw_sha256,
                      self.provenance_reference_digest): c._hex(value)
        for value in (self.capture_uuid,self.context_uuid,self.writer_epoch_uuid): c._uuid(value)
        c._integer(self.raw_byte_count,1,1048576); c._integer(self.exit_status,0,255)
        c._require(self.transport=='offline_supplied_bytes_no_completeness_attestation','v2_topology_capture_invalid')

    @property
    def argv(self): return dict(s.COMMANDS)[self.source]

    @property
    def extent(self):
        return 'single_link' if self.source=='link_single' else 'basic_ports' if self.source=='bridge_link_basic' else 'namespace_source'


@dataclass(frozen=True, slots=True)
class DecodedTopologySource2(c._Offline2):
    profile: s.TopologyProfile2
    descriptor: CaptureDescriptor2
    rows: tuple[s.FrozenObject2, ...]
    raw_text: str = field(repr=False)
    stage: str = field(default='source_decoded',init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.profile,s.TopologyProfile2)
        c._typed(self.descriptor,CaptureDescriptor2)
        d=self.descriptor
        expected=self.profile.bridge_binary_digest if d.argv[0]=='bridge' else self.profile.ip_binary_digest
        c._require(d.profile_digest==self.profile.digest and d.binary_digest==expected,'v2_topology_profile_mismatch')
        c._require(d.exit_status==0,'v2_topology_capture_failed')
        c._require(type(self.raw_text) is str and 0<len(self.raw_text)<=1048576,'v2_topology_capture_invalid')
        try: raw=self.raw_text.encode('utf-8',errors='strict')
        except UnicodeEncodeError: raise c.ContractViolation2('v2_topology_capture_invalid') from None
        c._require(len(raw)==d.raw_byte_count and hashlib.sha256(raw).hexdigest()==d.raw_sha256,'v2_topology_capture_mismatch')
        s.validate_frozen_rows2(d.source,self.rows)
        c._require(self.rows==s.validate_rows2(d.source,bounded_topology_json2(raw)),'v2_topology_capture_mismatch')

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('decoded_topology_source', (self.profile.digest,self.descriptor.digest))


def decode_topology_source2(raw, profile, descriptor):
    c._typed(profile,s.TopologyProfile2); c._typed(descriptor,CaptureDescriptor2)
    c._require(type(raw) is bytes and len(raw)==descriptor.raw_byte_count and
               hashlib.sha256(raw).hexdigest()==descriptor.raw_sha256,'v2_topology_capture_mismatch')
    rows=s.validate_rows2(descriptor.source,bounded_topology_json2(raw))
    return DecodedTopologySource2(profile,descriptor,rows,raw.decode('utf-8'))


@dataclass(frozen=True, slots=True)
class LinkReference2(c._Offline2):
    namespace: c.NamespaceKey2
    ifindex: int

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.namespace,c.NamespaceKey2); c._integer(self.ifindex,1,2**31-1)


@dataclass(frozen=True, slots=True)
class PeerWitness2(c._Offline2):
    """Independent OFFLINE namespace/NSID mapping reference, not OS attestation."""
    first: LinkReference2
    second: LinkReference2
    first_observed_nsid: int
    second_observed_nsid: int
    reference_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.first,LinkReference2); c._typed(self.second,LinkReference2)
        c._integer(self.first_observed_nsid,0,2**31-1); c._integer(self.second_observed_nsid,0,2**31-1)
        c._hex(self.reference_digest)
        c._require(self.first.namespace!=self.second.namespace,'v2_topology_peer_invalid')


@dataclass(frozen=True, slots=True)
class TableMapping2(c._Offline2):
    namespace: c.NamespaceKey2
    token: str | int
    number: int
    reference_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.namespace,c.NamespaceKey2)
        s._scalar(self.token,'table'); c._integer(self.number,1,2**32-1); c._hex(self.reference_digest)
        c._require(type(self.token) is not int or self.token==self.number,'v2_topology_table_invalid')


@dataclass(frozen=True, slots=True)
class RouteTableReference2(c._Offline2):
    namespace: c.NamespaceKey2
    family: int
    native_token: str | int
    number: int
    mapping_reference_digest: str

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.namespace,c.NamespaceKey2)
        c._require(type(self.family) is int and self.family in (4,6),'v2_topology_family_mismatch')
        s._scalar(self.native_token,'table'); c._integer(self.number,1,2**32-1)
        c._hex(self.mapping_reference_digest)


@dataclass(frozen=True, slots=True)
class ResolvedObjectReference2(c._Offline2):
    relation: str
    source_capture_digest: str
    source_ordinal: int
    nested_ordinal: int | None
    target: LinkReference2 | RouteTableReference2

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.relation,('address_link','vlan_link','fdb_dev','fdb_master','route_dev',
                              'route_table','rule_table','rule_iif','rule_oif'))
        c._hex(self.source_capture_digest); c._integer(self.source_ordinal,0,1023)
        if self.nested_ordinal is not None: c._integer(self.nested_ordinal,0,1023)
        cls=RouteTableReference2 if self.relation in ('route_table','rule_table') else LinkReference2
        c._typed(self.target,cls)


@dataclass(frozen=True, slots=True)
class TopologyCapturePlan2(c._Offline2):
    """Independently pinned fixture coverage/references. Never a capture permit."""
    profile: s.TopologyProfile2
    context_uuid: str
    approval_digest: str
    writer_epoch_uuid: str
    namespaces: tuple[NamespaceRole2, ...]
    captures: tuple[CaptureDescriptor2, ...]
    peer_witnesses: tuple[PeerWitness2, ...]
    table_mappings: tuple[TableMapping2, ...]

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.profile,s.TopologyProfile2)
        c._uuid(self.context_uuid); c._uuid(self.writer_epoch_uuid); c._hex(self.approval_digest)
        _tuple(self.namespaces,NamespaceRole2,3); _tuple(self.captures,CaptureDescriptor2)
        _tuple(self.peer_witnesses,PeerWitness2); _tuple(self.table_mappings,TableMapping2)
        _unique([n.role for n in self.namespaces]); _unique([n.key for n in self.namespaces])
        keys=tuple(n.key for n in self.namespaces)
        _unique([d.capture_uuid for d in self.captures]); _unique([(d.namespace,d.source) for d in self.captures])
        c._require(len({(k.host_boot_uuid,k.reader_session_uuid) for k in keys})<=1,'v2_topology_namespace_mismatch')
        _unique([k.netns_inode for k in keys])
        for d in self.captures:
            c._require(d.namespace in keys and d.profile_digest==self.profile.digest and
                       (d.context_uuid,d.approval_digest,d.writer_epoch_uuid)==
                       (self.context_uuid,self.approval_digest,self.writer_epoch_uuid),'v2_topology_provenance_mismatch')
        for w in self.peer_witnesses:
            c._require(w.first.namespace in keys and w.second.namespace in keys,'v2_topology_namespace_mismatch')
        _unique([ref for w in self.peer_witnesses for ref in (w.first,w.second)])
        nsid_targets={}
        for w in self.peer_witnesses:
            for a,b,nsid in ((w.first,w.second,w.first_observed_nsid),(w.second,w.first,w.second_observed_nsid)):
                key=(a.namespace,nsid)
                c._require(key not in nsid_targets or nsid_targets[key]==b.namespace,'v2_topology_peer_invalid')
                nsid_targets[key]=b.namespace
        _unique([(t.namespace,type(t.token).__name__,t.token) for t in self.table_mappings])
        for t in self.table_mappings: c._require(t.namespace in keys,'v2_topology_namespace_mismatch')


@dataclass(frozen=True, slots=True)
class _SourceRecord2(c._Offline2):
    source: DecodedTopologySource2
    ordinal: int

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        # Exact immutable source already validates bytes/schema on construction;
        # reparsing its entire inventory once per row would be quadratic.
        c._require(type(self.source) is DecodedTopologySource2,'v2_type_invalid')
        c._integer(self.ordinal,0,len(self.source.rows)-1)
        allowed={Link2:('link','link_single'),Address2:('address',),BridgePort2:('bridge_link','bridge_link_basic'),
                 VlanRow2:('vlan',),FdbRow2:('fdb',),Route2:('route4','route6'),PolicyRule2:('rule4','rule6')}
        c._require(self.source.descriptor.source in allowed.get(type(self),()),'v2_topology_source_invalid')

    @property
    def namespace(self): return self.source.descriptor.namespace

    @property
    def attributes(self): return self.source.rows[self.ordinal]

    @property
    def provenance(self): return (self.source.descriptor.digest,self.ordinal)


@dataclass(frozen=True, slots=True)
class Link2(_SourceRecord2):
    @property
    def reference(self): return LinkReference2(self.namespace,self.attributes.get('ifindex'))

    @property
    def ifname(self): return self.attributes.get('ifname')

    @property
    def kind(self):
        info=self.attributes.get('linkinfo')
        return info.get('info_kind') if info is not None else None


@dataclass(frozen=True, slots=True)
class Address2(_SourceRecord2):
    address_ordinal: int

    def __post_init__(self):
        _SourceRecord2.__post_init__(self)
        c._integer(self.address_ordinal,0,len(self.attributes.get('addr_info'))-1)

    @property
    def address(self): return self.attributes.get('addr_info')[self.address_ordinal]


@dataclass(frozen=True, slots=True)
class BridgePort2(_SourceRecord2):
    pass


@dataclass(frozen=True, slots=True)
class VlanRow2(_SourceRecord2):
    vlan_ordinal: int

    def __post_init__(self):
        _SourceRecord2.__post_init__(self); c._integer(self.vlan_ordinal,0,len(self.attributes.get('vlans'))-1)

    @property
    def vlan(self): return self.attributes.get('vlans')[self.vlan_ordinal]


@dataclass(frozen=True, slots=True)
class FdbRow2(_SourceRecord2):
    pass


@dataclass(frozen=True, slots=True)
class Route2(_SourceRecord2):
    pass


@dataclass(frozen=True, slots=True)
class PolicyRule2(_SourceRecord2):
    pass


@dataclass(frozen=True, slots=True)
class Attachment2(c._Offline2):
    """Reserved unobserved surface, cannot manufacture absence of OS attachments."""
    namespace: c.NamespaceKey2
    surface: str
    status: str = 'unobserved'

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.namespace,c.NamespaceKey2)
        c._enum(self.surface,('tc','xdp','flowtable','offloads','sysctl','external_fds','nft_hooks'))
        c._require(self.status=='unobserved','v2_topology_attachment_unproven')


@dataclass(frozen=True, slots=True)
class Namespace2(c._Offline2):
    identity: NamespaceRole2
    sources: tuple[DecodedTopologySource2, ...]
    links: tuple[Link2, ...] = field(init=False)
    addresses: tuple[Address2, ...] = field(init=False)
    ports: tuple[BridgePort2, ...] = field(init=False)
    vlans: tuple[VlanRow2, ...] = field(init=False)
    fdb: tuple[FdbRow2, ...] = field(init=False)
    routes: tuple[Route2, ...] = field(init=False)
    rules: tuple[PolicyRule2, ...] = field(init=False)
    attachments: tuple[Attachment2, ...] = field(init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.identity,NamespaceRole2)
        _tuple(self.sources,DecodedTopologySource2)
        c._require(all(d.descriptor.namespace==self.identity.key for d in self.sources),'v2_topology_namespace_mismatch')
        _unique([d.descriptor.source for d in self.sources])
        groups={name:[] for name in ('links','addresses','ports','vlans','fdb','routes','rules')}
        for d in self.sources:
            source=d.descriptor.source
            for i,row in enumerate(d.rows):
                if source in ('link','link_single'): groups['links'].append(Link2(d,i))
                elif source=='address': groups['addresses'].extend(Address2(d,i,j) for j in range(len(row.get('addr_info'))))
                elif source in ('bridge_link','bridge_link_basic'): groups['ports'].append(BridgePort2(d,i))
                elif source=='vlan': groups['vlans'].extend(VlanRow2(d,i,j) for j in range(len(row.get('vlans'))))
                elif source=='fdb': groups['fdb'].append(FdbRow2(d,i))
                elif source.startswith('route'): groups['routes'].append(Route2(d,i))
                elif source.startswith('rule'): groups['rules'].append(PolicyRule2(d,i))
        for name,values in groups.items(): object.__setattr__(self,name,tuple(values))
        object.__setattr__(self,'attachments',tuple(Attachment2(self.identity.key,kind) for kind in
            ('tc','xdp','flowtable','offloads','sysctl','external_fds','nft_hooks')))


def _coverage(sources,plan):
    _tuple(sources,DecodedTopologySource2,MAX_DOCUMENTS); c._typed(plan,TopologyCapturePlan2)
    c._require(sum(d.descriptor.raw_byte_count for d in sources)<=MAX_AGGREGATE_BYTES,'v2_topology_aggregate_limit')
    _unique([d.descriptor.capture_uuid for d in sources])
    _unique([(d.descriptor.namespace,d.descriptor.source) for d in sources])
    for d in sources:
        c._require(d.profile==plan.profile and d.descriptor in plan.captures,'v2_topology_source_reference_mismatch')


@dataclass(frozen=True, slots=True)
class NormalizedTopology2(c._Offline2):
    plan: TopologyCapturePlan2
    sources: tuple[DecodedTopologySource2, ...]
    namespaces: tuple[Namespace2, ...] = field(init=False)
    stage: str = field(default='topology_normalized',init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self); _coverage(self.sources,self.plan)
        object.__setattr__(self,'namespaces',tuple(Namespace2(n,tuple(d for d in self.sources if d.descriptor.namespace==n.key)) for n in self.plan.namespaces))

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('normalized_topology', (self.plan.digest,tuple(d.digest for d in self.sources)))


def normalize_topology2(sources,plan):
    return NormalizedTopology2(plan,sources)


def decode_topology_documents2(documents,profile,plan):
    """Batch byte/count caps checked before parsing any document; no transport I/O."""
    c._typed(profile,s.TopologyProfile2); c._typed(plan,TopologyCapturePlan2)
    c._require(profile==plan.profile,'v2_topology_profile_mismatch')
    c._require(type(documents) is tuple and len(documents)<=MAX_DOCUMENTS,'v2_topology_documents_limit')
    total=0
    for item in documents:
        c._require(type(item) is tuple and len(item)==2,'v2_topology_capture_invalid')
        raw,d=item; c._typed(d,CaptureDescriptor2)
        c._require(type(raw) is bytes and 0<len(raw)<=1048576,'v2_topology_json_size_invalid')
        total+=len(raw)
        c._require(total<=MAX_AGGREGATE_BYTES,'v2_topology_aggregate_limit')
        c._require(d in plan.captures,'v2_topology_source_reference_mismatch')
    return tuple(decode_topology_source2(raw,profile,d) for raw,d in documents)


def _join_issues(normalized):
    plan=normalized.plan; issues=[]; edges=[]; references=[]
    def reference(record,relation,target,nested=None):
        references.append(ResolvedObjectReference2(relation,record.source.descriptor.digest,
                                                   record.ordinal,nested,target))
    def issue(code):
        if code not in issues: issues.append(code)
    if {n.identity.role for n in normalized.namespaces}!={'host','runner','target'}: issue('namespace_coverage_missing')
    if {d.descriptor for d in normalized.sources}!=set(plan.captures): issue('source_coverage_missing')
    by_ref={}
    for n in normalized.namespaces:
        ns=n.identity.key
        source_by_kind={d.descriptor.source:d for d in n.sources}
        if not set(s.SOURCES)<=set(source_by_kind): issue('source_coverage_missing')
        if any(d.descriptor.extent!='namespace_source' for d in n.sources): issue('partial_capture')
        indices=[l.reference.ifindex for l in n.links]; names=[l.ifname for l in n.links]
        if len(set(indices))!=len(indices) or len(set(names))!=len(names):
            issue('link_identity_ambiguous'); continue
        links={l.reference.ifindex:l for l in n.links}; named={l.ifname:l for l in n.links}
        if sum('LOOPBACK' in l.attributes.get('flags') for l in n.links)!=1:
            issue('loopback_identity_unproven')
        for l in n.links: by_ref[l.reference]=l
        for l in n.links:
            master=l.attributes.get('master')
            if master is not None and (master not in links or links[master].kind!='bridge'): issue('master_unproven')
        address_source=source_by_kind.get('address')
        if address_source:
            ids=[]
            for row in address_source.rows:
                idx=row.get('ifindex'); ids.append(idx)
                if idx not in links or links[idx].ifname!=row.get('ifname'): issue('address_link_unproven')
            if len(set(ids))!=len(ids) or set(ids)!=set(links): issue('address_coverage_missing')
            for a in n.addresses:
                idx=a.attributes.get('ifindex')
                if idx in links and links[idx].ifname==a.attributes.get('ifname'):
                    reference(a,'address_link',links[idx].reference,a.address_ordinal)
            address_keys=[(a.attributes.get('ifindex'),a.address.get('family'),a.address.get('local'),a.address.get('prefixlen')) for a in n.addresses]
            if len(address_keys)!=len(set(address_keys)): issue('address_identity_ambiguous')
        port_ids=[]
        for p in n.ports:
            a=p.attributes; idx=a.get('ifindex'); port_ids.append(idx)
            port=links.get(idx); master=named.get(a.get('master'))
            if (port is None or port.ifname!=a.get('ifname') or master is None or master.kind!='bridge' or
                port.attributes.get('master')!=master.reference.ifindex): issue('bridge_membership_unproven')
            else: edges.append(('bridge_member',port.reference,master.reference,p.provenance))
        expected_ports={idx for idx,l in links.items() if l.attributes.has('master')}
        if len(port_ids)!=len(set(port_ids)) or set(port_ids)!=expected_ports: issue('bridge_membership_unproven')
        vlan_keys=set()
        for v in n.vlans:
            link=named.get(v.attributes.get('ifname')); row=v.vlan
            if link is None or (link.kind!='bridge' and not link.attributes.has('master')): issue('vlan_link_unproven')
            else: reference(v,'vlan_link',link.reference,v.vlan_ordinal)
            for vlan in range(row.get('vlan'),row.get('vlanEnd',row.get('vlan'))+1):
                key=(v.attributes.get('ifname'),vlan)
                if key in vlan_keys: issue('vlan_identity_ambiguous')
                vlan_keys.add(key)
        fdb_keys=set()
        for f in n.fdb:
            a=f.attributes; link=named.get(a.get('dev')); master=named.get(a.get('master'))
            if link is None or master is None or master.kind!='bridge' or (link!=master and link.attributes.get('master')!=master.reference.ifindex): issue('fdb_link_unproven')
            if a.has('vlan') and (a.get('dev'),a.get('vlan')) not in vlan_keys: issue('fdb_vlan_unproven')
            if link is not None: reference(f,'fdb_dev',link.reference)
            if master is not None and master.kind=='bridge': reference(f,'fdb_master',master.reference)
            key=(a.get('dev'),a.get('master'),a.get('mac'),a.get('vlan'))
            if key in fdb_keys: issue('fdb_identity_ambiguous')
            fdb_keys.add(key)
        tables={t.token:t for t in plan.table_mappings if t.namespace==ns}
        for r in (*n.routes,*n.rules):
            a=r.attributes
            if a.get('table') not in tables: issue('table_reference_unproven')
            else:
                mapping=tables[a.get('table')]
                reference(r,'route_table' if type(r) is Route2 else 'rule_table',
                          RouteTableReference2(ns,int(r.source.descriptor.source[-1]),mapping.token,
                                               mapping.number,mapping.reference_digest))
            for key in ('dev','iif','oif'):
                if a.has(key) and a.get(key) not in named: issue('route_link_unproven')
                elif a.has(key):
                    reference(r,'route_dev' if key=='dev' else 'rule_'+key,named[a.get(key)].reference)
        # Source order is preserved, including equal priorities; policy ambiguity is V2-04.
    used=set()
    for w in plan.peer_witnesses:
        a=by_ref.get(w.first); b=by_ref.get(w.second)
        if a is None or b is None: issue('peer_identity_unproven'); continue
        if not (a.kind==b.kind=='veth' and a.attributes.get('link_index')==b.reference.ifindex and
                b.attributes.get('link_index')==a.reference.ifindex and
                a.attributes.get('link_netnsid')==w.first_observed_nsid and
                b.attributes.get('link_netnsid')==w.second_observed_nsid): issue('peer_identity_unproven')
        else:
            used.update((a.reference,b.reference)); edges.append(('veth_peer',a.reference,b.reference,w.reference_digest))
    for ref,l in by_ref.items():
        if l.kind=='veth' and ref not in used: issue('peer_identity_unproven')
    return tuple(issues),tuple(edges),tuple(references)


@dataclass(frozen=True, slots=True)
class TopologyEnvelope2(c._Offline2):
    normalized: NormalizedTopology2
    stage: str = field(init=False)
    reason: str = field(init=False)
    uncertainty_reasons: tuple[str, ...] = field(init=False)
    joins: tuple = field(init=False)
    resolved_references: tuple[ResolvedObjectReference2, ...] = field(init=False)
    isolation_verified: bool = field(default=False,init=False)
    management_policy_verified: bool = field(default=False,init=False)
    measurement_verified: bool = field(default=False,init=False)
    provenance_authentication: str = field(default='unproven_offline_references',init=False)
    continuity: str = field(default='snapshots_only_not_atomic',init=False)
    limitations: tuple[str, ...] = field(default=(
        'provisional_schemas', 'capture_completeness_not_attested',
        'os_namespace_witnesses_not_authenticated', 'attachments_config_fds_unobserved',
        'writer_control_unproven', 'management_policy_not_validated',
    ),init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self); c._typed(self.normalized,NormalizedTopology2)
        issues,edges,references=_join_issues(self.normalized)
        object.__setattr__(self,'uncertainty_reasons',issues)
        object.__setattr__(self,'joins',edges)
        object.__setattr__(self,'resolved_references',references)
        object.__setattr__(self,'stage','topology_unproven' if issues else 'topology_complete')
        object.__setattr__(self,'reason',issues[0] if issues else 'offline_source_structure_complete')

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('topology_envelope',(self.normalized.digest,self.stage,self.uncertainty_reasons))


def complete_topology2(normalized):
    return TopologyEnvelope2(normalized)


def compare_topology_snapshots2(candidate, pinned):
    """Exact unchanged transition only; no volatile erasure or policy permission."""
    c._typed(candidate,TopologyEnvelope2); c._typed(pinned,TopologyEnvelope2)
    c._require(candidate.stage==pinned.stage=='topology_complete','v2_topology_incomplete')
    a,b=candidate.normalized,pinned.normalized
    c._require(a.plan.profile==b.plan.profile and a.plan.namespaces==b.plan.namespaces and
               (a.plan.context_uuid,a.plan.approval_digest,a.plan.writer_epoch_uuid,a.plan.peer_witnesses,a.plan.table_mappings)==
               (b.plan.context_uuid,b.plan.approval_digest,b.plan.writer_epoch_uuid,b.plan.peer_witnesses,b.plan.table_mappings),
               'v2_topology_identity_changed')
    # Compare all typed fields, optional presence and row order, not capture UUIDs/hashes.
    def rows(value):
        return tuple((n.identity,tuple((d.descriptor.source,d.rows) for d in n.sources)) for n in value.namespaces)
    c._require(rows(a)==rows(b),'v2_topology_snapshot_changed')
    return candidate
