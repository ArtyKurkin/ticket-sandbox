"""Permanent offline H1 remediation regressions, including reconstructed audit
safe expectations. Original /tmp audit harness was unavailable on 2026-10-22.
No native entry or OS primitive is called by this module.
"""
import ast
from dataclasses import FrozenInstanceError,replace
from pathlib import Path
import sys
import threading
import unittest

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_helper_protocol as p
from trusted_checker_network import native_v2_helper_runtime as r
from trusted_checker_network import native_v2_helper_fake as fake
from .native_v2_helper_support import HelperFixtureH1,hd,uid


def lose_return(kernel,method,*,after=True,error=RuntimeError,role=None):
    original=getattr(kernel,method);fired=[]
    def operation(*args,**kwargs):
        applies=role is None or (method=='prepare_owned' and args[1]==role)
        if not applies or fired:return original(*args,**kwargs)
        fired.append(True)
        if after:original(*args,**kwargs)
        raise error('synthetic fault')
    setattr(kernel,method,operation)
    return fired


def abort_poll():
    raise RuntimeError('synthetic failure with a still-owned running child')


class FixtureCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.f=HelperFixtureH1.create()

    def assert_no_orphans(self,kernel):
        self.assertTrue(all(not obj['running'] and obj['reaped'] and obj['closed']
                            for obj in kernel._objects.values()),kernel._objects)
        self.assertEqual(kernel.open_transferred_count,0)
        close_fds=[call[1] for call in kernel.calls if call[0]=='close_fd']
        self.assertEqual(len(close_fds),len(set(close_fds)),'double close')

    def assert_terminal(self,supervisor,kernel,*,unknown=True):
        value=supervisor._terminal;self.assertIsNotNone(value)
        self.assertEqual(value.result,'unknown' if unknown else 'helper_fake_capture_preserved')
        self.assertIsNone(supervisor.registry._active)
        if unknown:self.assertTrue(supervisor.registry._circuit)
        calls=tuple(kernel.calls)
        self.assertIs(supervisor.run_fake(),value);self.assertEqual(tuple(kernel.calls),calls)
        self.assertTrue(supervisor._channel.closed)
        return value


