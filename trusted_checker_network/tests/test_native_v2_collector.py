"""Every fault starts from a valid, explicitly synthetic capture stage."""
import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_capture_contracts as a
from trusted_checker_network import native_v2_collector as r
from trusted_checker_network import native_v2_capture_adapters as bridge
from .native_v2_collector_support import CollectorFixture2, scripts2, stamp, WALL, MONO
from .native_v2_support import uid, hd


class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = CollectorFixture2.create()
        cls.good, cls.issuer, _ = cls.f.run()
        assert cls.good.result == 'capture_preserved_in_mock_model'

    def fault(self, scripts, reason):
        value, collector, transport = self.f.run(scripts)
        self.assertEqual((value.result, value.reason), ('unknown', reason))
        self.assertIsNone(value.manifest); self.assertTrue(transport.closed)
        self.assertIs(collector.capture(), value)
        return value

    def changed_reader(self, **fields): return replace(self.f.plan.reader, **fields)

    def changed_namespace(self, **fields):
        namespaces = self.f.plan.reader.namespaces
        changed = replace(namespaces[0], **fields)
        peers = tuple(replace(p,first=changed.key) if p.first==namespaces[0].key else p
                      for p in self.f.plan.reader.peers)
        return self.changed_reader(namespaces=(changed, *namespaces[1:]),peers=peers)

    def test_complete_explicit_synthetic_capture(self):
        v = self.good
        self.assertEqual(len(v.manifest.artifacts), 30)
        self.assertTrue(all(x.stdout == b'[]' for x in v.manifest.artifacts))
        self.assertEqual(v.manifest.plan, self.f.plan)
        self.assertIs(self.issuer.validate_manifest(v.manifest), v)

    def test_default_off_has_no_transport_calls(self):
        transport = r.DeterministicMockTransport2(self.f.scripts)
        runner = r.ReadOnlyCommandRunner2(transport)
        collector = r.FencedReadOnlyCollector2(self.f.plan, self.f.plan.digest, self.f.plan.binaries.digest,
                                             runner, uid(8000), stamp())
        self.assertEqual(transport.calls, ())
        self.assertEqual(collector.capture().reason, 'disabled')
        self.assertEqual(transport.calls, ())

    def test_constructors_have_no_io_or_dispatch(self):
        collector, transport = self.f.collector()
        self.assertEqual(transport.calls, ()); self.assertFalse(transport.closed)
        self.assertEqual(collector.session.reader, self.f.plan.reader)

    def test_registry_exact_absolute_commands(self):
        self.assertEqual(len(a.OPERATIONS), 10)
        self.assertEqual(a.operation2('nft').argv, ('/usr/sbin/nft','-j','-a','list','ruleset'))
        self.assertEqual(a.operation2('route6').argv, ('/usr/sbin/ip','-j','-6','route','show','table','all'))
        for op in a.OPERATIONS:
            self.assertTrue(op.binary.startswith('/usr/')); self.assertEqual(op.argv[0], op.binary)
            self.assertEqual(op.roles, ('host','runner','target'))
            self.assertLessEqual(op.stdout_cap, 1048576); self.assertEqual(op.stderr_cap, 4096)

    def test_correct_argv_and_namespace_reference(self):
        _, _, transport = self.f.run()
        self.assertEqual(transport.calls, tuple((q.argv, q.namespace.fd_reference_uuid, q.digest)
                                               for q in self.f.plan.requests))

    def test_raw_bytes_and_stderr_preserved_exactly(self):
        script = self.f.scripts[0]
        events = (replace(script.events[0], data=b' [ ]\n'),
                  r.MockReadEvent2('stderr', stamp(1001), self.f.plan.reader, b'bounded diagnostic\n'),
                  *script.events[1:])
        value, _, _ = self.f.run(self.f.changed_script(events=events))
        artifact = value.manifest.artifacts[0]
        self.assertEqual(artifact.stdout, b' [ ]\n'); self.assertEqual(artifact.stderr, b'bounded diagnostic\n')
        self.assertEqual(artifact.stdout_sha256, hashlib.sha256(b' [ ]\n').hexdigest())
        self.assertEqual(artifact.stdout_byte_count, 5)
        self.assertEqual(artifact.stderr_category, 'bounded_stderr_present')
        self.assertNotIn('bounded diagnostic', repr(artifact))

    def test_zero_byte_stdout_distinct_from_empty_json(self):
        script = self.f.scripts[0]
        value, _, _ = self.f.run(self.f.changed_script(events=script.events[1:]))
        self.assertEqual(value.result, 'capture_preserved_in_mock_model')
        self.assertEqual(value.manifest.artifacts[0].stdout, b'')
        self.assertNotEqual(value.manifest.artifacts[0].stdout_sha256, self.good.manifest.artifacts[0].stdout_sha256)

    def test_timestamps_integer_and_utc(self):
        artifact = self.good.manifest.artifacts[0]
        self.assertTrue(artifact.started.wall_utc.endswith('+00:00'))
        self.assertLessEqual(artifact.started.monotonic_us, artifact.finished.monotonic_us)
        self.assertEqual(artifact.session.deadline_monotonic_us, MONO+2000000)

    def test_false_authority_and_unobserved_requirements(self):
        for value in (self.good, self.good.manifest, self.good.manifest.artifacts[0], self.f.plan):
            for key in ('physical_probe_permitted','ownership_proven','continuous_attestation'):
                self.assertIs(getattr(value,key),False)
            self.assertEqual(value.authentication, 'not_authenticated')
        self.assertIs(self.good.isolation_verified,False); self.assertIs(self.good.management_policy_verified,False)
        self.assertIs(self.good.measurement_verified,False)
        self.assertEqual(self.good.requirements,a.UNOBSERVED)
        self.assertIn('timing_unproven', self.good.timing)

    def test_offline_domain_version_flags(self):
        for change in ({'version':1},{'version':True},{'origin':'physical'}, {'domain':'v1'},
                       {'physical_probe_permitted':True},{'ownership_proven':True}):
            with self.subTest(change=change), self.assertRaises(c.ContractViolation2): replace(self.f.plan,**change)

    def test_immutable_dtos(self):
        with self.assertRaises(FrozenInstanceError): self.good.reason = 'verified'
        with self.assertRaises(TypeError): replace(self.good,result='verified')

    def test_plan_pin_independent(self):
        with self.assertRaisesRegex(c.ContractViolation2,'pin_mismatch'):
            r.FencedReadOnlyCollector2(self.f.plan,hd('wrong'),self.f.plan.binaries.digest,
                r.ReadOnlyCommandRunner2(r.DeterministicMockTransport2(self.f.scripts)),uid(7000),stamp())

    def test_binary_manifest_pin_independent(self):
        with self.assertRaisesRegex(c.ContractViolation2,'pin_mismatch'):
            r.FencedReadOnlyCollector2(self.f.plan,self.f.plan.digest,hd('wrong'),
                r.ReadOnlyCommandRunner2(r.DeterministicMockTransport2(self.f.scripts)),uid(7000),stamp())

    def test_wrong_binary_hash(self):
        binary = replace(self.f.scripts[0].observed_binary,binary_sha256=hd('wrong'))
        self.fault(self.f.changed_script(observed_binary=binary),'binary_mismatch')

    def test_wrong_binary_path(self):
        binary = replace(self.f.scripts[0].observed_binary,path='/usr/sbin/ip')
        self.fault(self.f.changed_script(observed_binary=binary),'binary_mismatch')

    def test_version_text_not_build_proof(self):
        binary = replace(self.f.scripts[0].observed_binary,source_manifest_digest=hd('wrong-source'))
        self.fault(self.f.changed_script(observed_binary=binary),'binary_mismatch')

    def test_wrong_protection_reference(self):
        binary = replace(self.f.scripts[0].observed_binary,protection_review_digest=hd('wrong-protection'))
        self.fault(self.f.changed_script(observed_binary=binary),'binary_mismatch')

    def test_changed_principal_before(self):
        self.fault(self.f.changed_script(before=self.changed_reader(reader_principal_digest=hd('intruder'))),
                   'identity_changed')

    def test_changed_principal_during_stream(self):
        self.fault(self.f.changed_event(reader=self.changed_reader(reader_principal_digest=hd('intruder'))),
                   'identity_changed')

    def test_changed_principal_after_exit(self):
        self.fault(self.f.changed_event(-1,reader=self.changed_reader(reader_principal_digest=hd('intruder'))),
                   'identity_changed')

    def test_namespace_replacement(self):
        ns = self.f.plan.reader.namespaces[0]
        reader = self.changed_namespace(key=replace(ns.key,namespace_binding_generation=2))
        self.fault(self.f.changed_event(reader=reader),'identity_changed')

    def test_wrong_session_scoped_nsid_mapping(self):
        namespaces=self.f.plan.reader.namespaces
        changed=replace(namespaces[0],nsid_mappings=((20,101),(21,102)))
        peers=tuple(replace(p,first_nsid=20+i) for i,p in enumerate(self.f.plan.reader.peers))
        reader=self.changed_reader(namespaces=(changed,*namespaces[1:]),peers=peers)
        self.fault(self.f.changed_event(reader=reader),'identity_changed')

    def test_missing_reciprocal_peer_witness(self):
        namespaces=self.f.plan.reader.namespaces
        reader = self.changed_reader(namespaces=(replace(namespaces[0],reciprocal_peer_reference_digests=()),
                                                 *namespaces[1:]),peers=())
        self.fault(self.f.changed_event(reader=reader),'identity_changed')

    def test_lost_namespace_fd(self):
        self.fault(self.f.changed_event(reader=self.changed_namespace(fd_state='lost_in_mock_model')),
                   'namespace_fd_lost')

    def test_replaced_namespace_fd_reference(self):
        self.fault(self.f.changed_event(reader=self.changed_namespace(fd_reference_uuid=uid(7777))),
                   'identity_changed')

    def test_pid_reuse_with_new_start_ticks(self):
        self.fault(self.f.changed_event(reader=self.changed_namespace(process_start_ticks=20000)),
                   'identity_changed')

    def test_pid_replaced(self):
        self.fault(self.f.changed_event(-1,reader=self.changed_namespace(lookup_pid=444)), 'identity_changed')

    def test_writer_epoch_drift(self):
        self.fault(self.f.changed_event(reader=self.changed_reader(writer_epoch_uuid=uid(7778))),
                   'identity_changed')

    def test_configuration_drift(self):
        self.fault(self.f.changed_event(reader=self.changed_reader(configuration_digest=hd('changed'))),
                   'identity_changed')

    def test_role_principals_cannot_be_same(self):
        with self.assertRaisesRegex(c.ContractViolation2,'duplicate'):
            self.changed_reader(reader_principal_digest=self.f.plan.reader.writer_principal_digest)

    def test_nonzero_exit(self):
        self.fault(self.f.changed_event(-2,exit_status=1),'nonzero_exit')

    def test_missing_source(self): self.fault((), 'missing_source')

    def test_partial_plan_sources_not_implied_empty(self):
        value, _, _ = self.f.run(self.f.scripts[:-1])
        self.assertEqual(value.reason,'missing_source'); self.assertIsNone(value.manifest)

    def test_truncated_stdout(self):
        self.fault(self.f.changed_event(kind='truncated',data=b''),'transport_incomplete')

    def test_missing_completion_event(self):
        self.fault(self.f.changed_script(events=self.f.scripts[0].events[:-1]),'transport_incomplete')

    def test_missing_stdout_eof(self):
        events=tuple(e for e in self.f.scripts[0].events if e.kind!='stdout_eof')
        self.fault(self.f.changed_script(events=events),'transport_incomplete')

    def test_missing_stderr_eof(self):
        events=tuple(e for e in self.f.scripts[0].events if e.kind!='stderr_eof')
        self.fault(self.f.changed_script(events=events),'transport_incomplete')

    def test_duplicate_eof(self):
        events=self.f.scripts[0].events
        self.fault(self.f.changed_script(events=(events[0],events[1],events[1],*events[2:])),'stream_invalid')

    def test_output_after_eof(self):
        events=self.f.scripts[0].events
        self.fault(self.f.changed_script(events=(events[0],events[1],replace(events[0],at=events[1].at),*events[2:])),
                   'stream_invalid')

    def test_data_after_completion(self):
        events=self.f.scripts[0].events
        self.fault(self.f.changed_script(events=(*events,replace(events[0],at=stamp(1200)))),'stream_invalid')

    def test_untrusted_complete_boolean_is_only_stdout(self):
        value, _, _ = self.f.run(self.f.changed_event(data=b'{"complete":true}'))
        self.assertEqual(value.manifest.artifacts[0].stdout,b'{"complete":true}')
        self.fault(self.f.changed_script(events=(replace(self.f.scripts[0].events[0],data=b'{"complete":true}'),)),
                   'transport_incomplete')

    def test_oversized_stdout(self):
        script=self.f.scripts[0]
        raw=b'x'*(a.operation2('nft').stdout_cap+1)
        events=tuple(r.MockReadEvent2('stdout',stamp(1000+i),self.f.plan.reader,raw[pos:pos+a.CHUNK_BYTES])
                     for i,pos in enumerate(range(0,len(raw),a.CHUNK_BYTES)))
        self.fault(self.f.changed_script(events=events),'stdout_limit')

    def test_oversized_stderr(self):
        self.fault(self.f.changed_event(kind='stderr',data=b'x'*4097),'stderr_limit')

    def test_transport_cannot_return_more_than_requested_chunk(self):
        self.fault(self.f.changed_event(data=b'x'*(a.CHUNK_BYTES+1)),'stream_invalid')

    def test_timeout_signal(self):
        self.fault(self.f.changed_event(kind='timeout',data=b''),'timeout')

    def test_per_command_time_cap(self):
        self.fault(self.f.changed_event(at=stamp(501001)),'timeout')

    def test_global_two_second_cap(self):
        self.fault(self.f.changed_script(started=stamp(2000001)),'timing_unproven')

    def test_wall_forward_jump(self):
        self.fault(self.f.changed_event(at=a.CaptureTime2(WALL+2000001,MONO+1000)),'timing_unproven')

    def test_interrupted_capture(self):
        self.fault(self.f.changed_event(kind='interrupted',data=b''),'interrupted')

    def test_unexpected_process_death(self):
        self.fault(self.f.changed_event(kind='process_died',data=b''),'process_died')

    def test_wall_clock_rollback(self):
        self.fault(self.f.changed_event(at=a.CaptureTime2(WALL+999,MONO+1000)),'clock_rollback')

    def test_monotonic_clock_rollback(self):
        self.fault(self.f.changed_event(at=a.CaptureTime2(WALL+1000,MONO+999)),'clock_rollback')

    def test_duplicate_capture_plan_identity(self):
        with self.assertRaisesRegex(c.ContractViolation2,'duplicate'):
            replace(self.f.plan,requests=(self.f.plan.requests[0],self.f.plan.requests[0]))

    def test_duplicate_transport_script(self):
        with self.assertRaisesRegex(c.ContractViolation2,'duplicate'):
            r.DeterministicMockTransport2((self.f.scripts[0],self.f.scripts[0]))

    def test_duplicate_artifact_manifest(self):
        with self.assertRaisesRegex(c.ContractViolation2,'source_coverage_incomplete'):
            replace(self.good.manifest,artifacts=(self.good.manifest.artifacts[0],)*30)

    def test_partial_manifest(self):
        with self.assertRaisesRegex(c.ContractViolation2,'source_coverage_incomplete'):
            replace(self.good.manifest,artifacts=self.good.manifest.artifacts[:-1])

    def test_source_substitution(self):
        script=replace(self.f.scripts[0],request=self.f.plan.requests[1])
        self.fault((script,*self.f.scripts[2:]),'missing_source')

    def test_manifest_coherent_but_not_issued(self):
        candidate=replace(self.good.manifest)
        with self.assertRaisesRegex(c.ContractViolation2,'receipt_unissued'):self.issuer.validate_manifest(candidate)

    def test_capture_replay_other_collector(self):
        value, collector, _=self.f.run()
        self.assertIsNot(value,self.good)
        with self.assertRaisesRegex(c.ContractViolation2,'result_unissued'):collector.admit_for_parsing(self.good)

    def test_forged_result_constructor_cannot_be_admitted(self):
        forged=replace(self.good)
        with self.assertRaisesRegex(c.ContractViolation2,'result_unissued'):self.issuer.admit_for_parsing(forged)

    def test_forged_completion_receipt_digest(self):
        artifact=self.good.manifest.artifacts[0]
        with self.assertRaisesRegex(c.ContractViolation2,'receipt_mismatch'):
            replace(artifact,completion=replace(artifact.completion,stdout_sha256=hd('forged')))

    def test_forged_stdout_with_old_receipt(self):
        with self.assertRaisesRegex(c.ContractViolation2,'receipt_mismatch'):
            replace(self.good.manifest.artifacts[0],stdout=b'forged')

    def test_forged_metadata_namespace(self):
        artifact=self.good.manifest.artifacts[0]
        changed=replace(artifact.request,namespace=self.f.plan.reader.namespaces[1])
        with self.assertRaisesRegex(c.ContractViolation2,'receipt_mismatch'):replace(artifact,request=changed)

    def test_reuse_runner_does_not_replay(self):
        collector, _=self.f.collector()
        first=collector.capture()
        self.assertIs(collector.capture(),first)
        runner=collector._runner
        other=r.FencedReadOnlyCollector2(self.f.plan,self.f.plan.digest,self.f.plan.binaries.digest,
                                         runner,uid(4000),stamp(),enabled=True)
        self.assertEqual(other.capture().result,'unknown')

    def test_terminal_immutable_after_kill(self):
        value, collector, _=self.f.run()
        self.assertIs(collector.kill(),value);self.assertIs(collector.capture(),value)
        with self.assertRaisesRegex(c.ContractViolation2,'result_unissued'):collector.admit_for_parsing(value)

    def test_kill_before_dispatch(self):
        collector, transport=self.f.collector()
        terminal=collector.kill()
        self.assertIs(collector.capture(),terminal);self.assertEqual(terminal.reason,'killed')
        self.assertEqual(transport.calls,())

    def test_concurrent_entry_fenced(self):
        collector, _=self.f.collector()
        collector._lock.acquire()
        try:
            with self.assertRaisesRegex(c.ContractViolation2,'capture_busy'):collector.capture()
        finally:collector._lock.release()
        self.assertEqual(collector.capture().result,'capture_preserved_in_mock_model')

    def test_kill_before_publication_cannot_be_overwritten(self):
        collector,_=self.f.collector()
        original=r.ReadOnlyCommandRunner2._owns
        def kill_before_publish(runner,artifacts):
            collector.kill()
            return original(runner,artifacts)
        with patch.object(r.ReadOnlyCommandRunner2,'_owns',kill_before_publish):value=collector.capture()
        self.assertEqual(value.reason,'killed');self.assertIs(value,collector.capture())

    def test_binary_version_utf8_bounded_with_finite_error(self):
        for version in ('x'*129,'\ud800','é'*100):
            with self.subTest(version=repr(version)),self.assertRaisesRegex(c.ContractViolation2,'binary_version_invalid'):
                replace(self.f.plan.binaries.binaries[0],build_version=version)

    def test_malicious_argv(self):
        self.fault(self.f.changed_script(observed_argv=('/usr/sbin/nft','flush','ruleset')),'binary_mismatch')

    def test_shell_injection_argv(self):
        self.fault(self.f.changed_script(observed_argv=('/bin/sh','-c','nft; echo injected')),'binary_mismatch')

    def test_dynamic_namespace_names_not_api(self):
        with self.assertRaises(TypeError):a.CaptureRequest2(uid(9000),self.f.plan.reader.namespaces[0],
                                           'link',hd('profile'),namespace_name='x; bad')

    def test_unknown_operation_forbidden(self):
        for source in ('nft_apply','cleanup','setns','docker','packet_send','link; bad','*'):
            with self.subTest(source=source),self.assertRaises(c.ContractViolation2):a.operation2(source)

    def test_arbitrary_executable_forbidden(self):
        with self.assertRaises(c.ContractViolation2):replace(self.f.scripts[0].observed_binary,path='/tmp/ip')

    def test_generic_or_native_transport_forbidden(self):
        with self.assertRaisesRegex(c.ContractViolation2,'os_backend_dormant'):r.ReadOnlyCommandRunner2(object())
        class Subclass(r.DeterministicMockTransport2): pass
        with self.assertRaisesRegex(c.ContractViolation2,'os_backend_dormant'):r.ReadOnlyCommandRunner2(Subclass(()))

    def test_boolean_not_integer_time_or_exit(self):
        for make in (lambda:a.CaptureTime2(True,1),lambda:a.CaptureTime2(WALL,True),
                     lambda:replace(self.f.scripts[0].events[-2],exit_status=True)):
            with self.subTest(make=make),self.assertRaises(c.ContractViolation2):make()

    def test_no_deadline_extension(self):
        with self.assertRaisesRegex(c.ContractViolation2,'deadline_invalid'):
            replace(self.good.session,deadline_monotonic_us=MONO+2000001)

    def test_peer_nsid_contradiction_rejected_before_capture(self):
        with self.assertRaisesRegex(c.ContractViolation2,'peer_invalid'):
            self.changed_reader(peers=(replace(self.f.plan.reader.peers[0],first_nsid=30),))

    def test_peer_same_namespace_is_not_identity(self):
        p=self.f.plan.reader.peers[0]
        with self.assertRaisesRegex(c.ContractViolation2,'peer_invalid'):replace(p,second=p.first)

    def test_peer_endpoint_substitution_during_read(self):
        peers=self.f.plan.reader.peers
        reader=self.changed_reader(peers=(replace(peers[0],first_ifindex=555),*peers[1:]))
        self.fault(self.f.changed_event(reader=reader),'identity_changed')

    def test_explicit_os_surfaces_scoped_unobserved(self):
        self.assertEqual(len(self.good.evidence_statuses),54)
        self.assertTrue(all(s.status=='unsupported_unobserved' for s in self.good.evidence_statuses))
        self.assertEqual({s.namespace_reference_digest for s in self.good.evidence_statuses},
                         {n.reference_digest for n in self.f.plan.reader.namespaces})
        with self.assertRaisesRegex(c.ContractViolation2,'os_evidence_unproven'):
            replace(self.good.evidence_statuses[0],status='verified')

    def test_unknown_attempt_does_not_auto_retry(self):
        value,collector,transport=self.f.run(self.f.changed_event(kind='interrupted',data=b''))
        calls=transport.calls
        for _ in range(3):self.assertIs(collector.capture(),value)
        self.assertEqual(transport.calls,calls)

    def test_lost_completion_cannot_be_repaired_by_late_data(self):
        collector,transport=self.f.collector(self.f.changed_script(events=self.f.scripts[0].events[:-1]))
        terminal=collector.capture()
        transport._scripts=self.f.scripts
        self.assertIs(collector.capture(),terminal)
        self.assertEqual(terminal.reason,'transport_incomplete')

    def test_matching_receipt_copy_still_needs_issued_objects(self):
        original=self.good.manifest.artifacts[0]
        forged=replace(original,completion=replace(original.completion))
        manifest=replace(self.good.manifest,artifacts=(forged,*self.good.manifest.artifacts[1:]))
        with self.assertRaisesRegex(c.ContractViolation2,'receipt_unissued'):
            self.issuer.validate_manifest(manifest)

    def test_failure_categories_never_contain_stderr(self):
        events=(r.MockReadEvent2('stderr',stamp(1000),self.f.plan.reader,b'PRIVATE STDERR'),
                r.MockReadEvent2('process_died',stamp(1010),self.f.plan.reader))
        value=self.fault(self.f.changed_script(events=events),'process_died')
        self.assertNotIn('PRIVATE',repr(value));self.assertIsNone(value.manifest)

    def test_registry_and_inventory_purpose_are_pinned(self):
        for fields in ({'registry_digest':hd('other')},{'purpose':'packet_measurement'}):
            with self.subTest(fields=fields),self.assertRaises(c.ContractViolation2):replace(self.f.plan,**fields)

    def test_coherent_new_install_does_not_accept_previous_manifest(self):
        install=replace(self.f.plan.installation,install_generation=2)
        plan=replace(self.f.plan,installation=install)
        fixture=CollectorFixture2(plan,self.f.raw_documents,scripts2(plan,self.f.raw_documents))
        _,collector,_=fixture.run()
        with self.assertRaisesRegex(c.ContractViolation2,'receipt_unissued'):
            collector.validate_manifest(self.good.manifest)

    def test_physical_gate_closed_for_all_new_stages(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        for value in (self.good,self.good.manifest,self.good.manifest.artifacts[0],self.good.session):
            with self.subTest(value=type(value).__name__),self.assertRaisesRegex(Denied,'physical_network_boundary_not_accepted'):
                PhysicalProbeGate.permit(value)


class AggregateTests(unittest.TestCase):
    def test_aggregate_includes_stdout_and_stderr_before_buffering(self):
        base=CollectorFixture2.create()
        requests=tuple(q for q in base.plan.requests if q.source!='nft')
        plan=replace(base.plan,requests=requests)
        raw=tuple(b'x'*1048576 for _ in requests)
        fixture=CollectorFixture2(plan,raw,scripts2(plan,raw))
        value,_,transport=fixture.run()
        self.assertEqual(value.reason,'aggregate_limit');self.assertIsNone(value.manifest)
        self.assertEqual(len(transport.calls),17)

    def test_command_document_and_script_cardinality_bounds(self):
        f=CollectorFixture2.create()
        with self.assertRaises(c.ContractViolation2):replace(f.plan,requests=f.plan.requests*9)
        with self.assertRaises(c.ContractViolation2):replace(f.scripts[0],events=(f.scripts[0].events[0],)*4097)


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from .native_v2_readback_support import ReadbackFixture2
        cls.nft=ReadbackFixture2.create()
        raw=json.dumps(cls.nft.document(),separators=(',',':')).encode()
        cls.f=CollectorFixture2.create((('host','nft',cls.nft.expected.profile.digest,raw,uid(1000)),),
              (('host',cls.nft.context.namespace),),cls.nft.context.installation,
              {'/usr/sbin/nft':cls.nft.expected.profile.nft_binary_digest})
        cls.good,cls.collector,_=cls.f.run()

    def test_nft_bridge_only_decodes_not_recipe_validates(self):
        decoded,ref=bridge.decode_collected_nft2(self.collector,self.good,uid(1000),
                                                self.nft.expected.profile,self.nft.context)
        self.assertEqual(decoded.stage,'format_decoded')
        self.assertEqual(ref.parser_domain,'nft_v2');self.assertFalse(ref.physical_probe_permitted)

    def test_nft_identity_not_relabelled(self):
        context=replace(self.nft.context,namespace=replace(self.nft.context.namespace,namespace_binding_generation=2))
        with self.assertRaisesRegex(c.ContractViolation2,'namespace_mismatch'):
            bridge.decode_collected_nft2(self.collector,self.good,uid(1000),self.nft.expected.profile,context)

    def test_nft_installation_not_relabelled(self):
        context=replace(self.nft.context,installation=replace(self.nft.context.installation,install_generation=2))
        with self.assertRaisesRegex(c.ContractViolation2,'profile_mismatch'):
            bridge.decode_collected_nft2(self.collector,self.good,uid(1000),self.nft.expected.profile,context)

    def test_unknown_native_field_still_rejected_after_capture(self):
        document=self.nft.document();document['extra']='forbidden'
        raw=json.dumps(document).encode();scripts=scripts2(self.f.plan,(raw,))
        value,collector,_=self.f.run(scripts)
        self.assertEqual(value.result,'capture_preserved_in_mock_model')
        with self.assertRaises(c.ContractViolation2):
            bridge.decode_collected_nft2(collector,value,uid(1000),self.nft.expected.profile,self.nft.context)

    def test_forged_complete_json_does_not_decode_as_nft(self):
        scripts=scripts2(self.f.plan,(b'{"complete":true}',))
        value,collector,_=self.f.run(scripts)
        with self.assertRaises(c.ContractViolation2):
            bridge.decode_collected_nft2(collector,value,uid(1000),self.nft.expected.profile,self.nft.context)

    def test_unknown_capture_uuid_refused(self):
        with self.assertRaisesRegex(c.ContractViolation2,'missing_source'):
            bridge.decode_collected_nft2(self.collector,self.good,uid(8888),self.nft.expected.profile,self.nft.context)

    def test_old_v2_receipts_not_collector_results(self):
        with self.assertRaises(c.ContractViolation2):
            bridge.decode_collected_nft2(self.collector,self.nft.validate(),uid(1000),self.nft.expected.profile,self.nft.context)

    def test_full_v203_coverage_bridge_preserves_old_limitations(self):
        from .native_v2_topology_support import TopologyFixture2
        from trusted_checker_network import native_v2_topology as topology
        t=TopologyFixture2.create();docs,expected=t.bundle()
        mapping={'vlan':'bridge_vlan','fdb':'bridge_fdb'}
        documents=tuple((next(n.role for n in t.namespaces if n.key==d.namespace),mapping.get(d.source,d.source),
                         t.profile.digest,raw,d.capture_uuid) for raw,d in docs)
        fixture=CollectorFixture2.create(documents,tuple((n.role,n.key) for n in t.namespaces),
            binary_digests={'/usr/sbin/ip':t.profile.ip_binary_digest,'/usr/sbin/bridge':t.profile.bridge_binary_digest})
        value,collector,_=fixture.run()
        decoded,refs=bridge.decode_collected_topology2(collector,value,t.profile,expected)
        self.assertEqual(len(decoded),27);self.assertEqual(len(refs),27)
        self.assertTrue(all(x.descriptor.transport=='offline_supplied_bytes_no_completeness_attestation' for x in decoded))
        envelope=topology.complete_topology2(topology.normalize_topology2(decoded,expected))
        self.assertEqual(envelope.stage,'topology_complete');self.assertFalse(envelope.physical_probe_permitted)
        # Full old-plan coverage cannot be silently reduced to the captured subset.
        partial=replace(fixture.plan,requests=fixture.plan.requests[:-1])
        bad=CollectorFixture2(partial,fixture.raw_documents[:-1],scripts2(partial,fixture.raw_documents[:-1]))
        val,col,_=bad.run()
        with self.assertRaisesRegex(c.ContractViolation2,'source_coverage_incomplete'):
            bridge.decode_collected_topology2(col,val,t.profile,expected)

    def test_native61_bridge_retains_unrecorded_original_metadata(self):
        from .native_v2_native61_support import FormatFixture61
        f=FormatFixture61.create();raw,ref=next((raw,ref) for raw,ref in f.documents() if ref.scope_label=='host' and ref.source=='route6')
        fixture=CollectorFixture2.create((('host','route6',f.profile.digest,raw,uid(1000)),))
        value,collector,_=fixture.run()
        decoded,wrapper=bridge.decode_collected_native61(collector,value,uid(1000),f.profile,ref,ref.digest)
        self.assertEqual(decoded.reference.exact_argv,'unrecorded')
        self.assertEqual(decoded.reference.timestamps,'unrecorded')
        self.assertEqual(wrapper.provenance,'mock_capture_reference_only_os_unproven')
        self.assertFalse(decoded.physical_probe_permitted)
        with self.assertRaisesRegex(c.ContractViolation2,'pin_mismatch'):
            bridge.decode_collected_native61(collector,value,uid(1000),f.profile,ref,hd('wrong'))


class IsolationTests(unittest.TestCase):
    def test_ast_has_no_os_io_or_mutation_imports(self):
        allowed={'dataclasses','hashlib','datetime','threading'}
        for name in ('native_v2_capture_contracts','native_v2_collector','native_v2_capture_adapters'):
            path=Path(__file__).parents[1]/(name+'.py')
            tree=ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    self.assertTrue(all(n.name in allowed for n in node.names))
                elif isinstance(node,ast.ImportFrom) and node.level==0:
                    self.assertIn(node.module,allowed)
                elif isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                    self.assertNotIn(node.func.id,('open','eval','exec','compile','__import__'))

    def test_fresh_import_and_constructors_cannot_start_os_work(self):
        script='''
import os, socket, subprocess
def forbidden(*args, **kwargs): raise AssertionError('unexpected OS operation')
socket.socket=forbidden
subprocess.Popen=forbidden
os.system=forbidden
os.open=forbidden
os.setns=forbidden
from trusted_checker_network import native_v2_capture_contracts
from trusted_checker_network import native_v2_collector
from trusted_checker_network import native_v2_capture_adapters
from trusted_checker_network.tests.native_v2_collector_support import CollectorFixture2
f=CollectorFixture2.create()
c,t=f.collector()
assert t.calls==()
assert c.capture().physical_probe_permitted is False
'''
        completed=subprocess.run([sys.executable,'-W','error::ResourceWarning','-c',script],capture_output=True,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stderr.decode())

    def test_unexpected_exception_has_finite_redacted_reason(self):
        f=CollectorFixture2.create();collector,_=f.collector()
        with patch.object(r.ReadOnlyCommandRunner2,'_run',side_effect=RuntimeError('SECRET STDOUT')):
            value=collector.capture()
        self.assertEqual(value.reason,'evidence_invalid');self.assertNotIn('SECRET',repr(value))

    def test_no_native_transport_or_mutation_surface(self):
        self.assertFalse(hasattr(r,'LinuxTransport2'))
        for method in ('execute','shell','stdin','apply','cleanup','send_packet','setns','docker'):
            self.assertFalse(hasattr(r.ReadOnlyCommandRunner2,method))
            self.assertFalse(hasattr(r.FencedReadOnlyCollector2,method))


if __name__ == '__main__': unittest.main()
