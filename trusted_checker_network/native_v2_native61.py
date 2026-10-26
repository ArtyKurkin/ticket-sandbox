"""Diagnostic-only native topology processing with named, UNATTESTED capture scopes.

No NamespaceKey/FD/NSID witness is invented. No conversion to V2-03/V2-04 types,
no ownership, approved native semantics or OS/physical measurement acceptance.
"""
from dataclasses import dataclass, field
import hashlib
import re

from . import native_v2_contracts as c
from . import native_v2_topology_schema as old
from . import native_v2_native61_schema as s
from . import native_v2_management as management


def _scope(value):
    c._require(type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,64}',value) is not None,
               'v2_native61_scope_invalid')


@dataclass(frozen=True, slots=True)
class NativeSourceReference61(c._Offline2):
    scope_label: str
    source: str
    artifact_path: str
    archive_reference_digest: str
    raw_sha256: str
    raw_byte_count: int
    exact_argv: str = 'unrecorded'
    timestamps: str = 'unrecorded'
    namespace_identity: str = 'unobserved'
    os_principal: str = 'unobserved'

    def __post_init__(self):
        c._Offline2.__post_init__(self); _scope(self.scope_label); c._enum(self.source,s.SOURCES)
        c._require(type(self.artifact_path) is str and
            self.artifact_path==self.scope_label+'/'+self.source+'.json','v2_native61_reference_invalid')
        c._hex(self.archive_reference_digest);c._hex(self.raw_sha256)
        c._integer(self.raw_byte_count,1,1048576)
        for actual,expected in ((self.exact_argv,'unrecorded'),(self.timestamps,'unrecorded'),
                (self.namespace_identity,'unobserved'),(self.os_principal,'unobserved')):
            c._require(type(actual) is str and actual==expected,'v2_native61_attestation_forbidden')

    @property
    def nominal_argv(self):
        return dict(s.NOMINAL_ARGV)[self.source]