class AuditSafeExpectations(FixtureCase):
    """The ten original safe conditions from the review, not green reproductions.

    Strengthen accounting checks; do not change their intended safe outcomes.
    """
    def test_A01_parent_watch_is_read_after_close(self):
        k=self.f.kernel();original=k.parent_alive;closed=[]
        def tracking(fd,pid,ticks):
            if fd in k.closed_received:closed.append(fd)
            return original(fd,pid,ticks)
        k.parent_alive=tracking
        value,_,k=self.f.run(k)
        self.assertEqual(closed,[]);self.assertEqual(value.result,'helper_fake_capture_preserved')
        self.assert_no_orphans(k)

    def test_A01_strict_fake_fd_semantics_reject_positive(self):
        k=self.f.kernel();original=k.parent_alive
        def strict(fd,pid,ticks):
            if fd in k.closed_received:raise OSError('synthetic closed FD')
            return original(fd,pid,ticks)
        k.parent_alive=strict
        value,_,k=self.f.run(k)
        self.assertEqual(value.result,'helper_fake_capture_preserved');self.assert_no_orphans(k)

    def test_A02_lost_helper_registration_return(self):
        k=self.f.kernel();lose_return(k,'register_helper')
        value,supervisor,k=self.f.run(k)
        self.assert_terminal(supervisor,k);self.assert_no_orphans(k)
        self.assertEqual(value.cleanup,'reaped_closed')

    def test_A02_lost_child_reservation_return(self):
        k=self.f.kernel();lose_return(k,'reserve_child')
        value,supervisor,k=self.f.run(k)
        self.assert_terminal(supervisor,k);self.assert_no_orphans(k)
        self.assertEqual(value.cleanup,'reaped_closed')

    def test_A03_incomplete_transcript_finish_is_recoverable(self):
        _,supervisor,_=self.f.run();frames=supervisor._channel.frames
        v=r.HelperTranscriptH1(self.f.invocation)
        for raw in frames[:-1]:v.accept(raw)
        with self.assertRaises(c.ContractViolation2):v.finish()
        for operation in (lambda:v.accept(frames[-1]),v.finish):
            with self.assertRaises(c.ContractViolation2):operation()
        self.assertFalse(v.complete);self.assertTrue(v._failed)

    def test_A03_oversized_feed_does_not_latch(self):
        codec=p.HelperCodecH1(self.f.invocation);decoder=p.HelperStreamDecoderH1(codec)
        raw=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(self.f.invocation.fd_catalog_digest)))
        with self.assertRaises(c.ContractViolation2):decoder.feed(b'x'*(p.MAX_FRAME+1))
        for operation in (lambda:decoder.feed(raw),decoder.finish):
            with self.assertRaises(c.ContractViolation2):operation()
        self.assertTrue(decoder._failed);self.assertEqual(len(decoder._buffer),0)

    def test_A04_cancel_queue_grows_after_disabled_terminal(self):
        supervisor,k=self.f.supervisor(enabled=False);value=supervisor.run_fake()
        for _ in range(5000):supervisor.kill()
        self.assertLessEqual(len(supervisor._channel.cancel_frames),1)
        self.assertEqual(supervisor._channel.cancel_frames,[]);self.assertEqual(k.calls,[])
        self.assertIs(supervisor.run_fake(),value);self.assertTrue(supervisor._channel.closed)

    def test_A05_keyboard_interrupt_bypasses_terminal_and_registry_finish(self):
        k=self.f.kernel();lose_return(k,'poll_child',after=False,error=KeyboardInterrupt)
        supervisor,k=self.f.supervisor(k)
        with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
        self.assert_terminal(supervisor,k);self.assert_no_orphans(k)
        self.assertIn(35,k.closed_received)

    def test_A06_non_executable_mode_gets_success(self):
        i=self.f.invocation;exe=replace(i.executable,mode=0o100644)
        spec=replace(i.descriptors[1],identity=replace(i.descriptors[1].identity,
            object_digest=p.executable_object_digest_h1(exe)))
        with self.assertRaises(c.ContractViolation2):
            replace(i,executable=exe,descriptors=(i.descriptors[0],spec,*i.descriptors[2:]))

    def test_A07_oversized_transfer_skips_close_on_abort(self):
        k=self.f.kernel();k.received=(*k.received,p.ReceivedDescriptorH1('stdout_pipe',100),
                                    p.ReceivedDescriptorH1('stderr_pipe',101))
        value,supervisor,k=self.f.run(k)
        self.assertEqual(value.reason,'fd_transfer_invalid');self.assert_terminal(supervisor,k)
        self.assert_no_orphans(k);self.assertEqual(len(k.closed_received),9)
        self.assertEqual(value.cleanup,'reaped_closed')


