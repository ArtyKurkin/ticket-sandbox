"""H1 binary protocol and lifecycle tests; fake FD/kernel/process/clock ONLY."""
import ast
from dataclasses import FrozenInstanceError,replace
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_capture_contracts as cap
from trusted_checker_network import native_v2_helper_protocol as p
from trusted_checker_network import native_v2_helper_identity as identity
from trusted_checker_network import native_v2_helper_runtime as r
from trusted_checker_network import native_v2_helper_fake as fake
from trusted_checker_network import native_v2_helper_native as native
from .native_v2_helper_support import HelperFixtureH1,stat_bytes,status_bytes
from .native_v2_collector_support import stamp
from .native_v2_support import uid,hd


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=HelperFixtureH1.create();cls.i=cls.f.invocation;cls.codec=p.HelperCodecH1(cls.i)
        cls.raw=cls.codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(cls.i.fd_catalog_digest)))

    def test_fixed_header_and_binding_lengths(self):
        self.assertEqual((p.HEADER.size,p.BINDING.size),(12,272))
        self.assertEqual(len(self.raw),316)
        self.assertEqual(self.raw[:4],b'TCH1');self.assertEqual(self.raw[4],1)

    def test_round_trip_all_fixed_message_types(self):
        sizes={'invoke':32,'ready':32,'entered':32,'credentials':32,'exec':32,'stdout':1,'stderr':1,
               'stdout_eof':0,'stderr_eof':0,'exit':2,'reaped':32,'complete':112,'error':3,'cancel':0}
        for kind,size in sizes.items():
            with self.subTest(kind=kind):
                message=p.HelperMessageH1(kind,0,b'\0'*size)
                self.assertEqual(self.codec.decode(self.codec.encode(message)),message)

    def test_stream_one_byte_fragments(self):
        decoder=p.HelperStreamDecoderH1(self.codec);messages=[]
        for value in self.raw:messages.extend(decoder.feed(bytes((value,))))
        decoder.finish();self.assertEqual(len(messages),1);self.assertEqual(messages[0].kind,'invoke')

    def test_stream_multiple_frames_per_chunk(self):
        decoder=p.HelperStreamDecoderH1(self.codec)
        messages=decoder.feed(self.raw*2);decoder.finish();self.assertEqual(len(messages),2)

    def test_unknown_version(self):
        raw=bytearray(self.raw);raw[4]=2
        with self.assertRaisesRegex(c.ContractViolation2,'protocol_invalid'):self.codec.decode(bytes(raw))

    def test_unknown_magic(self):
        with self.assertRaisesRegex(c.ContractViolation2,'protocol_invalid'):self.codec.decode(b'BAD!'+self.raw[4:])

    def test_unknown_kind(self):
        raw=bytearray(self.raw);raw[5]=255
        with self.assertRaisesRegex(c.ContractViolation2,'protocol_invalid'):self.codec.decode(bytes(raw))

    def test_wrong_nonce(self):
        changed=replace(self.i,nonce=hd('wrong nonce'))
        wrong=p.HelperCodecH1(changed).encode(p.HelperMessageH1('invoke',0,bytes.fromhex(changed.fd_catalog_digest)))
        with self.assertRaisesRegex(c.ContractViolation2,'binding_mismatch'):self.codec.decode(wrong)

    def test_binding_each_security_field(self):
        # Every byte of the fixed binding is checked, not a selected tuple.
        for index in range(p.BINDING.size):
            with self.subTest(index=index):
                raw=bytearray(self.raw);raw[p.HEADER.size+index]^=1
                with self.assertRaisesRegex(c.ContractViolation2,'binding_mismatch'):self.codec.decode(bytes(raw))

    def test_extra_field_or_trailing_bytes(self):
        with self.assertRaisesRegex(c.ContractViolation2,'protocol_invalid'):self.codec.decode(self.raw+b'\0')
        magic,version,kind,seq,size=p.HEADER.unpack_from(self.raw)
        wrong=p.HEADER.pack(magic,version,kind,seq,size+1)+self.raw[p.HEADER.size:]+b'\0'
        with self.assertRaisesRegex(c.ContractViolation2,'protocol_invalid'):self.codec.decode(wrong)

    def test_oversize_declaration_before_body(self):
        decoder=p.HelperStreamDecoderH1(self.codec)
        raw=p.HEADER.pack(p.MAGIC,1,1,0,2**32-1)
        with self.assertRaisesRegex(c.ContractViolation2,'protocol_invalid'):decoder.feed(raw)
        with self.assertRaises(c.ContractViolation2):decoder.feed(self.raw)

    def test_truncation_latches_failed_stream(self):
        decoder=p.HelperStreamDecoderH1(self.codec);decoder.feed(self.raw[:-1])
        with self.assertRaisesRegex(c.ContractViolation2,'protocol_invalid'):decoder.finish()
        with self.assertRaises(c.ContractViolation2):decoder.feed(self.raw[-1:])

    def test_chunk_input_type_and_bounds(self):
        for raw in (bytearray(self.raw),'raw',b'x'*(p.MAX_FRAME+1)):
            with self.subTest(raw=type(raw).__name__),self.assertRaises(c.ContractViolation2):
                p.HelperStreamDecoderH1(self.codec).feed(raw)

    def test_zero_data_and_oversized_data_rejected(self):
        for raw in (b'',b'x'*(p.CHUNK+1)):
            with self.assertRaises(c.ContractViolation2):p.HelperMessageH1('stdout',0,raw)

    def test_message_sequence_bound_and_bool(self):
        for seq in (-1,True,p.MAX_MESSAGES):
            with self.assertRaises(c.ContractViolation2):p.HelperMessageH1('cancel',seq,b'')

    def test_finite_error_code_only(self):
        with self.assertRaises(c.ContractViolation2):p.HelperMessageH1('error',0,b'\xff\xff\0')
        with self.assertRaises(c.ContractViolation2):p.HelperMessageH1('error',0,b'\0\0\x02')

    def test_zero_nonce_not_accepted(self):
        with self.assertRaisesRegex(c.ContractViolation2,'binding_mismatch'):replace(self.i,nonce='0'*64)

    def test_fd_catalog_requires_all_roles(self):
        with self.assertRaises(c.ContractViolation2):replace(self.i,descriptors=self.i.descriptors[:-1])

    def test_fd_role_kind_not_interchangeable(self):
        with self.assertRaisesRegex(c.ContractViolation2,'fd_transfer_invalid'):
            replace(self.i.descriptors[0],identity=self.i.descriptors[1].identity)

    def test_parent_pidfd_bound_to_start_generation(self):
        with self.assertRaisesRegex(c.ContractViolation2,'fd_transfer_invalid'):
            replace(self.i,parent_start_ticks=self.i.parent_start_ticks+1)

    def test_executable_digest_independent_of_fd_renumbering(self):
        first=self.i.executable;second=replace(first,fd=300)
        self.assertEqual(p.executable_object_digest_h1(first),p.executable_object_digest_h1(second))

    def test_no_user_argv_or_namespace_names(self):
        with self.assertRaises(TypeError):replace(self.i,argv=('/bin/sh','-c','bad'))
        with self.assertRaises(TypeError):replace(self.i,namespace_name='x; bad')

    def test_deadline_not_extendable(self):
        with self.assertRaisesRegex(c.ContractViolation2,'timeout'):
            replace(self.i,deadline_monotonic_us=self.i.session.started.monotonic_us+500001)


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=HelperFixtureH1.create();cls.good,cls.issuer,cls.good_kernel=cls.f.run()
        assert cls.good.result=='helper_fake_capture_preserved'

    def fault(self,kernel,reason):
        value,supervisor,kernel=self.f.run(kernel)
        self.assertEqual((value.result,value.reason),('unknown',reason));self.assertEqual((value.stdout,value.stderr),(b'',b''))
        self.assertIs(supervisor.run_fake(),value)
        return value,supervisor,kernel

    def transform_message(self,transform):
        kernel=self.f.kernel();codec=p.HelperCodecH1(self.f.invocation)
        kernel.frame_transform=lambda raw:codec.encode(transform(codec.decode(raw)))
        return kernel

    def test_positive_standalone_e2e(self):
        self.assertEqual((self.good.stdout,self.good.stderr,self.good.cleanup),(b'[]',b'','reaped_closed'))
        self.assertIs(self.issuer.admit(self.good),self.good)
        self.assertEqual([p.HelperCodecH1(self.f.invocation).decode(raw).kind for raw in self.issuer._channel.frames],
            ['ready','entered','credentials','exec','stdout','stdout_eof','stderr_eof','exit','reaped','complete'])

    def test_default_off_no_kernel_calls(self):
        supervisor,kernel=self.f.supervisor(enabled=False)
        value=supervisor.run_fake();self.assertEqual(value.reason,'disabled');self.assertEqual(kernel.calls,[])

    def test_native_entry_closed_for_fake_approval(self):
        supervisor,kernel=self.f.supervisor()
        with self.assertRaisesRegex(c.ContractViolation2,'native_identity_unreviewed'):supervisor.capture_native()
        self.assertEqual(kernel.calls,[])

    def test_registration_precedes_dispatch(self):
        calls=self.good_kernel.calls
        self.assertEqual(calls[0][0:2],('register_owned','helper'));self.assertEqual(calls[1][0],'dispatch_helper')

    def test_reap_child_and_helper(self):
        reaped=[call[1] for call in self.good_kernel.calls if call[0]=='reap']
        self.assertEqual(reaped,['child','helper']);self.assertEqual(self.good_kernel.closed_received,set(range(30,37)))

    def test_descriptor_renumbering_is_permitted(self):
        kernel=self.f.kernel();mapping={fd.local_fd:fd.local_fd+100 for fd in kernel.received}
        kernel.received=tuple(replace(fd,local_fd=mapping[fd.local_fd]) for fd in kernel.received)
        kernel.fd_facts={mapping[fd]:fact for fd,fact in kernel.fd_facts.items()}
        value,_,_=self.f.run(kernel);self.assertEqual(value.result,'helper_fake_capture_preserved')

    def test_runner_target_namespace_entry(self):
        f=HelperFixtureH1.create('runner');value,_,kernel=f.run()
        self.assertEqual(value.result,'helper_fake_capture_preserved')
        self.assertNotEqual(f.invocation.initial_namespace_inode,f.invocation.namespace.reference.key.netns_inode)
        self.assertTrue(any(call[0]=='enter_namespace_child_only' for call in kernel.calls))

    def test_lifecycle_order(self):
        names=[call[0] for call in self.good_kernel.calls]
        self.assertLess(names.index('verify_executable'),names.index('enter_namespace_child_only'))
        self.assertLess(names.index('enter_namespace_child_only'),names.index('drop_credentials'))
        self.assertLess(names.index('drop_credentials'),names.index('prepare_child_fds'))
        self.assertLess(names.index('prepare_child_fds'),names.index('exec_fd_child'))

    def test_wrong_nonce_in_invoke(self):
        kernel=self.f.kernel();other=replace(self.f.invocation,nonce=hd('other'))
        kernel.invoke_transform=lambda raw:p.HelperCodecH1(other).encode(p.HelperMessageH1('invoke',0,bytes.fromhex(other.fd_catalog_digest)))
        _,_,kernel=self.fault(kernel,'binding_mismatch')
        self.assertEqual(kernel.closed_received,set(range(30,37)))
        self.assertFalse(any(call[0]=='enter_namespace_child_only' for call in kernel.calls))

    def test_wrong_fd_catalog_in_invoke(self):
        kernel=self.f.kernel();codec=p.HelperCodecH1(self.f.invocation)
        kernel.invoke_transform=lambda raw:codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(hd('other'))))
        self.fault(kernel,'binding_mismatch')

    def test_unknown_protocol_version(self):
        kernel=self.f.kernel()
        def change(raw):
            result=bytearray(raw);result[4]=2;return bytes(result)
        kernel.invoke_transform=change;self.fault(kernel,'protocol_invalid')

    def test_forged_completion_hash(self):
        kernel=self.transform_message(lambda m:replace(m,payload=b'x'+m.payload[1:]) if m.kind=='complete' else m)
        self.fault(kernel,'incomplete_output')

    def test_forged_completion_before_reap(self):
        kernel=self.transform_message(lambda m:replace(m,kind='complete',payload=b'\0'*112) if m.kind=='reaped' else m)
        self.fault(kernel,'sequence_invalid')

    def test_duplicate_completion(self):
        kernel=self.f.kernel();supervisor,kernel=self.f.supervisor(kernel)
        def duplicate():
            supervisor._channel.frames.append(supervisor._channel.frames[-1])
        kernel.close_control_hook=duplicate
        self.assertEqual(supervisor.run_fake().reason,'sequence_invalid')

    def test_reordered_phase_messages(self):
        kernel=self.transform_message(lambda m:replace(m,kind='entered') if m.kind=='ready' else m)
        self.fault(kernel,'sequence_invalid')

    def test_credential_phase_commitment_changed(self):
        kernel=self.transform_message(lambda m:replace(m,payload=bytes.fromhex(hd('wrong'))) if m.kind=='credentials' else m)
        self.fault(kernel,'sequence_invalid')

    def test_fd_substitution(self):
        kernel=self.f.kernel();kernel.fd_facts[30]=replace(kernel.fd_facts[30],inode=999)
        self.fault(kernel,'fd_transfer_invalid')

    def test_fd_wrong_type(self):
        kernel=self.f.kernel();kernel.fd_facts[30]=replace(kernel.fd_facts[30],kind='regular')
        self.fault(kernel,'fd_transfer_invalid')

    def test_incomplete_fd_transfer(self):
        kernel=self.f.kernel();kernel.received=kernel.received[:-1]
        self.fault(kernel,'fd_transfer_invalid')

    def test_unexpected_transferred_fd(self):
        kernel=self.f.kernel();kernel.received=(*kernel.received,p.ReceivedDescriptorH1('stdout_pipe',50))
        self.fault(kernel,'fd_transfer_invalid')

    def test_duplicate_descriptor_number(self):
        kernel=self.f.kernel();kernel.received=(replace(kernel.received[0],local_fd=31),*kernel.received[1:])
        self.fault(kernel,'fd_transfer_invalid')

    def test_wrong_namespace(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,namespace_inode=999)
        self.fault(kernel,'identity_mismatch')

    def test_parent_check_uses_transferred_pidfd(self):
        _,_,kernel=self.f.run()
        calls=[call for call in kernel.calls if call[0]=='parent_check']
        self.assertTrue(calls);self.assertTrue(all(call[1:]==(36,5000,9000) for call in calls))

    def test_wrong_nsfs(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,namespace_fs='unreviewed')
        self.fault(kernel,'identity_mismatch')

    def test_wrong_boot(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,boot_uuid=uid(999))
        self.fault(kernel,'identity_mismatch')

    def test_pid_reuse(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,helper_start_ticks=999)
        self.fault(kernel,'pid_reuse')

    def test_namespace_pid_reuse(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,namespace_lookup_start_ticks=999)
        self.fault(kernel,'pid_reuse')

    def test_parent_pid_reuse(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,parent_start_ticks=999)
        self.fault(kernel,'pid_reuse')

    def test_wrong_session_nsid_refs(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,nsid_references_digest=hd('wrong'))
        self.fault(kernel,'identity_mismatch')

    def test_wrong_config_or_journal_reference(self):
        for name in ('configuration_reference_digest','journal_reference_digest'):
            with self.subTest(name=name):
                kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,**{name:hd('wrong')})
                self.fault(kernel,'identity_mismatch')

    def test_credential_drift(self):
        kernel=self.f.kernel()
        kernel.identity_transform=lambda value,phase:replace(value,principal=replace(value.principal,uid=0)) if phase=='final' else value
        self.fault(kernel,'credential_drift')

    def test_failed_privilege_drop(self):
        kernel=self.f.kernel();kernel.drop_ok=False
        self.fault(kernel,'privilege_drop_failed');self.assertFalse(any(call[0]=='exec_fd_child' for call in kernel.calls))

    def test_unexpected_inherited_fd(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,inherited_fds=(*value.inherited_fds,999))
        self.fault(kernel,'fd_transfer_invalid')

    def test_unexpected_child_fd(self):
        kernel=self.f.kernel();kernel.unexpected_child_fd=True;self.fault(kernel,'fd_transfer_invalid')

    def test_wrong_executable_hash(self):
        kernel=self.f.kernel();kernel.executable_ok=False;self.fault(kernel,'executable_mismatch')

    def test_wrong_executable_identity_snapshot(self):
        kernel=self.f.kernel();kernel.identity_transform=lambda value,phase:replace(value,executable_object_digest=hd('wrong'))
        self.fault(kernel,'executable_mismatch')

    def test_helper_crash_on_dispatch(self):
        kernel=self.f.kernel();kernel.helper_crash=True
        _,_,kernel=self.fault(kernel,'helper_crashed');self.assertTrue(any(call[0]=='reap' for call in kernel.calls))

    def test_helper_death_during_child_read(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1(helper_alive=False),)
        self.fault(kernel,'helper_crashed')

    def test_lost_spawn_response(self):
        kernel=self.f.kernel();kernel.lost_spawn=True
        _,_,kernel=self.fault(kernel,'spawn_response_lost')
        self.assertEqual([call[1] for call in kernel.calls if call[0]=='reap'],['helper'])

    def test_failed_fd_exec_after_reservation(self):
        kernel=self.f.kernel();kernel.child_exec_error=True
        _,_,kernel=self.fault(kernel,'helper_crashed')
        self.assertEqual([call[1] for call in kernel.calls if call[0]=='reap'],['child','helper'])

    def test_timeout_term_grace_kill_reap(self):
        kernel=self.f.kernel();kernel.polls=();kernel.term_effective=False
        _,_,kernel=self.fault(kernel,'timeout')
        names=[call[0] for call in kernel.calls]
        self.assertLess(names.index('term'),names.index('kill'));self.assertLess(names.index('kill'),names.index('reap'))

    def test_frozen_clock_has_finite_poll_count(self):
        kernel=self.f.kernel();kernel.polls=();kernel.step_us=0
        self.fault(kernel,'incomplete_output')
        self.assertEqual(sum(call[0]=='poll_child' for call in kernel.calls),p.MAX_MESSAGES-16)

    def test_clock_rollback_before_enter(self):
        kernel=self.f.kernel();kernel.clock_sequence=(stamp(-1),)
        self.fault(kernel,'clock_rollback')

    def test_clock_rollback_during_cleanup_quarantines(self):
        kernel=self.f.kernel();original=kernel.poll_child
        def change(owned,maximum,deadline):
            result=original(owned,maximum,deadline)
            if result.exit_code is not None:
                kernel.clock_sequence=(stamp(1000),stamp(1100),stamp(500),stamp(1200),stamp(1300))
            return result
        kernel.poll_child=change
        self.fault(kernel,'cleanup_unproven')

    def test_unknown_exception_is_redacted(self):
        kernel=self.f.kernel()
        kernel.on_poll=lambda:(_ for _ in ()).throw(RuntimeError('PRIVATE OBSERVATION'))
        value,_,_=self.fault(kernel,'evidence_invalid');self.assertNotIn('PRIVATE',repr(value))

    def test_incomplete_stdout(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1(stderr_eof=True,exit_code=0),)
        self.fault(kernel,'timeout')

    def test_incomplete_stderr(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1(stdout_eof=True,exit_code=0),)
        self.fault(kernel,'timeout')

    def test_child_exit_without_protocol_completion(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1(exit_code=0),)
        self.fault(kernel,'timeout')

    def test_nonzero_child_exit(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1(stdout_eof=True,stderr_eof=True,exit_code=2),)
        self.fault(kernel,'incomplete_output')

    def test_parent_death(self):
        kernel=self.f.kernel();kernel.parent_ok=False;self.fault(kernel,'parent_died')

    def test_parent_death_during_read(self):
        kernel=self.f.kernel();kernel.on_poll=lambda:setattr(kernel,'parent_ok',False)
        self.fault(kernel,'parent_died')

    def test_failed_reap(self):
        kernel=self.f.kernel();kernel.reap_ok=False
        value,_,_=self.fault(kernel,'cleanup_unproven');self.assertEqual(value.cleanup,'cleanup_unproven')

    def test_failed_close_owned(self):
        kernel=self.f.kernel();kernel.close_ok=False;self.fault(kernel,'cleanup_unproven')

    def test_failed_close_transfer(self):
        kernel=self.f.kernel();kernel.transfer_close_ok=False;self.fault(kernel,'cleanup_unproven')

    def test_failed_close_control(self):
        kernel=self.f.kernel();kernel.control_close_ok=False;self.fault(kernel,'cleanup_unproven')

    def test_stdout_overflow(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1((('stdout',b'x'*p.CHUNK),)),)*65
        self.fault(kernel,'stdout_limit')

    def test_stderr_overflow(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1((('stderr',b'x'*p.CHUNK),)),r.ChildPollH1((('stderr',b'x'),)))
        self.fault(kernel,'stderr_limit')

    def test_late_stdout_after_eof(self):
        kernel=self.f.kernel();kernel.polls=(r.ChildPollH1(stdout_eof=True),r.ChildPollH1((('stdout',b'late'),)))
        self.fault(kernel,'sequence_invalid')

    def test_late_completion_after_deadline(self):
        kernel=self.f.kernel()
        def late(raw):
            if p.HelperCodecH1(self.f.invocation).decode(raw).kind=='complete':kernel.now=stamp(500001)
            return raw
        kernel.frame_transform=late;self.fault(kernel,'timeout')

    def test_kill_before_dispatch(self):
        supervisor,kernel=self.f.supervisor();supervisor.kill()
        value=supervisor.run_fake();self.assertEqual(value.reason,'killed');self.assertEqual(kernel.calls,[])

    def test_kill_protocol_during_read(self):
        supervisor,kernel=self.f.supervisor();kernel.on_poll=supervisor.kill
        value=supervisor.run_fake();self.assertEqual(value.reason,'killed');self.assertEqual(value.stdout,b'')
        self.assertTrue(any(call[0]=='reap' for call in kernel.calls))

    def test_kill_after_success_denies_admission(self):
        value,supervisor,_=self.f.run();supervisor.kill()
        self.assertIs(supervisor.run_fake(),value)
        with self.assertRaisesRegex(c.ContractViolation2,'replay'):supervisor.admit(value)

    def test_duplicate_cancel_coalesced(self):
        channel=r.ControlChannelH1(self.f.invocation);channel.cancel();channel.cancel()
        self.assertEqual(len(channel.cancel_frames),1)
        self.assertTrue(channel.receive_cancel())
        channel.cancel();self.assertEqual(channel.cancel_frames,[])

    def test_replay_shared_registry(self):
        registry=r.OwnedInvocationRegistryH1(self.f.invocation.session.session_uuid)
        first,_=self.f.supervisor(registry=registry);self.assertEqual(first.run_fake().result,'helper_fake_capture_preserved')
        second,kernel=self.f.supervisor(registry=registry)
        self.assertEqual(second.run_fake().reason,'replay');self.assertEqual(kernel.calls,[])

    def test_reused_nonce_different_invocation(self):
        registry=r.OwnedInvocationRegistryH1(self.f.invocation.session.session_uuid)
        registry.reserve(self.f.invocation);registry.finish(self.f.invocation,True)
        with self.assertRaisesRegex(c.ContractViolation2,'replay'):
            registry.reserve(replace(self.f.invocation,invocation_uuid=uid(999)))

    def test_unknown_circuit_blocks_new_nonce(self):
        registry=r.OwnedInvocationRegistryH1(self.f.invocation.session.session_uuid)
        registry.reserve(self.f.invocation);registry.finish(self.f.invocation,False)
        with self.assertRaisesRegex(c.ContractViolation2,'replay'):
            registry.reserve(replace(self.f.invocation,invocation_uuid=uid(999),nonce=hd('fresh')))

    def test_session_aggregate_cap_before_verifier_buffering(self):
        registry=r.OwnedInvocationRegistryH1(self.f.invocation.session.session_uuid)
        registry.reserve(self.f.invocation)
        for _ in range(cap.MAX_AGGREGATE//p.CHUNK):registry.debit_data(p.CHUNK)
        with self.assertRaisesRegex(c.ContractViolation2,'aggregate_limit'):registry.debit_data(1)

    def test_completed_prior_capture_counts_toward_session_cap(self):
        registry=r.OwnedInvocationRegistryH1(self.f.invocation.session.session_uuid)
        first,_=self.f.supervisor(registry=registry);first.run_fake()
        self.assertEqual(registry._captured_bytes,2)
        self.assertEqual(registry._seen,{self.f.invocation.invocation_uuid})

    def test_concurrent_invocation(self):
        registry=r.OwnedInvocationRegistryH1(self.f.invocation.session.session_uuid);registry.reserve(self.f.invocation)
        with self.assertRaisesRegex(c.ContractViolation2,'sequence_invalid'):
            registry.reserve(replace(self.f.invocation,invocation_uuid=uid(999),nonce=hd('fresh')))

    def test_concurrent_supervisor_entry(self):
        supervisor,_=self.f.supervisor();supervisor._lock.acquire()
        try:
            with self.assertRaisesRegex(c.ContractViolation2,'sequence_invalid'):supervisor.run_fake()
        finally:supervisor._lock.release()

    def test_issued_result_identity_only(self):
        with self.assertRaisesRegex(c.ContractViolation2,'replay'):self.issuer.admit(replace(self.good))
        _,other,_=self.f.run()
        with self.assertRaisesRegex(c.ContractViolation2,'replay'):other.admit(self.good)

    def test_no_arbitrary_pid_termination(self):
        with self.assertRaisesRegex(c.ContractViolation2,'identity_mismatch'):self.f.kernel().kill_owned(12345)

    def test_helper_one_invocation_only(self):
        i=self.f.invocation;kernel=self.f.kernel();channel=r.ControlChannelH1(i);helper=r.StandaloneHelperH1()
        raw=channel.codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(i.fd_catalog_digest)))
        native.standalone_helper_entry_h1(i,raw,kernel.received,kernel,channel)
        helper._used=True
        with self.assertRaisesRegex(c.ContractViolation2,'replay'):helper.run_fake(i,raw,kernel.received,kernel,channel)

    def test_result_false_flags_and_immutability(self):
        for name in ('physical_probe_permitted','ownership_proven','isolation_verified','management_policy_verified',
                     'measurement_verified','continuous_attestation'):
            self.assertIs(getattr(self.good,name),False)
        self.assertEqual(self.good.native_identity,'native_identity_unreviewed')
        with self.assertRaises(FrozenInstanceError):self.good.reason='verified'
        with self.assertRaises(TypeError):replace(self.good,isolation_verified=True)
        with self.assertRaises(c.ContractViolation2):replace(self.good,physical_probe_permitted=True)


class TranscriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=HelperFixtureH1.create();_,cls.supervisor,_=cls.f.run();cls.frames=tuple(cls.supervisor._channel.frames)

    def test_missing_complete_refused(self):
        verifier=r.HelperTranscriptH1(self.f.invocation)
        for raw in self.frames[:-1]:verifier.accept(raw)
        with self.assertRaisesRegex(c.ContractViolation2,'incomplete_output'):verifier.finish()

    def test_duplicate_eof_refused(self):
        verifier=r.HelperTranscriptH1(self.f.invocation)
        for raw in self.frames[:6]:verifier.accept(raw)
        codec=p.HelperCodecH1(self.f.invocation)
        raw=codec.encode(p.HelperMessageH1('stdout_eof',6,b''))
        with self.assertRaisesRegex(c.ContractViolation2,'sequence_invalid'):verifier.accept(raw)

    def test_late_frame_after_complete(self):
        verifier=r.HelperTranscriptH1(self.f.invocation)
        for raw in self.frames:verifier.accept(raw)
        raw=verifier.codec.encode(p.HelperMessageH1('stdout',10,b'late'))
        with self.assertRaisesRegex(c.ContractViolation2,'sequence_invalid'):verifier.accept(raw)

    def test_complete_cannot_forge_numeric_totals(self):
        verifier=r.HelperTranscriptH1(self.f.invocation)
        for raw in self.frames[:-1]:verifier.accept(raw)
        message=verifier.codec.decode(self.frames[-1]);payload=bytearray(message.payload);payload[71]^=1
        with self.assertRaisesRegex(c.ContractViolation2,'incomplete_output'):
            verifier.accept(verifier.codec.encode(replace(message,payload=bytes(payload))))

    def test_untrusted_data_is_not_control(self):
        codec=p.HelperCodecH1(self.f.invocation)
        with self.assertRaises(c.ContractViolation2):codec.decode(b'{"complete":true}')

    def test_failed_transcript_cannot_be_repaired_by_late_completion(self):
        verifier=r.HelperTranscriptH1(self.f.invocation)
        for raw in self.frames[:-1]:verifier.accept(raw)
        message=verifier.codec.decode(self.frames[-1])
        forged=verifier.codec.encode(replace(message,payload=b'\0'*112))
        with self.assertRaises(c.ContractViolation2):verifier.accept(forged)
        with self.assertRaises(c.ContractViolation2):verifier.accept(self.frames[-1])
        with self.assertRaises(c.ContractViolation2):verifier.finish()


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.f=HelperFixtureH1.create()

    def test_explicit_pid_stat_projection(self):
        self.assertEqual(identity.parse_pid_stat_h1(stat_bytes(6000,12345),'helper_stat'),(6000,12345))

    def test_exact_boot_id_parser(self):
        self.assertEqual(identity.parse_boot_h1((uid(1)+'\n').encode()),uid(1))
        for raw in (uid(1).encode(),b'not-a-boot-id\n',(uid(1)+' \n').encode()):
            with self.assertRaises(c.ContractViolation2):identity.parse_boot_h1(raw)

    def test_fd_inventory_is_bounded_unique_set(self):
        self.assertEqual(identity.parse_fd_inventory_h1(b'32\n30\n31\n'),(30,31,32))
        with self.assertRaises(c.ContractViolation2):identity.parse_fd_inventory_h1(b'30\n30\n')
        with self.assertRaises(c.ContractViolation2):identity.parse_fd_inventory_h1(b'30\n-1\n')

    def test_fd_inventory_cardinality_bound(self):
        raw=b''.join((str(i)+'\n').encode() for i in range(257))
        with self.assertRaises(c.ContractViolation2):identity.parse_fd_inventory_h1(raw)

    def test_pid_comm_parentheses_and_spaces(self):
        self.assertEqual(identity.parse_pid_stat_h1(stat_bytes(6000,12345,'x ) y ( z'),'helper_stat'),(6000,12345))

    def test_truncated_stat_refused(self):
        with self.assertRaises(c.ContractViolation2):identity.parse_pid_stat_h1(b'6000 (x) S 1\n','helper_stat')

    def test_stat_encoding_and_bounds(self):
        for raw in (b'\xff',b'x'*4097,b''):
            with self.assertRaises(c.ContractViolation2):identity.parse_pid_stat_h1(raw,'helper_stat')

    def test_explicit_status_projection_and_fixture_bit_mapping(self):
        value=identity.parse_status_h1(status_bytes(),(('CAP_NET_ADMIN',0),('CAP_SYS_ADMIN',1)))
        self.assertEqual(value.uid,1002);self.assertEqual(value.effective_caps,('CAP_NET_ADMIN',))
        self.assertFalse(value.physical_probe_permitted)

    def test_unknown_capability_mask_refused(self):
        with self.assertRaisesRegex(c.ContractViolation2,'native_identity_unreviewed'):
            identity.parse_status_h1(status_bytes(capmask='0000000000000080'),(('CAP_NET_ADMIN',0),))

    def test_duplicate_capability_mapping_refused(self):
        with self.assertRaises(c.ContractViolation2):
            identity.parse_status_h1(status_bytes(),(('CAP_NET_ADMIN',0),('CAP_SYS_ADMIN',0)))

    def test_status_size_is_bounded(self):
        with self.assertRaises(c.ContractViolation2):identity.parse_status_h1(b'x'*16385,(('CAP_NET_ADMIN',0),))

    def test_uid_variants_not_coerced(self):
        raw=status_bytes().replace(b'1002 1002 1002 1002',b'1002 0 1002 1002',1)
        with self.assertRaisesRegex(c.ContractViolation2,'credential_drift'):
            identity.parse_status_h1(raw,(('CAP_NET_ADMIN',0),))

    def test_duplicate_status_field(self):
        with self.assertRaisesRegex(c.ContractViolation2,'native_identity_unreviewed'):
            identity.parse_status_h1(status_bytes()+b'NoNewPrivs: 1\n',(('CAP_NET_ADMIN',0),))

    def test_unknown_status_field(self):
        with self.assertRaisesRegex(c.ContractViolation2,'native_identity_unreviewed'):
            identity.parse_status_h1(status_bytes()+b'Extra: 1\n',(('CAP_NET_ADMIN',0),))

    def test_no_new_privileges_required(self):
        with self.assertRaisesRegex(c.ContractViolation2,'credential_drift'):
            identity.parse_status_h1(status_bytes().replace(b'NoNewPrivs:\t1',b'NoNewPrivs:\t0'),(('CAP_NET_ADMIN',0),))

    def test_actual_reader_stays_unreviewed(self):
        value=identity.NativeIdentityAdapterH1().observe_native()
        self.assertEqual(value.result,'native_identity_unreviewed');self.assertFalse(value.physical_probe_permitted)

    def test_source_whitelist_not_arbitrary_paths(self):
        for source in ('/etc/shadow','environ','cmdline','secret','*'):
            with self.assertRaises(c.ContractViolation2):native.source_path_h1(self.f.invocation,source)
        self.assertEqual(native.source_path_h1(self.f.invocation,'helper_stat'),'/proc/6000/stat')

    def test_protected_references_are_not_filesystem_attestation(self):
        with self.assertRaisesRegex(c.ContractViolation2,'native_identity_unreviewed'):
            native.source_path_h1(self.f.invocation,'protected_references')

    def test_nsfs_unproven_cannot_be_used(self):
        kernel=self.f.kernel();snapshot=replace(kernel.identity('before'),namespace_fs='unreviewed')
        with self.assertRaisesRegex(c.ContractViolation2,'identity_mismatch'):
            identity.validate_identity_h1(snapshot,self.f.invocation,'before',snapshot.inherited_fds)


