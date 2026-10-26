"""Independent read-only H1 re-review, 2026-10-22.

Default: assert observed defect reproductions (green is NOT a security pass).
--assert-safe: assert safe outcomes for the same new findings; failures expected
on the audited source. No production/test/fixture files are changed.
"""
import ast
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import unittest

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_capture_contracts as cap
from trusted_checker_network import native_v2_helper_protocol as p
from trusted_checker_network import native_v2_helper_runtime as r
from trusted_checker_network import native_v2_helper_fake as fake
from trusted_checker_network import native_v2_helper_identity as identity
from trusted_checker_network.tests.native_v2_helper_support import HelperFixtureH1,hd,uid

SAFE='--assert-safe' in sys.argv
if SAFE:sys.argv.remove('--assert-safe')
HERE=Path(__file__).resolve().parent
EVIDENCE={}


def evidence(key,**values):EVIDENCE[key]=values


def catalog(kernel):
    return {'processes':{token:dict(obj) for token,obj in kernel._objects.items()},
            'owned_fds':sorted(kernel._transfer_catalog),'closed_fds':sorted(kernel.closed_received),
            'unresolved_fds':kernel.open_transferred_count}


def one_fault(target,name,error,*,after=True,limit=1,predicate=None):
    original=getattr(target,name);fired=[]
    def call(*args,**kwargs):
        if len(fired)>=limit or (predicate is not None and not predicate(*args,**kwargs)):
            return original(*args,**kwargs)
        fired.append(True)
        if after:original(*args,**kwargs)
        raise error('independent synthetic fault')
    setattr(target,name,call)
    return fired


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.f=HelperFixtureH1.create()

    def clean(self,kernel):
        self.assertEqual(kernel.open_transferred_count,0)
        self.assertTrue(all(not obj['running'] and obj['reaped'] and obj['closed']
                            for obj in kernel._objects.values()),catalog(kernel))
        closed=[call[1] for call in kernel.calls if call[0]=='close_fd']
        self.assertEqual(len(closed),len(set(closed)))

    def terminal(self,s,k):
        self.assertIsNotNone(s._terminal)
        calls=tuple(k.calls);value=s._terminal
        self.assertIs(s.run_fake(),value);self.assertEqual(tuple(k.calls),calls)
        return value


