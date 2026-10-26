"""OS backend review tests: fake drivers only, including FD resolver operations."""
import ast
from dataclasses import FrozenInstanceError,replace
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_capture_contracts as capture
from trusted_checker_network import native_v2_os_contracts as o
from trusted_checker_network import native_v2_os_reader as r
from trusted_checker_network import native_v2_os_linux as linux
from trusted_checker_network import native_v2_os_fake as fake
from .native_v2_os_reader_support import OSFixture2,FakeDescriptorKernel2
from .native_v2_collector_support import stamp,WALL,MONO
from .native_v2_support import uid,hd


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=OSFixture2.create();cls.good,cls.issuer,_=cls.f.run()
        assert cls.good.reason=='fake_driver_capture_preserved_os_unproven'

    def fault(self,driver,reason):
        result,backend,driver=self.f.run(driver)
        self.assertEqual((result.result,result.reason),('unknown',reason));self.assertEqual(result.artifacts,())
        self.assertIs(backend.exercise_fake_driver(),result)
        return result,backend,driver

    def polls(self,values):
        driver=self.f.driver();driver.scripts=((self.f.policy.template.requests[0].capture_uuid,tuple(values)),)
        return driver

    def observed_executable(self):return self.f.driver().open_executable('/usr/sbin/nft')

    def test_default_off_no_calls(self):
        backend,driver=self.f.backend(enabled=False)
        self.assertEqual(driver.calls,[])
        self.assertEqual(backend.exercise_fake_driver().reason,'disabled');self.assertEqual(driver.calls,[])

    def test_real_entry_disabled_before_io(self):
        backend,driver=self.f.backend(enabled=False)
        with self.assertRaisesRegex(c.ContractViolation2,'disabled'):backend.capture_os()
        self.assertEqual(driver.calls,[])

    def test_real_entry_cannot_use_offline_approval(self):
        backend,driver=self.f.backend()
        with self.assertRaisesRegex(c.ContractViolation2,'native_activation_unreviewed'):backend.capture_os()
        self.assertEqual(driver.calls,[])

    def test_import_constructor_no_os_io(self):
        driver=linux.LinuxReadOnlyDriver2()
        backend,_=self.f.backend(driver)
        self.assertEqual(driver._children,{})
        with self.assertRaisesRegex(c.ContractViolation2,'native_activation_unreviewed'):backend.capture_os()

    def test_native_driver_not_exercised_as_fake(self):
        backend,_=self.f.backend(linux.LinuxReadOnlyDriver2())
        with self.assertRaisesRegex(c.ContractViolation2,'fake_driver_required'):backend.exercise_fake_driver()

    def test_fake_subclass_not_execution_surface(self):
        class Subclass(fake.FakeOSReadDriver2):pass
        driver=Subclass(self.f.policy,stamp(),self.f.scripts)
        backend,_=self.f.backend(driver)
        with self.assertRaisesRegex(c.ContractViolation2,'fake_driver_required'):backend.exercise_fake_driver()

    def test_correct_fixed_argv_closed_env_and_fd(self):
        result,_,driver=self.f.run();spawn=next(x for x in driver.calls if x[0]=='spawn')
        self.assertEqual(spawn[1],('/usr/sbin/nft','-j','-a','list','ruleset'))
        self.assertEqual(spawn[3],10);self.assertEqual(spawn[4],(('LANG','C'),('LC_ALL','C')))
        self.assertEqual(result.artifacts[0].stdout,b'[]')
        self.assertEqual(result.artifacts[0].completion,'fake_os_driver_eofs_exit_reap_and_handshake')

    def test_complete_full_registry_in_three_namespaces(self):
        fixture=OSFixture2.create(full=True);result,_,driver=fixture.run()
        self.assertEqual(len(result.artifacts),30)
        self.assertEqual(sum(x[0]=='spawn' for x in driver.calls),30)
        self.assertEqual(sum(x[0]=='reap' for x in driver.calls),30)

    def test_raw_bytes_exact_and_no_parser_in_transport(self):
        raw=b'\x00unsupported JSON\n'
        driver=self.polls((r.ProcessPoll2((('stdout',raw),('stderr',b'exact error\n'))),
                           r.ProcessPoll2(stdout_eof=True,stderr_eof=True,exit_status=0,helper_completed=True,control_eof=True)))
        result,_,_=self.f.run(driver)
        self.assertEqual(result.artifacts[0].stdout,raw);self.assertEqual(result.artifacts[0].stderr,b'exact error\n')
        self.assertNotIn('unsupported JSON',repr(result))

    def test_success_requires_reap_and_close(self):
        result,_,driver=self.f.run()
        names=[x[0] for x in driver.calls]
        self.assertLess(names.index('reap'),names.index('close'))
        self.assertLess(names.index('close'),names.index('close_executable'))
        self.assertEqual(result.cleanup,'reaped_and_closed');self.assertFalse(driver._running)

    def test_namespace_before_and_after(self):
        result,_,_=self.f.run();artifact=result.artifacts[0]
        self.assertEqual(artifact.reader_before,artifact.reader_after)
        self.assertEqual(artifact.child.namespace_pin_digest,self.f.policy.namespace_fds[0].digest)

    def test_authority_flags_always_false(self):
        for value in (self.good,*self.good.artifacts):
            for key in ('physical_probe_permitted','ownership_proven','continuous_attestation'):
                self.assertIs(getattr(value,key),False)
        for key in ('isolation_verified','management_policy_verified','measurement_verified'):
            self.assertIs(getattr(self.good,key),False)
        self.assertEqual(self.good.os_provenance,'unproven');self.assertEqual(self.good.unresolved,o.UNRESOLVED)

    def test_completed_artifact_cannot_describe_partial_output(self):
        for change in ({'exit_status':1},{'exit_status':True},{'stdout_eof':False},{'stderr_eof':False},
                       {'truncated':True},{'interrupted':True},{'timed_out':True}):
            with self.subTest(change=change),self.assertRaisesRegex(c.ContractViolation2,'incomplete_output'):
                replace(self.good.artifacts[0],**change)

    def test_wall_time_limits_rechecked_in_artifact_constructor(self):
        artifact=self.good.artifacts[0]
        with self.assertRaisesRegex(c.ContractViolation2,'timing_unproven'):
            replace(artifact,finished=replace(artifact.finished,wall_utc_us=artifact.started.wall_utc_us+500001))

    def test_exact_plan_and_binary_pins(self):
        for pin,binary in ((hd('wrong'),self.f.policy.template.binaries.digest),(self.f.policy.digest,hd('wrong'))):
            driver=self.f.driver()
            with self.assertRaisesRegex(c.ContractViolation2,'pin_mismatch'):
                r.DormantOSReadOnlyBackend2(self.f.policy,pin,binary,driver,uid(9),stamp())
            self.assertEqual(driver.calls,[])

    def test_unknown_executable(self):
        with self.assertRaises(c.ContractViolation2):replace(self.observed_executable(),path='/tmp/nft')

    def test_path_substitution(self):
        driver=self.f.driver();driver.executable_overrides=(replace(self.observed_executable(),path='/usr/sbin/ip'),)
        self.fault(driver,'executable_mismatch');self.assertFalse(any(x[0]=='spawn' for x in driver.calls))

    def test_symlink_substitution(self):
        driver=self.f.driver();driver.executable_overrides=(replace(self.observed_executable(),no_symlink_components=False),)
        self.fault(driver,'executable_unprotected')

    def test_wrong_binary_hash(self):
        driver=self.f.driver();driver.executable_overrides=(replace(self.observed_executable(),sha256=hd('wrong')),)
        self.fault(driver,'executable_mismatch')

    def test_wrong_binary_source_manifest(self):
        driver=self.f.driver();driver.executable_overrides=(replace(self.observed_executable(),source_manifest_digest=hd('wrong')),)
        self.fault(driver,'executable_mismatch')

    def test_mutable_setid_hardlinked_or_capability_binary(self):
        for change in ({'protected_ancestors':False},{'uid':1001},{'links':2},{'mode':0o104755},
                       {'mode':0o100777},{'mode':0o040755},{'no_file_capabilities':False}):
            with self.subTest(change=change):
                driver=self.f.driver();driver.executable_overrides=(replace(self.observed_executable(),**change),)
                self.fault(driver,'executable_unprotected')

    def test_binary_in_place_change_after_read(self):
        driver=self.f.driver();driver.after_executable=replace(self.observed_executable(),ctime_ns=9999)
        self.fault(driver,'executable_changed')

    def test_after_executable_requires_exact_type(self):
        class AlwaysEqual:
            def __eq__(self,other):return True
        driver=self.f.driver();driver.after_executable=AlwaysEqual()
        self.fault(driver,'evidence_invalid')

    def test_executable_fd_cannot_alias_namespace_fd(self):
        driver=self.f.driver();driver.executable_overrides=(replace(self.observed_executable(),fd=10),)
        self.fault(driver,'inherited_fd')

    def test_wrong_uid(self):
        driver=self.f.driver();driver.default_observation=replace(driver.default_observation,
            principal=replace(driver.default_observation.principal,uid=999))
        self.fault(driver,'principal_mismatch')

    def test_wrong_gid_or_capabilities(self):
        for fields in ({'gid':999},{'effective_caps':()},{'supplementary_groups':(10,)}):
            with self.subTest(fields=fields):
                driver=self.f.driver();driver.default_observation=replace(driver.default_observation,
                    principal=replace(driver.default_observation.principal,**fields))
                self.fault(driver,'principal_mismatch')

    def test_child_helper_wrong_command_uid(self):
        driver=self.f.driver();driver.helper_transform=lambda h:replace(h,command_principal=replace(h.command_principal,uid=0))
        self.fault(driver,'principal_mismatch')

    def test_child_helper_wrong_command_capabilities(self):
        driver=self.f.driver();driver.helper_transform=lambda h:replace(h,command_principal=replace(h.command_principal,effective_caps=()))
        self.fault(driver,'principal_mismatch')

    def test_child_helper_unexpected_fd(self):
        driver=self.f.driver();driver.helper_transform=lambda h:replace(h,inherited_fds_after_exec=(0,1,2,33))
        self.fault(driver,'inherited_fd')

    def test_child_helper_untrusted_stdin(self):
        driver=self.f.driver();driver.helper_transform=lambda h:replace(h,stdin_kind='untrusted_inherited')
        self.fault(driver,'inherited_fd')

    def test_child_helper_environment_substitution(self):
        driver=self.f.driver();driver.helper_transform=lambda h:replace(h,environment=(('LD_PRELOAD','evil'),))
        self.fault(driver,'driver_protocol_invalid')

    def test_child_helper_namespace_substitution(self):
        driver=self.f.driver();driver.helper_transform=lambda h:replace(h,namespace=self.f.policy.namespace_fds[1])
        self.fault(driver,'source_substitution')

    def test_child_helper_session_replay(self):
        driver=self.f.driver();driver.helper_transform=lambda h:replace(h,session_uuid=uid(9999))
        self.fault(driver,'source_substitution')

    def test_ambient_caps_forbidden(self):
        with self.assertRaisesRegex(c.ContractViolation2,'privileges_invalid'):
            replace(self.f.policy.helper_principal,ambient_caps=('CAP_SYS_ADMIN',))

    def test_unexpected_inherited_fd(self):
        driver=self.f.driver();driver.default_observation=replace(driver.default_observation,inherited_fds=(0,1,2,10,11,12,33))
        self.fault(driver,'inherited_fd')

    def test_wrong_namespace_inode(self):
        driver=self.f.driver();driver.default_observation=replace(driver.default_observation,namespace_inodes=(999,101,102))
        self.fault(driver,'namespace_mismatch')

    def test_lost_namespace_fd(self):
        driver=self.f.driver();driver.default_observation=replace(driver.default_observation,fd_open=(False,True,True))
        self.fault(driver,'namespace_fd_lost')

    def test_pid_reuse(self):
        driver=self.f.driver();good=driver.default_observation
        driver.observations=(good,replace(good,reader_start_ticks=12345))
        self.fault(driver,'pid_reuse')

    def test_namespace_fd_generation_change(self):
        driver=self.f.driver();pins=driver.default_observation.namespace_fds
        driver.observations=(driver.default_observation,replace(driver.default_observation,
            namespace_fds=(replace(pins[0],fd_generation=2),*pins[1:])))
        self.fault(driver,'namespace_mismatch')

    def test_epoch_session_boot_changes(self):
        for field in ('writer_epoch_uuid','reader_session_uuid','host_boot_uuid'):
            with self.subTest(field=field):
                driver=self.f.driver();driver.default_observation=replace(driver.default_observation,**{field:uid(777)})
                self.fault(driver,'identity_changed')

    def test_identity_drift_at_final_bracket(self):
        driver=self.f.driver();good=driver.default_observation
        driver.observations=(good,)*4+(replace(good,reader_start_ticks=111),)
        self.fault(driver,'pid_reuse')

    def test_process_status_without_handshake(self):
        driver=self.polls((r.ProcessPoll2(stdout_eof=True,stderr_eof=True,exit_status=0,control_eof=True),))
        self.fault(driver,'handshake_missing')

    def test_stdout_complete_field_not_helper_control(self):
        driver=self.polls((r.ProcessPoll2((('stdout',b'{"complete":true}'),),True,True,0,False,True),))
        self.fault(driver,'handshake_missing')

    def test_incomplete_stdout_eof(self):
        driver=self.polls((r.ProcessPoll2(stderr_eof=True,exit_status=0,helper_completed=True,control_eof=True),))
        self.fault(driver,'timeout')

    def test_nonzero_exit(self):
        driver=self.polls((r.ProcessPoll2(exit_status=7),))
        result,_,driver=self.fault(driver,'nonzero_exit')
        self.assertTrue(any(x[0]=='reap' for x in driver.calls));self.assertEqual(result.cleanup,'reaped_and_closed')

    def test_exit_can_precede_pipe_eof(self):
        driver=self.polls((r.ProcessPoll2(exit_status=0),r.ProcessPoll2((('stdout',b'[]'),),True,True,0,True,True)))
        result,_,_=self.f.run(driver);self.assertEqual(result.reason,'fake_driver_capture_preserved_os_unproven')

    def test_oversized_stdout(self):
        polls=tuple(r.ProcessPoll2((('stdout',b'x'*capture.CHUNK_BYTES),)) for _ in range(17))
        _,_,driver=self.fault(self.polls(polls),'stdout_limit')
        self.assertTrue(any(x[0]=='terminate' for x in driver.calls));self.assertTrue(any(x[0]=='reap' for x in driver.calls))

    def test_oversized_stderr(self):
        self.fault(self.polls((r.ProcessPoll2((('stderr',b'x'*4097),)),)),'stderr_limit')

    def test_driver_cannot_return_larger_chunk(self):
        self.fault(self.polls((r.ProcessPoll2((('stdout',b'x'*(capture.CHUNK_BYTES+1)),)),)),'driver_protocol_invalid')

    def test_output_after_eof(self):
        self.fault(self.polls((r.ProcessPoll2(stdout_eof=True),r.ProcessPoll2((('stdout',b'late'),)))),
                   'driver_protocol_invalid')

    def test_timeout_terminates_kills_and_reaps(self):
        driver=self.polls(());driver.term_effective=False
        result,_,driver=self.fault(driver,'timeout');names=[x[0] for x in driver.calls]
        self.assertLess(names.index('terminate'),names.index('kill'));self.assertLess(names.index('kill'),names.index('reap'))
        self.assertEqual(result.cleanup,'reaped_and_closed')

    def test_bounded_drain_after_term_failure_to_exit(self):
        driver=self.polls(());driver.term_effective=False;driver.drain_bytes=b'x'*capture.CHUNK_BYTES
        _,_,driver=self.fault(driver,'timeout')
        self.assertEqual(sum(x[0]=='drain' for x in driver.calls),4)

    def test_drain_overrun_quarantines_but_still_reaps(self):
        driver=self.polls(());driver.term_effective=False;driver.drain_bytes=b'x'*(capture.CHUNK_BYTES+1)
        result,_,driver=self.fault(driver,'cleanup_unproven')
        self.assertEqual(result.cleanup,'quarantine_cleanup_unproven')
        self.assertTrue(any(x[0]=='kill' for x in driver.calls));self.assertTrue(any(x[0]=='reap' for x in driver.calls))

    def test_failed_terminate_still_attempts_kill_and_reap(self):
        driver=self.polls(());driver.fail_terminate=True
        _,_,driver=self.fault(driver,'cleanup_unproven')
        self.assertTrue(any(x[0]=='kill' for x in driver.calls));self.assertTrue(any(x[0]=='reap' for x in driver.calls))

    def test_unreaped_child_cannot_publish_success(self):
        driver=self.f.driver();driver.reap_ok=False
        result,_,_=self.fault(driver,'cleanup_unproven');self.assertEqual(result.cleanup,'quarantine_cleanup_unproven')

    def test_pipe_close_failure_cannot_publish_success(self):
        driver=self.f.driver();driver.close_ok=False;self.fault(driver,'cleanup_unproven')

    def test_executable_close_failure_cannot_publish_success(self):
        driver=self.f.driver();driver.executable_close_ok=False;self.fault(driver,'cleanup_unproven')

    def test_lost_spawn_response_still_reaps_owned_invocation(self):
        driver=self.f.driver();driver.spawn_error_after_registration=True
        _,_,driver=self.fault(driver,'evidence_invalid')
        self.assertTrue(any(x[0]=='terminate' for x in driver.calls));self.assertTrue(any(x[0]=='reap' for x in driver.calls))

    def test_interrupted_process_transport(self):
        self.fault(self.polls((r.ProcessPoll2(interrupted=True),)),'interrupted')

    def test_interrupted_system_read(self):
        driver=self.f.driver();driver.poll_exception=InterruptedError('secret interrupted')
        self.fault(driver,'interrupted')

    def test_reader_death(self):self.fault(self.polls((r.ProcessPoll2(reader_alive=False),)),'reader_died')

    def test_clock_rollback_before_dispatch(self):
        driver=self.f.driver();driver.clock_sequence=(capture.CaptureTime2(WALL-1,MONO),)
        self.fault(driver,'clock_rollback');self.assertFalse(any(x[0]=='spawn' for x in driver.calls))

    def test_independent_clock_enforces_deadline(self):
        driver=self.f.driver();driver.step_us=1000001
        self.fault(driver,'timeout')

    def test_frozen_clock_does_not_create_unbounded_loop(self):
        driver=self.polls(());driver.step_us=0
        self.fault(driver,'incomplete_output')
        self.assertEqual(sum(x[0]=='poll' for x in driver.calls),4096)

    def test_late_publication_after_reap_is_unknown(self):
        driver=self.f.driver()
        original=driver.close_executable
        def late_close(executable):
            driver.now=stamp(2000001)
            return original(executable)
        driver.close_executable=late_close
        self.fault(driver,'timeout')

    def test_kill_before_attempt(self):
        backend,driver=self.f.backend();backend.kill()
        result=backend.exercise_fake_driver();self.assertEqual(result.reason,'killed')
        self.assertEqual(driver.calls,[])

    def test_kill_during_capture_cleans_child(self):
        backend,driver=self.f.backend();driver.on_poll=backend.kill
        result=backend.exercise_fake_driver();self.assertEqual(result.reason,'killed')
        self.assertEqual(result.artifacts,());self.assertTrue(any(x[0]=='reap' for x in driver.calls))

    def test_kill_after_publication_preserves_record_and_denies_admission(self):
        result,backend,_=self.f.run();backend.kill()
        self.assertIs(backend.exercise_fake_driver(),result)
        with self.assertRaisesRegex(c.ContractViolation2,'result_unissued'):backend.admit_fake_result(result)

    def test_concurrent_attempt_is_rejected(self):
        backend,_=self.f.backend();backend._lock.acquire()
        try:
            with self.assertRaisesRegex(c.ContractViolation2,'concurrent_attempt'):backend.exercise_fake_driver()
        finally:backend._lock.release()
        self.assertEqual(backend.exercise_fake_driver().reason,'fake_driver_capture_preserved_os_unproven')

    def test_replay_other_instance(self):
        _,backend,_=self.f.run()
        with self.assertRaisesRegex(c.ContractViolation2,'result_unissued'):backend.admit_fake_result(self.good)

    def test_forged_result_copy(self):
        with self.assertRaisesRegex(c.ContractViolation2,'result_unissued'):self.issuer.admit_fake_result(replace(self.good))

    def test_unknown_circuit_no_retry(self):
        result,backend,driver=self.fault(self.polls((r.ProcessPoll2(interrupted=True),)),'interrupted')
        count=len(driver.calls);self.assertIs(backend.exercise_fake_driver(),result);self.assertEqual(len(driver.calls),count)

    def test_source_replacement_child_binding(self):
        driver=self.f.driver();q=self.f.policy.template.requests[0];executable=self.observed_executable()
        driver.spawn_override=o.ChildHandle2(6000,20000,uid(999),self.f.policy.namespace_fds[0].digest,executable.digest)
        self.fault(driver,'source_substitution')

    def test_environment_and_arbitrary_argv_not_accepted(self):
        for env in ((('LD_PRELOAD','evil'),),(('LANG','C'),('LC_ALL','C'),('PATH','/tmp'))):
            with self.subTest(env=env),self.assertRaises(c.ContractViolation2):replace(self.f.policy,environment=env)
        with self.assertRaises(TypeError):self.f.backend(argv=('/bin/sh','-c','echo bad'))
        with self.assertRaises(c.ContractViolation2):replace(self.f.policy.template.requests[0],source='nft; bad')

    def test_no_fallback_from_old_collector_or_fake(self):
        from trusted_checker_network.native_v2_collector import ReadOnlyCommandRunner2
        with self.assertRaisesRegex(c.ContractViolation2,'os_backend_dormant'):ReadOnlyCommandRunner2(linux.LinuxReadOnlyDriver2())

    def test_old_capture_adapters_reject_new_result(self):
        from .native_v2_collector_support import CollectorFixture2
        _,old,_=CollectorFixture2.create().run()
        with self.assertRaises(c.ContractViolation2):old.admit_for_parsing(self.good)

    def test_immutable_no_authority_overrides(self):
        with self.assertRaises(FrozenInstanceError):self.good.reason='verified'
        with self.assertRaises(TypeError):replace(self.good,isolation_verified=True)
        with self.assertRaises(c.ContractViolation2):replace(self.good,physical_probe_permitted=True)
        with self.assertRaises(c.ContractViolation2):replace(self.f.policy,origin='physical')

    def test_no_approved_timing_or_measurement_extension(self):
        with self.assertRaises(c.ContractViolation2):replace(self.f.policy.timing,capture_us=2000001)
        with self.assertRaises(c.ContractViolation2):replace(self.f.policy.timing,acceptance='approved')
        self.assertEqual(self.f.policy.template.purpose,'inventory_preflight_only')

    def test_additional_os_surfaces_stay_unobserved(self):
        self.assertEqual(self.good.unsupported_surfaces,capture.UNOBSERVED)
        self.assertIn('tc_ingress_egress',self.good.unsupported_surfaces)
        self.assertIn('external_inherited_fds',self.good.unsupported_surfaces)
        self.assertEqual(self.good.os_provenance,'unproven')

    def test_mock_capture_cannot_be_promoted_to_native_attestation(self):
        helper=self.good.artifacts[0].helper
        with self.assertRaises(c.ContractViolation2):replace(helper,basis='native_verified')
        with self.assertRaises(c.ContractViolation2):replace(self.good.artifacts[0],completion='physical_complete')

    def test_kill_before_final_publication_is_terminal(self):
        backend,driver=self.f.backend();close=driver.close_executable
        def cancel(executable):
            backend.kill();return close(executable)
        driver.close_executable=cancel
        result=backend.exercise_fake_driver()
        self.assertEqual(result.reason,'killed');self.assertEqual(result.artifacts,())
        self.assertIs(backend.exercise_fake_driver(),result)

    def test_physical_gate_closed(self):
        from trusted_checker_physical.collector import PhysicalProbeGate
        from trusted_checker_runtime.profiles import Denied
        for value in (self.good,self.good.artifacts[0],self.f.policy):
            with self.subTest(value=type(value).__name__),self.assertRaisesRegex(Denied,'physical_network_boundary_not_accepted'):
                PhysicalProbeGate.permit(value)