class OwnershipAndFDTests(FixtureCase):
    def test_registration_all_partial_effect_windows(self):
        for method in ('register_helper','reserve_child','dispatch_helper','exec_fd_child'):
            for after in (False,True):
                with self.subTest(method=method,after=after):
                    k=self.f.kernel();fired=lose_return(k,method,after=after)
                    _,supervisor,k=self.f.run(k)
                    self.assertTrue(fired);self.assert_terminal(supervisor,k);self.assert_no_orphans(k)

    def test_escrow_exists_before_helper_and_child_effect(self):
        k=self.f.kernel()
        for method,role in (('register_helper','helper'),('reserve_child','child')):
            original=getattr(k,method)
            def checked(*args,_original=original,_role=role):
                self.assertIn((self.f.invocation.digest,_role),k._escrows)
                return _original(*args)
            setattr(k,method,checked)
        value,_,k=self.f.run(k)
        self.assertEqual(value.result,'helper_fake_capture_preserved');self.assert_no_orphans(k)

    def test_failure_to_recover_is_quarantine(self):
        k=self.f.kernel();original=k.register_helper
        def lost(*args):
            original(*args);k.recovery_ok=False;raise RuntimeError('lost return')
        k.register_helper=lost
        value,supervisor,k=self.f.run(k)
        self.assert_terminal(supervisor,k)
        self.assertEqual(value.cleanup,'cleanup_unproven');self.assertTrue(k._objects)
        self.assertTrue(any(not obj['closed'] for obj in k._objects.values()))

    def test_recovery_cannot_target_foreign_invocation_or_role(self):
        k=self.f.kernel();i=self.f.invocation;k.prepare_owned(i,'helper');token=k.register_helper(i)
        with self.assertRaises(c.ContractViolation2):k.recover_owned(replace(i,nonce=hd('foreign')),'helper')
        with self.assertRaises(c.ContractViolation2):k.recover_owned(i,'arbitrary')
        with self.assertRaises(c.ContractViolation2):k.kill_owned(12345)
        self.assertTrue(k._objects[token]['running'])

    def test_cardinality_zero_six_seven_eight_nine(self):
        for count in (0,6,7,8,9):
            with self.subTest(count=count):
                k=self.f.kernel();rows=k.received
                if count<7:rows=rows[:count]
                else:rows=(*rows,*(p.ReceivedDescriptorH1('stdout_pipe',100+n) for n in range(count-7)))
                k.received=rows;value,supervisor,k=self.f.run(k)
                self.assertEqual(value.result,'helper_fake_capture_preserved' if count==7 else 'unknown')
                self.assert_no_orphans(k);self.assertEqual(len(k.closed_received),count)
                self.assertEqual(value.cleanup,'reaped_closed')

    def test_malformed_projection_does_not_erase_owned_fds(self):
        for bad in (None,object(),('control',999),999):
            with self.subTest(bad=type(bad).__name__):
                k=self.f.kernel();k.received=(bad,*k.received[1:])
                value,_,k=self.f.run(k)
                self.assertEqual(value.result,'unknown');self.assert_no_orphans(k)
                self.assertEqual(k.closed_received,set(range(30,37)))
                self.assertNotIn(999,k.closed_received)

    def test_arbitrary_row_numbers_do_not_authorize_close(self):
        k=self.f.kernel();channel=r.ControlChannelH1(self.f.invocation)
        raw=channel.codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(self.f.invocation.fd_catalog_digest)))
        forged=(p.ReceivedDescriptorH1('namespace',999),*k.received[1:])
        reason,clean=r.StandaloneHelperH1().run_fake(self.f.invocation,raw,forged,k,channel)
        self.assertEqual(reason,'fd_transfer_invalid');self.assertTrue(clean)
        self.assert_no_orphans(k);self.assertNotIn(999,k.closed_received)

    def test_duplicates_closed_once(self):
        k=self.f.kernel();k.received=(*k.received,k.received[0],k.received[0])
        value,_,k=self.f.run(k)
        self.assertEqual(value.result,'unknown');self.assert_no_orphans(k)
        self.assertEqual(k.closed_received,set(range(30,37)))

    def test_receive_cap_before_ownership_allocation(self):
        k=self.f.kernel();before=dict(k._transfer_catalog)
        rows=tuple(p.ReceivedDescriptorH1('stdout_pipe',100+n) for n in range(fake.MAX_TRANSFER_FDS+1))
        with self.assertRaises(c.ContractViolation2):k.received=rows
        self.assertEqual(k._transfer_catalog,before)
        value,_,k=self.f.run(k);self.assertEqual(value.result,'helper_fake_capture_preserved')

    def test_closed_fd_operations_refuse(self):
        k=self.f.kernel();i=self.f.invocation;k.transfer_receipt(i)
        k.close_transferred(k.received)
        checks=(lambda:k.describe_fd(30),lambda:k.parent_alive(36,i.parent_pid,i.parent_start_ticks),
                lambda:k.verify_executable_fd(31,i.executable),lambda:k.enter_namespace(30),
                lambda:k.prepare_child_fds({row.slot:row.local_fd for row in k.received},(0,1,2)),
                lambda:k.identity('final'))
        for operation in checks:
            with self.assertRaises(c.ContractViolation2):operation()
        self.assertEqual(k.open_transferred_count,0)

    def test_coherent_executable_replacement_after_admission(self):
        k=self.f.kernel()
        def replace_live():
            observed=replace(k.executable_observation,inode=999,sha256=hd('replacement'))
            k.executable_observation=observed
            k.fd_facts[31]=replace(k.fd_facts[31],inode=999,generation=2,
                                  object_digest=p.executable_object_digest_h1(observed))
        k.on_poll=replace_live
        value,supervisor,k=self.f.run(k)
        self.assert_terminal(supervisor,k)
        self.assertEqual(value.cleanup,'cleanup_unproven')
        self.assertNotIn(31,k.closed_received,'replacement must not be a close target')
        self.assertEqual(k.open_transferred_count,1)

    def test_inconsistent_executable_metadata_is_not_ignored(self):
        k=self.f.kernel()
        k.on_poll=lambda:setattr(k,'fd_facts',{**k.fd_facts,31:replace(k.fd_facts[31],inode=999,generation=2)})
        value,_,k=self.f.run(k)
        self.assertEqual(value.result,'unknown');self.assertEqual(value.cleanup,'cleanup_unproven')

    def test_observed_identity_does_not_rebuild_expected_facts(self):
        k=self.f.kernel();k.identity_observation=replace(k.identity_observation,helper_start_ticks=999)
        value,_,k=self.f.run(k)
        self.assertEqual(value.reason,'pid_reuse');self.assert_no_orphans(k)

    def test_each_owned_fd_close_failure_is_quarantine(self):
        for fd in range(30,37):
            with self.subTest(fd=fd):
                k=self.f.kernel();original=k.close_transferred;failed=[]
                def close(rows):
                    if any(row.local_fd==fd for row in rows) and not failed:
                        failed.append(True);original(tuple(row for row in rows if row.local_fd!=fd))
                        return False
                    return original(rows)
                k.close_transferred=close
                value,supervisor,k=self.f.run(k)
                self.assertTrue(failed);self.assert_terminal(supervisor,k)
                self.assertEqual(value.cleanup,'cleanup_unproven')
                self.assert_no_orphans(k)  # Successful fallback must not erase the earlier fault.


