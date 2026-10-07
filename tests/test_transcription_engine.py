import sys
import unittest
import threading
import queue
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Mock imageio_ffmpeg avant l'import
mock_imageio = MagicMock()
mock_imageio.get_ffmpeg_exe.return_value = "/mock/ffmpeg"
sys.modules['imageio_ffmpeg'] = mock_imageio

from core.hardware_profiler import HardwareProfile
from core.transcription_engine import transcribe_file_threaded, transcribe_batch_threaded

class TestTranscriptionEngine(unittest.TestCase):

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_threaded_success(self, mock_whisper_class):
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 10.0
            language = "fr"
            
        class DummySegment:
            start = 0.0
            end = 5.0
            text = "Hello world"
            
        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_audio = tmp_path / "audio.mp3"
            fake_audio.write_bytes(b"dummy audio content")
            out_dir = tmp_path / "output"
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_file_threaded(
                file_path=fake_audio,
                output_dir=out_dir,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event
            )
            
            messages = []
            while not q.empty():
                messages.append(q.get())
                
            self.assertEqual(messages[0]["status"], "loading_model")
            self.assertEqual(messages[1]["status"], "starting")
            self.assertEqual(messages[2]["status"], "progress")
            self.assertEqual(messages[2]["percentage"], 50.0)
            self.assertEqual(messages[3]["status"], "file_complete")
            
            # Vérification de la création effective des fichiers
            self.assertTrue((out_dir / "audio.txt").exists())
            self.assertTrue((out_dir / "audio.md").exists())
            self.assertTrue((out_dir / "audio.srt").exists())
            self.assertIn("Hello world", (out_dir / "audio.txt").read_text(encoding="utf-8"))

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_threaded_stopped(self, mock_whisper_class):
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 10.0
            language = "fr"
            
        class DummySegment:
            end = 5.0
            text = "Hello"
            
        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_audio = Path(tmp_dir) / "audio.mp3"
            fake_audio.write_bytes(b"dummy")
            
            q = queue.Queue()
            stop_event = threading.Event()
            stop_event.set() # Arrêt immédiat
            
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_file_threaded(
                file_path=fake_audio,
                output_dir=Path(tmp_dir),
                profile=profile,
                progress_queue=q,
                stop_event=stop_event
            )
            
            messages = []
            while not q.empty():
                messages.append(q.get())
                
            self.assertEqual(messages[-1]["status"], "stopped")

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_batch_threaded(self, mock_whisper_class):
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 15.0
            language = "fr"
            
        class DummySegment:
            end = 15.0
            text = "Batch text transcription"
            
        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sub = root / "subfolder"
            sub.mkdir()
            
            # Deux fichiers vidéo simulés
            v1 = root / "video1.mp4"
            v2 = sub / "video2.mkv"
            v1.write_bytes(b"fake video 1")
            v2.write_bytes(b"fake video 2")
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_batch_threaded(
                target_dir=root,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event
            )
            
            messages = []
            while not q.empty():
                messages.append(q.get())
                
            statuses = [m["status"] for m in messages]
            self.assertIn("batch_discovered", statuses)
            self.assertIn("file_complete", statuses)
            self.assertIn("batch_complete", statuses)
            
            # Vérification que les fichiers .txt sont créés dans le même dossier que chaque vidéo
            txt1 = root / "video1.txt"
            txt2 = sub / "video2.txt"
            self.assertTrue(txt1.exists(), "video1.txt doit être créé à côté de video1.mp4")
            self.assertTrue(txt2.exists(), "video2.txt doit être créé à côté de video2.mkv")
            self.assertIn("Batch text transcription", txt1.read_text(encoding="utf-8"))
            self.assertIn("Batch text transcription", txt2.read_text(encoding="utf-8"))

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_batch_smart_resume(self, mock_whisper_class):
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            v1 = root / "video_already_done.mp4"
            txt1 = root / "video_already_done.txt"
            v1.write_bytes(b"fake video")
            txt1.write_text("Transcription existante", encoding="utf-8")
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_batch_threaded(
                target_dir=root,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event
            )
            
            messages = []
            while not q.empty():
                messages.append(q.get())
                
            statuses = [m["status"] for m in messages]
            self.assertIn("file_skipped", statuses)
            # Whisper ne doit même pas avoir été appelé
            mock_model.transcribe.assert_not_called()

if __name__ == "__main__":
    unittest.main()