class AggregateTests(unittest.TestCase):
    def test_aggregate_cap_over_all_sources_includes_stderr(self):
        fixture=OSFixture2.create(full=True)
        template=replace(fixture.policy.template,requests=tuple(q for q in fixture.policy.template.requests if q.source!='nft'))
        policy=replace(fixture.policy,template=template)
        polls=(r.ProcessPoll2((('stdout',b'x'*capture.CHUNK_BYTES),)),)*64
        complete=r.ProcessPoll2(stdout_eof=True,stderr_eof=True,exit_status=0,helper_completed=True,control_eof=True)
        scripts=tuple((q.capture_uuid,(*polls,complete)) for q in template.requests)
        f=OSFixture2(policy,scripts);result,_,driver=f.run()
        self.assertEqual(result.reason,'aggregate_limit');self.assertEqual(result.artifacts,())
        self.assertEqual(sum(x[0]=='spawn' for x in driver.calls),17)
        self.assertEqual(sum(x[0]=='reap' for x in driver.calls),17)


class ResolverTests(unittest.TestCase):
    def test_held_fd_hash_against_independent_manifest(self):
        kernel=FakeDescriptorKernel2();observed=linux.resolve_executable2(kernel,kernel.expected,1000)
        self.assertEqual(observed.fd,6);self.assertEqual(observed.sha256,kernel.expected.binary_sha256)
        self.assertEqual(kernel.closed,[5,4,3]);self.assertNotIn(6,kernel.closed)
        self.assertEqual([x for x in kernel.calls if x[0]=='openat_nofollow'],
                         [('openat_nofollow',3,'usr',True),('openat_nofollow',4,'sbin',True),('openat_nofollow',5,'nft',False)])

    def test_unknown_absolute_path(self):
        with self.assertRaises(c.ContractViolation2):replace(FakeDescriptorKernel2().expected,path='/bin/sh')

    def test_symlink_component_nofollow_failure_closes_parents(self):
        kernel=FakeDescriptorKernel2();kernel.fail_component='sbin'
        with self.assertRaises(OSError):linux.resolve_executable2(kernel,kernel.expected,1000)
        self.assertEqual(kernel.closed,[4,3])

    def test_symlink_file_type_rejected(self):
        kernel=FakeDescriptorKernel2();kernel.identities[6]=replace(kernel.identities[6],mode=0o120777)
        with self.assertRaisesRegex(c.ContractViolation2,'executable_unprotected'):linux.resolve_executable2(kernel,kernel.expected,1000)
        self.assertEqual(kernel.closed,[6,5,4,3])

    def test_writable_parent_rejected(self):
        kernel=FakeDescriptorKernel2();kernel.identities[4]=replace(kernel.identities[4],mode=0o040777)
        with self.assertRaisesRegex(c.ContractViolation2,'executable_unprotected'):linux.resolve_executable2(kernel,kernel.expected,1000)
        self.assertEqual(kernel.closed,[4,3])

    def test_wrong_binary_digest_closes_final_fd(self):
        kernel=FakeDescriptorKernel2()
        with self.assertRaisesRegex(c.ContractViolation2,'executable_mismatch'):
            linux.resolve_executable2(kernel,replace(kernel.expected,binary_sha256=hd('wrong')),1000)
        self.assertEqual(kernel.closed,[6,5,4,3])

    def test_file_mutation_during_hash(self):
        kernel=FakeDescriptorKernel2();kernel.after_identity=replace(kernel.identities[6],inode=999)
        with self.assertRaisesRegex(c.ContractViolation2,'executable_changed'):linux.resolve_executable2(kernel,kernel.expected,1000)

    def test_executable_size_limit_before_read(self):
        kernel=FakeDescriptorKernel2();kernel.identities[6]=replace(kernel.identities[6],size=67108865)
        with self.assertRaisesRegex(c.ContractViolation2,'executable_unprotected'):linux.resolve_executable2(kernel,kernel.expected,1000)
        self.assertEqual(kernel.read_count,0)

    def test_capability_file_rejected(self):
        kernel=FakeDescriptorKernel2();kernel.file_caps=True
        with self.assertRaisesRegex(c.ContractViolation2,'executable_unprotected'):linux.resolve_executable2(kernel,kernel.expected,1000)

    def test_reader_must_not_assume_file_immutability_from_hash(self):
        kernel=FakeDescriptorKernel2();observed=linux.resolve_executable2(kernel,kernel.expected,1000)
        self.assertEqual(observed.descriptor_execution,'required_not_native_proven')
        self.assertIn('binary_write_exclusion',o.UNRESOLVED)

    def test_literal_path_traversal_and_shell_tokens_rejected(self):
        for path in ('/usr/sbin/../sbin/nft','/usr/sbin/nft; bad','/proc/self/fd/6'):
            with self.subTest(path=path),self.assertRaises(c.ContractViolation2):replace(FakeDescriptorKernel2().expected,path=path)

    def test_hash_deadline(self):
        kernel=FakeDescriptorKernel2()
        with self.assertRaisesRegex(c.ContractViolation2,'timeout'):linux.resolve_executable2(kernel,kernel.expected,1)
        self.assertEqual(kernel.closed,[4,3])

    def test_bounded_hash_read(self):
        kernel=FakeDescriptorKernel2();kernel.return_oversized=True
        with self.assertRaisesRegex(c.ContractViolation2,'driver_protocol_invalid'):linux.resolve_executable2(kernel,kernel.expected,1000)

    def test_close_failure_closes_every_other_owned_descriptor(self):
        kernel=FakeDescriptorKernel2();kernel.close_failure=5
        with self.assertRaisesRegex(c.ContractViolation2,'cleanup_unproven'):linux.resolve_executable2(kernel,kernel.expected,1000)
        self.assertEqual(set(kernel.closed),{3,4,5,6})


