"""Exact owned cleanup and independently authenticated create-trace recovery."""
from uuid import uuid4
import json
from trusted_checker_runtime.boundary import capture_create_response
from trusted_checker_runtime.contracts import CleanupConfirmation, Resource
from trusted_checker_runtime.profiles import require
from trusted_checker_runtime.journal import body
from trusted_checker_shadow.policy import digest
from .spec import normalize


class ExactCleanup:
    def __init__(self, adapter, signer):
        self.adapter, self.signer = adapter, signer

    def confirm(self, identifier, resource):
        adapter, a = self.adapter, self.adapter.authority
        row, intent, approval, owned = adapter.owned(identifier, resource)
        if row['cleanup'] == 'confirmed':
            return a.report(identifier, resource)  # Idempotent replay, no remove.
        require(row['terminal'] is not None if resource == Resource.RUNNER else row['phase'] == 'quarantined',
                'cleanup_not_authorized')
        adapter.daemon(identifier, recovery=True)
        attrs = adapter._call('inspect_container', owned['receipt']['container_id'], recovery=True)
        require(attrs.get('Id') == owned['receipt']['container_id'] and attrs.get('Image') == intent.image_id,
                'cleanup_identity_mismatch')
        # Exact original intent labels are consistency checks AFTER ownership,
        # not the source of permission. Includes mutable root target quarantine.
        labels = attrs.get('Config', {}).get('Labels') or {}
        require(labels.get('tc-shadow.intent') == identifier and labels.get('tc-shadow.scope') == intent.scope and
                labels.get('tc-shadow.domain') == resource.value and
                labels.get('tc-shadow.binding') == intent.runtime_binding_uuid and
                labels.get('tc-shadow.generation') == intent.generation_uuid, 'cleanup_binding_mismatch')
        with a.journal.transaction() as db:
            a.journal.put(db, 'remove_intent', identifier, {'container_id': owned['receipt']['container_id'],
                          'ownership': owned['attestation_digest'], 'daemon': body(approval.daemon)})
        # Successful raw DELETE/HTTP204 is removal evidence. A timeout/404 after
        # lost response is not promoted to confirmed by a later NotFound inspect.
        acknowledgement = adapter._call('remove_owned_raw', owned['receipt']['container_id'], recovery=True)
        require(acknowledgement == 204, 'remove_acknowledgement_unconfirmed')
        evidence = {'exact_id': owned['receipt']['container_id'], 'ownership': owned['attestation_digest'],
                    'daemon': body(approval.daemon), 'operation': 'raw_delete_acknowledged', 'at': a.clock()}
        with a.journal.transaction() as db:
            a.journal.put(db, 'remove_ack', identifier, evidence)
        signed = self.signer.sign(CleanupConfirmation(str(uuid4()), identifier, approval.scope, a.clock(), resource,
            approval.daemon, owned['receipt']['container_id'], owned['attestation_digest'], digest(evidence), 'removed_confirmed'))
        a.record_cleanup(signed)
        return a.report(identifier, resource)


class OwnershipRecovery:
    """No list/search/prune/start/delete. Requires a separately signed trace.

    Trace source must already have established exact event/intent/session origin;
    matching labels/inspect alone is never accepted as independent evidence.
    """
    def __init__(self, adapter):
        self.adapter = adapter

    def recover(self, permit, signed_trace):
        from trusted_checker_runtime.contracts import CreateTrace
        adapter, a = self.adapter, self.adapter.authority
        row, intent, approval = adapter.context(permit.intent_uuid, permit.resource, False)
        require(row['phase'] == 'quarantined' or row['terminal'] is not None and
                json.loads(row['terminal'])['result'] == 'unknown', 'recovery_cleanup_only')
        trace = a.verifier.verify(signed_trace, CreateTrace, approval.scope)
        require((trace.context_uuid, trace.daemon, trace.intent_digest, trace.image_id, trace.resource) ==
                (intent.intent_uuid, intent.daemon, digest(body(intent)), intent.image_id, intent.resource) and
                intent.created_at <= trace.create_at <= intent.deadline and trace.observed_at <= a.clock(), 'create_trace_binding_mismatch')
        with a.journal.transaction() as db:
            require(a.journal.get(db, 'create_dispatch_'+a._kind(intent.resource), intent.intent_uuid) == body(permit),
                    'recovery_dispatch_missing')
            a.journal.receipt(db, signed_trace, intent.intent_uuid, 'independent_create_trace')
            a.journal.put(db, 'independent_create_trace', intent.intent_uuid, {'digest': signed_trace.digest, 'proof': body(trace)})
            if a._document_exists(db, 'ownership_'+intent.resource.value, intent.intent_uuid):
                owned = a._ownership(db, intent.resource, intent.intent_uuid)
                require(owned['receipt']['container_id'] == trace.container_id, 'recovery_ownership_conflict')
                already_owned = True
            else:
                already_owned = False
        if already_owned:
            return a.report(intent.intent_uuid, intent.resource)
        adapter.daemon(intent.intent_uuid, recovery=True)
        attrs = adapter._call('inspect_container', trace.container_id, recovery=True)
        require(attrs.get('Id') == trace.container_id and attrs.get('Image') == intent.image_id and
                attrs.get('State', {}).get('Status') == 'created' and attrs.get('RestartCount') == 0, 'recovery_prestart_required')
        normalize(approval, intent, attrs)
        signed = adapter.signer.sign(capture_create_response(intent, permit, {'Id': trace.container_id},
            daemon=approval.daemon, receipt_uuid=str(uuid4()), observed_at=a.clock()))
        # Quarantined/terminal state ensures even an unexpired approval cannot start.
        a.record_create_response(permit, signed)
        return a.report(intent.intent_uuid, intent.resource)
