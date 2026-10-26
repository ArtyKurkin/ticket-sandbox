"""Independent trusted SYNTHETIC policy inputs, fixed before capture decoding."""
from copy import deepcopy
from dataclasses import dataclass, replace
from .native_v2_support import uid, hd
from .native_v2_topology_support import TopologyFixture2
from trusted_checker_network import native_v2_topology as t
from trusted_checker_network import native_v2_topology_schema as s
from trusted_checker_network import native_v2_management as m


def address(family,local,prefixlen,scope='global'):
    return {'family':family,'local':local,'prefixlen':prefixlen,'scope':scope,
            'valid_life_time':'forever','preferred_life_time':'forever'}


@dataclass
class ManagementFixture2:
    topology_fixture: TopologyFixture2
    policy: m.ManagementHostProfile2
    pinned_digest: str

    @classmethod
    def create(cls):
        f=TopologyFixture2.create()
        # These are authored policy inputs, NOT rows extracted from a decoded snapshot.
        f.rows['host']['address'][1]['addr_info']=[address('inet','192.0.2.2',24),
                                                   address('inet6','2001:db8::2',64)]
        for role,ip in (('runner','10.201.1.2'),('target','10.201.1.3')):
            f.rows[role]['address'][1]['addr_info']=[address('inet',ip,24)]
            f.rows[role]['route4']=[
                {'dst':'10.201.1.0/24','dev':'eth0','table':'main','protocol':'kernel',
                 'scope':'link','type':'unicast','prefsrc':ip},
                {'dst':ip+'/32','dev':'eth0','table':'local','protocol':'kernel',
                 'scope':'host','type':'local','prefsrc':ip},
            ]
            f.rows[role]['route6']=[{'dst':'::1/128','dev':'lo','table':'local',
                                   'protocol':'kernel','scope':'host','type':'local'}]
        roles_by_namespace={
            'host':('loopback','management','test_bridge','runner_host_port','target_host_port'),
            'runner':('loopback','peer'), 'target':('loopback','peer'),
        }
        namespaces=[]
        for identity in f.namespaces:
            rows=f.rows[identity.role]
            links=tuple(m.ManagedLinkPolicy2(role,t.LinkReference2(identity.key,row['ifindex']),row['address'],
                    None if role in ('loopback','management') else hd('synthetic-creation-'+identity.role+'-'+role))
                    for role,row in zip(roles_by_namespace[identity.role],rows['link']))
            sources=tuple(m.ExpectedTopologySource2(source,s.validate_rows2(source,deepcopy(rows[source])))
                          for source in s.SOURCES)
            namespaces.append(m.NamespaceManagementPolicy2(identity,links,sources))
        policy=m.ManagementHostProfile2(uid(800),hd('synthetic-policy-review-not-authentication'),f.profile,
            uid(3),hd('synthetic-approval'),uid(4),tuple(namespaces),f.peers,f.tables,
            m.WriterPolicy2((hd('synthetic-installer-principal'),hd('synthetic-setup-principal')),
                            hd('synthetic-writer-review-no-os-proof')),
            hd('synthetic-canonical-nft-recipe-reference'))
        # Only now may observed supplied captures be rendered/decoded.
        return cls(f,policy,policy.digest)

    def topology(self,rows=None):
        return self.topology_fixture.complete(rows)

    def validate(self,rows=None):
        return m.validate_management_profile2(self.topology(rows),self.policy,self.pinned_digest)

    def changed_rows(self,change):
        rows=deepcopy(self.topology_fixture.rows)
        change(rows)
        return rows

    def policy_change(self,role,source,change):
        """Mutate trusted specs for constructor/pin tests, never fit a tested snapshot."""
        policies=list(self.policy.namespaces)
        index=next(i for i,p in enumerate(policies) if p.identity.role==role)
        spec=policies[index]; rows=deepcopy(self.topology_fixture.rows[role][source]); change(rows)
        sources=tuple(m.ExpectedTopologySource2(source,s.validate_rows2(source,rows))
                      if p.source==source else p for p in spec.sources)
        policies[index]=replace(spec,sources=sources)
        return replace(self.policy,namespaces=tuple(policies))
