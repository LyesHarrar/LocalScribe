import os
import unittest
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.visual_extractor import (
    VisualKeyframe,
    is_video_file,
    sanitize_slug,
    format_time_slug,
    detect_visual_moments_heuristic,
    detect_visual_moments_ai,
    extract_keyframe_image,
    generate_illustrated_markdown,
    create_captures_zip_bytes,
    process_video_visuals
)
from core.text_formatter import TranscriptionSegment


class DummySegment:
    def __init__(self, start, end, text, speaker=None):
        self.start = start
        self.end = end
        self.text = text
        self.speaker = speaker


class TestVisualExtractor(unittest.TestCase):
    def test_is_video_file(self):
        self.assertTrue(is_video_file("video.mp4"))
        self.assertTrue(is_video_file("path/to/movie.mkv"))
        self.assertTrue(is_video_file(Path("conference.mov")))
        self.assertTrue(is_video_file("screen.webm"))
        self.assertFalse(is_video_file("audio.mp3"))
        self.assertFalse(is_video_file("podcast.wav"))
        self.assertFalse(is_video_file(""))

    def test_sanitize_slug(self):
        self.assertEqual(sanitize_slug("Schéma d'Architecture & Cloud!"), "schema_darchitecture_cloud")
        self.assertEqual(sanitize_slug("Matrice SWOT / Eisenhower"), "matrice_swot_eisenhower")
        self.assertEqual(sanitize_slug(""), "capture")
        self.assertEqual(sanitize_slug("   "), "capture")

    def test_format_time_slug(self):
        self.assertEqual(format_time_slug(15.0), "00m15s")
        self.assertEqual(format_time_slug(255.4), "04m15s")
        self.assertEqual(format_time_slug(3665.0), "01h01m05s")

    def test_detect_visual_moments_heuristic_french(self):
        segments = [
            DummySegment(0.0, 5.0, "Bonjour à tous, bienvenue dans ce cours."),
            DummySegment(5.0, 15.0, "Comme vous le voyez sur ce schéma de l'architecture microservices, nous avons 3 couches."),
            DummySegment(15.0, 25.0, "Et voici la matrice de priorisation des tâches."),
            DummySegment(25.0, 30.0, "C'est tout pour aujourd'hui.")
        ]
        moments = detect_visual_moments_heuristic(segments, min_interval_seconds=5.0)
        self.assertEqual(len(moments), 2)
        
        m1 = moments[0]
        self.assertAlmostEqual(m1.timestamp, 10.0)
        self.assertIn("Architecture", m1.title)
        self.assertEqual(m1.time_str, "00:00:10")
        self.assertTrue(m1.image_filename.endswith(".jpg"))

        m2 = moments[1]
        self.assertAlmostEqual(m2.timestamp, 20.0)
        self.assertIn("Matrice", m2.title)

    def test_detect_visual_moments_heuristic_english(self):
        segments = [
            DummySegment(10.0, 20.0, "As you can see on this diagram of the neural network pipeline..."),
            DummySegment(30.0, 40.0, "Look at this table showing our Q3 benchmarks.")
        ]
        moments = detect_visual_moments_heuristic(segments, min_interval_seconds=5.0)
        self.assertEqual(len(moments), 2)
        self.assertIn("Diagram", moments[0].title)
        self.assertIn("Table", moments[1].title)

    def test_detect_visual_moments_de_duplication(self):
        segments = [
            DummySegment(10.0, 14.0, "Regardez ce schéma ici."),
            DummySegment(14.0, 18.0, "Sur ce schéma, on voit le premier bloc."),  # < 12s plus tard
            DummySegment(50.0, 55.0, "Passons maintenant à ce graphique des ventes.")
        ]
        moments = detect_visual_moments_heuristic(segments, min_interval_seconds=12.0)
        self.assertEqual(len(moments), 2)

    @patch("core.local_ai_engine.generate_ai_response")
    def test_detect_visual_moments_ai_success(self, mock_ai):
        mock_ai.return_value = {
            "success": True,
            "text": '```json\n[{"timestamp": 45.0, "title": "Architecture Microservices", "context": "Sur ce schéma..."}]\n```'
        }
        segments = [DummySegment(40.0, 50.0, "Sur ce schéma nous détaillons l'architecture...")]
        moments = detect_visual_moments_ai(segments)
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0].title, "Architecture Microservices")
        self.assertEqual(moments[0].source, "ai")
        self.assertEqual(moments[0].timestamp, 45.0)

    @patch("core.local_ai_engine.generate_ai_response")
    def test_detect_visual_moments_ai_fallback(self, mock_ai):
        # En cas d'erreur IA ou JSON invalide, repli heuristique automatique
        mock_ai.return_value = {
            "success": False,
            "error": "Ollama indisponible"
        }
        segments = [DummySegment(10.0, 20.0, "Comme vous le voyez sur ce schéma de l'infrastructure.")]
        moments = detect_visual_moments_ai(segments)
        self.assertEqual(len(moments), 1)
        self.assertEqual(moments[0].source, "heuristic")
        self.assertIn("Schéma", moments[0].title)

    def test_visual_keyframe_dataclass_serialization(self):
        kf = VisualKeyframe(
            timestamp=125.5,
            time_str="02:05",
            title="Schéma Flux",
            slug="schema_flux",
            context="Regardez ce schéma de flux",
            image_path="C:/tmp/img.jpg",
            image_filename="02m05s_schema_flux.jpg",
            confidence=0.9,
            source="heuristic"
        )
        d = kf.to_dict()
        self.assertEqual(d["timestamp"], 125.5)
        self.assertEqual(d["title"], "Schéma Flux")

        restored = VisualKeyframe.from_dict(d)
        self.assertEqual(restored.timestamp, kf.timestamp)
        self.assertEqual(restored.title, kf.title)
        self.assertEqual(restored.image_path, kf.image_path)

    @patch("core.visual_extractor.subprocess.run")
    def test_extract_keyframe_image_mock(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_img = Path(tmp_dir) / "test.jpg"
            # Simuler la création du fichier par FFmpeg
            def side_effect(cmd, **kwargs):
                out_img.write_bytes(b"\xFF\xD8\xFF\xE0FakeJPEGData")
                mock_res = MagicMock()
                mock_res.returncode = 0
                return mock_res

            mock_run.side_effect = side_effect

            success = extract_keyframe_image(
                video_path="fake_video.mp4",
                timestamp=42.5,
                output_path=out_img,
                ffmpeg_exe="fake_ffmpeg.exe"
            )
            self.assertTrue(success)
            self.assertTrue(out_img.is_file())
            self.assertGreater(out_img.stat().st_size, 0)

            # Vérifier les arguments de ligne de commande passés à FFmpeg
            args, kwargs = mock_run.call_args
            cmd_called = args[0]
            self.assertEqual(cmd_called[0], "fake_ffmpeg.exe")
            self.assertIn("-ss", cmd_called)
            self.assertIn("42.500", cmd_called)
            self.assertIn("-vframes", cmd_called)
            self.assertIn("1", cmd_called)

    def test_generate_illustrated_markdown(self):
        segments = [
            TranscriptionSegment(start=0.0, end=4.0, text="Introduction à la conférence.", speaker="Alice"),
            TranscriptionSegment(start=4.0, end=10.0, text="Comme vous le voyez sur ce schéma de flux.", speaker="Alice"),
            TranscriptionSegment(start=10.0, end=15.0, text="Conclusion de la session.", speaker="Bob")
        ]
        kf = VisualKeyframe(
            timestamp=7.0,
            time_str="00:00:07",
            title="Schéma Flux",
            slug="schema_flux",
            context="Comme vous le voyez sur ce schéma de flux.",
            image_path="C:/test/captures/00m07s_schema_flux.jpg",
            image_filename="00m07s_schema_flux.jpg"
        )
        meta = {
            "filename": "webinar.mp4",
            "duration": 15.0,
            "language": "fr"
        }
        md = generate_illustrated_markdown(segments, meta, [kf], captures_relative_dir="captures_webinar")
        self.assertIn("Transcription Illustrée de webinar.mp4", md)
        self.assertIn("visual_captures_count: 1", md)
        self.assertIn("![Schéma Flux](captures_webinar/00m07s_schema_flux.jpg)", md)
        self.assertIn("> 🖼️ **[00:00:07] Schéma / Slide : Schéma Flux**", md)

    def test_create_captures_zip_bytes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p1 = Path(tmp_dir) / "img1.jpg"
            p2 = Path(tmp_dir) / "img2.jpg"
            p1.write_bytes(b"JPEG1")
            p2.write_bytes(b"JPEG2")

            kf1 = VisualKeyframe(timestamp=1.0, time_str="00:01", title="A", slug="a", context="c1", image_path=str(p1), image_filename="img1.jpg")
            kf2 = VisualKeyframe(timestamp=5.0, time_str="00:05", title="B", slug="b", context="c2", image_path=str(p2), image_filename="img2.jpg")

            zip_bytes = create_captures_zip_bytes([kf1, kf2])
            self.assertGreater(len(zip_bytes), 0)

            # Vérifier l'intégrité du ZIP
            import io
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                names = zf.namelist()
                self.assertIn("img1.jpg", names)
                self.assertIn("img2.jpg", names)

    def test_process_video_visuals_non_video_skipped(self):
        keyframes, folder = process_video_visuals("audio.mp3", [DummySegment(0, 5, "sur ce schéma")])
        self.assertEqual(keyframes, [])
        self.assertIsNone(folder)


if __name__ == "__main__":
    unittest.main()
