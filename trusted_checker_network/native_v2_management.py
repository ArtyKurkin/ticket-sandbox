"""Offline dedicated-management-host-v2 policy; no physical evidence or authority.

Expected records are supplied by trusted fixture setup BEFORE decoding observed
captures. A pinned content digest is not a signature or an approval issuance.
There is deliberately no snapshot-to-profile factory or accepted OS proof input.
"""
from dataclasses import dataclass, field

from . import native_v2_contracts as c
from . import native_v2_topology as t
from . import native_v2_topology_schema as s

PROFILE_ID = 'dedicated-management-host-v2'
ROLES = ('host', 'runner', 'target')
LINK_ROLES = ('loopback', 'management', 'test_bridge', 'runner_host_port', 'target_host_port', 'peer')
EXPECTATIONS = (
    ('nft_hooks_priorities', 'full_inventory_exact_approved_recipe'),
    ('flowtables', 'none_in_approved_boundary'),
    ('ipv4_forwarding', 'disabled'),
    ('ipv6_forwarding', 'disabled'),
    ('proxy_arp', 'disabled'),
    ('proxy_nd', 'disabled'),
    ('bridge_netfilter', 'exact_reviewed_configuration'),
    ('network_capabilities', 'reviewed_principals_peers_dropall_nnp_no_network_caps'),
    ('external_inherited_fds', 'no_external_network_fds_or_privileged_sockets'),
    ('writer_authority', 'exclusive_reviewed_serialized_writers'),
    ('namespace_attachments', 'only_exact_registered_namespace_bindings'),
    ('capture_provenance', 'independent_authenticated_complete_fenced_capture'),
    ('native_host_profile', 'reviewed_exact_native_build_and_host_manifest'),
)
LINK_EXPECTATIONS = (
    ('tc_ingress', 'none_in_approved_boundary'),
    ('tc_egress', 'none_in_approved_boundary'),
    ('xdp', 'none_in_approved_boundary'),
    ('offloads', 'exact_reviewed_disabled_offload_configuration'),
    ('ipv4_forwarding', 'disabled'),
    ('ipv6_forwarding', 'disabled'),
    ('proxy_arp', 'disabled'),
    ('proxy_nd', 'disabled'),
    ('bridge_netfilter', 'exact_reviewed_configuration'),
)
HOOKS = (
    ('bridge', 'prerouting', 0, 'drop'), ('bridge', 'input', 0, 'drop'),
    ('bridge', 'forward', 0, 'drop'), ('bridge', 'output', 0, 'drop'),
    ('inet', 'input', -310, 'accept'), ('inet', 'forward', -310, 'accept'),
    ('inet', 'output', -310, 'accept'),
)


def _rows(value, cls, minimum=0, maximum=1024):
    c._require(type(value) is tuple and minimum <= len(value) <= maximum,
               'v2_management_collection_invalid')
    for row in value:
        c._typed(row, cls)


def _unique(values):
    c._require(len(values) == len(set(values)), 'v2_management_identity_collision')


@dataclass(frozen=True, slots=True)
class ExpectedTopologySource2(c._Offline2):
    """Trusted policy specification, never an observed capture or JSON adapter."""
    source: str
    rows: tuple[s.FrozenObject2, ...]

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.source, s.SOURCES)
        c._require(self.rows == s.validate_frozen_rows2(self.source, self.rows),
                   'v2_management_expected_invalid')


@dataclass(frozen=True, slots=True)
class ManagedLinkPolicy2(c._Offline2):
    role: str
    reference: t.LinkReference2
    mac: str
    creation_record_reference_digest: str | None

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.role, LINK_ROLES)
        c._typed(self.reference, t.LinkReference2)
        s._scalar(self.mac, 'mac')
        if self.role in ('loopback', 'management'):
            c._require(self.creation_record_reference_digest is None,
                       'v2_management_creation_reference_invalid')
        else:
            c._hex(self.creation_record_reference_digest)


