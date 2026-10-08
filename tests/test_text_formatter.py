import unittest
from core.text_formatter import format_timestamp, generate_srt, generate_txt, generate_markdown


class DummySegment:
    def __init__(self, start, end, text, speaker=None):
        self.start = start
        self.end = end
        self.text = text
        if speaker is not None:
            self.speaker = speaker


class TestTextFormatter(unittest.TestCase):
    def setUp(self):
        self.segments = [
            DummySegment(0.0, 5.5, "Bonjour et bienvenue."),
            DummySegment(5.5, 12.125, " Voici un test de sous-titres.")
        ]
        self.diarized_segments = [
            DummySegment(0.0, 4.0, "Bonjour tout le monde.", speaker="Locuteur 1"),
            DummySegment(4.5, 8.0, "Bonjour, merci d'être là.", speaker="Locuteur 2")
        ]
        
    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(0), "00:00:00,000")
        self.assertEqual(format_timestamp(5.5), "00:00:05,500")
        self.assertEqual(format_timestamp(3661.123), "01:01:01,123")

    def test_generate_srt(self):
        srt = generate_srt(self.segments)
        self.assertIn("1\n00:00:00,000 --> 00:00:05,500\nBonjour et bienvenue.", srt)
        self.assertIn("2\n00:00:05,500 --> 00:00:12,125\nVoici un test de sous-titres.", srt)

    def test_generate_srt_with_speakers(self):
        srt = generate_srt(self.diarized_segments)
        self.assertIn("[Locuteur 1] Bonjour tout le monde.", srt)
        self.assertIn("[Locuteur 2] Bonjour, merci d'être là.", srt)
        
    def test_generate_txt(self):
        txt = generate_txt(self.segments)
        self.assertEqual(txt, "Bonjour et bienvenue.\nVoici un test de sous-titres.")

    def test_generate_txt_with_speakers(self):
        txt = generate_txt(self.diarized_segments)
        self.assertEqual(
            txt, 
            "[Locuteur 1] Bonjour tout le monde.\n[Locuteur 2] Bonjour, merci d'être là."
        )
        
    def test_generate_markdown(self):
        meta = {
            "filename": "test.mp3",
            "duration": 12.125,
            "language": "fr",
            "model": "small"
        }
        md = generate_markdown(self.segments, meta)
        
        self.assertIn('title: "Transcription de test.mp3"', md)
        self.assertIn("duration_seconds: 12.12", md)
        self.assertIn('language: "fr"', md)
        self.assertIn('model: "small"', md)
        self.assertIn("# Transcription", md)
        self.assertIn("Bonjour et bienvenue.\nVoici un test de sous-titres.", md)

    def test_generate_markdown_with_speakers(self):
        meta = {
            "filename": "interview.mp3",
            "duration": 8.0,
            "language": "fr",
            "model": "small",
            "speakers": ["Locuteur 1", "Locuteur 2"]
        }
        md = generate_markdown(self.diarized_segments, meta)
        
        self.assertIn('speakers: ["Locuteur 1", "Locuteur 2"]', md)
        self.assertIn("- `[00:00:00 -> 00:00:04]` **Locuteur 1** : Bonjour tout le monde.", md)
        self.assertIn("- `[00:00:04 -> 00:00:08]` **Locuteur 2** : Bonjour, merci d'être là.", md)


if __name__ == "__main__":
    unittest.main()
