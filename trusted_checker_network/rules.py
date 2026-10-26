"""V3 exact approved templates; no application and no generic rules input."""
from copy import deepcopy
from trusted_checker_live.egress import compile_rules, canonical_readback, PortBinding
from trusted_checker_runtime.profiles import require
from trusted_checker_shadow.policy import digest
from .contracts import POLICY


def table_name(approval_uuid):
    from trusted_checker_runtime.contracts import uid
    uid(approval_uuid)
    return 'tc3_'+approval_uuid.replace('-', '')  # Full UUID, not name-selected ownership.


def approved_rules(approval_uuid, runtime_approval, binding, *, active):
    require(type(active) is bool, 'rules_mode_invalid')
    ports = tuple(PortBinding(n.interface,n.ifindex,n.container_id,n.endpoint_id,n.mac,n.ipv4)
                  for n in (binding.target,binding.runner)) if active else ()
    rules = deepcopy(compile_rules(runtime_approval, ports))
    for command in rules['nftables']:
        item = next(iter(command['add'].values()))
        if item.get('name') == 'tc_shadow': item['name'] = table_name(approval_uuid)
        if item.get('table') == 'tc_shadow': item['table'] = table_name(approval_uuid)
        if 'hook' in item:
            item['prio'] = POLICY.bridge_priority if item['family'] == 'bridge' else POLICY.inet_priority
    # Add explicit EtherType dependencies before IP/ARP payload accesses. This
    # also prevents implicit nft parser dependency insertion during readback.
    for command in rules['nftables']:
        rule = command['add'].get('rule')
        if rule and rule['family'] == 'bridge':
            text = str(rule['expr'])
            proto = 'arp' if "'protocol': 'arp'" in text else 'ip'
            rule['expr'].insert(0, {'match': {'op':'==', 'left':{'payload':{'protocol':'ether','field':'type'}}, 'right':proto}})
    return rules


def rules_hash(rules): return digest(canonical_readback(rules))


def exact_tables(rules):
    return tuple((item['table']['family'], item['table']['name']) for item in canonical_readback(rules) if 'table' in item)


def transaction_for(approval_uuid, rules, *, replacing):
    """One native nft transaction, restricted to two exact durably owned tables.

    Caller must prove ownership before passing replacing=True; the UUID/name
    check alone never grants deletion rights.
    """
    tables = (('bridge',table_name(approval_uuid)),('inet',table_name(approval_uuid)))
    require(exact_tables(rules) == tables and type(replacing) is bool,'foreign_rules_transaction')
    prefix = [{'delete':{'table':{'family':family,'name':name}}} for family,name in tables] if replacing else []
    commands=deepcopy(rules['nftables'])
    if not replacing:
        # Native create (exclusive), not idempotent add: pre-existing tables
        # with a colliding name cannot be silently adopted or modified.
        commands=[{'create':c['add']} if 'table' in c['add'] else c for c in commands]
    return {'nftables':prefix+commands}
