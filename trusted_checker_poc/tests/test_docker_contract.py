"""SDK mocks only: verifies operation construction/guards, not Docker isolation."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock
import copy
import json
from pathlib import Path
import tempfile
import unittest

from trusted_checker_poc.contracts import AdapterError, Runner
from trusted_checker_poc.docker_adapter import DockerAdapter, DedicatedDaemonApproval, Plan, launch_spec
from trusted_checker_poc.registry import Registry, POLICY_ID
from .fakes import IMAGE, fixture_target
from . import support


class DockerContractTests(unittest.TestCase):
    def setUp(self):
        self.target = fixture_target()
        self.policy = Registry(runner_image_id=IMAGE).get(POLICY_ID)
        self.plan = Plan(self.policy,self.target,'00000000-0000-4000-8000-000000000001','a'*64)
        self.client = MagicMock()
        self.client.info.return_value = {'ID':'approved-dedicated-daemon'}
        self.client.networks.get.return_value.attrs = {'Id':self.target.network_id,'Name':'fixture','Internal':True,'Labels':{'tc-poc.scope':'poc-unit'}}
        self.approval = DedicatedDaemonApproval('approved-dedicated-daemon',self.target.network_id,'poc-unit','operator test fixture; not runtime verification')
        self.adapter = DockerAdapter(self.client,self.approval)

    def runner_attrs(self, phase='created', *, detached=False):
        spec = launch_spec(self.plan)
        started = phase != 'created'
        running = phase == 'running'
        connected = started and not detached
        return {'Id':'e'*64,'Image':IMAGE,'Config':{'User':spec['user'],'Entrypoint':spec['entrypoint'],'Cmd':[],
                'WorkingDir':'/scratch','Labels':spec['labels'],'Env':[k+'='+v for k,v in spec['environment'].items()]},
                'HostConfig':{'ReadonlyRootfs':True,'Privileged':False,'CapDrop':['ALL'],'CapAdd':[],
                              'Memory':self.policy.memory_bytes,'NanoCpus':self.policy.cpu_nanos,'PidsLimit':32,
                              'SecurityOpt':['no-new-privileges:true'],'NetworkMode':self.target.network_id,'Tmpfs':spec['tmpfs']},
                'State':{'Status':phase,'Running':running,'Pid':1234 if running else 0,
                         'StartedAt':'2026-10-15T00:00:01Z' if started else '0001-01-01T00:00:00Z'},
                'RestartCount':0,
                'NetworkSettings':{'Networks':{'fixture':{
                    'NetworkID':self.target.network_id if started else '',
                    'EndpointID':'1'*64 if connected else '',
                    'IPAddress':'172.29.0.3' if connected else ''}}},'Mounts':[]}

    def sdk_runner(self):
        obj = MagicMock()
        obj.id, obj.attrs = 'e'*64,self.runner_attrs()
        obj.start.side_effect = lambda: setattr(obj,'attrs',self.runner_attrs('running'))
        obj.wait.return_value = {'StatusCode':0}
        def finish(*args,**kwargs):
            obj.attrs = self.runner_attrs('exited',detached=True)
            return obj.wait.return_value
        obj.wait.side_effect = finish
        obj.logs.return_value = iter([b'{"result":"passed","reason":"probe_passed","evidence":{}}'])
        self.client.containers.get.return_value = obj
        self.client.containers.create.return_value = obj
        self.client.api.create_container.return_value = {'Id': obj.id}
        return obj

    def running_connection(self):
        return dict(container_id='e'*64,started_at='2026-10-15T00:00:01Z',
                    network_id=self.target.network_id,endpoint_id='1'*64,ipv4='172.29.0.3')

    def test_missing_daemon_approval_denies_before_contact(self):
        self.client.reset_mock()
        with self.assertRaises(ValueError):
            DockerAdapter(self.client,replace(self.approval,isolation_evidence=''))
        self.client.info.assert_not_called()

    def test_different_daemon_and_public_network_are_rejected(self):
        with self.assertRaises(ValueError):
            DockerAdapter(self.client,replace(self.approval,daemon_id='wrong'))
        self.client.networks.get.return_value.attrs['Internal'] = False
        with self.assertRaises(ValueError):
            DockerAdapter(self.client,self.approval)

    def test_docker_unavailability_is_distinct_from_missing_target(self):
        from docker.errors import NotFound
        for error,reason in ((NotFound('absent'),'target_unavailable'),(RuntimeError('daemon offline'),'docker_unavailable')):
            with self.subTest(reason=reason):
                self.client.containers.get.side_effect = error
                with self.assertRaises(AdapterError) as caught:
                    self.adapter.inspect_target(self.target.container_id)
                self.assertEqual(caught.exception.reason,reason)

    def test_create_spec_uses_registry_and_scoped_network_without_exec(self):
        obj = self.client.containers.create.return_value
        obj.id, obj.attrs = 'e'*64,self.runner_attrs()
        runner = self.adapter.prepare(self.plan)
        self.assertTrue(runner.config_verified)
        self.assertEqual(self.client.containers.create.call_args.kwargs,launch_spec(self.plan))
        obj.exec_run.assert_not_called()

    def test_runner_inspection_rejects_weakened_security(self):
        for field,value in [('Privileged',True),('ReadonlyRootfs',False),('CapAdd',['SYS_ADMIN']),
                            ('Binds',['/:/host']),('VolumesFrom',['other']),('PidMode','host'),('IpcMode','container:other'),
                            ('NetworkMode','host'),('PidsLimit',-1),('Memory',0),('Tmpfs',{})]:
            with self.subTest(field=field):
                attrs = self.runner_attrs()
                attrs['HostConfig'][field] = value
                obj = SimpleNamespace(attrs=attrs)
                self.assertFalse(self.adapter._runner_valid(obj,self.plan,phase='pre_start'))

    def test_runner_identity_environment_and_interactive_changes_rejected(self):
        for field,value in [('Tty',True),('OpenStdin',True),('User','0'),('Env',['POC_TARGET_IPV4=8.8.8.8']),
                            ('Labels',{'tc-poc.run':'forged'}),('Entrypoint',['sh'])]:
            with self.subTest(field=field):
                attrs = self.runner_attrs()
                attrs['Config'][field] = value
                self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='pre_start'))

    def test_created_endpoint_is_pending_only_for_expected_network_configuration(self):
        for network_id in ('',self.target.network_id):
            with self.subTest(network_id=network_id):
                attrs = self.runner_attrs()
                attrs['NetworkSettings']['Networks']['fixture']['NetworkID'] = network_id
                self.assertTrue(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='pre_start'))
        for mode,key,network_id in [('host','fixture',''),(self.target.network_id,'foreign',''),
                                    (self.target.network_id,'fixture','f'*64)]:
            with self.subTest(mode=mode,key=key,network_id=network_id):
                attrs = self.runner_attrs()
                attrs['HostConfig']['NetworkMode'] = mode
                endpoint = attrs['NetworkSettings']['Networks'].pop('fixture')
                endpoint['NetworkID'] = network_id
                attrs['NetworkSettings']['Networks'][key] = endpoint
                self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='pre_start'))

    def test_created_exception_requires_proof_of_never_started_state(self):
        variants = [('Status','running'),('Status','exited'),('Running',True),('Pid',1234),
                    ('StartedAt','2026-10-15T00:00:01Z'),('StartedAt',''),('Paused',True),('Restarting',True)]
        for field,value in variants:
            with self.subTest(field=field,value=value):
                attrs = self.runner_attrs()
                attrs['State'][field] = value
                self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='pre_start'))
        attrs = self.runner_attrs()
        attrs['RestartCount'] = 1
        self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='pre_start'))

    def test_approved_network_id_can_be_the_inspect_mapping_key(self):
        for state,phase in [('created','pre_start'),('running','post_start')]:
            with self.subTest(state=state):
                attrs = self.runner_attrs(state)
                networks = attrs['NetworkSettings']['Networks']
                networks[self.target.network_id] = networks.pop('fixture')
                self.assertTrue(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase=phase))

    def test_running_requires_real_network_id_endpoint_and_ipv4(self):
        attrs = self.runner_attrs('running')
        self.assertTrue(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='post_start'))
        for field,value in [('NetworkID',''),('NetworkID','f'*64),('EndpointID',''),
                            ('EndpointID','short'),('IPAddress',''),('IPAddress','127.0.0.1')]:
            with self.subTest(field=field,value=value):
                attrs = self.runner_attrs('running')
                attrs['NetworkSettings']['Networks']['fixture'][field] = value
                self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='post_start'))

    def test_extra_or_missing_network_rejected_in_both_phases(self):
        for state,phase in [('created','pre_start'),('running','post_start')]:
            for extra in (False,True):
                with self.subTest(state=state,extra=extra):
                    attrs = self.runner_attrs(state)
                    networks = attrs['NetworkSettings']['Networks']
                    if extra:
                        networks['foreign'] = copy.deepcopy(networks['fixture'])
                    else:
                        networks.clear()
                    self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase=phase))

    def test_created_and_running_phases_cannot_substitute_for_each_other(self):
        self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=self.runner_attrs()),self.plan,phase='post_start'))
        self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=self.runner_attrs('running')),self.plan,phase='pre_start'))

    def test_security_invariants_remain_required_after_start(self):
        for section,field,value in [('HostConfig','ReadonlyRootfs',False),('HostConfig','CapAdd',['SYS_ADMIN']),
                                    ('HostConfig','NetworkMode','host'),('Config','User','0'),
                                    ('Config','Env',[]),('Config','Labels',{})]:
            with self.subTest(section=section,field=field):
                attrs = self.runner_attrs('running')
                attrs[section][field] = value
                self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='post_start'))

    def test_finished_detach_needs_previous_live_endpoint_and_same_start(self):
        attrs = self.runner_attrs('exited',detached=True)
        obj = SimpleNamespace(attrs=attrs)
        self.assertTrue(self.adapter._runner_valid(obj,self.plan,phase='finished',connection=self.running_connection()))
        self.assertFalse(self.adapter._runner_valid(obj,self.plan,phase='finished'))
        for field,value in [('NetworkID',''),('NetworkID','f'*64),('EndpointID','f'*64),('IPAddress','172.29.0.4')]:
            with self.subTest(field=field):
                attrs = self.runner_attrs('exited',detached=True)
                attrs['NetworkSettings']['Networks']['fixture'][field] = value
                self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='finished',
                                                            connection=self.running_connection()))
        attrs = self.runner_attrs('exited',detached=True)
        attrs['State']['StartedAt'] = '2026-10-15T00:00:02Z'
        self.assertFalse(self.adapter._runner_valid(SimpleNamespace(attrs=attrs),self.plan,phase='finished',
                                                    connection=self.running_connection()))

    def test_valid_created_running_finished_lifecycle(self):
        obj = self.sdk_runner()
        runner = self.adapter.prepare(self.plan)
        self.assertTrue(runner.config_verified)
        outcome = self.adapter.run(self.plan,runner,1)
        self.assertEqual(outcome.result,'passed')
        obj.start.assert_called_once()

    def test_config_substitution_before_start_is_rejected(self):
        obj = self.sdk_runner()
        runner = self.adapter.prepare(self.plan)
        obj.attrs['HostConfig']['NetworkMode'] = 'host'
        with self.assertRaises(AdapterError) as caught:
            self.adapter.run(self.plan,runner,1)
        self.assertEqual(caught.exception.failure_class,'integrity')
        obj.start.assert_not_called()

    def test_fast_exit_without_observed_live_endpoint_is_unknown(self):
        obj = self.sdk_runner()
        runner = self.adapter.prepare(self.plan)
        obj.start.side_effect = lambda: setattr(obj,'attrs',self.runner_attrs('exited',detached=True))
        with self.assertRaises(AdapterError) as caught:
            self.adapter.run(self.plan,runner,1)
        self.assertEqual(caught.exception.failure_class,'integrity')
        obj.logs.assert_not_called()

    def test_post_start_failure_blocks_result_and_broker_cleans_exact_id(self):
        from trusted_checker_poc.broker import Broker
        from trusted_checker_poc.state import State
        for mutation in ('empty_network','foreign_network','extra_network','missing_endpoint','security'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory, support.RuntimeScope() as scope:
                obj = self.sdk_runner()
                def create(**spec):
                    labels = spec['labels']
                    intent = {key: labels['tc-poc.' + label] for key,label in
                              (('intent_id','intent'),('generation','generation'),('token','token'),('integration_id','integration'))}
                    self.plan = Plan(self.policy,self.target,labels['tc-poc.run'],spec['environment']['POC_CHALLENGE'],intent=intent)
                    obj.attrs = self.runner_attrs()
                    return {'Id': obj.id}
                self.client.api.create_container.side_effect = create
                def start():
                    attrs = self.runner_attrs('running')
                    endpoint = attrs['NetworkSettings']['Networks']['fixture']
                    if mutation == 'empty_network': endpoint['NetworkID'] = ''
                    elif mutation == 'foreign_network': endpoint['NetworkID'] = 'f'*64
                    elif mutation == 'extra_network': attrs['NetworkSettings']['Networks']['foreign'] = copy.deepcopy(endpoint)
                    elif mutation == 'missing_endpoint': endpoint['EndpointID'] = ''
                    else: attrs['HostConfig']['ReadonlyRootfs'] = False
                    obj.attrs = attrs
                obj.start.side_effect = start
                self.adapter.inspect_target = MagicMock(return_value=self.target)
                state = State(Path(directory)/'receipts.sqlite3')
                state.enroll(self.target)
                broker = Broker(state,Registry(runner_image_id=IMAGE),self.adapter,scope=self.target.scope)
                request = broker.issue(self.target.container_id,self.target.owner,POLICY_ID)
                result = broker.execute(request,owner=self.target.owner)
                scope.workers.join()
                self.assertEqual(result['result'],'unknown')
                self.assertEqual(result['failure_class'],'integrity')
                self.assertEqual(result['integrity']['checker_runtime'],'unknown')
                obj.wait.assert_not_called()
                obj.logs.assert_not_called()
                obj.remove.assert_called_once_with(force=True)
                self.assertTrue(all(call.args == ('e'*64,) for call in self.client.containers.get.call_args_list))
                self.client.containers.get.reset_mock()

    def test_cleanup_requires_exact_id_image_role_scope_run(self):
        runner = Runner('e'*64,IMAGE,self.plan.run_id,'poc-unit',True)
        obj = self.client.containers.get.return_value
        obj.attrs = self.runner_attrs()
        self.assertTrue(self.adapter.cleanup(runner))
        obj.remove.assert_called_once_with(force=True)
        for key in ('tc-poc.role','tc-poc.scope','tc-poc.run'):
            obj.remove.reset_mock()
            obj.attrs = self.runner_attrs()
            obj.attrs['Config']['Labels'][key] = 'foreign'
            self.assertFalse(self.adapter.cleanup(runner))
            obj.remove.assert_not_called()
        self.client.containers.list.assert_not_called()
        self.client.containers.prune.assert_not_called()

    def test_output_protocol_and_nonzero_runner_exit(self):
        runner = Runner('e'*64,IMAGE,self.plan.run_id,'poc-unit',True)
        obj = self.sdk_runner()
        obj.wait.return_value = {'StatusCode':2}
        with self.assertRaises(AdapterError) as caught:
            self.adapter.run(self.plan,runner,1)
        self.assertEqual(caught.exception.reason,'runner_crash')
        obj.wait.return_value = {'StatusCode':0}
        for raw in (b'x'*5000,b'{"integrity":"verified"}',b'not json'):
            obj.attrs = self.runner_attrs()
            obj.logs.return_value = iter([raw])
            with self.assertRaises(AdapterError):
                self.adapter.run(self.plan,runner,1)
