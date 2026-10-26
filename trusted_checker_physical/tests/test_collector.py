from dataclasses import replace
import struct
import unittest
from trusted_checker_runtime.profiles import Denied
from trusted_checker_physical.collector import CollectionReport,PhysicalProbeGate,CollectorSealer,physical_plan
from trusted_checker_physical.trace import decode_kernel
from trusted_checker_physical.packet_io import packet_read,packet_statistics,peer_arp_request,approved_peer_arp
from .support import Lab,uuid,trace_packet,nla


class CollectorTests(unittest.TestCase):
    def setUp(self):self.l=Lab();self.addCleanup(self.l.close)
    def measure(self):return self.l.collector.measure(uuid(),self.l.budget())
    def test_rst_and_full_observations_still_no_continuity_success(self):
        l=self.l;l.active();r=self.measure()
        self.assertEqual(r.observations[0],'path_open_rst');self.assertEqual(len(r.observations),15)
        self.assertEqual(r.reason,'native_nftrace_continuity_unproven');self.assertEqual(r.result,'unknown')
        self.assertFalse(r.probe_permitted);self.assertTrue(l.packets.closed);self.assertTrue(l.journal.stopped())
        with self.assertRaises(Denied):PhysicalProbeGate.permit(r)
    def test_synack_is_distinct_from_timeout(self):
        l=self.l;l.active();l.packets.rst=False;r=self.measure()
        self.assertEqual(r.observations[0],'path_open_synack');self.assertEqual(r.result,'unknown')
    def test_timeout_not_a_drop(self):
        l=self.l;l.active();l.packets.modify=lambda rows:rows[:1]
        r=self.measure();self.assertEqual(r.reason,'physical_allow_chain_incomplete');self.assertEqual(len(l.packets.sent),1)
    def test_missing_kernel_drop_trace(self):
        l=self.l;l.active();l.packets.modify=lambda rows:[r for r in rows if not(r[0]=='trace' and decode_kernel(r[1],r[2])[0].verdict==0)]
        r=self.measure();self.assertEqual(r.reason,'physical_drop_trace_missing');self.assertFalse(r.probe_permitted)
    def test_forged_kernel_sender(self):
        l=self.l;l.active()
        l.packets.modify=lambda rows:[(role,raw,(999,256) if role=='trace' else addr) for role,raw,addr in rows]
        r=self.measure();self.assertEqual(r.reason,'physical_kernel_event_not_kernel')
    def test_foreign_kernel_table(self):
        l=self.l;l.active()
        def modify(rows):
            if len(l.packets.sent)>1:
                rows[1]=('trace',trace_packet(l,l.packets.probe,77,foreign=True),(0,256))
            return rows
        l.packets.modify=modify
        self.assertEqual(self.measure().reason,'physical_foreign_kernel_hook')
    def test_stale_generation_packet(self):
        l=self.l;l.active()
        def modify(rows):
            if len(l.packets.sent)>1:
                stale=physical_plan(l.binding,uuid())[1]
                rows[1]=('trace',trace_packet(l,stale,77),(0,256))
            return rows
        l.packets.modify=modify
        self.assertEqual(self.measure().reason,'physical_foreign_kernel_packet')
    def test_spoofed_source_response(self):
        l=self.l;l.active()
        def spoof(rows):return [(role,(b'\x00'+raw[1:]) if role=='runner' else raw,addr) for role,raw,addr in rows]
        l.packets.modify=spoof;r=self.measure()
        self.assertEqual(r.result,'unknown');self.assertFalse(r.probe_permitted)
    def test_capture_loss_no_receipt_success(self):
        l=self.l;l.active();l.packets.loss=True
        self.assertEqual(self.measure().reason,'physical_packet_capture_loss')
    def test_kill_during_capture_no_next_packet(self):
        l=self.l;l.active();l.packets.modify=lambda rows:(l.journal.stop() or rows)
        r=self.measure();self.assertEqual(r.reason,'physical_capture_killed');self.assertEqual(len(l.packets.sent),1)
    def test_deadline_during_capture_no_resume(self):
        l=self.l;l.active();budget=l.budget(.15)
        report=l.collector.measure(uuid(),budget)
        self.assertEqual(report.result,'unknown');self.assertLess(len(l.packets.sent),15)
        with self.assertRaises(Denied):budget.remaining()
    def test_duplicate_collection_returns_history_no_send(self):
        l=self.l;l.active();key=uuid();first=l.collector.measure(key,l.budget());count=len(l.packets.sent)
        second=l.collector.measure(key,l.budget());self.assertEqual(first,second);self.assertEqual(count,len(l.packets.sent))
    def test_bootstrap_only_denies_injection(self):
        l=self.l;l.install('bootstrap');r=self.measure()
        self.assertEqual(r.result,'unknown');self.assertEqual(l.packets.sent,[])
    def test_default_off_denies_before_capture(self):
        l=self.l;l.activation.enabled=False
        with self.assertRaises(Denied):self.measure()
        self.assertEqual(l.packets.sent,[]);self.assertEqual(l.io.calls,[])
    def test_mock_evidence_cannot_become_physical_success(self):
        l=self.l;l.active();report=self.measure()
        with self.assertRaises(Denied):replace(report,matrix_complete=True,probe_permitted=True,result='passed')
        with self.assertRaises(Denied):PhysicalProbeGate.permit(replace(report,origin='physical_linux'))
    def test_capture_authentication_origin_and_roles(self):
        l=self.l;l.active();report=self.measure()
        principal=next(p for p in l.principals if p.role=='collector')
        sealer=CollectorSealer(l.activation,l.journal,principal);signed=sealer.seal(report)
        self.assertEqual(l.auth.verify(signed,'capture',CollectionReport),report)
        with self.assertRaises(Denied):l.auth.verify(replace(signed,signature='0'*64),'capture',CollectionReport)
        with self.assertRaises(Denied):sealer.seal(replace(report,origin='physical_linux'))
        with self.assertRaises(Denied):l.auth.verify(replace(signed,principal='observer:physical'),'capture',CollectionReport)
    def test_no_packets_or_keys_in_report_journal(self):
        l=self.l;l.active();r=self.measure()
        with l.journal.transaction() as db:
            raw='\n'.join(row[0] for row in db.execute('SELECT body FROM docs'))
        self.assertNotIn('frame',raw);self.assertNotIn('signature',raw);self.assertNotIn('body_b64',raw)
        self.assertNotIn(l.principals[0].key.hex(),raw)