@dataclass(frozen=True, slots=True)
class NamespaceManagementPolicy2(c._Offline2):
    identity: t.NamespaceRole2
    links: tuple[ManagedLinkPolicy2, ...]
    sources: tuple[ExpectedTopologySource2, ...]

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.identity, t.NamespaceRole2)
        _rows(self.links, ManagedLinkPolicy2, 2, 5)
        _rows(self.sources, ExpectedTopologySource2, 9, 9)
        _unique([link.role for link in self.links])
        _unique([link.reference for link in self.links])
        _unique([source.source for source in self.sources])
        c._require({source.source for source in self.sources} == set(s.SOURCES),
                   'v2_management_expected_coverage_invalid')
        expected_roles = ({'loopback', 'management', 'test_bridge', 'runner_host_port', 'target_host_port'}
                          if self.identity.role == 'host' else {'loopback', 'peer'})
        c._require({link.role for link in self.links} == expected_roles,
                   'v2_management_link_roles_invalid')
        for link in self.links:
            c._require(link.reference.namespace == self.identity.key,
                       'v2_management_namespace_invalid')
        link_rows = next(source.rows for source in self.sources if source.source == 'link')
        _unique([row.get('ifindex') for row in link_rows])
        _unique([row.get('ifname') for row in link_rows])
        c._require({link.reference.ifindex for link in self.links} ==
                   {row.get('ifindex') for row in link_rows}, 'v2_management_expected_links_invalid')
        for link in self.links:
            row = next(row for row in link_rows if row.get('ifindex') == link.reference.ifindex)
            c._require(row.get('address') == link.mac, 'v2_management_expected_links_invalid')


@dataclass(frozen=True, slots=True)
class WriterPolicy2(c._Offline2):
    principal_reference_digests: tuple[str, ...]
    review_reference_digest: str
    mode: str = 'exclusive_reviewed_serialized_only'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._require(type(self.principal_reference_digests) is tuple and
                   1 <= len(self.principal_reference_digests) <= 16, 'v2_management_writer_policy_invalid')
        for digest in self.principal_reference_digests:
            c._hex(digest)
        _unique(list(self.principal_reference_digests))
        c._hex(self.review_reference_digest)
        c._enum(self.mode, ('exclusive_reviewed_serialized_only',))


@dataclass(frozen=True, slots=True)
class EvidenceRequirement2(c._Offline2):
    namespace: c.NamespaceKey2
    surface: str
    expectation: str
    link: t.LinkReference2 | None

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.namespace, c.NamespaceKey2)
        expectations = dict(LINK_EXPECTATIONS if self.link is not None else EXPECTATIONS)
        c._enum(self.surface, tuple(expectations))
        c._enum(self.expectation, (expectations[self.surface],))
        if self.link is not None:
            c._typed(self.link, t.LinkReference2)
            c._require(self.link.namespace == self.namespace, 'v2_management_namespace_invalid')


@dataclass(frozen=True, slots=True)
class EvidenceRequirementStatus2(c._Offline2):
    requirement: EvidenceRequirement2
    status: str = 'unobserved'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.requirement, EvidenceRequirement2)
        c._enum(self.status, ('unobserved',))


def _source_map(sources):
    return {source.source: source.rows for source in sources}


def _kind(row):
    info = row.get('linkinfo')
    return info.get('info_kind') if info is not None else None


