# Observed native field matrix — capture 20261021

Generated offline from original saved bytes. Counts describe this corpus only; bounds/requiredness come from the separate static diagnostic registry.
No command execution, kernel defaults, binary provenance or namespace attestation is inferred. Exact execution argv is absent.

| Source/path | Observed type/count | Present / parent | Absent | New kind / required | Old provisional type |
|---|---|---:|---:|---|---|
| address/*.ifindex | int:13 | 13 / 13 | 0 | index / True | positive |
| address/*.ifname | str:13 | 13 / 13 | 0 | ifname / True | ifname |
| address/*.flags | list:13 | 13 / 13 | 0 | linkflags / True | unsupported path |
| address/*.mtu | int:13 | 13 / 13 | 0 | index / True | unsupported path |
| address/*.qdisc | str:13 | 13 / 13 | 0 | qdisc / True | unsupported path |
| address/*.operstate | str:13 | 13 / 13 | 0 | operstate / True | unsupported path |
| address/*.group | str:13 | 13 / 13 | 0 | group / True | unsupported path |
| address/*.txqlen | int:13 | 13 / 13 | 0 | uint32 / True | unsupported path |
| address/*.link_type | str:13 | 13 / 13 | 0 | link_type / True | unsupported path |
| address/*.address | str:13 | 13 / 13 | 0 | mac / True | unsupported path |
| address/*.broadcast | str:13 | 13 / 13 | 0 | mac / True | unsupported path |
| address/*.addr_info | list:13 | 13 / 13 | 0 | rows / True | array |
| address/*.addr_info.*.family | str:23 | 23 / 23 | 0 | family / True | family |
| address/*.addr_info.*.local | str:23 | 23 / 23 | 0 | ip / True | ip |
| address/*.addr_info.*.prefixlen | int:23 | 23 / 23 | 0 | prefix / True | prefix |
| address/*.addr_info.*.scope | str:23 | 23 / 23 | 0 | address_scope / True | token |
| address/*.addr_info.*.label | str:10 | 10 / 23 | 13 | ifname / False | ifname |
| address/*.addr_info.*.valid_life_time | int:23 | 23 / 23 | 0 | uint32 / True | lifetime |
| address/*.addr_info.*.preferred_life_time | int:23 | 23 / 23 | 0 | uint32 / True | lifetime |
| address/*.link_index | int:6 | 6 / 13 | 7 | index / False | unsupported path |
| address/*.link_netnsid | int:6 | 6 / 13 | 7 | uint32 / False | unsupported path |
| address/*.addr_info.*.noprefixroute | bool:1 | 1 / 23 | 22 | bool / False | unsupported path |
| address/*.altnames | list:1 | 1 / 13 | 12 | ifnames / False | unsupported path |
| address/*.addr_info.*.metric | int:1 | 1 / 23 | 22 | uint32 / False | unsupported path |
| address/*.addr_info.*.broadcast | str:1 | 1 / 23 | 22 | ip / False | ip |
| address/*.addr_info.*.dynamic | bool:1 | 1 / 23 | 22 | bool / False | unsupported path |
| address/*.master | str:2 | 2 / 13 | 11 | ifname / False | unsupported path |
| bridge_fdb/*.mac | str:23 | 23 / 23 | 0 | mac / True | mac |
| bridge_fdb/*.ifname | str:23 | 23 / 23 | 0 | ifname / True | unsupported path |
| bridge_fdb/*.flags | list:23 | 23 / 23 | 0 | fdbflags / True | flags:self / master / router / extern_learn / offload / sticky |
| bridge_fdb/*.state | str:23 | 23 / 23 | 0 | fdbstate / True | flags:permanent / static / dynamic / reachable / stale / noarp / failed / incomplete / delay / probe |
| bridge_fdb/*.vlan | int:3 | 3 / 23 | 20 | vlan / False | vlan |
| bridge_fdb/*.master | str:6 | 6 / 23 | 17 | ifname / False | ifname |
| bridge_link/*.ifindex | int:2 | 2 / 2 | 0 | index / True | positive |
| bridge_link/*.link | str:2 | 2 / 2 | 0 | ifname / True | ifname |
| bridge_link/*.ifname | str:2 | 2 / 2 | 0 | ifname / True | ifname |
| bridge_link/*.flags | list:2 | 2 / 2 | 0 | linkflags / True | flags:LOOPBACK / BROADCAST / MULTICAST / UP / LOWER_UP / NOARP / POINTOPOINT / DORMANT / PROMISC / ALLMULTI / MASTER / SLAVE |
| bridge_link/*.mtu | int:2 | 2 / 2 | 0 | index / True | positive |
| bridge_link/*.master | str:2 | 2 / 2 | 0 | ifname / True | ifname |
| bridge_link/*.state | str:2 | 2 / 2 | 0 | portstate / True | enum:disabled / listening / learning / forwarding / blocking |
| bridge_link/*.priority | int:2 | 2 / 2 | 0 | uint32 / True | uint |
| bridge_link/*.cost | int:2 | 2 / 2 | 0 | uint32 / True | uint |
| bridge_link/*.hairpin | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.guard | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.root_block | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.fastleave | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.learning | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.flood | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.mcast_flood | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.bcast_flood | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.mcast_router | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| bridge_link/*.mcast_to_unicast | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.neigh_suppress | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.vlan_tunnel | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.isolated | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_link/*.locked | bool:2 | 2 / 2 | 0 | bool / True | onoff |
| bridge_vlan/*.ifname | str:3 | 3 / 3 | 0 | ifname / True | ifname |
| bridge_vlan/*.vlans | list:3 | 3 / 3 | 0 | rows / True | array |
| bridge_vlan/*.vlans.*.vlan | int:3 | 3 / 3 | 0 | vlan / True | vlan |
| bridge_vlan/*.vlans.*.flags | list:3 | 3 / 3 | 0 | vlanflags / True | flags:PVID / Egress_Untagged |
| link/*.ifindex | int:13 | 13 / 13 | 0 | index / True | positive |
| link/*.ifname | str:13 | 13 / 13 | 0 | ifname / True | ifname |
| link/*.flags | list:13 | 13 / 13 | 0 | linkflags / True | flags:LOOPBACK / BROADCAST / MULTICAST / UP / LOWER_UP / NOARP / POINTOPOINT / DORMANT / PROMISC / ALLMULTI / MASTER / SLAVE |
| link/*.mtu | int:13 | 13 / 13 | 0 | index / True | positive |
| link/*.qdisc | str:13 | 13 / 13 | 0 | qdisc / True | token |
| link/*.operstate | str:13 | 13 / 13 | 0 | operstate / True | token |
| link/*.linkmode | str:13 | 13 / 13 | 0 | linkmode / True | token |
| link/*.group | str:13 | 13 / 13 | 0 | group / True | token |
| link/*.txqlen | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.link_type | str:13 | 13 / 13 | 0 | link_type / True | token |
| link/*.address | str:13 | 13 / 13 | 0 | mac / True | mac |
| link/*.broadcast | str:13 | 13 / 13 | 0 | mac / True | mac |
| link/*.promiscuity | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.allmulti | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.min_mtu | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.max_mtu | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.inet6_addr_gen_mode | str:13 | 13 / 13 | 0 | addrgen / True | token |
| link/*.num_tx_queues | int:13 | 13 / 13 | 0 | index / True | positive |
| link/*.num_rx_queues | int:13 | 13 / 13 | 0 | index / True | positive |
| link/*.gso_max_size | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.gso_max_segs | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.tso_max_size | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.tso_max_segs | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.gro_max_size | int:13 | 13 / 13 | 0 | uint32 / True | uint |
| link/*.link_index | int:6 | 6 / 13 | 7 | index / False | positive |
| link/*.link_netnsid | int:6 | 6 / 13 | 7 | uint32 / False | uint |
| link/*.linkinfo | dict:7 | 7 / 13 | 6 | object / False | object |
| link/*.linkinfo.info_kind | str:7 | 7 / 7 | 0 | kind / True | kind |
| link/*.parentbus | str:1 | 1 / 13 | 12 | parentbus / False | unsupported path |
| link/*.parentdev | str:1 | 1 / 13 | 12 | parentdev / False | unsupported path |
| link/*.altnames | list:1 | 1 / 13 | 12 | ifnames / False | unsupported path |
| link/*.linkinfo.info_data | dict:1 | 1 / 7 | 6 | object / False | object |
| link/*.linkinfo.info_data.forward_delay | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.hello_time | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.max_age | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.ageing_time | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.stp_state | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.priority | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.vlan_filtering | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.vlan_protocol | str:1 | 1 / 1 | 0 | vlanprotocol / True | token |
| link/*.linkinfo.info_data.bridge_id | str:1 | 1 / 1 | 0 | bridgeid / True | token |
| link/*.linkinfo.info_data.root_id | str:1 | 1 / 1 | 0 | bridgeid / True | token |
| link/*.linkinfo.info_data.root_port | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.root_path_cost | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.topology_change | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.topology_change_detected | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.hello_timer | decimal:1 | 1 / 1 | 0 | decimal / True | timer |
| link/*.linkinfo.info_data.tcn_timer | decimal:1 | 1 / 1 | 0 | decimal / True | timer |
| link/*.linkinfo.info_data.topology_change_timer | decimal:1 | 1 / 1 | 0 | decimal / True | timer |
| link/*.linkinfo.info_data.gc_timer | decimal:1 | 1 / 1 | 0 | decimal / True | timer |
| link/*.linkinfo.info_data.vlan_default_pvid | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.vlan_stats_enabled | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.vlan_stats_per_port | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.group_fwd_mask | str:1 | 1 / 1 | 0 | masktoken / True | token |
| link/*.linkinfo.info_data.group_addr | str:1 | 1 / 1 | 0 | mac / True | mac |
| link/*.linkinfo.info_data.mcast_snooping | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.no_linklocal_learn | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_vlan_snooping | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_router | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_query_use_ifaddr | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_querier | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_hash_elasticity | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_hash_max | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_last_member_cnt | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_startup_query_cnt | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_last_member_intvl | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_membership_intvl | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_querier_intvl | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_query_intvl | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_query_response_intvl | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_startup_query_intvl | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_stats_enabled | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_igmp_version | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.mcast_mld_version | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.nf_call_iptables | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.nf_call_ip6tables | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.linkinfo.info_data.nf_call_arptables | int:1 | 1 / 1 | 0 | uint32 / True | uint |
| link/*.master | str:2 | 2 / 13 | 11 | ifname / False | positive |
| link/*.linkinfo.info_slave_kind | str:2 | 2 / 7 | 5 | slavekind / False | unsupported path |
| link/*.linkinfo.info_slave_data | dict:2 | 2 / 7 | 5 | object / False | unsupported path |
| link/*.linkinfo.info_slave_data.state | str:2 | 2 / 2 | 0 | portstate / True | unsupported path |
| link/*.linkinfo.info_slave_data.priority | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| link/*.linkinfo.info_slave_data.cost | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| link/*.linkinfo.info_slave_data.hairpin | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.guard | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.root_block | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.fastleave | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.learning | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.flood | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.id | str:2 | 2 / 2 | 0 | hextoken / True | unsupported path |
| link/*.linkinfo.info_slave_data.no | str:2 | 2 / 2 | 0 | hextoken / True | unsupported path |
| link/*.linkinfo.info_slave_data.designated_port | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| link/*.linkinfo.info_slave_data.designated_cost | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| link/*.linkinfo.info_slave_data.bridge_id | str:2 | 2 / 2 | 0 | bridgeid / True | unsupported path |
| link/*.linkinfo.info_slave_data.root_id | str:2 | 2 / 2 | 0 | bridgeid / True | unsupported path |
| link/*.linkinfo.info_slave_data.hold_timer | decimal:2 | 2 / 2 | 0 | decimal / True | unsupported path |
| link/*.linkinfo.info_slave_data.message_age_timer | decimal:2 | 2 / 2 | 0 | decimal / True | unsupported path |
| link/*.linkinfo.info_slave_data.forward_delay_timer | decimal:2 | 2 / 2 | 0 | decimal / True | unsupported path |
| link/*.linkinfo.info_slave_data.topology_change_ack | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| link/*.linkinfo.info_slave_data.config_pending | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| link/*.linkinfo.info_slave_data.proxy_arp | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.proxy_arp_wifi | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.multicast_router | int:2 | 2 / 2 | 0 | uint32 / True | unsupported path |
| link/*.linkinfo.info_slave_data.mcast_flood | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.bcast_flood | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.mcast_to_unicast | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.neigh_suppress | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.group_fwd_mask | str:2 | 2 / 2 | 0 | masktoken / True | unsupported path |
| link/*.linkinfo.info_slave_data.group_fwd_mask_str | str:2 | 2 / 2 | 0 | hextoken / True | unsupported path |
| link/*.linkinfo.info_slave_data.vlan_tunnel | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.isolated | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| link/*.linkinfo.info_slave_data.locked | bool:2 | 2 / 2 | 0 | bool / True | unsupported path |
| route4/*.dst | str:35 | 35 / 35 | 0 | routeprefix / True | network |
| route4/*.dev | str:35 | 35 / 35 | 0 | ifname / True | ifname |
| route4/*.protocol | str:35 | 35 / 35 | 0 | protocol4 / True | enum:kernel / boot / static / ra / dhcp |
| route4/*.scope | str:32 | 32 / 35 | 3 | route_scope / False | enum:global / link / host |
| route4/*.prefsrc | str:35 | 35 / 35 | 0 | ip / True | ip |
| route4/*.flags | list:35 | 35 / 35 | 0 | emptyflags / True | flags:onlink / linkdown / offload / trap |
| route4/*.type | str:25 | 25 / 35 | 10 | routetype4 / False | enum:unicast / local / broadcast |
| route4/*.table | str:25 | 25 / 35 | 10 | routetable / False | table |
| route4/*.gateway | str:3 | 3 / 35 | 32 | ip / False | ip |
| route4/*.metric | int:6 | 6 / 35 | 29 | uint32 / False | uint |
| route6/*.dst | str:30 | 30 / 30 | 0 | routeprefix / True | network |
| route6/*.dev | str:30 | 30 / 30 | 0 | ifname / True | ifname |
| route6/*.protocol | str:30 | 30 / 30 | 0 | protocol6 / True | enum:kernel / boot / static / ra / dhcp |
| route6/*.metric | int:30 | 30 / 30 | 0 | uint32 / True | uint |
| route6/*.flags | list:30 | 30 / 30 | 0 | emptyflags / True | flags:onlink / linkdown / offload / trap |
| route6/*.pref | str:30 | 30 / 30 | 0 | pref / True | enum:low / medium / high |
| route6/*.type | str:21 | 21 / 30 | 9 | routetype6 / False | enum:unicast / local / broadcast |
| route6/*.table | str:21 | 21 / 30 | 9 | routetable / False | table |
| route6/*.gateway | str:1 | 1 / 30 | 29 | ip / False | ip |
| route6/*.expires | int:1 | 1 / 30 | 29 | uint32 / False | unsupported path |
| route6/*.metrics | list:1 | 1 / 30 | 29 | metrics / False | unsupported path |
| route6/*.metrics.*.hoplimit | int:1 | 1 / 1 | 0 | uint8 / True | unsupported path |
| rule4/*.priority | int:15 | 15 / 15 | 0 | uint32 / True | uint |
| rule4/*.src | str:15 | 15 / 15 | 0 | all / True | network |
| rule4/*.table | str:15 | 15 / 15 | 0 | ruletable4 / True | table |
| rule6/*.priority | int:10 | 10 / 10 | 0 | uint32 / True | uint |
| rule6/*.src | str:10 | 10 / 10 | 0 | all / True | network |
| rule6/*.table | str:10 | 10 / 10 | 0 | ruletable6 / True | table |

Exact array cardinalities, raw values, per-document row counts/hashes and decoder outcomes are retained in [observed_matrix.json](observed_matrix.json).
