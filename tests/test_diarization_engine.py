"""
tests/test_diarization_engine.py — Tests unitaires pour le moteur de diarisation
Valide l'alignement temporel des locuteurs avec les segments de transcription Whisper.
"""

import unittest
from core.diarization_engine import (
    DiarizationSegment,
    TranscriptSegmentWrapper,
    assign_speakers_to_whisper_segments
)


class MockWhisperSegment:
    """Segment factice produit par faster-whisper."""
    def __init__(self, start: float, end: float, text: str):
        self.start = start
        self.end = end
        self.text = text


class TestDiarizationEngine(unittest.TestCase):
    
    def test_assign_speakers_empty(self):
        """Cas où la liste des segments Whisper est vide."""
        segments, speakers = assign_speakers_to_whisper_segments([], [])
        self.assertEqual(segments, [])
        self.assertEqual(speakers, [])

    def test_assign_speakers_no_diarization_results(self):
        """Cas où aucun locuteur n'a été détecté par la diarisation."""
        whisper_segs = [
            MockWhisperSegment(0.0, 3.0, "Bonjour tout le monde."),
            MockWhisperSegment(3.5, 6.0, "Comment allez-vous ?")
        ]
        segments, speakers = assign_speakers_to_whisper_segments(whisper_segs, [])
        self.assertEqual(len(segments), 2)
        self.assertEqual(speakers, ["Locuteur 1"])
        self.assertEqual(segments[0].speaker, "Locuteur 1")
        self.assertEqual(segments[1].speaker, "Locuteur 1")

    def test_assign_speakers_exact_matches(self):
        """Cas nominal où chaque segment correspond exactement à un locuteur."""
        whisper_segs = [
            MockWhisperSegment(0.0, 4.0, "Bonjour Alice."),
            MockWhisperSegment(4.5, 9.0, "Bonjour Bob, tout va bien ?"),
            MockWhisperSegment(9.2, 13.0, "Parfait, continuons la réunion.")
        ]
        diar_segs = [
            DiarizationSegment(start=0.0, end=4.2, speaker_id=0, speaker="Locuteur 1"),
            DiarizationSegment(start=4.4, end=9.1, speaker_id=1, speaker="Locuteur 2"),
            DiarizationSegment(start=9.1, end=13.0, speaker_id=0, speaker="Locuteur 1")
        ]
        
        segments, speakers = assign_speakers_to_whisper_segments(whisper_segs, diar_segs)
        
        self.assertEqual(len(segments), 3)
        self.assertEqual(speakers, ["Locuteur 1", "Locuteur 2"])
        self.assertEqual(segments[0].speaker, "Locuteur 1")
        self.assertEqual(segments[1].speaker, "Locuteur 2")
        self.assertEqual(segments[2].speaker, "Locuteur 1")

    def test_assign_speakers_majority_overlap(self):
        """Cas où un segment Whisper chevauche deux locuteurs : le plus long gagne."""
        whisper_segs = [
            # Segment de 2.0 à 7.0 (5 secondes total)
            # 2.0 -> 3.0 (1s avec Locuteur 1)
            # 3.0 -> 7.0 (4s avec Locuteur 2)
            MockWhisperSegment(2.0, 7.0, "Je commence et tu finis ma phrase.")
        ]
        diar_segs = [
            DiarizationSegment(start=0.0, end=3.0, speaker_id=0, speaker="Locuteur 1"),
            DiarizationSegment(start=3.0, end=10.0, speaker_id=1, speaker="Locuteur 2")
        ]
        
        segments, speakers = assign_speakers_to_whisper_segments(whisper_segs, diar_segs)
        
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0].speaker, "Locuteur 2")
        self.assertEqual(speakers, ["Locuteur 2"])

    def test_assign_speakers_fallback_gap(self):
        """Cas où un court segment Whisper tombe dans un petit blanc sans diarisation."""
        whisper_segs = [
            MockWhisperSegment(0.0, 4.0, "Première prise de parole."),
            # Segment Whisper isolé entre 5.0 et 5.5
            MockWhisperSegment(5.0, 5.5, "Oui tout à fait.")
        ]
        diar_segs = [
            DiarizationSegment(start=0.0, end=4.0, speaker_id=0, speaker="Locuteur 1"),
            DiarizationSegment(start=6.0, end=10.0, speaker_id=1, speaker="Locuteur 2")
        ]
        
        segments, speakers = assign_speakers_to_whisper_segments(whisper_segs, diar_segs)
        
        self.assertEqual(len(segments), 2)
        # Doit être attribué au locuteur le plus proche dans le temps (ici Locuteur 2 à 0.5s de distance)
        self.assertEqual(segments[0].speaker, "Locuteur 1")
        self.assertEqual(segments[1].speaker, "Locuteur 2")


if __name__ == "__main__":
    unittest.main()