def _invariants(policy, sources, table_mappings):
    """Hard conservative constraints also apply to the trusted manifest itself."""
    issues = []
    def issue(reason):
        if reason not in issues:
            issues.append(reason)
    roles = {link.role: link for link in policy.links}
    expected_indices = {link.reference.ifindex for link in policy.links}
    links = sources.get('link')
    if links is None:
        return ()  # Missing source is handled by completeness, never as [].
    if {row.get('ifindex') for row in links} != expected_indices or len(links) != len(expected_indices):
        issue('link_inventory_mismatch')
    indexed = {row.get('ifindex'): row for row in links}
    named = {row.get('ifname'): row for row in links}
    for role, link in roles.items():
        row = indexed.get(link.reference.ifindex)
        if row is None:
            continue
        if row.get('address') != link.mac:
            issue('link_identity_mismatch')
        if role == 'loopback':
            if 'LOOPBACK' not in row.get('flags') or row.get('link_type') != 'loopback':
                issue('loopback_mismatch')
        elif 'LOOPBACK' in row.get('flags'):
            issue('link_identity_mismatch')
        if role == 'management':
            if (any(row.has(key) for key in ('master', 'link_index', 'link_netnsid')) or row.has('linkinfo') or
                    any(flag in row.get('flags') for flag in ('MASTER', 'SLAVE'))):
                issue('management_link_attachment_forbidden')
            if row.get('link_type') != 'ether':
                issue('management_link_identity_mismatch')
        elif role == 'test_bridge':
            if _kind(row) != 'bridge' or row.get('ifname') != 'tcsh0' or row.has('master'):
                issue('test_bridge_mismatch')
        elif role in ('runner_host_port', 'target_host_port', 'peer'):
            if _kind(row) != 'veth':
                issue('veth_kind_mismatch')
            if role == 'peer' and row.has('master'):
                issue('peer_master_forbidden')
            if role != 'peer':
                bridge = roles['test_bridge']
                if row.get('master') != bridge.reference.ifindex:
                    issue('bridge_membership_mismatch')
                # Existing binding's veth naming constraint; no interface rename.
                suffix = row.get('ifname')[4:] if row.get('ifname').startswith('veth') else ''
                if not (1 <= len(suffix) <= 10 and suffix.isascii() and suffix.isalnum()):
                    issue('host_veth_name_mismatch')
    if policy.identity.role == 'host':
        bridge = roles['test_bridge']
        ports = {roles[key].reference.ifindex for key in ('runner_host_port', 'target_host_port')}
        if {row.get('ifindex') for row in links if row.has('master')} != ports:
            issue('bridge_membership_mismatch')
        test_indices = ports | {bridge.reference.ifindex}
    else:
        test_indices = {roles['peer'].reference.ifindex}
    test_names = {row.get('ifname') for row in links if row.get('ifindex') in test_indices}
    for row in sources.get('address', ()):
        if row.get('ifindex') in test_indices:
            if any(address.get('family') == 'inet6' for address in row.get('addr_info')):
                issue('test_side_ipv6_forbidden')
    for source in ('route4', 'route6'):
        for route in sources.get(source, ()):
            if source == 'route6' and route.get('dev') in test_names:
                issue('test_side_ipv6_route_forbidden')
            if policy.identity.role == 'host':
                management = indexed.get(roles['management'].reference.ifindex)
                if route.get('dst') == 'default' and (management is None or route.get('dev') != management.get('ifname')):
                    issue('host_default_route_not_management')
            else:
                if route.get('dst') == 'default':
                    issue('peer_default_route_forbidden')
                if route.has('gateway'):
                    issue('peer_gateway_forbidden')
                if route.has('src'):
                    issue('peer_source_route_forbidden')
                if route.get('protocol') != 'kernel' or route.get('scope') not in ('link', 'host'):
                    issue('peer_route_not_connected_or_local')
                if route.get('dev') not in named:
                    issue('peer_route_device_mismatch')
                number = next((mapping.number for mapping in table_mappings
                               if mapping.namespace == policy.identity.key and mapping.token == route.get('table')), None)
                if number not in (254, 255):
                    issue('peer_alternate_route_table_forbidden')
    for source in ('rule4', 'rule6'):
        priorities = [row.get('priority') for row in sources.get(source, ())]
        if len(set(priorities)) != len(priorities):
            issue('ambiguous_rpdb_priority')
        if policy.identity.role != 'host':
            for rule in sources.get(source, ()):
                if set(key for key, value in rule.fields) - {'priority', 'src', 'table', 'action', 'protocol'}:
                    issue('peer_policy_routing_forbidden')
                if rule.get('src') != 'all':
                    issue('peer_policy_routing_forbidden')
                number = next((mapping.number for mapping in table_mappings
                               if mapping.namespace == policy.identity.key and mapping.token == rule.get('table')), None)
                if (rule.get('priority'), number) not in ((0, 255), (32766, 254), (32767, 253)):
                    issue('peer_policy_routing_forbidden')
    return tuple(issues)