class SafetyTests(unittest.TestCase):
    def test_all_native_methods_deny_before_any_io(self):
        driver=linux.LinuxReadOnlyDriver2();kernel=linux.LinuxDescriptorKernel2()
        calls=((driver.clock,()),(driver.observe,()),(driver.open_executable,('/usr/sbin/nft',)),
            (driver.spawn,(None,)*5),(driver.poll,(None,10,100)),(driver.terminate,(None,)),
            (driver.kill,(None,)),(driver.running,(None,)),(driver.reap,(None,100)),
            (driver.close,(None,)),(driver.drain,(None,10,100)),
            (kernel.open_root,()),(kernel.open_component,(3,'usr',True)),(kernel.identity,(3,)),
            (kernel.file_capabilities,(3,)),(kernel.read,(3,1)),(kernel.rewind,(3,)),(kernel.close,(3,)),(kernel.monotonic_us,()))
        with patch.object(linux.os,'open',side_effect=AssertionError('OS read')),patch.object(linux.os,'read',side_effect=AssertionError('OS read')):
            for method,args in calls:
                with self.subTest(method=method.__name__),self.assertRaisesRegex(c.ContractViolation2,'native_activation_unreviewed'):
                    method(*args)

    def test_fresh_import_and_constructors_without_any_os_capture(self):
        code='''
import os,subprocess,socket,time
def forbidden(*args,**kwargs):raise AssertionError('native action attempted')
os.open=forbidden
os.fork=forbidden
os.execve=forbidden
os.setns=forbidden
os.system=forbidden
subprocess.Popen=forbidden
socket.socket=forbidden
from trusted_checker_network.native_v2_os_linux import LinuxReadOnlyDriver2
from trusted_checker_network.tests.native_v2_os_reader_support import OSFixture2
f=OSFixture2.create()
backend,driver=f.backend(LinuxReadOnlyDriver2())
try:backend.capture_os()
except ValueError as error:assert str(error)=='v2_os_reader_native_activation_unreviewed'
else:raise AssertionError('native entry accepted')
value,_,_=f.run()
assert value.physical_probe_permitted is False
'''
        result=subprocess.run([sys.executable,'-W','error::ResourceWarning','-c',code],capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def test_native_syscalls_confined_to_guarded_module(self):
        root=Path(__file__).parents[1]
        for name in ('native_v2_os_contracts','native_v2_os_reader','native_v2_os_fake'):
            tree=ast.parse((root/(name+'.py')).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    self.assertTrue(all(n.name not in ('os','socket','subprocess','ctypes','selectors') for n in node.names))
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                    self.assertNotIn(node.func.id,('open','exec','eval','__import__'))
        tree=ast.parse((root/'native_v2_os_linux.py').read_text())
        for cls in (node for node in tree.body if isinstance(node,ast.ClassDef) and node.name in ('LinuxDescriptorKernel2','LinuxReadOnlyDriver2')):
            for method in cls.body:
                if not isinstance(method,ast.FunctionDef) or method.name in ('__init__','_owned'):continue
                first=method.body[0]
                self.assertIsInstance(first,ast.Expr)
                self.assertIsInstance(first.value,ast.Call)
                self.assertEqual(first.value.func.id,'_native_guard2')

    def test_arbitrary_driver_does_not_gain_native_activation(self):
        class Malicious(r.OSReadDriver2):
            def clock(self):raise AssertionError('must not call')
        f=OSFixture2.create();backend,_=f.backend(Malicious())
        with self.assertRaisesRegex(c.ContractViolation2,'native_activation_unreviewed'):backend.capture_os()

    def test_no_process_or_namespace_creation_api(self):
        self.assertFalse(hasattr(linux,'run_command'))
        tree=ast.parse(Path(linux.__file__).read_text())
        attrs={node.func.attr for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)}
        self.assertTrue({'fork','setns','Popen','system','execve','setuid','setgid'}.isdisjoint(attrs))


if __name__=='__main__':unittest.main()
