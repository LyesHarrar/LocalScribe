"""
tests/test_desktop.py — Tests unitaires pour la couche Desktop (Phase 3)
"""

import sys
import socket
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from desktop.run_app import (
    find_available_port,
    check_webview_dependencies,
    wait_for_server,
    cleanup_server
)


class TestDesktop(unittest.TestCase):

    def test_find_available_port_default(self):
        """Vérifie que la fonction renvoie un port valide (> 1024)."""
        port = find_available_port(8501)
        self.assertIsInstance(port, int)
        self.assertGreater(port, 1024)

    def test_find_available_port_when_occupied(self):
        """Vérifie qu'un port dynamique est alloué si le port préféré est déjà occupé."""
        # Créer un socket qui occupe un port temporaire
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, occupied_port = s.getsockname()
            s.listen(1)
            
            # Tenter d'allouer ce port occupé
            free_port = find_available_port(occupied_port)
            self.assertNotEqual(free_port, occupied_port)
            self.assertGreater(free_port, 1024)

    @patch("desktop.run_app.sys")
    def test_check_webview_dependencies_windows_success(self, mock_sys):
        """Vérifie la détection réussie sur Windows."""
        mock_sys.platform = "win32"
        with patch("webview.platforms.winforms._is_chromium", return_value=True):
            self.assertTrue(check_webview_dependencies())

    @patch("desktop.run_app.sys")
    @patch("desktop.run_app.logger")
    def test_check_webview_dependencies_missing_fallback(self, mock_logger, mock_sys):
        """Vérifie le repli gracieux sans crash si WebView2 est absent."""
        mock_sys.platform = "win32"
        with patch("webview.platforms.winforms._is_chromium", side_effect=Exception("Missing")):
            with patch("tkinter.Tk", side_effect=Exception("No GUI")):
                result = check_webview_dependencies()
                self.assertFalse(result)

    @patch("urllib.request.urlopen")
    def test_wait_for_server_success(self, mock_urlopen):
        """Vérifie que wait_for_server réussit dès que le serveur renvoie HTTP 200."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        
        self.assertTrue(wait_for_server(port=9999, timeout=2.0))

    @patch("urllib.request.urlopen")
    def test_wait_for_server_timeout(self, mock_urlopen):
        """Vérifie le comportement en cas de timeout."""
        mock_urlopen.side_effect = Exception("Connection refused")
        
        self.assertFalse(wait_for_server(port=9999, timeout=0.5))

    def test_cleanup_server_none(self):
        """Vérifie que cleanup_server ne lève aucune exception si le processus est None."""
        try:
            cleanup_server(None)
        except Exception as e:
            self.fail(f"cleanup_server(None) a levé une exception inattendue : {e}")

    def test_cleanup_server_process(self):
        """Vérifie que cleanup_server tente d'arrêter le processus."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        
        with patch("subprocess.run") as mock_sub:
            cleanup_server(mock_proc)
            self.assertTrue(mock_proc.terminate.called)


if __name__ == "__main__":
    unittest.main()
