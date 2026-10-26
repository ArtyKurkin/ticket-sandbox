root\@msk-1-vm-fgv4:\~# echo "===== FINAL NFT JSON ====="

nft -j -a list ruleset



echo "===== BRIDGE PORTS ====="

bridge -j link show



echo "===== BRIDGE CONFIG ====="

ip -j -d link show tc-br0



echo "===== NAMESPACES ====="

ip netns list



echo "===== HOST ROUTING ====="

ip -4 route show

ip -6 route show



echo "===== MODULES ====="

lsmod | grep -E 'bridge|nf_conntrack|nft_ct|br_netfilter'



echo "===== HTTP SERVER ====="

ip netns exec tc-br-target ss -lntp '( sport = :8080 )'

\===== FINAL NFT JSON =====

{"nftables": [{"metainfo": {"version": "1.0.9", "release_name": "Old Doc Yak #3", "json_schema_version": 1}}, {"table": {"family": "bridge", "name": "tc_ct_lab", "handle": 6}}, {"chain": {"family": "bridge", "table": "tc_ct_lab", "name": "forward", "handle": 1, "type": "filter", "hook": "forward", "prio": -200, "policy": "accept"}}, {"rule": {"family": "bridge", "table": "tc_ct_lab", "chain": "forward", "handle": 2, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "protocol"}}, "right": "tcp"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "dport"}}, "right": 8080}}, {"match": {"op": "in", "left": {"ct": {"key": "state"}}, "right": "new"}}, {"counter": {"packets": 3, "bytes": 180}}]}}, {"rule": {"family": "bridge", "table": "tc_ct_lab", "chain": "forward", "handle": 3, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "protocol"}}, "right": "tcp"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "dport"}}, "right": 8080}}, {"match": {"op": "in", "left": {"ct": {"key": "state"}}, "right": "established"}}, {"counter": {"packets": 15, "bytes": 1014}}]}}, {"rule": {"family": "bridge", "table": "tc_ct_lab", "chain": "forward", "handle": 4, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "protocol"}}, "right": "tcp"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "sport"}}, "right": 8080}}, {"match": {"op": "in", "left": {"ct": {"key": "state"}}, "right": "established"}}, {"counter": {"packets": 12, "bytes": 3530}}]}}, {"table": {"family": "bridge", "name": "tc_strict_lab", "handle": 8}}, {"chain": {"family": "bridge", "table": "tc_strict_lab", "name": "forward", "handle": 1, "type": "filter", "hook": "forward", "prio": 10, "policy": "accept"}}, {"rule": {"family": "bridge", "table": "tc_strict_lab", "chain": "forward", "handle": 2, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ether", "field": "type"}}, "right": "arp"}}, {"accept": null}]}}, {"rule": {"family": "bridge", "table": "tc_strict_lab", "chain": "forward", "handle": 3, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ether", "field": "type"}}, "right": "arp"}}, {"accept": null}]}}, {"rule": {"family": "bridge", "table": "tc_strict_lab", "chain": "forward", "handle": 4, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "saddr"}}, "right": "10.201.1.2"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "daddr"}}, "right": "10.201.1.3"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "protocol"}}, "right": "tcp"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "dport"}}, "right": 8080}}, {"match": {"op": "in", "left": {"ct": {"key": "state"}}, "right": "new"}}, {"counter": {"packets": 1, "bytes": 60}}, {"accept": null}]}}, {"rule": {"family": "bridge", "table": "tc_strict_lab", "chain": "forward", "handle": 5, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "saddr"}}, "right": "10.201.1.2"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "daddr"}}, "right": "10.201.1.3"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "protocol"}}, "right": "tcp"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "dport"}}, "right": 8080}}, {"match": {"op": "in", "left": {"ct": {"key": "state"}}, "right": "established"}}, {"counter": {"packets": 5, "bytes": 338}}, {"accept": null}]}}, {"rule": {"family": "bridge", "table": "tc_strict_lab", "chain": "forward", "handle": 6, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "saddr"}}, "right": "10.201.1.3"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "daddr"}}, "right": "10.201.1.2"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "ip", "field": "protocol"}}, "right": "tcp"}}, {"match": {"op": "==", "left": {"payload": {"protocol": "tcp", "field": "sport"}}, "right": 8080}}, {"match": {"op": "in", "left": {"ct": {"key": "state"}}, "right": "established"}}, {"counter": {"packets": 6, "bytes": 1931}}, {"accept": null}]}}, {"rule": {"family": "bridge", "table": "tc_strict_lab", "chain": "forward", "handle": 7, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-r-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-t-host"}}, {"counter": {"packets": 6, "bytes": 428}}, {"drop": null}]}}, {"rule": {"family": "bridge", "table": "tc_strict_lab", "chain": "forward", "handle": 8, "expr": [{"match": {"op": "==", "left": {"meta": {"key": "iifname"}}, "right": "tc-br-t-host"}}, {"match": {"op": "==", "left": {"meta": {"key": "oifname"}}, "right": "tc-br-r-host"}}, {"counter": {"packets": 3, "bytes": 176}}, {"drop": null}]}}]}

\===== BRIDGE PORTS =====

[{"ifindex":7,"link":"if6","ifname":"tc-br-r-host","flags":["BROADCAST","MULTICAST","UP","LOWER_UP"],"mtu":1500,"master":"tc-br0","state":"forwarding","priority":32,"cost":2},{"ifindex":9,"link":"if8","ifname":"tc-br-t-host","flags":["BROADCAST","MULTICAST","UP","LOWER_UP"],"mtu":1500,"master":"tc-br0","state":"forwarding","priority":32,"cost":2}]

\===== BRIDGE CONFIG =====

[{"ifindex":5,"ifname":"tc-br0","flags":["BROADCAST","MULTICAST","UP","LOWER_UP"],"mtu":1500,"qdisc":"noqueue","operstate":"UP","linkmode":"DEFAULT","group":"default","txqlen":1000,"link_type":"ether","address":"da:86:66:ca:86:59","broadcast":"ff:ff:ff:ff:ff:ff","promiscuity":0,"allmulti":0,"min_mtu":68,"max_mtu":65535,"linkinfo":{"info_kind":"bridge","info_data":{"forward_delay":1500,"hello_time":200,"max_age":2000,"ageing_time":30000,"stp_state":0,"priority":32768,"vlan_filtering":0,"vlan_protocol":"802.1Q","bridge_id":"8000.da:86:66:ca:86:59","root_id":"8000.da:86:66:ca:86:59","root_port":0,"root_path_cost":0,"topology_change":0,"topology_change_detected":0,"hello_timer":0.00,"tcn_timer":0.00,"topology_change_timer":0.00,"gc_timer":178.16,"vlan_default_pvid":1,"vlan_stats_enabled":0,"vlan_stats_per_port":0,"group_fwd_mask":"0","group_addr":"01:80:c2:00:00:00","mcast_snooping":1,"no_linklocal_learn":0,"mcast_vlan_snooping":0,"mcast_router":1,"mcast_query_use_ifaddr":0,"mcast_querier":0,"mcast_hash_elasticity":16,"mcast_hash_max":4096,"mcast_last_member_cnt":2,"mcast_startup_query_cnt":2,"mcast_last_member_intvl":100,"mcast_membership_intvl":26000,"mcast_querier_intvl":25500,"mcast_query_intvl":12500,"mcast_query_response_intvl":1000,"mcast_startup_query_intvl":3125,"mcast_stats_enabled":0,"mcast_igmp_version":2,"mcast_mld_version":1,"nf_call_iptables":0,"nf_call_ip6tables":0,"nf_call_arptables":0}},"inet6_addr_gen_mode":"eui64","num_tx_queues":1,"num_rx_queues":1,"gso_max_size":65536,"gso_max_segs":65535,"tso_max_size":524280,"tso_max_segs":65535,"gro_max_size":65536}]

\===== NAMESPACES =====

tc-br-target (id: 3)

tc-br-runner (id: 2)

tc-target (id: 1)

tc-runner (id: 0)

\===== HOST ROUTING =====

default via 89.169.0.1 dev eth0 proto dhcp src 89.169.0.131 metric 100 

85.193.93.193 via 89.169.0.1 dev eth0 proto dhcp src 89.169.0.131 metric 100 

85.193.93.194 via 89.169.0.1 dev eth0 proto dhcp src 89.169.0.131 metric 100 

89.169.0.0/24 dev eth0 proto kernel scope link src 89.169.0.131 metric 100 

89.169.0.1 dev eth0 proto dhcp scope link src 89.169.0.131 metric 100 

169.254.169.0/24 dev eth0 proto dhcp scope link src 89.169.0.131 metric 100 

fe80::/64 dev eth0 proto kernel metric 256 pref medium

fe80::/64 dev tc-br-r-host proto kernel metric 256 pref medium

fe80::/64 dev tc-br0 proto kernel metric 256 pref medium

fe80::/64 dev tc-br-t-host proto kernel metric 256 pref medium

default via fe80::9cce:edff:fee6:7340 dev eth0 proto ra metric 100 expires 1734sec hoplimit 64 pref medium

\===== MODULES =====

**nf_conntrack**\_**bridge**    12288  6

**nft_ct**                 24576  6

**nf_conntrack**          196608  2 **nft_ct**,**nf_conntrack**\_**bridge**

nf_defrag_ipv6         24576  2 **nf_conntrack**,**nf_conntrack**\_**bridge**

nf_defrag_ipv4         12288  1 **nf_conntrack**

nft_meta\_**bridge**        12288  23

**bridge**                425984  2 nft_meta\_**bridge**,**nf_conntrack**\_**bridge**

stp                    12288  1 **bridge**

llc                    16384  2 **bridge**,stp

nf_tables             364544  117 nft_meta\_**bridge**,**nft_ct**

libcrc32c              12288  4 **nf_conntrack**,btrfs,nf_tables,raid456

\===== HTTP SERVER =====

State                                       Recv-Q                                      Send-Q                                                                           Local Address:Port                                                                           Peer Address:Port                                     Process                                     

LISTEN                                      0                                           5                                                                                   10.201.1.3:8080                                                                                0.0.0.0:\*                                         users:(("python3",pid=2107,fd=3))          

root\@msk-1-vm-fgv4:\~# 