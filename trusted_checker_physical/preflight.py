"""Read-only inventory, never a network isolation attestation."""
from dataclasses import dataclass
import hashlib
import re
from trusted_checker_runtime.profiles import require,Denied
from .contracts import PROFILE
from .io import json_output

REQUIRED_CONFIG=('CONFIG_BRIDGE','CONFIG_VETH','CONFIG_NF_TABLES','CONFIG_NF_TABLES_BRIDGE',
                 'CONFIG_NF_CONNTRACK','CONFIG_NF_CONNTRACK_BRIDGE','CONFIG_NFT_CT','CONFIG_PACKET','CONFIG_NETFILTER_NETLINK')
MODULES={'CONFIG_BRIDGE':'bridge','CONFIG_VETH':'veth','CONFIG_NF_TABLES':'nf_tables',
         'CONFIG_NF_CONNTRACK':'nf_conntrack','CONFIG_NF_CONNTRACK_BRIDGE':'nf_conntrack_bridge','CONFIG_NFT_CT':'nft_ct',
         'CONFIG_NETFILTER_NETLINK':'nfnetlink'}
OFFLOAD=('rx-checksumming','tx-checksumming','tcp-segmentation-offload','generic-segmentation-offload',
         'generic-receive-offload','large-receive-offload','rx-vlan-offload','tx-vlan-offload')


def validate_ruleset(rules,owned_tables=()):
    require(type(rules) is dict and set(rules)=={'nftables'},'physical_ruleset_shape_invalid')
    for item in rules['nftables']:
        require(type(item) is dict and len(item)==1,'physical_ruleset_object_invalid')
        if 'metainfo' in item:continue
        kind=next(iter(item));obj=item[kind]
        require(kind in ('table','chain','rule'),'physical_unknown_ruleset_object')
        family,name=obj.get('family'),obj.get('name') if kind=='table' else obj.get('table')
        require((family,name) in owned_tables,'physical_foreign_table_or_hook')


@dataclass(frozen=True)
class PreflightReport:
    kernel: str
    nft: str
    origin: str
    observed_at: float
    facts_digest: str
    isolation_proven: bool = False
    capture_continuity_proven: bool = False


class HostPreflight:
    def __init__(self,activation,io,docker):
        require(io.activation is activation and docker.activation is activation,'physical_preflight_boundary_mismatch')
        self.activation,self.io,self.docker=activation,io,docker
    def check(self,budget,owned_tables=(),*,expected_ids=None,allow_missing=False):
        started=budget.monotonic()
        a=self.activation.check('read');b=a.binding;io=self.io
        try:
            kernel=io.run('kernel',budget).decode().strip()
            require(re.fullmatch(r'\d+\.\d+\.\d+(?:[-+.][a-zA-Z0-9_.+-]+)?',kernel) and
                    '.'.join(kernel.split('.')[:2]) in PROFILE.kernel_series,'physical_kernel_unsupported')
            nft=io.run('nft_version',budget).decode().strip()
            match=re.fullmatch(r'nftables v(\d+\.\d+\.\d+)(?: \([^\n]+\))?',nft)
            require(match is not None and match[1] in PROFILE.nft_series,'physical_nft_unsupported')
            config=io.read('/boot/config-'+kernel,budget)
            config=dict(line.split('=',1) for line in config.splitlines() if line.startswith('CONFIG_') and '=' in line)
            loaded={line.split()[0] for line in io.read('/proc/modules',budget).splitlines() if line}
            require(all(config.get(key) in ('y','m') and (config[key]=='y' or key not in MODULES or MODULES[key] in loaded)
                        for key in REQUIRED_CONFIG),'physical_kernel_feature_unproven')
            require(config['CONFIG_NF_TABLES_BRIDGE']=='y' or 'nf_tables' in loaded,'physical_bridge_family_unproven')
            for name in ('iptables','ip6tables','arptables'):
                require(io.read('/proc/sys/net/bridge/bridge-nf-call-'+name,budget).strip()=='0','physical_br_netfilter_active')
            require(io.read('/proc/sys/kernel/random/boot_id',budget).strip()==b.host_boot_uuid,'physical_host_boot_changed')
            machine=io.read('/etc/machine-id',budget).strip().encode()
            require(hashlib.sha256(machine).hexdigest()==b.host_identity_digest and
                    io.inode('/proc/self/ns/net',budget)==b.host_netns_inode,'physical_host_identity_changed')
            links=json_output(io.run('links',budget))
            bridges=[l for l in links if l.get('linkinfo',{}).get('info_kind')=='bridge']
            require(len(bridges)==1 and bridges[0]['ifname']==b.bridge_name and bridges[0]['ifindex']==b.bridge_ifindex and
                    bridges[0]['address']==b.bridge_mac,'physical_bridge_changed')
            require(not any(link.get('xdp') for link in links) and
                    bridges[0].get('linkinfo',{}).get('info_data',{}).get('vlan_filtering',0)==0,'physical_xdp_or_vlan_unapproved')
            status=dict(line.split(':',1) for line in io.read('/proc/self/status',budget).splitlines() if ':' in line)
            capabilities=int(status['CapEff'].strip(),16)
            require(all(capabilities & (1<<bit) for bit in (12,13,21)) and status.get('Seccomp','').strip()=='0',
                    'physical_helper_capabilities_unproven')
            self.docker.call('info',budget)
            ids=tuple(expected_ids) if expected_ids is not None else (b.target.container_id,b.runner.container_id)
            require(set(ids)<={b.target.container_id,b.runner.container_id},'physical_workload_allowlist_invalid')
            observed=self.docker.call('containers',budget)
            observed_ids={c['Id'] for c in observed}
            require(type(observed) is list and (observed_ids<=set(ids) if allow_missing else observed_ids==set(ids)) and
                    len(observed)==len(observed_ids),'physical_foreign_workload')
            require({p['ifindex'] for p in links if p.get('master')==b.bridge_ifindex} <= {b.target.ifindex,b.runner.ifindex},
                    'physical_foreign_workload')
            rules=json_output(io.run('nft_read',budget));validate_ruleset(rules,owned_tables)
            facts=[]
            for interface in (b.bridge_name,b.target.interface,b.runner.interface):
                if allow_missing and interface not in {p['ifname'] for p in links}:continue
                text=io.run('offload',budget,interface=interface).decode()
                features=dict((m[1],m[2]) for line in text.splitlines() if
                              (m:=re.fullmatch(r'\s*([a-z0-9-]+): (on|off)(?: \[fixed\])?',line)))
                require(all(features.get(key)=='off' for key in OFFLOAD),'physical_offload_unproven')
                for op in ('tc_ingress','tc_egress'):
                    require(json_output(io.run(op,budget,interface=interface))==[],'physical_tc_filters_unapproved')
                facts.append(features)
            # Existence/limits are capability facts, not proof that packets or
            # netlink messages were received without loss.
            for path in ('/proc/sys/net/core/rmem_max','/proc/sys/net/core/rmem_default'):
                require(int(io.read(path,budget))>=131072,'physical_capture_buffer_insufficient')
            from trusted_checker_shadow.policy import digest
            return PreflightReport(kernel,nft,self.activation.origin,self.activation.clock(),digest(facts))
        except Denied:raise
        except Exception:raise Denied('physical_preflight_unknown') from None
        finally:budget.observe('preflight',started)
