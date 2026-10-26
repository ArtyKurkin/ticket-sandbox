"""Real PostgreSQL concurrency test for observation-only dispatch."""

from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import connection, connections
from django.test import TransactionTestCase

from sandbox.models import HTTPObservationRun
from sandbox.services.http_observations import request_observation
from sandbox.tests.base import SandboxTestCase
from sandbox.tests.test_http_observations import HTTPObservationTests


class PostgreSQLConcurrencyTests(TransactionTestCase):
    # Reuse existing synthetic fixtures without inheriting TestCase's
    # wrapping transaction, which would conceal PostgreSQL row locking.
    create_user = SandboxTestCase.create_user
    create_queue = SandboxTestCase.create_queue
    create_task = SandboxTestCase.create_task
    env_event = HTTPObservationTests.env_event
    setUp = HTTPObservationTests.setUp

    def test_two_requests_create_one_run_and_one_dispatch(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL row locks")

        barrier = Barrier(2)

        def request():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                run, created = request_observation(
                    attempt_id=self.attempt.pk,
                    user_id=self.user.pk,
                )
                return str(run.run_id), created
            finally:
                connections.close_all()

        # Django settings overrides are context-local: propagate them
        # independently into each worker thread.
        ctx1 = copy_context()
        ctx2 = copy_context()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(ctx1.run, request)
            second = pool.submit(ctx2.run, request)
            results = [first.result(timeout=20), second.result(timeout=20)]

        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sorted(r[1] for r in results), [False, True])
        self.assertEqual(
            HTTPObservationRun.objects.filter(attempt=self.attempt).count(),
            1,
        )
        self.delay.assert_called_once_with(results[0][0])
