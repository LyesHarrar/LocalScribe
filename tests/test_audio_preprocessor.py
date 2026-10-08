"""
tests/test_audio_preprocessor.py — Tests unitaires pour le prétraitement audio et extraction FFmpeg
Valide la détection de FFmpeg, la construction des filtres, la normalisation, le denoising et le nettoyage.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.audio_preprocessor import (
    find_ffmpeg_path,
    is_ffmpeg_available,
    is_video_file,
    build_audio_filter_string,
    preprocess_audio,
    cleanup_preprocessed_file
)


class TestAudioPreprocessor(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_is_video_file(self):
        """Vérifie la distinction entre conteneurs vidéo et fichiers audio."""
        self.assertTrue(is_video_file(Path("film.mp4")))
        self.assertTrue(is_video_file(Path("conference.MKV")))
        self.assertTrue(is_video_file(Path("clip.avi")))
        self.assertTrue(is_video_file(Path("web.webm")))

        self.assertFalse(is_video_file(Path("podcast.mp3")))
        self.assertFalse(is_video_file(Path("interview.wav")))
        self.assertFalse(is_video_file(Path("audio.m4a")))
        self.assertFalse(is_video_file(Path("transcription.txt")))

    def test_build_audio_filter_string(self):
        """Vérifie la construction correcte des chaînes de filtres FFmpeg."""
        # 1. Normalisation seule
        f_norm = build_audio_filter_string(normalize_volume=True, denoise=False)
        self.assertIn("dynaudnorm", f_norm)
        self.assertNotIn("highpass", f_norm)

        # 2. Denoising seul
        f_denoise = build_audio_filter_string(normalize_volume=False, denoise=True)
        self.assertIn("highpass=f=80", f_denoise)
        self.assertIn("lowpass=f=8000", f_denoise)
        self.assertIn("afftdn=nf=-25", f_denoise)
        self.assertNotIn("dynaudnorm", f_denoise)

        # 3. Les deux combinés (ordre optimal : denoising puis normalisation)
        f_both = build_audio_filter_string(normalize_volume=True, denoise=True)
        self.assertIn("highpass=f=80", f_both)
        self.assertIn("dynaudnorm", f_both)
        # Vérifier que le highpass précède dynaudnorm
        self.assertLess(f_both.find("highpass"), f_both.find("dynaudnorm"))

        # 4. Aucun filtre
        f_none = build_audio_filter_string(normalize_volume=False, denoise=False)
        self.assertEqual(f_none, "")

    @patch("core.audio_preprocessor.find_ffmpeg_path")
    def test_preprocess_fallback_when_ffmpeg_missing(self, mock_find):
        """Vérifie le repli gracieux et transparent si FFmpeg n'est pas présent."""
        mock_find.return_value = None

        fake_file = self.tmp_path / "test_audio.mp3"
        fake_file.write_bytes(b"dummy audio data")

        status_msgs = []
        out_path, meta = preprocess_audio(
            fake_file,
            normalize_volume=True,
            status_callback=lambda m: status_msgs.append(m)
        )

        self.assertEqual(out_path, fake_file)
        self.assertFalse(meta["preprocessed"])
        self.assertEqual(meta["reason"], "ffmpeg_not_available")
        self.assertIn("FFmpeg non détecté", status_msgs[0])

    def test_cleanup_preprocessed_file(self):
        """Vérifie que seul le fichier temporaire prétraité est supprimé, jamais le fichier source."""
        orig_file = self.tmp_path / "original.mp3"
        orig_file.write_bytes(b"source content")

        temp_prep = self.tmp_path / "ls_opt_123_original.wav"
        temp_prep.write_bytes(b"temp wav content")

        # 1. Nettoyage du fichier temporaire
        cleanup_preprocessed_file(temp_prep, orig_file)
        self.assertFalse(temp_prep.exists())
        self.assertTrue(orig_file.exists())

        # 2. Si on tente de nettoyer avec orig_file == prep_p, il ne doit PAS être supprimé
        cleanup_preprocessed_file(orig_file, orig_file)
        self.assertTrue(orig_file.exists())

    def test_preprocess_real_ffmpeg_if_installed(self):
        """Si FFmpeg est installé sur le système, teste la conversion réelle d'un court extrait audio."""
        if not is_ffmpeg_available():
            self.skipTest("FFmpeg n'est pas disponible dans cet environnement de test.")

        # Créer un fichier audio de synthèse via ffmpeg (1 seconde de tonalité sinusoïdale 440Hz)
        ffmpeg_bin = find_ffmpeg_path()
        synth_file = self.tmp_path / "sine_input.mp4"

        import subprocess
        subprocess.run(
            [ffmpeg_bin, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(synth_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.assertTrue(synth_file.exists())

        # Exécuter le prétraitement complet avec normalisation et denoising
        out_path, meta = preprocess_audio(
            synth_file,
            output_dir=self.tmp_path,
            normalize_volume=True,
            denoise=True
        )

        self.assertTrue(meta["preprocessed"])
        self.assertTrue(out_path.exists())
        self.assertNotEqual(out_path, synth_file)
        self.assertEqual(out_path.suffix, ".wav")
        self.assertGreater(out_path.stat().st_size, 0)

        # Nettoyage
        cleanup_preprocessed_file(out_path, synth_file)
        self.assertFalse(out_path.exists())
        self.assertTrue(synth_file.exists())


if __name__ == "__main__":
    unittest.main()