@dataclass(frozen=True, slots=True)
class DecodedNativeSource61(c._Offline2):
    profile: s.NativeTopologyProfile61
    reference: NativeSourceReference61
    rows: tuple[old.FrozenObject2, ...]
    raw_text: str = field(repr=False)
    stage: str = field(default='native_format_decoded_diagnostic_only',init=False)
    management_policy_verified: bool = field(default=False,init=False)
    isolation_verified: bool = field(default=False,init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._typed(self.profile,s.NativeTopologyProfile61)
        c._typed(self.reference,NativeSourceReference61)
        c._require(type(self.raw_text) is str and 0<len(self.raw_text)<=1048576,'v2_native61_raw_invalid')
        try: raw=self.raw_text.encode('utf-8',errors='strict')
        except UnicodeEncodeError: raise c.ContractViolation2('v2_native61_raw_invalid') from None
        c._require(len(raw)==self.reference.raw_byte_count and hashlib.sha256(raw).hexdigest()==
            self.reference.raw_sha256,'v2_native61_reference_mismatch')
        c._require(type(self.rows) is tuple and len(self.rows)<=1024,'v2_native61_rows_invalid')
        # Validate supplied typed rows as well (Python bool == int must not bypass types).
        s.validate_native61_rows(self.reference.source,[old._thaw(row) for row in self.rows])
        # Rebuild from bounded ORIGINAL bytes; constructors cannot swap a typed row.
        c._require(self.rows==s.decode_native61_rows(raw,self.reference.source),'v2_native61_reference_mismatch')

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('decoded_native61',(self.profile.digest,self.reference.digest))


def decode_native_source61(raw,profile,reference):
    c._typed(profile,s.NativeTopologyProfile61);c._typed(reference,NativeSourceReference61)
    c._require(type(raw) is bytes and len(raw)==reference.raw_byte_count and
        hashlib.sha256(raw).hexdigest()==reference.raw_sha256,'v2_native61_reference_mismatch')
    return DecodedNativeSource61(profile,reference,s.decode_native61_rows(raw,reference.source),raw.decode('utf-8'))


def decode_native_documents61(documents,profile):
    c._typed(profile,s.NativeTopologyProfile61)
    c._require(type(documents) is tuple and len(documents)<=256,'v2_native61_documents_limit')
    total=0; keys=[]
    for item in documents:
        c._require(type(item) is tuple and len(item)==2,'v2_native61_document_invalid')
        raw,reference=item;c._typed(reference,NativeSourceReference61)
        c._require(type(raw) is bytes and 0<len(raw)<=1048576,'v2_native61_raw_invalid')
        total+=len(raw);c._require(total<=16777216,'v2_native61_aggregate_limit')
        keys.append((reference.scope_label,reference.source))
    c._require(len(keys)==len(set(keys)),'v2_native61_duplicate_source')
    return tuple(decode_native_source61(raw,profile,reference) for raw,reference in documents)


@dataclass(frozen=True, slots=True)
class DiagnosticJoin61(c._Offline2):
    scope_label: str
    source: str
    row_ordinal: int
    relation: str
    target_ifindex: int
    namespace_binding: str = 'unproven_capture_scope_only'

    def __post_init__(self):
        c._Offline2.__post_init__(self);_scope(self.scope_label);c._enum(self.source,s.SOURCES)
        c._integer(self.row_ordinal,0,1023);c._integer(self.target_ifindex,1,2**31-1)
        c._enum(self.relation,('address_link','bridge_member','vlan_link','fdb_interface','fdb_bridge','route_device'))
        c._enum(self.namespace_binding,('unproven_capture_scope_only',))


@dataclass(frozen=True, slots=True)
class PeerIndexCandidate61(c._Offline2):
    first_scope: str
    first_ifindex: int
    first_nsid: int
    second_scope: str
    second_ifindex: int
    second_nsid: int
    status: str = 'unproven_no_namespace_fd_nsid_witness'

    def __post_init__(self):
        c._Offline2.__post_init__(self);_scope(self.first_scope);_scope(self.second_scope)
        c._integer(self.first_ifindex,1,2**31-1);c._integer(self.second_ifindex,1,2**31-1)
        c._integer(self.first_nsid,0,2**32-1);c._integer(self.second_nsid,0,2**32-1)
        c._enum(self.status,('unproven_no_namespace_fd_nsid_witness',))


def _diagnose(sources,scope_labels):
    joins=[]; candidates=[]; issues=[]; fdb_classes=[]; coverage=[]; veths=[]
    def issue(reason):
        if reason not in issues: issues.append(reason)
    for scope in scope_labels:
        documents={d.reference.source:d for d in sources if d.reference.scope_label==scope}
        for source in s.SOURCES:
            if source not in documents: coverage.append((scope,source))
        link_doc=documents.get('link')
        if link_doc is None:
            issue('link_source_missing');continue
        rows=link_doc.rows
        indices=[row.get('ifindex') for row in rows];names=[row.get('ifname') for row in rows]
        if len(set(indices))!=len(indices) or len(set(names))!=len(names):
            issue('local_link_identity_ambiguous');continue
        indexed={row.get('ifindex'):row for row in rows};named={row.get('ifname'):row for row in rows}
        def kind(row):
            info=row.get('linkinfo');return info.get('info_kind') if info is not None else None
        for row in rows:
            if row.has('master'):
                master=named.get(row.get('master'))
                if master is None or kind(master)!='bridge':issue('master_join_unproven')
            if kind(row)=='veth':veths.append((scope,row))
        def join(source,ordinal,relation,row):
            joins.append(DiagnosticJoin61(scope,source,ordinal,relation,row.get('ifindex')))
        address_doc=documents.get('address')
        if address_doc is not None:
            seen=[]
            for ordinal,row in enumerate(address_doc.rows):
                index=row.get('ifindex');seen.append(index);link=indexed.get(index)
                if link is None or link.get('ifname')!=row.get('ifname'):
                    issue('address_join_unproven');continue
                join('address',ordinal,'address_link',link)
                for key,value in row.fields:
                    if key!='addr_info' and link.has(key) and link.get(key)!=value:issue('address_link_fields_conflict')
            if len(set(seen))!=len(seen) or set(seen)!=set(indexed):issue('address_coverage_incomplete')
        port_doc=documents.get('bridge_link')
        if port_doc is not None:
            port_ids=[]
            for ordinal,port in enumerate(port_doc.rows):
                index=port.get('ifindex');port_ids.append(index);link=indexed.get(index);master=named.get(port.get('master'))
                if (link is None or link.get('ifname')!=port.get('ifname') or master is None or
                    kind(master)!='bridge' or link.get('master')!=port.get('master')):
                    issue('bridge_join_unproven');continue
                join('bridge_link',ordinal,'bridge_member',master)
                for key in ('flags','mtu'):
                    if link.get(key)!=port.get(key):issue('bridge_link_fields_conflict')
                slave=link.get('linkinfo').get('info_slave_data')
                for key,value in port.fields:
                    if slave.has(key) and slave.get(key)!=value:issue('bridge_option_fields_conflict')
            if len(set(port_ids))!=len(port_ids) or set(port_ids)!={row.get('ifindex') for row in rows if row.has('master')}:
                issue('bridge_membership_incomplete')
        vlans=set();vlan_doc=documents.get('bridge_vlan')
        if vlan_doc is not None:
            for ordinal,row in enumerate(vlan_doc.rows):
                link=named.get(row.get('ifname'))
                if link is None or (kind(link)!='bridge' and not link.has('master')):issue('vlan_join_unproven')
                else:join('bridge_vlan',ordinal,'vlan_link',link)
                for vlan in row.get('vlans'):
                    key=(row.get('ifname'),vlan.get('vlan'))
                    if key in vlans:issue('vlan_membership_ambiguous')
                    vlans.add(key)
        fdb_doc=documents.get('bridge_fdb')
        if fdb_doc is not None:
            seen=set()
            for ordinal,row in enumerate(fdb_doc.rows):
                link=named.get(row.get('ifname'))
                if link is None:issue('fdb_interface_unproven');continue
                join('bridge_fdb',ordinal,'fdb_interface',link)
                if row.has('master'):
                    master=named.get(row.get('master'))
                    category='bridge_master_entry'
                    if master is None or kind(master)!='bridge' or not (link==master or link.get('master')==master.get('ifname')):
                        issue('fdb_bridge_unproven')
                    else:join('bridge_fdb',ordinal,'fdb_bridge',master)
                else:
                    category='bridge_or_port_self_entry' if kind(link)=='bridge' or link.has('master') else 'non_bridge_interface_self_entry'
                fdb_classes.append((scope,ordinal,category))
                if row.has('vlan') and (row.get('ifname'),row.get('vlan')) not in vlans:issue('fdb_vlan_unproven')
                key=(row.get('ifname'),row.get('mac'),row.get('master'),row.get('vlan'),row.get('flags'))
                if key in seen:issue('fdb_identity_ambiguous')
                seen.add(key)
        for source in ('route4','route6'):
            doc=documents.get(source)
            if doc is None:continue
            for ordinal,row in enumerate(doc.rows):
                link=named.get(row.get('dev'))
                if link is None:issue('route_device_unproven')
                else:join(source,ordinal,'route_device',link)
                if not row.has('table'):issue('route_table_absent_semantics_unproven')
                if not row.has('type') or not row.has('scope'):issue('route_defaults_not_inferred')
                if row.has('expires') or row.has('metrics'):issue('ra_expiry_metrics_semantics_unreviewed')
        for source in ('rule4','rule6'):
            doc=documents.get(source)
            if doc is not None:
                priorities=[row.get('priority') for row in doc.rows]
                if len(set(priorities))!=len(priorities):issue('rpdb_priority_ambiguous')
                issue('table_alias_mapping_unproven')
    matched_counts={}
    for i,(scope,a) in enumerate(veths):
        for other_scope,b in veths[i+1:]:
            if a.get('link_index')==b.get('ifindex') and b.get('link_index')==a.get('ifindex'):
                candidates.append(PeerIndexCandidate61(scope,a.get('ifindex'),a.get('link_netnsid'),
                    other_scope,b.get('ifindex'),b.get('link_netnsid')))
                for key in ((scope,a.get('ifindex')),(other_scope,b.get('ifindex'))):matched_counts[key]=matched_counts.get(key,0)+1
    if any(value>1 for value in matched_counts.values()):issue('peer_index_candidates_ambiguous')
    if coverage:issue('native_source_coverage_missing')
    issue('namespace_fd_nsid_witness_unobserved')
    issue('capture_argv_timing_principal_unrecorded')
    issue('os_attachments_permissions_fds_unobserved')
    issue('native_policy_semantics_unreviewed')
    return tuple(joins),tuple(candidates),tuple(coverage),tuple(fdb_classes),tuple(issues)


@dataclass(frozen=True, slots=True)
class NativeDiagnosticBundle61(c._Offline2):
    profile: s.NativeTopologyProfile61
    declared_scope_labels: tuple[str, ...]
    sources: tuple[DecodedNativeSource61, ...]
    stage: str = field(default='topology_unproven',init=False)
    management_policy_verified: bool = field(default=False,init=False)
    isolation_verified: bool = field(default=False,init=False)
    joins: tuple[DiagnosticJoin61, ...] = field(init=False)
    peer_index_candidates: tuple[PeerIndexCandidate61, ...] = field(init=False)
    missing_sources: tuple = field(init=False)
    fdb_classifications: tuple = field(init=False)
    uncertainty_reasons: tuple[str, ...] = field(init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._typed(self.profile,s.NativeTopologyProfile61)
        c._require(type(self.declared_scope_labels) is tuple and 1<=len(self.declared_scope_labels)<=32,
                   'v2_native61_scope_invalid')
        for label in self.declared_scope_labels:_scope(label)
        c._require(len(set(self.declared_scope_labels))==len(self.declared_scope_labels),'v2_native61_scope_invalid')
        c._require(type(self.sources) is tuple and len(self.sources)<=256,'v2_native61_documents_limit')
        keys=[];total=0
        for doc in self.sources:
            c._typed(doc,DecodedNativeSource61);total+=doc.reference.raw_byte_count
            c._require(doc.profile==self.profile and doc.reference.scope_label in self.declared_scope_labels,
                'v2_native61_profile_mismatch')
            keys.append((doc.reference.scope_label,doc.reference.source))
        c._require(total<=16777216,'v2_native61_aggregate_limit')
        c._require(len(set(keys))==len(keys),'v2_native61_duplicate_source')
        joins,candidates,missing,classes,issues=_diagnose(self.sources,self.declared_scope_labels)
        for key,value in (('joins',joins),('peer_index_candidates',candidates),('missing_sources',missing),
                          ('fdb_classifications',classes),('uncertainty_reasons',issues)):
            object.__setattr__(self,key,value)

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('native61_diagnostic_bundle',(self.profile.digest,self.declared_scope_labels,tuple(d.digest for d in self.sources)))


@dataclass(frozen=True, slots=True)
class NativePolicyReview61(c._Offline2):
    """Known incompatibilities only; never a complete V2-04 policy evaluation."""
    bundle: NativeDiagnosticBundle61
    expected_policy: management.ManagementHostProfile2
    pinned_policy_digest: str
    findings: tuple[str, ...] = field(init=False)
    result: str = field(init=False)
    isolation_result: str = field(default='isolation_unproven',init=False)
    management_policy_verified: bool = field(default=False,init=False)
    isolation_verified: bool = field(default=False,init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self);c._typed(self.bundle,NativeDiagnosticBundle61)
        c._typed(self.expected_policy,management.ManagementHostProfile2);c._hex(self.pinned_policy_digest)
        findings=[]
        if self.expected_policy.digest!=self.pinned_policy_digest:findings.append('profile_digest_mismatch')
        if len(self.bundle.declared_scope_labels)>len(self.expected_policy.namespaces):findings.append('additional_named_capture_scopes')
        docs={(d.reference.scope_label,d.reference.source):d for d in self.bundle.sources}
        host=docs.get(('host','link'))
        if host is not None:
            expected=next(p for p in self.expected_policy.namespaces if p.identity.role=='host')
            expected_rows=next(d.rows for d in expected.sources if d.source=='link')
            if {r.get('ifname') for r in host.rows}!={r.get('ifname') for r in expected_rows}:findings.append('host_link_inventory_mismatch')
            expected_bridge=next(r.get('ifname') for r in expected_rows if r.get('linkinfo') is not None and r.get('linkinfo').get('info_kind')=='bridge')
            if any(r.get('linkinfo') is not None and r.get('linkinfo').get('info_kind')=='bridge' and r.get('ifname')!=expected_bridge for r in host.rows):
                findings.append('canonical_bridge_name_mismatch')
        for scope in self.bundle.declared_scope_labels:
            links=docs.get((scope,'link'));addresses=docs.get((scope,'address'));routes=docs.get((scope,'route6'))
            if links is None:continue
            test_names=set();test_ids=set()
            for row in links.rows:
                info=row.get('linkinfo')
                if info is not None and info.get('info_kind') in ('bridge','veth'):
                    test_names.add(row.get('ifname'));test_ids.add(row.get('ifindex'))
            if addresses is not None and any(row.get('ifindex') in test_ids and
                any(a.get('family')=='inet6' for a in row.get('addr_info')) for row in addresses.rows):
                if 'test_side_ipv6_forbidden' not in findings:findings.append('test_side_ipv6_forbidden')
            if routes is not None and any(row.get('dev') in test_names for row in routes.rows):
                if 'test_side_ipv6_route_forbidden' not in findings:findings.append('test_side_ipv6_route_forbidden')
        object.__setattr__(self,'findings',tuple(findings))
        object.__setattr__(self,'result','profile_mismatch' if findings else 'profile_unproven')

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('native61_policy_review',(self.bundle.digest,self.expected_policy.digest,
                      self.pinned_policy_digest,self.findings,self.result))


def review_native_policy61(bundle,expected_policy,pinned_policy_digest):
    return NativePolicyReview61(bundle,expected_policy,pinned_policy_digest)
