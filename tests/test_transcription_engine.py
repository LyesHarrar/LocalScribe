import sys
import unittest
import threading
import queue
from pathlib import Path
from unittest.mock import patch, MagicMock

# Mock imageio_ffmpeg and faster_whisper avant l'import
mock_imageio = MagicMock()
mock_imageio.get_ffmpeg_exe.return_value = "/mock/ffmpeg"
sys.modules['imageio_ffmpeg'] = mock_imageio
sys.modules['faster_whisper'] = MagicMock()

from core.hardware_profiler import HardwareProfile
from core.transcription_engine import transcribe_file_threaded

class TestTranscriptionEngine(unittest.TestCase):
    
    @patch("core.transcription_engine.WhisperModel")
    @patch("core.transcription_engine.generate_markdown")
    @patch("core.transcription_engine.generate_srt")
    @patch("pathlib.Path.write_text")
    @patch("pathlib.Path.rename")
    @patch("pathlib.Path.mkdir")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.unlink")
    def test_transcribe_file_threaded_success(self, mock_unlink, mock_exists, mock_mkdir, mock_rename, mock_write, mock_gen_srt, mock_gen_md, mock_whisper_class):
        mock_exists.return_value = False
        
        # Mock Whisper behavior
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 10.0
            language = "fr"
            
        class DummySegment:
            end = 5.0
            text = "Hello"
            
        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())
        
        q = queue.Queue()
        stop_event = threading.Event()
        
        profile = HardwareProfile("cpu", "int8", "small")
        
        transcribe_file_threaded(
            file_path=Path("test.mp3"),
            output_dir=Path("out"),
            profile=profile,
            progress_queue=q,
            stop_event=stop_event
        )
        
        # Verify queue messages
        messages = []
        while not q.empty():
            messages.append(q.get())
            
        self.assertEqual(messages[0]["status"], "loading_model")
        self.assertEqual(messages[1]["status"], "starting")
        self.assertEqual(messages[2]["status"], "progress")
        self.assertEqual(messages[2]["percentage"], 50.0)
        self.assertEqual(messages[3]["status"], "file_complete")
        
        # Verify atomic operations (tmp written then renamed)
        self.assertEqual(mock_write.call_count, 2)
        self.assertEqual(mock_rename.call_count, 2)

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_threaded_stopped(self, mock_whisper_class):
        # Mock Whisper behavior
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 10.0
            language = "fr"
            
        class DummySegment:
            end = 5.0
            text = "Hello"
            
        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())
        
        q = queue.Queue()
        stop_event = threading.Event()
        stop_event.set() # Interruption immédiate
        
        profile = HardwareProfile("cpu", "int8", "small")
        
        transcribe_file_threaded(
            file_path=Path("test.mp3"),
            output_dir=Path("out"),
            profile=profile,
            progress_queue=q,
            stop_event=stop_event
        )
        
        messages = []
        while not q.empty():
            messages.append(q.get())
            
        self.assertEqual(messages[-1]["status"], "stopped")

if __name__ == "__main__":
    unittest.main()
