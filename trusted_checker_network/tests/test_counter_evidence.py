from copy import deepcopy
from dataclasses import replace
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest

from trusted_checker_runtime.profiles import Denied
from trusted_checker_network.counter_contracts import MAXIMUM
from trusted_checker_network.counter_auth import FixtureAuthenticator, SignedCounter
from trusted_checker_network.counter_evidence import MeasurementFixture
from trusted_checker_network.counter_readback import validate_readback, parse_json
from trusted_checker_network.counter_rules import compile_counter_rules
from trusted_checker_network.rules import approved_rules
from trusted_checker_network.tests.counter_support import CounterLab


class CounterEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.lab = CounterLab(); self.addCleanup(self.lab.close)

    def unknown(self, modify, reason=None):
        result = self.lab.run(modify)
        self.assertEqual(result.result, 'unknown')
        self.assertTrue(self.lab.verifier.circuit)
        self.assertFalse(result.physical_probe_permitted)
        if reason: self.assertEqual(result.reason, reason)
        return result

    def test_terminal_drop_deltas_and_rst(self):
        r = self.lab.run()
        self.assertEqual((r.result,r.reason), ('verified','offline_counter_model_verified'))
        self.assertEqual(len(r.samples),15)
        self.assertEqual(r.samples[0].outcome,'path_open_rst')
        self.assertTrue(all(s.outcome=='terminal_drop_observed' for s in r.samples[1:]))
        self.assertFalse(r.continuous_attestation); self.assertFalse(r.physical_probe_permitted)
        self.assertEqual(r.trace_delivery_complete,'unproven')
        self.assertEqual(r.approval.runtime,self.lab.runtime)
        self.assertEqual(len(r.sample_plan),15)
        # Two independent local counters establish send path and terminal drop.
        sample = r.samples[1]
        changed = [(b.packets-a.packets,b.bytes-a.bytes) for a,b in zip(sample.before,sample.after)
                   if b.packets != a.packets]
        self.assertEqual(changed,[(1,54),(1,54)])

    def test_synack_does_not_assert_http_success(self):
        r = self.lab.run(flags=18)
        self.assertEqual(r.result,'verified'); self.assertEqual(r.samples[0].outcome,'path_open_synack')
        self.assertNotIn('http_passed',r.__dataclass_fields__)

    def corrupt_rule(self, mutate, reason='counter_readback_invalid'):
        def modify(f):
            s = next(s for s in self.lab.recipe.counters if s.purpose=='terminal_drop')
            return self.lab.change_read(f,1,'after',lambda raw:mutate(raw['nftables'][s.object_index]['rule'],s))
        self.unknown(modify,reason)

    def test_counter_before_accept_not_terminal_drop(self):
        self.corrupt_rule(lambda rule,s:rule['expr'].__setitem__(-1,{'accept':None}))

    def test_counter_moved_before_match(self):
        def change(rule,s): rule['expr'].insert(0,rule['expr'].pop(s.expression_index))
        self.corrupt_rule(change)

    def test_wrong_match_before_counter(self):
        self.corrupt_rule(lambda rule,s:rule['expr'][0]['match'].__setitem__('right',999))

    def test_counter_after_verdict(self):
        def change(rule,s): rule['expr'].append(rule['expr'].pop(s.expression_index))
        self.corrupt_rule(change)

    def test_wrong_rule_handle(self):
        self.corrupt_rule(lambda rule,s:rule.__setitem__('handle',999999))

    def test_bool_handle_rejected(self):
        self.corrupt_rule(lambda rule,s:rule.__setitem__('handle',True))

    def test_wrong_generation(self):
        self.unknown(lambda f:self.lab.change_packet(f,1,lambda p:replace(p,generation=2)), 'counter_generation_changed')

    def test_wrong_install_epoch(self):
        from trusted_checker_network.tests.support import uuid
        self.unknown(lambda f:self.lab.change_packet(f,1,lambda p:replace(p,install_epoch_uuid=uuid())), 'counter_generation_changed')

    def test_reset(self):
        def change(f):
            spec = next(s for s in self.lab.recipe.counters if s.probe_index==0 and s.purpose=='ingress')
            return self.lab.change_read(f,1,'after',lambda raw:raw['nftables'][spec.object_index]['rule']['expr'][spec.expression_index]['counter'].__setitem__('packets',0))
        self.unknown(change,'counter_reset_or_wrap')

    def test_wrap_and_invalid_numeric_values(self):
        for value in (2**64, -1, True, 1.0):
            with self.subTest(value=value):
                obs=self.lab.readback({},self.lab.clock()); raw=json.loads(obs.json)
                s=self.lab.recipe.counters[0]
                raw['nftables'][s.object_index]['rule']['expr'][s.expression_index]['counter']['packets']=value
                with self.assertRaises(Denied): validate_readback(replace(obs,json=json.dumps(raw)),self.lab.approval)

    def test_duplicate_counter_statement(self):
        self.corrupt_rule(lambda rule,s:rule['expr'].insert(s.expression_index,deepcopy(rule['expr'][s.expression_index])))

    def test_shared_named_counter_rejected(self):
        self.corrupt_rule(lambda rule,s:rule['expr'].__setitem__(s.expression_index,{'counter':'shared'}))

    def test_duplicate_rule_handle(self):
        def change(f):
            return self.lab.change_read(f,0,'before',lambda raw:raw['nftables'][1]['chain'].__setitem__('handle',100))
        self.unknown(change,'counter_readback_invalid')

    def test_unexplained_background_delta(self):
        def change(f):
            s=next(s for s in self.lab.recipe.counters if s.purpose=='fallback_drop')
            return self.lab.change_read(f,1,'after',lambda raw:raw['nftables'][s.object_index]['rule']['expr'][s.expression_index]['counter'].__setitem__('packets',1))
        self.unknown(change,'counter_delta_unexplained')

    def test_excess_drop_not_accepted_as_at_least_one(self):
        def change(rule,s):rule['expr'][s.expression_index]['counter']['packets']+=1
        self.corrupt_rule(change,'counter_delta_unexplained')

    def test_wrong_byte_delta(self):
        self.corrupt_rule(lambda rule,s:rule['expr'][s.expression_index]['counter'].__setitem__('bytes',1),'counter_delta_unexplained')

    def test_partial_readback(self):
        self.unknown(lambda f:self.lab.change_read(f,0,'before',lambda raw:raw['nftables'].pop()),'counter_readback_invalid')

    def test_missing_ingress(self):
        self.unknown(lambda f:self.lab.change_packet(f,1,lambda p:replace(p,events=p.events[:1])), 'counter_packet_incomplete')

    def test_missing_send(self):
        self.unknown(lambda f:self.lab.change_packet(f,1,lambda p:replace(p,events=p.events[1:])), 'counter_packet_incomplete')

    def test_timeout_without_drop(self):
        def change(f):
            sample=f.samples[1]; samples=list(f.samples)
            samples[1]=replace(sample,after=replace(sample.before,payload=replace(sample.before.payload,
                started_at=sample.after.payload.started_at,finished_at=sample.after.payload.finished_at)))
            samples[1]=replace(samples[1],after=self.lab.sign(samples[1].after.payload,'readback'))
            return replace(f,samples=tuple(samples))
        self.unknown(change,'counter_delta_unexplained')

    def test_allowed_packet_dropped(self):
        self.unknown(lambda f:self.lab.change_packet(f,0,lambda p:replace(p,events=p.events[:2])),'counter_packet_incomplete')

    def test_reply_wrong_flow(self):
        def change(p):
            events=list(p.events); events[-1]=replace(events[-1],frame=events[-1].frame[:-1]+b'\xff')
            return replace(p,events=tuple(events))
        self.unknown(lambda f:self.lab.change_packet(f,0,change))

    def topology_change(self,change):
        def modify(f): return replace(f,topology_after=self.lab.sign(change(f.topology_after.payload),'topology'))
        self.unknown(modify,'counter_topology_unproven')

    def test_extra_interface(self):
        def change(p):
            paths=list(p.paths); paths[-1]=replace(paths[-1],interfaces=paths[-1].interfaces+(('eth1',7,'veth',0,8,'',()),))
            return replace(p,paths=tuple(paths))
        self.topology_change(change)

    def test_extra_route_other_table(self):
        def change(p):
            paths=list(p.paths); paths[-1]=replace(paths[-1],routes=paths[-1].routes+((4,100,'0.0.0.0/0','unicast','eth0','172.30.0.1'),))
            return replace(p,paths=tuple(paths))
        self.topology_change(change)

    def test_changed_ipv6_policy_rule(self):
        def change(p):
            paths=list(p.paths); paths[-1]=replace(paths[-1],policy_rules=paths[-1].policy_rules+((6,1,100),))
            return replace(p,paths=tuple(paths))
        self.topology_change(change)

    def test_xdp_tc_flowtable_attachments(self):
        for kind in ('xdp','tc','flowtable'):
            p=self.lab.topology(self.lab.clock()); paths=list(p.paths)
            paths[0]=replace(paths[0],attachments=((kind,'tcsh0','foreign'),))
            from trusted_checker_network.counter_inventory import check_topology
            with self.subTest(kind=kind),self.assertRaises(Denied):check_topology(replace(p,paths=tuple(paths)),self.lab.approval)

    def test_unaccounted_writer(self):
        self.topology_change(lambda p:replace(p,unaccounted_writers=('foreign:root',)))

    def test_inherited_external_fd(self):
        self.topology_change(lambda p:replace(p,external_network_fds=('socket:foreign',)))

    def test_changed_review_identity(self):
        self.topology_change(lambda p:replace(p,review_digest='8'*64))

    def test_observed_endpoint_replaced(self):
        def change(p):
            b=replace(p.binding,runner=replace(p.binding.runner,endpoint_id='8'*64))
            return replace(p,binding=b,binding_digest=b.digest)
        self.topology_change(change)

    def test_observed_started_at_changed(self):
        def change(p):
            b=replace(p.binding,target=replace(p.binding.target,docker_started_at='2026-10-19T10:00:01Z'))
            return replace(p,binding=b,binding_digest=b.digest)
        self.topology_change(change)

    def test_unknown_nft_expression(self):
        self.corrupt_rule(lambda rule,s:rule['expr'].__setitem__(0,{'queue':{'num':1}}))

    def test_wrong_hook_priority_policy(self):
        obs=self.lab.readback({},self.lab.clock())
        for field,value in (('hook','output'),('prio',-999),('policy','accept')):
            raw=json.loads(obs.json);raw['nftables'][1]['chain'][field]=value
            with self.subTest(field=field),self.assertRaises(Denied):validate_readback(replace(obs,json=json.dumps(raw)),self.lab.approval)

    def test_missing_counter(self):
        self.corrupt_rule(lambda rule,s:rule['expr'].pop(s.expression_index))

    def test_duplicate_json_keys_and_nonfinite(self):
        for raw in ('{"nftables":[],"nftables":[]}','{"nftables":NaN}', '{', '{"nftables":1e999}'):
            with self.subTest(raw=raw),self.assertRaises(Denied):parse_json(raw)

    def test_forged_readback_signature(self):
        def change(f):
            samples=list(f.samples);s=samples[0];samples[0]=replace(s,before=replace(s.before,signature='0'*64))
            return replace(f,samples=tuple(samples))
        self.unknown(change,'counter_evidence_invalid')

    def test_foreign_signer_role(self):
        def change(f):
            samples=list(f.samples);s=samples[0]
            samples[0]=replace(s,before=replace(s.before,principal='packet:counter'))
            return replace(f,samples=tuple(samples))
        self.unknown(change)

    def test_old_v3_receipt_rejected(self):
        old=self.lab.base.signers['operator'].sign('approval',self.lab.base.approval)
        with self.assertRaises(Denied):self.lab.auth.verify(old,'approval',self.lab.approval.scope)

    def test_old_v4_receipt_rejected(self):
        from trusted_checker_physical.contracts import Signed
        old=Signed('capture','collector:physical',object(),'0'*64)
        with self.assertRaises(Denied):self.lab.auth.verify(old,'packets',self.lab.approval.scope)

    def test_default_off(self):
        with self.assertRaises(Denied):self.lab.verifier.begin(self.lab.clock()+2)

    def test_concurrent_measurement(self):
        self.lab.verifier.set_enabled(True); barrier=threading.Barrier(3); results=[]
        def begin():
            barrier.wait()
            try:results.append(self.lab.verifier.begin(self.lab.clock()+2))
            except Denied:results.append('denied')
        threads=[threading.Thread(target=begin) for _ in range(2)]
        for t in threads:t.start()
        barrier.wait()
        for t in threads:t.join(5);self.assertFalse(t.is_alive())
        self.assertEqual(sorted(results),sorted([self.lab.context,'denied']))

    def test_kill_and_late_success_immutable(self):
        v=self.lab.verifier;v.set_enabled(True);v.begin(self.lab.clock()+2);f=self.lab.fixture()
        v.kill();r=v.finish(f);self.assertEqual(r.reason,'counter_killed')
        v.set_enabled(True);self.assertIs(v.finish(f),r)
        with self.assertRaises(Denied):v.begin(self.lab.clock()+1)

    def test_disable_enable_epoch(self):
        v=self.lab.verifier;v.set_enabled(True);v.begin(self.lab.clock()+2);f=self.lab.fixture()
        v.set_enabled(False);v.set_enabled(True);self.assertEqual(v.finish(f).reason,'counter_killed')

    def test_deadline_exact_boundary(self):
        v=self.lab.verifier;v.set_enabled(True);v.begin(self.lab.clock()+2);f=self.lab.fixture()
        self.lab.clock.advance(1.2);r=v.finish(f)
        self.assertEqual(r.reason,'counter_deadline');self.assertEqual(r.finalized_at,r.absolute_deadline)

    def test_wall_clock_rollback(self):
        v=self.lab.verifier;v.set_enabled(True);v.begin(self.lab.clock()+2)
        self.lab.clock.advance(-1);self.assertEqual(v.finish(None).reason,'counter_clock_rollback')

    def test_monotonic_deadline_independent(self):
        v=self.lab.verifier;tick=[1.0];v.monotonic=lambda:tick[0]
        v.set_enabled(True);v.begin(self.lab.clock()+2);tick[0]=3.0
        self.assertEqual(v.finish(None).reason,'counter_deadline')

    def test_replay_verified_terminal(self):
        r=self.lab.run();self.assertIs(self.lab.verifier.finish(None),r)
        self.assertIs(self.lab.verifier.issued_report(self.lab.sign(r,'evidence')),r)

    def test_signed_but_unissued_report_not_imported(self):
        r=self.lab.run();other=self.lab.new_verifier()
        with self.assertRaises(Denied):other.issued_report(self.lab.sign(r,'evidence'))

    def test_distinct_role_keys_required(self):
        ps=list(self.lab.principals);ps[1]=replace(ps[1],key=ps[0].key)
        with self.assertRaises(Denied):FixtureAuthenticator(ps)

    def test_approval_signature_version_and_binding(self):
        from trusted_checker_network.counter_evidence import OfflineCounterVerifier
        signed=self.lab.sign(self.lab.approval,'approval')
        with self.assertRaises(Denied):OfflineCounterVerifier(self.lab.auth,replace(signed,signature='0'*64))
        for changes in ({'version':True},{'version':4},{'origin':'physical_linux'},{'dedicated_vm':False},
                        {'rules_digest':'0'*64},{'object_handles':(100,)*len(self.lab.approval.object_handles)}):
            with self.subTest(changes=changes),self.assertRaises(Denied):replace(self.lab.approval,**changes)

    def test_report_signature_and_release_flag_rejected(self):
        r=self.lab.run();signed=self.lab.sign(r,'evidence')
        with self.assertRaises(Denied):self.lab.verifier.issued_report(replace(signed,signature='0'*64))
        for changes in ({'physical_probe_permitted':True},{'continuous_attestation':True},
                        {'trace_delivery_complete':'proven'},{'result':'passed'}):
            with self.subTest(changes=changes),self.assertRaises(Denied):replace(r,**changes)

    def test_stale_future_and_overlapping_observation_windows(self):
        f=self.lab.fixture()
        from trusted_checker_network.counter_evidence import OfflineCounterVerifier
        for stamp in (self.lab.clock()+1,self.lab.clock()-10):
            with self.subTest(stamp=stamp):
                v=self.lab.new_verifier();v.set_enabled(True);v.begin(self.lab.clock()+2)
                changed=replace(f,topology_after=self.lab.sign(replace(f.topology_after.payload,observed_at=stamp),'topology'))
                self.assertEqual(v.finish(changed).result,'unknown')

    def test_expire_is_terminal_cleanup_free(self):
        v=self.lab.verifier;v.set_enabled(True);v.begin(self.lab.clock()+2)
        with self.assertRaises(Denied):v.expire()
        self.lab.clock.advance(2);r=v.expire()
        self.assertEqual(r.reason,'counter_deadline');self.assertIs(v.expire(),r)

    def test_concurrent_finish_returns_single_terminal(self):
        v=self.lab.verifier;v.set_enabled(True);v.begin(self.lab.clock()+2);f=self.lab.fixture()
        barrier=threading.Barrier(3);results=[]
        def finish():barrier.wait();results.append(v.finish(f))
        threads=[threading.Thread(target=finish) for _ in range(2)]
        for t in threads:t.start()
        barrier.wait()
        for t in threads:t.join(5);self.assertFalse(t.is_alive())
        self.assertEqual(len(results),2);self.assertIs(results[0],results[1]);self.assertEqual(results[0].result,'verified')

    def test_partial_matrix(self):
        self.unknown(lambda f:replace(f,samples=f.samples[:-1]))

    def test_overlapping_samples(self):
        def change(f):
            samples=list(f.samples);samples[1]=samples[0]
            return replace(f,samples=tuple(samples))
        self.unknown(change)

    def test_packet_loss_and_truncation(self):
        p=self.lab.fixture().samples[0].packets.payload
        for values in ({'dropped':1},{'truncated':True}):
            with self.subTest(values=values):
                # A separate fresh verifier for each fault avoids terminal masking.
                lab=CounterLab()
                try:self.assertEqual(lab.run(lambda f:lab.change_packet(f,0,lambda p:replace(p,**values))).result,'unknown')
                finally:lab.close()

    def test_recipe_no_new_allow_paths_or_historical_change(self):
        old=approved_rules(self.lab.identifier,self.lab.runtime,self.lab.binding,active=True)
        before=deepcopy(old)
        new=json.loads(self.lab.recipe.json)
        def accepts(raw):return [c['add']['rule']['expr'] for c in raw['nftables'] if 'rule' in c['add'] and c['add']['rule']['expr'][-1]=={'accept':None}]
        stripped=[[e for e in rule if 'counter' not in e] for rule in accepts(new)]
        self.assertEqual(stripped,accepts(old));self.assertEqual(old,before)
        specs=self.lab.recipe.counters
        self.assertEqual(len({s.identity for s in specs}),len(specs))
        drops=[s for s in specs if s.purpose=='terminal_drop']
        self.assertEqual(tuple(s.probe_index for s in drops),tuple(range(1,15)))
        for s in drops:
            expr=self.lab.commands[s.object_index]['add']['rule']['expr']
            self.assertTrue(all('match' in e for e in expr[:s.expression_index]))
            self.assertEqual(expr[s.expression_index+1:], [{'drop':None}])

    def test_bootstrap_recipe_drop_only(self):
        r=compile_counter_rules(self.lab.identifier,self.lab.runtime,self.lab.binding,self.lab.context,active=False)
        raw=json.loads(r.json)
        self.assertFalse(any({'accept':None} in c['add'].get('rule',{}).get('expr',[]) for c in raw['nftables']))

    def test_report_sanitized_and_bounded(self):
        r=self.lab.run();report=r.operator_report();raw=json.dumps(report,separators=(',',':'))
        forbidden={'signature','key','frame','json','credentials','stdout','stderr'}
        def check(value):
            if type(value) is dict:
                self.assertFalse(set(value)&forbidden)
                for v in value.values():check(v)
            elif type(value) in (tuple,list):
                for v in value:check(v)
        check(report)
        self.assertEqual(len(report['samples']),15)
        self.assertEqual(len(report['sample_plan']),15)
        self.assertTrue(report['topology_before_digest'])
        self.assertLess(len(raw.encode()),65536)

    def test_fresh_import_has_no_runtime_calls(self):
        code='''import socket, subprocess, os
def forbidden(*a, **k): raise AssertionError("runtime call")
socket.socket=forbidden
subprocess.Popen=forbidden
if hasattr(os,"setns"): os.setns=forbidden
import trusted_checker_network.counter_evidence
import trusted_checker_network.counter_readback
import trusted_checker_network.counter_inventory
import sys
assert "docker" not in sys.modules and "django" not in sys.modules
'''
        subprocess.run([sys.executable,'-c',code],check=True,capture_output=True,timeout=10)

    def test_new_modules_do_not_import_legacy_writers_or_io(self):
        root=Path(__file__).parents[1]
        forbidden={'django','sandbox','achievements','roadmap','traineediary','docker','socket','subprocess','os'}
        for p in root.glob('counter_*.py'):
            for n in ast.walk(ast.parse(p.read_text())):
                names=[a.name for a in n.names] if isinstance(n,ast.Import) else [n.module or ''] if isinstance(n,ast.ImportFrom) else []
                self.assertFalse({v.split('.')[0] for v in names}&forbidden,p)
