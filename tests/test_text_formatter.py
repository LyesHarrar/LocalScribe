import unittest
from core.text_formatter import (
    format_timestamp, 
    generate_srt, 
    generate_txt, 
    generate_markdown,
    TranscriptionSegment,
    parse_timestamp,
    parse_srt
)


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

    def test_transcription_segment_dataclass(self):
        seg = TranscriptionSegment(start=1.234, end=5.678, text="Test segment", speaker="Alice", id=1)
        d = seg.to_dict()
        self.assertEqual(d["start"], 1.234)
        self.assertEqual(d["end"], 5.678)
        self.assertEqual(d["text"], "Test segment")
        self.assertEqual(d["speaker"], "Alice")
        self.assertEqual(d["id"], 1)

        restored = TranscriptionSegment.from_dict(d)
        self.assertEqual(restored.start, seg.start)
        self.assertEqual(restored.end, seg.end)
        self.assertEqual(restored.text, seg.text)
        self.assertEqual(restored.speaker, seg.speaker)
        self.assertEqual(restored.id, seg.id)

    def test_parse_timestamp(self):
        self.assertAlmostEqual(parse_timestamp("00:00:00,000"), 0.0)
        self.assertAlmostEqual(parse_timestamp("00:01:23,456"), 83.456)
        self.assertAlmostEqual(parse_timestamp("01:02:03.500"), 3723.5)
        self.assertAlmostEqual(parse_timestamp("02:15"), 135.0)
        self.assertAlmostEqual(parse_timestamp("12.5"), 12.5)
        self.assertEqual(parse_timestamp("invalid"), 0.0)

    def test_parse_srt(self):
        srt_raw = """1
00:00:01,000 --> 00:00:04,500
[Alice] Bonjour tout le monde.

2
00:00:05,200 --> 00:00:09,800
Bob: Bonjour Alice, comment vas-tu ?

3
00:00:10,000 --> 00:00:14,000
Je vais très bien merci.
Deuxième ligne de texte.
"""
        parsed = parse_srt(srt_raw)
        self.assertEqual(len(parsed), 3)

        self.assertEqual(parsed[0].id, 1)
        self.assertAlmostEqual(parsed[0].start, 1.0)
        self.assertAlmostEqual(parsed[0].end, 4.5)
        self.assertEqual(parsed[0].speaker, "Alice")
        self.assertEqual(parsed[0].text, "Bonjour tout le monde.")

        self.assertEqual(parsed[1].id, 2)
        self.assertAlmostEqual(parsed[1].start, 5.2)
        self.assertAlmostEqual(parsed[1].end, 9.8)
        self.assertEqual(parsed[1].speaker, "Bob")
        self.assertEqual(parsed[1].text, "Bonjour Alice, comment vas-tu ?")

        self.assertEqual(parsed[2].id, 3)
        self.assertAlmostEqual(parsed[2].start, 10.0)
        self.assertAlmostEqual(parsed[2].end, 14.0)
        self.assertIsNone(parsed[2].speaker)
        self.assertIn("Je vais très bien merci", parsed[2].text)
        self.assertIn("Deuxième ligne de texte", parsed[2].text)

    def test_parse_srt_empty(self):
        self.assertEqual(parse_srt(""), [])
        self.assertEqual(parse_srt("   \n\n  "), [])


if __name__ == "__main__":
    unittest.main()

