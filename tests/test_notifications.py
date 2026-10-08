"""
tests/test_notifications.py — Tests unitaires pour le module de notifications.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

from core.notifications import (
    _escape_ps_string,
    send_windows_toast,
    send_macos_notification,
    send_linux_notification,
    send_system_notification,
    notify_transcription_complete,
    notify_batch_complete,
    play_chime
)


class TestNotifications(unittest.TestCase):

    def test_escape_ps_string(self):
        text = "L'audio `test` avec $symbole"
        escaped = _escape_ps_string(text)
        self.assertIn("''", escaped)
        self.assertIn("``", escaped)
        self.assertIn("`$", escaped)

    @patch("subprocess.run")
    def test_send_windows_toast_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        with patch("sys.platform", "win32"):
            ok = send_windows_toast("Titre", "Message de test")
            self.assertTrue(ok)
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            self.assertEqual(args[0][0], "powershell")
            # Vérification du flag CREATE_NO_WINDOW
            self.assertIn("creationflags", kwargs)

    @patch("subprocess.run")
    def test_send_windows_toast_failure(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Permission denied"
        mock_run.return_value = mock_proc

        with patch("sys.platform", "win32"):
            ok = send_windows_toast("Titre", "Message d'erreur")
            self.assertFalse(ok)

    @patch("subprocess.run", side_effect=Exception("Subprocess timeout"))
    def test_send_windows_toast_exception_graceful(self, mock_run):
        with patch("sys.platform", "win32"):
            ok = send_windows_toast("Titre", "Timeout test")
            self.assertFalse(ok)

    @patch("subprocess.run")
    def test_send_macos_notification(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        ok = send_macos_notification("Titre", "Message")
        self.assertTrue(ok)
        mock_run.assert_called_once()
        self.assertEqual(mock_run.call_args[0][0][0], "osascript")

    @patch("shutil.which", return_value="/usr/bin/notify-send")
    @patch("subprocess.run")
    def test_send_linux_notification(self, mock_run, mock_which):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        ok = send_linux_notification("Titre", "Message")
        self.assertTrue(ok)
        mock_run.assert_called_once()

    @patch("core.notifications.send_windows_toast", return_value=True)
    def test_notify_transcription_complete(self, mock_toast):
        with patch("sys.platform", "win32"):
            ok = notify_transcription_complete(
                filename="interview.mp3",
                elapsed_seconds=10.0,
                audio_duration=60.0,
                sound=False
            )
            self.assertTrue(ok)
            mock_toast.assert_called_once()
            _, kwargs = mock_toast.call_args
            # mock_toast(title, message)
            call_title = mock_toast.call_args[0][0]
            call_msg = mock_toast.call_args[0][1]
            self.assertIn("LocalScribe", call_title)
            self.assertIn("interview.mp3", call_msg)
            self.assertIn("6.0x", call_msg)

    @patch("core.notifications.send_windows_toast", return_value=True)
    def test_notify_batch_complete(self, mock_toast):
        with patch("sys.platform", "win32"):
            ok = notify_batch_complete(
                total_files=5,
                elapsed_seconds=75.0,
                sound=False
            )
            self.assertTrue(ok)
            mock_toast.assert_called_once()
            call_msg = mock_toast.call_args[0][1]
            self.assertIn("5 fichier(s)", call_msg)
            self.assertIn("1 min 15s", call_msg)

    @patch("winsound.MessageBeep", create=True)
    def test_play_chime_does_not_crash(self, mock_beep):
        with patch("sys.platform", "win32"):
            play_chime()
            # Non bloquant, s'exécute sans exception


if __name__ == "__main__":
    unittest.main()