def _expected_graph_checks(profile):
    """Validate expected joins without synthesizing an observed envelope/capture."""
    issues = []
    def require(condition, reason):
        if not condition and reason not in issues:
            issues.append(reason)
    all_links = {}
    for policy in profile.namespaces:
        sources = _source_map(policy.sources)
        ns = policy.identity.key
        links = {row.get('ifindex'): row for row in sources['link']}
        named = {row.get('ifname'): row for row in sources['link']}
        all_links.update({t.LinkReference2(ns, idx): row for idx, row in links.items()})
        addresses = sources['address']
        require(len(addresses) == len(links) and {row.get('ifindex') for row in addresses} == set(links),
                'expected_address_coverage_invalid')
        require(all(row.get('ifindex') in links and links[row.get('ifindex')].get('ifname') == row.get('ifname')
                    for row in addresses), 'expected_address_join_invalid')
        address_ids = [(row.get('ifindex'), a.get('family'), a.get('local'), a.get('prefixlen'))
                       for row in addresses for a in row.get('addr_info')]
        require(len(set(address_ids)) == len(address_ids), 'expected_address_collision')
        ports = sources['bridge_link']
        require(len(ports) == len({row.get('ifindex') for row in ports}) and
                {row.get('ifindex') for row in ports} == {idx for idx, row in links.items() if row.has('master')},
                'expected_bridge_membership_invalid')
        for port in ports:
            row, bridge = links.get(port.get('ifindex')), named.get(port.get('master'))
            require(row is not None and row.get('ifname') == port.get('ifname') and bridge is not None and
                    _kind(bridge) == 'bridge' and row.get('master') == bridge.get('ifindex'),
                    'expected_bridge_join_invalid')
        vlans = set()
        for row in sources['vlan']:
            link = named.get(row.get('ifname'))
            require(link is not None and (_kind(link) == 'bridge' or link.has('master')), 'expected_vlan_join_invalid')
            for vlan in row.get('vlans'):
                for number in range(vlan.get('vlan'), vlan.get('vlanEnd', vlan.get('vlan')) + 1):
                    key = (row.get('ifname'), number)
                    require(key not in vlans, 'expected_vlan_collision')
                    vlans.add(key)
        fdb_keys = set()
        for row in sources['fdb']:
            link, bridge = named.get(row.get('dev')), named.get(row.get('master'))
            require(link is not None and bridge is not None and _kind(bridge) == 'bridge' and
                    (link == bridge or link.get('master') == bridge.get('ifindex')), 'expected_fdb_join_invalid')
            require(not row.has('vlan') or (row.get('dev'), row.get('vlan')) in vlans, 'expected_fdb_vlan_invalid')
            key = (row.get('dev'), row.get('master'), row.get('mac'), row.get('vlan'))
            require(key not in fdb_keys, 'expected_fdb_collision')
            fdb_keys.add(key)
        mappings = {mapping.token: mapping.number for mapping in profile.table_mappings if mapping.namespace == ns}
        for row in (*sources['route4'], *sources['route6'], *sources['rule4'], *sources['rule6']):
            require(row.get('table') in mappings, 'expected_table_reference_invalid')
            require(all(not row.has(key) or row.get(key) in named for key in ('dev', 'iif', 'oif')),
                    'expected_route_reference_invalid')
        issues.extend(reason for reason in _invariants(policy, sources, profile.table_mappings) if reason not in issues)
    pairs = []
    host = next(policy for policy in profile.namespaces if policy.identity.role == 'host')
    for role in ('runner', 'target'):
        peer = next(policy for policy in profile.namespaces if policy.identity.role == role)
        pairs.append((next(link.reference for link in host.links if link.role == role + '_host_port'),
                      next(link.reference for link in peer.links if link.role == 'peer')))
    require(len(profile.peer_witnesses) == 2, 'expected_peer_witness_invalid')
    for first, second in pairs:
        witnesses = [w for w in profile.peer_witnesses if (w.first, w.second) in ((first, second), (second, first))]
        require(len(witnesses) == 1, 'expected_peer_witness_invalid')
        if len(witnesses) == 1:
            w = witnesses[0]
            a, b = all_links[w.first], all_links[w.second]
            require(a.get('link_index') == w.second.ifindex and b.get('link_index') == w.first.ifindex and
                    a.get('link_netnsid') == w.first_observed_nsid and
                    b.get('link_netnsid') == w.second_observed_nsid, 'expected_peer_identity_invalid')
    return tuple(issues)


