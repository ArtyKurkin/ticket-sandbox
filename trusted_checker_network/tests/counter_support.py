"""Explicit trusted OFFLINE fixtures; no Linux/daemon simulation presented as live."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import hmac
import json

from trusted_checker_network.tests.support import NetworkLab, uuid
from trusted_checker_network.collector import PacketEvent
from trusted_checker_network.counter_auth import FixturePrincipal, FixtureAuthenticator, SignedCounter, canonical
from trusted_checker_network.counter_contracts import CounterApproval, ReadbackFixture, PacketFixture
from trusted_checker_network.counter_inventory import ControlModel, TopologyObservation, expected_paths
from trusted_checker_network.counter_rules import compile_counter_rules, sample_plan
from trusted_checker_network.counter_evidence import OfflineCounterVerifier, MeasurementFixture, SampleFixture
from trusted_checker_network.packets import ipv4_frame


class CounterLab:
    def __init__(self):
        self.base = NetworkLab(); self.clock = self.base.clock
        self.runtime, self.binding = self.base.runtime_approval, self.base.binding
        self.context, self.identifier = uuid(), uuid()
        self.recipe = compile_counter_rules(self.identifier, self.runtime, self.binding, self.context)
        self.commands = json.loads(self.recipe.json)['nftables']
        self.approval = CounterApproval(self.identifier, self.context, 'operator:counter', self.runtime, self.binding,
            ControlModel('7'*64, uuid(), ('daemon:fixture', 'installer:fixture')), uuid(), 1,
            tuple(range(100, 100+len(self.commands))), self.recipe.digest, self.clock(), self.clock()+1000)
        self.principals = tuple(FixturePrincipal(role+':counter', role, self.approval.scope, bytes([i])*32)
            for i,role in enumerate(('operator', 'reader', 'packet', 'observer', 'validator'), 60))
        self.auth = FixtureAuthenticator(self.principals)
        self.verifier = self.new_verifier()
        self.probes = sample_plan(self.binding, self.context)

    def close(self): self.base.close()

    def sign(self, payload, kind):
        role = {'approval':'operator', 'readback':'reader', 'packets':'packet', 'topology':'observer', 'evidence':'validator'}[kind]
        p = next(p for p in self.principals if p.role == role)
        return SignedCounter(kind, p.name, payload,
            hmac.new(p.key, canonical(kind, p.name, payload), hashlib.sha256).hexdigest())

    def new_verifier(self):
        return OfflineCounterVerifier(self.auth, self.sign(self.approval, 'approval'), clock=self.clock, monotonic=self.clock)

    def readback(self, counters, when):
        items = [deepcopy(c['add']) for c in self.commands]
        for i,item in enumerate(items): next(iter(item.values()))['handle'] = self.approval.object_handles[i]
        for s in self.recipe.counters:
            p,b = counters.get(s.identity, (0, 0))
            items[s.object_index]['rule']['expr'][s.expression_index]['counter'] = {'packets':p, 'bytes':b}
        return ReadbackFixture(self.context, self.approval.scope, self.approval.digest,
            self.approval.install_epoch_uuid, 1, when, when, json.dumps({'nftables':items}))

    def topology(self, when):
        return TopologyObservation(self.context, self.approval.scope, self.binding.digest,
            self.approval.control.writer_epoch_uuid, self.approval.control.review_digest, when,
            self.binding, expected_paths(self.binding, self.runtime.network.subnet))

    def fixture(self, flags=20):
        started = self.clock(); counters = {}; samples = []
        for index,probe in enumerate(self.probes):
            t = started+index*.05+.001
            before = self.readback(counters, t)
            stages = ('send','ingress','target_ingress','response','runner_receive') if index == 0 else ('send','ingress')
            response = ipv4_frame(self.binding.target.mac, self.binding.runner.mac, self.binding.target.ipv4,
                self.binding.runner.ipv4, 8080, probe.sequence, flags=flags, reverse=True)
            events = tuple(PacketEvent(i+1, probe.probe_id, stage,
                self.binding.target.interface if stage in ('target_ingress','response') else self.binding.runner.interface,
                response if stage in ('response','runner_receive') else probe.frame, t+.01,
                self.recipe.digest, 1) for i,stage in enumerate(stages))
            packet = PacketFixture(self.context, self.approval.scope, self.approval.digest,
                self.approval.install_epoch_uuid, 1, index, t+.005, t+.02, events)
            # This fixed fixture knows the intended four existing TCP allow rules.
            for s in self.recipe.counters:
                amount = None
                if s.probe_index == index: amount = len(probe.frame)
                elif index == 0 and s.purpose == 'allow':
                    rule = self.commands[s.object_index]['add']['rule']
                    field = [e.get('match',{}).get('left',{}).get('payload',{}).get('field') for e in rule['expr']]
                    if 'dport' in field: amount = len(probe.frame)
                    elif 'sport' in field: amount = len(response)
                if amount is not None:
                    p,b = counters.get(s.identity, (0,0)); counters[s.identity] = p+1,b+amount
            after = self.readback(counters, t+.03)
            samples.append(SampleFixture(self.sign(before,'readback'), self.sign(packet,'packets'), self.sign(after,'readback')))
        self.clock.advance(.8)
        return MeasurementFixture(self.sign(self.topology(started),'topology'), tuple(samples),
                                  self.sign(self.topology(self.clock()),'topology'))

    def run(self, modify=None, flags=20):
        self.verifier.set_enabled(True); self.verifier.begin(self.clock()+2)
        fixture = self.fixture(flags)
        if modify: fixture = modify(fixture)
        return self.verifier.finish(fixture)

    def change_read(self, fixture, index, side, change):
        sample = fixture.samples[index]; observation = getattr(sample, side).payload
        raw = json.loads(observation.json); change(raw)
        observation = replace(observation, json=json.dumps(raw))
        sample = replace(sample, **{side:self.sign(observation,'readback')})
        samples = list(fixture.samples); samples[index] = sample
        return replace(fixture, samples=tuple(samples))

    def change_packet(self, fixture, index, change):
        samples = list(fixture.samples); sample = samples[index]
        samples[index] = replace(sample, packets=self.sign(change(sample.packets.payload),'packets'))
        return replace(fixture, samples=tuple(samples))