class IsolationTests(unittest.TestCase):
    def test_old_mock_collector_cannot_open_helper(self):
        from trusted_checker_network.native_v2_collector import ReadOnlyCommandRunner2
        with self.assertRaisesRegex(c.ContractViolation2,'os_backend_dormant'):ReadOnlyCommandRunner2(r.StandaloneHelperH1())

    def test_old_os_fake_backend_does_not_accept_new_kernel(self):
        from .native_v2_os_reader_support import OSFixture2
        f=OSFixture2.create()
        with self.assertRaises(c.ContractViolation2):f.backend(HelperFixtureH1.create().kernel())

    def test_old_adapters_cannot_adopt_helper_result(self):
        from .native_v2_collector_support import CollectorFixture2
        _,collector,_=CollectorFixture2.create().run();value,_,_=HelperFixtureH1.create().run()
        with self.assertRaises(c.ContractViolation2):collector.admit_for_parsing(value)

    def test_existing_physical_gate_stays_closed(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        value,_,_=HelperFixtureH1.create().run()
        with self.assertRaisesRegex(Denied,'physical_network_boundary_not_accepted'):PhysicalProbeGate.permit(value)

    def test_native_calls_guard_before_syscall(self):
        i=HelperFixtureH1.create().invocation;probe=native.LinuxIdentityKernelH1();helper=native.LinuxHelperKernelH1()
        calls=((probe.read_source,(i,'boot')),(probe.inherited_fds,(i,)),(probe.namespace_fd,(30,)),
               (probe.executable_fd_hash,(31,)),(probe.protected_references,(i,)),
               (helper.enter_namespace,(30,)),(helper.drop_credentials,(i.policy.command_principal,)),
               (helper.exec_verified_fd,(i,31)),(native.native_helper_entry_h1,()))
        with patch.object(native.os,'open',side_effect=AssertionError('OS I/O')):
            for method,args in calls:
                with self.subTest(method=method.__name__),self.assertRaisesRegex(c.ContractViolation2,'native_identity_unreviewed'):
                    method(*args)

    def test_native_does_not_accept_json_identity(self):
        with self.assertRaises(TypeError):identity.NativeIdentityAdapterH1().observe_native({'verified':True})

    def test_native_syscalls_isolated_and_guarded(self):
        root=Path(__file__).parents[1]
        for name in ('native_v2_helper_protocol','native_v2_helper_identity','native_v2_helper_runtime','native_v2_helper_fake'):
            tree=ast.parse((root/(name+'.py')).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):self.assertTrue(all(n.name not in ('os','socket','subprocess','ctypes') for n in node.names))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):self.assertNotIn(node.func.id,('open','exec','eval','__import__'))
        tree=ast.parse(Path(native.__file__).read_text())
        for cls in (n for n in tree.body if isinstance(n,ast.ClassDef)):
            for method in (n for n in cls.body if isinstance(n,ast.FunctionDef)):
                self.assertEqual(method.body[0].value.func.id,'native_guard_h1')

    def test_fresh_import_and_explicit_fake_entry_do_not_launch_helper(self):
        code='''
import os,socket,subprocess
def forbidden(*args,**kwargs):raise AssertionError('native operation')
os.open=forbidden
os.fork=forbidden
os.execve=forbidden
os.setns=forbidden
os.system=forbidden
socket.socket=forbidden
subprocess.Popen=forbidden
from trusted_checker_network import native_v2_helper_native
from trusted_checker_network.tests.native_v2_helper_support import HelperFixtureH1
f=HelperFixtureH1.create()
s,k=f.supervisor(enabled=False)
assert k.calls==[]
assert s.run_fake().reason=='disabled'
value,_,_=f.run()
assert value.result=='helper_fake_capture_preserved'
assert value.physical_probe_permitted is False
'''
        result=subprocess.run([sys.executable,'-W','error::ResourceWarning','-c',code],capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode())


if __name__=='__main__':unittest.main()