class NewFindings(Base):
    def test_R01_supplied_external_inherited_fd_is_hidden(self):
        f=self.f;obs=f.observations;external=999
        changed=replace(obs,
            descriptor_facts=(*obs.descriptor_facts,(external,p.DescriptorIdentityH1('char',1,9009,1,hd('external-held-fd')))),
            identity=replace(obs.identity,inherited_fds=(*obs.identity.inherited_fds,external)))
        k=fake.FakeHelperKernelH1(f.invocation,f.polls,observations=changed)
        actual_before=k.identity_observation.inherited_fds
        seen=k.identity('before').inherited_fds
        value,s,k=f.run(k)
        evidence('R01',result=value.result,reason=value.reason,cleanup=value.cleanup,
                 supplied_inherited=list(actual_before),validated_inherited=list(seen),
                 foreign_closed=external in k.closed_received,remaining_descriptor_facts=external in k.fd_facts,
                 accounting=catalog(k))
        self.assertNotIn(external,k.closed_received,'foreign FD must not become cleanup target')
        if SAFE:self.assertEqual(value.result,'unknown')
        else:
            self.assertEqual(value.result,'helper_fake_capture_preserved')
            self.assertIn(external,actual_before);self.assertNotIn(external,seen)

    def test_R02_fresh_registry_can_clean_active_other_owner(self):
        f=self.f;k=f.kernel();first,k=f.supervisor(k);i=f.invocation
        # Exact valid first-attempt prefix, paused after owned helper dispatch.
        first.registry.reserve(i,first);k.prepare_owned(i,'helper')
        token=k.register_helper(i);k.dispatch_helper(token,i)
        before=dict(k._objects[token])
        second,k=f.supervisor(k,registry=r.OwnedInvocationRegistryH1(i.session.session_uuid))
        value=second.run_fake();after=dict(k._objects[token])
        evidence('R02',second_result=value.result,second_reason=value.reason,second_cleanup=value.cleanup,
                 before=before,after=after,first_registry_still_active=first.registry.active_for(i,first),
                 second_registry_circuit=second.registry._circuit,accounting=catalog(k))
        self.assertEqual(value.reason,'replay')
        self.assertTrue(first.registry.active_for(i,first))
        if SAFE:self.assertEqual(after,before,'rejected second attempt must not reap/close first owner')
        else:
            self.assertTrue(before['running']);self.assertFalse(after['running'])
            self.assertTrue(after['reaped'] and after['closed'])

    def test_R03_clock_advancement_after_fence_before_publication(self):
        s,k=self.f.supervisor();i=self.f.invocation;original=s._publish;start=k.now
        def delay(*args):
            k.now=cap.CaptureTime2(start.wall_utc_us+600000,start.monotonic_us+600000)
            return original(*args)
        s._publish=delay;value=s.run_fake()
        evidence('R03',result=value.result,current_monotonic_us=k.now.monotonic_us,
                 deadline_monotonic_us=i.deadline_monotonic_us,elapsed_wall_us=k.now.wall_utc_us-start.wall_utc_us,
                 cleanup=value.cleanup,accounting=catalog(k))
        self.clean(k)
        self.assertGreater(k.now.monotonic_us,i.deadline_monotonic_us)
        if SAFE:self.assertEqual(value.result,'unknown')
        else:self.assertEqual(value.result,'helper_fake_capture_preserved')

    def test_R04_reentrant_and_concurrent_cancel_lock_cycle(self):
        s,k=self.f.supervisor();entered=threading.Event();external_in_cancel=threading.Event()
        internal_kill=threading.Event();errors=[];completed=[];original_exec=k.exec_fd_child
        def execute(*args):
            entered.set()
            if not external_in_cancel.wait(timeout=3):raise RuntimeError('audit synchronization timeout')
            internal_kill.set();s.kill()  # Waits for state held by external kill.
            return original_exec(*args)
        k.exec_fd_child=execute
        def run():
            try:completed.append(s.run_fake())
            except BaseException as error:errors.append(type(error).__name__)
        primary=threading.Thread(target=run,name='audit-primary',daemon=True)
        primary.start();self.assertTrue(entered.wait(timeout=3))
        original_cancel=s._channel.cancel
        def marked_cancel():
            external_in_cancel.set()
            return original_cancel()  # Waits for control held by dispatch.
        s._channel.cancel=marked_cancel
        canceller=threading.Thread(target=s.kill,name='audit-external-cancel',daemon=True)
        canceller.start();self.assertTrue(internal_kill.wait(timeout=3))
        primary.join(timeout=.25);canceller.join(timeout=.25)
        blocked=primary.is_alive() and canceller.is_alive()
        def stack(thread):
            frame=sys._current_frames().get(thread.ident);items=[]
            while frame is not None:
                items.append({'function':frame.f_code.co_name,'line':frame.f_lineno,
                              'file':Path(frame.f_code.co_filename).name});frame=frame.f_back
            return items
        evidence('R04',both_blocked=blocked,terminal=s._terminal is not None,
                 active=s.registry.active_for(self.f.invocation,s),circuit=s.registry._circuit,
                 cancellation_set=s._cancel.is_set(),dispatch_committed=s._channel.dispatch_committed,
                 primary_stack=stack(primary),cancel_stack=stack(canceller),errors=errors,
                 completed=len(completed),accounting=catalog(k))
        # These two isolated daemon audit threads are deliberately blocked only
        # in this test process; interpreter exit discards them. No helper/OS
        # process was launched. No native resource is targeted for cleanup.
        if SAFE:self.assertFalse(blocked,'cancel/dispatch must have a consistent lock order')
        else:
            self.assertTrue(blocked);self.assertIsNone(s._terminal)
            self.assertEqual(completed,[]);self.assertEqual(errors,[])

    def test_R05_interrupt_after_terminal_assignment_changes_issued_record(self):
        s,k=self.f.supervisor();lock=s._state
        class ExitInterrupt:
            def __init__(self):self.depth=0;self.fired=False;self.issued=None;self.admitted=False
            def __enter__(self):lock.acquire();self.depth+=1;return self
            def __exit__(self,*args):
                self.depth-=1
                inject=self.depth==0 and s._terminal is not None and not self.fired
                if inject:
                    self.fired=True;self.issued=s._terminal
                    try:self.admitted=s.admit(self.issued) is self.issued
                    except c.ContractViolation2:self.admitted=False
                lock.release()
                if inject:raise KeyboardInterrupt('after actual publication assignment')
        monitor=ExitInterrupt();s._state=monitor
        with self.assertRaises(KeyboardInterrupt):s.run_fake()
        after=self.terminal(s,k);self.clean(k)
        evidence('R05',issued=monitor.issued.result,admitted_before_interrupt=monitor.admitted,
                 terminal_after=after.result,same_object=monitor.issued is after,
                 circuit=s.registry._circuit,accounting=catalog(k))
        if SAFE:self.assertTrue(not monitor.admitted or after is monitor.issued)
        else:
            self.assertTrue(monitor.admitted);self.assertEqual(monitor.issued.result,'helper_fake_capture_preserved')
            self.assertIsNot(after,monitor.issued);self.assertEqual(after.result,'unknown')


