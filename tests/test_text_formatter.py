import unittest
from core.text_formatter import format_timestamp, generate_srt, generate_txt, generate_markdown

class DummySegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

class TestTextFormatter(unittest.TestCase):
    def setUp(self):
        self.segments = [
            DummySegment(0.0, 5.5, "Bonjour et bienvenue."),
            DummySegment(5.5, 12.125, " Voici un test de sous-titres.")
        ]
        
    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(0), "00:00:00,000")
        self.assertEqual(format_timestamp(5.5), "00:00:05,500")
        self.assertEqual(format_timestamp(3661.123), "01:01:01,123")

    def test_generate_srt(self):
        srt = generate_srt(self.segments)
        self.assertIn("1\n00:00:00,000 --> 00:00:05,500\nBonjour et bienvenue.", srt)
        self.assertIn("2\n00:00:05,500 --> 00:00:12,125\nVoici un test de sous-titres.", srt)
        
    def test_generate_txt(self):
        txt = generate_txt(self.segments)
        self.assertEqual(txt, "Bonjour et bienvenue.\nVoici un test de sous-titres.")
        
    def test_generate_markdown(self):
        meta = {
            "filename": "test.mp3",
            "duration": 12.125,
            "language": "fr",
            "model": "small"
        }
        md = generate_markdown(self.segments, meta)
        
        self.assertIn("title: \"Transcription de test.mp3\"", md)
        self.assertIn("duration_seconds: 12.12", md)
        self.assertIn("language: \"fr\"", md)
        self.assertIn("model: \"small\"", md)
        self.assertIn("# Transcription", md)
        self.assertIn("Bonjour et bienvenue.\nVoici un test de sous-titres.", md)

if __name__ == "__main__":
    unittest.main()