class InterruptionAndCleanupTests(FixtureCase):
    def test_partial_registry_reservation_cannot_leave_circuit_open(self):
        supervisor,k=self.f.supervisor()
        def partial(invocation,owner):
            supervisor.registry._owner=owner
            supervisor.registry._seen.add(invocation.invocation_uuid)
            raise KeyboardInterrupt('partial reserve before active assignment')
        supervisor.registry.reserve=partial
        with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
        self.assert_terminal(supervisor,k)
        self.assertIsNone(supervisor.registry._owner);self.assertEqual(k.calls,[])

    def test_keyboard_interrupt_all_process_boundaries(self):
        for method in ('register_helper','reserve_child','dispatch_helper','exec_fd_child','poll_child'):
            for after in (False,True):
                with self.subTest(method=method,after=after):
                    k=self.f.kernel();fired=lose_return(k,method,after=after,error=KeyboardInterrupt)
                    supervisor,k=self.f.supervisor(k)
                    with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
                    self.assertTrue(fired);self.assert_terminal(supervisor,k);self.assert_no_orphans(k)

    def test_interrupt_before_and_after_escrow(self):
        for role in ('helper','child'):
            for after in (False,True):
                with self.subTest(role=role,after=after):
                    k=self.f.kernel();lose_return(k,'prepare_owned',role=role,after=after,error=KeyboardInterrupt)
                    supervisor,k=self.f.supervisor(k)
                    with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
                    self.assert_terminal(supervisor,k);self.assert_no_orphans(k)

    def test_interrupt_all_cleanup_steps(self):
        for method in ('terminate_owned','owned_running','drain_owned','kill_owned','reap_owned',
                       'close_owned','close_transferred','close_control'):
            for after in (False,True):
                with self.subTest(method=method,after=after):
                    k=self.f.kernel();k.polls=();k.step_us=0;k.term_effective=False;k.on_poll=abort_poll
                    fired=lose_return(k,method,after=after,error=KeyboardInterrupt)
                    supervisor,k=self.f.supervisor(k)
                    with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
                    self.assertTrue(fired);value=self.assert_terminal(supervisor,k)
                    self.assertEqual(value.cleanup,'cleanup_unproven')
                    self.assert_no_orphans(k)

    def test_regular_faults_all_cleanup_steps(self):
        for method in ('terminate_owned','owned_running','drain_owned','kill_owned','reap_owned',
                       'close_owned','close_transferred','close_control'):
            with self.subTest(method=method):
                k=self.f.kernel();k.polls=();k.step_us=0;k.term_effective=False;k.on_poll=abort_poll
                fired=lose_return(k,method,after=False)
                value,supervisor,k=self.f.run(k)
                self.assertTrue(fired);self.assert_terminal(supervisor,k)
                self.assertEqual(value.cleanup,'cleanup_unproven');self.assert_no_orphans(k)

    def test_interrupt_registry_reserve_and_finish(self):
        for method in ('reserve','finish'):
            for after in (False,True):
                with self.subTest(method=method,after=after):
                    supervisor,k=self.f.supervisor();original=getattr(supervisor.registry,method)
                    fired=[]
                    def interrupt(*args):
                        if fired:return original(*args)
                        fired.append(True)
                        if after:original(*args)
                        raise KeyboardInterrupt('synthetic registry interruption')
                    setattr(supervisor.registry,method,interrupt)
                    with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
                    value=supervisor._terminal;self.assertIsNotNone(value);self.assertEqual(value.result,'unknown')
                    self.assertIsNone(supervisor.registry._active)
                    if after or method=='finish':self.assertTrue(supervisor.registry._circuit)
                    calls=tuple(k.calls);self.assertIs(supervisor.run_fake(),value);self.assertEqual(tuple(k.calls),calls)
                    if method=='finish':self.assert_no_orphans(k)

    def test_interrupt_publication_before_and_after_candidate(self):
        for after in (False,True):
            with self.subTest(after=after):
                supervisor,k=self.f.supervisor();original=supervisor._publish
                def interrupt(*args):
                    if after:original(*args)
                    self.assertIsNone(supervisor._terminal)
                    raise KeyboardInterrupt('synthetic publication failure')
                supervisor._publish=interrupt
                with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
                value=self.assert_terminal(supervisor,k);self.assert_no_orphans(k)
                self.assertEqual(value.cleanup,'cleanup_unproven')

    def test_baseexception_is_rethrown_after_finalization(self):
        class StopModel(BaseException):pass
        k=self.f.kernel();lose_return(k,'poll_child',error=StopModel)
        supervisor,k=self.f.supervisor(k)
        with self.assertRaises(StopModel):supervisor.run_fake()
        self.assert_terminal(supervisor,k);self.assert_no_orphans(k)

    def test_clock_failure_still_attempts_kill_reap_close(self):
        k=self.f.kernel();original=k.clock;fired=[]
        def clock():
            if any(call[0]=='term' for call in k.calls) and not fired:
                fired.append(True);raise KeyboardInterrupt('cleanup clock')
            return original()
        k.clock=clock;k.polls=();k.step_us=0;k.term_effective=False;k.on_poll=abort_poll
        supervisor,k=self.f.supervisor(k)
        with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
        value=self.assert_terminal(supervisor,k);self.assert_no_orphans(k)
        self.assertEqual(value.cleanup,'cleanup_unproven')
        self.assertTrue(any(call[0]=='kill' for call in k.calls))

    def test_permanent_reap_failure_cannot_claim_closed(self):
        k=self.f.kernel();k.reap_ok=False
        value,supervisor,k=self.f.run(k)
        self.assert_terminal(supervisor,k);self.assertEqual(value.cleanup,'cleanup_unproven')
        self.assertTrue(any(not obj['reaped'] or not obj['closed'] for obj in k._objects.values()))

    def test_permanent_close_failure_is_visible(self):
        k=self.f.kernel();k.transfer_close_ok=False
        value,supervisor,k=self.f.run(k)
        self.assert_terminal(supervisor,k);self.assertEqual(value.cleanup,'cleanup_unproven')
        self.assertGreater(k.open_transferred_count,0)


