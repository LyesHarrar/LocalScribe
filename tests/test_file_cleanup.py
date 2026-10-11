"""
tests/test_file_cleanup.py — Tests unitaires pour la Corbeille Windows et le nettoyage de fichiers
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.file_cleanup import send_to_recycle_bin, get_folder_media_stats


class TestFileCleanup(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_send_to_recycle_bin_empty(self):
        """Vérifie qu'une liste vide renvoie (0, 0) sans erreur."""
        success, failed = send_to_recycle_bin([])
        self.assertEqual(success, 0)
        self.assertEqual(failed, 0)

    def test_send_to_recycle_bin_non_existent(self):
        """Vérifie que les fichiers inexistants sont ignorés sans crash."""
        fake_path = self.root / "inexistant.mp4"
        success, failed = send_to_recycle_bin([fake_path])
        self.assertEqual(success, 0)
        self.assertEqual(failed, 0)

    def test_send_to_recycle_bin_real_files(self):
        """Vérifie le déplacement réel de fichiers vers la Corbeille sous Windows."""
        f1 = self.root / "video1.mp4"
        f2 = self.root / "video2.mkv"
        f1.write_bytes(b"dummy video content 1")
        f2.write_bytes(b"dummy video content 2")
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())

        success, failed = send_to_recycle_bin([f1, f2])
        self.assertEqual(success, 2)
        self.assertEqual(failed, 0)
        self.assertFalse(f1.exists())
        self.assertFalse(f2.exists())

    def test_get_folder_media_stats_categorization(self):
        """Vérifie l'analyse récursive, le calcul des tailles et la distinction déjà transcrit vs restant."""
        sub = self.root / "formation" / "module1"
        sub.mkdir(parents=True, exist_ok=True)

        # Vidéo 1 : Transcrite (possède un .txt non vide)
        v1 = sub / "cours1.mp4"
        v1.write_bytes(b"0" * 1024 * 1024)  # 1 Mo
        txt1 = sub / "cours1.txt"
        txt1.write_text("Transcription du cours 1", encoding="utf-8")

        # Vidéo 2 : Non transcrite
        v2 = sub / "cours2.mp4"
        v2.write_bytes(b"0" * (2 * 1024 * 1024))  # 2 Mo

        # Fichier non supporté
        img = sub / "slide.png"
        img.write_bytes(b"png")

        # Fichier temporaire opt
        opt = sub / "ls_opt_temp.wav"
        opt.write_bytes(b"wav")

        stats = get_folder_media_stats(self.root, {".mp4", ".mkv"})

        self.assertEqual(stats["total_found"], 2)
        self.assertEqual(stats["already_done_count"], 1)
        self.assertEqual(stats["remaining_count"], 1)
        self.assertEqual(len(stats["already_done_files"]), 1)
        self.assertEqual(stats["already_done_files"][0].name, "cours1.mp4")
        self.assertEqual(stats["remaining_files"][0].name, "cours2.mp4")
        self.assertAlmostEqual(stats["total_size_mb"], 3.0, delta=0.2)
        self.assertAlmostEqual(stats["already_done_size_mb"], 1.0, delta=0.2)
        self.assertAlmostEqual(stats["remaining_size_mb"], 2.0, delta=0.2)

    def test_get_folder_media_stats_non_existent_folder(self):
        """Vérifie le retour gracieux si le dossier n'existe pas."""
        stats = get_folder_media_stats(self.root / "dossier_fantome", {".mp4"})
        self.assertEqual(stats["total_found"], 0)
        self.assertEqual(stats["already_done_count"], 0)
        self.assertEqual(stats["remaining_count"], 0)


if __name__ == "__main__":
    unittest.main()
