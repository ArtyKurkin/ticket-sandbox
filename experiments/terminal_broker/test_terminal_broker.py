"""Offline unit tests: python -m unittest discover -s experiments/terminal_broker -p 'test_*.py'"""
import json
import unittest
from unittest.mock import patch

from terminal_broker import valid_target


class TargetIdentityTests(unittest.TestCase):
    def setUp(self):
        self.container_id = "a" * 64
        self.payload = {
            "Id": self.container_id,
            "State": {"Running": True},
            "Config": {"Labels": {
                "ticket-sandbox.type": "task",
                "ticket-sandbox.attempt": "17",
                "ticket-sandbox.queue": "l1",
                "ticket-sandbox.task": "service-bind-localhost",
            }},
        }

    def allowed(self, **changes):
        payload = json.loads(json.dumps(self.payload))
        for k, v in changes.items():
            payload[k] = v
        with patch("terminal_broker.inspect_target", return_value=payload):
            return valid_target(self.container_id, 17, "l1", "service-bind-localhost")

    def test_matching_target(self):
        self.assertTrue(self.allowed())

    def test_replaced_id(self):
        self.assertFalse(self.allowed(Id="b" * 64))

    def test_stopped_target(self):
        self.assertFalse(self.allowed(State={"Running": False}))

    def test_wrong_attempt(self):
        self.payload["Config"]["Labels"]["ticket-sandbox.attempt"] = "18"
        self.assertFalse(self.allowed())

    def test_wrong_queue(self):
        self.payload["Config"]["Labels"]["ticket-sandbox.queue"] = "candidate"
        self.assertFalse(self.allowed())

    def test_wrong_task(self):
        self.payload["Config"]["Labels"]["ticket-sandbox.task"] = "other"
        self.assertFalse(self.allowed())

    def test_no_labels(self):
        self.assertFalse(self.allowed(Config={"Labels": {}}))

    def test_docker_failure_closed(self):
        with patch("terminal_broker.inspect_target", side_effect=ValueError("failed")):
            self.assertFalse(valid_target(self.container_id, 17, "l1", "service-bind-localhost"))


if __name__ == "__main__":
    unittest.main()
