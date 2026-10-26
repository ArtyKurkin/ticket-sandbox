"""Bracketed exact-ID Docker/proc/veth/netns checks, without target filesystem."""
from copy import deepcopy
from dataclasses import dataclass
from trusted_checker_runtime.profiles import require,Denied
from .io import json_output


def start_ticks(raw):
    try:return int(raw.rsplit(')',1)[1].split()[19])
    except (ValueError,IndexError):raise Denied('physical_proc_stat_invalid') from None


@dataclass(frozen=True)
class InventoryReceipt:
    binding_digest: str
    origin: str
    observed_at: float
    namespace_peers: tuple
    continuity_proven: bool = False


class NamespaceInventory:
    def __init__(self,activation,io,docker):
        require(io.activation is activation and docker.activation is activation,'physical_inventory_boundary_mismatch')
        self.activation,self.io,self.docker=activation,io,docker
    def observe(self,budget):
        started=budget.monotonic()
        approval=self.activation.check('read');b=approval.binding
        try:
            require(self.io.inode('/proc/self/ns/net',budget)==b.host_netns_inode and
                    self.io.read('/proc/sys/kernel/random/boot_id',budget).strip()==b.host_boot_uuid,
                    'physical_host_namespace_changed')
            before_links=json_output(self.io.run('links',budget))
            peers=[]
            for n in (b.target,b.runner):
                before=deepcopy(self.docker.call('inspect_container',budget,n.container_id));state=before['State']
                require(before['Id']==n.container_id and state['Pid']==n.pid and state['Running'] is True and
                        state['Status']=='running' and state['StartedAt']==n.docker_started_at and
                        before['RestartCount']==n.restart_count==0 and
                        not any(state.get(k) for k in ('Paused','Restarting','Dead')),'physical_container_generation_changed')
                inode=self.io.inode('/proc/'+str(n.pid)+'/ns/net',budget)
                ticks=start_ticks(self.io.read('/proc/'+str(n.pid)+'/stat',budget))
                require(inode==n.netns_inode and ticks==n.process_start_ticks,'physical_pid_namespace_reuse')
                links=json_output(self.io.run('links',budget,namespace=n.pid))
                links=[p for p in links if p['ifname']!='lo']
                require(len(links)==1,'physical_extra_namespace_interface')
                peer=links[0]
                host=[p for p in before_links if p.get('ifindex')==n.ifindex]
                require(len(host)==1,'physical_veth_missing');host=host[0]
                require(host['ifname']==n.interface and host['master']==b.bridge_ifindex and
                        host['link_index']==n.peer_ifindex and peer['ifindex']==n.peer_ifindex and
                        peer['link_index']==n.ifindex and peer['address']==n.mac and
                        host['linkinfo']['info_kind']==peer['linkinfo']['info_kind']=='veth','physical_veth_identity_changed')
                endpoints=before['NetworkSettings']['Networks']
                require(len(endpoints)==1,'physical_extra_docker_network')
                ep=next(iter(endpoints.values()))
                require((ep['NetworkID'],ep['EndpointID'],ep['IPAddress'],ep['MacAddress'])==
                        (b.network_id,n.endpoint_id,n.ipv4,n.mac),'physical_endpoint_changed')
                addresses=json_output(self.io.run('addresses',budget,namespace=n.pid))
                addresses=[a for a in addresses if a['ifindex']==n.peer_ifindex]
                require(len(addresses)==1 and [a['local'] for a in addresses[0]['addr_info'] if a['family']=='inet']==[n.ipv4],
                        'physical_namespace_address_changed')
                require(self.io.inode('/proc/'+str(n.pid)+'/ns/net',budget)==inode and
                        start_ticks(self.io.read('/proc/'+str(n.pid)+'/stat',budget))==ticks,'physical_pid_namespace_reuse')
                after=self.docker.call('inspect_container',budget,n.container_id)
                require(after['Id']==before['Id'] and after['State']==before['State'] and
                        after['NetworkSettings']==before['NetworkSettings'] and after['RestartCount']==before['RestartCount'],
                        'physical_identity_changed_during_observation')
                peers.append((n.pid,n.netns_inode,n.peer_ifindex,peer['ifname']))
            after_links=json_output(self.io.run('links',budget))
            require(after_links==before_links,'physical_host_links_changed')
            bridge=[p for p in after_links if p.get('linkinfo',{}).get('info_kind')=='bridge']
            require(len(bridge)==1 and bridge[0]['ifindex']==b.bridge_ifindex and bridge[0]['ifname']==b.bridge_name and
                    bridge[0]['address']==b.bridge_mac,'physical_bridge_identity_changed')
            members={p['ifindex'] for p in after_links if p.get('master')==b.bridge_ifindex}
            require(members=={b.target.ifindex,b.runner.ifindex},'physical_unowned_bridge_attachment')
            network=self.docker.call('inspect_network',budget,b.network_id)
            require(network['Id']==b.network_id and network['Driver']=='bridge' and network['Internal'] is True and
                    network.get('EnableIPv6') is False and network['Options'].get('com.docker.network.bridge.name')==b.bridge_name and
                    set(network['Containers'])=={b.target.container_id,b.runner.container_id},'physical_network_changed')
            for n in (b.target,b.runner):
                require(network['Containers'][n.container_id]['EndpointID']==n.endpoint_id and
                        network['Containers'][n.container_id]['IPv4Address'].split('/')[0]==n.ipv4,'physical_network_endpoint_changed')
            return InventoryReceipt(b.digest,self.activation.origin,self.activation.clock(),tuple(peers))
        except Denied:raise
        except Exception:raise Denied('physical_inventory_unknown') from None
        finally:budget.observe('namespace_inventory',started)