@dataclass(frozen=True, slots=True)
class ManagementHostProfile2(c._Offline2):
    profile_uuid: str
    review_reference_digest: str
    topology_profile: s.TopologyProfile2
    context_uuid: str
    capture_approval_reference_digest: str
    writer_epoch_uuid: str
    namespaces: tuple[NamespaceManagementPolicy2, ...]
    peer_witnesses: tuple[t.PeerWitness2, ...]
    table_mappings: tuple[t.TableMapping2, ...]
    writers: WriterPolicy2
    canonical_nft_recipe_reference_digest: str
    profile_id: str = PROFILE_ID
    policy_revision: int = 1
    acceptance: str = 'provisional_offline_only'
    requirements: tuple[EvidenceRequirement2, ...] = field(init=False)
    expected_host_hooks: tuple = field(default=HOOKS, init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._enum(self.profile_id, (PROFILE_ID,))
        c._require(type(self.policy_revision) is int and self.policy_revision == 1,
                   'v2_management_profile_version_invalid')
        c._enum(self.acceptance, ('provisional_offline_only',))
        for value in (self.profile_uuid, self.context_uuid, self.writer_epoch_uuid):
            c._uuid(value)
        for value in (self.review_reference_digest, self.capture_approval_reference_digest,
                      self.canonical_nft_recipe_reference_digest):
            c._hex(value)
        c._typed(self.topology_profile, s.TopologyProfile2)
        c._typed(self.writers, WriterPolicy2)
        _rows(self.namespaces, NamespaceManagementPolicy2, 3, 3)
        c._require(tuple(policy.identity.role for policy in self.namespaces) == ROLES,
                   'v2_management_namespace_roles_invalid')
        keys = tuple(policy.identity.key for policy in self.namespaces)
        _unique(list(keys))
        _unique([key.netns_inode for key in keys])
        c._require(len({(key.host_boot_uuid, key.reader_session_uuid) for key in keys}) == 1,
                   'v2_management_namespace_invalid')
        _rows(self.peer_witnesses, t.PeerWitness2, 2, 2)
        _rows(self.table_mappings, t.TableMapping2, 1, 32)
        _unique([(mapping.namespace, type(mapping.token).__name__, mapping.token) for mapping in self.table_mappings])
        c._require(all(mapping.namespace in keys for mapping in self.table_mappings), 'v2_management_namespace_invalid')
        c._require(all(w.first.namespace in keys and w.second.namespace in keys for w in self.peer_witnesses),
                   'v2_management_namespace_invalid')
        nsid_targets = {}
        for witness in self.peer_witnesses:
            for a, b, nsid in ((witness.first, witness.second, witness.first_observed_nsid),
                               (witness.second, witness.first, witness.second_observed_nsid)):
                key = (a.namespace, nsid)
                c._require(key not in nsid_targets or nsid_targets[key] == b.namespace,
                           'v2_management_peer_nsid_conflict')
                nsid_targets[key] = b.namespace
        issues = _expected_graph_checks(self)
        c._require(not issues, 'v2_management_manifest_unsafe')
        requirements = []
        for policy in self.namespaces:
            ns = policy.identity.key
            requirements.extend(EvidenceRequirement2(ns, surface, expectation, None)
                                for surface, expectation in EXPECTATIONS)
            for link in policy.links:
                requirements.extend(EvidenceRequirement2(ns, surface, expectation, link.reference)
                                    for surface, expectation in LINK_EXPECTATIONS)
        object.__setattr__(self, 'requirements', tuple(requirements))


def _compare(topology, profile, pinned_digest):
    mismatches, unknowns = [], []
    def mismatch(reason):
        if reason not in mismatches:
            mismatches.append(reason)
    def unknown(reason):
        if reason not in unknowns:
            unknowns.append(reason)
    if profile.digest != pinned_digest:
        mismatch('profile_digest_mismatch')
    plan = topology.normalized.plan
    if plan.profile != profile.topology_profile:
        mismatch('topology_profile_mismatch')
    if (plan.context_uuid, plan.approval_digest, plan.writer_epoch_uuid) != (
            profile.context_uuid, profile.capture_approval_reference_digest, profile.writer_epoch_uuid):
        mismatch('capture_context_mismatch')
    if any(witness not in profile.peer_witnesses for witness in plan.peer_witnesses):
        mismatch('peer_witness_mismatch')
    if any(witness not in plan.peer_witnesses for witness in profile.peer_witnesses):
        unknown('peer_witness_missing')
    if plan.table_mappings != profile.table_mappings:
        mismatch('table_mapping_mismatch')
    observed = {ns.identity.role: ns for ns in topology.normalized.namespaces}
    if set(observed) != set(ROLES):
        unknown('namespace_coverage_missing')
    for expected in profile.namespaces:
        actual = observed.get(expected.identity.role)
        if actual is None:
            continue
        if actual.identity != expected.identity:
            mismatch('namespace_identity_mismatch')
        sources = {source.descriptor.source: source.rows for source in actual.sources}
        if set(sources) != set(s.SOURCES):
            unknown('source_coverage_incomplete')
        for reason in _invariants(expected, sources, profile.table_mappings):
            mismatch(reason)
        for source in expected.sources:
            if source.source in sources and sources[source.source] != source.rows:
                mismatch(source.source + '_policy_mismatch')
    if topology.stage != 'topology_complete':
        unknown('topology_incomplete')
    structural = ('profile_mismatch' if mismatches else 'profile_unproven' if unknowns else
                  'profile_structurally_matched')
    # No accepted OS evidence path exists in this offline revision.
    unknown('native_schema_provisional')
    unknown('capture_provenance_unauthenticated')
    unknown('approved_native_host_profile_unproven')
    unknown('mandatory_os_evidence_unobserved')
    unknown('writer_control_unproven')
    return structural, tuple(mismatches), tuple(unknowns)


@dataclass(frozen=True, slots=True)
class ManagementProfileValidation2(c._Offline2):
    topology: t.TopologyEnvelope2
    profile: ManagementHostProfile2
    pinned_profile_digest: str
    structural_result: str = field(init=False)
    result: str = field(init=False)
    reason: str = field(init=False)
    mismatch_reasons: tuple[str, ...] = field(init=False)
    uncertainty_reasons: tuple[str, ...] = field(init=False)
    evidence_statuses: tuple[EvidenceRequirementStatus2, ...] = field(init=False)
    isolation_result: str = field(default='isolation_unproven', init=False)
    management_policy_verified: bool = field(default=False, init=False)
    isolation_verified: bool = field(default=False, init=False)
    measurement_verified: bool = field(default=False, init=False)

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        c._typed(self.topology, t.TopologyEnvelope2)
        c._typed(self.profile, ManagementHostProfile2)
        c._hex(self.pinned_profile_digest)
        structural, mismatches, unknowns = _compare(self.topology, self.profile, self.pinned_profile_digest)
        object.__setattr__(self, 'structural_result', structural)
        object.__setattr__(self, 'mismatch_reasons', mismatches)
        object.__setattr__(self, 'uncertainty_reasons', unknowns)
        object.__setattr__(self, 'result', 'profile_mismatch' if mismatches else 'profile_unproven')
        object.__setattr__(self, 'reason', mismatches[0] if mismatches else unknowns[0])
        object.__setattr__(self, 'evidence_statuses', tuple(EvidenceRequirementStatus2(requirement)
                                                        for requirement in self.profile.requirements))

    @property
    def digest(self):
        self.__post_init__()
        return c._hash('management_profile_validation', (
            self.topology.digest, self.profile.digest, self.pinned_profile_digest,
            self.structural_result, self.result, self.mismatch_reasons, self.uncertainty_reasons,
        ))


def validate_management_profile2(topology, expected_profile, pinned_profile_digest):
    """Full offline policy comparison against independently pinned trusted input.

    Schema errors are finite ContractViolation2; concrete mismatches precede
    provisional/evidence blockers. No input can opt into an isolation success.
    """
    return ManagementProfileValidation2(topology, expected_profile, pinned_profile_digest)
