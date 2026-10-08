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
            self.assertEqual(messages[2]["status"], "info_detected")
            self.assertEqual(messages[2]["language"], "fr")
            self.assertEqual(messages[3]["status"], "progress")
            self.assertEqual(messages[3]["percentage"], 50.0)
            self.assertEqual(messages[4]["status"], "file_complete")
            
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

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_with_language_and_task(self, mock_whisper_class):
        """Vérifie que language et task="translate" sont bien transmis à model.transcribe."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 10.0
            language = "es"
            language_probability = 0.98
            
        mock_model.transcribe.return_value = ([], DummyInfo())
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_audio = tmp_path / "audio.mp3"
            fake_audio.write_bytes(b"content")
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_file_threaded(
                file_path=fake_audio,
                output_dir=tmp_path / "out",
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                language="es",
                task="translate"
            )
            
            mock_model.transcribe.assert_called_once()
            _, kwargs = mock_model.transcribe.call_args
            self.assertEqual(kwargs.get("language"), "es")
            self.assertEqual(kwargs.get("task"), "translate")

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_with_prompt_and_vad(self, mock_whisper_class):
        """Vérifie que initial_prompt et vad_filter sont bien transmis."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 5.0
            language = "en"
            language_probability = 0.99
            
        mock_model.transcribe.return_value = ([], DummyInfo())
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_audio = tmp_path / "audio.mp3"
            fake_audio.write_bytes(b"content")
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_file_threaded(
                file_path=fake_audio,
                output_dir=tmp_path / "out",
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                initial_prompt="LocalScribe, Kubernetes",
                vad_filter=False
            )
            
            _, kwargs = mock_model.transcribe.call_args
            self.assertEqual(kwargs.get("initial_prompt"), "LocalScribe, Kubernetes")
            self.assertEqual(kwargs.get("vad_filter"), False)

    @patch("core.diarization_engine.DiarizationEngine")
    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_with_diarization(self, mock_whisper_class, mock_diar_class):
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummySegment:
            def __init__(self, start, end, text):
                self.start = start
                self.end = end
                self.text = text
                
        class DummyInfo:
            duration = 10.0
            language = "fr"
            language_probability = 0.98
            
        mock_model.transcribe.return_value = (
            [
                DummySegment(0.0, 4.0, "Bonjour"),
                DummySegment(4.5, 9.0, "Salut")
            ], 
            DummyInfo()
        )
        
        from core.diarization_engine import DiarizationSegment
        mock_diar_instance = MagicMock()
        mock_diar_class.return_value = mock_diar_instance
        mock_diar_instance.diarize.return_value = [
            DiarizationSegment(0.0, 4.2, 0, "Locuteur 1"),
            DiarizationSegment(4.3, 9.1, 1, "Locuteur 2")
        ]
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_audio = tmp_path / "audio.mp3"
            fake_audio.write_bytes(b"content")
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            out_dir = tmp_path / "out"
            
            transcribe_file_threaded(
                file_path=fake_audio,
                output_dir=out_dir,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                diarize=True,
                num_speakers=2
            )
            
            mock_diar_instance.diarize.assert_called_once()
            _, kwargs = mock_diar_instance.diarize.call_args
            self.assertEqual(kwargs.get("num_speakers"), 2)
            
            messages = []
            while not q.empty():
                messages.append(q.get())
                
            statuses = [m["status"] for m in messages]
            self.assertIn("diarizing", statuses)
            complete_msg = next(m for m in messages if m["status"] == "file_complete")
            self.assertEqual(complete_msg["speakers"], ["Locuteur 1", "Locuteur 2"])
            
            # Vérifier le fichier Markdown généré
            md_file = out_dir / "audio.md"
            self.assertTrue(md_file.exists())
            content = md_file.read_text(encoding="utf-8")
            self.assertIn('speakers: ["Locuteur 1", "Locuteur 2"]', content)
            self.assertIn("**Locuteur 1** : Bonjour", content)
            self.assertIn("**Locuteur 2** : Salut", content)

    @patch("core.diarization_engine.DiarizationEngine")
    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_batch_with_diarization(self, mock_whisper_class, mock_diar_class):
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummySegment:
            def __init__(self, start, end, text):
                self.start = start
                self.end = end
                self.text = text
                
        class DummyInfo:
            duration = 5.0
            language = "fr"
            language_probability = 0.95
            
        mock_model.transcribe.return_value = (
            [DummySegment(0.0, 3.0, "Segment batch")],
            DummyInfo()
        )
        
        from core.diarization_engine import DiarizationSegment
        mock_diar_instance = MagicMock()
        mock_diar_class.return_value = mock_diar_instance
        mock_diar_instance.diarize.return_value = [
            DiarizationSegment(0.0, 3.0, 0, "Locuteur 1")
        ]
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            v1 = root / "video.mp4"
            v1.write_bytes(b"content")
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_batch_threaded(
                target_dir=root,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                diarize=True,
                export_md=True
            )
            
            mock_diar_instance.diarize.assert_called_once()
            
            md_file = root / "video.md"
            self.assertTrue(md_file.exists())
            self.assertIn('speakers: ["Locuteur 1"]', md_file.read_text(encoding="utf-8"))

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_batch_files_queue_success(self, mock_whisper_class):
        """Vérifie le traitement à la chaîne d'une liste explicite de fichiers (file d'attente)."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummySegment:
            def __init__(self, start, end, text):
                self.start = start
                self.end = end
                self.text = text
                
        class DummyInfo:
            duration = 12.0
            language = "fr"
            language_probability = 0.98
            
        mock_model.transcribe.return_value = (
            [DummySegment(0.0, 6.0, "Partie 1"), DummySegment(6.0, 12.0, "Partie 2")],
            DummyInfo()
        )
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f1 = tmp_path / "podcast_ep1.mp3"
            f2 = tmp_path / "podcast_ep2.mp3"
            f3 = tmp_path / "interview.wav"
            for f in (f1, f2, f3):
                f.write_bytes(b"dummy audio")
                
            out_dir = tmp_path / "custom_exports"
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_batch_threaded(
                files=[f1, f2, f3],
                output_dir=out_dir,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                export_srt=True,
                export_md=True
            )
            
            messages = []
            while not q.empty():
                messages.append(q.get())
                
            statuses = [m["status"] for m in messages]
            self.assertIn("batch_discovered", statuses)
            self.assertIn("loading_model", statuses)
            self.assertIn("batch_complete", statuses)
            
            # Vérifier que les 3 fichiers ont été créés dans out_dir
            for name in ("podcast_ep1", "podcast_ep2", "interview"):
                self.assertTrue((out_dir / f"{name}.txt").exists())
                self.assertTrue((out_dir / f"{name}.srt").exists())
                self.assertTrue((out_dir / f"{name}.md").exists())
                self.assertIn("Partie 1", (out_dir / f"{name}.txt").read_text(encoding="utf-8"))
                
            batch_complete_msg = [m for m in messages if m["status"] == "batch_complete"][0]
            self.assertEqual(batch_complete_msg["total_files"], 3)
            self.assertEqual(batch_complete_msg["processed"], 3)
            self.assertEqual(len(batch_complete_msg["files"]), 3)

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_batch_files_queue_smart_resume(self, mock_whisper_class):
        """Vérifie que la file d'attente saute un fichier si son .txt existe déjà dans output_dir."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model
        
        class DummyInfo:
            duration = 10.0
            language = "fr"
            language_probability = 0.99
            
        mock_model.transcribe.return_value = ([], DummyInfo())
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f1 = tmp_path / "deja_fait.mp3"
            f2 = tmp_path / "a_faire.mp3"
            f1.write_bytes(b"audio1")
            f2.write_bytes(b"audio2")
            
            out_dir = tmp_path / "output"
            out_dir.mkdir(parents=True, exist_ok=True)
            # Simuler un fichier déjà transcrit
            (out_dir / "deja_fait.txt").write_text("Déjà transcrit précédemment", encoding="utf-8")
            
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")
            
            transcribe_batch_threaded(
                files=[f1, f2],
                output_dir=out_dir,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event
            )
            
            messages = []
            while not q.empty():
                messages.append(q.get())
                
            statuses = [m["status"] for m in messages]
            self.assertIn("file_skipped", statuses)
            
            batch_complete_msg = [m for m in messages if m["status"] == "batch_complete"][0]
            self.assertEqual(batch_complete_msg["total_files"], 2)
            self.assertEqual(batch_complete_msg["processed"], 1)
            self.assertEqual(batch_complete_msg["skipped"], 1)

    def test_create_batch_zip(self):
        """Vérifie la génération en mémoire de l'archive ZIP contenant tous les fichiers d'export."""
        import zipfile
        import io
        from ui.app import create_batch_zip
        
        # Cas 1 : liste vide
        self.assertEqual(create_batch_zip([]), b"")
        
        # Cas 2 : fichiers réels
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            txt1 = tmp_path / "audio1.txt"
            srt1 = tmp_path / "audio1.srt"
            txt2 = tmp_path / "audio2.txt"
            
            txt1.write_text("Texte 1", encoding="utf-8")
            srt1.write_text("00:00:00 --> 00:00:05\nTexte 1", encoding="utf-8")
            txt2.write_text("Texte 2", encoding="utf-8")
            
            files_meta = [
                {"filename": "audio1.mp3", "txt_path": str(txt1), "srt_path": str(srt1), "md_path": ""},
                {"filename": "audio2.mp3", "txt_path": str(txt2), "srt_path": "", "md_path": ""}
            ]
            
            zip_bytes = create_batch_zip(files_meta)
            self.assertTrue(len(zip_bytes) > 0)
            
            # Vérifier le contenu de l'archive ZIP
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                namelist = zf.namelist()
                self.assertIn("audio1.txt", namelist)
                self.assertIn("audio1.srt", namelist)
                self.assertIn("audio2.txt", namelist)
                self.assertEqual(zf.read("audio1.txt").decode("utf-8"), "Texte 1")

    @patch("core.transcription_engine.WhisperModel")
    @patch("core.translation_engine.is_translation_model_installed", return_value=True)
    @patch("core.translation_engine.get_translation_engine")
    def test_transcribe_file_with_target_translation(
        self, mock_get_trans_engine, mock_model_installed, mock_whisper_class
    ):
        """Vérifie que la transcription avec target_translation produit les fichiers traduits."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model

        class DummySegment:
            def __init__(self, start, end, text):
                self.start = start
                self.end = end
                self.text = text

        class DummyInfo:
            duration = 5.0
            language = "fr"
            language_probability = 0.99

        mock_model.transcribe.return_value = (
            [DummySegment(0.0, 5.0, "Bonjour le monde")],
            DummyInfo()
        )

        mock_trans_engine = MagicMock()
        mock_get_trans_engine.return_value = mock_trans_engine

        from core.translation_engine import TranslatedSegment
        mock_trans_engine.translate_segments.return_value = [
            TranslatedSegment(0.0, 5.0, "Hello world")
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_audio = tmp_path / "audio.mp3"
            fake_audio.write_bytes(b"content")

            out_dir = tmp_path / "out"
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")

            transcribe_file_threaded(
                file_path=fake_audio,
                output_dir=out_dir,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                target_translation="en"
            )

            messages = []
            while not q.empty():
                messages.append(q.get())

            statuses = [m["status"] for m in messages]
            self.assertIn("translating", statuses)
            self.assertIn("file_complete", statuses)

            # Vérifier création des fichiers d'origine et traduits
            self.assertTrue((out_dir / "audio.txt").exists())
            self.assertTrue((out_dir / "audio_en.txt").exists())
            self.assertTrue((out_dir / "audio_en.srt").exists())
            self.assertTrue((out_dir / "audio_en.md").exists())

            # Vérifier contenu
            self.assertIn("Hello world", (out_dir / "audio_en.txt").read_text(encoding="utf-8"))

            file_complete_msg = [m for m in messages if m["status"] == "file_complete"][0]
            self.assertEqual(file_complete_msg["target_translation"], "en")
            self.assertIn("Hello world", file_complete_msg["translated_text"])

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_emits_serialized_segments(self, mock_whisper_class):
        """Vérifie que transcribe_file_threaded émet bien les segments sérialisés pour l'éditeur."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model

        class DummySegment:
            def __init__(self, start, end, text, speaker="Alice"):
                self.start = start
                self.end = end
                self.text = text
                self.speaker = speaker

        class DummyInfo:
            duration = 10.0
            language = "fr"
            language_probability = 0.99

        mock_model.transcribe.return_value = (
            [
                DummySegment(0.0, 4.5, "Bonjour à tous."),
                DummySegment(4.5, 10.0, "Bienvenue dans l'éditeur.")
            ],
            DummyInfo()
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_audio = tmp_path / "interview_ed.mp3"
            fake_audio.write_bytes(b"content")

            out_dir = tmp_path / "out"
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

            file_complete_msg = [m for m in messages if m["status"] == "file_complete"][0]
            self.assertIn("segments", file_complete_msg)
            segs = file_complete_msg["segments"]
            self.assertEqual(len(segs), 2)
            self.assertEqual(segs[0]["id"], 1)
            self.assertEqual(segs[0]["text"], "Bonjour à tous.")
            self.assertEqual(segs[0]["start"], 0.0)
            self.assertEqual(segs[0]["end"], 4.5)
            self.assertEqual(segs[0]["speaker"], "Alice")
            self.assertEqual(segs[1]["id"], 2)
            self.assertEqual(segs[1]["text"], "Bienvenue dans l'éditeur.")

    @patch("core.audio_preprocessor.cleanup_preprocessed_file")
    @patch("core.audio_preprocessor.preprocess_audio")
    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_with_preprocessing_enabled(self, mock_whisper_class, mock_preprocess, mock_cleanup):
        """Vérifie que le prétraitement acoustique FFmpeg est déclenché et nettoyé après transcription."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model

        class DummyInfo:
            duration = 10.0
            language = "fr"
            language_probability = 0.98

        class DummySegment:
            start = 0.0
            end = 5.0
            text = "Audio optimisé"
            speaker = None

        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_video = tmp_path / "conference.mp4"
            source_video.write_bytes(b"video content")
            fake_preprocessed_wav = tmp_path / "preprocessed_conference.wav"
            fake_preprocessed_wav.write_bytes(b"wav content")

            mock_preprocess.return_value = (
                fake_preprocessed_wav,
                {
                    "preprocessed": True,
                    "normalized": True,
                    "denoised": True,
                    "filters_applied": "highpass, lowpass, dynaudnorm"
                }
            )

            out_dir = tmp_path / "out"
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")

            transcribe_file_threaded(
                file_path=source_video,
                output_dir=out_dir,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                preprocess_audio=True,
                normalize_volume=True,
                denoise=True
            )

            # Vérification de l'appel à preprocess_audio
            mock_preprocess.assert_called_once()
            _, kwargs = mock_preprocess.call_args
            self.assertEqual(kwargs["input_path"], source_video)
            self.assertTrue(kwargs["normalize_volume"])
            self.assertTrue(kwargs["denoise"])

            # Vérification de l'appel à Whisper sur le fichier prétraité
            mock_model.transcribe.assert_called_once()
            called_audio_arg = mock_model.transcribe.call_args[0][0]
            self.assertEqual(called_audio_arg, str(fake_preprocessed_wav))

            # Vérification du nettoyage du fichier temporaire
            mock_cleanup.assert_called_once_with(fake_preprocessed_wav, source_video)

            # Vérification des messages émis
            messages = []
            while not q.empty():
                messages.append(q.get())

            file_complete = [m for m in messages if m["status"] == "file_complete"][0]
            self.assertTrue(file_complete["preprocessed"])
            self.assertIn("dynaudnorm", file_complete["filters_applied"])

    @patch("core.audio_preprocessor.cleanup_preprocessed_file")
    @patch("core.audio_preprocessor.preprocess_audio")
    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_batch_with_preprocessing(self, mock_whisper_class, mock_preprocess, mock_cleanup):
        """Vérifie que le prétraitement acoustique FFmpeg fonctionne sur une file d'attente multi-fichiers."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model

        class DummyInfo:
            duration = 5.0
            language = "fr"
            language_probability = 0.95

        class DummySegment:
            start = 0.0
            end = 2.5
            text = "Segment batch"
            speaker = None

        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f1 = tmp_path / "vid1.mp4"
            f2 = tmp_path / "vid2.mkv"
            f1.write_bytes(b"vid1")
            f2.write_bytes(b"vid2")

            wav1 = tmp_path / "pre_vid1.wav"
            wav2 = tmp_path / "pre_vid2.wav"
            wav1.write_bytes(b"wav1")
            wav2.write_bytes(b"wav2")

            mock_preprocess.side_effect = [
                (wav1, {"preprocessed": True, "filters_applied": "dynaudnorm"}),
                (wav2, {"preprocessed": True, "filters_applied": "dynaudnorm"})
            ]

            out_dir = tmp_path / "out_batch"
            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")

            transcribe_batch_threaded(
                files=[f1, f2],
                output_dir=out_dir,
                profile=profile,
                progress_queue=q,
                stop_event=stop_event,
                preprocess_audio=True,
                normalize_volume=True,
                denoise=False
            )

            self.assertEqual(mock_preprocess.call_count, 2)
            self.assertEqual(mock_cleanup.call_count, 2)

            messages = []
            while not q.empty():
                messages.append(q.get())

            batch_complete = [m for m in messages if m["status"] == "batch_complete"][0]
            self.assertEqual(batch_complete["processed"], 2)
            self.assertEqual(batch_complete["total_files"], 2)
            self.assertIn("total_elapsed_seconds", batch_complete)

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_file_emits_eta_and_speed_metrics(self, mock_whisper_class):
        """Vérifie que les métriques d'ETA, de vitesse et de temps écoulé sont émises dans la queue."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model

        class DummySegment:
            def __init__(self, start, end, text):
                self.start = start
                self.end = end
                self.text = text

        class DummyInfo:
            duration = 60.0
            language = "fr"
            language_probability = 0.99

        mock_model.transcribe.return_value = (
            [DummySegment(0.0, 15.0, "Segment 1"), DummySegment(15.0, 30.0, "Segment 2")],
            DummyInfo()
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            fake_audio = tmp_path / "audio_eta.mp3"
            fake_audio.write_bytes(b"content")

            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")

            transcribe_file_threaded(
                file_path=fake_audio,
                output_dir=tmp_path / "out",
                profile=profile,
                progress_queue=q,
                stop_event=stop_event
            )

            messages = []
            while not q.empty():
                messages.append(q.get())

            prog_msgs = [m for m in messages if m["status"] == "progress"]
            self.assertEqual(len(prog_msgs), 2)
            for pm in prog_msgs:
                self.assertIn("speed_ratio", pm)
                self.assertIn("speed_str", pm)
                self.assertIn("eta_seconds", pm)
                self.assertIn("eta_str", pm)
                self.assertIn("elapsed_seconds", pm)
                self.assertIn("elapsed_str", pm)

            file_comp = [m for m in messages if m["status"] == "file_complete"][0]
            self.assertIn("elapsed_seconds", file_comp)
            self.assertIn("duration", file_comp)

    @patch("core.transcription_engine.WhisperModel")
    def test_transcribe_batch_emits_batch_eta_metrics(self, mock_whisper_class):
        """Vérifie que le traitement par lot propage l'ETA globale du lot."""
        mock_model = MagicMock()
        mock_whisper_class.return_value = mock_model

        class DummySegment:
            start = 0.0
            end = 10.0
            text = "Segment batch"

        class DummyInfo:
            duration = 20.0
            language = "fr"
            language_probability = 0.95

        mock_model.transcribe.return_value = ([DummySegment()], DummyInfo())

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            f1 = tmp_path / "b1.mp3"
            f2 = tmp_path / "b2.mp3"
            f1.write_bytes(b"1")
            f2.write_bytes(b"2")

            q = queue.Queue()
            stop_event = threading.Event()
            profile = HardwareProfile("cpu", "int8", "small")

            transcribe_batch_threaded(
                files=[f1, f2],
                output_dir=tmp_path / "out",
                profile=profile,
                progress_queue=q,
                stop_event=stop_event
            )

            messages = []
            while not q.empty():
                messages.append(q.get())

            prog_msgs = [m for m in messages if m["status"] == "progress"]
            self.assertTrue(len(prog_msgs) >= 2)
            for pm in prog_msgs:
                self.assertIn("batch_eta_str", pm)
                self.assertIn("batch_elapsed_str", pm)

            batch_comp = [m for m in messages if m["status"] == "batch_complete"][0]
            self.assertIn("total_elapsed_seconds", batch_comp)


if __name__ == "__main__":
    unittest.main()






