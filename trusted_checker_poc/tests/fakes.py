"""Fake Docker boundary: none of these operations connect to a daemon."""
from dataclasses import replace
import json
import threading
import time
from uuid import uuid4

from trusted_checker_poc.contracts import AdapterError, Outcome, Runner, Target
from trusted_checker_poc.docker_adapter import Plan
from trusted_checker_poc.runner import probe

IMAGE = 'sha256:'+'a'*64


def fixture_target():
    return Target('b'*64,'generation-1','synthetic-owner','synthetic-localhost','c'*64,
                  '172.29.0.2','2026-10-15T00:00:00Z',0,'sha256:'+'d'*64,'poc-unit')


class FakeAdapter:
    def __init__(self, target=None, counter=None):
        self.target = target or fixture_target()
        self.counter = counter
        self.physical_runs = 0
        self.prepares = 0
        self.target_exec_calls = 0
        self.cleaned = []
        self.bind = '0.0.0.0'
        self.static_body = None
        self.status = 200
        self.delay = 0
        self.started = threading.Event()
        self.block = None
        self.error = None
        self.post_target = None
        self.artifact = IMAGE
        self.cleanup_ok = True
        self.inspect_error = None
        self.before_disappears = False
        self.after_disappears = False
        self.check_sh = 'untrusted'
        self.curl = 'untrusted'
        self.path = 'untrusted'

    def inspect_target(self, container_id):
        if self.inspect_error:
            raise self.inspect_error
        if self.before_disappears or (self.after_disappears and self.physical_runs):
            raise AdapterError('target_unavailable','target_unavailable')
        if self.physical_runs and self.post_target:
            return self.post_target
        return self.target

    def plan(self, policy, target, run_id, challenge):
        return Plan(policy,target,run_id,challenge)

    def prepare(self, plan):
        self.prepares += 1
        return Runner(uuid4().hex + uuid4().hex,self.artifact,plan.run_id,self.target.scope,True)

    def run(self, plan, runner, remaining):
        self.physical_runs += 1
        if self.counter is not None:
            with self.counter.get_lock():
                self.counter.value += 1
        self.started.set()
        if self.block:
            self.block.wait()  # Owned/released by the test, never an automatic fake success.
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        adapter = self

        class Response:
            status = adapter.status
            def read(self, maximum):
                raw = adapter.static_body if adapter.static_body is not None else json.dumps(
                    {'challenge':plan.challenge,'service':'synthetic-ipv4-v1'}).encode()
                return raw[:maximum]

        class Connection:
            def __init__(self, host, port, timeout):
                assert host == plan.target.ipv4 and port == 8080
            def request(self, method, path, headers):
                assert method == 'GET' and path == '/probe'
                if adapter.bind == '127.0.0.1':
                    raise ConnectionRefusedError
            def getresponse(self):
                return Response()
            def close(self):
                pass

        return Outcome(**probe(plan.target.ipv4,plan.challenge,connection_factory=Connection))

    def cleanup(self, runner):
        self.cleaned.append(runner.container_id)
        return self.cleanup_ok
