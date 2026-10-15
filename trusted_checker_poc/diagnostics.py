"""Bounded allowlisted diagnostics. Never serialize exception text or SDK data."""
import math
import sqlite3
import time
from uuid import UUID

from .contracts import AdapterError, InvalidRequest

STAGES = frozenset(('before_create','create_requested','create_response_received','ownership_persisted',
                    'inspect_pending','prepare_finished','start_invoked','cancellation','timeout'))
ERRORS = frozenset(('none','api_timeout','api_error','transport_error','response_decode_error',
                    'response_type_invalid','response_id_missing','response_id_invalid',
                    'sqlite_busy','sqlite_locked','sqlite_error','ownership_binding_error',
                    'invalid_request','key_error','type_error','value_error','unexpected_error',
                    'cancelled','deadline_expired','adapter_error'))
FIELDS = frozenset(('run_id','stage','elapsed_ms','has_exact_id','error_code','intent_persisted',
                    'ownership_persisted','start_invoked'))


def error_code(error, *, ownership=False):
    # Class/code only, no str(error), repr, traceback, URL or response body.
    from requests.exceptions import Timeout, ConnectionError, JSONDecodeError
    from docker.errors import APIError
    if isinstance(error, (TimeoutError, Timeout)):
        return 'api_timeout'
    if isinstance(error, JSONDecodeError):
        return 'response_decode_error'
    if isinstance(error, APIError):
        return 'api_error'
    if isinstance(error, ConnectionError):
        return 'transport_error'
    if isinstance(error, sqlite3.Error):
        number = getattr(error, 'sqlite_errorcode', None)
        if type(number) is int:
            if number & 255 == sqlite3.SQLITE_BUSY: return 'sqlite_busy'
            if number & 255 == sqlite3.SQLITE_LOCKED: return 'sqlite_locked'
        return 'sqlite_error'
    if isinstance(error, InvalidRequest):
        return 'ownership_binding_error' if ownership else 'invalid_request'
    if isinstance(error, AdapterError):
        if error.reason == 'runner_deadline_exceeded': return 'deadline_expired'
        if error.reason == 'execution_cancelled': return 'cancelled'
        return 'adapter_error'
    if isinstance(error, KeyError): return 'key_error'
    if isinstance(error, TypeError): return 'type_error'
    if isinstance(error, ValueError): return 'value_error'
    return 'unexpected_error'


def valid_event(body):
    try:
        return (type(body) is dict and set(body) == FIELDS and str(UUID(body['run_id'])) == body['run_id'] and
                body['stage'] in STAGES and body['error_code'] in ERRORS and
                type(body['elapsed_ms']) in (int,float) and math.isfinite(body['elapsed_ms']) and
                body['elapsed_ms'] >= 0 and
                all(type(body[k]) is bool for k in ('has_exact_id','intent_persisted','ownership_persisted','start_invoked')))
    except (ValueError,TypeError,KeyError,AttributeError):
        return False


class PrepareTrace:
    def __init__(self, run_id, sink=None):
        self.run_id, self.sink = run_id, sink
        self.began = time.monotonic()
        self.stage = 'before_create'
        self.has_exact_id = self.intent_persisted = self.ownership_persisted = self.start_invoked = False
        self.count = 0
        self.last_error = None

    def snapshot(self, stage, code='none', *, update_stage=True):
        if update_stage:
            self.stage = stage
        return {'run_id': self.run_id, 'stage': stage,
                'elapsed_ms': round(max(0, time.monotonic()-self.began)*1000, 3),
                'has_exact_id': self.has_exact_id, 'error_code': code,
                'intent_persisted': self.intent_persisted, 'ownership_persisted': self.ownership_persisted,
                'start_invoked': self.start_invoked}

    def write(self, event):
        if self.count >= 32:
            return
        self.count += 1
        if self.sink is not None and valid_event(event):
            try:
                self.sink(event)
            except Exception:
                # Diagnostics MUST NOT prevent ownership persistence/start fencing.
                # The sink records its own health failure for harness fail-fast.
                pass

    def emit(self, stage, code='none'):
        self.write(self.snapshot(stage, code))

    def fail(self, error, *, ownership=False, code=None):
        code = code or error_code(error, ownership=ownership)
        stage = 'timeout' if code == 'deadline_expired' else 'cancellation' if code == 'cancelled' else self.stage
        # The enclosing broker may see the same error again; preserve the more
        # specific prepare-stage diagnosis rather than overwrite it generically.
        if self.last_error is None:
            self.emit(stage, code)
            self.last_error = code