class TraceTests(unittest.TestCase):
    def setUp(self):self.l=Lab();self.addCleanup(self.l.close)
    def test_native_trace_packet_then_policy_drop(self):
        l=self.l;probe=physical_plan(l.binding,uuid())[1]
        first=decode_kernel(trace_packet(l,probe,123),(0,256))[0]
        drop=decode_kernel(trace_packet(l,probe,123,drop=True),(0,256))[0]
        self.assertEqual(first.frame,probe.frame);self.assertEqual(drop.trace_id,first.trace_id)
        self.assertEqual(drop.verdict,0);self.assertIsNone(drop.frame);self.assertFalse(drop.continuity_proven)
    def test_invalid_header_pid_seq_family_and_type(self):
        l=self.l;probe=physical_plan(l.binding,uuid())[1];raw=trace_packet(l,probe,1)
        for offset,value in ((4,b'\x03\x00'),(8,b'\x01\x00\x00\x00'),(12,b'\x01\x00\x00\x00'),(16,b'\x02')):
            with self.subTest(offset=offset),self.assertRaises(Denied):decode_kernel(raw[:offset]+value+raw[offset+len(value):],(0,256))
        with self.assertRaises(Denied):decode_kernel(raw,(99,256))
    def test_duplicate_and_truncated_attributes(self):
        l=self.l;probe=physical_plan(l.binding,uuid())[1];raw=trace_packet(l,probe,1)
        with self.assertRaises(Denied):decode_kernel(raw[:-1],(0,256))
        extra=nla(6,struct.pack('=I',1));changed=struct.pack('=I',len(raw)+len(extra))+raw[4:]+extra
        with self.assertRaises(Denied):decode_kernel(changed,(0,256))
    def test_packet_stats_drop_and_truncation(self):
        from unittest.mock import Mock
        sock=Mock();sock.getsockopt.return_value=struct.pack('=II',100,1)
        with self.assertRaises(Denied):packet_statistics(sock)
        sock.recvmsg.return_value=(b'x'*129,[],0,('eth0',3,0))
        with self.assertRaises(Denied):packet_read(sock)
        sock.recvmsg.return_value=(b'x'*54,[(263,8,struct.pack('=IIIHHHH',4,54,54,0,14,0,0))],0,('eth0',3,0))
        with self.assertRaises(Denied):packet_read(sock)
    def test_udp_nonce_is_bound_in_kernel_transport_dump(self):
        l=self.l;probes=physical_plan(l.binding,uuid());other=physical_plan(l.binding,uuid())
        for index in (9,13):
            self.assertNotEqual(probes[index].frame,other[index].frame)
            self.assertEqual(decode_kernel(trace_packet(l,probes[index],99),(0,256))[0].frame,probes[index].frame)
    def test_spoofed_ip_and_mac_are_fixed_header_probes(self):
        l=self.l;probes=physical_plan(l.binding,uuid())
        self.assertNotEqual(probes[13].frame[6:12],bytes.fromhex(l.binding.runner.mac.replace(':','')))
        self.assertEqual(probes[13].frame[12:14],b'\x81\x00')
        self.assertEqual(probes[12].frame[26:30],b'\xac\x1f\xff\xfe')
    def test_arp_is_only_the_approved_peer_pair(self):
        raw=peer_arp_request(self.l.binding)
        self.assertEqual(len(raw),42);self.assertTrue(approved_peer_arp(raw,self.l.binding))
        with self.assertRaises(Denied):approved_peer_arp(raw[:22]+b'\x00'*6+raw[28:],self.l.binding)
