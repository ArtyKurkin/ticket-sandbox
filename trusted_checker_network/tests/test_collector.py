from dataclasses import replace
import json
from pathlib import Path
import unittest
from trusted_checker_runtime.profiles import Denied
from trusted_checker_network.auth import NetworkVerifier
from trusted_checker_network.collector import MatrixReceipt
from trusted_checker_network.contracts import CASES
from trusted_checker_network.packets import plan
from .support import NetworkLab,uuid
from trusted_checker_network.packets import checksum,classify_reply,ipv4_frame,unpad
import struct


class CollectorTests(unittest.TestCase):
    def setUp(self):self.l=NetworkLab();self.addCleanup(self.l.close)

    def test_broken_rst_and_fixed_synack_full_matrix(self):
        l=self.l;l.active()
        for flags,expected in ((20,'path_open_rst'),(18,'path_open_synack')):
            l.response_flags=flags
            signed=l.measure();receipt=l.verifier.verify(signed,'matrix',MatrixReceipt,l.scope)
            self.assertEqual(receipt.cases,CASES);self.assertEqual(receipt.outcomes[0],expected)
            self.assertEqual(receipt.outcomes[1:],('blocked_at_hook',)*14)

    def fail_capture(self,modifier):
        l=self.l;l.active();l.modify_capture=modifier
        with self.assertRaises(Denied):l.measure()
        self.assertTrue(l.store.stopped())
        with l.store.transaction() as db:self.assertIsNone(db.execute("SELECT 1 FROM documents WHERE kind='matrix'").fetchone())

    def test_capture_packet_loss(self):self.fail_capture(lambda c:replace(c,packets_dropped=1))
    def test_capture_stats_mismatch(self):self.fail_capture(lambda c:replace(c,packets_received=0))
    def test_capture_truncated(self):self.fail_capture(lambda c:replace(c,truncated=True))
    def test_capture_netlink_loss(self):self.fail_capture(lambda c:replace(c,netlink_lost=1))
    def test_collector_error(self):self.fail_capture(lambda c:replace(c,error='collector_error'))
    def test_endpoint_unavailable(self):self.fail_capture(lambda c:replace(c,endpoint_available=False,error='endpoint_unavailable'))
    def test_generation_mismatch(self):self.fail_capture(lambda c:replace(c,generation=c.generation+1))
    def test_policy_rules_mismatch(self):self.fail_capture(lambda c:replace(c,rules_digest='0'*64))
    def test_context_mismatch(self):self.fail_capture(lambda c:replace(c,context_uuid=uuid()))
    def test_event_sequence_gap(self):
        self.fail_capture(lambda c:replace(c,events=(replace(c.events[0],sequence=3),)+c.events[1:]))

    def test_missing_negative_case(self):
        def remove(c):
            probe_id=c.events[-1].probe_id
            events=tuple(e for e in c.events if e.probe_id!=probe_id)
            return replace(c,events=events,packets_received=len(events))
        self.fail_capture(remove)

    def test_silence_without_drop_trace_is_unknown(self):
        def drop(c):
            events=c.events[:-1]
            return replace(c,events=events,packets_received=len(events))
        self.fail_capture(drop)

    def test_allowed_path_firewall_drop_not_target_rst(self):
        def blocked(c):
            events=list(c.events);events[2]=replace(events[2],stage='drop',interface=self.l.binding.runner.interface)
            return replace(c,events=tuple(events))
        self.fail_capture(blocked)

    def test_target_response_wrong_flow_or_l2_not_accepted(self):
        def corrupt(c):
            events=list(c.events)
            for index in (3,4):events[index]=replace(events[index],frame=b'\x00'+events[index].frame[1:])
            return replace(c,events=tuple(events))
        self.fail_capture(corrupt)

    def test_stale_capture(self):
        def stale(c):self.l.clock.advance(4);return c
        self.fail_capture(stale)

    def test_netns_reuse_during_capture(self):
        def reuse(c):
            b=replace(c.after.binding,runner=replace(c.after.binding.runner,netns_inode=999))
            return replace(c,after=replace(c.after,binding=b))
        self.fail_capture(reuse)

    def test_process_start_reuse_during_capture(self):
        def reuse(c):
            b=replace(c.after.binding,runner=replace(c.after.binding.runner,process_start_ticks=10003))
            return replace(c,after=replace(c.after,binding=b))
        self.fail_capture(reuse)

    def test_transient_attachment_event(self):
        self.fail_capture(lambda c:replace(c,after=replace(c.after,netlink_sequence_start=11,netlink_sequence_end=11)))

    def test_forged_capture(self):
        l=self.l;l.active();original=l.host.capture_factory
        l.host.capture_factory=lambda a,r:replace(original(a,r),signature='0'*64)
        with self.assertRaises(Denied):l.measure()

    def test_capture_other_signer_role(self):
        l=self.l;l.active();original=l.host.capture_factory
        l.host.capture_factory=lambda a,r:replace(original(a,r),principal='host:network')
        with self.assertRaises(Denied):l.measure()

    def test_kill_during_capture(self):
        l=self.l;l.active();l.host.on_capture=lambda host:l.store.stop()
        with self.assertRaises(Denied):l.measure()
        self.assertTrue(l.store.stopped())

    def test_monotonic_capture_deadline(self):
        l=self.l;l.active();times=iter((0,3))
        l.collector.monotonic=lambda:next(times)
        with self.assertRaises(Denied):l.measure()

    def test_unknown_reasons_distinguish_endpoint_and_capture(self):
        for changes,expected in (({'packets_dropped':1},'capture_loss'),
                                 ({'endpoint_available':False},'capture_endpoint_unavailable'),
                                 ({'error':'collector_error'},'capture_collector_error')):
            with self.subTest(expected=expected):
                l=NetworkLab();self.addCleanup(l.close);l.active();context=uuid()
                l.modify_capture=lambda c:replace(c,**changes)
                with self.assertRaises(Denied):l.measure(context)
                with l.store.transaction() as db:self.assertEqual(l.store.get(db,'matrix_unknown',context)['reason'],expected)

    def test_padded_frames_and_tcp_mss_reply(self):
        l=self.l
        probe=plan(l.binding,uuid())[0]
        frame=ipv4_frame(l.binding.target.mac,l.binding.runner.mac,l.binding.target.ipv4,l.binding.runner.ipv4,
                         8080,probe.sequence,reverse=True,flags=18)
        ip,tcp=bytearray(frame[14:34]),bytearray(frame[34:])
        tcp[12]=96;tcp.extend(b'\x02\x04\x05\xb4');tcp[16:18]=b'\x00\x00'
        pseudo=bytes(ip[12:20])+struct.pack('!BBH',0,6,len(tcp))
        tcp[16:18]=struct.pack('!H',checksum(pseudo+tcp))
        ip[2:4]=struct.pack('!H',44);ip[10:12]=b'\x00\x00';ip[10:12]=struct.pack('!H',checksum(bytes(ip)))
        frame=frame[:14]+bytes(ip)+bytes(tcp)
        self.assertEqual(classify_reply(probe,l.binding,frame+b'\x00'*2),'path_open_synack')
        self.assertEqual(unpad(probe.frame+b'\x00'*6),probe.frame)
        with self.assertRaises(Denied):unpad(probe.frame+b'SECRET')

    def test_all_captured_frames_may_have_ethernet_padding(self):
        l=self.l;l.active()
        def pad(c):return replace(c,events=tuple(replace(e,frame=e.frame+b'\x00'*max(0,60-len(e.frame))) for e in c.events))
        l.modify_capture=pad
        self.assertEqual(l.measure().payload.outcomes[0],'path_open_rst')

    def test_deadline_during_capture(self):
        l=self.l;l.active()
        with self.assertRaises(Denied):l.measure(deadline=l.clock()+0.5)

    def test_rules_change_during_capture(self):
        l=self.l;l.active();l.host.on_capture=lambda host:host.rules['nftables'].pop()
        with self.assertRaises(Denied):l.measure()

    def test_no_bootstrap_permission(self):
        l=self.l;l.install('bootstrap')
        with self.assertRaises(Denied):l.measure()

    def test_fixed_plan_no_arbitrary_url_or_network_injection(self):
        l=self.l;probes=plan(l.binding,uuid())
        self.assertEqual(len(probes),15);self.assertEqual(set(p.case for p in probes),set(CASES))
        self.assertEqual({p.port for p in probes if p.case=='deny_dns'},{53})
        self.assertEqual({p.port for p in probes if p.case=='deny_db_redis_django'},{5432,6379,8000})
        self.assertTrue(all(len(p.frame)<=128 for p in probes))

    def test_reports_do_not_archive_packets_or_signatures(self):
        l=self.l;l.active();signed=l.measure()
        with l.store.transaction() as db:
            raw=json.dumps([tuple(r) for r in db.execute('SELECT payload FROM documents')])
        self.assertNotIn(signed.signature,raw);self.assertNotIn('body_b64',raw)
        self.assertNotIn('packets_received',raw);self.assertNotIn('frame',raw)

    def test_roles_require_distinct_keys(self):
        l=self.l
        with self.assertRaises(Denied):NetworkVerifier((l.principals[0],replace(l.principals[1],key=l.principals[0].key)))
