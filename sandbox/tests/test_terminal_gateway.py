import os
from unittest.mock import patch

from django.test import SimpleTestCase

from sandbox.services.terminal_gateway import (
    build_terminal_base_path,
    build_terminal_url,
    terminal_gateway_enabled,
)


class TerminalGatewayUrlTests(SimpleTestCase):
    @patch.dict(
        os.environ,
        {
            "TERMINAL_GATEWAY_ENABLED": "false",
            "EXTERNAL_HOST": "localhost",
        },
    )
    def test_terminal_gateway_disabled_builds_direct_url(self):
        self.assertFalse(terminal_gateway_enabled())

        self.assertEqual(
            build_terminal_base_path(
                attempt_id=123,
                port=24000,
            ),
            "",
        )

        self.assertEqual(
            build_terminal_url(
                attempt_id=123,
                port=24000,
            ),
            "http://localhost:24000",
        )

    @patch.dict(
        os.environ,
        {
            "TERMINAL_GATEWAY_ENABLED": "true",
            "EXTERNAL_HOST": "localhost",
        },
    )
    def test_terminal_gateway_enabled_builds_gateway_url(self):
        self.assertTrue(terminal_gateway_enabled())

        self.assertEqual(
            build_terminal_base_path(
                attempt_id=123,
                port=24000,
            ),
            "/terminal/123/24000/",
        )

        self.assertEqual(
            build_terminal_url(
                attempt_id=123,
                port=24000,
            ),
            "/terminal/123/24000/",
        )

    @patch.dict(
        os.environ,
        {
            "TERMINAL_GATEWAY_ENABLED": "1",
            "EXTERNAL_HOST": "localhost",
        },
    )
    def test_terminal_gateway_accepts_one_as_enabled(self):
        self.assertTrue(terminal_gateway_enabled())

    @patch.dict(
        os.environ,
        {
            "TERMINAL_GATEWAY_ENABLED": "yes",
            "EXTERNAL_HOST": "localhost",
        },
    )
    def test_terminal_gateway_accepts_yes_as_enabled(self):
        self.assertTrue(terminal_gateway_enabled())