class OriginalFindingChecks(Base):
    def test_A01_positive_and_abort_fd_lifetime(self):
        results=[]
        for bad in (False,True):
            k=self.f.kernel();original=k._open_fd;closed_reads=[]
            def checked(fd):
                if fd in k.closed_received:closed_reads.append(fd)
                return original(fd)
            k._open_fd=checked
            if bad:k.invoke_transform=lambda raw:b'bad'
            value,s,k=self.f.run(k);self.clean(k);self.assertEqual(closed_reads,[])
            self.assertEqual(value.result,'unknown' if bad else 'helper_fake_capture_preserved')
            results.append(value.result)
        evidence('A01',results=results,no_closed_reads=True,no_double_close=True)

    def test_A02_lost_handle_before_after_allocation(self):
        outcomes=[]
        for method in ('register_helper','reserve_child'):
            for after in (False,True):
                with self.subTest(method=method,after=after):
                    k=self.f.kernel();one_fault(k,method,RuntimeError,after=after)
                    value,s,k=self.f.run(k);self.clean(k);self.assertEqual(value.result,'unknown')
                    self.assertIsNone(s.registry._active);self.assertTrue(s.registry._circuit)
                    outcomes.append({'method':method,'after':after,'cleanup':value.cleanup})
        evidence('A02',outcomes=outcomes,no_orphans=True)

    def test_A03_feed_accept_finish_failure_and_interruption(self):
        i=self.f.invocation;codec=p.HelperCodecH1(i)
        raw=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(i.fd_catalog_digest)))
        for bad in (b'x'*(p.MAX_FRAME+1),b'bad header!!',None):
            d=p.HelperStreamDecoderH1(codec)
            with self.assertRaises(c.ContractViolation2):d.feed(bad)
            with self.assertRaises(c.ContractViolation2):d.feed(raw)
            with self.assertRaises(c.ContractViolation2):d.finish()
            self.assertTrue(d._failed)
        _,s,_=self.f.run();frames=s._channel.frames
        v=r.HelperTranscriptH1(i)
        for item in frames[:-1]:v.accept(item)
        with self.assertRaises(c.ContractViolation2):v.finish()
        with self.assertRaises(c.ContractViolation2):v.accept(frames[-1])
        self.assertFalse(v.complete)
        v=r.HelperTranscriptH1(i)
        one_fault(v,'_accept',KeyboardInterrupt,after=False)
        with self.assertRaises(KeyboardInterrupt):v.accept(frames[0])
        with self.assertRaises(c.ContractViolation2):v.accept(frames[0])
        evidence('A03',latch=True,late_completion_rejected=True)

    def test_A04_parallel_kill_and_terminal_queue(self):
        s,k=self.f.supervisor(enabled=False);value=s.run_fake();threads=[];errors=[]
        def cancel():
            try:
                for _ in range(2500):s.kill()
            except BaseException as error:errors.append(type(error).__name__)
        for _ in range(4):
            thread=threading.Thread(target=cancel);threads.append(thread);thread.start()
        for thread in threads:thread.join(timeout=3);self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[]);self.assertEqual(s._channel.cancel_frames,[])
        self.assertIs(s.run_fake(),value);self.assertEqual(k.calls,[])
        evidence('A04',calls=10000,pending=0,default_off_calls=0)

    def test_A05_original_poll_interrupt_cleanup(self):
        k=self.f.kernel();one_fault(k,'poll_child',KeyboardInterrupt,after=False)
        s,k=self.f.supervisor(k)
        with self.assertRaises(KeyboardInterrupt):s.run_fake()
        self.clean(k);self.assertEqual(self.terminal(s,k).result,'unknown')
        self.assertIsNone(s.registry._active);self.assertTrue(s.registry._circuit)
        evidence('A05',original_case_closed=True,circuit=True,terminal='unknown')

    def test_A06_expected_modes_and_command_group_precedence(self):
        principal=self.f.invocation.policy.command_principal;exe=self.f.invocation.executable
        for mode in (0o000,0o600,0o644):
            with self.subTest(mode=oct(mode)),self.assertRaises(c.ContractViolation2):
                p.validate_executable_h1(replace(exe,mode=0o100000|mode),principal)
        p.validate_executable_h1(exe,principal)
        for mode,group,allowed in ((0o750,False,False),(0o750,True,True),(0o701,True,False),
                                   (0o701,False,True)):
            candidate=replace(exe,mode=0o100000|mode)
            actor=replace(principal,supplementary_groups=(0,) if group else ())
            if allowed:p.validate_executable_h1(candidate,actor)
            else:
                with self.assertRaises(c.ContractViolation2):p.validate_executable_h1(candidate,actor)
        evidence('A06',modes={'0000':'refused','0600':'refused','0644':'refused','0755':'admitted'},group_precedence=True)

    def test_A07_cardinality_malformed_duplicates_foreign(self):
        outcomes=[]
        for count in (0,6,7,8,9,16):
            k=self.f.kernel();rows=k.received[:count] if count<7 else (*k.received,
                *(p.ReceivedDescriptorH1('stdout_pipe',100+n) for n in range(count-7)))
            k.received=rows;value,s,k=self.f.run(k);self.clean(k)
            self.assertEqual(value.result,'helper_fake_capture_preserved' if count==7 else 'unknown')
            self.assertEqual(len(k.closed_received),count);outcomes.append({'received':count,'result':value.result})
        for projection in ('malformed','duplicates','foreign_argument'):
            k=self.f.kernel()
            if projection=='malformed':k.received=(None,*k.received[1:])
            elif projection=='duplicates':k.received=(*k.received,k.received[0])
            if projection=='foreign_argument':
                i=self.f.invocation;channel=r.ControlChannelH1(i)
                raw=channel.codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(i.fd_catalog_digest)))
                reason,_=r.StandaloneHelperH1().run_fake(i,raw,(p.ReceivedDescriptorH1('namespace',999),*k.received[1:]),k,channel)
                self.assertEqual(reason,'fd_transfer_invalid')
            else:self.f.run(k)
            self.clean(k);self.assertNotIn(999,k.closed_received)
        evidence('A07',outcomes=outcomes,malformed_closed=True,foreign_closed=False)


