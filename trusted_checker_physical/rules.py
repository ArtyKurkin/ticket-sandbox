"""Physical recipe v4: own tables plus narrowly bound native nftrace marking."""
from copy import deepcopy
from trusted_checker_network.rules import approved_rules,exact_tables,rules_hash
from trusted_checker_runtime.profiles import require


def name(identifier):return 'tc4_'+identifier.replace('-','')


def recipes(identifier,runtime_approval,binding,*,active):
    rules=deepcopy(approved_rules(identifier,runtime_approval,binding,active=active))
    for command in rules['nftables']:
        obj=next(iter(command['add'].values()))
        if obj.get('name','').startswith('tc3_'):obj['name']=name(identifier)
        if obj.get('table','').startswith('tc3_'):obj['table']=name(identifier)
    # Observability changes are part of the v4 approved digest, never appended
    # ad hoc to an already approved/installed v3 table.
    if active:
        rule={'add':{'rule':{'family':'bridge','table':name(identifier),'chain':'prerouting','expr':[
            {'match':{'op':'==','left':{'meta':{'key':'iif'}},'right':binding.runner.ifindex}},
            {'mangle':{'key':{'meta':{'key':'nftrace'}},'value':1}}]}}}
        index=next(i for i,c in enumerate(rules['nftables']) if 'rule' in c['add'] and c['add']['rule']['family']=='bridge')
        rules['nftables'].insert(index,rule)
    return rules


def transaction(approval,rules,handles=None):
    tables=(('bridge',name(approval.approval_uuid)),('inet',name(approval.approval_uuid)))
    require(exact_tables(rules)==tables,'physical_foreign_transaction')
    commands=deepcopy(rules['nftables'])
    if handles is None:
        commands=[{'create':c['add']} if 'table' in c['add'] else c for c in commands]
    else:
        require(type(handles) is tuple and len(handles)==2 and all(type(h) is int and h>0 for h in handles),
                'physical_table_ownership_missing')
        # Delete by exact kernel handle prevents replacing a same-name table
        # whose identity changed after the independent ownership readback.
        commands=[{'delete':{'table':{'family':family,'handle':handle}}}
                  for (family,_),handle in zip(tables,handles)]+commands
    return {'nftables':commands}
