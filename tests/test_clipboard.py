"""
tests/test_clipboard.py — Tests unitaires pour le module de presse-papier multi-plateforme (core/clipboard.py)
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

from core.clipboard import (
    copy_to_clipboard,
    copy_windows_ctypes
)


class TestClipboard(unittest.TestCase):

    def test_copy_empty_text(self):
        """Vérifie qu'une chaîne vide renvoie False sans lever d'exception."""
        self.assertFalse(copy_to_clipboard(""))
        self.assertFalse(copy_to_clipboard(None))

    def test_copy_windows_ctypes_native(self):
        """Vérifie le fonctionnement de l'API ctypes sur Windows."""
        if sys.platform == "win32":
            sample_text = "Test LocalScribe Win32 ctypes clipboard"
            res = copy_windows_ctypes(sample_text)
            self.assertTrue(res)

    @patch("pyperclip.copy")
    def test_copy_pyperclip_success(self, mock_pyperclip):
        """Vérifie que pyperclip est prioritaire et renvoie True."""
        mock_pyperclip.return_value = None
        self.assertTrue(copy_to_clipboard("Test avec pyperclip"))
        mock_pyperclip.assert_called_once_with("Test avec pyperclip")

    @patch("pyperclip.copy", side_effect=Exception("Pyperclip error"))
    @patch("core.clipboard.copy_windows_ctypes", return_value=True)
    def test_copy_pyperclip_fail_fallback_ctypes(self, mock_ctypes, mock_pyperclip):
        """Vérifie le repli sur ctypes Windows en cas d'erreur de pyperclip."""
        with patch("sys.platform", "win32"):
            res = copy_to_clipboard("Test repli ctypes")
            self.assertTrue(res)
            mock_ctypes.assert_called_once_with("Test repli ctypes")

    @patch("pyperclip.copy", side_effect=Exception("Pyperclip error"))
    @patch("subprocess.run")
    def test_copy_darwin_fallback(self, mock_sub, mock_pyperclip):
        """Vérifie le repli sur pbcopy sous macOS."""
        with patch("sys.platform", "darwin"):
            mock_sub.return_value = MagicMock(returncode=0)
            res = copy_to_clipboard("Test macOS pbcopy")
            self.assertTrue(res)
            mock_sub.assert_called_once()
            self.assertEqual(mock_sub.call_args[0][0], ["pbcopy"])

    @patch("pyperclip.copy", side_effect=Exception("Pyperclip error"))
    @patch("subprocess.run")
    def test_copy_linux_fallback(self, mock_sub, mock_pyperclip):
        """Vérifie le repli sur wl-copy sous Linux."""
        with patch("sys.platform", "linux"):
            mock_sub.return_value = MagicMock(returncode=0)
            res = copy_to_clipboard("Test Linux wl-copy")
            self.assertTrue(res)
            mock_sub.assert_called_once()
            self.assertEqual(mock_sub.call_args[0][0], ["wl-copy"])

    @patch("pyperclip.copy", side_effect=Exception("Pyperclip error"))
    @patch("core.clipboard.copy_windows_ctypes", return_value=False)
    @patch("subprocess.run")
    def test_copy_windows_powershell_fallback(self, mock_sub, mock_ctypes, mock_pyperclip):
        """Vérifie le repli sur PowerShell sur Windows si ctypes échoue."""
        with patch("sys.platform", "win32"):
            mock_sub.return_value = MagicMock(returncode=0)
            res = copy_to_clipboard("Test PowerShell fallback")
            self.assertTrue(res)
            mock_sub.assert_called_once()
            self.assertIn("powershell", mock_sub.call_args[0][0][0])


if __name__ == "__main__":
    unittest.main()
