import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import terminal_broker as b
except ImportError:
    import terminal_broker as b


ID = 'a' * 64
TOKEN = 'b' * 32


class RecoveryTests(unittest.TestCase):
    def test_roundtrip_and_recovery(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            b.save_session(folder, ID, 123, TOKEN)
            self.assertEqual((folder / (TOKEN + '.json')).stat().st_mode & 0o777, 0o600)
            with patch.object(b, 'cleanup_remote_shell', return_value=True) as cleanup:
                self.assertTrue(b.recover_sessions(folder, ID))
            cleanup.assert_called_once_with(ID, 123, TOKEN)
            self.assertEqual(list(folder.glob('*.json')), [])

    def test_unconfirmed_remains_for_operator(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            b.save_session(folder, ID, 123, TOKEN)
            with patch.object(b, 'cleanup_remote_shell', return_value=False):
                self.assertFalse(b.recover_sessions(folder, ID))
            self.assertTrue((folder / (TOKEN + '.json')).exists())

    def test_foreign_container_not_signalled(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            b.save_session(folder, 'c'*64, 123, TOKEN)
            with patch.object(b, 'cleanup_remote_shell') as cleanup:
                self.assertFalse(b.recover_sessions(folder, ID))
            cleanup.assert_not_called()

    def test_invalid_tokens_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                b.save_session(Path(root), ID, 123, '../danger')

    def test_malformed_record_not_signalled(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            (folder / (TOKEN + '.json')).write_text('{')
            with patch.object(b, 'cleanup_remote_shell') as cleanup:
                self.assertFalse(b.recover_sessions(folder, ID))
            cleanup.assert_not_called()

    def test_boolean_pid_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            (folder / (TOKEN + '.json')).write_text('{"container_id":"' + ID + '","pid":true,"token":"' + TOKEN + '"}')
            with patch.object(b, 'cleanup_remote_shell') as cleanup:
                self.assertFalse(b.recover_sessions(folder, ID))
            cleanup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
