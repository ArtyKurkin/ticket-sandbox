from dataclasses import asdict, replace
import json
import multiprocessing
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch

from trusted_checker_poc.broker import Broker
from trusted_checker_poc.contracts import AdapterError, InvalidRequest, Request
from trusted_checker_poc.registry import Policy, Registry, POLICY_ID
from trusted_checker_poc.state import State
from trusted_checker_poc.docker_adapter import launch_spec
from trusted_checker_poc.runner import probe
from .fakes import IMAGE, FakeAdapter, fixture_target
from . import support


def process_execute(path, request, barrier, counter, wall):
    with support.RuntimeScope() as scope:
        scope.clock.wall = wall  # Both children observe the same test time.
        state = State(path)
        adapter = FakeAdapter(counter=counter)
        broker = Broker(state,Registry(runner_image_id=IMAGE,timeout=1),adapter,scope='poc-unit')
        barrier.wait(timeout=support.WATCHDOG)
        broker.execute(request,owner='synthetic-owner')


class FoundationTests(support.WorkerTestCase):
    def setUp(self):
        super().setUp()
        self.path = Path(self.temp.name)/'receipts.sqlite3'
        self.state = State(self.path)
        self.target = fixture_target()
        self.state.enroll(self.target)
        self.adapter = FakeAdapter(self.target)
        self.registry = Registry(runner_image_id=IMAGE,timeout=1)
        self.broker = Broker(self.state,self.registry,self.adapter,scope='poc-unit')

    def issue(self, policy=POLICY_ID):
        return self.broker.issue(self.target.container_id,self.target.owner,policy)

    def execute(self, request=None, wait=True):
        result = self.broker.execute(request or self.issue(),owner=self.target.owner)
        if wait:
            self.workers.join()
        return result

    def test_independent_peer_detects_localhost_then_accepts_network_binding(self):
        self.adapter.bind = '127.0.0.1'
        self.assertEqual(self.execute()['reason'],'service_unreachable')
        self.adapter.bind = '0.0.0.0'
        result = self.execute()
        self.assertEqual(result['result'],'passed')
        self.assertEqual(result['integrity']['checker_runtime'],'verified_configuration')
        self.assertEqual(result['integrity']['target_fixture'],'unknown')
        self.assertFalse(result['integrity']['cryptographic_attestation'])
        self.assertEqual(len(result['evidence_digest']),64)

    def test_target_check_sh_curl_and_path_cannot_select_checker(self):
        for field in ('check_sh','curl','path'):
            with self.subTest(field=field):
                setattr(self.adapter,field,'forged exit 0 / hostile PATH')
                self.assertEqual(self.execute()['result'],'passed')
        self.assertEqual(self.adapter.target_exec_calls,0)

    def test_static_fake_body_cannot_echo_fresh_challenge(self):
        self.adapter.static_body = b'{"service":"synthetic-ipv4-v1","challenge":"old"}'
        self.assertEqual(self.execute()['reason'],'unexpected_http_response')

    def test_dynamic_fake_service_can_pass_behavior_but_not_fixture_integrity(self):
        result = self.execute()
        self.assertEqual(result['result'],'passed')
        self.assertEqual(result['integrity']['target_fixture'],'unknown')
        self.assertEqual(result['integrity']['criteria_validity'],'synthetic_ipv4_behavior_only')

    def test_redirect_is_not_followed(self):
        self.adapter.status = 302
        self.assertEqual(self.execute()['reason'],'redirect_rejected')

    def test_oversized_or_malformed_response(self):
        for body in (b'x'*5000,b'not json',b'\xff',b'{}'):
            with self.subTest(size=len(body)):
                self.adapter.static_body = body
                self.assertEqual(self.execute()['result'],'failed')

    def test_request_rejects_all_docker_escape_parameters(self):
        data = asdict(self.issue())
        for name,value in [('command',['sh','-c','anything']),('image','arbitrary'),('mounts',['/']),
                           ('volumes_from','target'),('socket','/var/run/docker.sock'),('network_mode','host'),
                           ('capabilities',['SYS_ADMIN']),('target_name','friendly-name'),('integrity','verified'),('url','http://arbitrary/'),('port',6379),('endpoint','/admin')]:
            with self.subTest(field=name), self.assertRaises(InvalidRequest):
                self.broker.execute({**data,name:value},owner=self.target.owner)
        self.assertEqual(self.adapter.prepares,0)

    def test_invalid_types_short_id_unissued_id_and_schema(self):
        data = asdict(self.issue())
        for extra in ({'schema_version':True},{'schema_version':2},{'target_id':'short'}, {'run_id':'not-a-uuid'}, {'generation':3}):
            with self.subTest(extra=extra),self.assertRaises(InvalidRequest):
                self.broker.execute({**data,**extra},owner=self.target.owner)
        from uuid import uuid4
        with self.assertRaises(InvalidRequest):
            self.broker.execute({**data,'run_id':str(uuid4())},owner=self.target.owner)

    def test_foreign_owner_and_changed_request_rejected(self):
        request = self.issue()
        with self.assertRaises(InvalidRequest):
            self.broker.execute(request,owner='foreign-owner')
        with self.assertRaises(InvalidRequest):
            self.broker.execute(replace(request,generation='reset'),owner=self.target.owner)
        with self.assertRaises(InvalidRequest):
            self.broker.issue(self.target.container_id,'foreign-owner',POLICY_ID)
        self.assertEqual(self.adapter.prepares,0)

    def test_unknown_policy_no_legacy_fallback(self):
        self.assertEqual(self.execute(self.issue('unregistered'))['reason'],'policy_unsupported')
        self.assertEqual(self.adapter.prepares,0)

    def test_unprovisioned_artifact_cannot_start(self):
        self.broker.registry = Registry()
        self.assertEqual(self.execute()['reason'],'artifact_not_provisioned')
        self.assertEqual(self.adapter.prepares,0)

    def test_mutable_artifact_and_policy_resource_overrides_rejected(self):
        for image in ('runner:latest','sha256:short'):
            with self.assertRaises(ValueError):
                Registry(runner_image_id=image)
        with self.assertRaises(ValueError):
            Policy(pids=10000)

    def test_artifact_identity_substitution_rejected_before_run(self):
        self.adapter.artifact = 'sha256:'+'f'*64
        result = self.execute()
        self.assertEqual(result['reason'],'runner_identity_mismatch')
        self.assertEqual(result['integrity']['checker_runtime'],'unknown')
        self.assertEqual(self.adapter.physical_runs,0)

    def test_target_disappears_before_and_during(self):
        self.adapter.before_disappears = True
        self.assertEqual(self.execute()['reason'],'target_unavailable')
        # A completed preflight rejection never invokes prepare; no runner exists.
        self.assertEqual(self.adapter.physical_runs,0)

    def test_daemon_failure_before_prepare_has_no_physical_run(self):
        self.adapter.inspect_error = AdapterError('docker_unavailable')
        result = self.execute()
        self.assertEqual(result['result'],'unknown')
        self.assertEqual(result['reason'],'docker_unavailable')
        self.assertEqual(self.adapter.prepares,0)

    def test_target_disappears_during(self):
        self.adapter.after_disappears = True
        self.assertEqual(self.execute()['reason'],'target_unavailable')

    def test_target_replacement_restart_reset_image_network_ip_detected(self):
        changes = [dict(container_id='f'*64),dict(generation='new'),dict(started_at='new'),dict(restart_count=1),
                   dict(image_id='sha256:'+'f'*64),dict(network_id='f'*64),dict(ipv4='172.29.0.3')]
        for changed in changes:
            with self.subTest(changed=changed):
                self.adapter.physical_runs = 0
                self.adapter.post_target = replace(self.target,**changed)
                result = self.execute()
                self.assertEqual(result['result'],'unknown')
                self.assertEqual(result['reason'],'target_changed_during_execution')
                self.assertEqual(result['observed_target'],asdict(self.adapter.post_target))
                self.assertEqual(result['integrity']['target_identity'],'unknown')

    def test_duplicate_completed_result_survives_broker_restart(self):
        request = self.issue()
        first = self.execute(request)
        restarted = Broker(State(self.path),self.registry,self.adapter,scope='poc-unit')
        self.assertEqual(restarted.execute(request,owner=self.target.owner),first)
        self.assertEqual(self.adapter.physical_runs,1)

    def test_same_run_concurrent_no_second_runner(self):
        self.adapter.block = self.workers.gate()
        request = self.issue()
        future = self.workers.submit(self.execute,request,wait=False)
        try:
            self.wait_for(self.adapter.started)
            second = self.execute(request,wait=False)
            self.assertEqual(second['reason'],'execution_in_progress')
        finally:
            self.adapter.block.set()
        self.assertEqual(future.result(support.WATCHDOG)['result'],'passed')
        self.workers.join()
        self.assertEqual(self.adapter.prepares,1)

    def test_other_run_does_not_steal_active_target(self):
        self.adapter.block = self.workers.gate()
        future = self.workers.submit(self.execute,wait=False)
        try:
            self.wait_for(self.adapter.started)
            self.assertEqual(self.execute(wait=False)['reason'],'target_busy')
        finally:
            self.adapter.block.set()
        future.result(support.WATCHDOG)
        self.workers.join()
        self.assertEqual(self.adapter.physical_runs,1)

    def test_timeout_late_pass_never_replaces_receipt(self):
        # Guarantee an actual fake pass before forcing deadline expiry. A 30ms
        # setup window cannot guarantee even one execution on a slower VDS.
        self.broker.registry = Registry(runner_image_id=IMAGE,timeout=5)
        ready, release = threading.Event(), self.workers.gate()
        original_run = self.adapter.run
        def delayed_delivery(*args):
            outcome = original_run(*args)
            self.assertEqual(outcome.result,'passed')
            ready.set()
            release.wait()
            return outcome
        request = self.issue()
        with patch.object(self.adapter,'run',side_effect=delayed_delivery):
            try:
                execution = self.workers.submit(self.execute,request,wait=False)
                self.wait_for(ready)
                self.clock.advance()
                result = execution.result(support.WATCHDOG)
                self.assertEqual(result['reason'],'runner_deadline_exceeded')
                self.assertEqual(result['failure_class'],'timeout')
                self.assertEqual(result['result'],'unknown')
            finally:
                release.set()
            self.workers.join()
            late,_ = self.clock.inboxes[-1].items.get(timeout=support.WATCHDOG)
            self.assertEqual(late['reason'],'runner_deadline_exceeded')
        self.assertEqual(self.execute(request),result)
        self.assertEqual(self.adapter.physical_runs,1)
        self.assertFalse(self.state.finish(request.run_id,{**result,'result':'passed','reason':'probe_passed'}))

    def test_crash_and_daemon_failure_unknown(self):
        for error in (AdapterError('runner_crash','runner'),AdapterError('docker_unavailable'),RuntimeError('private exception')):
            self.adapter.error = error
            result = self.execute()
            self.assertEqual(result['result'],'unknown')
            self.assertNotIn('private exception',json.dumps(result))

    def test_cleanup_failure_preserves_pass_and_holds_target(self):
        request = self.issue()
        self.adapter.cleanup_ok = False
        result = self.execute(request)
        self.assertEqual(result['result'],'passed')
        self.assertEqual(self.execute()['reason'],'target_busy')
        self.adapter.cleanup_ok = True
        self.assertTrue(self.broker.cleanup(request.run_id))
        self.assertEqual(self.execute(request),result)
        self.assertEqual(self.execute()['result'],'passed')

    def test_expired_running_receipt_after_process_loss_is_not_reexecuted(self):
        request = self.issue()
        self.state.admit(request,self.target.owner,2,self.clock.time()-1)
        restarted = Broker(State(self.path),self.registry,self.adapter,scope='poc-unit')
        result = restarted.execute(request,owner=self.target.owner)
        self.assertEqual(result['reason'],'execution_outcome_unknown')
        self.assertEqual(self.adapter.physical_runs,0)
        self.assertEqual(restarted.execute(request,owner=self.target.owner),result)
        self.assertEqual(self.execute()['reason'],'target_busy')

    def test_cross_process_sqlite_admission(self):
        ctx = multiprocessing.get_context('spawn')
        counter,barrier = ctx.Value('i',0),ctx.Barrier(2)
        request = asdict(self.issue())
        children = [ctx.Process(target=process_execute,args=(str(self.path),request,barrier,counter,self.clock.wall)) for _ in range(2)]
        try:
            for child in children: child.start()
            for child in children:
                child.join(support.WATCHDOG)
                self.assertFalse(child.is_alive(),'child process did not finish')
                self.assertEqual(child.exitcode,0)
        finally:
            for child in children:
                if child.is_alive(): child.terminate()
                if child.pid is not None: child.join(support.WATCHDOG)
        self.assertEqual(counter.value,1)

    def test_launch_spec_has_no_privileges_socket_or_host_namespaces(self):
        plan = self.adapter.plan(self.registry.get(POLICY_ID),self.target,self.issue().run_id,'a'*64)
        spec = launch_spec(plan)
        self.assertEqual(spec['image'],IMAGE)
        self.assertTrue(spec['read_only'])
        self.assertEqual(spec['user'],'10001:10001')
        self.assertEqual(spec['cap_drop'],['ALL'])
        self.assertFalse(spec['privileged'])
        for key in ('volumes','volumes_from','mounts','pid_mode','network_mode'):
            self.assertNotIn(key,spec)
        self.assertEqual(set(spec['environment']),{'POC_TARGET_IPV4','POC_CHALLENGE'})
        self.assertEqual(spec['network'],self.target.network_id)

    def test_policy_artifact_change_after_issue_is_not_silent(self):
        request = self.issue()
        self.broker.registry = Registry(runner_image_id='sha256:'+'f'*64,timeout=1)
        result = self.execute(request)
        self.assertEqual(result['reason'],'policy_changed_since_issue')
        self.assertEqual(result['policy_identity']['runner_image_id'],IMAGE)
        self.assertEqual(self.adapter.prepares,0)

    def test_global_capacity_counts_durable_target_leases(self):
        requests = []
        for identifier in ('1','2','3'):
            target = replace(self.target,container_id=identifier*64)
            self.state.enroll(target)
            requests.append(self.broker.issue(target.container_id,target.owner,POLICY_ID))
        self.assertEqual(self.state.admit(requests[0],self.target.owner,2,time.time()+1),'admitted')
        self.assertEqual(self.state.admit(requests[1],self.target.owner,2,time.time()+1),'admitted')
        result = self.execute(requests[2])
        self.assertEqual(result['reason'],'capacity_exhausted')
        self.assertEqual(self.adapter.prepares,0)

    def test_probe_rejects_unsanctioned_endpoints_without_transport(self):
        def forbidden(*args,**kwargs):
            self.fail('transport must not be created')
        for address in ('127.0.0.1','8.8.8.8','169.254.169.254','example.com','http://172.29.0.2/','::1'):
            with self.subTest(address=address),self.assertRaises(ValueError):
                probe(address,'a'*64,connection_factory=forbidden)


if __name__ == '__main__':
    unittest.main()
