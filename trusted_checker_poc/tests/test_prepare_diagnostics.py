"""SDK fakes + real standalone SQLite/sidecar evidence. No Docker connections."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import time
from unittest.mock import Mock, patch
from uuid import uuid4

from requests.exceptions import ReadTimeout
from trusted_checker_poc.broker import Broker
from trusted_checker_poc.contracts import AdapterError, Runner
from trusted_checker_poc.diagnostics import PrepareTrace, valid_event
from trusted_checker_poc.lifecycle import Lifecycle
from trusted_checker_poc.integration.evidence import Journal
from trusted_checker_poc.integration.health import SuiteHalted
from trusted_checker_poc.integration.runtime import Runtime, RecordingAdapter
from trusted_checker_poc.integration.safety import Approval
from trusted_checker_poc.integration.scenarios import Scenarios, expect
from trusted_checker_poc.registry import Registry, POLICY_ID
from .fakes import IMAGE
from . import test_docker_contract
from . import support


class PrepareDiagnosticsTests(support.WorkerTestCase):
    def setUp(self):
        super().setUp()
        self.approval = Approval('unix:///never-contacted','approved-dedicated-daemon','poc-diag',
            IMAGE,'sha256:'+'d'*64,'python@sha256:'+'a'*64,approved=True,execute=True)
        self.journal = Journal(Path(self.temp.name)/'run',create=True,approval=self.approval,
            environment={'daemon_id':self.approval.daemon_id,'images':{'runner':IMAGE,'target':self.approval.target_image}})
        self.fixture = test_docker_contract.DockerContractTests(methodName='runTest')
        self.fixture.setUp()
        self.fixture.target = replace(self.fixture.target,scope=self.journal.body['scope'])
        self.fixture.approval = replace(self.fixture.approval,scope=self.journal.body['scope'])
        self.fixture.plan = replace(self.fixture.plan,target=self.fixture.target)
        self.client = self.fixture.client
        self.client.networks.get.return_value.attrs['Labels']['tc-poc.scope'] = self.journal.body['scope']
        self.obj = self.fixture.sdk_runner()
        self.runtime = Runtime(self.client,self.approval,self.journal)
        self.state = self.runtime.state
        self.state.enroll(self.fixture.target)
        self.adapter = RecordingAdapter(self.client,self.fixture.approval,self.journal)
        self.adapter.inspect_target = lambda _:self.fixture.target
        prepare = self.adapter.prepare
        def issued_prepare(plan):
            self.assertIsNotNone(self.state.receipt('create_intents',plan.run_id))
            self.fixture.plan = plan
            self.obj.attrs = self.fixture.runner_attrs()
            return prepare(plan)
        self.adapter.prepare = issued_prepare
        self.registry = Registry(runner_image_id=IMAGE,timeout=5)
        self.broker = Broker(self.state,self.registry,self.adapter,scope=self.fixture.target.scope)
        self.runtime.adapter,self.runtime.registry,self.runtime.broker = self.adapter,self.registry,self.broker
        self.request = None

    def execute(self):
        if self.request is None:
            self.request = self.broker.issue(self.fixture.target.container_id,self.fixture.target.owner,POLICY_ID)
        # Runtime's synthetic operator is fixed; this fixture uses its own owner.
        result = self.broker.execute(self.request,owner=self.fixture.target.owner)
        self.workers.join()
        self.runtime.returned_results.append({k:result[k] for k in ('run_id','result','reason','failure_class')})
        self.journal.report()
        return result

    def events(self):
        return self.journal.prepare_events()

    def assert_error(self,stage,code,known,owned=False):
        matches = [e for e in self.events() if e['error_code']==code and e['stage']==stage]
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0]['has_exact_id'],known)
        self.assertEqual(matches[0]['ownership_persisted'],owned)
        self.assertTrue(matches[0]['intent_persisted'])
        self.assertFalse(matches[0]['start_invoked'])

    def test_full_lifecycle_allowlist_without_tokens_or_sdk_data(self):
        self.assertEqual(self.execute()['result'],'passed')
        events = self.events()
        self.assertEqual([e['stage'] for e in events],['before_create','create_requested',
            'create_response_received','ownership_persisted','inspect_pending','prepare_finished','start_invoked'])
        self.assertTrue(all(valid_event(e) for e in events))
        self.assertEqual([e['elapsed_ms'] for e in events],sorted(e['elapsed_ms'] for e in events))
        intent = self.state.receipt('create_intents',self.request.run_id)
        raw = (self.journal.directory/'prepare-events.jsonl').read_text()
        self.assertNotIn(intent['token'],raw)
        self.assertNotIn('POC_CHALLENGE',raw)
        self.assertNotIn('Env',raw)
        self.assertEqual((self.journal.directory/'prepare-events.jsonl').stat().st_mode & 0o777,0o600)

    def test_exact_id_persisted_before_response_diagnostics_and_inspect(self):
        own = self.state.own_runner
        def persist(*args,**kwargs):
            self.assertNotIn('create_response_received',[e['stage'] for e in self.events()])
            self.client.containers.get.assert_not_called()
            return own(*args,**kwargs)
        with patch.object(self.state,'own_runner',side_effect=persist):
            self.assertEqual(self.execute()['result'],'passed')
        self.assertTrue(self.state.receipt('runner_ownership',self.request.run_id))

    def test_ownership_write_failure_preserves_known_id_fact_and_quarantine(self):
        error = sqlite3.OperationalError('private path token=SECRET')
        error.sqlite_errorcode = sqlite3.SQLITE_BUSY
        with patch.object(self.state,'own_runner',side_effect=error):
            result = self.execute()
        self.assertEqual((result['result'],result['reason']),('unknown','runner_prepare_unknown'))
        self.assert_error('create_response_received','sqlite_busy',True)
        self.obj.start.assert_not_called()
        self.client.containers.get.assert_not_called()
        self.obj.remove.assert_not_called()
        with self.assertRaises(SuiteHalted):self.runtime.ensure_healthy()
        self.assertEqual(self.journal.body['halt']['reason'],'unresolved_create_outcome')
        self.assertNotIn('SECRET',(self.journal.directory/'report.json').read_text())

    def test_api_timeout_during_create_has_no_claimed_exact_id(self):
        self.client.api.create_container.side_effect = ReadTimeout('http://private-host/?token=SECRET')
        result = self.execute()
        self.assertEqual(result['result'],'unknown')
        self.assert_error('create_requested','api_timeout',False)
        self.assertIsNone(self.state.receipt('runner_ownership',self.request.run_id))
        self.assertFalse(self.runtime.cleanup())
        self.obj.remove.assert_not_called()
        self.assertNotIn('SECRET',(self.journal.directory/'report.json').read_text())

    def test_sdk_response_lost_after_modeled_create_retains_lease(self):
        created = []
        def lost(**spec):
            created.append(True)  # Model daemon accepted create; caller has no ID.
            raise ReadTimeout('response lost')
        self.client.api.create_container.side_effect = lost
        self.execute()
        self.assertEqual(created,[True])
        self.assert_error('create_requested','api_timeout',False)
        self.assertIsNone(self.state.receipt('runner_ownership',self.request.run_id))
        self.assertFalse(self.runtime.cleanup())
        self.obj.remove.assert_not_called()

    def test_prepare_exception_with_owned_id_records_inspect_stage(self):
        self.client.containers.get.side_effect = ReadTimeout('private SDK detail')
        self.execute()
        self.assert_error('inspect_pending','api_timeout',True,True)
        self.assertIsNotNone(self.state.receipt('runner_ownership',self.request.run_id))
        self.obj.start.assert_not_called()
        with self.assertRaises(SuiteHalted):self.runtime.ensure_healthy()
        self.assertEqual(self.journal.body['halt']['reason'],'cleanup_incomplete')

    def test_prepare_exception_before_create_does_not_claim_container_absent(self):
        self.client.api.create_host_config.side_effect = ValueError('private data')
        self.execute()
        self.assert_error('before_create','value_error',False)
        self.client.api.create_container.assert_not_called()
        self.assertFalse(self.runtime.cleanup())  # No durable no-create proof is invented.

    def response_error(self,response,code):
        self.client.api.create_container.return_value = response
        self.assertEqual(self.execute()['reason'],'runner_prepare_unknown')
        self.assert_error('create_response_received',code,False)
        self.obj.start.assert_not_called()
        self.client.containers.get.assert_not_called()
        self.obj.remove.assert_not_called()

    def test_non_object_create_response_is_rejected(self):self.response_error(['SECRET'],'response_type_invalid')
    def test_missing_id_is_not_guessed_from_alternate_field(self):self.response_error({'ID':'e'*64},'response_id_missing')
    def test_short_id_is_not_accepted(self):self.response_error({'Id':'short SECRET'},'response_id_invalid')

    def test_duplicate_terminal_unknown_never_recreates_runner(self):
        self.client.api.create_container.side_effect = ReadTimeout('lost')
        first = self.execute()
        self.assertEqual(self.execute(),first)
        self.client.api.create_container.assert_called_once()
        self.obj.start.assert_not_called()
        self.assertIsNone(self.state.receipt('runner_ownership',self.request.run_id))

    def test_fail_fast_prevents_all_remaining_runtime_mutations(self):
        self.client.api.create_container.side_effect = ReadTimeout('lost')
        suite = Scenarios(self.runtime,20)
        suite.create_register_race = self.execute
        mutations = Mock(side_effect=AssertionError('must not run'))
        for name in ('basic','repetitions_case','security','identity','concurrency','timeout','crash','hung_runner','cleanup_guards'):
            setattr(suite,name,mutations)
        suite.run()
        mutations.assert_not_called()
        self.client.api.create_container.assert_called_once()
        self.client.containers.create.assert_not_called()
        self.client.networks.create.assert_not_called()
        self.assertEqual(self.journal.body['scenarios'][0]['status'],'test_inconclusive')
        self.assertTrue(all(s['status']=='NOT RUN' and s['started_at'] is None for s in self.journal.body['scenarios'][1:]))
        with self.assertRaises(SuiteHalted):self.runtime.target()
        with self.assertRaises(SuiteHalted):self.runtime.network_create()
        self.obj.remove.assert_not_called()

    def test_repetitions_stop_after_first_unknown_create_not_twenty_requests(self):
        self.client.api.create_container.side_effect = ReadTimeout('lost')
        # Synthetic target already enrolled, no SDK fixture provisioning in this fake test.
        record = {'id':self.fixture.target.container_id}
        self.runtime.target = Mock(return_value=record)
        self.runtime.configure = Mock()
        self.runtime.issue = lambda *_:self.broker.issue(record['id'],self.fixture.target.owner,POLICY_ID)
        self.runtime.execute = lambda request: self.broker.execute(request,owner=self.fixture.target.owner)
        suite = Scenarios(self.runtime,20)
        suite.case('short_runner_repetitions',suite.repetitions_case)
        summary = self.journal.body['short_runner_summary']
        self.assertEqual((summary['runs'],summary['unknown'],summary['not_run_repetitions']),(1,1,19))
        self.assertEqual(summary['request_metrics']['issued'],1)
        self.assertEqual(summary['request_metrics']['admitted'],1)
        self.assertEqual(summary['request_metrics']['physically_started_observed'],0)
        self.client.api.create_container.assert_called_once()

    def test_metrics_separate_issued_admitted_blocked_and_started(self):
        first = self.broker.issue(self.fixture.target.container_id,self.fixture.target.owner,POLICY_ID)
        self.state.admit(first,self.fixture.target.owner,2,time.time()+5)
        second = self.broker.issue(self.fixture.target.container_id,self.fixture.target.owner,POLICY_ID)
        blocked = self.broker.execute(second,owner=self.fixture.target.owner)
        self.runtime.returned_results.append(blocked)
        metrics = self.runtime.metrics()
        self.assertEqual((metrics['issued'],metrics['admitted'],metrics['not_admitted']),(2,1,1))
        self.assertEqual(metrics['blocked_by_active_lease'],1)
        self.assertEqual(metrics['terminal_receipts'],0)
        self.assertEqual(metrics['physically_started_observed'],0)
        self.assertEqual(metrics['start_invocations'],0)

    def test_success_metrics_distinguish_start_invocation_from_live_validation(self):
        self.execute()
        metrics = self.runtime.metrics()
        self.assertEqual((metrics['issued'],metrics['admitted'],metrics['start_requests'],metrics['start_invocations'],
                          metrics['physically_started_observed']),(1,1,1,1,1))

    def test_post_start_integrity_failure_halts_even_after_exact_cleanup(self):
        def bad_start():
            self.obj.attrs = self.fixture.runner_attrs('running')
            self.obj.attrs['HostConfig']['ReadonlyRootfs'] = False
        self.obj.start.side_effect = bad_start
        result = self.execute()
        self.assertEqual(result['failure_class'],'integrity')
        metrics = self.runtime.metrics()
        self.assertEqual(metrics['start_invocations'],1)
        self.assertEqual(metrics['physically_started_observed'],0)
        self.assertEqual(metrics['post_start_validation_failure'],1)
        self.obj.remove.assert_called_once_with(force=True)
        with self.assertRaises(SuiteHalted):self.runtime.ensure_healthy()
        self.assertEqual(self.journal.body['halt']['reason'],'environmental_integrity_unproven')

    def test_preexisting_halt_marks_case_not_run_without_fixture_mutations(self):
        self.journal.body['halt'] = {'reason':'unresolved_create_outcome','run_id':str(uuid4()),'at':'test'}
        operation = Mock()
        suite = Scenarios(self.runtime,20)
        suite.case('not_started',operation)
        operation.assert_not_called()
        self.assertEqual(self.journal.body['scenarios'][0]['status'],'NOT RUN')
        self.client.api.create_container.assert_not_called()

    def test_narrow_scenario_selects_one_request_and_no_repetition_batch(self):
        record = {'id':self.fixture.target.container_id}
        self.runtime.target = Mock(return_value=record)
        self.runtime.configure = Mock()
        def issue(*_):
            self.request = self.broker.issue(record['id'],self.fixture.target.owner,POLICY_ID)
            return self.request
        self.runtime.issue = issue
        self.runtime.execute = lambda request:self.execute()
        suite = Scenarios(self.runtime,20)
        suite.run_diagnostic()
        self.assertEqual(self.journal.body['status'],'test_passed')
        self.assertEqual(len(self.journal.body['scenarios']),1)
        self.client.api.create_container.assert_called_once()
        self.assertNotIn('short_runner_measurements',self.journal.body)

    def test_expected_negative_with_confirmed_cleanup_does_not_halt_suite(self):
        self.obj.logs.return_value = iter([b'{"result":"failed","reason":"service_unreachable","evidence":{}}'])
        suite = Scenarios(self.runtime,1)
        suite.case('expected_negative',lambda:expect(self.execute(),'failed','service_unreachable'))
        subsequent = Mock()
        suite.case('next',subsequent)
        subsequent.assert_called_once()
        self.assertNotIn('halt',self.journal.body)
        self.assertEqual(self.journal.body['scenarios'][0]['status'],'test_passed')

    def test_sink_failure_does_not_lose_ownership_or_allow_more_fixtures(self):
        with patch('trusted_checker_poc.integration.evidence.os.fsync',side_effect=OSError('disk error SECRET')):
            result = self.broker.execute(self.broker.issue(self.fixture.target.container_id,self.fixture.target.owner,POLICY_ID),
                                         owner=self.fixture.target.owner)
            self.workers.join()
        self.assertEqual(result['result'],'unknown')  # Existing inspect journal save fails closed.
        self.assertEqual(self.state.receipt('runner_ownership',result['run_id'])['container_id'],self.obj.id)
        self.assertTrue(self.journal.body['diagnostics_write_failed'])
        with self.assertRaises(SuiteHalted):self.runtime.ensure_healthy()
        self.assertEqual(self.journal.body['halt']['reason'],'diagnostics_unavailable')
        self.client.api.create_container.assert_called_once()

    def test_diagnostics_are_bounded_and_reject_extra_sensitive_fields(self):
        values = []
        trace = PrepareTrace(str(uuid4()),values.append)
        for _ in range(100):trace.emit('before_create')
        self.assertEqual(len(values),32)
        with self.assertRaises(ValueError):self.journal.prepare_event({**values[0],'token':'SECRET'})
        self.assertNotIn('SECRET',json.dumps(self.journal.body))

    def test_timeout_event_does_not_replace_inflight_create_stage(self):
        trace = PrepareTrace(str(uuid4()),self.journal.prepare_event)
        trace.emit('create_requested')
        trace.write(trace.snapshot('timeout','deadline_expired',update_stage=False))
        trace.fail(ReadTimeout('SECRET'))
        self.assertEqual([(e['stage'],e['error_code']) for e in self.events()],
            [('create_requested','none'),('timeout','deadline_expired'),('create_requested','api_timeout')])

    def test_start_diagnostics_do_not_delay_fenced_sdk_invocation(self):
        request = self.broker.issue(self.fixture.target.container_id,self.fixture.target.owner,POLICY_ID)
        self.state.admit(request,self.fixture.target.owner,2,time.time()+5)
        order = []
        lifecycle = Lifecycle(self.state,request.run_id,time.monotonic()+5,self.approval.daemon_id,
                              self.journal.body['integration_id'],lambda event:order.append(event['stage']))
        lifecycle.begin('a'*64)
        lifecycle.received(self.obj.id)
        self.assertTrue(self.state.register_runner(request.run_id,
            Runner(self.obj.id,IMAGE,request.run_id,self.fixture.target.scope,True)))
        def invoked():
            self.assertNotIn('start_invoked',order)
            order.append('sdk_start')
            raise AdapterError('docker_unavailable','infrastructure')
        with self.assertRaises(AdapterError):
            lifecycle.start(invoked)
        self.assertEqual(order[-2:],['sdk_start','start_invoked'])
        with self.state.db() as db:
            self.assertIsNotNone(db.execute('SELECT 1 FROM runner_starts WHERE run_id=?',(request.run_id,)).fetchone())