class FailureAndCancellationTests(FixtureCase):
    def test_parser_interrupts_latch_without_suppression(self):
        codec=p.HelperCodecH1(self.f.invocation)
        raw=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(self.f.invocation.fd_catalog_digest)))
        decoder=p.HelperStreamDecoderH1(codec)
        original=p.HelperCodecH1.decode
        def interrupt(*args):raise KeyboardInterrupt('synthetic parser interruption')
        p.HelperCodecH1.decode=interrupt
        try:
            with self.assertRaises(KeyboardInterrupt):decoder.feed(raw)
        finally:p.HelperCodecH1.decode=original
        self.assertTrue(decoder._failed)
        with self.assertRaises(c.ContractViolation2):decoder.feed(raw)
        verifier=r.HelperTranscriptH1(self.f.invocation)
        verifier._accept=interrupt
        with self.assertRaises(KeyboardInterrupt):verifier.accept(raw)
        self.assertTrue(verifier._failed)

    def test_other_supervisor_cannot_finalize_active_owner(self):
        registry=r.OwnedInvocationRegistryH1(self.f.invocation.session.session_uuid)
        first,k=self.f.supervisor(registry=registry);second,foreign_kernel=self.f.supervisor(registry=registry)
        entered=threading.Event();resume=threading.Event();outcomes=[];errors=[]
        def block_once():
            if not entered.is_set():
                entered.set()
                if not resume.wait(timeout=5):raise RuntimeError('test synchronization timeout')
        k.on_poll=block_once
        def run():
            try:outcomes.append(first.run_fake())
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=run);thread.start()
        try:
            self.assertTrue(entered.wait(timeout=5))
            value=second.run_fake();self.assertEqual(value.reason,'sequence_invalid')
            self.assertTrue(registry.active_for(self.f.invocation,first));self.assertFalse(registry._circuit)
            self.assertEqual(foreign_kernel.calls,[])
        finally:resume.set();thread.join(timeout=5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(outcomes[0].result,'helper_fake_capture_preserved');self.assert_no_orphans(k)

    def test_decoder_all_fatal_inputs_latch(self):
        codec=p.HelperCodecH1(self.f.invocation)
        valid=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(self.f.invocation.fd_catalog_digest)))
        cases=(b'x'*(p.MAX_FRAME+1),None,bytearray(valid),b'BAD!'+valid[4:])
        for malformed in cases:
            with self.subTest(kind=type(malformed).__name__,size=len(malformed) if malformed is not None else 0):
                decoder=p.HelperStreamDecoderH1(codec)
                with self.assertRaises(c.ContractViolation2):decoder.feed(malformed)
                for operation in (lambda:decoder.feed(valid),decoder.finish):
                    with self.assertRaises(c.ContractViolation2):operation()
                self.assertTrue(decoder._failed);self.assertEqual(len(decoder._buffer),0)

    def test_decoder_incomplete_eof_and_successful_eof_are_sealed(self):
        codec=p.HelperCodecH1(self.f.invocation)
        valid=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(self.f.invocation.fd_catalog_digest)))
        for prefix in (valid[:1],valid[:-1]):
            decoder=p.HelperStreamDecoderH1(codec);decoder.feed(prefix)
            with self.assertRaises(c.ContractViolation2):decoder.finish()
            with self.assertRaises(c.ContractViolation2):decoder.feed(valid)
        decoder=p.HelperStreamDecoderH1(codec);decoder.feed(valid);decoder.finish();decoder.finish()
        with self.assertRaises(c.ContractViolation2):decoder.feed(valid)
        self.assertTrue(decoder._failed)

    def test_each_truncated_invoke_prefix_is_failed_terminal(self):
        codec=p.HelperCodecH1(self.f.invocation)
        raw=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(self.f.invocation.fd_catalog_digest)))
        for length in range(1,len(raw)):
            with self.subTest(length=length):
                decoder=p.HelperStreamDecoderH1(codec);decoder.feed(raw[:length])
                with self.assertRaises(c.ContractViolation2):decoder.finish()
                with self.assertRaises(c.ContractViolation2):decoder.feed(raw[length:])
                self.assertTrue(decoder._failed)

    def test_transcript_failed_state_is_stable(self):
        _,supervisor,_=self.f.run();frames=supervisor._channel.frames
        for bad in (b'wrong',frames[1]):
            v=r.HelperTranscriptH1(self.f.invocation)
            with self.assertRaises(c.ContractViolation2):v.accept(bad)
            state=(v.sequence,v.stage,len(v.stdout),v.complete)
            for raw in frames:
                with self.assertRaises(c.ContractViolation2):v.accept(raw)
            with self.assertRaises(c.ContractViolation2):v.finish()
            self.assertEqual((v.sequence,v.stage,len(v.stdout),v.complete),state)

    def test_thousands_of_cancel_before_and_after_consume(self):
        channel=r.ControlChannelH1(self.f.invocation)
        for _ in range(10000):channel.cancel()
        self.assertEqual(len(channel.cancel_frames),1);self.assertTrue(channel.receive_cancel())
        for _ in range(10000):channel.cancel()
        self.assertEqual(channel.cancel_frames,[])
        channel.seal();channel.cancel();self.assertEqual(channel.cancel_frames,[])

    def test_cancel_after_all_terminal_kinds_is_bounded(self):
        for mode in ('disabled','success','failure','close_failure'):
            with self.subTest(mode=mode):
                k=self.f.kernel()
                if mode=='failure':k.lost_spawn=True
                if mode=='close_failure':k.control_close_ok=False
                supervisor,k=self.f.supervisor(k,enabled=mode!='disabled');value=supervisor.run_fake()
                for _ in range(5000):supervisor.kill()
                self.assertEqual(supervisor._channel.cancel_frames,[])
                self.assertIs(supervisor.run_fake(),value)
                with self.assertRaises(c.ContractViolation2):supervisor.admit(value)

    def test_cancel_between_child_reserve_and_exec(self):
        supervisor,k=self.f.supervisor();original=k.reserve_child
        def reserve(*args):
            owned=original(*args);supervisor.kill();return owned
        k.reserve_child=reserve
        value=supervisor.run_fake();self.assertEqual(value.reason,'killed')
        self.assertFalse(any(call[0]=='exec_fd_child' for call in k.calls))
        self.assertFalse(supervisor._channel.dispatch_committed);self.assert_no_orphans(k)

    def test_cancel_between_helper_registration_and_dispatch(self):
        supervisor,k=self.f.supervisor();original=k.register_helper
        def register(*args):
            owned=original(*args);supervisor.kill();return owned
        k.register_helper=register
        value=supervisor.run_fake();self.assertEqual(value.reason,'killed')
        self.assertFalse(any(call[0]=='dispatch_helper' for call in k.calls));self.assert_no_orphans(k)

    def test_cancel_after_commit_is_cleanup_not_reversal(self):
        supervisor,k=self.f.supervisor();original=k.exec_fd_child
        def execute(*args):
            self.assertTrue(supervisor._channel.dispatch_committed)
            supervisor.kill();return original(*args)
        k.exec_fd_child=execute
        value=supervisor.run_fake();self.assertEqual(value.reason,'killed')
        self.assertEqual(sum(call[0]=='exec_fd_child' for call in k.calls),1);self.assert_no_orphans(k)

    def test_concurrent_kill_queue_does_not_grow(self):
        channel=r.ControlChannelH1(self.f.invocation);barrier=threading.Barrier(5);errors=[]
        def cancel():
            try:
                barrier.wait(timeout=5)
                for _ in range(1000):channel.cancel()
            except BaseException as error:errors.append(error)
        threads=[threading.Thread(target=cancel) for _ in range(4)]
        for thread in threads:thread.start()
        barrier.wait(timeout=5)
        for thread in threads:thread.join(timeout=5);self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[]);self.assertEqual(len(channel.cancel_frames),1)

    def test_publication_interruption_never_issues_success(self):
        supervisor,k=self.f.supervisor();original=supervisor._publish
        def publication(*args):
            candidate=original(*args)
            self.assertEqual(candidate.result,'helper_fake_capture_preserved')
            self.assertIsNone(supervisor._terminal)
            raise KeyboardInterrupt('candidate is not issued')
        supervisor._publish=publication
        with self.assertRaises(KeyboardInterrupt):supervisor.run_fake()
        self.assert_terminal(supervisor,k)
        with self.assertRaises(c.ContractViolation2):supervisor.admit(supervisor._terminal)