class IndependentInvariants(Base):
    def test_positive_complete_resource_catalog(self):
        value,s,k=self.f.run();self.clean(k)
        self.assertEqual(value.result,'helper_fake_capture_preserved')
        self.assertIsNone(s.registry._active);self.assertFalse(s.registry._circuit)
        evidence('I-positive',result=value.result,accounting=catalog(k))

    def test_recovery_is_idempotent_after_verified_cleanup(self):
        value,s,k=self.f.run();self.clean(k)
        for _ in range(3):
            self.assertIsNone(k.recover_owned(self.f.invocation,'child'))
            self.assertIsNone(k.recover_owned(self.f.invocation,'helper'))
        with self.assertRaises(c.ContractViolation2):k.recover_owned(replace(self.f.invocation,nonce=hd('other')),'helper')
        with self.assertRaises(c.ContractViolation2):k.kill_owned(12345)

    def test_recovery_failure_is_sticky_not_clean(self):
        for failure_number in (1,2,3,4):
            with self.subTest(failure_number=failure_number):
                k=self.f.kernel();original=k.recover_owned;calls=[]
                def recover(*args):
                    calls.append(args[1])
                    if len(calls)==failure_number:raise KeyboardInterrupt('recovery interruption')
                    return original(*args)
                k.recover_owned=recover;s,k=self.f.supervisor(k)
                with self.assertRaises(KeyboardInterrupt):s.run_fake()
                value=self.terminal(s,k)
                self.assertEqual(value.result,'unknown');self.assertTrue(s.registry._circuit)
                if k.cleanup_failed:self.assertEqual(value.cleanup,'cleanup_unproven')

    def test_two_faults_in_fallback_cleanup_preserve_unknown(self):
        k=self.f.kernel();k.polls=();k.step_us=0;k.term_effective=False
        def abort():raise RuntimeError('stop without child exit')
        k.on_poll=abort
        one_fault(k,'drain_owned',RuntimeError,after=False)
        one_fault(k,'reap_owned',KeyboardInterrupt,after=False,limit=2)
        s,k=self.f.supervisor(k)
        with self.assertRaises(KeyboardInterrupt):s.run_fake()
        value=self.terminal(s,k)
        self.assertEqual((value.result,value.cleanup),('unknown','cleanup_unproven'))
        self.assertTrue(s.registry._circuit);self.assertIsNone(s.registry._active)
        evidence('I-double-cleanup-fault',result=value.result,cleanup=value.cleanup,accounting=catalog(k))

    def test_before_after_every_effectful_boundary(self):
        outcomes=[]
        for method in ('prepare_owned','register_helper','reserve_child','dispatch_helper','exec_fd_child',
                       'poll_child','transfer_receipt','reap_owned','close_owned','close_transferred','close_control'):
            for after in (False,True):
                for error in (RuntimeError,KeyboardInterrupt):
                    with self.subTest(method=method,after=after,error=error.__name__):
                        k=self.f.kernel();one_fault(k,method,error,after=after);s,k=self.f.supervisor(k)
                        if error is KeyboardInterrupt:
                            with self.assertRaises(KeyboardInterrupt):s.run_fake()
                            value=s._terminal
                        else:value=s.run_fake()
                        self.assertIsNotNone(value);self.assertEqual(value.result,'unknown')
                        self.assertIsNone(s.registry._active);self.assertTrue(s.registry._circuit)
                        self.terminal(s,k)
                        leftovers=any(obj['running'] or not obj['reaped'] or not obj['closed'] for obj in k._objects.values())
                        if leftovers or k.open_transferred_count:
                            self.assertEqual(value.cleanup,'cleanup_unproven')
                        outcomes.append({'method':method,'after':after,'error':error.__name__,
                                         'cleanup':value.cleanup,'open_fds':k.open_transferred_count})
        evidence('I-effect-boundaries',cases=outcomes)

    def test_owned_close_failure_cannot_be_erased_by_recovery(self):
        k=self.f.kernel();original=k.close_transferred;failed=[]
        def close(rows):
            if not failed:
                failed.append(True);original(rows[:-1]);return False
            return original(rows)
        k.close_transferred=close;value,s,k=self.f.run(k)
        self.assertEqual((value.result,value.cleanup),('unknown','cleanup_unproven'));self.clean(k)
        self.assertTrue(s.registry._circuit)

    def test_coherent_generation_hash_replacement_is_quarantined(self):
        k=self.f.kernel()
        def replace_fd():
            observed=replace(k.executable_observation,inode=901,sha256=hd('new inode content'))
            k.executable_observation=observed
            k.fd_facts[31]=replace(k.fd_facts[31],inode=901,generation=2,
                                  object_digest=p.executable_object_digest_h1(observed))
        k.on_poll=replace_fd;value,s,k=self.f.run(k)
        self.assertEqual((value.result,value.cleanup),('unknown','cleanup_unproven'))
        self.assertNotIn(31,k.closed_received);self.assertEqual(k.open_transferred_count,1)
        evidence('I-coherent-replacement',result=value.result,cleanup=value.cleanup,accounting=catalog(k))

    def test_closed_operations_reject_without_double_close(self):
        k=self.f.kernel();i=self.f.invocation;k.transfer_receipt(i);k.close_transferred(k.received)
        for operation in (lambda:k.describe_fd(30),lambda:k.parent_alive(36,i.parent_pid,i.parent_start_ticks),
                          lambda:k.enter_namespace(30),lambda:k.verify_executable_fd(31,i.executable),
                          lambda:k.identity('final')):
            with self.assertRaises(c.ContractViolation2):operation()
        k.close_transferred(k.received)
        self.assertEqual(sum(call[0]=='close_fd' for call in k.calls),7)

    def test_receiver_cap_and_malformed_metadata(self):
        k=self.f.kernel();original=dict(k._transfer_catalog)
        rows=tuple(p.ReceivedDescriptorH1('stdout_pipe',100+n) for n in range(17))
        with self.assertRaises(c.ContractViolation2):k.received=rows
        self.assertEqual(original,k._transfer_catalog)
        value,_,k=self.f.run(k);self.clean(k);self.assertEqual(value.result,'helper_fake_capture_preserved')

    def test_common_registry_preserves_active_owner(self):
        f=self.f;i=f.invocation;shared=r.OwnedInvocationRegistryH1(i.session.session_uuid)
        first,k=f.supervisor(registry=shared);second,other=f.supervisor(registry=shared)
        entered=threading.Event();resume=threading.Event();out=[];errors=[]
        def pause():
            if not entered.is_set():
                entered.set()
                if not resume.wait(timeout=3):raise RuntimeError('audit synchronization timeout')
        k.on_poll=pause
        def run():
            try:out.append(first.run_fake())
            except BaseException as error:errors.append(type(error).__name__)
        worker=threading.Thread(target=run);worker.start()
        try:
            self.assertTrue(entered.wait(timeout=3));value=second.run_fake()
            self.assertEqual(value.reason,'sequence_invalid');self.assertEqual(other.calls,[])
            self.assertTrue(shared.active_for(i,first));self.assertFalse(shared._circuit)
        finally:resume.set();worker.join(timeout=3)
        self.assertFalse(worker.is_alive());self.assertEqual(errors,[])
        self.assertEqual(out[0].result,'helper_fake_capture_preserved');self.clean(k)
        evidence('I-shared-registry',first=out[0].result,second=value.result,second_calls=len(other.calls))

    def test_cancel_before_child_commit_blocks_execution(self):
        s,k=self.f.supervisor();original=k.reserve_child
        def reserve(*args):
            token=original(*args);s.kill();return token
        k.reserve_child=reserve;value=s.run_fake()
        self.assertEqual(value.reason,'killed');self.clean(k)
        self.assertFalse(any(call[0]=='exec_fd_child' for call in k.calls))

    def test_terminal_identity_immutable_on_normal_retry_and_kill(self):
        value,s,k=self.f.run();self.assertIs(s.admit(value),value)
        with self.assertRaises(c.ContractViolation2):s.admit(replace(value))
        s.kill();self.assertIs(self.terminal(s,k),value)
        with self.assertRaises(c.ContractViolation2):s.admit(value)

    def test_all_binding_bytes_and_late_sequence_fail(self):
        i=self.f.invocation;codec=p.HelperCodecH1(i)
        raw=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(i.fd_catalog_digest)))
        for offset in range(272):
            changed=bytearray(raw);changed[12+offset]^=1
            with self.subTest(offset=offset),self.assertRaises(c.ContractViolation2):codec.decode(bytes(changed))
        _,s,_=self.f.run();frames=s._channel.frames
        for late in (frames[-1],frames[-2],frames[0]):
            v=r.HelperTranscriptH1(i)
            for frame in frames:v.accept(frame)
            v.finish()
            with self.assertRaises(c.ContractViolation2):v.accept(late)
            with self.assertRaises(c.ContractViolation2):v.finish()

    def test_truncated_frames_all_prefixes_and_no_repair(self):
        i=self.f.invocation;codec=p.HelperCodecH1(i)
        raw=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(i.fd_catalog_digest)))
        for length in range(1,len(raw)):
            d=p.HelperStreamDecoderH1(codec);d.feed(raw[:length])
            with self.subTest(length=length),self.assertRaises(c.ContractViolation2):d.finish()
            with self.assertRaises(c.ContractViolation2):d.feed(raw[length:])

    def test_stream_output_and_registry_caps(self):
        i=self.f.invocation;codec=p.HelperCodecH1(i)
        raw=codec.encode(p.HelperMessageH1('invoke',0,bytes.fromhex(i.fd_catalog_digest)))
        decoder=p.HelperStreamDecoderH1(codec)
        for _ in range(p.MAX_MESSAGES):decoder.feed(raw)
        with self.assertRaises(c.ContractViolation2):decoder.feed(raw)
        self.assertTrue(decoder._failed)
        results={}
        for stream,count in (('stdout',65),('stderr',2)):
            k=self.f.kernel();k.step_us=0
            k.polls=tuple(r.ChildPollH1(((stream,b'x'*p.CHUNK),)) for _ in range(count))
            value,_,k=self.f.run(k);self.clean(k)
            self.assertEqual(value.reason,stream+'_limit');results[stream]=value.reason
        registry=r.OwnedInvocationRegistryH1(i.session.session_uuid);registry.reserve(i)
        for _ in range(cap.MAX_AGGREGATE//p.CHUNK):registry.debit_data(p.CHUNK)
        with self.assertRaises(c.ContractViolation2):registry.debit_data(1)
        evidence('I-resource-caps',stream_limit=p.MAX_MESSAGES,outputs=results,aggregate=registry._captured_bytes)

    def test_current_observed_mode_hash_mismatch_does_not_adopt(self):
        k=self.f.kernel();k.executable_observation=replace(k.executable_observation,mode=0o100644)
        value,_,k=self.f.run(k);self.assertEqual(value.result,'unknown');self.clean(k)

    def test_clock_rollback_frozen_and_incomplete_eof(self):
        results={}
        for kind in ('rollback','frozen','missing_eof'):
            k=self.f.kernel()
            if kind=='rollback':k.clock_sequence=(cap.CaptureTime2(k.now.wall_utc_us-1,k.now.monotonic_us-1),)
            elif kind=='frozen':k.step_us=0;k.polls=()
            else:k.polls=(r.ChildPollH1(stdout_eof=True,exit_code=0),)
            value,s,k=self.f.run(k)
            self.assertEqual(value.result,'unknown');self.clean(k)
            self.assertLessEqual(sum(call[0]=='poll_child' for call in k.calls),4080)
            results[kind]=value.reason
        evidence('I-clocks',results=results)

    def test_process_tree_and_authority_stay_unproven(self):
        value,s,k=self.f.run()
        self.assertEqual(value.native_process_tree,'unproven')
        for name in ('physical_probe_permitted','ownership_proven','isolation_verified',
                     'management_policy_verified','measurement_verified','continuous_attestation'):
            self.assertIs(getattr(value,name),False)
        with self.assertRaises(TypeError):replace(value,native_process_tree='verified')
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        with self.assertRaises(Denied):PhysicalProbeGate.permit(value)

    def test_native_guards_static_only(self):
        root=Path(r.__file__).parent
        tree=ast.parse((root/'native_v2_helper_native.py').read_text())
        guard=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='native_guard_h1')
        self.assertIsInstance(guard.body[0],ast.Raise)
        for cls in (n for n in tree.body if isinstance(n,ast.ClassDef)):
            for method in (n for n in cls.body if isinstance(n,ast.FunctionDef)):
                self.assertEqual(method.body[0].value.func.id,'native_guard_h1')
        tree=ast.parse((root/'native_v2_os_reader.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DormantOSReadOnlyBackend2')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='capture_os')
        self.assertTrue(any(isinstance(n,ast.Raise) for n in method.body))


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    suffix='safe' if SAFE else 'observations'
    summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'skips':len(result.skipped),'assert_safe':SAFE,'observations':EVIDENCE}
    (HERE/(suffix+'.json')).write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
