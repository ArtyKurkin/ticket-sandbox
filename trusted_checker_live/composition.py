"""Explicit synchronous operator composition. No HTTP/Celery/Django/bootstrap."""
from trusted_checker_runtime.contracts import Phase, Resource
from trusted_checker_runtime.profiles import Denied, require


class LiveRuntime:
    def __init__(self, authority, adapter, enforcer, validator, cleanup, *, mock_network_factory=None):
        require(validator is not enforcer.checker, 'independent_validator_required')
        self.authority, self.adapter = authority, adapter
        self.enforcer, self.validator, self.cleanup = enforcer, validator, cleanup
        self.mock_network_factory = mock_network_factory

    def _bundle(self, context, phase, enrollment=None, runner=None):
        adapter = self.adapter
        approval = adapter.approval()
        identity = (adapter.observe_initial_target(context) if phase == Phase.ENROLL else
                    adapter.observe_target(enrollment, context, phase))
        network = adapter.observe_network(context, phase, identity.payload.target, runner.payload if runner else None)
        enforcement = self.enforcer.attest(approval, context, phase, identity.payload.target, runner.payload if runner else None)
        validation = self.validator.attest(approval, context, phase, identity.payload.target,
                                           runner.payload if runner else None, enforcement)
        return identity, network, enforcement, validation

    def provision_new(self, request):
        a, adapter = self.authority, self.adapter
        adapter.approval()  # OFF before client factory; no arbitrary target locator.
        intent = a.provision(request)
        report = a.report(intent.intent_uuid, Resource.TARGET)
        if report['phase'] == 'enrolled':
            return a.enroll(intent.intent_uuid)
        require(report['phase'] == 'intent_recorded', 'provision_in_progress_or_unknown')
        try:
            adapter.create(intent)
            adapter.start_target(intent.intent_uuid)
            a.verify_provision(intent.intent_uuid, *self._bundle(intent.intent_uuid, Phase.ENROLL))
            return a.enroll(intent.intent_uuid)
        except Exception:
            a.quarantine(intent.intent_uuid, Resource.TARGET)
            raise Denied('target_provision_unconfirmed') from None

    def submit(self, request, enrollment):
        a, adapter = self.authority, self.adapter
        adapter.approval()
        run_id = a.reserve_run(request, enrollment)
        network = None
        if a.report(run_id)['phase'] != 'reserved':
            a.expire_run(run_id)
            return a.report(run_id)  # Never resume a half-issued/start-ambiguous run.
        try:
            a.check_target(run_id, Phase.BEFORE_CREATE, *self._bundle(run_id, Phase.BEFORE_CREATE, enrollment))
            adapter.create(a.runner_create_intent(run_id))
            runner = adapter.observe_owned_runner(run_id)
            a.check_target(run_id, Phase.BEFORE_START, *self._bundle(run_id, Phase.BEFORE_START, enrollment, runner), runner=runner)
            adapter.start_runner(a.authorize_start(run_id))
            a.record_runner_live(run_id, adapter.observe_owned_runner(run_id))
            if self.mock_network_factory is not None:
                from trusted_checker_network.lifecycle import MockNetworkLifecycle
                network = self.mock_network_factory(a, run_id)
                require(type(network) is MockNetworkLifecycle, 'sealed_mock_network_session_required')
                network.before_probe()
            # A real independently installed active ruleset + namespace matrix
            # MUST exist here. Bootstrap-only rules never release the HTTP probe.
            runner = adapter.observe_owned_runner(run_id)
            a.check_target(run_id, Phase.BEFORE_PROBE, *self._bundle(run_id, Phase.BEFORE_PROBE, enrollment, runner), runner=runner)
            a.record_probe(run_id, adapter.release_and_collect(run_id, enrollment))
            if network is not None:
                network.after_probe()
            for phase in (Phase.AFTER_PROBE, Phase.BEFORE_PUBLISH):
                runner = adapter.observe_owned_runner(run_id)
                a.check_target(run_id, phase, *self._bundle(run_id, phase, enrollment, runner), runner=runner)
            if network is not None:
                network.before_publication()
            adapter.finish_runner(run_id)
            if network is not None:
                network.finished()
            a.publish(run_id)
        except Exception:
            if network is not None:
                network.abort()
            a.abandon_run(run_id)
        try:
            self.cleanup.confirm(run_id, Resource.RUNNER)
            if network is not None:
                network.cleaned()
        except Exception:
            pass  # Separate pending/quarantined cleanup is authoritative in report.
        return a.report(run_id)

    def kill(self):
        # Persist cancellation independently of SQLite lock held by an in-flight
        # SDK call. This live journal cannot be re-enabled; recovery remains usable.
        self.authority.journal.request_stop()
        try:
            self.authority.kill()
        except Exception:
            # The durable stop latch itself closes every v2 launch gate.
            return 'stop_latched_control_update_pending'
        return 'stop_latched'

    def rollback_target(self, enrollment):
        self.kill()
        self.authority.revoke_binding(enrollment)
        return self.cleanup.confirm(enrollment.provisioning_uuid, Resource.TARGET)