class ExecutableAndIsolationTests(FixtureCase):
    def fixture_with_observed_mode(self,invocation,mode):
        observed=replace(self.f.observations.executable,mode=0o100000|mode)
        facts=tuple((fd,replace(row,object_digest=p.executable_object_digest_h1(observed)))
                    if fd==31 else (fd,row) for fd,row in self.f.observations.descriptor_facts)
        identity=replace(self.f.observations.identity,
                         executable_object_digest=p.executable_object_digest_h1(observed))
        observations=replace(self.f.observations,executable=observed,descriptor_facts=facts,identity=identity)
        return HelperFixtureH1(invocation,self.f.polls,observations)

    def test_fake_requires_explicit_observations(self):
        with self.assertRaises(TypeError):fake.FakeHelperKernelH1(self.f.invocation,self.f.polls)
        with self.assertRaises(c.ContractViolation2):HelperFixtureH1(self.f.invocation,self.f.polls).kernel()

    def test_changing_expected_invocation_does_not_change_observed_facts(self):
        i=self.altered_invocation(0o751)
        fixture=HelperFixtureH1(i,self.f.polls,self.f.observations)
        value,_,k=fixture.run();self.assertEqual(value.result,'unknown');self.assert_no_orphans(k)
        self.assertFalse(any(call[0]=='enter_namespace_child_only' for call in k.calls))

    def test_foreign_registry_session_rejected_before_driver(self):
        k=self.f.kernel();registry=r.OwnedInvocationRegistryH1(uid(99999))
        with self.assertRaises(c.ContractViolation2):self.f.supervisor(k,registry=registry)
        self.assertEqual(k.calls,[])

    def altered_invocation(self,mode,*,principal=None,gid=0):
        i=self.f.invocation;exe=replace(i.executable,mode=0o100000|mode,gid=gid)
        policy=i.policy if principal is None else replace(i.policy,command_principal=principal)
        spec=replace(i.descriptors[1],identity=replace(i.descriptors[1].identity,
            object_digest=p.executable_object_digest_h1(exe)))
        return replace(i,policy=policy,executable=exe,descriptors=(i.descriptors[0],spec,*i.descriptors[2:]))

    def test_modes_zero_sixhundred_sixfourfour_sevenfivefive(self):
        for mode in (0o000,0o600,0o644):
            with self.subTest(mode=oct(mode)),self.assertRaises(c.ContractViolation2):self.altered_invocation(mode)
        i=self.altered_invocation(0o755);value,_,k=self.fixture_with_observed_mode(i,0o755).run()
        self.assertEqual(value.result,'helper_fake_capture_preserved');self.assert_no_orphans(k)

    def test_owner_group_other_execute_selection(self):
        principal=self.f.invocation.policy.command_principal
        with self.assertRaises(c.ContractViolation2):self.altered_invocation(0o750)
        group=replace(principal,supplementary_groups=(0,))
        i=self.altered_invocation(0o750,principal=group)
        value,_,_=self.fixture_with_observed_mode(i,0o750).run()
        self.assertEqual(value.result,'helper_fake_capture_preserved')
        with self.assertRaises(c.ContractViolation2):self.altered_invocation(0o701,principal=group)
        root=replace(principal,uid=0)
        self.altered_invocation(0o100,principal=root)
        with self.assertRaises(c.ContractViolation2):self.altered_invocation(0o644,principal=root)

    def test_forbidden_modes_owners_and_file_kinds(self):
        for mode in (0o4755,0o2755,0o777,0o775):
            with self.subTest(mode=oct(mode)),self.assertRaises(c.ContractViolation2):self.altered_invocation(mode)
        exe=self.f.invocation.executable;principal=self.f.invocation.policy.command_principal
        for changed in (replace(exe,uid=1002),replace(exe,mode=0o040755),replace(exe,links=2),
                        replace(exe,no_file_capabilities=False),replace(exe,protected_ancestors=False)):
            with self.assertRaises(c.ContractViolation2):p.validate_executable_h1(changed,principal)

    def test_observed_execute_bits_not_inherited_from_expected(self):
        k=self.f.kernel();k.executable_observation=replace(k.executable_observation,mode=0o100644)
        value,_,k=self.f.run(k)
        self.assertEqual(value.result,'unknown');self.assert_no_orphans(k)

    def test_process_tree_remains_unproven(self):
        value,_,_=self.f.run()
        self.assertEqual(value.native_process_tree,'unproven')
        with self.assertRaises(TypeError):replace(value,native_process_tree='verified')
        for name in ('physical_probe_permitted','ownership_proven','isolation_verified','management_policy_verified',
                     'measurement_verified','continuous_attestation'):self.assertIs(getattr(value,name),False)
        with self.assertRaises(FrozenInstanceError):value.reason='verified'

    def test_native_source_and_entry_guards_are_still_closed_static(self):
        root=Path(r.__file__).parent;tree=ast.parse((root/'native_v2_helper_native.py').read_text())
        guard=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='native_guard_h1')
        self.assertIsInstance(guard.body[0],ast.Raise)
        for cls in (n for n in tree.body if isinstance(n,ast.ClassDef)):
            for method in (n for n in cls.body if isinstance(n,ast.FunctionDef)):
                self.assertEqual(method.body[0].value.func.id,'native_guard_h1')
        for filename in ('native_v2_helper_protocol.py','native_v2_helper_runtime.py','native_v2_helper_fake.py'):
            source=ast.parse((root/filename).read_text())
            imports=[n for n in ast.walk(source) if isinstance(n,(ast.Import,ast.ImportFrom))]
            for node in imports:
                modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or '']
                self.assertFalse(set(modules)&{'os','socket','subprocess','ctypes','multiprocessing'})


if __name__=='__main__':
    if '--assert-safe' in sys.argv:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(AuditSafeExpectations)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    unittest.main()
