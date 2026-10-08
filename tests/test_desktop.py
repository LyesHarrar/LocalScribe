"""
tests/test_desktop.py — Tests unitaires pour la couche Desktop et le packaging portable (Phases 3 & v1.4)
"""

import sys
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from desktop.run_app import (
    find_available_port,
    check_webview_dependencies,
    wait_for_server,
    cleanup_server,
    get_python_executable,
)
from desktop.launcher import (
    find_python_executable,
    show_error_dialog,
)
from desktop.package_portable import (
    create_batch_launcher,
    create_readme,
    get_copy_filter,
)


class TestDesktop(unittest.TestCase):

    def test_find_available_port_default(self):
        """Vérifie que la fonction renvoie un port valide (> 1024)."""
        port = find_available_port(8501)
        self.assertIsInstance(port, int)
        self.assertGreater(port, 1024)

    def test_find_available_port_when_occupied(self):
        """Vérifie qu'un port dynamique est alloué si le port préféré est déjà occupé."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            _, occupied_port = s.getsockname()
            s.listen(1)
            
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
        
        with patch("subprocess.run"):
            cleanup_server(mock_proc)
            self.assertTrue(mock_proc.terminate.called)


class TestLauncher(unittest.TestCase):
    """Tests unitaires pour le Bootstrap Launcher LocalScribe.exe."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_find_python_executable_portable_pythonw(self):
        """Vérifie la priorité absolue de python/pythonw.exe."""
        py_dir = self.app_dir / "python"
        py_dir.mkdir()
        mock_exe = py_dir / "pythonw.exe"
        mock_exe.touch()

        found = find_python_executable(self.app_dir)
        self.assertEqual(Path(found).resolve(), mock_exe.resolve())

    def test_find_python_executable_portable_python_fallback(self):
        """Vérifie que python/python.exe est détecté si pythonw n'existe pas."""
        py_dir = self.app_dir / "python"
        py_dir.mkdir()
        mock_exe = py_dir / "python.exe"
        mock_exe.touch()

        found = find_python_executable(self.app_dir)
        self.assertEqual(Path(found).resolve(), mock_exe.resolve())

    def test_find_python_executable_dev_mode(self):
        """En mode dev (sans python/ portable), retourne sys.executable."""
        found = find_python_executable(self.app_dir)
        self.assertEqual(found, sys.executable)

    @patch("shutil.which", return_value=None)
    def test_find_python_executable_not_found(self, mock_which):
        """Vérifie qu'une chaîne vide est renvoyée si aucun Python n'est disponible."""
        with patch("sys.executable", None):
            with patch.object(sys, "frozen", True, create=True):
                with patch.dict("os.environ", {"LOCALAPPDATA": "", "ProgramFiles": "", "ProgramFiles(x86)": ""}):
                    found = find_python_executable(self.app_dir)
                    self.assertEqual(found, "")

    @patch("ctypes.windll.user32.MessageBoxW", return_value=1)
    def test_show_error_dialog(self, mock_msgbox):
        """Vérifie que show_error_dialog appelle MessageBoxW sur Windows sans crash."""
        with patch("sys.platform", "win32"):
            show_error_dialog("Titre Test", "Message Test")
            mock_msgbox.assert_called_once()


class TestRunAppPythonResolution(unittest.TestCase):
    """Tests unitaires pour la détection de Python dans run_app."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_python_executable_portable(self):
        """Vérifie que get_python_executable détecte python/python.exe portable."""
        py_dir = self.root_dir / "python"
        py_dir.mkdir()
        mock_exe = py_dir / "python.exe"
        mock_exe.touch()

        with patch("desktop.run_app.get_project_root", return_value=self.root_dir):
            with patch("sys.platform", "win32"):
                result = get_python_executable()
                self.assertEqual(Path(result).resolve(), mock_exe.resolve())


class TestPortablePackager(unittest.TestCase):
    """Tests unitaires pour les fonctions de packaging portable."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.target_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_batch_launcher(self):
        """Vérifie la génération du script batch de lancement."""
        bat_file = create_batch_launcher(self.target_dir)
        self.assertTrue(bat_file.exists())
        content = bat_file.read_text(encoding="utf-8")
        self.assertIn("LocalScribe.exe", content)
        self.assertIn("python\\pythonw.exe", content)
        self.assertIn("desktop\\run_app.py", content)

    def test_create_readme(self):
        """Vérifie la génération du fichier d'instructions README-PORTABLE.txt."""
        readme = create_readme(self.target_dir, is_cpu_only=True)
        self.assertTrue(readme.exists())
        content = readme.read_text(encoding="utf-8")
        self.assertIn("LocalScribe.exe", content)
        self.assertIn("100 % LOCAL", content)
        self.assertIn("CPU (Optimisé multi-cœurs)", content)
        self.assertIn("LICENSES-THIRD-PARTY.txt", content)
        self.assertIn("FFmpeg", content)

    def test_batch_launcher_injects_bin_path(self):
        """Vérifie que Lancer-LocalScribe.bat injecte bin/ dans le PATH."""
        bat_file = create_batch_launcher(self.target_dir)
        content = bat_file.read_text(encoding="utf-8")
        self.assertIn("set \"PATH=%~dp0bin;%PATH%\"", content)

    def test_package_structure_and_licenses(self):
        """Vérifie la présence des fichiers de licence à la racine du projet."""
        project_root = Path(__file__).resolve().parent.parent
        self.assertTrue((project_root / "LICENSE").is_file(), "LICENSE doit exister")
        self.assertTrue((project_root / "LICENSES-THIRD-PARTY.txt").is_file(), "LICENSES-THIRD-PARTY.txt doit exister")
        self.assertTrue((project_root / "bin" / ".gitkeep").is_file(), "bin/.gitkeep doit exister")
        self.assertTrue((project_root / "models" / ".gitkeep").is_file(), "models/.gitkeep doit exister")

    def test_get_copy_filter_standard(self):
        """Vérifie que le filtre ignore __pycache__, .pyc et les dossiers de doc."""
        src_root = Path("C:/fake/python")
        filter_func = get_copy_filter(src_root, cpu_only=False)

        names = ["__pycache__", "script.pyc", "script.py", "Doc", "include", "normal_folder"]
        ignored = filter_func("C:/fake/python", names)
        
        self.assertIn("__pycache__", ignored)
        self.assertIn("script.pyc", ignored)
        self.assertIn("doc", {x.lower() for x in ignored})
        self.assertIn("include", {x.lower() for x in ignored})
        self.assertNotIn("script.py", ignored)
        self.assertNotIn("normal_folder", ignored)

    def test_get_copy_filter_cpu_only(self):
        """Vérifie que le mode cpu-only filtre les packages nvidia."""
        src_root = Path("C:/fake/python")
        filter_func = get_copy_filter(src_root, cpu_only=True)

        names = ["nvidia", "nvidia_cublas", "faster_whisper", "streamlit"]
        ignored = filter_func("C:/fake/python/Lib/site-packages", names)

        self.assertIn("nvidia", ignored)
        self.assertIn("nvidia_cublas", ignored)
        self.assertNotIn("faster_whisper", ignored)
        self.assertNotIn("streamlit", ignored)


if __name__ == "__main__":
    unittest.main()
