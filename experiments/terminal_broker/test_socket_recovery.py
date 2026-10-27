import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import terminal_broker as broker
except ImportError:
    import terminal_broker as broker


class SocketRecoveryTests(unittest.TestCase):
    def test_missing_path_is_allowed(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(broker.prepare_socket_path(Path(folder) / 'session.sock'))

    def test_stale_socket_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.sock'
            s = socket.socket(socket.AF_UNIX)
            s.bind(str(path))
            s.close()
            self.assertTrue(broker.prepare_socket_path(path))
            self.assertFalse(path.exists())

    def test_live_listener_not_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.sock'
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(path))
                server.listen(1)
                with self.assertRaisesRegex(RuntimeError, 'active listener'):
                    broker.prepare_socket_path(path)
                self.assertTrue(path.exists())

    def test_regular_file_not_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.sock'
            path.write_text('do not delete')
            with self.assertRaisesRegex(RuntimeError, 'not an owned Unix socket'):
                broker.prepare_socket_path(path)
            self.assertEqual(path.read_text(), 'do not delete')

    def test_symlink_not_followed(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'target'
            target.write_text('keep')
            path = Path(folder) / 'session.sock'
            path.symlink_to(target)
            with self.assertRaisesRegex(RuntimeError, 'not an owned Unix socket'):
                broker.prepare_socket_path(path)
            self.assertEqual(target.read_text(), 'keep')

    def test_foreign_owner_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.sock'
            s = socket.socket(socket.AF_UNIX)
            s.bind(str(path))
            s.close()
            with patch.object(broker.os, 'geteuid', return_value=os.geteuid() + 1):
                with self.assertRaisesRegex(RuntimeError, 'not an owned Unix socket'):
                    broker.prepare_socket_path(path)
            self.assertTrue(path.exists())


if __name__ == '__main__':
    unittest.main()
